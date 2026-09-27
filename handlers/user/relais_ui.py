"""Composants visuels, gabarits textuels et claviers pour le relais des messages demandeur."""

import html
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def build_relay_header(user, is_vip: bool, demande_id: int, user_comment: str) -> str:
    """Génère l'en-tête du message transmis au référent."""
    badge_vip = " ⭐ <b>[VIP]</b>" if is_vip else ""
    user_label = f"@{user.username}" if user.username else f"{user.first_name} (ID : {user.id})"
    user_label_esc = html.escape(user_label)
    corps = f"\n\n« {html.escape(user_comment)} »" if user_comment else ""

    return (
        f"📩 <b>Message du demandeur{badge_vip} (Demande #{demande_id})</b>\n"
        f"De : {user_label_esc}"
        f"{corps}"
    )


def build_admin_relay_keyboard(demande_id: int, is_conv: bool) -> InlineKeyboardMarkup:
    """Construit le clavier d'actions pour le piégeur recevant la réponse."""
    if is_conv:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("💬 RÉPONDRE 💬", callback_data=f"contacter_{demande_id}")],
            [InlineKeyboardButton("🔒 CLÔTURER LA CONVERSATION 🔒", callback_data=f"contact_close_conv_{demande_id}")],
        ])
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("💬 RÉPONDRE À NOUVEAU", callback_data=f"contacter_{demande_id}"),
        InlineKeyboardButton("📄 VOIR LA FICHE", callback_data=f"retour_texte_{demande_id}"),
    ]])


def get_client_confirmation_content(demande_id: int, admin_id: int, is_conv: bool) -> tuple[str, InlineKeyboardMarkup]:
    """Message et clavier de confirmation envoyés au demandeur."""
    if is_conv:
        text = (
            "✅ <b>Message transmis à votre référent !</b>\n\n"
            "<i>La conversation reste ouverte. Cliquez ci-dessous si vous souhaitez ajouter un autre message ou document :</i>"
        )
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("💬 ENVOYER UN AUTRE MESSAGE 💬", callback_data=f"reply_to_admin_{demande_id}_{admin_id}")
        ]])
    else:
        text = "✅ <b>Votre message a été transmis à votre référent !</b>"
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🗂️ MES DEMANDES 🗂️", callback_data="voir_demandes")
        ]])
    return text, kb


def build_surveillance_alert(
    user_label_esc: str,
    badge_vip: str,
    demande_id: int,
    alias_staff: str,
    admin_id: int,
    corps: str
) -> tuple[str, InlineKeyboardMarkup]:
    """Alerte et clavier pour les superviseurs lors de la réception d'un message client."""
    alias_staff_esc = html.escape(str(alias_staff or "Opérateur"))
    text = (
        f"📩 <b>SURVEILLANCE — RÉPONSE DU DEMANDEUR</b>\n\n"
        f"• <b>Demandeur :</b> {user_label_esc}{badge_vip}\n"
        f"• <b>Dossier :</b> #{demande_id}\n"
        f"• <b>Opérateur :</b> {alias_staff_esc} (<code>{admin_id}</code>)"
        f"{corps}"
    )
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("📄 VOIR LE DOSSIER 📄", callback_data=f"retour_texte_{demande_id}")
    ]])
    return text, kb