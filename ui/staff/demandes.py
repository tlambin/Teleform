"""ui/staff/demandes.py
Composants visuels, gabarits textuels et claviers pour la gestion complète
des demandes côté Staff (Disponibles, Suivies, Statuts et Archives).
"""

from datetime import datetime
import html
import re
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from utils.validators import convert_utc_to_paris


# ==============================================================================
# 0. MENU PRINCIPAL DE GESTION DES DEMANDES
# ==============================================================================

def get_gerer_demandes_menu(nb_dispo: int, nb_suivies: int, nb_archives: int) -> tuple[str, InlineKeyboardMarkup]:
    """Affiche le menu de gestion des demandes avec compteurs dynamiques."""
    message = (
        "📋 <b>Gestion des demandes</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Accédez aux dossiers selon leur niveau d'assignation :"
    )
    keyboard = [
        [InlineKeyboardButton(f"📮 DISPONIBLE ({nb_dispo})", callback_data="demandes_disponibles")],
        [InlineKeyboardButton(f"💌 SUIVIES ({nb_suivies})", callback_data="demandes_suivies")],
        [InlineKeyboardButton(f"📦 ARCHIVÉES ({nb_archives})", callback_data="demandes_archives")],
        [InlineKeyboardButton("⬅️ RETOUR", callback_data="start_menu")],
    ]
    return message, InlineKeyboardMarkup(keyboard)


# ==============================================================================
# 1. FONCTIONS UTILITAIRES PARTAGÉES (DATES & TEXTES)
# ==============================================================================

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


# ==============================================================================
# 2. DEMANDES DISPONIBLES (AFFICHAGE, CLAVIERS & FILTRES)
# ==============================================================================

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
    titre = (
        f"💎  <b>Demande Prioritaire #{real_id} ({page + 1}/{total})</b>"
        if is_prio else
        f"📝  <b>Demande Standard #{real_id} ({page + 1}/{total})</b>"
    )

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


# ==============================================================================
# 3. DEMANDES SUIVIES (AFFICHAGE, CLAVIERS & NOTICES)
# ==============================================================================

def format_archive_countdown(demande: dict, db_manager) -> str:
    """Calcule et renvoie la mention visuelle du compte à rebours d'archivage dynamique."""
    if demande.get("statut") != "✅ Réussie" or demande.get("reussie_substatus") != "terminee":
        return ""

    if not demande.get("has_delivered_content"):
        return "⏳ <b>Clôture :</b> <i>En attente d'expédition du contenu</i>"

    hours_setting = db_manager.get_auto_archive_hours()
    date_liv = demande.get("date_livraison")
    if not date_liv:
        return f"📦 <b>Auto-archivage :</b> programmé sous {hours_setting}h"

    try:
        if isinstance(date_liv, str):
            date_liv = datetime.strptime(date_liv[:19], "%Y-%m-%d %H:%M:%S")
        diff_hours = (datetime.now() - date_liv).total_seconds() / 3600.0
        hours_left = max(0, int(hours_setting - diff_hours))

        if hours_left > 0:
            return f"📦 <b>Auto-archivage :</b> dans ~{hours_left}h (Contenu livré)"
        return "📦 <b>Auto-archivage :</b> <i>imminent...</i>"
    except Exception:
        return f"📦 <b>Auto-archivage :</b> programmé sous {hours_setting}h"


