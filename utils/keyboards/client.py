"""Constructeur des menus et interfaces orientés demandeurs / clients."""

import html
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


class ClientKeyboards:
    """Génère les vues d'accueil, paramètres client et boutique VIP."""

    def __init__(self, config, db_manager, role_resolver):
        self.config = config
        self.db_manager = db_manager
        self._get_user_role = role_resolver

    def get_start_interface(self, user_id: int, first_name: str):
        """Construit l'interface d'accueil adaptée au statut de l'utilisateur."""
        user_role = self._get_user_role(user_id)
        is_vip = self.db_manager.is_user_vip(user_id)
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

    def get_client_parametres_menu(self, user_id: int):
        """Construit le panneau Paramètres spécifique aux clients / demandeurs."""
        is_vip = self.db_manager.is_user_vip(user_id)
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

        support_link = self.db_manager.get_support_contact()
        if support_link.startswith("@"):
            support_url = f"https://t.me/{support_link.lstrip('@')}"
        elif support_link.startswith(("http://", "https://")):
            support_url = support_link
        else:
            support_url = f"https://t.me/{support_link}"

        keyboard.append([InlineKeyboardButton("🎧 CONTACTER LE SUPPORT", url=support_url)])
        keyboard.append([InlineKeyboardButton("⬅️ RETOUR", callback_data="start_menu")])
        return message, InlineKeyboardMarkup(keyboard)

    def get_vip_shop_menu(self, is_vip: bool = False):
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