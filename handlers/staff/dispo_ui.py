"""Composants visuels, formatage des fiches et claviers pour les demandes disponibles."""

from datetime import datetime
import html
import re
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from utils.validators import convert_utc_to_paris


def format_date_fr(val) -> str:
    """Convertit une date ou un timestamp au format strict JJ/MM/AAAA."""
    if not val:
        return "?"
    if hasattr(val, "strftime"):
        return convert_utc_to_paris(val).strftime("%d/%m/%Y")
    try:
        dt = datetime.strptime(str(val)[:19], "%Y-%m-%d %H:%M:%S")
        return convert_utc_to_paris(dt).strftime("%d/%m/%Y")
    except Exception:
        pass
    try:
        parts = str(val)[:10].split("-")
        if len(parts) == 3:
            return f"{parts[2]}/{parts[1]}/{parts[0]}"
    except Exception:
        pass
    return str(val)[:10]


def format_datetime_fr(val) -> str:
    """Convertit une date ou un timestamp au format strict JJ/MM/AAAA HH:MM."""
    if not val:
        return "?"
    if hasattr(val, "strftime"):
        return convert_utc_to_paris(val).strftime("%d/%m/%Y %H:%M")
    try:
        dt = datetime.strptime(str(val)[:19], "%Y-%m-%d %H:%M:%S")
        return convert_utc_to_paris(dt).strftime("%d/%m/%Y %H:%M")
    except Exception:
        pass
    try:
        parts = str(val)[:10].split("-")
        time_part = str(val)[11:16] if len(str(val)) >= 16 else "00:00"
        if len(parts) == 3:
            return f"{parts[2]}/{parts[1]}/{parts[0]} {time_part}"
    except Exception:
        pass
    return str(val)[:16]


def clean_reason_text(raw_reason: str) -> str:
    """Nettoie les balises HTML, puces et préfixes de nom déjà enregistrés dans le motif."""
    if not raw_reason:
        return "Non précisée"
    clean = str(raw_reason).strip()
    clean = re.sub(r"<[^>]+>", "", clean)
    clean = re.sub(r"^[•\-\*]\s*", "", clean)
    if ":" in clean:
        parts = clean.split(":", 1)
        if len(parts[0].strip().split()) <= 3:
            clean = parts[1].strip()
    clean = clean.strip(" «»\"'")
    return html.escape(clean) if clean else "Non précisée"


