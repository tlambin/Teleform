"""Module de gestion des préférences de notifications, rappels staff et notifications utilisateurs."""

import logging
from typing import Optional
from telegram import InlineKeyboardMarkup, Update
from telegram.error import Forbidden, TelegramError
from telegram.ext import ContextTypes
from . import notifs_ui as ui

logger = logging.getLogger(__name__)

# Liste blanche stricte des colonnes de surveillance éditables
VALID_SURVEILLANCE_COLUMNS = frozenset({
    "monitor_prise_en_charge",
    "monitor_changement_statut",
    "monitor_abandon",
    "monitor_reussite",
    "monitor_staff_msg",
    "monitor_user_msg",
})


class NotifsManager:
    """Gestionnaire des préférences d'alertes staff et des notifications envoyées aux utilisateurs."""

    def __init__(self, db_manager, config):
        self.db_manager = db_manager
        self.config = config
        logger.info("NotifsManager initialisé avec support Staff/Admin, Surveillance & Paiement Prio")

    # ==================== NOTIFICATIONS UTILISATEURS ====================

    async def send_status_update_notification(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        user_id: int,
        demande_id: int,
        request_number: Optional[int],
        prenom_cible: str,
        old_status: str,
        new_status: str,
        is_difficile: bool = False,
        reussie_substatus: Optional[str] = None,
        admin_alias: Optional[str] = None,
        raison_abandon: Optional[str] = None,
    ) -> bool:
        """Transmet une alerte explicative au demandeur avec options de règlement pour les demandes prioritaires."""
        try:
            is_prio = False
            montant = 0.0
            paiement_statut = "non_requis"

            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    "SELECT prioritaire, montant, paiement_statut FROM demandes WHERE id = %s",
                    (demande_id,)
                )
                row = cursor.fetchone()
                if row:
                    is_prio = bool(row.get("prioritaire"))
                    montant = float(row.get("montant") or 0.0)
                    paiement_statut = str(row.get("paiement_statut") or "non_requis")

            text, keyboard = ui.build_status_notification_content(
                request_number=request_number,
                demande_id=demande_id,
                prenom_cible=prenom_cible,
                old_status=old_status,
                new_status=new_status,
                is_difficile=is_difficile,
                reussie_substatus=reussie_substatus,
                admin_alias=admin_alias,
                raison_abandon=raison_abandon,
                is_prio=is_prio,
                montant=montant,
                paiement_statut=paiement_statut,
                db_manager=self.db_manager
            )

            await context.bot.send_message(
                chat_id=int(user_id),
                text=text,
                parse_mode="HTML",
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )
            logger.info("Notification de statut envoyée à %s pour la demande %s", user_id, demande_id)
            return True

        except Forbidden:
            logger.warning("Notification bloquée (bot bloqué par l'utilisateur %s)", user_id)
            return False
        except TelegramError as exc:
            logger.error("Erreur Telegram envoi notification à %s : %s", user_id, exc)
            return False
        except Exception as exc:
            logger.error("Erreur inattendue envoi notification à %s : %s", user_id, exc, exc_info=True)
            return False

    # ==================== PRÉFÉRENCES STAFF ====================

    async def _render_clean_menu(self, query, context: ContextTypes.DEFAULT_TYPE, text: str, keyboard: InlineKeyboardMarkup):
        """Met à jour le message ou supprime la photo existante pour envoyer le menu texte."""
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
                reply_markup=keyboard,
                disable_web_page_preview=True
            )
        else:
            try:
                await query.edit_message_text(
                    text=text,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                    disable_web_page_preview=True
                )
            except Exception as exc:
                if "Message is not modified" not in str(exc):
                    if query.message:
                        await query.message.reply_text(
                            text=text,
                            parse_mode="HTML",
                            reply_markup=keyboard,
                            disable_web_page_preview=True
                        )

    async def show_notifs_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Affiche le panneau principal de réglage des notifications."""
        query = update.callback_query
        user = update.effective_user
        if not user or not self.config.is_staff(user.id):
            if query:
                await query.answer("❌ Accès non autorisé.", show_alert=True)
            return

        if query:
            await query.answer()

        prefs = self.db_manager.get_admin_preferences(user.id)
        raw_alias = self.db_manager.get_staff_alias(user.id) or f"Staff_{user.id}"
        privs = self.db_manager.get_admin_privileges(user.id)
        can_monitor = bool(privs.get("is_owner") or privs.get("can_monitor_staff"))

        text, keyboard = ui.build_menu_content(user.id, prefs, can_monitor, raw_alias)

        if query:
            await self._render_clean_menu(query, context, text, keyboard)
        elif update.message:
            await update.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)

    # ==================== SOUS-PANNEAU SURVEILLANCE DU STAFF ====================

    async def show_surveillance_notifs_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Affiche le menu de réglage des 6 notifications de surveillance pour les superviseurs."""
        query = update.callback_query
        user_id = update.effective_user.id

        privs = self.db_manager.get_admin_privileges(user_id)
        if not (privs.get("is_owner") or privs.get("can_monitor_staff")):
            if query:
                await query.answer("❌ Option réservée aux superviseurs.", show_alert=True)
            return

        with self.db_manager.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT monitor_prise_en_charge, monitor_changement_statut, monitor_abandon,
                       monitor_reussite, monitor_staff_msg, monitor_user_msg
                FROM admin_preferences WHERE user_id = %s
                """,
                (user_id,)
            )
            prefs = cursor.fetchone() or {}

        text, keyboard = ui.build_surveillance_menu_content(prefs)
        await self._render_clean_menu(query, context, text, keyboard)

    async def handle_surveillance_toggle(self, update: Update, context: ContextTypes.DEFAULT_TYPE, key: str):
        """Bascule l'interrupteur d'alerte ciblé avec validation stricte par liste blanche."""
        query = update.callback_query
        user_id = update.effective_user.id
        col_name = f"monitor_{key}"

        if col_name not in VALID_SURVEILLANCE_COLUMNS:
            logger.warning("Tentative d'accès à une colonne non autorisée : '%s' par l'utilisateur %s", col_name, user_id)
            if query:
                await query.answer("❌ Option non reconnue.", show_alert=True)
            return

        with self.db_manager.get_cursor() as cursor:
            cursor.execute(f"SELECT `{col_name}` FROM admin_preferences WHERE user_id = %s", (user_id,))
            row = cursor.fetchone()
            current = bool(row.get(col_name, True)) if row and row.get(col_name) is not None else True

        new_val = not current
        self.db_manager.update_admin_preference(user_id, col_name, new_val)
        await query.answer(f"Option {'activée 🔔' if new_val else 'coupée 🔕'}")
        await self.show_surveillance_notifs_menu(update, context)

    # ==================== ROUTEUR DES CALLBACKS ====================

    async def handle_callback_routing(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Aiguillage des clics sur les préférences avec persistance et protection anti-400."""
        query = update.callback_query
        if not query or not update.effective_user:
            return

        user_id = int(update.effective_user.id)

        if data == "menu_surveillance_notifs":
            await query.answer()
            await self.show_surveillance_notifs_menu(update, context)
            return

        if data.startswith("toggle_mon_"):
            key = data.replace("toggle_mon_", "")
            await self.handle_surveillance_toggle(update, context, key)
            return

        if data == "menu_notifs":
            await query.answer()
            await self.show_notifs_menu(update, context)
            return

        await query.answer()

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
            prefs = self.db_manager.get_admin_preferences(user_id)
            current_h = prefs.get("rappel_heure", 18)
            grid = ui.build_hour_picker_keyboard(current_h)
            text = "⏰ <b>Sélectionnez l'heure du rappel :</b>"
            await self._render_clean_menu(query, context, text, grid)
            return

        elif data.startswith("pref_set_hour_"):
            try:
                hour = int(data.replace("pref_set_hour_", ""))
                if 0 <= hour <= 23:
                    self.db_manager.update_admin_preference(user_id, "rappel_heure", hour)
            except (ValueError, TypeError):
                pass

        elif data == "pref_pick_weekday":
            prefs = self.db_manager.get_admin_preferences(user_id)
            current_d = prefs.get("rappel_jour_semaine", 6)
            rows = ui.build_weekday_picker_keyboard(current_d)
            text = "📅 <b>Sélectionnez le jour de la semaine :</b>"
            await self._render_clean_menu(query, context, text, rows)
            return

        elif data.startswith("pref_set_weekday_"):
            try:
                day_idx = int(data.replace("pref_set_weekday_", ""))
                if 0 <= day_idx < len(ui.JOURS_SEMAINE):
                    self.db_manager.update_admin_preference(user_id, "rappel_jour_semaine", day_idx)
            except (ValueError, TypeError):
                pass

        elif data == "pref_pick_monthday":
            prefs = self.db_manager.get_admin_preferences(user_id)
            current_md = prefs.get("rappel_jour_mois", 1)
            grid = ui.build_monthday_picker_keyboard(current_md)
            text = (
                "📅 <b>Sélectionnez le jour du mois :</b>\n"
                "<i>(Limité au 28 pour s'adapter à tous les mois)</i>"
            )
            await self._render_clean_menu(query, context, text, grid)
            return

        elif data.startswith("pref_set_monthday_"):
            try:
                mday = int(data.replace("pref_set_monthday_", ""))
                if 1 <= mday <= 28:
                    self.db_manager.update_admin_preference(user_id, "rappel_jour_mois", mday)
            except (ValueError, TypeError):
                pass

        prefs = self.db_manager.get_admin_preferences(user_id)
        raw_alias = self.db_manager.get_staff_alias(user_id) or f"Staff_{user_id}"
        privs = self.db_manager.get_admin_privileges(user_id)
        can_monitor = bool(privs.get("is_owner") or privs.get("can_monitor_staff"))

        text, keyboard = ui.build_menu_content(user_id, prefs, can_monitor, raw_alias)
        await self._render_clean_menu(query, context, text, keyboard)