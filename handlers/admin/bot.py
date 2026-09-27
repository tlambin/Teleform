"""Module de gestion et de contrôle opérationnel du bot (Direction / Super-Admins)."""

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from . import bot_ui as ui

logger = logging.getLogger(__name__)


class BotManager:
    """Gestionnaire d'état opérationnel (actif, suspendu, maintenance) avec support Multi-Owner."""

    def __init__(self, db_manager, config, interface_manager=None):
        self.db_manager = db_manager
        self.config = config
        self.interface = interface_manager
        logger.info("BotManager initialisé avec support Multi-Owner")

    def set_interface_manager(self, interface_manager):
        """Injecte l'InterfaceManager si nécessaire."""
        self.interface = interface_manager

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

    async def bot_on(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Active l'acceptation globale des demandes et coupe le mode maintenance."""
        query = update.callback_query
        user = update.effective_user
        if not query or not user or not self.config.is_owner(user.id):
            if query:
                await query.answer("❌ Action réservée à la direction.", show_alert=True)
            return

        await query.answer()

        try:
            self.config.enable_demandes()
            logger.info("Bot activé par le propriétaire %s", user.id)

            text, keyboard = ui.get_bot_on_content()
            await self._safe_edit_or_send(query, context, text, reply_markup=keyboard)

        except Exception as exc:
            logger.error("Erreur activation bot : %s", exc, exc_info=True)
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Retour", callback_data="gerer_bot")]])
            await self._safe_edit_or_send(query, context, "❌ Erreur technique lors de l'activation.", reply_markup=kb)

    async def bot_off(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Désactive la prise de demandes avec message d'information."""
        query = update.callback_query
        user = update.effective_user
        if not query or not user or not self.config.is_owner(user.id):
            if query:
                await query.answer("❌ Action réservée à la direction.", show_alert=True)
            return

        await query.answer()

        try:
            self.config.disable_demandes()
            logger.info("Demandes suspendues par le propriétaire %s", user.id)

            text, keyboard = ui.get_bot_off_content()
            await self._safe_edit_or_send(query, context, text, reply_markup=keyboard)

        except Exception as exc:
            logger.error("Erreur désactivation bot : %s", exc, exc_info=True)
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Retour", callback_data="gerer_bot")]])
            await self._safe_edit_or_send(query, context, "❌ Erreur technique lors de la désactivation.", reply_markup=kb)

    async def bot_maintenance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Active l'état de maintenance restreint."""
        query = update.callback_query
        user = update.effective_user
        if not query or not user or not self.config.is_owner(user.id):
            if query:
                await query.answer("❌ Action réservée à la direction.", show_alert=True)
            return

        await query.answer()

        try:
            self.config.disable_demandes()
            self.db_manager.set_config_value("maintenance_mode", "true")
            logger.info("Mode maintenance enclenché par le propriétaire %s", user.id)

            text, keyboard = ui.get_bot_maintenance_content()
            await self._safe_edit_or_send(query, context, text, reply_markup=keyboard)

        except Exception as exc:
            logger.error("Erreur passage en mode maintenance : %s", exc, exc_info=True)
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Retour", callback_data="gerer_bot")]])
            await self._safe_edit_or_send(query, context, "❌ Erreur lors de l'activation de la maintenance.", reply_markup=kb)

    async def get_bot_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Affiche l'état courant du service et des paramètres."""
        user = update.effective_user
        if not user or not self.config.is_admin(user.id):
            return

        try:
            is_active = self.config.are_demandes_enabled()
            is_maint = str(self.db_manager.get_config_value("maintenance_mode", "false")).lower() in ("true", "1")

            text, keyboard = ui.build_bot_status_content(is_active, is_maint)

            if update.callback_query:
                await update.callback_query.answer()
                await self._safe_edit_or_send(update.callback_query, context, text, reply_markup=keyboard)
            elif update.message:
                await update.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)

        except Exception as exc:
            logger.error("Erreur extraction statut bot : %s", exc, exc_info=True)
            err = "❌ Impossible de lire le statut du bot."
            if update.callback_query:
                await self._safe_edit_or_send(update.callback_query, context, err)
            elif update.message:
                await update.message.reply_text(err)