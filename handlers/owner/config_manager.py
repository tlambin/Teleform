"""Module de gestion des paramètres de configuration dynamique du bot."""

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


class ConfigManager:
    """Gestionnaire de configuration globale synchronisé avec la table config."""

    DEFAULT_SETTINGS = {
        "bot_active": "true",
        "maintenance_mode": "false",
        "max_demandes_per_user": "3",
        "max_total_demandes": "0",
        "allow_priority_requests": "true",
        "admin_notifications": "true",
        "max_request_age_days": "30",
    }

    def __init__(self, db_manager, config):
        self.db_manager = db_manager
        self.config = config
        logger.info("ConfigManager initialisé")

    async def show_config_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Affiche le menu récapitulatif des configurations courantes."""
        user = update.effective_user
        if not user or not self.config.is_owner(user.id):
            if update.callback_query:
                await update.callback_query.answer("❌ Accès réservé au propriétaire.", show_alert=True)
            elif update.message:
                await update.message.reply_text("❌ Accès non autorisé.")
            return

        try:
            current_config = self._get_current_config()
            message = self._format_config_message(current_config)
            keyboard = self._create_config_keyboard()

            if update.callback_query:
                query = update.callback_query
                if query.message and query.message.photo:
                    chat_id = query.message.chat_id
                    await query.message.delete()
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=message,
                        parse_mode="HTML",
                        reply_markup=keyboard,
                    )
                else:
                    await query.edit_message_text(
                        message, parse_mode="HTML", reply_markup=keyboard
                    )
            elif update.message:
                await update.message.reply_text(
                    message, parse_mode="HTML", reply_markup=keyboard
                )

        except Exception as exc:
            logger.error("Erreur affichage menu configuration: %s", exc, exc_info=True)
            await self._send_error_message(update, "❌ Erreur lors de la récupération de la configuration.")

    async def toggle_maintenance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Bascule l'état du mode maintenance."""
        query = update.callback_query
        user = update.effective_user
        if not query or not user or not self.config.is_owner(user.id):
            return

        try:
            current = self.is_maintenance_mode()
            new_val = not current
            self.set_setting("maintenance_mode", "true" if new_val else "false")

            if new_val:
                self.config.disable_demandes()
            else:
                self.config.enable_demandes()

            status_str = "activé" if new_val else "désactivé"
            logger.info("Maintenance %s par le propriétaire %s", status_str, user.id)

            await query.edit_message_text(
                f"🛠️ <b>Mode maintenance {status_str}</b>\n\n"
                f"Le service est désormais {'restreint au propriétaire' if new_val else 'disponible selon les paramètres standards'}.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Retour Configuration", callback_data="gerer_bot")
                ]]),
            )

        except Exception as exc:
            logger.error("Erreur bascule mode maintenance: %s", exc)
            await self._send_error_message(update, "❌ Erreur lors de la mise à jour de la maintenance.")

    async def toggle_priority_requests(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Autorise ou interdit la soumission de demandes prioritaires."""
        query = update.callback_query
        user = update.effective_user
        if not query or not user or not self.config.is_owner(user.id):
            return

        try:
            current = self.is_priority_allowed()
            new_val = not current
            self.set_setting("allow_priority_requests", "true" if new_val else "false")

            status_str = "autorisées" if new_val else "désactivées"
            await query.edit_message_text(
                f"💎 <b>Demandes prioritaires {status_str}</b>\n\n"
                f"Les demandes prioritaires payantes sont dorénavant {'acceptées' if new_val else 'refusées'}.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Retour Configuration", callback_data="gerer_bot")
                ]]),
            )

        except Exception as exc:
            logger.error("Erreur bascule demandes prioritaires: %s", exc)
            await self._send_error_message(update, "❌ Erreur lors du réglage des demandes prioritaires.")

    def get_setting(self, key: str, default=None):
        """Récupère une valeur de configuration depuis la table config."""
        val = self.db_manager.get_config_value(key)
        if val is None:
            return default if default is not None else self.DEFAULT_SETTINGS.get(key)
        return val

    def set_setting(self, key: str, value):
        """Met à jour une clé de configuration avec invalidation automatique du cache."""
        str_val = "true" if value is True else ("false" if value is False else str(value))
        return self.db_manager.set_config_value(key, str_val)

    def is_maintenance_mode(self) -> bool:
        """Indique si la maintenance technique est active."""
        return self.get_setting("maintenance_mode", "false").lower() == "true"

    def is_priority_allowed(self) -> bool:
        """Indique si les demandes prioritaires sont activées."""
        return self.get_setting("allow_priority_requests", "true").lower() == "true"

    def get_max_requests_per_user(self) -> int:
        """Retourne le quota maximal de demandes actives autorisé par utilisateur."""
        val = self.get_setting("max_demandes_per_user", "3")
        return int(val) if str(val).isdigit() else 3

    def _get_current_config(self) -> dict:
        """Lit l'ensemble des réglages applicatifs."""
        raw = self.db_manager.get_all_config()
        cfg = self.DEFAULT_SETTINGS.copy()
        for k, v in raw.items():
            cfg[k] = v
        return cfg

    def _format_config_message(self, cfg: dict) -> str:
        """Formate le récapitulatif des réglages pour l'Owner."""
        is_maint = cfg.get("maintenance_mode", "false").lower() == "true"
        is_prio = cfg.get("allow_priority_requests", "true").lower() == "true"
        is_active = self.config.are_demandes_enabled()

        maint_badge = "🔴 Activé" if is_maint else "🟢 Désactivé"
        prio_badge = "✅ Autorisées" if is_prio else "❌ Désactivées"
        active_badge = "🟢 Ouvert" if is_active else "🔴 Suspendu"

        max_user = cfg.get("max_demandes_per_user", "3")
        max_tot = cfg.get("max_total_demandes", "0")
        tot_str = "Illimité" if max_tot == "0" else max_tot

        return (
            "⚙️ <b>Paramètres Généraux du Système</b>\n\n"
            f"• <b>Service global :</b> {active_badge}\n"
            f"• <b>Mode maintenance :</b> {maint_badge}\n"
            f"• <b>Demandes prioritaires :</b> {prio_badge}\n"
            f"• <b>Plafond global :</b> <code>{tot_str}</code>\n"
            f"• <b>Plafond par utilisateur :</b> <code>{max_user}</code>\n"
            f"• <b>Rétention archives :</b> {cfg.get('max_request_age_days', '30')} jours\n\n"
            "Sélectionnez un paramètre pour modifier son état :"
        )

    def _create_config_keyboard(self) -> InlineKeyboardMarkup:
        """Génère le clavier de contrôle de configuration."""
        keyboard = [
            [
                InlineKeyboardButton("🛠️ Maintenance", callback_data="config_toggle_maintenance"),
                InlineKeyboardButton("💎 Prioritaires", callback_data="config_toggle_priority"),
            ],
            [
                InlineKeyboardButton("⚙️ Quotas & Limites", callback_data="menu_limits")
            ],
            [
                InlineKeyboardButton("🔙 Menu Owner", callback_data="gerer_bot")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)

    async def _send_error_message(self, update: Update, text: str):
        """Envoie un message d'erreur avec retour sécurisé."""
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Menu Owner", callback_data="gerer_bot")
        ]])
        if update.callback_query:
            await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
        elif update.message:
            await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb)