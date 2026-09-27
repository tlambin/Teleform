"""Composants visuels, gabarits de messages et claviers pour la messagerie Staff / Direction."""

import html
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


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