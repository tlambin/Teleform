"""ui/staff/notifs.py
Composants visuels, gabarits textuels et claviers pour les alertes staff, rappels et surveillance.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

JOURS_SEMAINE = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]


# ==============================================================================
# 1. MENU PRINCIPAL NOTIFICATIONS & RAPPELS
# ==============================================================================

def build_menu_content(
    user_id: int,
    prefs: dict,
    can_monitor: bool,
    raw_alias: str
) -> tuple[str, InlineKeyboardMarkup]:
    """Construit le panneau principal des notifications et fréquences de rappel."""

    # 1. Alertes nouvelles demandes (défaut 'off')
    mode_new = prefs.get("notif_new_mode", "off")

    # 2. Rappels de suivis (binaire 'sound' ou 'silent', jamais 'off')
    mode_rappel = prefs.get("rappel_mode", "silent")
    if mode_rappel == "off":
        mode_rappel = "silent"

    # 3. Fréquence et horaire (défaut weekly, dimanche, 21h)
    freq = prefs.get("rappel_freq", "weekly")
    heure = int(prefs.get("rappel_heure", 21))
    jour_sem = int(prefs.get("rappel_jour_semaine", 6))
    jour_mois = int(prefs.get("rappel_jour_mois", 1))

    # --- TEXTES ET ÉMOJIS D'ÉTAT ---
    if mode_new == "sound":
        txt_new = "🔊 Activées (Sonore)"
    elif mode_new == "silent":
        txt_new = "🔇 Activées (Silencieuse)"
    else:
        txt_new = "🔕 Désactivées"

    if mode_rappel == "sound":
        txt_rap = "🔊 Activés (Sonore)"
    else:
        txt_rap = "🔇 Activés (Silencieux)"

    if freq == "daily":
        timing_str = f"Tous les jours à {heure:02d}h00"
    elif freq == "weekly" and 0 <= jour_sem < len(JOURS_SEMAINE):
        timing_str = f"Tous les {JOURS_SEMAINE[jour_sem].lower()}s à {heure:02d}h00"
    elif freq == "monthly":
        timing_str = f"Le {jour_mois} du mois à {heure:02d}h00"
    else:
        timing_str = f"À {heure:02d}h00"

    text = (
        "🔔 <b>NOTIFICATIONS ET RAPPELS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Configurez vos alertes et la fréquence de vos rappels.</i>\n\n"
        f"• <b>Nouvelles demandes :</b>\n{txt_new}\n\n"
        f"• <b>Rappels de suivi :</b>\n{txt_rap}\n\n"
        f"• <b>Fréquence :</b>\n⏰ {timing_str}\n\n"
        "<i>Modifiez vos préférences avec les boutons ci-dessous :</i>"
    )

    # --- LABELS DYNAMIQUES DU CLAVIER ---
    b_new_sound = "✅ SONORE" if mode_new == "sound" else "🔊 SONORE"
    b_new_silent = "✅ SILENCIEUSE" if mode_new == "silent" else "🔇 SILENCIEUSE"
    b_new_off = "✅ COUPÉ" if mode_new == "off" else "🚫 COUPÉ"

    b_rap_sound = "✅ SONORE" if mode_rappel == "sound" else "🔊 SONORE"
    b_rap_silent = "✅ SILENCIEUX" if mode_rappel == "silent" else "🔇 SILENCIEUX"

    b_freq_daily = "✅ 1/JOUR" if freq == "daily" else "1/JOUR"
    b_freq_weekly = "✅ 1/SEMAINE" if freq == "weekly" else "1/SEMAINE"
    b_freq_monthly = "✅ 1/MOIS" if freq == "monthly" else "1/MOIS"

    keyboard = []

    # En tête : Surveillance staff (si superviseur ou owner)
    if can_monitor:
        keyboard.append([
            InlineKeyboardButton("🛰️ SURVEILLANCE STAFF 🛰️", callback_data="menu_surveillance_notifs")
        ])

    # Rangée 1 : Nouvelles demandes
    keyboard.append([
        InlineKeyboardButton(b_new_sound, callback_data="pref_new_sound"),
        InlineKeyboardButton(b_new_silent, callback_data="pref_new_silent"),
        InlineKeyboardButton(b_new_off, callback_data="pref_new_off"),
    ])

    # Rangée 2 : Rappels de suivi
    keyboard.append([
        InlineKeyboardButton("⏰", callback_data="noop"),
        InlineKeyboardButton(b_rap_sound, callback_data="pref_rap_sound"),
        InlineKeyboardButton(b_rap_silent, callback_data="pref_rap_silent"),
    ])

    # Rangée 3 : Fréquence
    keyboard.append([
        InlineKeyboardButton(b_freq_daily, callback_data="pref_freq_daily"),
        InlineKeyboardButton(b_freq_weekly, callback_data="pref_freq_weekly"),
        InlineKeyboardButton(b_freq_monthly, callback_data="pref_freq_monthly"),
    ])

    # Rangée 4 : Heure et Jour
    timing_row = [
        InlineKeyboardButton(f"🕒 {heure:02d}H", callback_data="pref_pick_hour")
    ]
    if freq == "weekly" and 0 <= jour_sem < len(JOURS_SEMAINE):
        timing_row.append(
            InlineKeyboardButton(f"📅 {JOURS_SEMAINE[jour_sem].upper()}", callback_data="pref_pick_weekday")
        )
    elif freq == "monthly":
        timing_row.append(
            InlineKeyboardButton(f"📅 LE {jour_mois}", callback_data="pref_pick_monthday")
        )
    keyboard.append(timing_row)

    # Rangée de retour
    keyboard.append([InlineKeyboardButton("⬅️ RETOUR", callback_data="menu_mon_profil")])

    return text, InlineKeyboardMarkup(keyboard)


# ==============================================================================
# 2. PANNEAU DE SURVEILLANCE STAFF (SUPERVISEURS)
# ==============================================================================

def build_surveillance_menu_content(prefs: dict) -> tuple[str, InlineKeyboardMarkup]:
    """Construit l'interface de surveillance avec interrupteurs dynamiques."""
    p_pec = bool(prefs.get("monitor_prise_en_charge", True))
    p_stat = bool(prefs.get("monitor_changement_statut", True))
    p_reu = bool(prefs.get("monitor_reussite", True))
    p_ab = bool(prefs.get("monitor_abandon", True))
    p_smsg = bool(prefs.get("monitor_staff_msg", True))
    p_umsg = bool(prefs.get("monitor_user_msg", True))

    def _state_header(emoji_bell: str, label: str, active: bool) -> str:
        state_txt = "Activé" if active else "Désactivé"
        return f"{emoji_bell} {label} • {state_txt}"

    bell_pec = "🔔" if p_pec else "🔕"
    bell_stat = "🔔" if p_stat else "🔕"
    bell_reu = "🔔" if p_reu else "🔕"
    bell_ab = "🔔" if p_ab else "🔕"
    bell_smsg = "🔔" if p_smsg else "🔕"
    bell_umsg = "🔔" if p_umsg else "🔕"

    hdr_pec = _state_header(bell_pec, "Prise en charge", p_pec)
    hdr_stat = _state_header(bell_stat, "Changement de statut", p_stat)
    hdr_reu = _state_header(bell_reu, "Réussite", p_reu)
    hdr_ab = _state_header(bell_ab, "Abandon", p_ab)
    hdr_smsg = _state_header(bell_smsg, "Messages de l'équipe", p_smsg)
    hdr_umsg = _state_header(bell_umsg, "Messages des clients", p_umsg)

    text = (
        "🛰️ <b>SURVEILLANCE DU STAFF</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Activez / désactivez chaque type d'alerte :\n\n"
        f"{hdr_pec}\n"
        "<i>Vous êtes alerté lorsqu'un agent prend en charge une nouvelle demande.</i>\n\n"
        f"{hdr_stat}\n"
        "<i>Vous êtes alerté dès qu'un agent modifie le statut d'une demande en cours.</i>\n\n"
        f"{hdr_reu}\n"
        "<i>Vous êtes alerté quand un agent termine une demande avec succès.</i>\n\n"
        f"{hdr_ab}\n"
        "<i>Vous êtes alerté si un agent abandonne une demande.</i>\n\n"
        f"{hdr_smsg}\n"
        "<i>Vous recevez les messages envoyés par les agents.</i>\n\n"
        f"{hdr_umsg}\n"
        "<i>Vous recevez les messages envoyés par les clients.</i>"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"💌 EN CHARGE {bell_pec}", callback_data="toggle_mon_prise_en_charge"),
            InlineKeyboardButton(f"🔄 STATUT {bell_stat}", callback_data="toggle_mon_changement_statut"),
        ],
        [
            InlineKeyboardButton(f"✅ RÉUSSITE {bell_reu}", callback_data="toggle_mon_reussite"),
            InlineKeyboardButton(f"❌ ABANDON {bell_ab}", callback_data="toggle_mon_abandon"),
        ],
        [
            InlineKeyboardButton(f"💬 STAFF {bell_smsg}", callback_data="toggle_mon_staff_msg"),
            InlineKeyboardButton(f"💬 CLIENTS {bell_umsg}", callback_data="toggle_mon_user_msg"),
        ],
        [
            InlineKeyboardButton("⬅️ RETOUR", callback_data="menu_notifs")
        ]
    ])
    return text, keyboard


