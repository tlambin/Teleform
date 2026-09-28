"""ui/admin/users.py
Gabarits visuels, textes et claviers pour la gestion des utilisateurs :
Staff, Administrateurs, Membres, VIPs et matrices de permissions.
"""

from datetime import datetime
import html
from typing import Any, Dict, List, Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from utils.validators import convert_utc_to_paris


def _format_datetime_fr(val) -> str:
    if not val:
        return "Inconnue"
    if hasattr(val, "strftime"):
        return convert_utc_to_paris(val).strftime("%d/%m/%Y à %H:%M")
    try:
        dt = datetime.strptime(str(val)[:19], "%Y-%m-%d %H:%M:%S")
        return convert_utc_to_paris(dt).strftime("%d/%m/%Y à %H:%M")
    except Exception:
        return str(val)[:16]


# ==================== STAFF (OPÉRATEURS) ====================

def format_staff_list_text(staff_members: List[Dict[str, Any]]) -> str:
    if not staff_members:
        return "📭 <b>Aucun opérateur dans l'équipe Staff pour le moment.</b>"

    lines = [f"👥 <b>Équipe Staff (Opérateurs)</b> ({len(staff_members)})\n"]
    for st in staff_members:
        raw_pseudo = f"@{st['username']}" if st.get("username") else (st.get("first_name") or "")
        pseudo_esc = html.escape(str(raw_pseudo))
        alias_esc = html.escape(str(st.get("alias") or f"Staff_{st['user_id']}"))
        date_str = _format_datetime_fr(st.get("date_added"))
        par_qui = html.escape(str(st.get("nom_ajouteur") or "Direction"))
        status_badge = "⏸️ (En pause)" if st.get("is_paused") else "🟢 (En service)"
        trial_badge = " 🧪 <b>[À l'essai]</b>" if st.get("is_trial") else ""

        lines.append(
            f"• <b>{alias_esc}</b> {status_badge}{trial_badge} ({pseudo_esc})\n"
            f"  ID : <code>{st['user_id']}</code> | Recruté le {date_str} par {par_qui}\n"
        )
    return "\n".join(lines)


def get_staff_add_prompt_content(current_count: int) -> tuple[str, InlineKeyboardMarkup]:
    text = (
        "👤 <b>Recrutement d'un Opérateur (Staff)</b>\n\n"
        f"Équipe actuelle : <b>{current_count}</b> opérateur(s)\n\n"
        "Envoyez l'<b>ID Telegram</b> ou le <b>@username</b> du compte à recruter :\n\n"
        "<i>(L'utilisateur doit obligatoirement avoir démarré le bot au préalable avec /start)</i>"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="cancel_staff_add")]])
    return text, kb


def build_recruit_config_content(cfg: dict) -> tuple[str, InlineKeyboardMarkup]:
    target_id = cfg.get("target_id")
    alias_esc = html.escape(str(cfg.get("alias") or ""))
    nom_esc = html.escape(str(cfg.get("first_name") or ""))

    res = cfg.get("reseaux", "all")
    typ = cfg.get("type", "all")
    ori = cfg.get("orientation", "all")
    is_trial = bool(cfg.get("is_trial", True))

    b_res_all = "✅ Tous réseaux" if res == "all" else "Tous réseaux"
    b_res_insta = "✅ Insta" if res == "insta" else "Insta"
    b_res_snap = "✅ Snap" if res == "snap" else "Snap"

    b_typ_all = "✅ Tout type" if typ == "all" else "Tout type"
    b_typ_prio = "✅ 💎 Payantes" if typ == "prio_only" else "💎 Payantes"
    b_typ_std = "✅ 📝 Gratuites" if typ == "standard_only" else "📝 Gratuites"

    b_ori_all = "✅ 🔄 Tous / Bi" if ori in ("all", "bi") else "🔄 Tous / Bi"
    b_ori_h = "✅ Hétéro" if ori == "hetero" else "Hétéro"
    b_ori_g = "✅ Gay" if ori == "gay" else "Gay"

    trial_label = "🧪 À l'essai : ✅ OUI" if is_trial else "🧪 À l'essai : ❌ NON"

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(b_res_all, callback_data="cfgadd_res_all"),
            InlineKeyboardButton(b_res_insta, callback_data="cfgadd_res_insta"),
            InlineKeyboardButton(b_res_snap, callback_data="cfgadd_res_snap"),
        ],
        [
            InlineKeyboardButton(b_typ_all, callback_data="cfgadd_typ_all"),
            InlineKeyboardButton(b_typ_prio, callback_data="cfgadd_typ_prio_only"),
            InlineKeyboardButton(b_typ_std, callback_data="cfgadd_typ_standard_only"),
        ],
        [
            InlineKeyboardButton(b_ori_h, callback_data="cfgadd_ori_hetero"),
            InlineKeyboardButton(b_ori_g, callback_data="cfgadd_ori_gay"),
            InlineKeyboardButton(b_ori_all, callback_data="cfgadd_ori_all"),
        ],
        [InlineKeyboardButton(trial_label, callback_data="cfgadd_trial_toggle")],
        [InlineKeyboardButton("🚀 Valider et recruter", callback_data="cfgadd_confirm_save")],
        [InlineKeyboardButton("❌ Annuler", callback_data="cancel_staff_add")],
    ])

    text = (
        f"⚙️ <b>Configuration initiale de l'opérateur</b>\n\n"
        f"👤 <b>Cible :</b> {nom_esc} (ID : <code>{target_id}</code>)\n"
        f"🏷️ <b>Alias provisoire :</b> <code>{alias_esc}</code>\n\n"
        "Ajustez ses autorisations et son mode à l'essai avant d'enregistrer le recrutement :"
    )
    return text, keyboard


def build_recruit_welcome_message(alias: str, is_trial: bool) -> tuple[str, InlineKeyboardMarkup]:
    alias_esc = html.escape(alias)
    trial_notice = (
        "🧪 <b>Période probatoire (À l'essai) :</b>\n"
        "Vous devez mener à bien <b>une première demande test</b> attribuée au hasard pour débloquer l'accès complet à la plateforme.\n\n"
        if is_trial else
        "🟢 <b>Accès complet :</b>\n"
        "Vous avez accès dès maintenant à l'ensemble des demandes disponibles correspondant à vos autorisations.\n\n"
    )
    welcome_msg = (
        "🎉 <b>Bienvenue dans l'équipe opérationnelle (Staff) !</b>\n\n"
        f"🏷️ <b>Votre alias provisoire :</b> <code>{alias_esc}</code>\n\n"
        f"{trial_notice}"
        "⚠️ <b>Pseudonyme officiel :</b> Vous pouvez définir votre alias dès maintenant.\n"
        "<i>Attention : vous ne disposez que d'une seule modification autorisée.</i>\n\n"
        "Cliquez ci-dessous pour démarrer :"
    )
    welcome_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏷️ DÉFINIR MON ALIAS", callback_data="modifier_alias")],
        [InlineKeyboardButton("🚀 Menu principal", callback_data="start_menu")],
    ])
    return welcome_msg, welcome_kb


def build_recruit_admin_summary(cfg: dict) -> tuple[str, InlineKeyboardMarkup]:
    target_id = cfg["target_id"]
    alias_esc = html.escape(cfg["alias"])
    res_label = {"all": "Tous", "insta": "Instagram", "snap": "Snapchat"}.get(cfg["reseaux"], cfg["reseaux"])
    typ_label = {"all": "Tous", "prio_only": "Payantes", "standard_only": "Gratuites"}.get(cfg["type"], cfg["type"])
    ori_label = {"all": "Tous / Bi", "bi": "Tous / Bi", "hetero": "Hétéro", "gay": "Gay"}.get(cfg["orientation"], cfg["orientation"])
    trial_text = "🧪 <b>À l'essai</b> (Demande aléatoire imposée)" if cfg["is_trial"] else "🟢 <b>Confirmé</b> (Accès complet)"

    msg = (
        f"✅ <b>Opérateur recruté et configuré avec succès !</b>\n\n"
        f"👤 <b>Cible :</b> {html.escape(cfg['first_name'])} (ID : <code>{target_id}</code>)\n"
        f"🏷️ <b>Alias :</b> <code>{alias_esc}</code>\n"
        f"🌐 <b>Réseaux :</b> {res_label}\n"
        f"🎯 <b>Type :</b> {typ_label}\n"
        f"🧭 <b>Orientation :</b> {ori_label}\n"
        f"🧪 <b>Statut :</b> {trial_text}"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Équipe Staff", callback_data="gerer_staff")],
        [InlineKeyboardButton("🔙 Menu principal", callback_data="start_menu")],
    ])
    return msg, kb


