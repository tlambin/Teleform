"""Composants visuels, gabarits textuels et claviers pour la configuration dynamique."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def get_delais_menu_content(hours: int, days: int, pay_days: int, remun_days: int) -> tuple[str, InlineKeyboardMarkup]:
    """Construit la vue principale de gestion des délais paramétrables."""
    text = (
        "⏳ <b>CONFIGURATION DES DÉLAIS DU SYSTÈME</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• 📦 <b>Auto-archivage post-livraison :</b> <code>{hours}h</code>\n"
        f"• 🚚 <b>Rappel livraison (Staff) :</b> <code>{days} jours</code>\n"
        f"• 💰 <b>Rappel impayé (Demandeur) :</b> <code>{pay_days} jours</code>\n"
        f"• ⏳ <b>Délai réponse rémunération :</b> <code>{remun_days} jours</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<i>Cliquez sur une option pour modifier sa valeur :</i>"
    )
    keyboard = [
        [
            InlineKeyboardButton(f"📦 Auto-archivage ({hours}h)", callback_data="cfg_sub_archive_hours"),
            InlineKeyboardButton(f"🚚 Rappel Livraison ({days}j)", callback_data="cfg_sub_reminder_days")
        ],
        [
            InlineKeyboardButton(f"💰 Rappel Impayé Client ({pay_days}j)", callback_data="cfg_sub_payrem_days"),
            InlineKeyboardButton(f"⏳ Délai Rémunération ({remun_days}j)", callback_data="cfg_sub_remun_days")
        ],
        [InlineKeyboardButton("⬅️ RETOUR", callback_data="gerer_bot")]
    ]
    return text, InlineKeyboardMarkup(keyboard)


def get_archive_hours_content(current: int) -> tuple[str, InlineKeyboardMarkup]:
    """Sous-menu de sélection du délai d'auto-archivage."""
    def b_lbl(name: str, val: int) -> str:
        return f"✅ {name}" if current == val else name

    keyboard = [
        [
            InlineKeyboardButton(b_lbl("24h (1j)", 24), callback_data="set_arch_hours_24"),
            InlineKeyboardButton(b_lbl("48h (2j)", 48), callback_data="set_arch_hours_48"),
        ],
        [
            InlineKeyboardButton(b_lbl("72h (3j)", 72), callback_data="set_arch_hours_72"),
            InlineKeyboardButton(b_lbl("168h (7j)", 168), callback_data="set_arch_hours_168"),
        ],
        [InlineKeyboardButton("⬅️ RETOUR", callback_data="menu_delais")]
    ]
    text = (
        "📦 <b>Délai d'auto-archivage</b>\n\n"
        f"Actuel : <b>{current} heures</b> post-livraison avant archivage automatique."
    )
    return text, InlineKeyboardMarkup(keyboard)


def get_reminder_days_content(current: int) -> tuple[str, InlineKeyboardMarkup]:
    """Sous-menu de sélection du délai de relance de livraison staff."""
    def b_lbl(name: str, val: int) -> str:
        return f"✅ {name}" if current == val else name

    keyboard = [
        [
            InlineKeyboardButton(b_lbl("3 jours", 3), callback_data="set_rem_days_3"),
            InlineKeyboardButton(b_lbl("5 jours", 5), callback_data="set_rem_days_5"),
        ],
        [
            InlineKeyboardButton(b_lbl("7 jours", 7), callback_data="set_rem_days_7"),
            InlineKeyboardButton(b_lbl("14 jours", 14), callback_data="set_rem_days_14"),
        ],
        [InlineKeyboardButton("⬅️ RETOUR", callback_data="menu_delais")]
    ]
    text = (
        "🚚 <b>Délai de relance pour contenu non livré (Staff)</b>\n\n"
        f"Actuel : <b>{current} jours</b>."
    )
    return text, InlineKeyboardMarkup(keyboard)


def get_payment_reminder_days_content(current: int) -> tuple[str, InlineKeyboardMarkup]:
    """Sous-menu de sélection de la fréquence de rappel d'impayé client."""
    def b_lbl(name: str, val: int) -> str:
        return f"✅ {name}" if current == val else name

    keyboard = [
        [
            InlineKeyboardButton(b_lbl("3 jours", 3), callback_data="set_payrem_days_3"),
            InlineKeyboardButton(b_lbl("5 jours", 5), callback_data="set_payrem_days_5"),
        ],
        [
            InlineKeyboardButton(b_lbl("7 jours", 7), callback_data="set_payrem_days_7"),
            InlineKeyboardButton(b_lbl("14 jours", 14), callback_data="set_payrem_days_14"),
        ],
        [InlineKeyboardButton("⬅️ RETOUR", callback_data="menu_delais")]
    ]
    text = (
        "💰 <b>Fréquence du rappel d'impayé (Demandeur)</b>\n\n"
        f"Actuelle : Tous les <b>{current} jours</b>."
    )
    return text, InlineKeyboardMarkup(keyboard)


def get_remun_expiration_days_content(current: int) -> tuple[str, InlineKeyboardMarkup]:
    """Sous-menu de sélection du délai de réponse pour la rémunération."""
    def b_lbl(name: str, val: int) -> str:
        return f"✅ {name}" if current == val else name

    keyboard = [
        [
            InlineKeyboardButton(b_lbl("3 jours", 3), callback_data="set_remun_days_3"),
            InlineKeyboardButton(b_lbl("5 jours", 5), callback_data="set_remun_days_5"),
        ],
        [
            InlineKeyboardButton(b_lbl("7 jours", 7), callback_data="set_remun_days_7"),
            InlineKeyboardButton(b_lbl("14 jours", 14), callback_data="set_remun_days_14"),
        ],
        [InlineKeyboardButton("⬅️ RETOUR", callback_data="menu_delais")]
    ]
    text = (
        "⏳ <b>Délai avant abandon pour non-réponse à la rémunération</b>\n\n"
        f"Actuel : <b>{current} jours</b>.\n\n"
        "<i>Passé ce délai sans réponse du demandeur, la demande sera classée sous « ❌ Abandonnée » avec explication.</i>"
    )
    return text, InlineKeyboardMarkup(keyboard)