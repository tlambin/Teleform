"""Composants visuels, formatage de fiche et claviers pour l'affichage photo et texte des demandes."""

import html
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


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


def format_demande_card(demande: dict, db_manager, is_photo: bool = False, admin_alias: str = None) -> str:
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