def build_staff_remove_list_content(staff_members: List[Dict[str, Any]]) -> tuple[str, InlineKeyboardMarkup]:
    if not staff_members:
        text = "👥 <b>Révocation d'un Opérateur</b>\n\nAucun opérateur révocable n'est configuré actuellement."
        return text, InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Retour", callback_data="gerer_staff")]])

    lines = ["👥 <b>Révocation d'un Opérateur (Staff)</b>\n", f"Opérateurs enregistrés : <b>{len(staff_members)}</b>\n"]
    for idx, st in enumerate(staff_members, 1):
        raw_pseudo = f"@{st['username']}" if st.get("username") else (st.get("first_name") or "")
        pseudo_esc = html.escape(str(raw_pseudo))
        alias_esc = html.escape(str(st.get("alias") or f"Staff_{st['user_id']}"))
        date_str = str(st.get("date_added", ""))[:10]
        lines.append(f"{idx}. <b>{alias_esc}</b> ({pseudo_esc}) — ID : <code>{st['user_id']}</code> [{date_str}]")

    lines.append("\nEnvoyez le <b>numéro</b> de l'opérateur à révoquer :")
    return "\n".join(lines), InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="cancel_staff_remove")]])


def build_staff_remove_confirmation_content(selected: dict) -> tuple[str, InlineKeyboardMarkup]:
    raw_pseudo = f"@{selected['username']}" if selected.get("username") else (selected.get("first_name") or "")
    pseudo_esc = html.escape(str(raw_pseudo))
    alias_esc = html.escape(str(selected.get("alias") or f"Staff_{selected['user_id']}"))
    text = (
        f"⚠️ <b>Confirmation de révocation</b>\n\n"
        f"Êtes-vous certain de vouloir retirer les accès opérationnels à :\n"
        f"• <b>Alias :</b> {alias_esc}\n"
        f"• <b>Profil :</b> {pseudo_esc}\n"
        f"• <b>ID :</b> <code>{selected['user_id']}</code> ?"
    )
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("⚠️ Confirmer la révocation", callback_data="confirm_staff_remove"),
        InlineKeyboardButton("❌ Annuler", callback_data="cancel_staff_remove"),
    ]])
    return text, kb


def get_staff_removed_success_content(alias: str, target_id: int) -> tuple[str, InlineKeyboardMarkup]:
    alias_esc = html.escape(str(alias or f"Staff_{target_id}"))
    text = f"✅ <b>Droits staff retirés avec succès pour {alias_esc}.</b>"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Équipe Staff", callback_data="gerer_staff")],
        [InlineKeyboardButton("🔙 Menu principal", callback_data="start_menu")],
    ])
    return text, kb


# ==================== SUPERVISION & DOSSIERS STAFF ====================

def get_staff_no_dossiers_content(alias: str, staff_id: int) -> tuple[str, InlineKeyboardMarkup]:
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
    demande: dict, alias: str, page: int, total: int, staff_id: int, statut_fmt: str
) -> tuple[str, InlineKeyboardMarkup]:
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
    admin_id: int, alias: str, privs: dict, is_primary_owner: bool
) -> tuple[str, InlineKeyboardMarkup]:
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


# ==================== NOMINATION / RÉVOCATION MANAGERS ====================

def get_admin_add_prompt_content() -> tuple[str, InlineKeyboardMarkup]:
    text = "🛡️ <b>Nomination d'un Administrateur (Manager)</b>\n\nEnvoyez l'<b>ID Telegram numérique</b> ou le nom d'utilisateur :"
    return text, InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="cancel_admin_add")]])


def build_admin_add_success_content(alias: str, target_id: int) -> tuple[str, InlineKeyboardMarkup]:
    alias_esc = html.escape(str(alias))
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚙️ Régler ses privilèges", callback_data=f"perm_admin_{target_id}")],
        [InlineKeyboardButton("⬅️ RETOUR", callback_data="gerer_admins")],
    ])
    return f"✅ <b>Manager nommé :</b> <code>{alias_esc}</code> ({target_id})", kb


