"""Composants visuels, gabarits textuels et claviers pour la gestion des privilèges VIP."""

import html
from typing import List, Dict, Any, Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def get_vip_add_prompt_content() -> tuple[str, InlineKeyboardMarkup]:
    """Invite de saisie pour identifier le compte à promouvoir VIP."""
    text = "⭐ <b>Promouvoir un Membre VIP</b>\n\nEnvoyez l'<b>ID numérique</b> ou le <b>@username</b> du compte :"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="cancel_vip_action")]])
    return text, kb


def build_vip_duration_choice_content(u_data: dict) -> tuple[str, InlineKeyboardMarkup]:
    """Propose le choix de durée d'abonnement pour le compte cible."""
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ 1 Mois (30 jours)", callback_data="vip_dur_30")],
        [InlineKeyboardButton("⭐ 3 Mois (90 jours)", callback_data="vip_dur_90")],
        [InlineKeyboardButton("👑 À Vie (Illimité)", callback_data="vip_dur_lifetime")],
        [InlineKeyboardButton("❌ Annuler", callback_data="cancel_vip_action")],
    ])
    nom = html.escape(str(u_data.get("first_name") or u_data.get("username") or u_data["user_id"]))
    text = f"👤 Cible : <b>{nom}</b>\n\nChoisissez la durée ou tapez le nombre de jours :"
    return text, kb


def get_vip_granted_notification(duration_days: Optional[int]) -> str:
    """Notification félicitant le membre pour l'obtention de son statut VIP."""
    type_str = f"pendant {duration_days} jours" if duration_days else "à vie"
    return f"🎉 <b>Félicitations ! Votre accès VIP ({type_str}) est activé !</b>"


def build_vip_grant_success_content(target_name: str, duration_days: Optional[int]) -> tuple[str, InlineKeyboardMarkup]:
    """Message de confirmation envoyé à l'administrateur ayant accordé le statut VIP."""
    dur_txt = f"{duration_days} jours" if duration_days else "À vie"
    nom_esc = html.escape(str(target_name))
    text = f"✅ Statut VIP activé pour {nom_esc} ({dur_txt}) !"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ RETOUR", callback_data="gerer_vips")]])
    return text, kb


def build_vip_remove_list_content(vips: List[Dict[str, Any]]) -> tuple[str, InlineKeyboardMarkup]:
    """Affiche la liste numérotée des membres VIP actifs pour sélection de révocation."""
    if not vips:
        text = "📭 Aucun membre VIP actif."
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ RETOUR", callback_data="gerer_vips")]])
        return text, kb

    lines = ["⭐ <b>Révocation Membre VIP</b>\n"]
    for idx, v in enumerate(vips, 1):
        nom = html.escape(str(v.get("first_name") or "Utilisateur"))
        lines.append(f"{idx}. <b>{nom}</b> (<code>{v['user_id']}</code>)")

    lines.append("\nEnvoyez le <b>numéro</b> de la personne à révoquer :")
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="cancel_vip_action")]])
    return "\n".join(lines), kb


def build_vip_revoked_success_content(target_name: str) -> tuple[str, InlineKeyboardMarkup]:
    """Confirmation de révocation du statut VIP."""
    nom_esc = html.escape(str(target_name))
    text = f"✅ <b>Statut VIP révoqué pour {nom_esc}.</b>"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ RETOUR", callback_data="gerer_vips")]])
    return text, kb