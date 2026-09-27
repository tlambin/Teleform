"""Composants visuels, formatage de fiches et claviers pour les demandes suivies."""

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