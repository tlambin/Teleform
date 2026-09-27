"""Composants visuels, gabarits textuels et claviers pour la gestion des alias du staff."""

import html
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def get_alias_locked_content() -> tuple[str, InlineKeyboardMarkup]:
    """Message et clavier quand un alias est déjà verrouillé."""
    text = (
        "🔒 <b>Alias verrouillé</b>\n\n"
        "Vous avez déjà configuré votre alias officiel. "
        "Seule la direction peut le modifier désormais."
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Paramètres", callback_data="parametres")]])
    return text, kb


def build_alias_prompt_content(
    target_alias: str,
    target_id: int,
    user_id: int,
    is_owner: bool
) -> tuple[str, InlineKeyboardMarkup]:
    """Construit l'invite de saisie du nouvel alias avec les avertissements appropriés."""
    target_alias_esc = html.escape(target_alias)

    if not is_owner and target_id == user_id:
        avertissement = (
            "⚠️ <b>Attention :</b> Vous ne disposez que d'<b>une seule modification</b> pour définir votre alias. "
            "Une fois validé, il sera définitivement verrouillé.\n\n"
        )
        retour_btn = InlineKeyboardButton("❌ Annuler", callback_data="cancel_alias_change")
    elif is_owner and target_id != user_id:
        avertissement = (
            "👑 <b>Gestion Propriétaire</b>\n"
            f"Modification forcée de l'alias pour le membre (ID : <code>{target_id}</code>).\n\n"
        )
        retour_btn = InlineKeyboardButton("❌ Annuler", callback_data="gerer_staff")
    else:
        avertissement = ""
        retour_btn = InlineKeyboardButton("❌ Annuler", callback_data="cancel_alias_change")

    text = (
        f"✏️ <b>Configuration de l'alias</b>\n\n"
        f"Alias actuel : <code>{target_alias_esc}</code>\n\n"
        f"{avertissement}"
        "Envoyez le nouveau pseudonyme en réponse à ce message :\n"
        "• 2 à 30 caractères\n"
        "• Lettres, chiffres, espaces, tirets et underscores autorisés\n"
        "• Doit être unique au sein de toute l'équipe"
    )
    keyboard = InlineKeyboardMarkup([[retour_btn]])
    return text, keyboard


def build_alias_success_content(
    new_alias: str,
    target_id: int,
    user_id: int,
    is_owner: bool
) -> tuple[str, InlineKeyboardMarkup]:
    """Construit le message de confirmation et le clavier de redirection."""
    new_alias_esc = html.escape(new_alias)

    if is_owner and target_id != user_id:
        retour_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("👥 Équipe Staff", callback_data="gerer_staff")],
            [InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")]
        ])
        succes_msg = (
            f"✅ <b>Alias mis à jour avec succès !</b>\n\n"
            f"👤 <b>Membre (ID {target_id}) :</b> <code>{new_alias_esc}</code>"
        )
    else:
        verrou_txt = "\n\n🔒 <i>Votre alias est désormais verrouillé et ne peut plus être modifié.</i>"
        retour_kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Menu Paramètres", callback_data="parametres")
        ]])
        succes_msg = f"✅ <b>Alias mis à jour :</b> <code>{new_alias_esc}</code>{verrou_txt}"

    return succes_msg, retour_kb


def get_cancel_alias_content(is_owner: bool, target_id: int, user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Message et clavier d'annulation de changement d'alias."""
    if is_owner and target_id and target_id != user_id:
        callback_target = "gerer_staff"
        btn_label = "👥 Équipe Staff"
    else:
        callback_target = "parametres"
        btn_label = "🔙 Paramètres"

    msg = "❌ <b>Modification d'alias annulée.</b>"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(btn_label, callback_data=callback_target)]])
    return msg, kb


def format_status_notification_text(
    prenom: str,
    request_number: int,
    old_status: str,
    new_status: str,
    admin_alias: str
) -> str:
    """Formate la notification directe de statut envoyée au demandeur."""
    prenom_esc = html.escape(str(prenom or ""))
    old_esc = html.escape(str(old_status or ""))
    new_esc = html.escape(str(new_status or ""))
    alias_esc = html.escape(str(admin_alias or ""))

    return (
        f"📢 <b>Notification de suivi</b>\n\n"
        f"Bonjour <b>{prenom_esc}</b>, le statut de votre demande <b>#{request_number}</b> a évolué :\n\n"
        f"Ancien statut : <s>{old_esc}</s>\n"
        f"Nouveau statut : <b>{new_esc}</b>\n\n"
        f"👨‍💼 <b>Opérateur en charge :</b> {alias_esc}\n\n"
        "Tapez /demandes pour afficher l'ensemble de vos demandes."
    )