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
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ RETOUR", callback_data="menu_mon_profil")]])
    return text, kb


def build_alias_prompt_content(
    target_alias: str,
    target_id: int,
    user_id: int,
    is_owner: bool
) -> tuple[str, InlineKeyboardMarkup]:
    """Construit l'invite de saisie du nouvel alias conforme à la maquette."""
    target_alias_esc = html.escape(str(target_alias))

    # Cas 1 : Le propriétaire modifie l'alias d'un autre membre
    if is_owner and target_id != user_id:
        text = (
            "👑 <b>MODIFICATION D'ALIAS (ADMIN)</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"Modification forcée pour le membre (ID : <code>{target_id}</code>).\n\n"
            f"• <b>Alias actuel :</b> {target_alias_esc}\n"
            "• <b>Limite :</b> 30 caractères maximum\n"
            "• <b>Contrainte :</b> Lettres, chiffres, espaces, tirets et underscores autorisés\n\n"
            "<i>Envoyez directement le nouvel alias dans le chat :</i>"
        )
        retour_btn = InlineKeyboardButton("❌ ANNULER", callback_data="gerer_staff")

    # Cas 2 : Modification de son propre alias
    else:
        text = (
            "🏷️ <b>MODIFIER MON ALIAS</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Configurez votre identifiant unique.\n\n"
            f"<b>Alias actuel :</b> {target_alias_esc}\n\n"
            "• <b>Limite :</b> 30 caractères maximum\n"
            "• <b>Contrainte :</b> Lettres, chiffres, espaces, tirets et underscores autorisés\n\n"
            "<i>Envoyez directement votre nouvel alias dans le chat :</i>"
        )
        retour_btn = InlineKeyboardButton("❌ ANNULER", callback_data="menu_mon_profil")

    keyboard = InlineKeyboardMarkup([[retour_btn]])
    return text, keyboard


def build_alias_success_content(
    new_alias: str,
    target_id: int,
    user_id: int,
    is_owner: bool
) -> tuple[str, InlineKeyboardMarkup]:
    """Construit le message de confirmation et le clavier de redirection."""
    new_alias_esc = html.escape(str(new_alias))

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
            InlineKeyboardButton("⬅️ MON PROFIL", callback_data="menu_mon_profil")
        ]])
        succes_msg = f"✅ <b>Alias mis à jour :</b> <code>{new_alias_esc}</code>{verrou_txt}"

    return succes_msg, retour_kb


def get_cancel_alias_content(is_owner: bool, target_id: int, user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Message et clavier d'annulation de changement d'alias."""
    if is_owner and target_id and target_id != user_id:
        callback_target = "gerer_staff"
        btn_label = "👥 Équipe Staff"
    else:
        callback_target = "menu_mon_profil"
        btn_label = "⬅️ MON PROFIL"

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