def format_suivi_card(demande: dict, page: int, total: int, db_manager) -> str:
    """Formate la fiche du dossier suivi par le staff avec liens sociaux cliquables."""
    real_id = demande["id"]
    is_prio = bool(demande.get("prioritaire"))
    titre = (
        f"💎  <b>Demande Prioritaire #{real_id} ({page + 1}/{total})</b>"
        if is_prio else
        f"📝  <b>Demande Standard #{real_id} ({page + 1}/{total})</b>"
    )

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
        demande.get("statut", "⏳ En attente"),
        demande.get("is_difficile", False),
        demande.get("reussie_substatus")
    )
    lines.append("\n───────  <b>STATUT</b>  ──────")
    lines.append(f" • <b>{html.escape(statut_label)}</b> • ")
    dt_mod = demande.get("date_modification")
    if dt_mod:
        lines.append(f" <i>{format_datetime_fr(dt_mod)}</i>")

    if is_prio:
        p_statut = demande.get("paiement_statut", "non_requis")
        if p_statut == "paye":
            lines.append("\n🟢 <b>Réglé et validé</b>")
        elif p_statut == "en_attente":
            lines.append("\n🟡 <b>En attente de règlement</b>")

    admin_id = demande.get("admin_en_charge")
    if admin_id:
        alias = html.escape(str(db_manager.get_staff_alias(admin_id) or f"Staff_{admin_id}"))
        lines.append(f"\n<b>Géré par :</b> <b>{alias}</b>")

    dt_suivi = demande.get("date_suivi")
    if dt_suivi:
        lines.append(f"<b>Depuis le :</b> <i>{format_datetime_fr(dt_suivi)}</i>")

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

    archive_badge = format_archive_countdown(demande, db_manager)
    if archive_badge:
        lines.append(f"\n{archive_badge}")

    return "\n".join(lines)


def build_suivi_keyboard(demande: dict, page: int, total: int) -> InlineKeyboardMarkup:
    """Construit le clavier des demandes suivies selon la maquette exacte."""
    demande_id = demande["id"]
    statut_raw = str(demande.get("statut") or "").strip()
    is_reussie = (statut_raw == "✅ Réussie")
    is_prio = bool(demande.get("prioritaire"))
    paiement_statut = demande.get("paiement_statut", "non_requis")
    has_delivered = bool(demande.get("has_delivered_content", False))

    buttons = [
        [InlineKeyboardButton("📌 CHANGER LE STATUT 📌", callback_data=f"change_status_{demande_id}")],
        [
            InlineKeyboardButton("👤 PROFIL", callback_data=f"profil_demande_{demande_id}"),
            InlineKeyboardButton("💬 CONTACT", callback_data=f"contacter_{demande_id}")
        ]
    ]

    if is_prio and is_reussie and paiement_statut == "en_attente":
        buttons.append([
            InlineKeyboardButton("💰 VALIDER LE PAIEMENT 💰", callback_data=f"confirm_payment_prio_{demande_id}")
        ])

    if is_reussie:
        if not is_prio or paiement_statut == "paye":
            if has_delivered:
                buttons.append([
                    InlineKeyboardButton("📦 ARCHIVER LE DOSSIER 📦", callback_data=f"status_archive_now_{demande_id}")
                ])
            else:
                buttons.append([
                    InlineKeyboardButton("📤 ENVOYER LE CONTENU 📤", callback_data=f"contacter_{demande_id}")
                ])

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ PRÉCÉDENTE", callback_data=f"suivi_prev_{page}"))
    if page < total - 1:
        nav_row.append(InlineKeyboardButton("SUIVANTE ➡️", callback_data=f"suivi_next_{page}"))
    if nav_row:
        buttons.append(nav_row)

    buttons.append([
        InlineKeyboardButton("🔍 TRIER", callback_data="suivi_sort_menu"),
        InlineKeyboardButton("📮 DISPO", callback_data="demandes_disponibles")
    ])

    buttons.append([
        InlineKeyboardButton("⬅️ RETOUR", callback_data="start_menu")
    ])

    return InlineKeyboardMarkup(buttons)


