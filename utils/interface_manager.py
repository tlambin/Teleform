"""Interface Manager - Gestionnaire centralisé des claviers et menus du bot."""

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)


class InterfaceManager:
    """Gestionnaire centralisé des interfaces adaptées aux rôles utilisateur."""

    def __init__(self, config, db_manager):
        self.config = config
        self.db_manager = db_manager

    # ========== INTERFACE PRINCIPALE /start ==========

    def get_start_interface(self, user_id: int, first_name: str):
        """Construit l'interface d'accueil selon le rôle de l'utilisateur."""
        user_role = self._get_user_role(user_id)

        if user_role == "owner":
            welcome_msg = (
                f"👑 <b>Bienvenue {first_name}, Propriétaire !</b>\n\n"
                "Sélectionnez une action ci-dessous :"
            )
        elif user_role == "admin":
            alias = self.db_manager.get_admin_alias(user_id)
            welcome_msg = (
                f"🦈 <b>Bienvenue {alias} !</b>\n\n"
                "Sélectionnez une action ci-dessous :"
            )
        else:
            welcome_msg = (
                f"👋 <b>Bonjour {first_name} !</b>\n\n"
                "Sélectionnez une option pour continuer :"
            )

        # Clavier utilisateur de base
        keyboard = [
            [
                InlineKeyboardButton("🗳️ FAIRE UNE DEMANDE", callback_data="new_demande"),
                InlineKeyboardButton("🗂️ MES DEMANDES", callback_data="voir_demandes")
            ]
        ]

        # Raccourcis de gestion pour l'équipe
        if user_role in ["admin", "owner"]:
            keyboard.append([
                InlineKeyboardButton("📋 GÉRER LES DEMANDES", callback_data="gerer_demandes")
            ])
            keyboard.append([
                InlineKeyboardButton("⚙️ PARAMÈTRES", callback_data="parametres")
            ])

        return welcome_msg, InlineKeyboardMarkup(keyboard)

    # ========== SOUS-MENU GÉRER LES DEMANDES ==========

    def get_gerer_demandes_menu(self):
        """Affiche le menu de traitement des demandes pour l'équipe."""
        message = "📋 <b>Gestion des Demandes</b>\n\nChoisissez une file de traitement :"
        keyboard = [
            [InlineKeyboardButton("📮 DEMANDES DISPONIBLES", callback_data="demandes_disponibles")],
            [InlineKeyboardButton("💌 DEMANDES SUIVIES", callback_data="demandes_suivies")],
            [InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")]
        ]
        return message, InlineKeyboardMarkup(keyboard)

    # ========== SOUS-MENU PARAMÈTRES ==========

    def get_parametres_menu(self, user_id: int):
        """Construit le panneau de configuration selon le rôle."""
        user_role = self._get_user_role(user_id)

        if user_role == "owner":
            message = "👑 <b>Paramètres Propriétaire</b>\n\nOptions d'administration globale :"
            keyboard = [
                [InlineKeyboardButton("🤖 GESTION DU SERVICE", callback_data="gerer_bot")],
                [InlineKeyboardButton("👥 ÉQUIPE D'ADMINISTRATION", callback_data="gerer_admins")],
                [InlineKeyboardButton("📊 STATISTIQUES GLOBALES", callback_data="bot_stats")],
                [InlineKeyboardButton("🏷️ MODIFIER MON ALIAS", callback_data="modifier_alias")],
                [InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")]
            ]
        else:
            message = "🦈 <b>Paramètres Administrateur</b>\n\nOptions disponibles :"
            keyboard = [
                [InlineKeyboardButton("🏷️ MODIFIER MON ALIAS", callback_data="modifier_alias")],
                [InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")]
            ]

        return message, InlineKeyboardMarkup(keyboard)

    # ========== SOUS-MENU GÉRER LES ADMINS (Owner Only) ==========

    def get_gerer_admins_menu(self):
        """Menu de gestion de l'équipe administrateur avec liste détaillée."""
        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT a.user_id, a.alias, a.first_name, a.username, a.date_added,
                           u.first_name AS nom_ajouteur
                    FROM admins a
                    LEFT JOIN users u ON a.added_by = u.user_id
                    ORDER BY a.date_added DESC
                    """
                )
                admins = cursor.fetchall()

            if not admins:
                message = "👥 <b>Gestion des Administrateurs</b>\n\n📊 Aucun administrateur secondaire configuré.\n\n"
            else:
                message = f"👥 <b>Gestion des Administrateurs</b> ({len(admins)})\n\n"
                for admin in admins:
                    pseudo = f"@{admin['username']}" if admin.get("username") else "Sans username"
                    date_str = admin["date_added"].strftime("%d/%m/%Y") if admin.get("date_added") else "Inconnue"
                    par_qui = admin.get("nom_ajouteur") or "Propriétaire"

                    message += (
                        f"• <b>{admin['alias']}</b> ({pseudo})\n"
                        f"  ID : <code>{admin['user_id']}</code> | Ajouté le {date_str} par {par_qui}\n\n"
                    )

            keyboard = [
                [
                    InlineKeyboardButton("➕ AJOUTER", callback_data="admin_ajouter"),
                    InlineKeyboardButton("➖ RÉVOQUER", callback_data="admin_supprimer")
                ],
                [InlineKeyboardButton("🔙 Retour", callback_data="parametres")]
            ]

        except Exception as exc:
            logger.error("Erreur génération menu gestion admins: %s", exc, exc_info=True)
            message = "👥 <b>Gestion des Administrateurs</b>\n\n❌ Erreur de lecture des données."
            keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="parametres")]]

        return message, InlineKeyboardMarkup(keyboard)

    # ========== SOUS-MENU GÉRER LE BOT (Owner) ==========

    def get_gerer_bot_menu(self):
        """Menu de contrôle du bot avec état dynamique et réglage des quotas."""
        try:
            bot_active = self.db_manager.is_bot_active()
        except Exception:
            bot_active = True

        if bot_active:
            status_badge = "🟢 ACTIF"
            toggle_text = "🔴 SUSPENDRE"
            toggle_callback = "bot_off"
        else:
            status_badge = "🔴 SUSPENDU"
            toggle_text = "🟢 ACTIVER"
            toggle_callback = "bot_on"

        # Récupération des quotas actuels pour affichage informatif direct
        try:
            max_tot = self.config.get_max_total_demandes()
            max_usr = self.config.get_max_demandes_per_user()
            tot_str = str(max_tot) if max_tot > 0 else "Illimité"
            usr_str = str(max_usr) if max_usr > 0 else "Illimité"
        except Exception:
            tot_str, usr_str = "Inconnu", "Inconnu"

        message = (
            "🤖 <b>Contrôle du Bot</b>\n\n"
            f"• <b>Statut des demandes :</b> {status_badge}\n"
            f"• <b>Plafond global :</b> <code>{tot_str}</code>\n"
            f"• <b>Plafond par personne :</b> <code>{usr_str}</code>\n\n"
            "Options opérationnelles :"
        )

        keyboard = [
            [InlineKeyboardButton(f"{toggle_text} LES DEMANDES", callback_data=toggle_callback)],
            [InlineKeyboardButton("⚙️ LIMITES & QUOTAS", callback_data="menu_limits")],
            [InlineKeyboardButton("🛠️ MAINTENANCE SYSTÈME", callback_data="maintenance")],
            [InlineKeyboardButton("🔙 Retour", callback_data="parametres")]
        ]

        return message, InlineKeyboardMarkup(keyboard)

    # ========== SOUS-MENU QUOTAS & LIMITES (Owner Only) ==========

    def get_limits_menu(self):
        """Génère l'affichage et le clavier de réglage des quotas."""
        max_total = self.config.get_max_total_demandes()
        max_user = self.config.get_max_demandes_per_user()

        total_str = f"<b>{max_total}</b>" if max_total > 0 else "<i>Illimité (aucun plafond)</i>"
        user_str = f"<b>{max_user}</b>" if max_user > 0 else "<i>Illimité</i>"

        message = (
            "⚙️ <b>Limitation des Demandes</b>\n\n"
            f"🌐 <b>Plafond global actif :</b> {total_str}\n"
            f"👤 <b>Plafond par personne :</b> {user_str}\n\n"
            "Ajustez les quotas souhaités via les commandes rapides ou par saisie :"
        )

        keyboard = [
            [
                InlineKeyboardButton("🌐 Global: -5", callback_data="limit_total_sub5"),
                InlineKeyboardButton("Illimité (0)", callback_data="limit_total_0"),
                InlineKeyboardButton("+5", callback_data="limit_total_add5"),
            ],
            [
                InlineKeyboardButton("👤 User: -1", callback_data="limit_user_sub1"),
                InlineKeyboardButton("Défaut (3)", callback_data="limit_user_3"),
                InlineKeyboardButton("+1", callback_data="limit_user_add1"),
            ],
            [
                InlineKeyboardButton("✏️ Saisir Total au clavier", callback_data="limit_input_total"),
                InlineKeyboardButton("✏️ Saisir User au clavier", callback_data="limit_input_user"),
            ],
            [
                InlineKeyboardButton("🔙 Retour Gestion Bot", callback_data="gerer_bot")
            ]
        ]

        return message, InlineKeyboardMarkup(keyboard)

    # ========== RÔLE UTILISATEUR ==========

    def _get_user_role(self, user_id: int) -> str:
        """Détermine le rôle de l'utilisateur."""
        if self.config.is_owner(user_id):
            return "owner"
        if self.config.is_admin(user_id):
            return "admin"
        return "user"

    # ========== ROUTEUR CENTRAL DES MENUS ==========

    def route_callback(self, callback_data: str, user_id: int, first_name: str):
        """Aiguillage des callbacks d'interface vers le bon générateur de vue."""
        routing_map = {
            "start_menu": lambda: self.get_start_interface(user_id, first_name),
            "gerer_demandes": self.get_gerer_demandes_menu,
            "parametres": lambda: self.get_parametres_menu(user_id),
            "gerer_admins": self.get_gerer_admins_menu,
            "gerer_bot": self.get_gerer_bot_menu,
            "menu_limits": self.get_limits_menu,
        }

        handler = routing_map.get(callback_data)
        if handler:
            return handler()
        return None, None