# ==============================================================================
# 3. SÉLECTEURS D'HORAIRE ET DE JOURS
# ==============================================================================

def build_hour_picker_keyboard(current_h: int) -> InlineKeyboardMarkup:
    """Clavier de sélection d'heure (0h à 23h)."""
    grid = []
    for row_start in range(0, 24, 4):
        row = []
        for h in range(row_start, row_start + 4):
            label = f"• {h:02d}h •" if h == current_h else f"{h:02d}h"
            row.append(InlineKeyboardButton(label, callback_data=f"pref_set_hour_{h}"))
        grid.append(row)
    grid.append([InlineKeyboardButton("⬅️ RETOUR", callback_data="menu_notifs")])
    return InlineKeyboardMarkup(grid)


def build_weekday_picker_keyboard(current_d: int) -> InlineKeyboardMarkup:
    """Clavier de sélection du jour de la semaine (en MAJ, 2 colonnes)."""
    grid = []
    row = []

    for idx, day in enumerate(JOURS_SEMAINE):
        day_upper = day.upper()
        label = f"✅ {day_upper}" if idx == current_d else day_upper
        row.append(InlineKeyboardButton(label, callback_data=f"pref_set_weekday_{idx}"))

        if len(row) == 2:
            grid.append(row)
            row = []

    if row:
        grid.append(row)

    grid.append([InlineKeyboardButton("⬅️ RETOUR", callback_data="menu_notifs")])
    return InlineKeyboardMarkup(grid)


def build_monthday_picker_keyboard(current_md: int) -> InlineKeyboardMarkup:
    """Clavier calendrier de sélection du jour du mois (1 à 31, 7 colonnes)."""
    grid = []
    row = []

    for d in range(1, 32):
        label = f"✅ {d}" if d == current_md else str(d)
        row.append(InlineKeyboardButton(label, callback_data=f"pref_set_monthday_{d}"))
        if len(row) == 7:
            grid.append(row)
            row = []

    if row:
        grid.append(row)

    grid.append([InlineKeyboardButton("⬅️ RETOUR", callback_data="menu_notifs")])
    return InlineKeyboardMarkup(grid)