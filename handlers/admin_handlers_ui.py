"""Composants visuels, gabarits textuels et claviers pour les fonctions de gouvernance administrative."""

import html
from typing import List, Dict, Any, Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


# ==================== MAINTENANCE & BOT SERVICE ====================

def format_maintenance_summary(storage_before: float, storage_after: float, demandes_count: int, archives_count: int) -> tuple[str, InlineKeyboardMarkup]:
    """Construit le rapport d'exécution de la maintenance système."""
    economie = max(0.0, storage_before - storage_after)
    message = (
        "✅ <b>Maintenance terminée avec succès</b>\n\n"
        "💾 <b>Stockage local :</b>\n"
        f"• Avant : {storage_before:.1f} Mo\n"
        f"• Après : {storage_after:.1f} Mo\n"
        f"• Gain : {economie:.1f} Mo\n\n"
        "📊 <b>Base de données :</b>\n"
        f"• Demandes actives : {demandes_count}\n"
        f"• Demandes archivées : {archives_count}\n\n"
        "🧹 Cache mémoire purgé et index optimisés."
    )
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ RETOUR", callback_data="gerer_bot")]])
    return message, keyboard


def get_bot_off_confirmation_content() -> tuple[str, InlineKeyboardMarkup]:
    """Invite de confirmation avant la suspension générale des demandes."""
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("⚠️ Confirmer la suspension", callback_data="confirm_bot_off"),
        InlineKeyboardButton("❌ Annuler", callback_data="cancel_bot_off"),
    ]])
    text = (
        "⚠️ <b>Suspension des nouvelles demandes</b>\n\n"
        "Les utilisateurs ne pourront plus créer de demandes jusqu'à la réactivation.\n"
        "Confirmez-vous cette action ?"
    )
    return text, keyboard


# ==================== SUPERVISION DOSSIERS PIÉGEUR ====================

def get_staff_no_dossiers_content(alias: str, staff_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Message et clavier quand un opérateur n'a aucun dossier actif."""
    alias_esc = html.escape(str(alias))
    msg = (
        f"📂 <b>Dossiers de {alias_esc}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "📭 Cet opérateur n'a aucune demande en cours de traitement pour le moment."
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Contacter le piégeur", callback_data=f"admin_contact_staff_{staff_id}")],
        [InlineKeyboardButton("⬅️ RETOUR", callback_data="gerer_staff")],
    ])
    return msg, kb


def format_staff_dossier_card(
    demande: dict,
    alias: str,
    page: int,
    total: int,
    staff_id: int,
    statut_fmt: str
) -> tuple[str, InlineKeyboardMarkup]:
    """Formate la fiche de supervision d'un dossier en cours et ses contrôles administratifs."""
    alias_esc = html.escape(str(alias))
    demande_id = demande["id"]
    nom_cible = f"{html.escape(str(demande.get('prenom') or ''))} {html.escape(str(demande.get('nom') or ''))}".strip() or "Non renseigné"
    prio_tag = f"💎 Prioritaire ({float(demande.get('montant') or 0.0):.2f} €)" if demande.get("prioritaire") else "📝 Standard"
    date_prise = str(demande.get("date_suivi") or demande.get("date_creation"))[:16]

    text = (
        f"📂 <b>Dossiers de {alias_esc} ({page + 1}/{total})</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• <b>Dossier :</b> #{demande_id}\n"
        f"• <b>Cible :</b> <b>{nom_cible}</b>\n"
        f"• <b>Formule :</b> {prio_tag}\n"
        f"• <b>Statut actuel :</b> <code>{html.escape(str(statut_fmt))}</code>\n"
        f"• <b>Prise en charge :</b> <i>{date_prise}</i>\n"
        f"• <b>Demandeur :</b> <code>{demande['user_id']}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<i>Actions administratives sur ce dossier :</i>"
    )

    buttons = [
        [InlineKeyboardButton("🔔 RELANCER LE PIÉGEUR", callback_data=f"admin_remind_staff_demande_{staff_id}_{demande_id}_{page}")],
        [
            InlineKeyboardButton("💬 CONTACTER LE PIÉGEUR", callback_data=f"admin_contact_staff_{staff_id}"),
            InlineKeyboardButton("👤 CONTACTER LE CLIENT", callback_data=f"contacter_{demande_id}"),
        ],
    ]

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ PRÉCÉDENTE", callback_data=f"staff_view_demandes_{staff_id}_{page - 1}"))
    if page < total - 1:
        nav_row.append(InlineKeyboardButton("SUIVANTE ➡️", callback_data=f"staff_view_demandes_{staff_id}_{page + 1}"))
    if nav_row:
        buttons.append(nav_row)

    buttons.append([InlineKeyboardButton("⬅️ RETOUR", callback_data="gerer_staff")])
    return text, InlineKeyboardMarkup(buttons)


