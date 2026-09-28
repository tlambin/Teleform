"""Module de gestion et de recrutement de l'équipe opérationnelle (Staff)."""

import html
import logging
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from ui.admin import users as ui

logger = logging.getLogger(__name__)


class StaffManager:
    """Gestionnaire de l'équipe opérationnelle (recrutement, droits et révocation du staff)."""

    WAITING_STAFF_ID = 1
    WAITING_STAFF_CONFIG = 2
    WAITING_STAFF_REMOVE = 3
    WAITING_STAFF_CONFIRMATION = 4

    def __init__(self, db_manager, config, interface_manager=None):
        self.db_manager = db_manager
        self.config = config
        self.interface = interface_manager
        logger.info("StaffManager initialisé avec pré-configuration avant validation")

    def set_interface_manager(self, interface_manager):
        self.interface = interface_manager

    def _get_interface(self):
        if not self.interface:
            from utils.interface_manager import InterfaceManager
            self.interface = InterfaceManager(self.config, self.db_manager)
        return self.interface

    def _has_staff_management_perm(self, user_id: int) -> bool:
        if self.config.is_owner(user_id):
            return True
        if self.config.is_admin(user_id):
            privs = self.db_manager.get_admin_privileges(user_id)
            return privs.get("can_manage_staff", True)
        return False

    async def _safe_edit_or_send(self, query, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None):
        if query.message and query.message.photo:
            chat_id = query.message.chat_id
            try:
                await query.message.delete()
            except Exception:
                pass
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="HTML",
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
        else:
            try:
                await query.edit_message_text(
                    text=text,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                    disable_web_page_preview=True
                )
            except Exception:
                if query.message:
                    await query.message.reply_text(
                        text=text,
                        parse_mode="HTML",
                        reply_markup=reply_markup,
                        disable_web_page_preview=True
                    )

    # ==================== LISTE DU STAFF ====================

    async def list_staff(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not user or not self._has_staff_management_perm(user.id):
            if update.message:
                await update.message.reply_text("❌ Action réservée aux responsables d'équipe.")
            return

        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT s.user_id, s.alias, s.date_added, s.perm_reseaux, s.perm_type, s.is_paused, s.is_trial,
                           u.first_name, u.username,
                           ua.first_name AS nom_ajouteur
                    FROM staff s
                    LEFT JOIN users u ON s.user_id = u.user_id
                    LEFT JOIN users ua ON s.added_by = ua.user_id
                    ORDER BY s.date_added ASC
                    """
                )
                staff_members = cursor.fetchall()

            text = ui.format_staff_list_text(staff_members)
            if update.message:
                await update.message.reply_text(text, parse_mode="HTML")

        except Exception as exc:
            logger.error("Erreur récupération liste staff : %s", exc, exc_info=True)
            if update.message:
                await update.message.reply_text("❌ Impossible de charger la liste des opérateurs.")

    # ==================== RECRUTEMENT D'UN OPÉRATEUR ====================

    async def staff_ajouter(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user = update.effective_user
        if not query or not user or not self._has_staff_management_perm(user.id):
            return ConversationHandler.END

        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute("SELECT COUNT(*) AS count FROM staff")
                count = cursor.fetchone()["count"]

            text, keyboard = ui.get_staff_add_prompt_content(count)
            await self._safe_edit_or_send(query, context, text, reply_markup=keyboard)
            return self.WAITING_STAFF_ID

        except Exception as exc:
            logger.error("Erreur interface ajout staff : %s", exc, exc_info=True)
            return ConversationHandler.END

    async def traiter_staff_ajouter(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Valide l'utilisateur cible et ouvre le panneau de pré-configuration des droits."""
        if not update.message or not update.message.text:
            return self.WAITING_STAFF_ID

        user = update.effective_user
        if not user or not self._has_staff_management_perm(user.id):
            return ConversationHandler.END

        saisie = update.message.text.strip().replace("@", "")

        try:
            with self.db_manager.get_cursor() as cursor:
                if saisie.isdigit():
                    cursor.execute("SELECT * FROM users WHERE user_id = %s", (int(saisie),))
                else:
                    cursor.execute("SELECT * FROM users WHERE LOWER(username) = LOWER(%s)", (saisie.lower(),))
                user_data = cursor.fetchone()

            if not user_data:
                saisie_esc = html.escape(saisie)
                await update.message.reply_text(
                    f"❌ L'utilisateur <code>{saisie_esc}</code> est introuvable dans la base.\n"
                    "Il doit obligatoirement envoyer /start au bot avant d'être recruté.",
                    parse_mode="HTML"
                )
                return self.WAITING_STAFF_ID

            target_id = int(user_data["user_id"])

            with self.db_manager.get_cursor() as cursor:
                cursor.execute("SELECT alias FROM staff WHERE user_id = %s", (target_id,))
                if cursor.fetchone():
                    await update.message.reply_text("⚠️ Cet utilisateur fait déjà partie de l'équipe Staff.")
                    return self.WAITING_STAFF_ID

            base_alias = user_data.get("first_name") or user_data.get("username") or f"Staff{target_id}"
            alias = str(base_alias)[:20]

            context.user_data["pending_staff_recruit"] = {
                "target_id": target_id,
                "alias": alias,
                "first_name": user_data.get("first_name") or "Utilisateur",
                "reseaux": "all",
                "type": "all",
                "orientation": "all",
                "is_trial": True
            }

            await self._render_recruit_config_menu(update, context)
            return self.WAITING_STAFF_CONFIG

        except Exception as exc:
            logger.error("Erreur vérification cible staff : %s", exc, exc_info=True)
            await update.message.reply_text("❌ Erreur technique lors de la vérification.")
            return ConversationHandler.END

    async def _render_recruit_config_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Affiche ou met à jour le panneau de pré-configuration."""
        cfg = context.user_data.get("pending_staff_recruit", {})
        text, kb = ui.build_recruit_config_content(cfg)

        if update.callback_query:
            await update.callback_query.answer()
            await self._safe_edit_or_send(update.callback_query, context, text, reply_markup=kb)
        elif update.message:
            await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb)

    async def handle_recruit_config_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Gère les clics sur les filtres de pré-configuration et la confirmation finale."""
        query = update.callback_query
        if not query or not query.data:
            return self.WAITING_STAFF_CONFIG

        data = query.data
        cfg = context.user_data.get("pending_staff_recruit")
        if not cfg:
            await query.answer("❌ Session expirée.", show_alert=True)
            return ConversationHandler.END

        if data.startswith("cfgadd_res_"):
            cfg["reseaux"] = data.replace("cfgadd_res_", "")
            await self._render_recruit_config_menu(update, context)
            return self.WAITING_STAFF_CONFIG

        elif data.startswith("cfgadd_typ_"):
            cfg["type"] = data.replace("cfgadd_typ_", "")
            await self._render_recruit_config_menu(update, context)
            return self.WAITING_STAFF_CONFIG

        elif data.startswith("cfgadd_ori_"):
            cfg["orientation"] = data.replace("cfgadd_ori_", "")
            await self._render_recruit_config_menu(update, context)
            return self.WAITING_STAFF_CONFIG

        elif data == "cfgadd_trial_toggle":
            cfg["is_trial"] = not cfg.get("is_trial", True)
            await self._render_recruit_config_menu(update, context)
            return self.WAITING_STAFF_CONFIG

        elif data == "cfgadd_confirm_save":
            await query.answer()
            return await self._finalize_staff_recruitment(update, context)

        return self.WAITING_STAFF_CONFIG

    async def _finalize_staff_recruitment(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Insère définitivement le membre dans la table staff avec les droits validés."""
        cfg = context.user_data.pop("pending_staff_recruit", None)
        if not cfg:
            return ConversationHandler.END

        target_id = cfg["target_id"]
        alias = cfg["alias"]
        reseaux = cfg["reseaux"]
        typ = cfg["type"]
        orientation = cfg["orientation"]
        is_trial = cfg["is_trial"]
        user_id_admin = update.effective_user.id

        try:
            with self.db_manager.transaction() as cursor:
                cursor.execute(
                    """
                    INSERT INTO staff (
                        user_id, alias, added_by, perm_reseaux, perm_type, perm_orientation,
                        alias_locked, is_trial, date_added
                    ) VALUES (%s, %s, %s, %s, %s, %s, FALSE, %s, NOW())
                    """,
                    (target_id, alias, user_id_admin, reseaux, typ, orientation, is_trial)
                )

            self.config.add_staff(target_id)
            logger.info("Opérateur Staff recruté : %s (%s) | Reseaux=%s, Type=%s, Ori=%s, Trial=%s",
                        target_id, alias, reseaux, typ, orientation, is_trial)

            welcome_msg, welcome_kb = ui.build_recruit_welcome_message(alias, is_trial)
            try:
                await context.bot.send_message(
                    chat_id=target_id,
                    text=welcome_msg,
                    parse_mode="HTML",
                    reply_markup=welcome_kb
                )
            except Exception as notif_err:
                logger.warning("Impossible de notifier le membre %s : %s", target_id, notif_err)

            msg_admin, kb_confirm = ui.build_recruit_admin_summary(cfg)

            if update.callback_query:
                await self._safe_edit_or_send(update.callback_query, context, msg_admin, reply_markup=kb_confirm)
            else:
                await update.message.reply_text(msg_admin, parse_mode="HTML", reply_markup=kb_confirm)

            return ConversationHandler.END

        except Exception as exc:
            logger.error("Erreur enregistrement final staff : %s", exc, exc_info=True)
            if update.callback_query:
                await update.callback_query.answer("❌ Erreur technique lors de l'enregistrement.", show_alert=True)
            return ConversationHandler.END

    async def cancel_staff_add(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data.pop("pending_staff_recruit", None)
        query = update.callback_query
        if query:
            await query.answer()
            interface = self._get_interface()
            message, keyboard = interface.get_gerer_staff_menu()
            await self._safe_edit_or_send(query, context, message, reply_markup=keyboard)
        return ConversationHandler.END

    # ==================== RÉVOCATION D'UN OPÉRATEUR ====================

    async def staff_supprimer(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user = update.effective_user
        if not query or not user or not self._has_staff_management_perm(user.id):
            return ConversationHandler.END

        await query.answer()

        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT s.user_id, s.alias, s.date_added, u.first_name, u.username
                    FROM staff s
                    LEFT JOIN users u ON s.user_id = u.user_id
                    ORDER BY s.date_added DESC
                    """
                )
                staff_members = cursor.fetchall()

            text, keyboard = ui.build_staff_remove_list_content(staff_members)
            if not staff_members:
                await self._safe_edit_or_send(query, context, text, reply_markup=keyboard)
                return ConversationHandler.END

            context.user_data["staff_remove_list"] = staff_members
            await self._safe_edit_or_send(query, context, text, reply_markup=keyboard)
            return self.WAITING_STAFF_REMOVE

        except Exception as exc:
            logger.error("Erreur affichage suppression staff : %s", exc, exc_info=True)
            return ConversationHandler.END

    async def traiter_staff_supprimer(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text:
            return self.WAITING_STAFF_REMOVE

        user = update.effective_user
        if not user or not self._has_staff_management_perm(user.id):
            return ConversationHandler.END

        choix = update.message.text.strip()
        staff_list = context.user_data.get("staff_remove_list", [])

        if not choix.isdigit():
            await update.message.reply_text("❌ Veuillez entrer un numéro valide issu de la liste :")
            return self.WAITING_STAFF_REMOVE

        idx = int(choix) - 1
        if idx < 0 or idx >= len(staff_list):
            await update.message.reply_text(f"❌ Numéro hors plage. Choisissez entre 1 et {len(staff_list)} :")
            return self.WAITING_STAFF_REMOVE

        selected = staff_list[idx]
        context.user_data["target_staff_to_remove"] = selected

        text, keyboard = ui.build_staff_remove_confirmation_content(selected)
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)
        return self.WAITING_STAFF_CONFIRMATION

    async def confirmer_staff_suppression(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user = update.effective_user
        if not query or not user or not self._has_staff_management_perm(user.id):
            return ConversationHandler.END

        await query.answer()

        selected = context.user_data.pop("target_staff_to_remove", None)
        context.user_data.pop("staff_remove_list", None)

        if not selected:
            await self._safe_edit_or_send(query, context, "❌ Erreur : aucun opérateur sélectionné.")
            return ConversationHandler.END

        target_id = int(selected["user_id"])
        try:
            with self.db_manager.transaction() as cursor:
                cursor.execute("DELETE FROM staff WHERE user_id = %s", (target_id,))

            self.config.remove_staff(target_id)
            logger.info("Droits staff supprimés pour %s par %s", target_id, user.id)

            text, keyboard = ui.get_staff_removed_success_content(selected.get("alias"), target_id)
            await self._safe_edit_or_send(query, context, text, reply_markup=keyboard)
            return ConversationHandler.END

        except Exception as exc:
            logger.error("Erreur exécution révocation staff : %s", exc, exc_info=True)
            await self._safe_edit_or_send(query, context, "❌ Erreur technique lors de la révocation.")
            return ConversationHandler.END

    async def cancel_staff_remove(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        context.user_data.pop("staff_remove_list", None)
        context.user_data.pop("target_staff_to_remove", None)

        if query:
            await query.answer()
            interface = self._get_interface()
            message, keyboard = interface.get_gerer_staff_menu()
            await self._safe_edit_or_send(query, context, message, reply_markup=keyboard)
        return ConversationHandler.END