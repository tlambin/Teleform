"""Interface Manager - Gestionnaire centralisé des claviers et menus du bot."""

import html
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from utils.validators import convert_utc_to_paris

logger = logging.getLogger(__name__)


class InterfaceManager:
    """Gestionnaire centralisé des interfaces adaptées aux rôles utilisateur."""

    def __init__(self, config, db_manager):
        self.config = config
        self.db_manager = db_manager

    # ========== INTERFACE PRINCIPALE /start ==========

    def get_start_interface(self, user_id: int, first_name: str):
        """Construit l'interface d'accueil selon le rôle et le statut VIP de l'utilisateur."""
        user_role = self._get_user_role(user_id)
        is_vip = self.db_manager.is_user_vip(user_id)
        badge_vip = " ⭐ <b>[MEMBRE VIP]</b>" if is_vip else ""
        first_name_esc = html.escape(str(first_name or "Utilisateur"))

        if user_role == "owner":
            welcome_msg = (
                f"👑 <b>Bienvenue {first_name_esc}, Propriétaire !</b>{badge_vip}\n\n"
                "Sélectionnez une action ci-dessous :"
            )
        elif user_role == "admin":
            raw_alias = self.db_manager.get_admin_alias(user_id) or f"Admin_{user_id}"
            alias_esc = html.escape(str(raw_alias))
            welcome_msg = (
                f"🦈 <b>Bienvenue {alias_esc} !</b>{badge_vip}\n\n"
                "Sélectionnez une action ci-dessous :"
            )
        else:
            welcome_msg = (
                f"👋 <b>Bonjour {first_name_esc} !</b>{badge_vip}\n\n"
                "Sélectionnez une option pour continuer :"
            )

        keyboard = [
            [
                InlineKeyboardButton("🗳️ FAIRE UNE DEMANDE", callback_data="new_demande"),
                InlineKeyboardButton("🗂️ MES DEMANDES", callback_data="voir_demandes")
            ]
        ]

        if not is_vip and user_role not in ["admin", "owner"]:
            keyboard.append([
                InlineKeyboardButton("⭐ DEVENIR VIP (Telegram Stars)", callback_data="menu_vip_shop")
            ])

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
                [InlineKeyboardButton("⭐ GESTION DES CLIENTS VIP", callback_data="gerer_vips")],
                [InlineKeyboardButton("📊 STATISTIQUES GLOBALES", callback_data="bot_stats")],
                [InlineKeyboardButton("🔔 NOTIFICATIONS & RAPPELS", callback_data="menu_notifs")],
                [InlineKeyboardButton("🏷️ MODIFIER MON ALIAS", callback_data="modifier_alias")],
                [InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")]
            ]
        else:
            is_paused = self.db_manager.is_admin_paused(user_id)
            pause_badge = "⏸️ EN PAUSE" if is_paused else "🟢 EN SERVICE"
            pause_btn_text = "▶️ REPRENDRE LE SERVICE" if is_paused else "⏸️ ME METTRE EN PAUSE"
            pause_cb = "admin_resume" if is_paused else "admin_pause_prompt"

            message = (
                "🦈 <b>Paramètres Administrateur</b>\n\n"
                f"• <b>Disponibilité :</b> {pause_badge}\n\n"
                "Options disponibles :"
            )
            keyboard = [
                [InlineKeyboardButton("📊 MON PROFIL & PERFORMANCES", callback_data=f"profil_admin_{user_id}")],
                [InlineKeyboardButton(pause_btn_text, callback_data=pause_cb)],
                [InlineKeyboardButton("🔔 NOTIFICATIONS & RAPPELS", callback_data="menu_notifs")],
                [InlineKeyboardButton("🏷️ MODIFIER MON ALIAS", callback_data="modifier_alias")],
                [InlineKeyboardButton("👑 CONTACTER LE PROPRIÉTAIRE", callback_data="contacter_owner")],
                [InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")]
            ]

        return message, InlineKeyboardMarkup(keyboard)

    # ========== SOUS-MENU GÉRER LES ADMINS (Owner Only) ==========

    def get_gerer_admins_menu(self):
        """Menu de gestion de l'équipe administrateur avec liste détaillée, statistiques et permissions."""
        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT a.user_id, a.alias, a.first_name, a.username, a.date_added,
                           a.perm_reseaux, a.perm_type, a.is_paused,
                           u.first_name AS nom_ajouteur
                    FROM admins a
                    LEFT JOIN users u ON a.added_by = u.user_id
                    ORDER BY a.date_added DESC
                    """
                )
                admins = cursor.fetchall()

            keyboard = []

            if not admins:
                message = "👥 <b>Gestion des Administrateurs</b>\n\n📊 Aucun administrateur secondaire configuré.\n\n"
            else:
                message = f"👥 <b>Gestion des Administrateurs</b> ({len(admins)})\n\n"
                for admin in admins:
                    raw_pseudo = f"@{admin['username']}" if admin.get("username") else "Sans username"
                    pseudo = html.escape(str(raw_pseudo))

                    dt_added = admin.get("date_added")
                    if dt_added:
                        date_paris = convert_utc_to_paris(dt_added)
                        date_str = date_paris.strftime("%d/%m/%Y")
                    else:
                        date_str = "Inconnue"

                    par_qui = html.escape(str(admin.get("nom_ajouteur") or "Propriétaire"))
                    alias_esc = html.escape(str(admin.get("alias") or f"Admin_{admin['user_id']}"))

                    res_tag = admin.get("perm_reseaux") or "all"
                    type_tag = admin.get("perm_type") or "all"

                    res_label = {"all": "Insta & Snap", "insta": "Insta seul", "snap": "Snap seul"}.get(res_tag, str(res_tag))
                    type_label = {"all": "Tous types", "prio_only": "Payantes", "standard_only": "Gratuites"}.get(type_tag, str(type_tag))
                    statut_dispo = "⏸️ <i>(En pause)</i>" if admin.get("is_paused") else "🟢 <i>(En service)</i>"

                    message += (
                        f"• <b>{alias_esc}</b> {statut_dispo} ({pseudo})\n"
                        f"  ID : <code>{admin['user_id']}</code> | Ajouté le {date_str} par {par_qui}\n"
                        f"  🛡️ <i>Accès : {html.escape(res_label)} | {html.escape(type_label)}</i>\n\n"
                    )

                    keyboard.append([
                        InlineKeyboardButton(f"🛡️ Droits : {admin.get('alias', admin['user_id'])}", callback_data=f"perm_admin_{admin['user_id']}"),
                        InlineKeyboardButton("📊 Stats", callback_data=f"profil_admin_{admin['user_id']}")
                    ])

            keyboard.append([
                InlineKeyboardButton("➕ AJOUTER", callback_data="admin_ajouter"),
                InlineKeyboardButton("➖ RÉVOQUER", callback_data="admin_supprimer")
            ])
            keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data="parametres")])

        except Exception as exc:
            logger.error("Erreur génération menu gestion admins : %s", exc, exc_info=True)
            message = "👥 <b>Gestion des Administrateurs</b>\n\n❌ Erreur de lecture des données."
            keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="parametres")]]

        return message, InlineKeyboardMarkup(keyboard)

    # ========== SOUS-MENU GÉRER LES MEMBRES VIP (Owner Only) ==========

    def get_gerer_vips_menu(self):
        """Affiche la liste des membres VIP et les outils d'administration dédiés."""
        try:
            vips = self.db_manager.get_vip_users_list()
            keyboard = []

            if not vips:
                message = "⭐ <b>Gestion des Membres VIP</b>\n\n📭 Aucun membre VIP actif actuellement.\n\n"
            else:
                message = f"⭐ <b>Gestion des Membres VIP</b> ({len(vips)})\n\n"
                for v in vips:
                    nom = html.escape(str(v.get("first_name") or "Utilisateur"))
                    pseudo = f"(@{html.escape(str(v['username']))})" if v.get("username") else ""
                    until = v.get("vip_until")
                    if until:
                        until_paris = convert_utc_to_paris(until)
                        exp_str = until_paris.strftime("%d/%m/%Y")
                        status_str = f"Expire le {exp_str}"
                    else:
                        status_str = "👑 À vie"

                    message += (
                        f"• <b>{nom}</b> {pseudo}\n"
                        f"  ID : <code>{v['user_id']}</code> | <i>{status_str}</i>\n\n"
                    )

            keyboard.append([
                InlineKeyboardButton("➕ PROMOUVOIR VIP", callback_data="owner_add_vip"),
                InlineKeyboardButton("➖ RÉVOQUER VIP", callback_data="owner_remove_vip")
            ])
            keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data="parametres")])

        except Exception as exc:
            logger.error("Erreur génération menu VIP owner : %s", exc, exc_info=True)
            message = "⭐ <b>Gestion des Membres VIP</b>\n\n❌ Erreur de lecture des données."
            keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="parametres")]]

        return message, InlineKeyboardMarkup(keyboard)

    # ========== SOUS-MENU BOUTIQUE VIP (Telegram Stars) ==========

    def get_vip_shop_menu(self):
        """Affiche l'offre d'abonnement VIP mensuel payable en Telegram Stars."""
        message = (
            "⭐ <b>Devenez Membre VIP via Telegram Stars !</b>\n\n"
            "Débloquez instantanément tous les privilèges premium du bot pour <b>30 jours</b> :\n\n"
            "• 🚀 <b>Demandes illimitées :</b> Aucun quota ne vous bloque, même si le service est saturé.\n"
            "• 🎯 <b>Choix du référent :</b> Choisissez quel administrateur s'occupe de vos demandes.\n"
            "• 💬 <b>Ligne directe :</b> Contactez votre référent à tout moment via le bot.\n"
            "• 🔔 <b>Relance hebdomadaire gratuite :</b> Relancez votre référent une fois par semaine.\n\n"
            "<i>Paiement sécurisé via Telegram Stars. Activation immédiate pour 30 jours.</i>"
        )
        keyboard = [
            [InlineKeyboardButton("⭐ S'abonner 1 Mois (250 ⭐️)", callback_data="buy_vip_month")],
            [InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")]
        ]
        return message, InlineKeyboardMarkup(keyboard)

    # ========== SOUS-MENU GÉRER LE BOT (Owner) ==========

    def get_gerer_bot_menu(self):
        """Menu de contrôle du bot avec synchronisation directe sur l'état des demandes."""
        try:
            bot_active = self.config.are_demandes_enabled()
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
            f"• <b>Plafond global :</b> <code>{html.escape(tot_str)}</code>\n"
            f"• <b>Plafond par personne :</b> <code>{html.escape(usr_str)}</code>\n\n"
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
        """Génère l'affichage et le clavier de réglage des quotas en direct depuis la configuration."""
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
        try:
            uid = int(user_id)
        except (ValueError, TypeError):
            return "user"

        if self.config.is_owner(uid):
            return "owner"
        if self.config.is_admin(uid):
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
            "gerer_vips": self.get_gerer_vips_menu,
            "menu_vip_shop": self.get_vip_shop_menu,
            "gerer_bot": self.get_gerer_bot_menu,
            "menu_limits": self.get_limits_menu,
        }

        handler = routing_map.get(callback_data)
        if handler:
            return handler()
        return None, None