def format_admin_reminder_message(admin_alias: str, req_num: int, prenom: str, demande_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Génère le message de relance formel envoyé à un opérateur."""
    alias_esc = html.escape(str(admin_alias))
    msg_staff = (
        f"🔔 <b>RAPPEL DE LA DIRECTION / ADMINISTRATION</b>\n\n"
        f"L'administrateur <b>{alias_esc}</b> vous relance concernant le dossier <b>#{req_num}</b> ({prenom}).\n\n"
        "👉 Merci de faire le point sur ce dossier dans vos suivis et de finaliser la démarche."
    )
    kb_staff = InlineKeyboardMarkup([
        [InlineKeyboardButton("📄 Ouvrir la fiche du dossier", callback_data=f"retour_texte_{demande_id}")],
        [InlineKeyboardButton("💌 Mes suivis", callback_data="demandes_suivies")],
    ])
    return msg_staff, kb_staff


# ==================== MATRICES DE PERMISSIONS ====================

def build_staff_permissions_menu_content(staff_id: int, alias: str, perms: dict) -> tuple[str, InlineKeyboardMarkup]:
    """Génère la grille interactive des autorisations attribuées à un opérateur."""
    reseau = perms.get("perm_reseaux", "all")
    typ = perms.get("perm_type", "all")
    ori = perms.get("perm_orientation", "all")
    allow_self = bool(perms.get("allow_self_prefs", True))
    is_trial = bool(perms.get("is_trial", False))

    b_res_all = "✅ Tous réseaux" if reseau == "all" else "Tous réseaux"
    b_res_insta = "✅ Insta seul" if reseau == "insta" else "Insta seul"
    b_res_snap = "✅ Snap seul" if reseau == "snap" else "Snap seul"

    b_typ_all = "✅ Tout type" if typ == "all" else "Tout type"
    b_typ_prio = "✅ 💎 Payantes" if typ == "prio_only" else "💎 Payantes"
    b_typ_std = "✅ 📝 Gratuites" if typ == "standard_only" else "📝 Gratuites"

    b_ori_all = "✅ 🔄 Tous / Bi" if ori in ("all", "bi") else "🔄 Tous / Bi"
    b_ori_h = "✅ Hétéro" if ori == "hetero" else "Hétéro"
    b_ori_g = "✅ Gay" if ori == "gay" else "Gay"

    trial_btn_label = "🧪 À l'essai : ✅ OUI" if is_trial else "🧪 À l'essai : ❌ NON"
    self_prefs_label = "🔒 Bloquer ses réglages cibles" if allow_self else "🔓 Débloquer ses réglages cibles"

    keyboard = [
        [
            InlineKeyboardButton(b_res_all, callback_data=f"set_permstaff_{staff_id}_reseaux_all"),
            InlineKeyboardButton(b_res_insta, callback_data=f"set_permstaff_{staff_id}_reseaux_insta"),
            InlineKeyboardButton(b_res_snap, callback_data=f"set_permstaff_{staff_id}_reseaux_snap"),
        ],
        [
            InlineKeyboardButton(b_typ_all, callback_data=f"set_permstaff_{staff_id}_type_all"),
            InlineKeyboardButton(b_typ_prio, callback_data=f"set_permstaff_{staff_id}_type_prio_only"),
            InlineKeyboardButton(b_typ_std, callback_data=f"set_permstaff_{staff_id}_type_standard_only"),
        ],
        [
            InlineKeyboardButton(b_ori_h, callback_data=f"set_permstaff_{staff_id}_orientation_hetero"),
            InlineKeyboardButton(b_ori_g, callback_data=f"set_permstaff_{staff_id}_orientation_gay"),
            InlineKeyboardButton(b_ori_all, callback_data=f"set_permstaff_{staff_id}_orientation_all"),
        ],
        [InlineKeyboardButton(self_prefs_label, callback_data=f"set_permstaff_{staff_id}_selfprefs_toggle")],
        [InlineKeyboardButton(trial_btn_label, callback_data=f"set_permstaff_{staff_id}_trial_toggle")],
        [InlineKeyboardButton("⬅️ RETOUR", callback_data="gerer_staff")],
    ]
    text = (
        f"🛡️ <b>Permissions Opérateur : {html.escape(str(alias))}</b>\n"
        f"🆔 ID : <code>{staff_id}</code>\n\n"
        "Ajustez les dossiers auxquels ce membre a accès, verrouillez ses réglages cibles ou modifiez son <b>mode à l'essai</b> :"
    )
    return text, InlineKeyboardMarkup(keyboard)


def build_admin_permissions_menu_content(
    admin_id: int,
    alias: str,
    privs: dict,
    is_primary_owner: bool
) -> tuple[str, InlineKeyboardMarkup]:
    """Génère la grille interactive des privilèges attribués à un administrateur."""
    st_staff = "✅ OUI" if privs.get("can_manage_staff") else "❌ NON"
    st_vips = "✅ OUI" if privs.get("can_manage_vips") else "❌ NON"
    st_stats = "✅ OUI" if privs.get("can_view_stats") else "❌ NON"
    st_delais = "✅ OUI" if privs.get("can_manage_delais") else "❌ NON"
    st_archives = "✅ OUI" if privs.get("can_view_archives") else "❌ NON"
    st_monitor = "✅ OUI" if privs.get("can_monitor_staff") else "❌ NON"
    st_ban = "✅ OUI" if privs.get("can_ban_users") else "❌ NON"
    st_edit_others = "✅ OUI" if privs.get("can_edit_others_demandes") else "❌ NON"
    st_vip_status = "✅ OUI" if privs.get("is_vip") else "❌ NON"
    st_owner = "👑 CO-GÉRANT" if privs.get("is_owner") else "🛡️ MANAGER"

    keyboard = [
        [
            InlineKeyboardButton(f"Gérer Staff : {st_staff}", callback_data=f"set_permadmin_{admin_id}_can_manage_staff"),
            InlineKeyboardButton(f"Gérer VIPs : {st_vips}", callback_data=f"set_permadmin_{admin_id}_can_manage_vips"),
        ],
        [
            InlineKeyboardButton(f"Voir Stats : {st_stats}", callback_data=f"set_permadmin_{admin_id}_can_view_stats"),
            InlineKeyboardButton(f"Régler Délais : {st_delais}", callback_data=f"set_permadmin_{admin_id}_can_manage_delais"),
        ],
        [
            InlineKeyboardButton(f"Archives Générales : {st_archives}", callback_data=f"set_permadmin_{admin_id}_can_view_archives"),
            InlineKeyboardButton(f"Surveillance Staff : {st_monitor}", callback_data=f"set_permadmin_{admin_id}_can_monitor_staff"),
        ],
        [
            InlineKeyboardButton(f"Gérer Dossiers Tiers : {st_edit_others}", callback_data=f"set_permadmin_{admin_id}_can_edit_others_demandes"),
            InlineKeyboardButton(f"🚫 Bannir Membres : {st_ban}", callback_data=f"set_permadmin_{admin_id}_can_ban_users"),
        ],
        [InlineKeyboardButton(f"⭐ Accès VIP : {st_vip_status}", callback_data=f"set_permadmin_{admin_id}_is_vip")],
    ]

    if not is_primary_owner:
        keyboard.append([InlineKeyboardButton(f"Rôle Suprême : {st_owner}", callback_data=f"set_permadmin_{admin_id}_is_owner")])

    keyboard.append([InlineKeyboardButton("⬅️ RETOUR", callback_data="gerer_admins")])
    text = (
        f"⚙️ <b>Droits Administrateur : {html.escape(str(alias))}</b>\n"
        f"🆔 ID : <code>{admin_id}</code>\n\n"
        + ("⚠️ <i>Ceci est le Propriétaire principal (Intouchable).</i>\n\n" if is_primary_owner else "")
        + "Activez ou désactivez les responsabilités et privilèges de ce compte :"
    )
    return text, InlineKeyboardMarkup(keyboard)


# ==================== RECRUTEMENT / RÉVOCATION MANAGERS ====================

def get_admin_add_prompt_content() -> tuple[str, InlineKeyboardMarkup]:
    """Invite de saisie pour nommer un administrateur."""
    text = "🛡️ <b>Nomination d'un Administrateur (Manager)</b>\n\nEnvoyez l'<b>ID Telegram numérique</b> ou le nom d'utilisateur :"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="cancel_admin_add")]])
    return text, kb


def build_admin_add_success_content(alias: str, target_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Confirmation de nomination d'un nouvel administrateur."""
    alias_esc = html.escape(str(alias))
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚙️ Régler ses privilèges", callback_data=f"perm_admin_{target_id}")],
        [InlineKeyboardButton("⬅️ RETOUR", callback_data="gerer_admins")],
    ])
    text = f"✅ <b>Manager nommé :</b> <code>{alias_esc}</code> ({target_id})"
    return text, kb


