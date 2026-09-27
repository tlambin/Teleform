"""Composants visuels, fiches détaillées et claviers pour les profils Staff et Utilisateurs."""

import html
import time
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from utils.validators import convert_utc_to_paris


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
        buttons.append([InlineKeyboardButton("⬅️ RETOUR", callback_data="parametres")])

    return InlineKeyboardMarkup(buttons)


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