def format_trial_demande_card(demande: dict, db_manager) -> str:
    """Formate la fiche d'une demande pour un membre à l'essai avec liens sociaux cliquables."""
    label_map = {"hetero": "Hétéro", "gay": "Gay", "bi": "Bi"}
    ori_label = label_map.get(demande.get("orientation", "hetero"), "Hétéro")

    prenom_esc = html.escape(str(demande.get("prenom") or ""))
    nom_esc = html.escape(str(demande.get("nom") or ""))
    nom_complet = f"{prenom_esc} {nom_esc}".strip() or "Identité non précisée"
    age_str = f"  •  {demande['age']} ans" if demande.get("age") is not None else ""
    loc_esc = html.escape(str(demande.get("localisation") or "Lieu non précisé"))
    real_id = demande["id"]

    is_prio = bool(demande.get("prioritaire"))
    titre = f"💎  <b>Demande Prioritaire #{real_id}</b>" if is_prio else f"📝  <b>Demande Standard #{real_id}</b>"

    lines = [
        titre,
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"👤  <b>{nom_complet}{age_str}</b>",
        f"📍  {ori_label} de {loc_esc}"
    ]

    if demande.get("details"):
        det = html.escape(str(demande["details"]).strip())
        lines.append(f"💬  <i>{det}</i>")

    if is_prio:
        montant_val = float(demande.get("montant") or 0.0)
        lines.append(f"💰  <b>{montant_val:.2f} €</b>")

    reseaux = []
    if demande.get("instagram"):
        raw_ig = str(demande["instagram"]).strip().lstrip("@")
        ig_esc = html.escape(raw_ig)
        reseaux.append(f'• <b>Instagram :</b> <a href="https://instagram.com/{ig_esc}">@{ig_esc}</a>')
    if demande.get("snapchat"):
        raw_snap = str(demande["snapchat"]).strip().lstrip("@")
        snap_esc = html.escape(raw_snap)
        reseaux.append(f'• <b>Snapchat :</b> <a href="https://snapchat.com/add/{snap_esc}">{snap_esc}</a>')

    if reseaux:
        lines.append("\n🌐  <b>SES RÉSEAUX</b>")
        lines.extend(reseaux)

    statut_label = db_manager.format_statut_display(
        demande.get("statut", "📥 Reçue"),
        demande.get("is_difficile", False),
        demande.get("reussie_substatus")
    )

    lines.append("\n───────  <b>STATUT</b>  ──────")
    lines.append(f" • <b>{html.escape(statut_label)}</b> • ")
    dt_mod = demande.get("date_modification")
    if dt_mod:
        lines.append(f" <i>{format_datetime_fr(dt_mod)}</i>")

    lines.append("\n───────  <b>INFOS</b>  ───────")
    dt_crea = demande.get("date_creation")
    lines.append(f"<b>Déposé le :</b>  {format_datetime_fr(dt_crea)}")

    ancien_alias = demande.get("ancien_admin_alias")
    raw_reason = demande.get("raison_abandon")
    if ancien_alias or raw_reason:
        alias_str = html.escape(str(ancien_alias or "Opérateur"))
        reason_str = clean_reason_text(raw_reason)
        dt_abandon = demande.get("date_modification")
        date_abandon_str = format_datetime_fr(dt_abandon) if dt_abandon else "Date inconnue"

        lines.append("\n─────  <b>HISTORIQUE</b>  ─────")
        lines.append("❌ Abandonné")
        lines.append(f"{alias_str} le {date_abandon_str}")
        lines.append(f"<b>Raison :</b> {reason_str}")

    return "\n".join(lines)


