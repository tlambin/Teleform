"""ui/user/compte.py
Composants visuels, textes et claviers pour le compte utilisateur et les préférences VIP.
"""

import html
from typing import Any, Dict, List, Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


# ==================== ACCUEIL & MENUS PRINCIPAUX ====================

def build_start_interface(user_id: int, first_name: str, user_role: str, is_vip: bool) -> tuple[str, InlineKeyboardMarkup]:
    """Construit l'interface d'accueil adaptée au statut de l'utilisateur."""
    first_name_esc = html.escape(str(first_name or "Utilisateur"))

    if user_role == "owner":
        header = "👑 PARABAIT 👑"
        subtitle = f"Bienvenue {first_name_esc} - <i>propriétaire</i>"
    elif user_role == "admin":
        header = "🧠 PARABAIT 🧠"
        subtitle = f"Bienvenue {first_name_esc} - <i>administrateur</i>"
    elif user_role == "staff":
        header = "🎣 PARABAIT 🎣"
        subtitle = f"Bienvenue {first_name_esc} - <i>piégeur</i>"
    elif is_vip:
        header = "★ PARABAIT ★"
        subtitle = f"Bienvenue {first_name_esc} - <i>VIP</i>"
    else:
        header = "✨ PARABAIT ✨"
        subtitle = f"Bienvenue {first_name_esc}"

    welcome_msg = (
        f"<b>{header}</b>\n\n"
        f"<b>{subtitle}</b>\n\n"
        "<i>Sélectionnez une option ci-dessous pour continuer :</i>"
    )

    keyboard = [
        [
            InlineKeyboardButton("🗳️ CRÉER", callback_data="new_demande"),
            InlineKeyboardButton("🗂️ MES DEMANDES", callback_data="voir_demandes"),
        ]
    ]

    if user_role in ["staff", "admin", "owner"]:
        keyboard.append([
            InlineKeyboardButton("🚦 GÉRER LES DEMANDES 🚦", callback_data="gerer_demandes")
        ])

    if not is_vip and user_role == "user":
        keyboard.append([
            InlineKeyboardButton("⭐ DEVENIR VIP ⭐", callback_data="menu_vip_shop")
        ])

    keyboard.append([
        InlineKeyboardButton("⚙️ PARAMÈTRES ⚙️", callback_data="parametres")
    ])

    return welcome_msg, InlineKeyboardMarkup(keyboard)


def build_client_parametres_menu(user_id: int, is_vip: bool, support_contact: str) -> tuple[str, InlineKeyboardMarkup]:
    """Construit le panneau Paramètres spécifique aux clients / demandeurs."""
    vip_mention = " <i>(Abonné VIP)</i>" if is_vip else ""
    message = (
        f"⚙️ <b>PARAMÈTRES DU COMPTE{vip_mention}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Gérez vos options, abonnements et assistance :"
    )
    keyboard = []
    if is_vip:
        keyboard.append([InlineKeyboardButton("✨ PRÉFÉRENCES VIP ✨", callback_data="menu_vip_settings")])
    else:
        keyboard.append([InlineKeyboardButton("⭐ DEVENIR VIP ⭐", callback_data="menu_vip_shop")])

    if support_contact.startswith("@"):
        support_url = f"https://t.me/{support_contact.lstrip('@')}"
    elif support_contact.startswith(("http://", "https://")):
        support_url = support_contact
    else:
        support_url = f"https://t.me/{support_contact}"

    keyboard.append([InlineKeyboardButton("🎧 CONTACTER LE SUPPORT", url=support_url)])
    keyboard.append([InlineKeyboardButton("⬅️ RETOUR", callback_data="start_menu")])
    return message, InlineKeyboardMarkup(keyboard)


def build_vip_shop_menu(is_vip: bool = False) -> tuple[str, InlineKeyboardMarkup]:
    """Affiche l'offre d'abonnement VIP mensuel payable en Telegram Stars."""
    message = (
        "⭐ <b>ADHÉSION AU STATUT VIP</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Débloquez l'ensemble des privilèges premium pour <b>30 jours</b> :\n\n"
        "• 🚀 <b>Demandes illimitées :</b> Dépassement complet des plafonds habituels.\n"
        "• 🎯 <b>Choix du référent :</b> Choisissez l'opérateur attitré à vos dossiers.\n"
        "• 💬 <b>Ligne directe :</b> Canal d'échange instantané avec votre opérateur.\n"
        "• 🔔 <b>Relances prioritaires :</b> Notification directe en cas d'attente prolongée.\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "💳 <i>Paiement sécurisé instantané en Telegram Stars.</i>"
    )
    keyboard = []
    if is_vip:
        keyboard.append([
            InlineKeyboardButton("✨ PRÉFÉRENCES VIP ✨", callback_data="menu_vip_settings")
        ])

    keyboard.extend([
        [InlineKeyboardButton("⭐ S'abonner pour 30 jours (250 ⭐️)", callback_data="buy_vip_month")],
        [InlineKeyboardButton("⬅️ RETOUR", callback_data="parametres")],
    ])
    return message, InlineKeyboardMarkup(keyboard)


# ==================== RÉGLAGES ATTRIBUTION VIP ====================

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
    
# ==================== ADHÉSION OBLIGATOIRE & ACCÈS ====================

def get_required_membership_content(sub_url: str) -> tuple[str, InlineKeyboardMarkup]:
    """Construit l'invite et les boutons pour l'obligation de rejoindre le groupe."""
    msg_text = (
        "📢 <b>Adhésion requise</b>\n\n"
        "Pour accéder aux services du bot et déposer vos demandes, vous devez obligatoirement rejoindre notre groupe.\n\n"
        "Cliquez sur le bouton ci-dessous pour vous inscrire via le bot dédié, puis cliquez sur <b>Vérifier mon adhésion</b> :"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✍️ S'INSCRIRE AU GROUPE ✍️", url=sub_url)],
        [InlineKeyboardButton("🔄 VÉRIFIER MON ADHÉSION 🔄", callback_data="check_subscription")],
    ])
    return msg_text, keyboard


def get_service_disabled_content() -> tuple[str, InlineKeyboardMarkup]:
    """Message et clavier quand le service de dépôt est désactivé."""
    text = (
        "🚫 <b>Service temporairement indisponible</b>\n\n"
        "La création et la navigation des demandes sont actuellement désactivées par l'administration."
    )
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔙 MENU PRINCIPAL 🔙", callback_data="start_menu")
    ]])
    return text, keyboard


def get_quota_reached_content(reason_msg: str) -> tuple[str, InlineKeyboardMarkup]:
    """Clavier proposé lorsque le quota de demandes actives est atteint."""
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ PASSER VIP ⭐", callback_data="menu_vip_shop")],
        [InlineKeyboardButton("🔙 MENU PRINCIPAL 🔙", callback_data="start_menu")],
    ])
    return reason_msg, keyboard