"""Composants visuels, gabarits textuels et claviers pour la gestion des membres et bannissements."""

import html
from typing import List, Dict, Any
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from utils.interface_manager import format_datetime_fr


def get_search_prompt_content() -> tuple[str, InlineKeyboardMarkup]:
    """Texte et clavier d'invite pour la recherche d'un membre."""
    text = (
        "🔍 <b>RECHERCHER UN MEMBRE</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "Envoyez ci-dessous son <b>ID Telegram numérique</b> ou son <b>@pseudo</b> :\n\n"
        "<i>Exemples : <code>123456789</code> ou <code>@nom_utilisateur</code></i>"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ ANNULER", callback_data="menu_membres")]])
    return text, kb


def get_member_not_found_content() -> tuple[str, InlineKeyboardMarkup]:
    """Message d'erreur et clavier lorsque le membre n'existe pas en base."""
    text = "❌ <b>Membre introuvable.</b>\nL'utilisateur doit avoir démarré le bot au moins une fois."
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 RÉESSAYER", callback_data="search_member_prompt")],
        [InlineKeyboardButton("⬅️ RETOUR", callback_data="menu_membres")],
    ])
    return text, kb


def build_banned_list_content(bannis: List[Dict[str, Any]], total: int, page: int, limit: int) -> tuple[str, InlineKeyboardMarkup]:
    """Construit l'affichage de la liste des bannis et son clavier de pagination/débannissement."""
    lines = [
        f"🚫 <b>LISTE DES COMPTES BANNIS ({total})</b>",
        "━━━━━━━━━━━━━━━━━━━━━━\n",
    ]
    keyboard = []

    if not bannis:
        lines.append("<i>Aucun compte banni sur la plateforme.</i>")
    else:
        for b in bannis:
            u_id = b["user_id"]
            pseudo = f"@{b['username']}" if b.get("username") else "Sans pseudo"
            nom = html.escape(str(b.get("first_name") or pseudo))
            par_qui = html.escape(str(b.get("admin_alias") or f"Admin_{b.get('banned_by')}"))
            dt_str = format_datetime_fr(b.get("date_ban"))
            raison = html.escape(str(b.get("reason") or "Non spécifiée"))

            lines.append(
                f"• <b>{nom}</b> (<code>{u_id}</code>)\n"
                f"  Banni le {dt_str} par {par_qui}\n"
                f"  <i>Motif : {raison}</i>\n"
            )
            keyboard.append([InlineKeyboardButton(f"🟢 DÉBANNIR {nom.upper()[:15]}", callback_data=f"unban_from_list_{u_id}")])

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ PRÉCÉDENT", callback_data=f"liste_bannis_{page - 1}"))
    if (page * limit + limit) < total:
        nav_row.append(InlineKeyboardButton("SUIVANT ➡️", callback_data=f"liste_bannis_{page + 1}"))
    if nav_row:
        keyboard.append(nav_row)

    keyboard.append([InlineKeyboardButton("⬅️ RETOUR", callback_data="menu_membres")])
    return "\n".join(lines), InlineKeyboardMarkup(keyboard)


def get_ban_reason_prompt_content(target_id: int, is_staff: bool, origin_demande_id: int = 0) -> tuple[str, InlineKeyboardMarkup]:
    """Invite de saisie pour le motif de bannissement."""
    role_str = "Piégeur (Staff)" if is_staff else "Utilisateur (Client)"
    text = (
        f"🚫 <b>Bannissement d'un compte : {role_str}</b>\n"
        f"🆔 ID Cible : <code>{target_id}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Veuillez envoyer au clavier la <b>raison du bannissement</b> :\n"
        "<i>(Tapez 'Passer' ou 'Non' pour ne spécifier aucun motif particulier).</i>"
    )
    back_cb = f"staff_view_demandes_{target_id}" if is_staff else (f"profil_demande_{origin_demande_id}" if origin_demande_id else "menu_membres")
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ ANNULER", callback_data=back_cb)]])
    return text, kb


def get_ban_notification_message(reason: str) -> str:
    """Message transmis au compte banni."""
    return (
        "🚫 <b>VOTRE COMPTE A ÉTÉ BANNI</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "L'accès aux services de la plateforme vous a été révoqué par la direction.\n"
        f"• <b>Motif :</b> <i>{html.escape(reason)}</i>\n\n"
        "Si vous pensez qu'il s'agit d'une erreur, vous pouvez contacter le support."
    )


def build_ban_success_content(target_id: int, reason: str, is_staff: bool) -> tuple[str, InlineKeyboardMarkup]:
    """Message de confirmation à l'administrateur ayant exécuté le ban."""
    role_str = "Piégeur" if is_staff else "Utilisateur"
    text = (
        f"✅ <b>{role_str} banni avec succès !</b>\n\n"
        f"• <b>ID Cible :</b> <code>{target_id}</code>\n"
        f"• <b>Motif enregistré :</b> <i>{html.escape(reason)}</i>"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("👥 GESTION DES MEMBRES", callback_data="menu_membres")]])
    return text, kb