def format_demande_card(demande: dict, page: int, total: int, active_filters: dict, db_manager) -> str:
    """Formate la fiche d'une demande disponible pour le staff avec liens sociaux cliquables."""
    real_id = demande["id"]
    is_prio = bool(demande.get("prioritaire"))
    titre = f"💎  <b>Demande Prioritaire #{real_id} ({page + 1}/{total})</b>" if is_prio else f"📝  <b>Demande Standard #{real_id} ({page + 1}/{total})</b>"

    prenom_esc = html.escape(str(demande.get("prenom") or ""))
    nom_esc = html.escape(str(demande.get("nom") or ""))
    nom_complet = f"{prenom_esc} {nom_esc}".strip() or "Identité non précisée"
    age_str = f"  •  {demande['age']} ans" if demande.get("age") is not None else ""

    ori_map = {"hetero": "Hétéro", "gay": "Gay", "bi": "Bi"}
    ori_label = ori_map.get(str(demande.get("orientation") or "").lower(), "Non précisée")
    loc = html.escape(str(demande.get("localisation") or "Lieu non précisé"))

    lines = [
        titre,
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"👤  <b>{nom_complet}{age_str}</b>",
        f"📍  {ori_label} de {loc}"
    ]

    if demande.get("details"):
        det = html.escape(str(demande["details"]).strip())
        lines.append(f"💬  <i>{det}</i>")

    if is_prio:
        montant_val = float(demande.get("montant") or 0.0)
        lines.append(f"💰  <b>{montant_val:.2f} €</b>")

    reseaux = []
    if demande.get("instagram"):
        raw_ig = str(demande["instagram"]).strip().lstrip("@")
        ig_esc = html.escape(raw_ig)
        reseaux.append(f'• <b>Instagram :</b> <a href="https://instagram.com/{ig_esc}">@{ig_esc}</a>')
    if demande.get("snapchat"):
        raw_snap = str(demande["snapchat"]).strip().lstrip("@")
        snap_esc = html.escape(raw_snap)
        reseaux.append(f'• <b>Snapchat :</b> <a href="https://snapchat.com/add/{snap_esc}">{snap_esc}</a>')

    if reseaux:
        lines.append("\n🌐  <b>SES RÉSEAUX</b>")
        lines.extend(reseaux)

    statut_label = db_manager.format_statut_display(
        demande.get("statut", "📥 Reçue"),
        demande.get("is_difficile", False),
        demande.get("reussie_substatus")
    )

    lines.append("\n───────  <b>STATUT</b>  ──────")
    lines.append(f" • <b>{html.escape(statut_label)}</b> • ")
    dt_mod = demande.get("date_modification")
    if dt_mod:
        lines.append(f" <i>{format_datetime_fr(dt_mod)}</i>")

    remun_asked_at = demande.get("remun_asked_at")
    if remun_asked_at:
        lines.append(f" ⏳ <i>Rémunération sollicitée le {format_date_fr(remun_asked_at)}</i>")

    lines.append("\n───────  <b>INFOS</b>  ───────")
    dt_crea = demande.get("date_creation")
    lines.append(f"<b>Déposé le :</b>  {format_datetime_fr(dt_crea)}")

    demandeur = f"@{html.escape(demande['username'])}" if demande.get("username") else (
        html.escape(str(demande.get("user_first_name") or f"User {demande['user_id']}"))
    )
    lines.append(f"<b>Par :</b>  {demandeur} (<code>{demande['user_id']}</code>)")

    ancien_alias = demande.get("ancien_admin_alias")
    raw_reason = demande.get("raison_abandon")
    if ancien_alias or raw_reason:
        alias_str = html.escape(str(ancien_alias or "Opérateur"))
        reason_str = clean_reason_text(raw_reason)
        dt_abandon = demande.get("date_modification")
        date_abandon_str = format_datetime_fr(dt_abandon) if dt_abandon else "Date inconnue"

        lines.append("\n─────  <b>HISTORIQUE</b>  ─────")
        lines.append("❌ Abandonné")
        lines.append(f"{alias_str} le {date_abandon_str}")
        lines.append(f"<b>Raison :</b> {reason_str}")

    active_tags = []
    if active_filters.get("orientation") and active_filters["orientation"] != "all":
        active_tags.append(f"🎯 {active_filters['orientation']}")
    if active_filters.get("reseau") and active_filters["reseau"] != "all":
        active_tags.append(f"🌐 {active_filters['reseau']}")
    if active_filters.get("age_range") and active_filters["age_range"] != "all":
        active_tags.append(f"🎂 {active_filters['age_range']}")
    if active_filters.get("search"):
        active_tags.append(f"🔎 «{active_filters['search']}»")

    if active_tags:
        lines.append(f"\n🏷️ <i>Filtres : {' • '.join(active_tags)}</i>")

    return "\n".join(lines)