def build_admin_remove_list_content(admins: List[Dict[str, Any]]) -> tuple[str, InlineKeyboardMarkup]:
    if not admins:
        return "📭 Aucun administrateur révocable.", InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ RETOUR", callback_data="gerer_admins")]])

    lines = ["🛡️ <b>Révocation d'un Administrateur</b>\n"]
    for idx, adm in enumerate(admins, 1):
        badge = "👑 [Co-Owner]" if adm.get("is_owner") else "🛡️ [Manager]"
        alias_esc = html.escape(str(adm.get("alias") or adm["user_id"]))
        lines.append(f"{idx}. {badge} <b>{alias_esc}</b> (<code>{adm['user_id']}</code>)")

    lines.append("\nEnvoyez le <b>numéro</b> de l'administrateur à révoquer :")
    return "\n".join(lines), InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="cancel_admin_remove")]])


def get_admin_remove_confirmation_content(alias: str) -> tuple[str, InlineKeyboardMarkup]:
    alias_esc = html.escape(str(alias))
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("⚠️ Confirmer", callback_data="confirm_admin_remove"),
        InlineKeyboardButton("❌ Annuler", callback_data="cancel_admin_remove"),
    ]])
    return f"⚠️ Retirer les droits administrateur à <b>{alias_esc}</b> ?", kb


# ==================== MEMBRES & BANNISSEMENTS ====================

def get_search_prompt_content() -> tuple[str, InlineKeyboardMarkup]:
    text = (
        "🔍 <b>RECHERCHER UN MEMBRE</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "Envoyez ci-dessous son <b>ID Telegram numérique</b> ou son <b>@pseudo</b> :\n\n"
        "<i>Exemples : <code>123456789</code> ou <code>@nom_utilisateur</code></i>"
    )
    return text, InlineKeyboardMarkup([[InlineKeyboardButton("❌ ANNULER", callback_data="menu_membres")]])


def get_member_not_found_content() -> tuple[str, InlineKeyboardMarkup]:
    text = "❌ <b>Membre introuvable.</b>\nL'utilisateur doit avoir démarré le bot au moins une fois."
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 RÉESSAYER", callback_data="search_member_prompt")],
        [InlineKeyboardButton("⬅️ RETOUR", callback_data="menu_membres")],
    ])
    return text, kb


def build_banned_list_content(bannis: List[Dict[str, Any]], total: int, page: int, limit: int) -> tuple[str, InlineKeyboardMarkup]:
    lines = [f"🚫 <b>LISTE DES COMPTES BANNIS ({total})</b>", "━━━━━━━━━━━━━━━━━━━━━━\n"]
    keyboard = []

    if not bannis:
        lines.append("<i>Aucun compte banni sur la plateforme.</i>")
    else:
        for b in bannis:
            u_id = b["user_id"]
            pseudo = f"@{b['username']}" if b.get("username") else "Sans pseudo"
            nom = html.escape(str(b.get("first_name") or pseudo))
            par_qui = html.escape(str(b.get("admin_alias") or f"Admin_{b.get('banned_by')}"))
            dt_str = _format_datetime_fr(b.get("date_ban"))
            raison = html.escape(str(b.get("reason") or "Non spécifiée"))

            lines.append(f"• <b>{nom}</b> (<code>{u_id}</code>)\n  Banni le {dt_str} par {par_qui}\n  <i>Motif : {raison}</i>\n")
            keyboard.append([InlineKeyboardButton(f"🟢 DÉBANNIR {nom.upper()[:15]}", callback_data=f"unban_from_list_{u_id}")])

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ PRÉCÉDENT", callback_data=f"liste_bannis_{page - 1}"))
    if (page * limit + limit) < total:
        nav_row.append(InlineKeyboardButton("SUIVANT ➡️", callback_data=f"liste_bannis_{page + 1}"))
    if nav_row:
        keyboard.append(nav_row)

    keyboard.append([InlineKeyboardButton("⬅️ RETOUR", callback_data="menu_membres")])
    return "\n".join(lines), InlineKeyboardMarkup(keyboard)


