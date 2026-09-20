"""Module de gestion des paramètres de configuration dynamique du bot."""

import html
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
        "auto_archive_hours": "72",
        "delivery_reminder_days": "7",
        "payment_reminder_days": "7",
        "allow_hetero_insta": "true",
        "allow_hetero_snap": "true",
        "allow_gay_insta": "true",
        "allow_gay_snap": "true",
        "max_hetero_insta": "0",
        "max_hetero_snap": "0",
        "max_gay_insta": "0",
        "max_gay_snap": "0",
    }

    def __init__(self, db_manager, config):
        self.db_manager = db_manager
        self.config = config
        logger.info("ConfigManager initialisé avec support Délais, Quotas & Rappels")

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

    # ==================== MENU 1 : PARAMÈTRES ====================

    async def show_parametres_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Affiche le menu général PARAMÈTRES via InterfaceManager."""
        query = update.callback_query
        if query:
            await query.answer()

        from utils.interface_manager import InterfaceManager
        ui = InterfaceManager(self.config, self.db_manager)
        text, keyboard = ui.get_parametres_menu(update.effective_user.id)

        if query:
            await self._safe_edit_or_send(query, context, text, reply_markup=keyboard)
        elif update.message:
            await update.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)

    # ==================== MENU 2 : GESTION DU BOT ====================

    async def show_gestion_bot_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Affiche le sous-menu GESTION DU BOT via InterfaceManager."""
        query = update.callback_query
        user = update.effective_user
        if not user or not self.config.is_admin(user.id):
            if query:
                await query.answer("❌ Action réservée aux administrateurs.", show_alert=True)
            return

        if query:
            await query.answer()

        from utils.interface_manager import InterfaceManager
        ui = InterfaceManager(self.config, self.db_manager)
        text, keyboard = ui.get_gerer_bot_menu()

        if query:
            await self._safe_edit_or_send(query, context, text, reply_markup=keyboard)
        elif update.message:
            await update.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)

    # ==================== ACTIONS GESTION DU BOT ====================

    async def toggle_demandes_service(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Bascule l'ouverture ou la fermeture du service de dépôt de demandes."""
        query = update.callback_query
        user = update.effective_user
        if not query or not user or not self.config.is_admin(user.id):
            if query:
                await query.answer("❌ Action réservée à l'administration.", show_alert=True)
            return

        actuellement_ouvert = self.config.are_demandes_enabled()
        if actuellement_ouvert:
            self.config.disable_demandes()
            self.set_setting("demandes_enabled", "false")
            await query.answer("🛑 Réception des demandes suspendue !", show_alert=True)
        else:
            self.config.enable_demandes()
            self.set_setting("demandes_enabled", "true")
            await query.answer("✅ Réception des demandes réactivée !", show_alert=True)

        await self.show_gestion_bot_menu(update, context)

    async def toggle_maintenance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Bascule l'état du mode maintenance avec synchronisation SQL."""
        query = update.callback_query
        user = update.effective_user
        if not query or not user or not self.config.is_owner(user.id):
            if query:
                await query.answer("❌ Action réservée à la direction.", show_alert=True)
            return

        try:
            current = self.is_maintenance_mode()
            new_val = not current
            self.set_setting("maintenance_mode", "true" if new_val else "false")

            if new_val:
                self.config.disable_demandes()
                self.set_setting("bot_active", "false")
                self.set_setting("demandes_enabled", "false")
            else:
                self.config.enable_demandes()
                self.set_setting("bot_active", "true")
                self.set_setting("demandes_enabled", "true")

            status_str = "activé" if new_val else "désactivé"
            logger.info("Maintenance %s par le propriétaire %s", status_str, user.id)
            await query.answer(f"🛠️ Mode maintenance {status_str} !", show_alert=True)
            await self.show_gestion_bot_menu(update, context)

        except Exception as exc:
            logger.error("Erreur bascule mode maintenance : %s", exc)
            await self._send_error_message(update, context, "❌ Erreur lors de la mise à jour de la maintenance.")

    async def toggle_priority_requests(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Autorise ou interdit la soumission de demandes prioritaires."""
        query = update.callback_query
        user = update.effective_user
        if not query or not user or not self.config.is_owner(user.id):
            if query:
                await query.answer("❌ Action réservée à la direction.", show_alert=True)
            return

        try:
            current = self.is_priority_allowed()
            new_val = not current
            self.set_setting("allow_priority_requests", "true" if new_val else "false")

            status_str = "autorisées" if new_val else "désactivées"
            await query.answer(f"💎 Demandes prioritaires {status_str} !", show_alert=True)
            await self.show_gestion_bot_menu(update, context)

        except Exception as exc:
            logger.error("Erreur bascule demandes prioritaires : %s", exc)
            await self._send_error_message(update, context, "❌ Erreur lors du réglage des demandes prioritaires.")

    # ==================== CANAUX & MATRICE ====================

    async def show_channels_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Menu interactif de bascule pour les 4 canaux combinés (Hétéro/Gay × Insta/Snap)."""
        query = update.callback_query
        if not query:
            return
        await query.answer()

        from utils.interface_manager import InterfaceManager
        ui = InterfaceManager(self.config, self.db_manager)
        text, keyboard = ui.get_channels_menu()
        await self._safe_edit_or_send(query, context, text, reply_markup=keyboard)

    async def toggle_channel_setting(self, update: Update, context: ContextTypes.DEFAULT_TYPE, key_name: str):
        """Bascule l'état d'un canal combiné."""
        query = update.callback_query
        if not query:
            return

        current = str(self.get_setting(key_name, "true")).lower() == "true"
        new_val = not current
        self.set_setting(key_name, "true" if new_val else "false")
        await query.answer("✅ État du canal mis à jour !")
        await self.show_channels_menu(update, context)

    # ==================== LIMITES & PLAFONDS ====================

    async def show_limits_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Affiche le menu complet des quotas globaux et par canal combiné."""
        query = update.callback_query
        if query:
            await query.answer()

        from utils.interface_manager import InterfaceManager
        ui = InterfaceManager(self.config, self.db_manager)
        text, keyboard = ui.get_limits_menu()

        if query:
            await self._safe_edit_or_send(query, context, text, reply_markup=keyboard)
        elif update.message:
            await update.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)

    # ==================== DÉLAIS PARAMÉTRABLES ====================

    async def show_delais_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Affiche le menu de paramétrage des délais automatiques."""
        query = update.callback_query
        if not query:
            return
        await query.answer()

        hours = self.db_manager.get_auto_archive_hours()
        days = self.db_manager.get_delivery_reminder_days()
        pay_days = self.db_manager.get_payment_reminder_days()

        text = (
            "⏳ <b>CONFIGURATION DES DÉLAIS DU SYSTÈME</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• 📦 <b>Auto-archivage post-livraison :</b> <code>{hours}h</code>\n"
            f"• 🚚 <b>Rappel livraison (Staff) :</b> <code>{days} jours</code>\n"
            f"• 💰 <b>Rappel impayé (Demandeur) :</b> <code>{pay_days} jours</code>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "<i>Cliquez sur une option pour modifier sa valeur :</i>"
        )
        keyboard = [
            [
                InlineKeyboardButton(f"📦 Auto-archivage ({hours}h)", callback_data="cfg_sub_archive_hours"),
                InlineKeyboardButton(f"🚚 Rappel Livraison ({days}j)", callback_data="cfg_sub_reminder_days")
            ],
            [
                InlineKeyboardButton(f"💰 Rappel Impayé Client ({pay_days}j)", callback_data="cfg_sub_payrem_days")
            ],
            [InlineKeyboardButton("⬅️ RETOUR", callback_data="gerer_bot")]
        ]
        await self._safe_edit_or_send(query, context, text, reply_markup=InlineKeyboardMarkup(keyboard))

    async def show_archive_hours_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Sous-menu pour choisir l'intervalle d'auto-archivage."""
        query = update.callback_query
        if not query:
            return
        await query.answer()

        current = self.db_manager.get_auto_archive_hours()

        def b_lbl(name: str, val: int) -> str:
            return f"✅ {name}" if current == val else name

        keyboard = [
            [
                InlineKeyboardButton(b_lbl("24h (1j)", 24), callback_data="set_arch_hours_24"),
                InlineKeyboardButton(b_lbl("48h (2j)", 48), callback_data="set_arch_hours_48"),
            ],
            [
                InlineKeyboardButton(b_lbl("72h (3j)", 72), callback_data="set_arch_hours_72"),
                InlineKeyboardButton(b_lbl("168h (7j)", 168), callback_data="set_arch_hours_168"),
            ],
            [InlineKeyboardButton("⬅️ RETOUR", callback_data="menu_delais")]
        ]
        text = (
            "📦 <b>Délai d'auto-archivage</b>\n\n"
            f"Actuel : <b>{current} heures</b> post-livraison avant archivage automatique."
        )
        await self._safe_edit_or_send(query, context, text, reply_markup=InlineKeyboardMarkup(keyboard))

    async def show_reminder_days_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Sous-menu pour choisir le délai de relance de livraison pour le staff."""
        query = update.callback_query
        if not query:
            return
        await query.answer()

        current = self.db_manager.get_delivery_reminder_days()

        def b_lbl(name: str, val: int) -> str:
            return f"✅ {name}" if current == val else name

        keyboard = [
            [
                InlineKeyboardButton(b_lbl("3 jours", 3), callback_data="set_rem_days_3"),
                InlineKeyboardButton(b_lbl("5 jours", 5), callback_data="set_rem_days_5"),
            ],
            [
                InlineKeyboardButton(b_lbl("7 jours", 7), callback_data="set_rem_days_7"),
                InlineKeyboardButton(b_lbl("14 jours", 14), callback_data="set_rem_days_14"),
            ],
            [InlineKeyboardButton("⬅️ RETOUR", callback_data="menu_delais")]
        ]
        text = (
            "🚚 <b>Délai de relance pour contenu non livré (Staff)</b>\n\n"
            f"Actuel : <b>{current} jours</b>."
        )
        await self._safe_edit_or_send(query, context, text, reply_markup=InlineKeyboardMarkup(keyboard))

    async def show_payment_reminder_days_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Sous-menu pour choisir la fréquence de rappel d'impayé envoyée au demandeur."""
        query = update.callback_query
        if not query:
            return
        await query.answer()

        current = self.db_manager.get_payment_reminder_days()

        def b_lbl(name: str, val: int) -> str:
            return f"✅ {name}" if current == val else name

        keyboard = [
            [
                InlineKeyboardButton(b_lbl("3 jours", 3), callback_data="set_payrem_days_3"),
                InlineKeyboardButton(b_lbl("5 jours", 5), callback_data="set_payrem_days_5"),
            ],
            [
                InlineKeyboardButton(b_lbl("7 jours", 7), callback_data="set_payrem_days_7"),
                InlineKeyboardButton(b_lbl("14 jours", 14), callback_data="set_payrem_days_14"),
            ],
            [InlineKeyboardButton("⬅️ RETOUR", callback_data="menu_delais")]
        ]
        text = (
            "💰 <b>Fréquence du rappel d'impayé (Demandeur)</b>\n\n"
            f"Actuelle : Tous les <b>{current} jours</b>."
        )
        await self._safe_edit_or_send(query, context, text, reply_markup=InlineKeyboardMarkup(keyboard))

    # ==================== ACCESSEURS DE CONFIGURATION ====================

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
        return str(self.get_setting("maintenance_mode", "false")).lower() == "true"

    def is_priority_allowed(self) -> bool:
        """Indique si les demandes prioritaires sont activées."""
        return str(self.get_setting("allow_priority_requests", "true")).lower() == "true"

    def get_max_requests_per_user(self) -> int:
        """Retourne le quota maximal de demandes actives autorisé par utilisateur."""
        val = self.get_setting("max_demandes_per_user", "3")
        return int(val) if str(val).isdigit() else 3

    async def _send_error_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
        """Envoie un message d'erreur avec retour sécurisé vers gerer_bot."""
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("⬅️ RETOUR", callback_data="gerer_bot")
        ]])
        if update.callback_query:
            await self._safe_edit_or_send(update.callback_query, context, text, reply_markup=kb)
        elif update.message:
            await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb)