"""
Interface Manager - Gestionnaire centralisé des interfaces bot Telegram
Architecture modulaire selon les spécifications utilisateur
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

class InterfaceManager:
    """Gestionnaire centralisé des interfaces selon le rôle utilisateur"""

    def __init__(self, config, db_manager):
        """Initialisation avec accès config et base de données"""
        self.config = config
        self.db_manager = db_manager

    # ========== INTERFACE PRINCIPALE /start ==========

    def get_start_interface(self, user_id, first_name):
        """Interface /start adaptative selon le rôle"""
        user_role = self._get_user_role(user_id)

        # Message adaptatif selon le rôle
        if user_role == 'owner':
            welcome_msg = (
                f"👑 <b>Bienvenue {first_name}, le proriétaire !</b>\n\n"
                f"Choisis une action ci-dessous :"
            )
        elif user_role == 'admin':
            welcome_msg = (
                f"🦈 <b>Bienvenue {first_name}, le piègeur !</b>\n\n"
                f"Choisis une action ci-dessous :"
            )
        else:
            welcome_msg = (
                f"👋 <b>Salut {first_name} !</b>\n\n"
                f"Choisis une action ci-dessous :"
            )

        # Construction du clavier selon vos spécifications exactes
        keyboard = [
            # Boutons universels (côte à côte)
            [
                InlineKeyboardButton("🗳️ FAIRE UNE DEMANDE", callback_data="new_demande"),
                InlineKeyboardButton("🗂️ MES DEMANDES", callback_data="voir_demandes")
            ]
        ]

        # Boutons admin/owner
        if user_role in ['admin', 'owner']:
            keyboard.append([
                InlineKeyboardButton("☎️️ GÉRER LES DEMANDES", callback_data="gerer_demandes")
            ])
            keyboard.append([
                InlineKeyboardButton("⚙️ PARAMÈTRES", callback_data="parametres")
            ])

        return welcome_msg, InlineKeyboardMarkup(keyboard)

    # ========== SOUS-MENU GERER LES DEMANDES ==========

    def get_gerer_demandes_menu(self):
        """Sous-menu GERER LES DEMANDES"""
        message = "⚖️ <b>Gestion des Demandes</b>\n\nChoisissez une action :"

        keyboard = [
            [InlineKeyboardButton("📮 DEMANDES DISPONIBLES", callback_data="demandes_disponibles")],
            [InlineKeyboardButton("💌️ DEMANDES SUIVIES", callback_data="demandes_suivies")],
            [InlineKeyboardButton("🔙 Retour", callback_data="start_menu")]
        ]

        return message, InlineKeyboardMarkup(keyboard)

    # ========== SOUS-MENU PARAMETRES ==========

    def get_parametres_menu(self, user_id):
        """Sous-menu PARAMETRES selon le rôle"""
        user_role = self._get_user_role(user_id)

        if user_role == 'owner':
            message = "👑 <b>Paramètres Propriétaire</b>\n\nOptions disponibles :"
            keyboard = [
                [InlineKeyboardButton("🤖 GESTION DU BOT", callback_data="gerer_bot")],
                [InlineKeyboardButton("👥 ADMINISTRATION", callback_data="gerer_admins")],
                [InlineKeyboardButton("📊 STATISTIQUES", callback_data="bot_stats")],
                [InlineKeyboardButton("🏷️ MODIFIER L'ALIAS", callback_data="modifier_alias")],
                [InlineKeyboardButton("🔙 Retour", callback_data="start_menu")]
            ]
        else:  # admin
            message = "🦈 <b>Paramètres Administration</b>\n\nOptions disponibles :"
            keyboard = [
                [InlineKeyboardButton("🏷️ MODIFIER L'ALIAS", callback_data="modifier_alias")],
                [InlineKeyboardButton("🔙 Retour", callback_data="start_menu")]
            ]

        return message, InlineKeyboardMarkup(keyboard)

    # ========== SOUS-MENU GERER LES ADMINS (Owner Only) ==========

    def get_gerer_admins_menu(self):
        """Menu GERER LES ADMINS avec liste + actions"""
        try:
            # Récupération liste admins
            with self.db_manager.get_cursor() as cursor:
                cursor.execute("""
                    SELECT a.user_id, a.alias, a.first_name, a.username, a.date_added,
                           o.first_name as added_by_name
                    FROM admins a
                    LEFT JOIN admins o ON a.added_by = o.user_id
                    ORDER BY a.date_added DESC
                """)
                admins = cursor.fetchall()

            if not admins:
                message = "👥 <b>Gestion des Administrateurs</b>\n\n📊 Aucun administrateur configuré.\n\n"
            else:
                message = f"👥 <b>Gestion des Administrateurs</b> ({len(admins)})\n\n"

                for admin in admins:
                    username = f"@{admin['username']}" if admin['username'] else "Pas de username"
                    date_str = admin['date_added'].strftime('%d/%m/%Y')
                    added_by = admin['added_by_name'] if admin['added_by_name'] else "Propriétaire"

                    message += (
                        f"👤 <b>{admin['first_name']}</b> - <b>{admin['alias']}</b>\n"
                        f"📱 {username}\n"
                        f"🆔 ID: <code>{admin['user_id']}</code>\n"
                        f"📅 Ajouté le: {date_str} par {added_by}\n\n"
                    )

            # Boutons d'action
            keyboard = [
                [
                    InlineKeyboardButton("➕ AJOUTER", callback_data="admin_ajouter"),
                    InlineKeyboardButton("➖ SUPPRIMER", callback_data="admin_supprimer")
                ],
                [InlineKeyboardButton("🔙 Retour", callback_data="parametres")]
            ]

        except Exception:
            message = "👥 <b>Gestion des Administrateurs</b>\n\n❌ Erreur de récupération des données."
            keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="parametres")]]

        return message, InlineKeyboardMarkup(keyboard)

    # ========== SOUS-MENU GERER LE BOT (Owner Only) ==========

    def get_gerer_bot_menu(self):
        """Menu GERER LE BOT avec toggle dynamique"""
        try:
            bot_active = self.db_manager.is_bot_active()
        except Exception:
            bot_active = True

        if bot_active:
            status_icon = "🟢 ACTIVÉ"
            toggle_text = "🔴 DÉSACTIVER"
            toggle_callback = "bot_off"
        else:
            status_icon = "🔴 DÉSACTIVÉ"
            toggle_text = "🟢 ACTIVER"
            toggle_callback = "bot_on"

        message = (
            f"🤖 <b>Gestion du Bot</b>\n\n"
            f"📊 <b>Status demandes :</b> {status_icon}\n\n"
            f"⚙️ <b>Contrôles système :</b>"
        )

        keyboard = [
            [InlineKeyboardButton(f"{toggle_text} DEMANDES", callback_data=toggle_callback)],
            [InlineKeyboardButton("🛠️ MAINTENANCE", callback_data="maintenance")],
            [InlineKeyboardButton("🔙 Retour", callback_data="parametres")]
        ]

        return message, InlineKeyboardMarkup(keyboard)

    # ========== FONCTIONS UTILITAIRES ==========

    def _get_user_role(self, user_id):
        """Détermine le rôle de l'utilisateur"""
        if self.config.is_owner(user_id):
            return 'owner'
        elif self.config.is_admin(user_id):
            return 'admin'
        else:
            return 'user'

    def _get_admin_alias(self, user_id):
        """Récupère l'alias d'un admin"""
        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute("SELECT alias FROM admins WHERE user_id = %s", (user_id,))
                result = cursor.fetchone()
                return result['alias'] if result else "Admin"
        except Exception:
            return "Admin"

    # ========== ROUTER DE NAVIGATION ==========

    def route_callback(self, callback_data, user_id, first_name):
        """Router principal pour les callbacks d'interface"""
        routing_map = {
            "start_menu": lambda: self.get_start_interface(user_id, first_name),
            "gerer_demandes": lambda: self.get_gerer_demandes_menu(),
            "parametres": lambda: self.get_parametres_menu(user_id),
            "gerer_admins": lambda: self.get_gerer_admins_menu(),
            "gerer_bot": lambda: self.get_gerer_bot_menu()
        }

        handler = routing_map.get(callback_data)
        if handler:
            return handler()
        else:
            return None, None