def get_ban_reason_prompt_content(target_id: int, is_staff: bool, origin_demande_id: int = 0) -> tuple[str, InlineKeyboardMarkup]:
    role_str = "Piégeur (Staff)" if is_staff else "Utilisateur (Client)"
    text = (
        f"🚫 <b>Bannissement d'un compte : {role_str}</b>\n"
        f"🆔 ID Cible : <code>{target_id}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Veuillez envoyer au clavier la <b>raison du bannissement</b> :\n"
        "<i>(Tapez 'Passer' ou 'Non' pour ne spécifier aucun motif particulier).</i>"
    )
    back_cb = f"staff_view_demandes_{target_id}" if is_staff else (f"profil_demande_{origin_demande_id}" if origin_demande_id else "menu_membres")
    return text, InlineKeyboardMarkup([[InlineKeyboardButton("❌ ANNULER", callback_data=back_cb)]])


def get_ban_notification_message(reason: str) -> str:
    return (
        "🚫 <b>VOTRE COMPTE A ÉTÉ BANNI</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "L'accès aux services de la plateforme vous a été révoqué par la direction.\n"
        f"• <b>Motif :</b> <i>{html.escape(reason)}</i>\n\n"
        "Si vous pensez qu'il s'agit d'une erreur, vous pouvez contacter le support."
    )


def build_ban_success_content(target_id: int, reason: str, is_staff: bool) -> tuple[str, InlineKeyboardMarkup]:
    role_str = "Piégeur" if is_staff else "Utilisateur"
    text = (
        f"✅ <b>{role_str} banni avec succès !</b>\n\n"
        f"• <b>ID Cible :</b> <code>{target_id}</code>\n"
        f"• <b>Motif enregistré :</b> <i>{html.escape(reason)}</i>"
    )
    return text, InlineKeyboardMarkup([[InlineKeyboardButton("👥 GESTION DES MEMBRES", callback_data="menu_membres")]])


# ==================== VIPs ====================

def get_vip_add_prompt_content() -> tuple[str, InlineKeyboardMarkup]:
    text = "⭐ <b>Promouvoir un Membre VIP</b>\n\nEnvoyez l'<b>ID numérique</b> ou le <b>@username</b> du compte :"
    return text, InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="cancel_vip_action")]])


def build_vip_duration_choice_content(u_data: dict) -> tuple[str, InlineKeyboardMarkup]:
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ 1 Mois (30 jours)", callback_data="vip_dur_30")],
        [InlineKeyboardButton("⭐ 3 Mois (90 jours)", callback_data="vip_dur_90")],
        [InlineKeyboardButton("👑 À Vie (Illimité)", callback_data="vip_dur_lifetime")],
        [InlineKeyboardButton("❌ Annuler", callback_data="cancel_vip_action")],
    ])
    nom = html.escape(str(u_data.get("first_name") or u_data.get("username") or u_data["user_id"]))
    return f"👤 Cible : <b>{nom}</b>\n\nChoisissez la durée ou tapez le nombre de jours :", kb


def get_vip_granted_notification(duration_days: Optional[int]) -> str:
    type_str = f"pendant {duration_days} jours" if duration_days else "à vie"
    return f"🎉 <b>Félicitations ! Votre accès VIP ({type_str}) est activé !</b>"


def build_vip_grant_success_content(target_name: str, duration_days: Optional[int]) -> tuple[str, InlineKeyboardMarkup]:
    dur_txt = f"{duration_days} jours" if duration_days else "À vie"
    return f"✅ Statut VIP activé pour {html.escape(str(target_name))} ({dur_txt}) !", InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ RETOUR", callback_data="gerer_vips")]])


def build_vip_remove_list_content(vips: List[Dict[str, Any]]) -> tuple[str, InlineKeyboardMarkup]:
    if not vips:
        return "📭 Aucun membre VIP actif.", InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ RETOUR", callback_data="gerer_vips")]])

    lines = ["⭐ <b>Révocation Membre VIP</b>\n"]
    for idx, v in enumerate(vips, 1):
        lines.append(f"{idx}. <b>{html.escape(str(v.get('first_name') or 'Utilisateur'))}</b> (<code>{v['user_id']}</code>)")

    lines.append("\nEnvoyez le <b>numéro</b> de la personne à révoquer :")
    return "\n".join(lines), InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="cancel_vip_action")]])


def build_vip_revoked_success_content(target_name: str) -> tuple[str, InlineKeyboardMarkup]:
    return f"✅ <b>Statut VIP révoqué pour {html.escape(str(target_name))}.</b>", InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ RETOUR", callback_data="gerer_vips")]])