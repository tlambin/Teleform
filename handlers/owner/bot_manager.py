"""Module de gestion et de contrôle opérationnel du bot par le propriétaire."""

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from utils.validators import convert_utc_to_paris

logger = logging.getLogger(__name__)


class BotManager:
    """Gestionnaire d'état opérationnel (actif, suspendu, maintenance)."""

    def __init__(self, db_manager, config, interface_manager=None):
        self.db_manager = db_manager
        self.config = config
        self.interface = interface_manager
        logger.info("BotManager initialisé")

    def set_interface_manager(self, interface_manager):
        """Injecte l'InterfaceManager si nécessaire."""
        self.interface = interface_manager

    async def bot_on(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Active l'acceptation globale des demandes."""
        query = update.callback_query
        user = update.effective_user
        if not query or not user or not self.config.is_owner(user.id):
            return

        try:
            self.db_manager.set_bot_active(True)
            logger.info("Bot activé par le propriétaire %s", user.id)

            msg = (
                "🟢 <b>Bot opérationnel</b>\n\n"
                "✅ Les utilisateurs peuvent à nouveau créer des demandes et naviguer librement.\n"
                "📊 Toutes les commandes sont actives."
            )
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔴 Désactiver", callback_data="bot_off")],
                [InlineKeyboardButton("🛠️ Maintenance", callback_data="maintenance")],
                [InlineKeyboardButton("🔙 Menu Owner", callback_data="start_menu")]
            ])

            await query.edit_message_text(msg, parse_mode="HTML", reply_markup=keyboard)

        except Exception as exc:
            logger.error("Erreur activation bot: %s", exc, exc_info=True)
            await query.edit_message_text(
                "❌ Erreur technique lors de l'activation.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Retour", callback_data="gerer_bot")
                ]])
            )

    async def bot_off(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Désactive la prise de demandes avec message d'information."""
        query = update.callback_query
        user = update.effective_user
        if not query or not user or not self.config.is_owner(user.id):
            return

        try:
            self.db_manager.set_bot_active(False)
            logger.info("Demandes suspendues par le propriétaire %s", user.id)

            msg = (
                "🔴 <b>Demandes suspendues</b>\n\n"
                "⏸️ Le service de création de demandes est désormais désactivé.\n"
                "🔒 Les administrateurs conservent leurs accès pour traiter les demandes en cours."
            )
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🟢 Réactiver", callback_data="bot_on")],
                [InlineKeyboardButton("🛠️ Maintenance", callback_data="maintenance")],
                [InlineKeyboardButton("🔙 Menu Owner", callback_data="start_menu")]
            ])

            await query.edit_message_text(msg, parse_mode="HTML", reply_markup=keyboard)

        except Exception as exc:
            logger.error("Erreur désactivation bot: %s", exc, exc_info=True)
            await query.edit_message_text(
                "❌ Erreur technique lors de la désactivation.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Retour", callback_data="gerer_bot")
                ]])
            )

    async def bot_maintenance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Active l'état de maintenance restreint."""
        query = update.callback_query
        user = update.effective_user
        if not query or not user or not self.config.is_owner(user.id):
            return

        try:
            self.db_manager.set_config_value("maintenance_mode", "true")
            self.db_manager.set_bot_active(False)
            logger.info("Mode maintenance enclenché par %s", user.id)

            msg = (
                "🛠️ <b>Mode maintenance actif</b>\n\n"
                "⚙️ Le bot est verrouillé pour des interventions techniques.\n"
                "Seul le compte propriétaire est habilité à exécuter des actions."
            )
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🟢 Réactiver le service", callback_data="bot_on")],
                [InlineKeyboardButton("🔙 Menu Owner", callback_data="start_menu")]
            ])

            await query.edit_message_text(msg, parse_mode="HTML", reply_markup=keyboard)

        except Exception as exc:
            logger.error("Erreur passage en mode maintenance: %s", exc, exc_info=True)
            await query.edit_message_text(
                "❌ Erreur lors de l'activation de la maintenance.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Retour", callback_data="gerer_bot")
                ]])
            )

    async def get_bot_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Affiche l'état courant du service et des paramètres."""
        user = update.effective_user
        if not user or not self.config.is_owner(user.id):
            return

        try:
            is_active = self.db_manager.is_bot_active()
            is_maint = self.db_manager.get_config_value("maintenance_mode", "false") == "true"

            if is_maint:
                badge = "🛠️ <b>Maintenance</b>"
                detail = "Accès restreint au propriétaire."
            elif is_active:
                badge = "🟢 <b>Actif</b>"
                detail = "Toutes les fonctions sont opérationnelles pour les utilisateurs."
            else:
                badge = "🔴 <b>Suspendu</b>"
                detail = "Les utilisateurs ne peuvent plus soumettre de formulaires."

            text = (
                "📊 <b>Statut Opérationnel du Bot</b>\n\n"
                f"• <b>État :</b> {badge}\n"
                f"• <b>Détails :</b> {detail}"
            )

            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🟢 Activer", callback_data="bot_on"),
                    InlineKeyboardButton("🔴 Couper", callback_data="bot_off")
                ],
                [InlineKeyboardButton("🛠️ Maintenance", callback_data="maintenance")],
                [InlineKeyboardButton("🔙 Menu Owner", callback_data="start_menu")]
            ])

            if update.callback_query:
                await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)
            elif update.message:
                await update.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)

        except Exception as exc:
            logger.error("Erreur extraction statut bot: %s", exc, exc_info=True)
            err = "❌ Impossible de lire le statut du bot."
            if update.callback_query:
                await update.callback_query.edit_message_text(err)
            elif update.message:
                await update.message.reply_text(err)