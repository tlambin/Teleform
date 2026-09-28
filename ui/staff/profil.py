"""ui/staff/profil.py
Composants visuels, gabarits textuels et claviers pour la gestion du profil Staff,
des fiches utilisateurs et des fiches d'archives.
"""

import html
import time
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from utils.validators import convert_utc_to_paris


# ==============================================================================
# 1. MENU PRINCIPAL DU PROFIL
# ==============================================================================

def get_mon_profil_menu(
    user_id: int,
    user_role: str,
    is_paused: bool,
    alias: str,
    is_primary_owner: bool,
    can_edit_alias: bool
) -> tuple[str, InlineKeyboardMarkup]:
    """Construit le sous-menu individuel 'MON PROFIL'."""
    is_admin = user_role in ["admin", "owner"]
    statut_dispo = "⏸️ <b>En pause</b>" if is_paused else "🟢 <b>En service</b>"
    alias_esc = html.escape(str(alias or f"Membre_{user_id}"))

    message = (
        "👤 <b>MON PROFIL</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"• <b>Identité :</b> <code>{alias_esc}</code>\n"
        f"• <b>Disponibilité :</b> {statut_dispo}\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Gérez vos paramètres individuels :"
    )
    keyboard = [
        [InlineKeyboardButton("🔔 NOTIFICATIONS 🔔", callback_data="menu_notifs")],
        [InlineKeyboardButton("🎯 MES CRITÈRES 🎯", callback_data="staff_self_prefs")],
    ]

    if is_admin or can_edit_alias:
        keyboard.append([
            InlineKeyboardButton("🏷️ MODIFIER MON ALIAS 🏷️", callback_data="modifier_alias")
        ])

    keyboard.append([
        InlineKeyboardButton("💰 MOYENS DE PAIEMENT 💰", callback_data="staff_payment_settings")
    ])

    if is_paused:
        keyboard.append([
            InlineKeyboardButton("▶️ REPRENDRE LE SERVICE ▶️", callback_data="admin_resume")
        ])
    else:
        keyboard.append([
            InlineKeyboardButton("⏸️ SE METTRE EN PAUSE ⏸️", callback_data="admin_pause_prompt")
        ])

    if (user_role in ["staff", "admin"]) or (user_role == "owner" and not is_primary_owner):
        keyboard.append([
            InlineKeyboardButton("❌ DÉMISSIONNER ❌", callback_data="menu_demission")
        ])

    keyboard.append([
        InlineKeyboardButton("🧮 MES STATS", callback_data=f"profil_admin_{user_id}"),
        InlineKeyboardButton("📦 MES ARCHIVES", callback_data="demandes_archives"),
    ])
    keyboard.append([
        InlineKeyboardButton("⬅️ RETOUR", callback_data="parametres")
    ])

    return message, InlineKeyboardMarkup(keyboard)


# ==============================================================================
# 2. GESTION DE L'ALIAS
# ==============================================================================