def build_navigation_keyboard(demande: dict, page: int, total: int, user_id: int, db_manager) -> InlineKeyboardMarkup:
    """Construit le clavier des demandes disponibles selon la maquette exacte."""
    demande_id = demande["id"]
    is_admin = db_manager.is_admin(user_id)
    is_prio = bool(demande.get("prioritaire"))
    is_remun_asked = bool(demande.get("remun_asked_at"))

    buttons = [
        [InlineKeyboardButton("🎯 PRENDRE EN CHARGE", callback_data=f"suivre_demande_{demande_id}")]
    ]

    row_profil = [InlineKeyboardButton("👤 PROFIL", callback_data=f"profil_demande_{demande_id}")]
    if is_admin:
        row_profil.append(InlineKeyboardButton("🗑️ SUPPRIMER", callback_data=f"admin_del_dispo_{demande_id}"))
    else:
        row_profil.append(InlineKeyboardButton("⚠️ SIGNALER", callback_data=f"staff_report_dispo_{demande_id}"))
    buttons.append(row_profil)

    perms = db_manager.get_staff_permissions(user_id)
    can_handle_prio = (perms.get("perm_type") in ("all", "prio_only") or is_admin)

    if is_remun_asked:
        buttons.append([
            InlineKeyboardButton("⏳ RÉMUNÉRATION DEMANDÉE", callback_data="dispo_remun_pending_info")
        ])
    else:
        if not is_prio and is_admin:
            buttons.append([
                InlineKeyboardButton("💰 RÉMUNÉRATION", callback_data=f"dispo_ask_remun_std_{demande_id}")
            ])
        elif is_prio and can_handle_prio:
            buttons.append([
                InlineKeyboardButton("💰 RÉMUNÉRATION", callback_data=f"dispo_ask_remun_prio_{demande_id}")
            ])

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ PRÉCÉDENTE", callback_data=f"dispo_prev_{page}"))
    if page < total - 1:
        nav_row.append(InlineKeyboardButton("SUIVANTE ➡️", callback_data=f"dispo_next_{page}"))
    if nav_row:
        buttons.append(nav_row)

    buttons.append([
        InlineKeyboardButton("🔍 TRIER", callback_data="dispo_filters_menu"),
        InlineKeyboardButton("🎲 AU HASARD", callback_data="dispo_random")
    ])

    buttons.append([
        InlineKeyboardButton("⬅️ RETOUR", callback_data="start_menu")
    ])

    return InlineKeyboardMarkup(buttons)


def build_single_dispo_keyboard(demande: dict, viewer_id: int, is_admin: bool, back_callback: str, db_manager) -> InlineKeyboardMarkup:
    """Construit le clavier d'une demande disponible unitaire."""
    demande_id = demande["id"]
    is_vip = (demande.get("statut") == "🎯 Assignée (VIP)")
    buttons = []

    if is_vip and demande.get("admin_en_charge") == viewer_id:
        buttons.append([
            InlineKeyboardButton("✅ ACCEPTER LA MISSION", callback_data=f"vip_accept_{demande_id}"),
            InlineKeyboardButton("❌ DÉCLINER", callback_data=f"vip_decline_{demande_id}")
        ])
    else:
        buttons.append([
            InlineKeyboardButton("🎯 PRENDRE EN CHARGE", callback_data=f"suivre_demande_{demande_id}")
        ])

    row_actions = [InlineKeyboardButton("👤 PROFIL", callback_data=f"profil_demande_{demande_id}")]
    if is_admin:
        row_actions.append(InlineKeyboardButton("🗑️ SUPPRIMER", callback_data=f"admin_del_dispo_{demande_id}"))
    else:
        row_actions.append(InlineKeyboardButton("⚠️ SIGNALER", callback_data=f"staff_report_dispo_{demande_id}"))
    buttons.append(row_actions)

    is_prio = bool(demande.get("prioritaire"))
    is_remun_asked = bool(demande.get("remun_asked_at"))
    perms = db_manager.get_staff_permissions(viewer_id)
    can_handle_prio = (perms.get("perm_type") in ("all", "prio_only") or is_admin)

    if is_remun_asked:
        buttons.append([InlineKeyboardButton("⏳ RÉMUNÉRATION DEMANDÉE", callback_data="dispo_remun_pending_info")])
    else:
        if not is_prio and is_admin:
            buttons.append([InlineKeyboardButton("💰 RÉMUNÉRATION", callback_data=f"dispo_ask_remun_std_{demande_id}")])
        elif is_prio and can_handle_prio:
            buttons.append([InlineKeyboardButton("💰 RÉMUNÉRATION", callback_data=f"dispo_ask_remun_prio_{demande_id}")])

    buttons.append([InlineKeyboardButton("⬅️ RETOUR", callback_data=back_callback)])
    return InlineKeyboardMarkup(buttons)