def build_admin_remove_list_content(admins: List[Dict[str, Any]]) -> tuple[str, InlineKeyboardMarkup]:
    """Affiche la liste numérotée pour révoquer un administrateur."""
    if not admins:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ RETOUR", callback_data="gerer_admins")]])
        return "📭 Aucun administrateur révocable.", kb

    lines = ["🛡️ <b>Révocation d'un Administrateur</b>\n"]
    for idx, adm in enumerate(admins, 1):
        badge = "👑 [Co-Owner]" if adm.get("is_owner") else "🛡️ [Manager]"
        alias_esc = html.escape(str(adm.get("alias") or adm["user_id"]))
        lines.append(f"{idx}. {badge} <b>{alias_esc}</b> (<code>{adm['user_id']}</code>)")

    lines.append("\nEnvoyez le <b>numéro</b> de l'administrateur à révoquer :")
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="cancel_admin_remove")]])
    return "\n".join(lines), kb


def get_admin_remove_confirmation_content(alias: str) -> tuple[str, InlineKeyboardMarkup]:
    """Demande confirmation avant la suppression des privilèges d'un manager."""
    alias_esc = html.escape(str(alias))
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("⚠️ Confirmer", callback_data="confirm_admin_remove"),
        InlineKeyboardButton("❌ Annuler", callback_data="cancel_admin_remove"),
    ]])
    text = f"⚠️ Retirer les droits administrateur à <b>{alias_esc}</b> ?"
    return text, kb