"""Composants visuels, textes et claviers pour la modification et la suppression de demandes."""

import html
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from utils.validators import Validators


def build_modify_menu_content(demande: dict) -> tuple[str, InlineKeyboardMarkup]:
    """Génère l'interface des champs modifiables selon le statut du dossier."""
    prenom_esc = html.escape(demande.get("prenom") or "")
    nom_esc = html.escape(demande.get("nom") or "")
    nom_complet = f"{prenom_esc} {nom_esc}".strip()
    loc_esc = html.escape(str(demande.get("localisation") or ""))
    req_num = html.escape(str(demande.get("request_number", demande["id"])))
    statut = demande.get("statut", "")
    is_prio = bool(demande.get("prioritaire"))
    montant = float(demande.get("montant") or 0.0)
    d_id = demande["id"]

    is_en_cours = statut in ("⏳ En attente", "🔄 En cours")
    keyboard = []

    if is_en_cours:
        text = (
            f"✏️ <b>Revalorisation du dossier n°{req_num}</b>\n\n"
            f"👤 <b>Cible :</b> {nom_complet} ({demande.get('age', '?')} ans)\n"
            f"💎 <b>Tarif actuel :</b> <b>{montant:.2f} €</b>\n"
            f"📊 <b>Statut :</b> <code>{statut}</code>\n\n"
            "Le dossier est déjà en cours de traitement. Vous pouvez uniquement <b>augmenter</b> "
            "le montant proposé à votre piégeur pour motiver ou accélérer le résultat :"
        )
        keyboard.append([InlineKeyboardButton(f"💰 Rehausser le tarif (Actuel: {montant:.2f} €)", callback_data=f"edit_montant_{d_id}")])
        keyboard.append([InlineKeyboardButton("🔙 Retour aux demandes", callback_data="voir_demandes")])
    else:
        text = (
            f"✏️ <b>Modifier la demande n°{req_num}</b>\n\n"
            f"👤 <b>Identité :</b> {nom_complet} ({demande.get('age', '?')} ans)\n"
            f"📍 <b>Localisation :</b> {loc_esc}\n"
        )
        if is_prio:
            text += f"💎 <b>Gratification :</b> <b>{montant:.2f} €</b>\n"

        text += "\nSélectionnez la donnée à modifier :"

        keyboard.extend([
            [
                InlineKeyboardButton("👤 Prénom", callback_data=f"edit_prenom_{d_id}"),
                InlineKeyboardButton("📝 Nom", callback_data=f"edit_nom_{d_id}")
            ],
            [
                InlineKeyboardButton("🎂 Âge", callback_data=f"edit_age_{d_id}"),
                InlineKeyboardButton("📍 Ville", callback_data=f"edit_localisation_{d_id}")
            ],
            [
                InlineKeyboardButton("📷 Instagram", callback_data=f"edit_instagram_{d_id}"),
                InlineKeyboardButton("👻 Snapchat", callback_data=f"edit_snapchat_{d_id}")
            ],
            [InlineKeyboardButton("💬 Remarques / Détails", callback_data=f"edit_details_{d_id}")],
        ])

        if is_prio:
            keyboard.append([InlineKeyboardButton(f"💰 Modifier le tarif ({montant:.2f} €)", callback_data=f"edit_montant_{d_id}")])

        keyboard.extend([
            [InlineKeyboardButton("🗑️ Supprimer la demande", callback_data=f"delete_{d_id}")],
            [InlineKeyboardButton("🔙 Retour aux demandes", callback_data="voir_demandes")]
        ])

    return text, InlineKeyboardMarkup(keyboard)


def build_edit_prompt_content(field_name: str, demande_id: int, demande: dict, allowed_fields: dict) -> tuple[str, InlineKeyboardMarkup]:
    """Affiche les instructions de saisie pour le champ sélectionné."""
    field_label = allowed_fields.get(field_name, field_name)

    if field_name == "montant":
        montant_actuel = float(demande.get("montant") or 0.0)
        statut = demande.get("statut", "")
        is_en_cours = statut in ("⏳ En attente", "🔄 En cours")

        if is_en_cours:
            consigne = (
                f"• Montant minimum actuel : <b>{montant_actuel:.2f} €</b>\n\n"
                "<i>Ce dossier étant déjà pris en charge, le montant ne peut qu'être augmenté.</i>"
            )
        else:
            consigne = (
                f"• Montant actuel : <b>{montant_actuel:.2f} €</b>\n\n"
                "<i>Vous pouvez ajuster librement le tarif proposé (à la hausse ou à la baisse, supérieur à 0).</i>"
            )

        text = (
            f"💰 <b>Modifier le tarif de la demande #{demande_id}</b>\n\n"
            f"{consigne}\n\n"
            "Tapez votre nouveau tarif (en euros) par message texte :"
        )
    else:
        help_text = Validators.get_validation_help(field_name)
        text = (
            f"✏️ <b>Modification : {html.escape(field_label)}</b>\n\n"
            f"{help_text}\n\n"
            "Envoyez votre nouvelle valeur par message texte :"
        )

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("❌ Annuler", callback_data="cancel_edit")
    ]])
    return text, keyboard


def build_delete_confirmation_content(demande: dict) -> tuple[str, InlineKeyboardMarkup]:
    """Affiche l'écran d'avertissement avant suppression."""
    prenom_esc = html.escape(demande.get("prenom") or "")
    nom_esc = html.escape(demande.get("nom") or "")
    nom_complet = f"{prenom_esc} {nom_esc}".strip()
    req_num = html.escape(str(demande.get("request_number", demande["id"])))

    text = (
        f"⚠️ <b>Confirmation de suppression</b>\n\n"
        f"Demande n°<b>{req_num}</b> ({nom_complet})\n\n"
        "Cette action est irréversible. Confirmez-vous la suppression ?"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑️ Confirmer la suppression", callback_data=f"confirm_delete_{demande['id']}")],
        [InlineKeyboardButton("❌ Annuler", callback_data=f"modify_{demande['id']}")]
    ])
    return text, keyboard