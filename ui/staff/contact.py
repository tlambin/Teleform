"""ui/staff/contact.py
Composants visuels, gabarits de messages et claviers pour la messagerie interne
Staff / Direction et les échanges directs avec les clients.
"""

import html
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


# ==============================================================================
# 1. MESSAGERIE INTERNE (STAFF <-> DIRECTION)
# ==============================================================================

def get_start_contact_content(owner_alias: str, staff_alias: str) -> tuple[str, InlineKeyboardMarkup]:
    """Texte d'invite et clavier pour initier un message vers la direction."""
    owner_esc = html.escape(str(owner_alias or "Direction"))
    staff_esc = html.escape(str(staff_alias or "Membre"))

    text = (
        f"👑 <b>Contacter la Direction ({owner_esc})</b>\n\n"
        f"Votre message sera transmis avec votre alias officiel <b>{staff_esc}</b>.\n\n"
        "Envoyez votre message ci-dessous (texte, photo ou document) :"
    )
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("❌ Annuler", callback_data="cancel_contact_owner")
    ]])
    return text, keyboard


def build_owner_forward_header(staff_alias: str, staff_id: int) -> str:
    """En-tête HTML accompagnant le message transmis à la direction."""
    alias_esc = html.escape(str(staff_alias or f"Staff_{staff_id}"))
    return (
        f"📨 <b>Message interne du membre : {alias_esc}</b>\n"
        f"🆔 ID : <code>{staff_id}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
    )


def build_owner_reply_keyboard(raw_staff_alias: str, staff_id: int) -> InlineKeyboardMarkup:
    """Clavier permettant à la direction de répondre directement au staff."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(f"💬 Répondre à {raw_staff_alias}", callback_data=f"owner_reply_to_{staff_id}")
    ]])


def get_owner_reply_prompt_content(staff_alias: str, target_staff_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Invite de saisie pour la direction lorsqu'elle répond à un opérateur."""
    alias_esc = html.escape(str(staff_alias or f"Membre_{target_staff_id}"))
    text = (
        f"💬 <b>Répondre au membre {alias_esc}</b> (ID : <code>{target_staff_id}</code>)\n\n"
        "Tapez votre réponse au clavier (votre alias officiel de direction sera utilisé) :"
    )
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("❌ Annuler", callback_data="cancel_owner_reply")
    ]])
    return text, keyboard


def build_staff_response_notification(owner_alias: str, raw_text: str) -> tuple[str, InlineKeyboardMarkup]:
    """Notification remise au staff contenant la réponse de la direction."""
    owner_esc = html.escape(str(owner_alias or "Direction"))
    texte_esc = html.escape(raw_text.strip())

    text = (
        f"👑 <b>Réponse de la Direction ({owner_esc})</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"« {texte_esc} »"
    )
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("💬 Répondre à la direction", callback_data="contacter_owner")
    ]])
    return text, keyboard


def get_sent_success_keyboard() -> InlineKeyboardMarkup:
    """Bouton de retour aux paramètres suite à l'envoi réussi vers la direction."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔙 Menu Paramètres", callback_data="parametres")
    ]])


# ==============================================================================
# 2. ÉCHANGES ET ENVOI DE CONTENU (STAFF <-> CLIENT)
# ==============================================================================

def build_contact_user_menu(
    req_num: int,
    cible_str: str,
    conv_active: bool,
    is_bundle: bool,
    demande_id: int
) -> tuple[str, InlineKeyboardMarkup]:
    """Menu interactif de configuration de l'échange avec le client."""
    badge_bundle = "✅ OUI" if is_bundle else "❌ NON"

    text = (
        "💬 <b>CONTACTER LE CLIENT</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Demande #{req_num}{cible_str}\n\n"
        "<i>Choisissez le type d'échange :</i>\n\n"
        "• <i>Simple : Le client a droit à une seule réponse.</i>\n\n"
        "• <i>Notification : Sans réponse possible.</i>\n\n"
        "• <i>Conversation : Discussion fluide ouverte à plusieurs messages.</i>\n\n"
        "<i>Option Contenu :</i>\n\n"
        "<i>Activez-la si vous souhaitez envoyer du contenu (photos/vidéos)</i>"
    )

    buttons = [
        [
            InlineKeyboardButton("💬 SIMPLE", callback_data=f"contact_mode_{demande_id}_yes"),
            InlineKeyboardButton("🔒 NOTIFICATION", callback_data=f"contact_mode_{demande_id}_no")
        ]
    ]

    if conv_active:
        buttons.append([
            InlineKeyboardButton("🔒 CLÔTURER LA CONVERSATION", callback_data=f"contact_close_conv_{demande_id}")
        ])
    else:
        buttons.append([
            InlineKeyboardButton("💬 CONVERSATION", callback_data=f"contact_mode_{demande_id}_conv")
        ])

    buttons.append([
        InlineKeyboardButton(f"📦 AVEC DU CONTENU : {badge_bundle}", callback_data=f"toggle_contact_content_{demande_id}")
    ])
    buttons.append([
        InlineKeyboardButton("⬅️ RETOUR", callback_data=f"retour_texte_{demande_id}")
    ])

    return text, InlineKeyboardMarkup(buttons)