def get_alias_locked_content() -> tuple[str, InlineKeyboardMarkup]:
    """Message et clavier quand un alias est déjà verrouillé."""
    text = (
        "🔒 <b>Alias verrouillé</b>\n\n"
        "Vous avez déjà configuré votre alias officiel. "
        "Seule la direction peut le modifier désormais."
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ RETOUR", callback_data="menu_mon_profil")]])
    return text, kb


def build_alias_prompt_content(
    target_alias: str,
    target_id: int,
    user_id: int,
    is_owner: bool
) -> tuple[str, InlineKeyboardMarkup]:
    """Construit l'invite de saisie du nouvel alias conforme à la maquette."""
    target_alias_esc = html.escape(str(target_alias))

    if is_owner and target_id != user_id:
        text = (
            "👑 <b>MODIFICATION D'ALIAS (ADMIN)</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Modification forcée pour le membre (ID : <code>{target_id}</code>).\n\n"
            f"• <b>Alias actuel :</b> {target_alias_esc}\n"
            "• <b>Limite :</b> 30 caractères maximum\n"
            "• <b>Contrainte :</b> Lettres, chiffres, espaces, tirets et underscores autorisés\n\n"
            "<i>Envoyez directement le nouvel alias dans le chat :</i>"
        )
        retour_btn = InlineKeyboardButton("❌ ANNULER", callback_data="gerer_staff")
    else:
        text = (
            "🏷️ <b>MODIFIER MON ALIAS</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "Configurez votre identifiant unique.\n\n"
            f"<b>Alias actuel :</b> {target_alias_esc}\n\n"
            "• <b>Limite :</b> 30 caractères maximum\n"
            "• <b>Contrainte :</b> Lettres, chiffres, espaces, tirets et underscores autorisés\n\n"
            "<i>Envoyez directement votre nouvel alias dans le chat :</i>"
        )
        retour_btn = InlineKeyboardButton("❌ ANNULER", callback_data="menu_mon_profil")

    return text, InlineKeyboardMarkup([[retour_btn]])


def build_alias_success_content(
    new_alias: str,
    target_id: int,
    user_id: int,
    is_owner: bool
) -> tuple[str, InlineKeyboardMarkup]:
    """Construit le message de confirmation et le clavier de redirection."""
    new_alias_esc = html.escape(str(new_alias))

    if is_owner and target_id != user_id:
        retour_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("👥 Équipe Staff", callback_data="gerer_staff")],
            [InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")]
        ])
        succes_msg = (
            f"✅ <b>Alias mis à jour avec succès !</b>\n\n"
            f"👤 <b>Membre (ID {target_id}) :</b> <code>{new_alias_esc}</code>"
        )
    else:
        verrou_txt = "\n\n🔒 <i>Votre alias est désormais verrouillé et ne peut plus être modifié.</i>"
        retour_kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("⬅️ MON PROFIL", callback_data="menu_mon_profil")
        ]])
        succes_msg = f"✅ <b>Alias mis à jour :</b> <code>{new_alias_esc}</code>{verrou_txt}"

    return succes_msg, retour_kb


