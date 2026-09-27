"""Composants visuels, gabarits textuels et claviers pour la navigation du formulaire."""

from typing import List, Dict, Any
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

NAV_CONFIG = {
    "back_text": "⬅️ Retour",
    "skip_text": "⏭️ Passer",
    "cancel_text": "❌ Annuler",
}


def create_navigation_keyboard(current_state: int, state_history: dict, skippable_fields: set, include_skip: bool = False) -> InlineKeyboardMarkup:
    """Construit le clavier dynamique adapté à l'étape courante."""
    keyboard = []
    action_row = []

    if current_state in state_history:
        action_row.append(
            InlineKeyboardButton(
                NAV_CONFIG["back_text"],
                callback_data=f"form_back_{current_state}",
            )
        )

    if include_skip and current_state in skippable_fields:
        action_row.append(
            InlineKeyboardButton(
                NAV_CONFIG["skip_text"],
                callback_data=f"form_skip_{current_state}",
            )
        )

    if action_row:
        keyboard.append(action_row)

    keyboard.append([
        InlineKeyboardButton(
            NAV_CONFIG["cancel_text"],
            callback_data="form_cancel",
        )
    ])

    return InlineKeyboardMarkup(keyboard)


def create_priority_keyboard(prioritaire_state: int, include_navigation: bool = True) -> InlineKeyboardMarkup:
    """Clavier pour le choix Standard vs Prioritaire."""
    keyboard = [
        [InlineKeyboardButton("⭐ Oui - Prioritaire", callback_data="priorite_oui")],
        [InlineKeyboardButton("📝 Non - Standard", callback_data="priorite_non")],
    ]
    if include_navigation:
        keyboard.append([
            InlineKeyboardButton(
                NAV_CONFIG["back_text"],
                callback_data=f"form_back_{prioritaire_state}",
            ),
            InlineKeyboardButton(
                NAV_CONFIG["cancel_text"],
                callback_data="form_cancel",
            ),
        ])
    return InlineKeyboardMarkup(keyboard)


def create_vip_admin_choice_keyboard(
    equipe: List[Dict[str, Any]],
    target_ori: str,
    choix_admin_state: int,
    db_manager
) -> InlineKeyboardMarkup:
    """Génère la liste dynamique des référents Staff compatibles pour le membre VIP."""
    kb_rows = []

    for member in equipe:
        raw_alias = member.get("alias") or f"Staff_{member['user_id']}"
        perms = db_manager.get_staff_permissions(member["user_id"])
        p_ori = perms.get("perm_orientation", "all")

        is_compatible = (
            p_ori in ("all", "bi")
            or p_ori == target_ori
            or (target_ori == "bi" and p_ori in ("hetero", "gay"))
        )

        if is_compatible:
            kb_rows.append([
                InlineKeyboardButton(
                    f"🦈 {raw_alias}",
                    callback_data=f"vip_assign_admin_{member['user_id']}"
                )
            ])

    kb_rows.append([InlineKeyboardButton("🎲 Premier disponible (Aléatoire)", callback_data="vip_assign_admin_0")])
    kb_rows.append([
        InlineKeyboardButton(NAV_CONFIG["back_text"], callback_data=f"form_back_{choix_admin_state}"),
        InlineKeyboardButton(NAV_CONFIG["cancel_text"], callback_data="form_cancel")
    ])
    return InlineKeyboardMarkup(kb_rows)


def get_mandatory_network_keyboard(snapchat_state: int) -> InlineKeyboardMarkup:
    """Clavier affiché si l'utilisateur tente d'ignorer les deux réseaux."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Retourner à Instagram", callback_data=f"form_back_{snapchat_state}")],
        [InlineKeyboardButton("❌ Annuler la demande", callback_data="form_cancel")]
    ])


def get_back_screens_dict(form, has_insta: bool, target_ori: str) -> dict:
    """Dictionnaire des textes et claviers lors d'un retour arrière sur chaque étape."""
    return {
        form.ORIENTATION: {
            "text": (
                "🎯 <b>Retour — Orientation de la cible</b>\n\n"
                "Quelle est l'<b>orientation de la cible</b> ou le type de piège souhaité ?"
            ),
            "keyboard": form._get_orientation_keyboard(),
        },
        form.PRENOM: {
            "text": "📝 <b>Retour — Prénom</b>\n\nQuel est son <b>prénom</b> ?",
            "keyboard": create_navigation_keyboard(form.PRENOM, form.state_history, form.skippable_fields),
        },
        form.NOM: {
            "text": "📝 <b>Retour — Nom</b>\n\nSon nom de famille :",
            "keyboard": create_navigation_keyboard(form.NOM, form.state_history, form.skippable_fields, include_skip=True),
        },
        form.AGE: {
            "text": "📝 <b>Retour — Âge</b>\n\nSon âge (18-40 ans) :",
            "keyboard": create_navigation_keyboard(form.AGE, form.state_history, form.skippable_fields),
        },
        form.LOCALISATION: {
            "text": "📝 <b>Retour — Localisation</b>\n\nSa localisation (ville, région ou pays) :",
            "keyboard": create_navigation_keyboard(form.LOCALISATION, form.state_history, form.skippable_fields),
        },
        form.PHOTO: {
            "text": "📝 <b>Retour — Photo</b>\n\n📸 Envoyez une photo :",
            "keyboard": create_navigation_keyboard(form.PHOTO, form.state_history, form.skippable_fields),
        },
        form.INSTAGRAM: {
            "text": "📝 <b>Retour — Instagram</b>\n\nSon profil Instagram :",
            "keyboard": create_navigation_keyboard(form.INSTAGRAM, form.state_history, form.skippable_fields, include_skip=True),
        },
        form.SNAPCHAT: {
            "text": (
                "📝 <b>Retour — Snapchat</b>\n\n"
                + ("Son compte Snapchat (ou passez) :" if has_insta else "⚠️ <b>Au moins un réseau est requis.</b>\nSon compte Snapchat :")
            ),
            "keyboard": create_navigation_keyboard(form.SNAPCHAT, form.state_history, form.skippable_fields, include_skip=has_insta),
        },
        form.DETAILS: {
            "text": "📝 <b>Retour — Détails</b>\n\nDes précisions ou remarques à apporter ?",
            "keyboard": create_navigation_keyboard(form.DETAILS, form.state_history, form.skippable_fields, include_skip=True),
        },
        form.PRIORITAIRE: {
            "text": (
                "📝 <b>Retour — Priorité</b>\n\n"
                "💎 <b>Demande prioritaire ?</b>\n\n"
                "Les demandes prioritaires nécessitent un montant et sont traitées en premier."
            ),
            "keyboard": create_priority_keyboard(form.PRIORITAIRE),
        },
        form.MONTANT: {
            "text": "💰 <b>Retour — Montant</b>\n\nIndiquez le montant (en euros) :",
            "keyboard": create_navigation_keyboard(form.MONTANT, form.state_history, form.skippable_fields),
        },
        form.CHOIX_ADMIN: {
            "text": (
                "⭐ <b>Avantage Membre VIP : Choix du Référent</b>\n\n"
                "Sélectionnez le membre de l'équipe qui prendra personnellement en charge votre demande :"
            ),
            "keyboard": create_vip_admin_choice_keyboard(
                form.db_manager.get_available_staff(),
                target_ori,
                form.CHOIX_ADMIN,
                form.db_manager
            ),
        },
    }