def build_sort_menu_keyboard(sb: str, order_arrow: str) -> InlineKeyboardMarkup:
    """Construit le clavier du menu de tri de suivi."""
    def btn_label(name: str, key: str) -> str:
        return f"✅ {name} {order_arrow}" if sb == key else name

    keyboard = [
        [
            InlineKeyboardButton(btn_label("📅 Date suivi", "date_suivi"), callback_data="suivi_set_sort_date_suivi"),
            InlineKeyboardButton(btn_label("📝 Date dépôt", "date_creation"), callback_data="suivi_set_sort_date_creation"),
        ],
        [
            InlineKeyboardButton(btn_label("👤 Nom", "nom"), callback_data="suivi_set_sort_nom"),
            InlineKeyboardButton(btn_label("🎂 Âge", "age"), callback_data="suivi_set_sort_age"),
        ],
        [
            InlineKeyboardButton(btn_label("💰 Tarif", "montant"), callback_data="suivi_set_sort_montant"),
            InlineKeyboardButton(btn_label("📊 Statut", "statut"), callback_data="suivi_set_sort_statut"),
        ],
        [
            InlineKeyboardButton("🔍 Rechercher par mot-clé", callback_data="suivi_search_prompt"),
            InlineKeyboardButton("🔄 Réinitialiser", callback_data="suivi_sort_reset"),
        ],
        [
            InlineKeyboardButton("🚀 Appliquer et afficher", callback_data="demandes_suivies")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def build_single_demande_keyboard(demande: dict, viewer_id: int, can_edit_all: bool, back_callback: str) -> InlineKeyboardMarkup:
    """Construit le clavier pour une demande unitaire (mode opérateur ou supervision)."""
    demande_id = demande["id"]
    admin_en_charge = demande.get("admin_en_charge")
    is_assigned_to_viewer = (admin_en_charge == viewer_id)
    buttons = []

    if is_assigned_to_viewer or can_edit_all:
        statut_raw = str(demande.get("statut") or "").strip()
        is_reussie = (statut_raw == "✅ Réussie")
        is_prio = bool(demande.get("prioritaire"))
        paiement_statut = demande.get("paiement_statut", "non_requis")
        has_delivered = bool(demande.get("has_delivered_content", False))

        buttons.append([InlineKeyboardButton("📌 CHANGER LE STATUT 📌", callback_data=f"change_status_{demande_id}")])
        buttons.append([
            InlineKeyboardButton("👤 PROFIL", callback_data=f"profil_demande_{demande_id}"),
            InlineKeyboardButton("💬 CONTACT", callback_data=f"contacter_{demande_id}")
        ])

        if is_prio and is_reussie and paiement_statut == "en_attente":
            buttons.append([
                InlineKeyboardButton("💰 VALIDER LE PAIEMENT 💰", callback_data=f"confirm_payment_prio_{demande_id}")
            ])

        if is_reussie:
            if not is_prio or paiement_statut == "paye":
                if has_delivered:
                    buttons.append([
                        InlineKeyboardButton("📦 ARCHIVER LE DOSSIER 📦", callback_data=f"status_archive_now_{demande_id}")
                    ])
                else:
                    buttons.append([
                        InlineKeyboardButton("📤 ENVOYER LE CONTENU 📤", callback_data=f"contacter_{demande_id}")
                    ])
    else:
        buttons.append([
            InlineKeyboardButton("👤 PROFIL", callback_data=f"profil_demande_{demande_id}")
        ])
        if admin_en_charge:
            buttons.append([
                InlineKeyboardButton("🛡️ CONTACTER LE PIÉGEUR", callback_data=f"admin_contact_staff_{demande_id}_{admin_en_charge}")
            ])

    buttons.append([InlineKeyboardButton("⬅️ RETOUR", callback_data=back_callback)])
    return InlineKeyboardMarkup(buttons)


# ==============================================================================
# 4. GESTION DES STATUTS (TRANSITIONS & MODALES)
# ==============================================================================

def build_status_change_keyboard(demande_id: int, current_status: str, is_diff: bool) -> InlineKeyboardMarkup:
    """Construit le clavier principal de progression de statut selon les règles de gestion."""
    keyboard = []

    # 1. Dossier réussi : aucune régression possible vers En attente ou En cours
    if current_status == "✅ Réussie":
        keyboard.append([
            InlineKeyboardButton("✅ MODIFIER SOUS-STATUT RÉUSSIE", callback_data=f"status_sub_reussie_{demande_id}")
        ])
        keyboard.append([
            InlineKeyboardButton("❌ ABANDONNER", callback_data=f"status_prompt_abandon_{demande_id}")
        ])

    # 2. Dossier en cours : Réussie ou Abandonner (pas de retour en attente)
    elif current_status == "🔄 En cours":
        keyboard.append([
            InlineKeyboardButton("✅ RÉUSSIE", callback_data=f"status_sub_reussie_{demande_id}"),
            InlineKeyboardButton("❌ ABANDONNER", callback_data=f"status_prompt_abandon_{demande_id}")
        ])
        diff_label = "⚠️ DIFFICILE : OUI" if is_diff else "⚠️ DIFFICILE : NON"
        keyboard.append([
            InlineKeyboardButton(diff_label, callback_data=f"status_toggle_diff_{demande_id}")
        ])

    # 3. Dossier en attente / Assignée VIP : En cours, Réussie ou Abandonner
    else:
        keyboard.append([
            InlineKeyboardButton("🔄 EN COURS", callback_data=f"status_apply_{demande_id}_encours")
        ])
        diff_label = "⚠️ DIFFICILE : OUI" if is_diff else "⚠️ DIFFICILE : NON"
        keyboard.append([
            InlineKeyboardButton(diff_label, callback_data=f"status_toggle_diff_{demande_id}")
        ])
        keyboard.append([
            InlineKeyboardButton("✅ RÉUSSIE", callback_data=f"status_sub_reussie_{demande_id}"),
            InlineKeyboardButton("❌ ABANDONNER", callback_data=f"status_prompt_abandon_{demande_id}")
        ])

    keyboard.append([
        InlineKeyboardButton("⬅️ RETOUR", callback_data=f"retour_texte_{demande_id}")
    ])
    return InlineKeyboardMarkup(keyboard)


def build_reussie_suboptions_keyboard(demande_id: int) -> InlineKeyboardMarkup:
    """Clavier de choix du sous-statut Active ou Terminée."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🟢 ACTIVE 🟢", callback_data=f"status_apply_reussie_{demande_id}_active"),
            InlineKeyboardButton("❎ TERMINÉE ❎", callback_data=f"status_apply_reussie_{demande_id}_terminee")
        ],
        [InlineKeyboardButton("⬅️ RETOUR", callback_data=f"change_status_{demande_id}")]
    ])


def build_demande_card_keyboard(demande: dict) -> InlineKeyboardMarkup:
    """Construit le clavier d'actions sur la vue de suivi après modification de statut."""
    demande_id = demande["id"]
    is_reussie = (demande.get("statut") == "✅ Réussie")
    has_delivered = bool(demande.get("has_delivered_content", False))
    is_prio = bool(demande.get("prioritaire"))
    paiement_statut = demande.get("paiement_statut", "non_requis")

    buttons = [
        [InlineKeyboardButton("📌 CHANGER LE STATUT 📌", callback_data=f"change_status_{demande_id}")],
        [
            InlineKeyboardButton("👤 PROFIL", callback_data=f"profil_demande_{demande_id}"),
            InlineKeyboardButton("💬 CONTACT", callback_data=f"contacter_{demande_id}")
        ]
    ]

    if is_prio and is_reussie and paiement_statut == "en_attente":
        buttons.append([
            InlineKeyboardButton("💰 VALIDER LE PAIEMENT 💰", callback_data=f"confirm_payment_prio_{demande_id}")
        ])

    if is_reussie:
        if not is_prio or paiement_statut == "paye":
            if has_delivered:
                buttons.append([
                    InlineKeyboardButton("📦 ARCHIVER LE DOSSIER 📦", callback_data=f"status_archive_now_{demande_id}")
                ])
            else:
                buttons.append([
                    InlineKeyboardButton("📤 ENVOYER LE CONTENU 📤", callback_data=f"contacter_{demande_id}")
                ])

    buttons.append([
        InlineKeyboardButton("🔍 TRIER", callback_data="suivi_sort_menu"),
        InlineKeyboardButton("📮 DISPO", callback_data="demandes_disponibles")
    ])
    buttons.append([InlineKeyboardButton("⬅️ RETOUR", callback_data="start_menu")])

    return InlineKeyboardMarkup(buttons)


def format_demande_suivi_text(demande: dict, db_manager) -> str:
    """Génère le texte complet de la fiche suivi mis à jour (mutualisé message texte et légende photo)."""
    real_id = html.escape(str(demande.get("request_number") or demande["id"]))
    is_prio = bool(demande.get("prioritaire"))
    titre = f"💎  <b>Demande Prioritaire #{real_id}</b>" if is_prio else f"📝  <b>Demande Standard #{real_id}</b>"

    prenom_esc = html.escape(str(demande.get("prenom") or ""))
    nom_esc = html.escape(str(demande.get("nom") or ""))
    nom_complet = f"{prenom_esc} {nom_esc}".strip() or "Identité non précisée"
    age_str = f"  •  {html.escape(str(demande['age']))} ans" if demande.get("age") is not None else ""

    ori_map = {"hetero": "Hétéro", "gay": "Gay", "bi": "Bi"}
    ori_label = html.escape(ori_map.get(str(demande.get("orientation") or "").lower(), "Non précisée"))
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
        demande.get("statut", "⏳ En attente"),
        demande.get("is_difficile", False),
        demande.get("reussie_substatus")
    )
    lines.append("\n───────  <b>STATUT</b>  ──────")
    lines.append(f" • <b>{html.escape(str(statut_label))}</b> • ")

    dt_mod = demande.get("date_modification")
    if dt_mod:
        lines.append(f" <i>{html.escape(format_datetime_fr(dt_mod))}</i>")

    if is_prio:
        p_statut = demande.get("paiement_statut", "non_requis")
        if p_statut == "paye":
            lines.append("\n🟢 <b>Réglé et validé</b>")
        elif p_statut == "en_attente":
            lines.append("\n🟡 <b>En attente de règlement</b>")

    admin_id = demande.get("admin_en_charge")
    if admin_id:
        alias = html.escape(str(db_manager.get_staff_alias(admin_id) or f"Staff_{admin_id}"))
        lines.append(f"\n<b>Géré par :</b> <b>{alias}</b>")

    lines.append("\n───────  <b>INFOS</b>  ───────")
    dt_crea = demande.get("date_creation")
    lines.append(f"<b>Déposé le :</b>  {html.escape(format_datetime_fr(dt_crea))}")

    demandeur = f"@{html.escape(demande['username'])}" if demande.get("username") else (
        html.escape(str(demande.get("user_first_name") or f"User {demande['user_id']}"))
    )
    lines.append(f"<b>Par :</b>  {demandeur} (<code>{demande['user_id']}</code>)")

    ancien_alias = demande.get("ancien_admin_alias")
    raw_reason = demande.get("raison_abandon")
    if ancien_alias or raw_reason:
        alias_str = html.escape(str(ancien_alias or "Opérateur"))
        clean_r = clean_reason_text(raw_reason)
        lines.append("\n─────  <b>HISTORIQUE</b>  ─────")
        lines.append("❌ Abandonné")
        lines.append(f"{alias_str} le {html.escape(format_datetime_fr(demande.get('date_modification')))}")
        lines.append(f"<b>Raison :</b> {clean_r}")

    return "\n".join(lines)


def build_reussie_active_notice(req_num: str, prenom: str, demande_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Message et boutons envoyés à l'opérateur pour une demande passée en Réussie Active."""
    text = (
        f"💡 <b>Rappel de suivi (Demande #{req_num})</b>\n\n"
        f"Le statut a été passé en <b>Réussie (Active)</b>.\n"
        f"D'autres contenus peuvent être obtenus sur <b>{prenom}</b>."
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Contacter le demandeur", callback_data=f"contacter_{demande_id}")],
        [InlineKeyboardButton("💌 Mes suivis", callback_data="demandes_suivies")]
    ])
    return text, kb


def build_prio_wait_payment_notice(req_num: str, montant: float, demande_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Message et boutons envoyés à l'opérateur pour une demande prioritaire en attente d'encaissement."""
    text = (
        f"💎 <b>Demande prioritaire #{req_num} réussie !</b>\n\n"
        f"Montant alloué : <b>{montant:.2f} €</b>\n\n"
        "⏳ <b>En attente du règlement du client :</b>\n"
        "Le demandeur a reçu les options de paiement (Stars Telegram ou contact direct).\n\n"
        "• Si le client règle par Stars, vous serez notifié instantanément.\n"
        "• S'il vous contacte pour un autre moyen de paiement (PayPal, virement, etc.), "
        "vous pourrez valider la réception des fonds via le bouton <b>« 💰 VALIDER LE PAIEMENT 💰 »</b> sur votre fiche de suivi.\n\n"
        "<i>Conservez vos fichiers : vous pourrez les envoyer dès que le paiement sera validé.</i>"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Échanger avec le client", callback_data=f"contacter_{demande_id}")],
        [InlineKeyboardButton("📄 Ouvrir la fiche du dossier", callback_data=f"retour_texte_{demande_id}")],
        [InlineKeyboardButton("💌 Mes suivis", callback_data="demandes_suivies")]
    ])
    return text, kb


def build_delivery_required_notice(req_num: str, demande_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Message et boutons envoyés à l'opérateur rappelant l'envoi obligatoire de contenu."""
    text = (
        f"⚠️ <b>Action requise (Demande #{req_num})</b>\n\n"
        "La demande a été déclarée <b>Réussie (Terminée)</b>.\n\n"
        "👉 Vous devez <b>obligatoirement envoyer le contenu obtenu</b> à l'utilisateur.\n"
        "<i>Le bouton d'archivage sera débloqué dès votre premier envoi (et la demande s'auto-archivera sous le délai configuré).</i>"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Transmettre le contenu maintenant", callback_data=f"contacter_{demande_id}")],
        [InlineKeyboardButton("💌 Mes suivis", callback_data="demandes_suivies")]
    ])
    return text, kb


def build_ready_to_archive_notice(req_num: str, demande_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Message et boutons envoyés à l'opérateur pour un dossier prêt à archiver manuellement."""
    text = (
        f"📦 <b>Dossier #{req_num} prêt pour l'archivage</b>\n\n"
        "Le contenu a bien été livré. Vous pouvez archiver ce dossier immédiatement pour clore la fiche, "
        "ou le laisser s'archiver automatiquement."
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 ARCHIVER LE DOSSIER 📦", callback_data=f"status_archive_now_{demande_id}")],
        [InlineKeyboardButton("💌 Mes suivis", callback_data="demandes_suivies")]
    ])
    return text, kb


# ==============================================================================
# 5. DEMANDES ARCHIVÉES (AFFICHAGE & NAVIGATION)
# ==============================================================================

def format_archive_card(item: dict, page: int, total: int, is_global: bool, staff_alias: str = None) -> str:
    """Formate la fiche d'une demande archivée avec liens sociaux cliquables."""
    prenom = html.escape(str(item.get("prenom") or ""))
    nom = html.escape(str(item.get("nom") or ""))
    complet = f"{prenom} {nom}".strip() or "Non renseigné"
    loc = html.escape(str(item.get("localisation") or "Non précisée"))
    statut = html.escape(str(item.get("statut") or "Archivée"))
    orig_id = item.get("original_id") or item.get("id") or "?"
    age = item.get("age") or "?"

    type_badge = "💎 Prioritaire" if item.get("prioritaire") else "📝 Standard"
    montant_str = f" ({item.get('montant', 0):.2f} €)" if item.get("prioritaire") else ""

    dt_crea = item.get("date_creation")
    crea_str = convert_utc_to_paris(dt_crea).strftime("%d/%m/%Y à %H:%M") if dt_crea else "?"

    dt_arch = item.get("date_archivage")
    arch_str = convert_utc_to_paris(dt_arch).strftime("%d/%m/%Y à %H:%M") if dt_arch else "?"

    titre = "📦 <b>Archives Générales</b>" if is_global else "📦 <b>Mon Archive Dossier</b>"
    lines = [
        f"{titre} #{orig_id} ({page + 1}/{total})\n",
        f"👤 <b>Cible :</b> {complet} ({age} ans)",
        f"📍 <b>Localisation :</b> {loc}",
        f"🎯 <b>Type :</b> {type_badge}{montant_str}",
        f"📊 <b>Statut de clôture :</b> <code>{statut}</code>",
    ]

    if is_global:
        if staff_alias:
            lines.append(f"👨‍💼 <b>Traité par :</b> {html.escape(staff_alias)}")
        else:
            lines.append("👨‍💼 <b>Traité par :</b> <i>Non spécifié</i>")

    reseaux = []
    if item.get("instagram"):
        raw_ig = str(item["instagram"]).strip().lstrip("@")
        ig_esc = html.escape(raw_ig)
        reseaux.append(f'📷 <a href="https://instagram.com/{ig_esc}">@{ig_esc}</a>')
    if item.get("snapchat"):
        raw_snap = str(item["snapchat"]).strip().lstrip("@")
        snap_esc = html.escape(raw_snap)
        reseaux.append(f'👻 <a href="https://snapchat.com/add/{snap_esc}">{snap_esc}</a>')

    if reseaux:
        lines.append(f"🌐 <b>Réseaux :</b> {' | '.join(reseaux)}")

    if item.get("details"):
        det = html.escape(str(item["details"]))
        lines.append(f"💬 <b>Remarques :</b> <i>{det[:200]}</i>")

    lines.append(f"\n📅 <i>Créée le {crea_str}</i>")
    lines.append(f"🗄️ <i>Archivée le {arch_str}</i>")

    return "\n".join(lines)


def build_archive_keyboard(item: dict, page: int, total: int, can_manage: bool, is_global: bool) -> InlineKeyboardMarkup:
    """Génère la barre d'actions et de navigation dans les archives."""
    prefix = "global_arch_page_" if is_global else "archive_page_"
    back_cb = "parametres" if is_global else "gerer_demandes"

    buttons = []
    archive_id = item["id"]
    statut_raw = str(item.get("statut") or "")

    if can_manage:
        action_row = [
            InlineKeyboardButton("💬 Contacter le client", callback_data=f"contacter_archive_{archive_id}")
        ]

        if "Réussie" in statut_raw:
            action_row.append(
                InlineKeyboardButton("🔄 Réussie Active", callback_data=f"unarchive_reussie_{archive_id}_{page}_{int(is_global)}")
            )
        elif "Abandon" in statut_raw or "Annul" in statut_raw:
            action_row.append(
                InlineKeyboardButton("🔄 Reprendre le dossier", callback_data=f"unarchive_abandon_{archive_id}_{page}_{int(is_global)}")
            )

        if action_row:
            buttons.append(action_row)

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Précédente", callback_data=f"{prefix}{page - 1}"))
    if page < total - 1:
        nav.append(InlineKeyboardButton("Suivante ➡️", callback_data=f"{prefix}{page + 1}"))

    if nav:
        buttons.append(nav)

    buttons.append([InlineKeyboardButton("⬅️ RETOUR", callback_data=back_cb)])
    return InlineKeyboardMarkup(buttons)

# ==============================================================================
# 6. AFFICHAGE PHOTO & RETOUR TEXTE (FICHE DEMANDE)
# ==============================================================================

def build_keyboard_for_viewer(demande: dict, viewer_id: int, custom_back: str = None, is_admin_or_owner: bool = False) -> InlineKeyboardMarkup:
    """Construit le clavier contextuel : opérationnel, supervision admin ou retour liste."""
    demande_id = demande["id"]
    admin_en_charge = demande.get("admin_en_charge")
    is_assigned_operator = (viewer_id == admin_en_charge)
    is_creator = (viewer_id == demande.get("user_id"))

    # Cas 1 : Consultation depuis une liste de profil pour un dossier tiers
    if custom_back and not (is_assigned_operator or is_creator):
        keyboard = []
        if is_admin_or_owner:
            contact_row = []
            if admin_en_charge and int(admin_en_charge) != viewer_id:
                contact_row.append(
                    InlineKeyboardButton("🦈 Contacter le piégeur", callback_data=f"admin_contact_staff_{demande_id}_{admin_en_charge}")
                )
            contact_row.append(
                InlineKeyboardButton("👤 Contacter le client", callback_data=f"contacter_{demande_id}")
            )
            keyboard.append(contact_row)

        keyboard.append([InlineKeyboardButton("↩️ Retour à la liste", callback_data=custom_back)])
        return InlineKeyboardMarkup(keyboard)

    # Cas 2 : Vue opérationnelle standard
    keyboard = [
        [
            InlineKeyboardButton("🔄 Statut", callback_data=f"change_status_{demande_id}"),
            InlineKeyboardButton("💬 Contacter", callback_data=f"contacter_{demande_id}")
        ],
        [
            InlineKeyboardButton("👤 Profil Demandeur", callback_data=f"profil_demande_{demande_id}")
        ]
    ]

    if custom_back:
        keyboard.append([InlineKeyboardButton("↩️ Retour à la liste", callback_data=custom_back)])
    else:
        keyboard.append([InlineKeyboardButton("🔙 Mes Suivis", callback_data="demandes_suivies")])

    return InlineKeyboardMarkup(keyboard)


def format_photo_demande_card(demande: dict, db_manager, is_photo: bool = False, admin_alias: str = None) -> str:
    """Génère la fiche textuelle ou la légende de la photo avec liens sociaux."""
    priorite_icon = "💎" if demande.get("prioritaire") else "📝"
    type_str = "Prioritaire" if demande.get("prioritaire") else "Standard"
    montant_val = float(demande.get("montant") or 0.0)
    montant_str = f" ({montant_val:.2f} €)" if demande.get("prioritaire") else ""

    prenom_esc = html.escape(str(demande.get("prenom") or ""))
    nom_esc = html.escape(str(demande.get("nom") or ""))
    nom_complet = f"{prenom_esc} {nom_esc}".strip()
    loc_esc = html.escape(str(demande.get("localisation") or "Non précisée"))

    statut_display = db_manager.format_statut_display(
        demande.get("statut", "📥 Reçue"),
        demande.get("is_difficile", False),
        demande.get("reussie_substatus")
    )
    statut_esc = html.escape(statut_display)
    req_num = html.escape(str(demande.get("request_number", demande["id"])))

    if demande.get("username"):
        user_display = f"@{html.escape(demande['username'])}"
    elif demande.get("user_first_name"):
        user_display = html.escape(demande["user_first_name"])
    else:
        user_display = f"User {demande['user_id']}"

    date_str = str(demande.get("date_creation", ""))[:16]

    if is_photo:
        lines = [
            f"📷 <b>Photo de la demande #{req_num}</b>\n",
            f"👤 <b>Identité :</b> {nom_complet} ({demande.get('age', '?')} ans)",
            f"📍 <b>Localisation :</b> {loc_esc}",
            f"🎯 <b>Type :</b> {priorite_icon} {type_str}{montant_str}",
            f"📊 <b>Statut :</b> <code>{statut_esc}</code>",
            f"🙋 <b>Demandeur :</b> {user_display}"
        ]
        if demande.get("details"):
            det = str(demande["details"])
            det_court = (det[:100] + "...") if len(det) > 100 else det
            lines.append(f"💬 <b>Détails :</b> <i>{html.escape(det_court)}</i>")
    else:
        lines = [
            f"💌 <b>Demande #{req_num}</b>\n",
            f"👤 <b>Identité :</b> {nom_complet} ({demande.get('age', '?')} ans)",
            f"📍 <b>Localisation :</b> {loc_esc}",
            f"🎯 <b>Type :</b> {priorite_icon} {type_str}{montant_str}",
            f"📊 <b>Statut :</b> <code>{statut_esc}</code>",
            f"🦈 <b>Référent :</b> {html.escape(str(admin_alias or 'Non assigné'))}",
            f"🙋 <b>Demandeur :</b> {user_display}"
        ]
        reseaux = []
        if demande.get("instagram"):
            ig = html.escape(str(demande["instagram"]))
            reseaux.append(f"📷 <a href='https://instagram.com/{ig}'>@{ig}</a>")
        if demande.get("snapchat"):
            snap = html.escape(str(demande["snapchat"]))
            reseaux.append(f"👻 <a href='https://snapchat.com/add/{snap}'>{snap}</a>")
        if reseaux:
            lines.append(f"🌐 <b>Réseaux :</b> {' | '.join(reseaux)}")

        if demande.get("details"):
            lines.append(f"💬 <b>Détails :</b> <i>{html.escape(str(demande['details']))}</i>")

    lines.append(f"\n📅 <i>Reçue le {date_str}</i>")
    return "\n".join(lines)