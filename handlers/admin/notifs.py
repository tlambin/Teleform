"""Module de gestion des préférences de notifications et rappels des administrateurs."""

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

JOURS_SEMAINE = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]


class NotifsManager:
    """Gestionnaire de l'interface des préférences d'alertes et de rappels."""

    def __init__(self, db_manager, config):
        self.db_manager = db_manager
        self.config = config
        logger.info("NotifsManager initialisé")

    async def show_notifs_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Affiche le panneau principal de réglage des notifications."""
        query = update.callback_query
        user = update.effective_user
        if not user or not self.config.is_admin(user.id):
            if query:
                await query.answer("❌ Accès non autorisé.", show_alert=True)
            return

        prefs = self.db_manager.get_admin_preferences(user.id)
        text, keyboard = self._build_menu_content(user.id, prefs)

        if query:
            if query.message and query.message.photo:
                await query.message.delete()
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=text,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
            else:
                await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)
        elif update.message:
            await update.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)

    def _build_menu_content(self, user_id: int, prefs: dict):
        alias = self.db_manager.get_admin_alias(user_id)

        # 1. Alertes nouvelles demandes
        mode_new = prefs.get("notif_new_mode", "sound")
        btn_new_sound = "✅ 🔊 Sonore" if mode_new == "sound" else "🔊 Sonore"
        btn_new_silent = "✅ 🔇 Silencieux" if mode_new == "silent" else "🔇 Silencieux"
        btn_new_off = "✅ 🔕 Coupé" if mode_new == "off" else "🔕 Coupé"

        # 2. Mode rappels de suivis
        mode_rappel = prefs.get("rappel_mode", "sound")
        btn_rap_sound = "✅ 🔊 Sonore" if mode_rappel == "sound" else "🔊 Sonore"
        btn_rap_silent = "✅ 🔇 Silencieux" if mode_rappel == "silent" else "🔇 Silencieux"
        btn_rap_off = "✅ ❌ Désactivé" if mode_rappel == "off" else "❌ Désactivé"

        # 3. Fréquence et timing
        freq = prefs.get("rappel_freq", "daily")
        heure = prefs.get("rappel_heure", 18)
        jour_sem = prefs.get("rappel_jour_semaine", 6)
        jour_mois = prefs.get("rappel_jour_mois", 1)

        btn_freq_daily = "✅ Chaque jour" if freq == "daily" else "Chaque jour"
        btn_freq_weekly = "✅ 1x / sem" if freq == "weekly" else "1x / sem"
        btn_freq_monthly = "✅ 1x / mois" if freq == "monthly" else "1x / mois"

        keyboard = [
            # Ligne 1 : Nouvelles demandes
            [
                InlineKeyboardButton(btn_new_sound, callback_data="pref_new_sound"),
                InlineKeyboardButton(btn_new_silent, callback_data="pref_new_silent"),
                InlineKeyboardButton(btn_new_off, callback_data="pref_new_off"),
            ],
            # Ligne 2 : Mode de rappel
            [
                InlineKeyboardButton(btn_rap_sound, callback_data="pref_rap_sound"),
                InlineKeyboardButton(btn_rap_silent, callback_data="pref_rap_silent"),
                InlineKeyboardButton(btn_rap_off, callback_data="pref_rap_off"),
            ],
        ]

        # Options détaillées si les rappels ne sont pas désactivés
        if mode_rappel != "off":
            keyboard.append([
                InlineKeyboardButton(btn_freq_daily, callback_data="pref_freq_daily"),
                InlineKeyboardButton(btn_freq_weekly, callback_data="pref_freq_weekly"),
                InlineKeyboardButton(btn_freq_monthly, callback_data="pref_freq_monthly"),
            ])

            timing_row = [
                InlineKeyboardButton(f"⏰ {heure:02d}h00", callback_data="pref_pick_hour")
            ]
            if freq == "weekly":
                timing_row.append(InlineKeyboardButton(f"📅 {JOURS_SEMAINE[jour_sem]}", callback_data="pref_pick_weekday"))
            elif freq == "monthly":
                timing_row.append(InlineKeyboardButton(f"📅 Le {jour_mois} du mois", callback_data="pref_pick_monthday"))

            keyboard.append(timing_row)

        keyboard.append([InlineKeyboardButton("🔙 Paramètres", callback_data="parametres")])

        mode_new_str = {"sound": "🔊 Sonore", "silent": "🔇 Silencieuse", "off": "🔕 Désactivée"}.get(mode_new)
        mode_rap_str = {"sound": "🔊 Sonore", "silent": "🔇 Silencieux", "off": "❌ Désactivé"}.get(mode_rappel)

        timing_desc = ""
        if mode_rappel != "off":
            if freq == "daily":
                timing_desc = f"• <b>Fréquence :</b> Tous les jours à <b>{heure:02d}h00</b>\n"
            elif freq == "weekly":
                timing_desc = f"• <b>Fréquence :</b> Chaque <b>{JOURS_SEMAINE[jour_sem]}</b> à <b>{heure:02d}h00</b>\n"
            elif freq == "monthly":
                timing_desc = f"• <b>Fréquence :</b> Le <b>{jour_mois}</b> du mois à <b>{heure:02d}h00</b>\n"

        text = (
            f"🔔 <b>Notifications & Rappels</b>\n"
            f"👤 Profil : <b>{alias}</b>\n\n"
            f"📩 <b>Nouvelles demandes :</b> {mode_new_str}\n"
            f"⏰ <b>Rappels des suivis :</b> {mode_rap_str}\n"
            f"{timing_desc}\n"
            "<i>Cliquez pour ajuster vos préférences :</i>"
        )
        return text, InlineKeyboardMarkup(keyboard)

    async def handle_callback_routing(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Aiguillage des clics sur les préférences."""
        query = update.callback_query
        if not query or not update.effective_user:
            return

        user_id = int(update.effective_user.id)

        if data == "pref_new_sound":
            self.db_manager.update_admin_preference(user_id, "notif_new_mode", "sound")
        elif data == "pref_new_silent":
            self.db_manager.update_admin_preference(user_id, "notif_new_mode", "silent")
        elif data == "pref_new_off":
            self.db_manager.update_admin_preference(user_id, "notif_new_mode", "off")

        elif data == "pref_rap_sound":
            self.db_manager.update_admin_preference(user_id, "rappel_mode", "sound")
        elif data == "pref_rap_silent":
            self.db_manager.update_admin_preference(user_id, "rappel_mode", "silent")
        elif data == "pref_rap_off":
            self.db_manager.update_admin_preference(user_id, "rappel_mode", "off")

        elif data == "pref_freq_daily":
            self.db_manager.update_admin_preference(user_id, "rappel_freq", "daily")
        elif data == "pref_freq_weekly":
            self.db_manager.update_admin_preference(user_id, "rappel_freq", "weekly")
        elif data == "pref_freq_monthly":
            self.db_manager.update_admin_preference(user_id, "rappel_freq", "monthly")

        elif data == "pref_pick_hour":
            await self._show_hour_picker(query, user_id)
            return
        elif data.startswith("pref_set_hour_"):
            hour = int(data.replace("pref_set_hour_", ""))
            self.db_manager.update_admin_preference(user_id, "rappel_heure", hour)

        elif data == "pref_pick_weekday":
            await self._show_weekday_picker(query, user_id)
            return
        elif data.startswith("pref_set_weekday_"):
            day_idx = int(data.replace("pref_set_weekday_", ""))
            self.db_manager.update_admin_preference(user_id, "rappel_jour_semaine", day_idx)

        elif data == "pref_pick_monthday":
            await self._show_monthday_picker(query, user_id)
            return
        elif data.startswith("pref_set_monthday_"):
            mday = int(data.replace("pref_set_monthday_", ""))
            self.db_manager.update_admin_preference(user_id, "rappel_jour_mois", mday)

        prefs = self.db_manager.get_admin_preferences(user_id)
        text, keyboard = self._build_menu_content(user_id, prefs)
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)

    async def _show_hour_picker(self, query, user_id: int):
        prefs = self.db_manager.get_admin_preferences(user_id)
        current_h = prefs.get("rappel_heure", 18)

        grid = []
        for row_start in range(0, 24, 4):
            row = []
            for h in range(row_start, row_start + 4):
                label = f"• {h:02d}h •" if h == current_h else f"{h:02d}h"
                row.append(InlineKeyboardButton(label, callback_data=f"pref_set_hour_{h}"))
            grid.append(row)

        grid.append([InlineKeyboardButton("🔙 Retour", callback_data="menu_notifs")])
        await query.edit_message_text(
            "⏰ <b>Sélectionnez l'heure du rappel :</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(grid),
        )

    async def _show_weekday_picker(self, query, user_id: int):
        prefs = self.db_manager.get_admin_preferences(user_id)
        current_d = prefs.get("rappel_jour_semaine", 6)

        rows = []
        for idx, day in enumerate(JOURS_SEMAINE):
            label = f"✅ {day}" if idx == current_d else day
            rows.append([InlineKeyboardButton(label, callback_data=f"pref_set_weekday_{idx}")])

        rows.append([InlineKeyboardButton("🔙 Retour", callback_data="menu_notifs")])
        await query.edit_message_text(
            "📅 <b>Sélectionnez le jour de la semaine :</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(rows),
        )

    async def _show_monthday_picker(self, query, user_id: int):
        prefs = self.db_manager.get_admin_preferences(user_id)
        current_md = prefs.get("rappel_jour_mois", 1)

        common_days = [1, 5, 10, 15, 20, 25, 28]
        grid = []
        row = []
        for d in common_days:
            label = f"• {d} •" if d == current_md else str(d)
            row.append(InlineKeyboardButton(label, callback_data=f"pref_set_monthday_{d}"))
            if len(row) == 4:
                grid.append(row)
                row = []
        if row:
            grid.append(row)

        grid.append([InlineKeyboardButton("🔙 Retour", callback_data="menu_notifs")])
        await query.edit_message_text(
            "📅 <b>Sélectionnez le jour du mois :</b>\n<i>(Limité au 28 pour s'adapter à tous les mois)</i>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(grid),
        )