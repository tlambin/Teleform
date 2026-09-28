"""Module de gestion manuelle des privilèges VIP (attribution et révocation)."""

import logging
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from ui.admin import users as ui

logger = logging.getLogger(__name__)


class VipManager:
    """Gère le cycle de vie des attributions VIP par l'administration."""

    WAITING_VIP_USER = 10
    WAITING_VIP_DURATION = 11
    WAITING_VIP_REMOVE = 12

    def __init__(self, db_manager, config, interface):
        self.db_manager = db_manager
        self.config = config
        self.interface = interface

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
                disable_web_page_preview=True,
            )
        else:
            try:
                await query.edit_message_text(
                    text=text,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                    disable_web_page_preview=True,
                )
            except Exception:
                if query.message:
                    await query.message.reply_text(
                        text=text,
                        parse_mode="HTML",
                        reply_markup=reply_markup,
                        disable_web_page_preview=True,
                    )

    # ==================== ATTRIBUTION VIP ====================

    async def start_add_vip(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Demande l'identifiant pour la promotion VIP."""
        query = update.callback_query
        if not query:
            return ConversationHandler.END
        await query.answer()

        text, kb = ui.get_vip_add_prompt_content()
        await self._safe_edit_or_send(query, context, text, reply_markup=kb)
        return self.WAITING_VIP_USER

    async def process_vip_target_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Vérifie le compte cible et propose la durée."""
        if not update.message or not update.message.text:
            return self.WAITING_VIP_USER

        saisie = update.message.text.strip().replace("@", "")
        try:
            with self.db_manager.get_cursor() as cursor:
                if saisie.isdigit():
                    cursor.execute("SELECT * FROM users WHERE user_id = %s", (int(saisie),))
                else:
                    cursor.execute("SELECT * FROM users WHERE LOWER(username) = LOWER(%s)", (saisie,))
                u_data = cursor.fetchone()

            if not u_data:
                await update.message.reply_text("❌ Utilisateur introuvable (/start obligatoire).")
                return self.WAITING_VIP_USER

            context.user_data["target_vip_user"] = u_data
            text, kb = ui.build_vip_duration_choice_content(u_data)
            await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb)
            return self.WAITING_VIP_DURATION
        except Exception as exc:
            logger.error("Erreur cible VIP : %s", exc)
            return ConversationHandler.END

    async def process_vip_duration_choice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Valide et applique la durée VIP choisie."""
        target_user = context.user_data.pop("target_vip_user", None)
        if not target_user:
            return ConversationHandler.END

        target_id = target_user["user_id"]
        duration_days = None

        if update.callback_query:
            query = update.callback_query
            await query.answer()
            data = query.data
            if data == "vip_dur_30":
                duration_days = 30
            elif data == "vip_dur_90":
                duration_days = 90
            elif data == "vip_dur_lifetime":
                duration_days = None
        elif update.message and update.message.text:
            text = update.message.text.strip()
            if text.isdigit() and int(text) > 0:
                duration_days = int(text)
            else:
                await update.message.reply_text("❌ Entrez un nombre de jours valide ou utilisez les boutons :")
                context.user_data["target_vip_user"] = target_user
                return self.WAITING_VIP_DURATION

        self.db_manager.set_user_vip(target_id, is_vip=True, duration_days=duration_days)

        try:
            notif_text = ui.get_vip_granted_notification(duration_days)
            await context.bot.send_message(
                chat_id=target_id,
                text=notif_text,
                parse_mode="HTML",
            )
        except Exception:
            pass

        target_name = target_user.get("first_name") or target_id
        succes_msg, kb = ui.build_vip_grant_success_content(target_name, duration_days)

        if update.callback_query:
            await self._safe_edit_or_send(update.callback_query, context, succes_msg, reply_markup=kb)
        elif update.message:
            await update.message.reply_text(succes_msg, parse_mode="HTML", reply_markup=kb)

        return ConversationHandler.END

    # ==================== RÉVOCATION VIP ====================

    async def start_remove_vip(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Affiche la liste des VIPs pour sélection de révocation."""
        query = update.callback_query
        if not query:
            return ConversationHandler.END
        await query.answer()

        vips = self.db_manager.get_vip_users_list()
        text, kb = ui.build_vip_remove_list_content(vips)
        if not vips:
            await self._safe_edit_or_send(query, context, text, reply_markup=kb)
            return ConversationHandler.END

        context.user_data["vip_remove_list"] = vips
        await self._safe_edit_or_send(query, context, text, reply_markup=kb)
        return self.WAITING_VIP_REMOVE

    async def process_vip_remove_choice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Valide et enregistre la fin de l'accès VIP."""
        if not update.message or not update.message.text:
            return self.WAITING_VIP_REMOVE

        choix = update.message.text.strip()
        vips = context.user_data.pop("vip_remove_list", [])

        if not choix.isdigit() or int(choix) < 1 or int(choix) > len(vips):
            await update.message.reply_text(f"❌ Numéro invalide (1 à {len(vips)}) :")
            context.user_data["vip_remove_list"] = vips
            return self.WAITING_VIP_REMOVE

        selected = vips[int(choix) - 1]
        self.db_manager.set_user_vip(selected["user_id"], is_vip=False)

        target_name = selected.get("first_name") or selected["user_id"]
        text, kb = ui.build_vip_revoked_success_content(target_name)
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb)
        return ConversationHandler.END

    async def cancel_vip_action(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Annule le flux VIP en cours."""
        context.user_data.pop("target_vip_user", None)
        context.user_data.pop("vip_remove_list", None)
        query = update.callback_query
        if query:
            await query.answer()
            msg, kb = self.interface.get_gerer_vips_menu()
            await self._safe_edit_or_send(query, context, msg, reply_markup=kb)
        return ConversationHandler.END