def get_cancel_alias_content(is_owner: bool, target_id: int, user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Message et clavier d'annulation de changement d'alias."""
    if is_owner and target_id and target_id != user_id:
        callback_target = "gerer_staff"
        btn_label = "👥 Équipe Staff"
    else:
        callback_target = "menu_mon_profil"
        btn_label = "⬅️ MON PROFIL"

    msg = "❌ <b>Modification d'alias annulée.</b>"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(btn_label, callback_data=callback_target)]])
    return msg, kb


# ==============================================================================
# 3. MOYENS DE PAIEMENT
# ==============================================================================

def get_staff_payment_settings_menu(accept_stars: bool, accept_direct: bool) -> tuple[str, InlineKeyboardMarkup]:
    """Menu interactif de configuration des moyens de paiement."""
    st_stars = "✅ Activé" if accept_stars else "❌ Désactivé"
    st_direct = "✅ Activé" if accept_direct else "❌ Désactivé"

    text = (
        "💳 <b>MOYENS DE PAIEMENT ACCEPTÉS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Définissez vos méthodes de règlement proposées pour les demandes prioritaires :\n\n"
        f"• <b>Telegram Stars :</b> {st_stars}\n"
        f"• <b>Paiement direct :</b> {st_direct}\n"
        "(Paypal, unlockt, etc...)\n\n"
        "⚠️ <i>Vous devez conserver au minimum un moyen de paiement actif.</i>\n\n"
        "<i>Modifiez votre sélection avec les boutons ci-dessous :</i>"
    )

    btn_stars = f"⭐ TELEGRAM STARS {'✅' if accept_stars else '❌'}"
    btn_direct = f"💸 PAIEMENT DIRECT {'✅' if accept_direct else '❌'}"

    keyboard = [
        [InlineKeyboardButton(btn_stars, callback_data="toggle_pay_staff_accept_stars")],
        [InlineKeyboardButton(btn_direct, callback_data="toggle_pay_staff_accept_direct")],
        [InlineKeyboardButton("⬅️ RETOUR", callback_data="menu_mon_profil")],
    ]
    return text, InlineKeyboardMarkup(keyboard)


# ==============================================================================
# 4. CHOIX DES CRITÈRES
# ==============================================================================

def get_staff_self_preferences_menu(perms: dict, can_edit: bool) -> tuple[str, InlineKeyboardMarkup]:
    """Menu interactif de configuration des critères (réseaux, orientation, type)."""
    reseau = str(perms.get("perm_reseaux") or "all").lower()
    typ = str(perms.get("perm_type") or "all").lower()
    ori = str(perms.get("perm_orientation") or "hetero").lower()

    if reseau == "insta":
        txt_res = "🌆 Insta"
    elif reseau == "snap":
        txt_res = "👻 Snap"
    else:
        txt_res = "🌆 Insta + 👻 Snap"

    if ori == "hetero":
        txt_ori = "🫂 Hétéro"
    elif ori == "gay":
        txt_ori = "🌈 Gay"
    else:
        txt_ori = "🫂 Hétéro + 🌈 Gay"

    if typ == "standard_only":
        txt_typ = "🧾 Standard"
    elif typ == "prio_only":
        txt_typ = "💎 Prioritaire"
    else:
        txt_typ = "🧾 Standard + 💎 Prioritaire"

    text = (
        "🎯 <b>CHOIX DE MES CRITÈRES</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Configurez vos critères en un clic.\n\n"
        f"• <b>Réseaux :</b> {txt_res}\n"
        f"• <b>Orientation :</b> {txt_ori}\n"
        f"• <b>Type :</b> {txt_typ}\n\n"
        "<i>Modifiez votre sélection avec les boutons ci-dessous :</i>"
    )

    if not can_edit:
        text += "\n\n🔒 <i>Vos critères sont actuellement verrouillés par l'administration.</i>"

    prefix = "self_pref" if can_edit else "self_pref_locked"

    btn_res_insta = "✅ INSTA" if reseau == "insta" else "🌆 INSTA"
    btn_res_all = "✅ LES 2" if reseau == "all" else "LES 2"
    btn_res_snap = "✅ SNAP" if reseau == "snap" else "👻 SNAP"

    btn_ori_h = "✅ HÉTÉRO" if ori == "hetero" else "🫂 HÉTÉRO"
    btn_ori_all = "✅ LES 2" if ori in ("all", "bi") else "LES 2"
    btn_ori_g = "✅ GAY" if ori == "gay" else "🌈 GAY"

    btn_typ_std = "✅ STANDARD" if typ == "standard_only" else "🧾 STANDARD"
    btn_typ_all = "✅ LES 2" if typ == "all" else "LES 2"
    btn_typ_prio = "✅ PRIORITAIRE" if typ == "prio_only" else "💎 PRIORITAIRE"

    keyboard = [
        [
            InlineKeyboardButton(btn_res_insta, callback_data=f"{prefix}_res_insta"),
            InlineKeyboardButton(btn_res_all, callback_data=f"{prefix}_res_all"),
            InlineKeyboardButton(btn_res_snap, callback_data=f"{prefix}_res_snap"),
        ],
        [
            InlineKeyboardButton(btn_ori_h, callback_data=f"{prefix}_ori_hetero"),
            InlineKeyboardButton(btn_ori_all, callback_data=f"{prefix}_ori_all"),
            InlineKeyboardButton(btn_ori_g, callback_data=f"{prefix}_ori_gay"),
        ],
        [
            InlineKeyboardButton(btn_typ_std, callback_data=f"{prefix}_type_standard_only"),
            InlineKeyboardButton(btn_typ_all, callback_data=f"{prefix}_type_all"),
            InlineKeyboardButton(btn_typ_prio, callback_data=f"{prefix}_type_prio_only"),
        ],
        [InlineKeyboardButton("⬅️ RETOUR", callback_data="menu_mon_profil")],
    ]
    return text, InlineKeyboardMarkup(keyboard)


# ==============================================================================
# 5. MODE PAUSE
# ==============================================================================

def get_pause_prompt_menu(nb_actives: int) -> tuple[str, InlineKeyboardMarkup]:
    """Menu d'arbitrage lors de la mise en pause."""
    text = (
        "⏸️ <b>SE METTRE EN PAUSE</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Vous avez actuellement <b>{nb_actives} demande(s) en cours de traitement</b>.\n\n"
        "<i>Que souhaitez-vous faire ?</i>"
    )
    keyboard = [
        [
            InlineKeyboardButton("📥 CONSERVER", callback_data="admin_pause_keep"),
            InlineKeyboardButton("❌ ABANDONNER", callback_data="admin_pause_release"),
        ],
        [InlineKeyboardButton("⬅️ RETOUR", callback_data="menu_mon_profil")],
    ]
    return text, InlineKeyboardMarkup(keyboard)


def get_pause_empty_content() -> tuple[str, InlineKeyboardMarkup]:
    """Message d'activation de pause sans dossier actif."""
    text = (
        "⏸️ <b>Mode pause activé</b>\n\n"
        "• Vous ne recevrez plus aucune notification de nouvelle demande.\n"
        "• Vous n'apparaissez plus dans la liste de sélection VIP.\n"
        "• Vous n'avez aucun dossier actif en attente."
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ RETOUR", callback_data="menu_mon_profil")]])
    return text, kb


def get_pause_kept_content() -> tuple[str, InlineKeyboardMarkup]:
    """Confirmation de pause avec conservation des dossiers."""
    text = (
        "⏸️ <b>Mode pause activé (dossiers conservés)</b>\n\n"
        "• Vos demandes en cours restent assignées à votre compte.\n"
        "• Aucune nouvelle demande ne vous sera attribuée ni notifiée.\n"
        "• Vous pouvez continuer à traiter vos suivis à votre rythme."
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ RETOUR", callback_data="menu_mon_profil")]])
    return text, kb


def get_pause_released_content(count_abandoned: int) -> tuple[str, InlineKeyboardMarkup]:
    """Confirmation de pause avec libération des dossiers."""
    text = (
        f"⏸️ <b>Mode pause activé</b>\n\n"
        f"• {count_abandoned} dossier(s) libéré(s) et notifiés aux demandeurs.\n"
        "• Vous êtes désormais retiré du service jusqu'à votre reprise."
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ RETOUR", callback_data="menu_mon_profil")]])
    return text, kb


def get_resume_service_content() -> tuple[str, InlineKeyboardMarkup]:
    """Confirmation de reprise de service."""
    text = (
        "🟢 <b>Bon retour ! Vous êtes à nouveau en service.</b>\n\n"
        "• Vous recevrez à nouveau les alertes et notifications.\n"
        "• Vous êtes à nouveau sélectionnable par les clients VIP."
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ RETOUR", callback_data="menu_mon_profil")]])
    return text, kb


# ==============================================================================
# 6. DÉMISSION DU PERSONNEL
# ==============================================================================

def get_demission_choice_menu() -> tuple[str, InlineKeyboardMarkup]:
    """Choix de démission pour un profil cumulant Admin et Piégeur."""
    text = (
        "❌ <b>CHOIX DE DÉMISSION</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Vous occupez actuellement deux fonctions dans l'équipe :\n"
        "• 🧠 <b>Administrateur</b>\n"
        "• 🎣 <b>Piégeur</b>\n\n"
        "<i>De quel rôle souhaitez-vous démissionner ?</i>"
    )
    keyboard = [
        [
            InlineKeyboardButton("🧠 ADMIN 🧠", callback_data="demission_confirm_admin"),
            InlineKeyboardButton("🎣 PIÉGEUR 🎣", callback_data="demission_confirm_staff"),
        ],
        [InlineKeyboardButton("🧠 LES DEUX 🎣", callback_data="demission_confirm_all")],
        [InlineKeyboardButton("⬅️ RETOUR", callback_data="menu_mon_profil")],
    ]
    return text, InlineKeyboardMarkup(keyboard)


def get_demission_confirm_menu(scope: str) -> tuple[str, InlineKeyboardMarkup]:
    """Confirmation avant démission définitive."""
    if scope == "admin":
        role_label = "de l'<b>Administration</b>"
        warning = "Vous perdrez l'accès aux panneaux de gestion et de surveillance."
    elif scope == "staff":
        role_label = "de l'équipe des <b>Piégeurs</b>"
        warning = "Vos demandes en cours seront immédiatement libérées et remises dans la file."
    else:
        role_label = "de <b>toutes vos fonctions</b> (Admin & Piégeur)"
        warning = "Vous redeviendrez simple utilisateur. Vos dossiers actifs seront libérés."

    text = (
        "⚠️ <b>CONFIRMATION DE DÉMISSION</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Êtes-vous certain de vouloir démissionner {role_label} ?\n\n"
        f"<i>{warning}</i>\n\n"
        "Cette action prend effet immédiatement."
    )
    keyboard = [
        [InlineKeyboardButton("⚠️ OUI, DÉMISSIONNER", callback_data=f"demission_exec_{scope}")],
        [InlineKeyboardButton("⬅️ ANNULER", callback_data="menu_mon_profil")],
    ]
    return text, InlineKeyboardMarkup(keyboard)


# ==============================================================================
# 7. FICHE DE STATS DU PIÉGEUR
# ==============================================================================

def render_progress_bar(rate: float) -> str:
    """Génère une jauge graphique sur 10 blocs."""
    try:
        val = float(rate or 0)
    except (ValueError, TypeError):
        val = 0.0
    filled = int(round(val / 10))
    filled = max(0, min(10, filled))
    empty = 10 - filled
    return f"{'🟩' * filled}{'⬜' * empty}"


def format_admin_profile_text(admin_id: int, stats: dict, is_target_banned: bool, is_owner_target: bool) -> str:
    """Formate la fiche textuelle de performance d'un piégeur."""
    alias_esc = html.escape(str(stats.get("alias") or f"Membre_{admin_id}"))

    if is_owner_target:
        date_str = "Direction / Propriétaire"
    else:
        dt_added = stats.get("date_added")
        date_str = dt_added.strftime("%d/%m/%Y") if dt_added and hasattr(dt_added, "strftime") else "Inconnue"

    taux = stats.get("taux_reussite", 0)
    bar = render_progress_bar(taux)

    res_label = {"all": "Insta & Snap", "insta": "Insta seul", "snap": "Snap seul"}.get(
        stats.get("perm_reseaux"), str(stats.get("perm_reseaux", "all"))
    )
    typ_label = {"all": "Tous types", "prio_only": "Payantes", "standard_only": "Gratuites"}.get(
        stats.get("perm_type"), str(stats.get("perm_type", "all"))
    )

    montant_total = float(stats.get("montant_total") or 0.0)

    lines = [
        f"🦈 <b>Fiche Piégeur : {alias_esc}</b>",
        f"🆔 ID Telegram : <code>{admin_id}</code>",
        f"📅 Dans l'équipe : <b>{html.escape(date_str)}</b>",
        f"🛡️ Permissions : <i>{html.escape(str(res_label))} | {html.escape(str(typ_label))}</i>\n",
    ]

    if is_target_banned:
        lines.insert(1, "🚫 <b>STATUT : COMPTE ACTUELLEMENT BANNI</b>\n")

    lines.extend([
        "━━━━━━━━━━━━━━━━━━━━━━",
        "📊 <b>PERFORMANCE OPÉRATIONNELLE</b>\n",
        f"⏳ <b>En cours de traitement :</b> <code>{stats.get('en_cours', 0)}</code>",
        f"✅ <b>Demandes réussies :</b> <code>{stats.get('reussies', 0)}</code>",
        f"❌ <b>Demandes abandonnées :</b> <code>{stats.get('abandonnees', 0)}</code>",
        f"📦 <b>Total demandes clôturées :</b> <code>{stats.get('total_traitees', 0)}</code>\n",
        f"📈 <b>Taux de succès :</b> <b>{taux}%</b>",
        f"{bar}\n",
        "💎 <b>DOSSIERS PRIORITAIRES</b>",
        f"• Demandes prioritaires traitées : <b>{stats.get('prioritaires_traitees', 0)}</b>",
        f"• Volume financier traité : <b>{montant_total:.2f} €</b>"
    ])

    return "\n".join(lines)


def build_admin_profile_keyboard(
    admin_id: int,
    viewer_id: int,
    is_target_banned: bool,
    can_ban: bool,
    is_owner: bool,
    is_admin: bool,
    is_owner_target: bool
) -> InlineKeyboardMarkup:
    """Construit le clavier d'actions sur la fiche d'un piégeur."""
    buttons = [
        [InlineKeyboardButton("📂 VOIR SES DEMANDES", callback_data=f"staff_view_demandes_{admin_id}")]
    ]

    if can_ban and viewer_id != admin_id and not is_owner_target:
        if is_target_banned:
            buttons.append([InlineKeyboardButton("🟢 DÉBANNIR CE PIÉGEUR", callback_data=f"unban_staff_{admin_id}")])
        else:
            buttons.append([InlineKeyboardButton("🚫 BANNIR CE PIÉGEUR", callback_data=f"ban_prompt_staff_{admin_id}")])

    if is_owner and viewer_id != admin_id:
        buttons.append([
            InlineKeyboardButton("🛡️ MODIFIER SES DROITS", callback_data=f"perm_staff_{admin_id}"),
            InlineKeyboardButton("🏷️ RENOMMER", callback_data=f"owner_edit_alias_{admin_id}")
        ])
        buttons.append([InlineKeyboardButton("⬅️ RETOUR", callback_data="gerer_staff")])
    elif (is_admin or is_owner) and viewer_id != admin_id:
        buttons.append([InlineKeyboardButton("⬅️ RETOUR", callback_data="gerer_staff")])
    else:
        buttons.append([InlineKeyboardButton("⬅️ RETOUR", callback_data="menu_mon_profil")])

    return InlineKeyboardMarkup(buttons)


# ==============================================================================
# 8. FICHE UTILISATEUR / DEMANDEUR
# ==============================================================================

def format_user_profile_text(
    target_user_id: int,
    stats: dict,
    demande_data: dict,
    is_target_banned: bool,
    is_target_vip: bool,
    is_target_owner: bool,
    is_target_admin: bool,
    is_target_staff: bool,
    date_role_str: str,
    is_viewer_admin: bool
) -> str:
    """Formate la fiche détaillée d'un utilisateur demandeur."""
    raw_prenom = (
        (demande_data.get("user_first_name") if demande_data else None)
        or stats.get("prenom")
        or (demande_data.get("user_username") if demande_data else None)
        or f"Utilisateur {target_user_id}"
    )
    nom_affiche = html.escape(str(raw_prenom)).upper()

    pseudo_val = (demande_data.get("user_username") if demande_data else None) or stats.get("username")
    pseudo_str = f"@{html.escape(str(pseudo_val))}" if pseudo_val else "Aucun"

    dt_insc = (demande_data.get("date_inscription") if demande_data else None) or stats.get("date_inscription")
    date_insc = dt_insc.strftime("%d/%m/%Y") if dt_insc and hasattr(dt_insc, "strftime") else "Inconnue"

    dt_act = (demande_data.get("derniere_activite") if demande_data else None) or stats.get("derniere_activite")
    if dt_act and hasattr(dt_act, "strftime"):
        date_act = dt_act.strftime("%d-%m-%Y %H:%M")
    else:
        date_act = str(dt_act)[:16] if dt_act else "Inconnue"

    lines = [
        f"👤 <b>FICHE UTILISATEUR : {nom_affiche}</b>",
        "━━━━━━━━━━━━━━━━━━━━━━\n"
    ]

    if is_target_banned:
        lines.append("🚫 <b>STATUT : COMPTE BANNI</b>\n")

    lines.append(f"🏷️ <b>Pseudo :</b> {pseudo_str}")
    lines.append(f"🆔 <b>ID :</b> <code>{target_user_id}</code>\n")

    if is_viewer_admin and (is_target_admin or is_target_staff or is_target_owner):
        vip_suffix = " (VIP)" if is_target_vip else ""
        dt_badge = f" depuis le <u>{date_role_str}</u>" if date_role_str else ""
        if is_target_owner:
            lines.append(f"👑 <b>Propriétaire{vip_suffix}</b>\n")
        elif is_target_admin:
            lines.append(f"🧠 <b>Admin{vip_suffix}</b><i>{dt_badge}</i>\n")
        elif is_target_staff:
            lines.append(f"🎣 <b>Piégeur{vip_suffix}</b><i>{dt_badge}</i>\n")

    lines.append(f"📅 <b>Inscrit le :</b> <u>{html.escape(date_insc)}</u>")
    lines.append(f"⏱️ <b>Dernière activité :</b> <u>{html.escape(date_act)}</u>\n")

    if is_target_vip:
        vip_until = stats.get("vip_until")
        if vip_until and hasattr(vip_until, "timestamp"):
            nb_jours = max(1, int((vip_until.timestamp() - time.time()) // 86400))
            nb_mois = max(1, round(nb_jours / 30))
            duree_txt = f"{nb_mois} mois"
        else:
            duree_txt = "À vie"

        lines.append(f"⭐ <b>VIP :</b> {duree_txt}")
        lines.append(f"<i>depuis le <u>{html.escape(date_insc)}</u></i>\n")

    montant_investi = float(stats.get("montant_total_investi") or 0.0)

    lines.extend([
        "━━━━ INFORMATIONS ━━━━\n",
        f"🗳️ <b>Demandes totales : {stats.get('total_demandes', 0)}</b>\n",
        f"• 📨 En attente : <b>{stats.get('en_attente', 0)}</b>\n",
        f"• ⏳ En cours : <b>{stats.get('en_cours', 0)}</b>\n",
        f"• ✅ Terminées : <b>{stats.get('reussies', 0)}</b>\n",
        f"• ❌ Échouées : <b>{stats.get('abandonnees', 0)}</b>\n\n",
        f"💎 <b>Demandes payantes : {stats.get('total_prio', 0)}</b>\n",
        f"• 💰 Investi : <b>{montant_investi:.2f} €</b>"
    ])

    return "\n".join(lines)


def build_user_profile_keyboard(
    target_user_id: int,
    origin_demande_id: int,
    viewer_id: int,
    is_target_banned: bool,
    can_ban: bool,
    is_owner_target: bool
) -> InlineKeyboardMarkup:
    """Construit le clavier d'actions sur la fiche d'un client."""
    buttons = [
        [InlineKeyboardButton("📋 VOIR SES DEMANDES", callback_data=f"user_view_demandes_{target_user_id}_{origin_demande_id}")]
    ]

    if can_ban and viewer_id != target_user_id and not is_owner_target:
        if is_target_banned:
            buttons.append([InlineKeyboardButton("🟢 DÉBANNIR L'UTILISATEUR", callback_data=f"unban_user_{target_user_id}_{origin_demande_id}")])
        else:
            buttons.append([InlineKeyboardButton("🚫 BANNIR L'UTILISATEUR", callback_data=f"ban_prompt_user_{target_user_id}_{origin_demande_id}")])

    if origin_demande_id:
        buttons.append([InlineKeyboardButton("⬅️ RETOUR", callback_data=f"retour_texte_{origin_demande_id}")])
    else:
        buttons.append([InlineKeyboardButton("⬅️ RETOUR", callback_data="gerer_demandes")])

    return InlineKeyboardMarkup(buttons)


# ==============================================================================
# 9. FICHE DÉTAILLÉE D'ARCHIVE
# ==============================================================================

def format_archive_detail_text(archive: dict, admin_alias: str, db_manager) -> str:
    """Formate la fiche détaillée et figée d'une archive."""
    req_num = html.escape(str(archive.get("original_id") or archive["id"]))
    prenom = html.escape(str(archive.get("prenom") or "Non précisé"))
    nom = html.escape(str(archive.get("nom") or ""))
    age = html.escape(str(archive.get("age") or "Non précisé"))
    loc = html.escape(str(archive.get("localisation") or "Non précisée"))
    insta = f"@{html.escape(archive['instagram'].lstrip('@'))}" if archive.get("instagram") else "Aucun"
    snap = html.escape(str(archive.get("snapchat") or "Aucun"))
    details = html.escape(str(archive.get("details") or "Aucun détail complémentaire"))

    dt_arch = archive.get("date_archivage")
    date_arch_str = convert_utc_to_paris(dt_arch).strftime("%d/%m/%Y à %H:%M") if dt_arch else "Inconnue"

    statut_display = html.escape(str(db_manager.format_statut_display(
        archive.get("statut", ""),
        archive.get("is_difficile", False),
        archive.get("reussie_substatus")
    )))
    type_str = "💎 Prioritaire (Payante)" if archive.get("prioritaire") else "Standard (Gratuite)"

    return (
        f"📦 <b>Archive Dossier #{req_num}</b>\n\n"
        f"• <b>Cible :</b> {prenom} {nom} ({age} ans)\n"
        f"• <b>Localisation :</b> {loc}\n"
        f"• <b>Instagram :</b> {insta}\n"
        f"• <b>Snapchat :</b> {snap}\n"
        f"• <b>Type de demande :</b> {html.escape(type_str)}\n"
        f"• <b>Statut final :</b> <code>{statut_display}</code>\n"
        f"• <b>Référent en charge :</b> {html.escape(str(admin_alias))}\n"
        f"• <b>Archivé le :</b> {html.escape(date_arch_str)}\n\n"
        f"📝 <b>Détails / Notes :</b>\n« {details} »"
    )

def format_status_notification_text(
    prenom: str,
    request_number: int,
    old_status: str,
    new_status: str,
    admin_alias: str
) -> str:
    """Formate la notification directe de statut envoyée au demandeur."""
    prenom_esc = html.escape(str(prenom or ""))
    old_esc = html.escape(str(old_status or ""))
    new_esc = html.escape(str(new_status or ""))
    alias_esc = html.escape(str(admin_alias or ""))

    return (
        f"📢 <b>Notification de suivi</b>\n\n"
        f"Bonjour <b>{prenom_esc}</b>, le statut de votre demande <b>#{request_number}</b> a évolué :\n\n"
        f"Ancien statut : <s>{old_esc}</s>\n"
        f"Nouveau statut : <b>{new_esc}</b>\n\n"
        f"👨‍💼 <b>Opérateur en charge :</b> {alias_esc}\n\n"
        "Tapez /demandes pour afficher l'ensemble de vos demandes."
    )