def format_close_conv_client_notification(req_num: int) -> tuple[str, InlineKeyboardMarkup]:
    """Notification transmise au client quand l'opérateur ferme la conversation."""
    text = (
        f"ℹ️ <b>Conversation clôturée (Demande #{req_num})</b>\n\n"
        "Votre référent a clôturé la discussion en cours pour ce dossier.\n"
        "Si besoin, vous pouvez consulter vos demandes ci-dessous :"
    )
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🗂️ MES DEMANDES", callback_data="voir_demandes")
    ]])
    return text, kb


def get_contact_input_prompt(
    req_num: int,
    prenom_esc: str,
    is_content_bundle: bool,
    demande_id: int
) -> tuple[str, InlineKeyboardMarkup]:
    """Invite de saisie pour amorcer l'envoi direct ou groupé."""
    if is_content_bundle:
        text = (
            "📤 <b>ENVOI DU CONTENU GROUPÉ</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Demande #{req_num} - {prenom_esc}\n\n"
            "<i>Envoyez vos textes, photos, vidéos ou documents. Un panier se mettra à jour sous chaque envoi.</i>\n\n"
            "<i>Cliquez sur ENVOYER quand vous aurez tout déposé.</i>"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 ENVOYER (0 ÉLÉMENT)", callback_data=f"send_batch_{demande_id}")],
            [InlineKeyboardButton("⬅️ RETOUR", callback_data=f"cancel_contact_{demande_id}")]
        ])
    else:
        text = (
            f"💬 <b>Envoi direct (Dossier #{req_num} - {prenom_esc})</b>\n\n"
            "Tapez votre message ou envoyez votre média : il sera <b>transmis instantanément</b> au client."
        )
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("⬅️ RETOUR", callback_data=f"cancel_contact_{demande_id}")
        ]])
    return text, keyboard


def build_basket_status_content(req_num: int, total: int, demande_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Panneau de mise à jour du panier de médias collectés."""
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🚀 ENVOYER ({total})", callback_data=f"send_batch_{demande_id}")],
        [InlineKeyboardButton("⬅️ RETOUR", callback_data=f"cancel_contact_{demande_id}")]
    ])
    text = (
        f"📥 <b>PANIER D'ENVOI : {total} élément{'s' if total > 1 else ''}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Demande #{req_num}\n\n"
        "<i>Déposez la suite de vos fichiers ou cliquez ci-dessous pour expédier l'ensemble :</i>"
    )
    return text, keyboard


def build_direct_message_header(req_num: int, alias_esc: str) -> str:
    """En-tête de message individuel remis au demandeur."""
    return f"💬 <b>Message de l'équipe (Demande #{req_num})</b>\nDe : <b>{alias_esc}</b>\n\n"


def build_batch_message_header(req_num: int, alias_esc: str, corps: str, mode: str, allow_reply: bool) -> str:
    """En-tête de lot remis au demandeur."""
    footer = (
        "\n\n<i>💬 Une conversation directe est ouverte avec votre référent.</i>"
        if mode == "conv"
        else ("\n\n<i>Vous pouvez répondre une seule fois ci-dessous.</i>" if allow_reply else "")
    )
    return (
        f"💬 <b>Message de l'équipe (Demande #{req_num})</b>\n"
        f"De : <b>{alias_esc}</b>"
        f"{corps}"
        f"{footer}"
    )


def get_client_reply_keyboard(demande_id: int, admin_id: int) -> InlineKeyboardMarkup:
    """Bouton permettant au demandeur de répondre à l'opérateur."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("💬 RÉPONDRE", callback_data=f"reply_to_admin_{demande_id}_{admin_id}")
    ]])


def get_staff_conv_open_confirmation(demande_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Confirmation au staff de l'envoi d'un message avec conversation maintenue ouverte."""
    text = (
        "🚀 <b>Message transmis au demandeur !</b>\n"
        "<i>La conversation reste ouverte. Vous pouvez continuer à écrire ou envoyer des fichiers directement.</i>"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔒 CLÔTURER LA CONVERSATION", callback_data=f"contact_close_conv_{demande_id}")],
        [InlineKeyboardButton("⬅️ RETOUR", callback_data=f"retour_texte_{demande_id}")]
    ])
    return text, kb


def get_batch_sent_success_content(total_items: int, alias_esc: str, demande_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Confirmation d'expédition du lot de fichiers pour le staff."""
    done_text = (
        f"✅ <b>Lot de {total_items} élément{'s' if total_items > 1 else ''} envoyé avec succès !</b>\n"
        f"Transmis sous votre alias : <code>{alias_esc}</code>"
    )
    back_keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("⬅️ RETOUR", callback_data=f"retour_texte_{demande_id}")
    ]])
    return done_text, back_keyboard