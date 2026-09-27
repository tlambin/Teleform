"""Composants visuels, formatage des fiches d'archives et claviers associés."""

import html
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from utils.validators import convert_utc_to_paris


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