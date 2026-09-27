"""Module de gestion des purges sécurisées de données SQL (Owner only)."""

import logging
from telegram import Update
from telegram.ext import ContextTypes
from utils.session import session_manager
from . import purge_ui as ui

logger = logging.getLogger(__name__)


class PurgeManager:
    """Gère le protocole de purge des tables MySQL avec double confirmation stricte et résilience uWSGI."""

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

    async def show_purge_menu(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Affiche le menu de sélection du lot de données à vider."""
        await query.answer()
        user_id = query.from_user.id
        context.user_data.pop("waiting_danger_confirmation", None)
        context.user_data.pop("pending_danger_target", None)
        session_manager.clear_state(user_id, "danger_purge")

        msg, kb = self.interface.get_danger_zone_menu()
        await self._safe_edit_or_send(query, context, msg, reply_markup=kb)

    async def prompt_confirmation(self, query, context: ContextTypes.DEFAULT_TYPE, target: str):
        """Demande la première confirmation par bouton."""
        await query.answer()
        user_id = query.from_user.id
        context.user_data["pending_danger_target"] = target
        session_manager.set_state(user_id, "danger_purge_step1", target, ttl=300.0)

        text, kb = ui.get_step1_confirmation_content(target)
        await self._safe_edit_or_send(query, context, text, reply_markup=kb)

    async def prompt_text_confirmation(self, query, context: ContextTypes.DEFAULT_TYPE, target: str):
        """Demande la saisie textuelle stricte du mot 'Effacer'."""
        await query.answer()
        user_id = query.from_user.id
        context.user_data["waiting_danger_confirmation"] = target
        # Persistance disque protégée pendant 5 minutes (300 s)
        session_manager.set_state(user_id, "danger_purge", target, ttl=300.0)

        text, kb = ui.get_step2_text_confirmation_content(target)
        await self._safe_edit_or_send(query, context, text, reply_markup=kb)

    async def handle_text_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Traite le message texte pour valider l'exécution de la purge."""
        if not update.message or not update.message.text:
            return False

        user_id = update.effective_user.id

        # Récupération avec fallback persistant si reload worker uWSGI
        target = context.user_data.get("waiting_danger_confirmation") or session_manager.get_state(user_id, "danger_purge")
        if not target:
            return False

        if not self.config.is_owner(user_id):
            context.user_data.pop("waiting_danger_confirmation", None)
            session_manager.clear_state(user_id, "danger_purge")
            return False

        saisie = update.message.text.strip()
        # Nettoyage immédiat des états
        context.user_data.pop("waiting_danger_confirmation", None)
        context.user_data.pop("pending_danger_target", None)
        session_manager.clear_state(user_id, "danger_purge")
        session_manager.clear_state(user_id, "danger_purge_step1")

        if saisie == "Effacer":
            success = self.db_manager.purge_table_data(target, owner_id=user_id)
            msg, kb = ui.get_purge_result_content(success=success, target=target)
        else:
            msg, kb = ui.get_purge_result_content(success=False, target=target, is_canceled=True)

        await update.message.reply_text(msg, parse_mode="HTML", reply_markup=kb)
        return True