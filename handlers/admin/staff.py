"""Module de gestion et de recrutement de l'équipe opérationnelle (Staff)."""

import html
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler
from utils.validators import convert_utc_to_paris

logger = logging.getLogger(__name__)


class StaffManager:
    """Gestionnaire de l'équipe opérationnelle (recrutement, droits et révocation du staff)."""

    WAITING_STAFF_ID = 1
    WAITING_STAFF_REMOVE = 2
    WAITING_STAFF_CONFIRMATION = 3

    def __init__(self, db_manager, config, interface_manager=None):
        self.db_manager = db_manager
        self.config = config
        self.interface = interface_manager
        logger.info("StaffManager initialisé avec support RBAC")

    def set_interface_manager(self, interface_manager):
        """Injection différée de l'InterfaceManager si nécessaire."""
        self.interface = interface_manager

    def _get_interface(self):
        """Récupère l'InterfaceManager existant ou l'initialise à la volée."""
        if not self.interface:
            from utils.interface_manager import InterfaceManager
            self.interface = InterfaceManager(self.config, self.db_manager)
        return self.interface

    def _has_staff_management_perm(self, user_id: int) -> bool:
        """Contrôle si l'utilisateur possède l'autorisation de gérer les opérateurs."""
        if self.config.is_owner(user_id):
            return True
        if self.config.is_admin(user_id):
            privs = self.db_manager.get_admin_privileges(user_id)
            return privs.get("can_manage_staff", True)
        return False

    async def _safe_edit_or_send(self, query, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None):
        """Met à jour le message ou supprime la photo existante pour émettre du texte."""
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
        """Affiche la liste complète des membres de l'équipe Staff."""
        user = update.effective_user
        if not user or not self._has_staff_management_perm(user.id):
            if update.message:
                await update.message.reply_text("❌ Action réservée aux responsables d'équipe.")
            return

        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT s.user_id, s.alias, s.date_added, s.perm_reseaux, s.perm_type, s.is_paused,
                           u.first_name, u.username,
                           ua.first_name AS nom_ajouteur
                    FROM staff s
                    LEFT JOIN users u ON s.user_id = u.user_id
                    LEFT JOIN users ua ON s.added_by = ua.user_id
                    ORDER BY s.date_added ASC
                    """
                )
                staff_members = cursor.fetchall()

            if not staff_members:
                msg = "📭 <b>Aucun opérateur dans l'équipe Staff pour le moment.</b>"
                if update.message:
                    await update.message.reply_text(msg, parse_mode="HTML")
                return

            lines = [f"👥 <b>Équipe Staff (Opérateurs)</b> ({len(staff_members)})\n"]
            for st in staff_members:
                raw_pseudo = f"@{st['username']}" if st.get("username") else (st.get("first_name") or "")
                pseudo_esc = html.escape(str(raw_pseudo))
                alias_esc = html.escape(str(st.get("alias") or f"Staff_{st['user_id']}"))

                dt_added = st.get("date_added")
                if dt_added:
                    date_paris = convert_utc_to_paris(dt_added)
                    date_str = date_paris.strftime("%d/%m/%Y à %H:%M")
                else:
                    date_str = "Inconnue"

                par_qui = html.escape(str(st.get("nom_ajouteur") or "Direction"))
                status_badge = "⏸️ (En pause)" if st.get("is_paused") else "🟢 (En service)"

                lines.append(
                    f"• <b>{alias_esc}</b> {status_badge} ({pseudo_esc})\n"
                    f"  ID : <code>{st['user_id']}</code> | Recruté le {date_str} par {par_qui}\n"
                )

            if update.message:
                await update.message.reply_text("\n".join(lines), parse_mode="HTML")

        except Exception as exc:
            logger.error("Erreur récupération liste staff : %s", exc, exc_info=True)
            if update.message:
                await update.message.reply_text("❌ Impossible de charger la liste des opérateurs.")

    # ==================== RECRUTEMENT D'UN OPÉRATEUR ====================

    async def staff_ajouter(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Ouvre le formulaire de recrutement d'un opérateur."""
        query = update.callback_query
        user = update.effective_user
        if not query or not user or not self._has_staff_management_perm(user.id):
            return ConversationHandler.END

        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute("SELECT COUNT(*) AS count FROM staff")
                count = cursor.fetchone()["count"]

            text = (
                "👤 <b>Recrutement d'un Opérateur (Staff)</b>\n\n"
                f"Équipe actuelle : <b>{count}</b> opérateur(s)\n\n"
                "Envoyez l'<b>ID Telegram</b> (ex: <code>123456789</code>) "
                "ou le <b>@username</b> de l'utilisateur à recruter.\n\n"
                "<i>Rappel : Le futur opérateur doit avoir démarré le bot au moins une fois (/start).</i>"
            )
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Annuler", callback_data="cancel_staff_add")
            ]])

            await self._safe_edit_or_send(query, context, text, reply_markup=keyboard)
            return self.WAITING_STAFF_ID

        except Exception as exc:
            logger.error("Erreur interface ajout staff : %s", exc, exc_info=True)
            return ConversationHandler.END

    async def traiter_staff_ajouter(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Valide l'identifiant et enregistre le nouveau membre du staff."""
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

            with self.db_manager.transaction() as cursor:
                cursor.execute(
                    """
                    INSERT INTO staff (user_id, alias, added_by, perm_reseaux, perm_type, alias_locked, date_added)
                    VALUES (%s, %s, %s, 'all', 'all', FALSE, NOW())
                    """,
                    (target_id, alias, user.id)
                )

            self.config.add_staff(target_id)
            logger.info("Opérateur Staff ajouté : %s (%s) par %s", target_id, alias, user.id)

            alias_esc = html.escape(alias)
            nom_user_esc = html.escape(str(user_data.get("first_name") or ""))

            # Notification au nouvel opérateur
            try:
                welcome_msg = (
                    "🎉 <b>Bienvenue dans l'équipe opérationnelle (Staff) !</b>\n\n"
                    "Vous disposez désormais des accès nécessaires pour traiter et suivre les demandes.\n\n"
                    f"🏷️ <b>Votre alias provisoire :</b> <code>{alias_esc}</code>\n\n"
                    "⚠️ <b>Important :</b> Vous avez la possibilité de choisir votre pseudonyme officiel.\n"
                    "<i>Attention : vous ne disposez que d'<b>une seule modification</b>. Une fois validé, il sera verrouillé.</i>\n\n"
                    "Cliquez ci-dessous pour ouvrir vos accès :"
                )
                welcome_kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏷️ DÉFINIR MON ALIAS", callback_data="modifier_alias")],
                    [InlineKeyboardButton("🚀 Menu Principal", callback_data="start_menu")]
                ])
                await context.bot.send_message(
                    chat_id=target_id,
                    text=welcome_msg,
                    parse_mode="HTML",
                    reply_markup=welcome_kb
                )
                logger.info("Notification envoyée à l'opérateur %s", target_id)
            except Exception as notif_err:
                logger.warning("Impossible de notifier le nouvel opérateur %s : %s", target_id, notif_err)

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🛡️ Configurer ses droits", callback_data=f"perm_staff_{target_id}")],
                [InlineKeyboardButton("👥 Équipe Staff", callback_data="gerer_staff")],
                [InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")]
            ])

            await update.message.reply_text(
                f"✅ <b>Opérateur ajouté avec succès !</b>\n\n"
                f"👤 <b>Nom :</b> {nom_user_esc}\n"
                f"🆔 <b>ID :</b> <code>{target_id}</code>\n"
                f"🏷️ <b>Alias initial :</b> <code>{alias_esc}</code>",
                parse_mode="HTML",
                reply_markup=keyboard
            )
            return ConversationHandler.END

        except Exception as exc:
            logger.error("Erreur enregistrement staff : %s", exc, exc_info=True)
            await update.message.reply_text("❌ Erreur technique lors de l'enregistrement.")
            return ConversationHandler.END

    async def cancel_staff_add(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Interrompt la procédure de recrutement."""
        query = update.callback_query
        if query:
            await query.answer()
            interface = self._get_interface()
            message, keyboard = interface.get_gerer_staff_menu()
            await self._safe_edit_or_send(query, context, message, reply_markup=keyboard)
        return ConversationHandler.END

    # ==================== RÉVOCATION D'UN OPÉRATEUR ====================

    async def staff_supprimer(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Affiche la liste des opérateurs révocables."""
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

            if not staff_members:
                kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Retour", callback_data="gerer_staff")]])
                text = (
                    "👥 <b>Révocation d'un Opérateur</b>\n\n"
                    "Aucun opérateur révocable n'est configuré actuellement."
                )
                await self._safe_edit_or_send(query, context, text, reply_markup=kb)
                return ConversationHandler.END

            lines = [
                "👥 <b>Révocation d'un Opérateur (Staff)</b>\n",
                f"Opérateurs enregistrés : <b>{len(staff_members)}</b>\n"
            ]
            for idx, st in enumerate(staff_members, 1):
                raw_pseudo = f"@{st['username']}" if st.get("username") else (st.get("first_name") or "")
                pseudo_esc = html.escape(str(raw_pseudo))
                alias_esc = html.escape(str(st.get("alias") or f"Staff_{st['user_id']}"))
                date_str = str(st.get("date_added", ""))[:10]
                lines.append(f"{idx}. <b>{alias_esc}</b> ({pseudo_esc}) — ID: <code>{st['user_id']}</code> [{date_str}]")

            lines.append("\nEnvoyez le <b>numéro</b> de l'opérateur à révoquer :")

            context.user_data["staff_remove_list"] = staff_members
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Annuler", callback_data="cancel_staff_remove")
            ]])

            await self._safe_edit_or_send(query, context, "\n".join(lines), reply_markup=keyboard)
            return self.WAITING_STAFF_REMOVE

        except Exception as exc:
            logger.error("Erreur affichage suppression staff : %s", exc, exc_info=True)
            return ConversationHandler.END

    async def traiter_staff_supprimer(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Intercepte le choix numérique de l'opérateur à révoquer."""
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

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("⚠️ Confirmer la révocation", callback_data="confirm_staff_remove"),
                InlineKeyboardButton("❌ Annuler", callback_data="cancel_staff_remove")
            ]
        ])

        raw_pseudo = f"@{selected['username']}" if selected.get("username") else (selected.get("first_name") or "")
        pseudo_esc = html.escape(str(raw_pseudo))
        alias_esc = html.escape(str(selected.get("alias") or f"Staff_{selected['user_id']}"))

        await update.message.reply_text(
            f"⚠️ <b>Confirmation de révocation</b>\n\n"
            f"Êtes-vous certain de vouloir retirer les accès opérationnels à :\n"
            f"• <b>Alias :</b> {alias_esc}\n"
            f"• <b>Profil :</b> {pseudo_esc}\n"
            f"• <b>ID :</b> <code>{selected['user_id']}</code> ?",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        return self.WAITING_STAFF_CONFIRMATION

    async def confirmer_staff_suppression(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Supprime l'opérateur de la base de données et met à jour le cache."""
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

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("👥 Équipe Staff", callback_data="gerer_staff")],
                [InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")]
            ])

            alias_esc = html.escape(str(selected.get("alias") or f"Staff_{target_id}"))
            text = f"✅ <b>Droits staff retirés avec succès pour {alias_esc}.</b>"
            await self._safe_edit_or_send(query, context, text, reply_markup=keyboard)
            return ConversationHandler.END

        except Exception as exc:
            logger.error("Erreur exécution révocation staff : %s", exc, exc_info=True)
            await self._safe_edit_or_send(query, context, "❌ Erreur technique lors de la révocation.")
            return ConversationHandler.END

    async def cancel_staff_remove(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Annule la révocation et nettoie le contexte."""
        query = update.callback_query
        context.user_data.pop("staff_remove_list", None)
        context.user_data.pop("target_staff_to_remove", None)

        if query:
            await query.answer()
            interface = self._get_interface()
            message, keyboard = interface.get_gerer_staff_menu()
            await self._safe_edit_or_send(query, context, message, reply_markup=keyboard)
        return ConversationHandler.END