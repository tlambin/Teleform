"""Composants visuels, gabarits textuels et claviers pour le protocole de purge."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

LABELS = {
    "archives": "des archives",
    "demandes": "des demandes",
    "users": "des utilisateurs",
    "staff": "du staff",
    "admins": "des administrateurs",
    "config": "de configuration (config)",
    "totale": "TOTALE (de toute la base de données)",
}


def get_step1_confirmation_content(target: str) -> tuple[str, InlineKeyboardMarkup]:
    """Construit le texte et les boutons de la première étape de confirmation."""
    libelle = LABELS.get(target, target)

    text = (
        f"🚨 <b>CONFIRMATION REQUISE</b>\n\n"
        f"Êtes-vous sûr de vouloir effacer la table <b>{libelle}</b> ?\n\n"
        "Cette action est <b>absolument irréversible</b>."
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ OUI, continuer", callback_data=f"danger_confirm_yes_{target}")],
        [InlineKeyboardButton("❌ NON, annuler", callback_data="menu_danger_zone")],
    ])
    return text, kb


def get_step2_text_confirmation_content(target: str) -> tuple[str, InlineKeyboardMarkup]:
    """Construit le texte de l'étape de saisie stricte du mot 'Effacer'."""
    text = (
        "✍️ <b>Dernière étape de sécurité</b>\n\n"
        f"Cible : <code>{target}</code>\n\n"
        "Pour valider définitivement la suppression, veuillez <b>taper exactement au clavier le mot</b> :\n"
        "<code>Effacer</code>\n\n"
        "<i>(Envoyez n'importe quel autre message ou cliquez ci-dessous pour annuler).</i>"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="menu_danger_zone")]])
    return text, kb


def get_purge_result_content(success: bool, target: str, is_canceled: bool = False) -> tuple[str, InlineKeyboardMarkup]:
    """Génère le message d'issue de la purge et le bouton de retour."""
    if is_canceled:
        msg = "❌ <b>Suppression annulée :</b> Le mot de confirmation n'était pas exactement 'Effacer'."
    elif success:
        msg = (
            f"✅ <b>Purge de la cible « {target} » exécutée avec succès !</b>\n\n"
            "La base de données a été mise à jour et le cache a été nettoyé."
        )
    else:
        msg = f"❌ <b>Échec lors de la purge de « {target} ».</b> Consultez les logs d'erreurs."

    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ RETOUR", callback_data="menu_danger_zone")]])
    return msg, kb