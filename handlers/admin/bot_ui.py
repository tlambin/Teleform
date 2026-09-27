"""Composants visuels, gabarits textuels et claviers pour la gestion opérationnelle du bot."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def get_bot_on_content() -> tuple[str, InlineKeyboardMarkup]:
    """Texte et clavier lors de l'activation globale du service."""
    text = (
        "🟢 <b>Bot opérationnel</b>\n\n"
        "✅ Les utilisateurs peuvent à nouveau créer des demandes et naviguer librement.\n"
        "📊 Toutes les commandes sont actives."
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔴 Suspendre", callback_data="bot_off")],
        [InlineKeyboardButton("🛠️ Maintenance", callback_data="maintenance")],
        [InlineKeyboardButton("🔙 Gestion Service", callback_data="gerer_bot")]
    ])
    return text, keyboard


def get_bot_off_content() -> tuple[str, InlineKeyboardMarkup]:
    """Texte et clavier lors de la suspension des demandes."""
    text = (
        "🔴 <b>Demandes suspendues</b>\n\n"
        "⏸️ Le service de création de demandes est désormais désactivé.\n"
        "🔒 L'équipe conserve ses accès pour traiter et clôturer les dossiers en cours."
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 Réactiver", callback_data="bot_on")],
        [InlineKeyboardButton("🛠️ Maintenance", callback_data="maintenance")],
        [InlineKeyboardButton("🔙 Gestion Service", callback_data="gerer_bot")]
    ])
    return text, keyboard


def get_bot_maintenance_content() -> tuple[str, InlineKeyboardMarkup]:
    """Texte et clavier lors du passage en mode maintenance."""
    text = (
        "🛠️ <b>Mode maintenance actif</b>\n\n"
        "⚙️ Le bot est verrouillé pour des interventions techniques.\n"
        "Seuls les comptes de direction sont habilités à exécuter des actions."
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 Réactiver le service", callback_data="bot_on")],
        [InlineKeyboardButton("🔙 Gestion Service", callback_data="gerer_bot")]
    ])
    return text, keyboard


def build_bot_status_content(is_active: bool, is_maint: bool) -> tuple[str, InlineKeyboardMarkup]:
    """Construit la fiche d'état courant et le clavier de pilotage."""
    if is_maint:
        badge = "🛠️ <b>Maintenance</b>"
        detail = "Accès restreint à la direction."
    elif is_active:
        badge = "🟢 <b>Actif</b>"
        detail = "Toutes les fonctions sont opérationnelles pour les utilisateurs."
    else:
        badge = "🔴 <b>Suspendu</b>"
        detail = "Les utilisateurs ne peuvent plus soumettre de formulaires."

    text = (
        "📊 <b>Statut Opérationnel du Service</b>\n\n"
        f"• <b>État :</b> {badge}\n"
        f"• <b>Détails :</b> {detail}"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🟢 Activer", callback_data="bot_on"),
            InlineKeyboardButton("🔴 Couper", callback_data="bot_off")
        ],
        [InlineKeyboardButton("🛠️ Maintenance", callback_data="maintenance")],
        [InlineKeyboardButton("🔙 Gestion Service", callback_data="gerer_bot")]
    ])
    return text, keyboard