"""Module de gestion des préférences de notifications, rappels staff et notifications utilisateurs."""

import html
import logging
from typing import Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import Forbidden, TelegramError
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

JOURS_SEMAINE = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]


def get_statut_explication(statut: str, is_difficile: bool = False, reussie_substatus: Optional[str] = None) -> str:
    """Retourne l'explication textuelle officielle du statut pour le demandeur."""
    clean = str(statut or "").strip()

    if clean == "📥 Reçue":
        return "La demande a bien été reçue. Elle est actuellement en attente d'attribution."

    if clean == "⏳ En attente":
        if is_difficile:
            return "Un opérateur a pris en charge la demande et attend un contact. La cible n'a toujours pas répondu (délai > 1 mois)."
        return "Un opérateur a pris en charge la demande. Il attend d'établir un premier contact."

    if clean == "🔄 En cours":
        if is_difficile:
            return "Le contact est établi avec la cible, mais celle-ci s'avère réticente ou peu encline à être sollicitée."
        return "Le contact est établi. La demande est en cours de traitement."

    if clean == "✅ Réussie":
        if reussie_substatus == "terminee":
            return "La demande est terminée avec succès. Aucun contenu supplémentaire ne sera recherché."
        return "La demande a été réussie avec succès ! Le suivi reste actif car d'autres contenus peuvent être obtenus."

    if clean == "❌ Abandonnée":
        return "La demande n'a pas pu aboutir. Consultez le motif rédigé par votre référent."

    return "Le statut de votre demande a été mis à jour."


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
            num_str = f"#{request_number}" if request_number else f"ID-{demande_id}"
            prenom_esc = html.escape(str(prenom_cible or "votre contact"))
            old_esc = html.escape(str(old_status or "Inconnu"))
            alias_esc = html.escape(str(admin_alias or "Équipe"))

            nouveau_libelle = self.db_manager.format_statut_display(new_status, is_difficile, reussie_substatus)
            new_esc = html.escape(nouveau_libelle)
            explication_esc = html.escape(get_statut_explication(new_status, is_difficile, reussie_substatus))

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

            lignes = [
                f"📢 <b>Mise à jour de votre demande {num_str}</b>\n",
                f"👤 Cible : <b>{prenom_esc}</b>",
                f"• Ancien statut : <s>{old_esc}</s>",
                f"• Nouveau statut : <b>{new_esc}</b>\n",
                "ℹ️ <b>Signification :</b>",
                f"« <i>{explication_esc}</i> »\n",
            ]

            keyboard_buttons = []

            needs_payment = (new_status == "✅ Réussie" and is_prio and montant > 0 and paiement_statut == "en_attente")

            if needs_payment:
                stars_amount = int(montant * 50)
                lignes.append(
                    "💰 <b>Règlement requis pour la livraison :</b>\n"
                    f"Votre demande prioritaire a abouti. Le montant alloué est de <b>{montant:.2f} €</b> ({stars_amount} ⭐).\n"
                    "Veuillez procéder au règlement pour débloquer l'envoi immédiat de vos contenus par votre référent :\n"
                )
                keyboard_buttons.append([
                    InlineKeyboardButton(f"⭐ Régler en Stars ({stars_amount} ⭐)", callback_data=f"pay_stars_prio_{demande_id}")
                ])
                keyboard_buttons.append([
                    InlineKeyboardButton("💬 Autre moyen (Contacter mon référent)", callback_data=f"pay_contact_prio_{demande_id}")
                ])

            if new_status == "❌ Abandonnée" and raison_abandon:
                lignes.append(f"📝 <b>Motif :</b> {html.escape(str(raison_abandon))}\n")

            lignes.append(f"👨‍💼 <b>Référent :</b> {alias_esc}")

            keyboard_buttons.append([
                InlineKeyboardButton("🗂️ Consulter mes demandes", callback_data="voir_demandes")
            ])

            await context.bot.send_message(
                chat_id=int(user_id),
                text="\n".join(lignes),
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard_buttons),
                disable_web_page_preview=True,
            )
            logger.info("Notification de statut envoyée à %s pour la demande %s (%s)", user_id, demande_id, nouveau_libelle)
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
        text, keyboard = self._build_menu_content(user.id, prefs)

        if query:
            await self._render_clean_menu(query, context, text, keyboard)
        elif update.message:
            await update.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)

    def _build_menu_content(self, user_id: int, prefs: dict):
        raw_alias = self.db_manager.get_staff_alias(user_id) or f"Staff_{user_id}"
        alias_esc = html.escape(str(raw_alias))

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
        heure = int(prefs.get("rappel_heure", 18))
        jour_sem = int(prefs.get("rappel_jour_semaine", 6))
        jour_mois = int(prefs.get("rappel_jour_mois", 1))

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

        if mode_rappel != "off":
            keyboard.append([
                InlineKeyboardButton(btn_freq_daily, callback_data="pref_freq_daily"),
                InlineKeyboardButton(btn_freq_weekly, callback_data="pref_freq_weekly"),
                InlineKeyboardButton(btn_freq_monthly, callback_data="pref_freq_monthly"),
            ])

            timing_row = [
                InlineKeyboardButton(f"⏰ {heure:02d}h00", callback_data="pref_pick_hour")
            ]
            if freq == "weekly" and 0 <= jour_sem < len(JOURS_SEMAINE):
                timing_row.append(InlineKeyboardButton(f"📅 {JOURS_SEMAINE[jour_sem]}", callback_data="pref_pick_weekday"))
            elif freq == "monthly":
                timing_row.append(InlineKeyboardButton(f"📅 Le {jour_mois} du mois", callback_data="pref_pick_monthday"))

            keyboard.append(timing_row)

        # Accès au sous-panneau de surveillance si le membre en a le droit
        privs = self.db_manager.get_admin_privileges(user_id)
        if privs.get("is_owner") or privs.get("can_monitor_staff"):
            keyboard.append([
                InlineKeyboardButton("👀 Alertes Surveillance Staff", callback_data="menu_surveillance_notifs")
            ])

        keyboard.append([InlineKeyboardButton("🔙 Paramètres", callback_data="parametres")])

        mode_new_str = {"sound": "🔊 Sonore", "silent": "🔇 Silencieuse", "off": "🔕 Désactivée"}.get(mode_new, "🔊 Sonore")
        mode_rap_str = {"sound": "🔊 Sonore", "silent": "🔇 Silencieux", "off": "❌ Désactivé"}.get(mode_rappel, "🔊 Sonore")

        timing_desc = ""
        if mode_rappel != "off":
            if freq == "daily":
                timing_desc = f"• <b>Fréquence :</b> Tous les jours à <b>{heure:02d}h00</b>\n"
            elif freq == "weekly" and 0 <= jour_sem < len(JOURS_SEMAINE):
                timing_desc = f"• <b>Fréquence :</b> Chaque <b>{JOURS_SEMAINE[jour_sem]}</b> à <b>{heure:02d}h00</b>\n"
            elif freq == "monthly":
                timing_desc = f"• <b>Fréquence :</b> Le <b>{jour_mois}</b> du mois à <b>{heure:02d}h00</b>\n"

        text = (
            f"🔔 <b>Notifications & Rappels</b>\n"
            f"👤 Profil : <b>{alias_esc}</b>\n\n"
            f"📩 <b>Nouvelles demandes :</b> {mode_new_str}\n"
            f"⏰ <b>Rappels des suivis :</b> {mode_rap_str}\n"
            f"{timing_desc}\n"
            "<i>Cliquez pour ajuster vos préférences :</i>"
        )
        return text, InlineKeyboardMarkup(keyboard)

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

        p_pec = bool(prefs.get("monitor_prise_en_charge", True))
        p_stat = bool(prefs.get("monitor_changement_statut", True))
        p_ab = bool(prefs.get("monitor_abandon", True))
        p_reu = bool(prefs.get("monitor_reussite", True))
        p_smsg = bool(prefs.get("monitor_staff_msg", True))
        p_umsg = bool(prefs.get("monitor_user_msg", True))

        text = (
            "👀 <b>SURVEILLANCE DU STAFF — ALERTES</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "Activez ou coupez individuellement chaque type d'alerte :\n\n"
            f"• <b>Prise en charge :</b> {'🔔 Activé' if p_pec else '🔕 Coupé'}\n"
            f"• <b>Changement statut :</b> {'🔔 Activé' if p_stat else '🔕 Coupé'}\n"
            f"• <b>Abandon dossier :</b> {'🔔 Activé' if p_ab else '🔕 Coupé'}\n"
            f"• <b>Réussite dossier :</b> {'🔔 Activé' if p_reu else '🔕 Coupé'}\n"
            f"• <b>Messages Staff (Envoyés) :</b> {'🔔 Activé' if p_smsg else '🔕 Coupé'}\n"
            f"• <b>Messages Demandeur (Reçus) :</b> {'🔔 Activé' if p_umsg else '🔕 Coupé'}"
        )

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(f"{'🟢' if p_pec else '🔴'} Prise en charge", callback_data="toggle_mon_prise_en_charge"),
                InlineKeyboardButton(f"{'🟢' if p_stat else '🔴'} Changement statut", callback_data="toggle_mon_changement_statut")
            ],
            [
                InlineKeyboardButton(f"{'🟢' if p_ab else '🔴'} Abandons", callback_data="toggle_mon_abandon"),
                InlineKeyboardButton(f"{'🟢' if p_reu else '🔴'} Réussites", callback_data="toggle_mon_reussite")
            ],
            [
                InlineKeyboardButton(f"{'🟢' if p_smsg else '🔴'} Msg Staff", callback_data="toggle_mon_staff_msg"),
                InlineKeyboardButton(f"{'🟢' if p_umsg else '🔴'} Msg Demandeur", callback_data="toggle_mon_user_msg")
            ],
            [InlineKeyboardButton("⬅️ RETOUR", callback_data="menu_notifs")]
        ])

        await self._render_clean_menu(query, context, text, keyboard)

    async def handle_surveillance_toggle(self, update: Update, context: ContextTypes.DEFAULT_TYPE, key: str):
        """Bascule l'interrupteur d'alerte ciblé."""
        query = update.callback_query
        user_id = update.effective_user.id
        col_name = f"monitor_{key}"

        with self.db_manager.get_cursor() as cursor:
            cursor.execute(f"SELECT {col_name} FROM admin_preferences WHERE user_id = %s", (user_id,))
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

        # Sous-menu de surveillance
        if data == "menu_surveillance_notifs":
            await query.answer()
            await self.show_surveillance_notifs_menu(update, context)
            return

        if data.startswith("toggle_mon_"):
            key = data.replace("toggle_mon_", "")
            await self.handle_surveillance_toggle(update, context, key)
            return

        # Retour menu principal des notifs
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
            await self._show_hour_picker(query, context, user_id)
            return
        elif data.startswith("pref_set_hour_"):
            try:
                hour = int(data.replace("pref_set_hour_", ""))
                if 0 <= hour <= 23:
                    self.db_manager.update_admin_preference(user_id, "rappel_heure", hour)
            except (ValueError, TypeError):
                pass

        elif data == "pref_pick_weekday":
            await self._show_weekday_picker(query, context, user_id)
            return
        elif data.startswith("pref_set_weekday_"):
            try:
                day_idx = int(data.replace("pref_set_weekday_", ""))
                if 0 <= day_idx < len(JOURS_SEMAINE):
                    self.db_manager.update_admin_preference(user_id, "rappel_jour_semaine", day_idx)
            except (ValueError, TypeError):
                pass

        elif data == "pref_pick_monthday":
            await self._show_monthday_picker(query, context, user_id)
            return
        elif data.startswith("pref_set_monthday_"):
            try:
                mday = int(data.replace("pref_set_monthday_", ""))
                if 1 <= mday <= 28:
                    self.db_manager.update_admin_preference(user_id, "rappel_jour_mois", mday)
            except (ValueError, TypeError):
                pass

        prefs = self.db_manager.get_admin_preferences(user_id)
        text, keyboard = self._build_menu_content(user_id, prefs)
        await self._render_clean_menu(query, context, text, keyboard)

    async def _show_hour_picker(self, query, context: ContextTypes.DEFAULT_TYPE, user_id: int):
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
        text = "⏰ <b>Sélectionnez l'heure du rappel :</b>"
        await self._render_clean_menu(query, context, text, InlineKeyboardMarkup(grid))

    async def _show_weekday_picker(self, query, context: ContextTypes.DEFAULT_TYPE, user_id: int):
        prefs = self.db_manager.get_admin_preferences(user_id)
        current_d = prefs.get("rappel_jour_semaine", 6)

        rows = []
        for idx, day in enumerate(JOURS_SEMAINE):
            label = f"✅ {day}" if idx == current_d else day
            rows.append([InlineKeyboardButton(label, callback_data=f"pref_set_weekday_{idx}")])

        rows.append([InlineKeyboardButton("🔙 Retour", callback_data="menu_notifs")])
        text = "📅 <b>Sélectionnez le jour de la semaine :</b>"
        await self._render_clean_menu(query, context, text, InlineKeyboardMarkup(rows))

    async def _show_monthday_picker(self, query, context: ContextTypes.DEFAULT_TYPE, user_id: int):
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
        text = (
            "📅 <b>Sélectionnez le jour du mois :</b>\n"
            "<i>(Limité au 28 pour s'adapter à tous les mois)</i>"
        )
        await self._render_clean_menu(query, context, text, InlineKeyboardMarkup(grid))