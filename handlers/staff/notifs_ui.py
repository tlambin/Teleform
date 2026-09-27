"""Composants visuels, claviers et textes d'explication pour les notifications et rappels."""

import html
from typing import Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

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


def build_status_notification_content(
    request_number: Optional[int],
    demande_id: int,
    prenom_cible: str,
    old_status: str,
    new_status: str,
    is_difficile: bool,
    reussie_substatus: Optional[str],
    admin_alias: Optional[str],
    raison_abandon: Optional[str],
    is_prio: bool,
    montant: float,
    paiement_statut: str,
    db_manager
) -> tuple[str, InlineKeyboardMarkup]:
    """Construit le texte et le clavier de notification de statut pour le client."""
    num_str = f"#{request_number}" if request_number else f"ID-{demande_id}"
    prenom_esc = html.escape(str(prenom_cible or "votre contact"))
    old_esc = html.escape(str(old_status or "Inconnu"))
    alias_esc = html.escape(str(admin_alias or "Équipe"))

    nouveau_libelle = db_manager.format_statut_display(new_status, is_difficile, reussie_substatus)
    new_esc = html.escape(nouveau_libelle)
    explication_esc = html.escape(get_statut_explication(new_status, is_difficile, reussie_substatus))

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

    return "\n".join(lignes), InlineKeyboardMarkup(keyboard_buttons)


def build_menu_content(user_id: int, prefs: dict, can_monitor: bool, raw_alias: str) -> tuple[str, InlineKeyboardMarkup]:
    """Construit le panneau principal des préférences de notification."""
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
        [
            InlineKeyboardButton(btn_new_sound, callback_data="pref_new_sound"),
            InlineKeyboardButton(btn_new_silent, callback_data="pref_new_silent"),
            InlineKeyboardButton(btn_new_off, callback_data="pref_new_off"),
        ],
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

    if can_monitor:
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


def build_surveillance_menu_content(prefs: dict) -> tuple[str, InlineKeyboardMarkup]:
    """Construit le texte et le clavier pour les 6 alertes superviseur."""
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
    return text, keyboard


def build_hour_picker_keyboard(current_h: int) -> InlineKeyboardMarkup:
    """Clavier de sélection d'heure (0h - 23h)."""
    grid = []
    for row_start in range(0, 24, 4):
        row = []
        for h in range(row_start, row_start + 4):
            label = f"• {h:02d}h •" if h == current_h else f"{h:02d}h"
            row.append(InlineKeyboardButton(label, callback_data=f"pref_set_hour_{h}"))
        grid.append(row)
    grid.append([InlineKeyboardButton("🔙 Retour", callback_data="menu_notifs")])
    return InlineKeyboardMarkup(grid)


def build_weekday_picker_keyboard(current_d: int) -> InlineKeyboardMarkup:
    """Clavier de sélection du jour de la semaine."""
    rows = []
    for idx, day in enumerate(JOURS_SEMAINE):
        label = f"✅ {day}" if idx == current_d else day
        rows.append([InlineKeyboardButton(label, callback_data=f"pref_set_weekday_{idx}")])
    rows.append([InlineKeyboardButton("🔙 Retour", callback_data="menu_notifs")])
    return InlineKeyboardMarkup(rows)


def build_monthday_picker_keyboard(current_md: int) -> InlineKeyboardMarkup:
    """Clavier de sélection du jour du mois."""
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
    return InlineKeyboardMarkup(grid)