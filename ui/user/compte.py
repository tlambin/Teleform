"""ui/user/compte.py
Composants visuels, textes et claviers pour le compte utilisateur et les préférences VIP.
"""

import html
from typing import Any, Dict, List, Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def build_vip_settings_content(
    current_pref: str,
    target_staff_alias: Optional[str] = None
) -> tuple[str, InlineKeyboardMarkup]:
    """Construit le texte descriptif et le clavier du menu des réglages d'attribution VIP."""
    is_prompt = (current_pref == "prompt")
    is_none = (current_pref == "none")
    is_specific = (not is_prompt and not is_none and current_pref.isdigit())

    btn_prompt = "✅ 📌 Demander à chaque création" if is_prompt else "📌 Demander à chaque création"
    btn_none = "✅ 🎲 Ne jamais choisir (Toute l'équipe)" if is_none else "🎲 Ne jamais choisir (Toute l'équipe)"

    specific_label = "🎯 Toujours assigner à un piégeur..."
    if is_specific and target_staff_alias:
        specific_label = f"✅ 🎯 Toujours assigner à : {target_staff_alias}"

    keyboard = [
        [InlineKeyboardButton(btn_prompt, callback_data="vip_set_assign_prompt")],
        [InlineKeyboardButton(btn_none, callback_data="vip_set_assign_none")],
        [InlineKeyboardButton(specific_label, callback_data="vip_pick_auto_staff")],
        [InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")]
    ]

    desc_mode = "📌 <b>Demander à chaque demande</b> (par défaut)"
    if is_none:
        desc_mode = "🎲 <b>Automatique (Sans piégeur attitré)</b> — Vos dossiers sont directement ouverts à toute l'équipe."
    elif is_specific and target_staff_alias:
        desc_mode = f"🎯 <b>Attribution directe :</b> {html.escape(str(target_staff_alias))} recevra directement chacune de vos créations."

    text = (
        "⚙️ <b>Préférences VIP : Attribution des demandes</b>\n\n"
        f"• <b>Mode actuel :</b> {desc_mode}\n\n"
        "<i>Choisissez comment vous souhaitez orienter vos nouvelles demandes :</i>"
    )
    return text, InlineKeyboardMarkup(keyboard)


def build_vip_staff_picker_content(
    equipe: List[Dict[str, Any]],
    current_user_id: int
) -> tuple[str, InlineKeyboardMarkup]:
    """Construit l'invite et la liste des boutons pour sélectionner un piégeur par défaut."""
    kb_rows = []

    for member in equipe:
        if int(member["user_id"]) == int(current_user_id):
            continue
        alias = member.get("alias", f"Staff_{member['user_id']}")
        kb_rows.append([
            InlineKeyboardButton(
                f"🦈 {alias}",
                callback_data=f"vip_set_assign_staff_{member['user_id']}"
            )
        ])

    kb_rows.append([InlineKeyboardButton("🔙 Retour", callback_data="menu_vip_settings")])

    text = (
        "🎯 <b>Définir un piégeur par défaut</b>\n\n"
        "Chaque nouvelle demande que vous créerez lui sera automatiquement assignée en priorité :\n"
        "<i>(Vous pourrez changer ce choix ou repasser en mode manuel à tout moment)</i>"
    )
    return text, InlineKeyboardMarkup(kb_rows)


def get_unrecognized_text_message() -> str:
    """Message par défaut envoyé lors de réceptions hors tunnel."""
    return (
        "🤖 Je n'ai pas compris votre message.\n"
        "Utilisez la commande /start ou les boutons de navigation pour interagir."
    )