"""Interface Manager - Gestionnaire centralisé des claviers et menus du bot selon la hiérarchie RBAC."""

import html
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from utils.validators import convert_utc_to_paris

logger = logging.getLogger(__name__)


class InterfaceManager:
    """Gestionnaire centralisé des interfaces adaptées aux rôles : Client, Staff, Admin et Owner."""

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
                f"🛡️ <b>Bienvenue {alias_esc} [Manager] !</b>{badge_vip}\n\n"
                "Sélectionnez une action ci-dessous :"
            )
        elif user_role == "staff":
            raw_alias = self.db_manager.get_staff_alias(user_id) or f"Staff_{user_id}"
            alias_esc = html.escape(str(raw_alias))
            welcome_msg = (
                f"🦈 <b>Bienvenue {alias_esc} [Opérateur] !</b>{badge_vip}\n\n"
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

        if not is_vip and user_role == "user":
            keyboard.append([
                InlineKeyboardButton("⭐ DEVENIR VIP (Telegram Stars)", callback_data="menu_vip_shop")
            ])

        # Tous les rôles opérationnels ont accès à la gestion des dossiers
        if user_role in ["staff", "admin", "owner"]:
            keyboard.append([
                InlineKeyboardButton("📋 GÉRER LES DEMANDES", callback_data="gerer_demandes")
            ])

        # Le bouton PARAMÈTRES est disponible pour tous (Clients, VIP, Staff, Admin, Owner)
        keyboard.append([
            InlineKeyboardButton("⚙️ PARAMÈTRES", callback_data="parametres")
        ])

        return welcome_msg, InlineKeyboardMarkup(keyboard)

    # ========== SOUS-MENU GÉRER LES DEMANDES ==========

    def get_gerer_demandes_menu(self):
        """Affiche le menu de traitement des demandes pour l'équipe opérationnelle."""
        message = "📋 <b>Gestion des Demandes</b>\n\nChoisissez une file de traitement :"
        keyboard = [
            [InlineKeyboardButton("📮 DEMANDES DISPONIBLES", callback_data="demandes_disponibles")],
            [InlineKeyboardButton("💌 DEMANDES SUIVIES", callback_data="demandes_suivies")],
            [InlineKeyboardButton("📦 MES DOSSIERS CLÔTURÉS", callback_data="demandes_archives")],
            [InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")]
        ]
        return message, InlineKeyboardMarkup(keyboard)

    # ========== SOUS-MENU PARAMÈTRES (HIÉRARCHIQUE) ==========

    def get_parametres_menu(self, user_id: int):
        """Construit le panneau de configuration selon les privilèges RBAC."""
        user_role = self._get_user_role(user_id)
        is_vip = self.db_manager.is_user_vip(user_id)

        # 1. Menu Super-Admin / Propriétaire
        if user_role == "owner":
            message = "👑 <b>Paramètres Propriétaire (Super-Admin)</b>\n\nOptions de contrôle global du service :"
            keyboard = [
                [InlineKeyboardButton("🤖 GESTION DU BOT", callback_data="gerer_bot")],
                [InlineKeyboardButton("👥 PIÈGEURS", callback_data="gerer_staff")],
                [InlineKeyboardButton("🛡️ ADMINS", callback_data="gerer_admins")],
                [InlineKeyboardButton("⭐ VIP", callback_data="gerer_vips")],
                [InlineKeyboardButton("💳 PAIEMENTS", callback_data="staff_payment_settings")],
                [InlineKeyboardButton("📦 ARCHIVES", callback_data="admin_global_archives")],
                [InlineKeyboardButton("📊 STATISTIQUES", callback_data="bot_stats")],
                [InlineKeyboardButton("🔔 NOTIFICATIONS & RAPPELS", callback_data="menu_notifs")],
                [InlineKeyboardButton("🏷️ MODIFIER MON ALIAS", callback_data="modifier_alias")],
            ]
            if is_vip:
                keyboard.append([InlineKeyboardButton("⭐ MES PRÉFÉRENCES VIP (Attribution)", callback_data="menu_vip_settings")])
            keyboard.append([InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")])

        # 2. Menu Administrateur / Manager
        elif user_role == "admin":
            privs = self.db_manager.get_admin_privileges(user_id)
            message = "🛡️ <b>Paramètres Administrateur (Manager)</b>\n\nOutils d'encadrement :"
            keyboard = []

            if privs.get("can_manage_staff", True):
                keyboard.append([InlineKeyboardButton("👥 ÉQUIPE STAFF (Opérateurs)", callback_data="gerer_staff")])

            if privs.get("can_manage_vips", True):
                keyboard.append([InlineKeyboardButton("⭐ GESTION DES CLIENTS VIP", callback_data="gerer_vips")])

            if privs.get("can_view_archives", False):
                keyboard.append([InlineKeyboardButton("📦 ARCHIVES GÉNÉRALES", callback_data="admin_global_archives")])

            if privs.get("can_view_stats", True):
                keyboard.append([InlineKeyboardButton("📊 STATISTIQUES GLOBALES", callback_data="bot_stats")])

            keyboard.extend([
                [InlineKeyboardButton("💳 MES MODES DE PAIEMENT ACCEPTÉS", callback_data="staff_payment_settings")],
                [InlineKeyboardButton("🔔 NOTIFICATIONS STAFF & RAPPELS", callback_data="menu_notifs")],
                [InlineKeyboardButton("🏷️ MODIFIER MON ALIAS", callback_data="modifier_alias")],
            ])
            if is_vip:
                keyboard.append([InlineKeyboardButton("⭐ MES PRÉFÉRENCES VIP (Attribution)", callback_data="menu_vip_settings")])
            keyboard.append([InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")])

        # 3. Menu Staff / Opérateur
        elif user_role == "staff":
            is_paused = self.db_manager.is_staff_paused(user_id)
            pause_badge = "⏸️ EN PAUSE" if is_paused else "🟢 EN SERVICE"
            pause_btn_text = "▶️ REPRENDRE LE SERVICE" if is_paused else "⏸️ ME METTRE EN PAUSE"
            pause_cb = "admin_resume" if is_paused else "admin_pause_prompt"

            message = (
                "🦈 <b>Paramètres Opérateur (Staff)</b>\n\n"
                f"• <b>Disponibilité :</b> {pause_badge}\n\n"
                "Options disponibles :"
            )
            keyboard = [
                [InlineKeyboardButton("📊 MON PROFIL & PERFORMANCES", callback_data=f"profil_admin_{user_id}")],
                [InlineKeyboardButton(pause_btn_text, callback_data=pause_cb)],
                [InlineKeyboardButton("💳 MES MODES DE PAIEMENT ACCEPTÉS", callback_data="staff_payment_settings")],
                [InlineKeyboardButton("🔔 NOTIFICATIONS STAFF & RAPPELS", callback_data="menu_notifs")],
                [InlineKeyboardButton("🏷️ MODIFIER MON ALIAS", callback_data="modifier_alias")],
                [InlineKeyboardButton("👑 CONTACTER L'ADMINISTRATION", callback_data="contacter_owner")],
            ]
            if is_vip:
                keyboard.append([InlineKeyboardButton("⭐ MES PRÉFÉRENCES VIP (Attribution)", callback_data="menu_vip_settings")])
            keyboard.append([InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")])

        # 4. Menu Utilisateur / Demandeur (Standard ou VIP)
        else:
            vip_mention = " <i>(Membre VIP)</i>" if is_vip else ""
            message = (
                f"⚙️ <b>Mes Paramètres{vip_mention}</b>\n\n"
                "Gérez vos options de compte :"
            )
            keyboard = []
            if is_vip:
                keyboard.append([InlineKeyboardButton("🎯 GÉRER MON ATTRIBUTION VIP", callback_data="menu_vip_settings")])
            keyboard.append([InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")])

        return message, InlineKeyboardMarkup(keyboard)

    # ========== SOUS-MENU MODES DE PAIEMENT DU STAFF ==========

    def get_staff_payment_settings_menu(self, staff_id: int):
        """Affiche les bascules de moyens de paiement pour l'opérateur."""
        methods = self.db_manager.get_staff_payment_methods(staff_id)
        st_stars = "✅ ACTIF" if methods["accept_stars"] else "❌ INACTIF"
        st_direct = "✅ ACTIF" if methods["accept_direct"] else "❌ INACTIF"

        text = (
            "💳 <b>Modes de Paiement Acceptés</b>\n\n"
            "Configurez les moyens de règlement proposés à vos clients lorsqu'ils paient leurs dossiers prioritaires :\n\n"
            f"• <b>Telegram Stars :</b> {st_stars}\n"
            f"• <b>Paiement direct (PayPal, virement, etc.) :</b> {st_direct}\n\n"
            "<i>Note : Vous devez toujours conserver au moins un mode de paiement actif.</i>"
        )
        keyboard = [
            [InlineKeyboardButton(f"⭐ Telegram Stars : {st_stars}", callback_data="toggle_pay_staff_accept_stars")],
            [InlineKeyboardButton(f"💬 Paiement direct : {st_direct}", callback_data="toggle_pay_staff_accept_direct")],
            [InlineKeyboardButton("🔙 Retour aux paramètres", callback_data="parametres")]
        ]
        return text, InlineKeyboardMarkup(keyboard)

    # ========== SOUS-MENU GÉRER LE SERVICE (Owner Only) ==========

    def get_gerer_bot_menu(self):
        """Menu de contrôle du bot avec synchronisation de l'état des demandes."""
        try:
            bot_active = self.config.are_demandes_enabled()
        except Exception:
            bot_active = True

        status_badge = "🟢 ACTIF" if bot_active else "🔴 SUSPENDU"
        toggle_text = "🔴 SUSPENDRE" if bot_active else "🟢 ACTIVER"
        toggle_callback = "bot_off" if bot_active else "bot_on"

        try:
            max_tot = self.config.get_max_total_demandes()
            max_usr = self.config.get_max_demandes_per_user()
            tot_str = str(max_tot) if max_tot > 0 else "Illimité"
            usr_str = str(max_usr) if max_usr > 0 else "Illimité"
        except Exception:
            tot_str, usr_str = "Inconnu", "Inconnu"

        message = (
            "🤖 <b>Contrôle du Service</b>\n\n"
            f"• <b>Statut des demandes :</b> {status_badge}\n"
            f"• <b>Plafond global :</b> <code>{html.escape(tot_str)}</code>\n"
            f"• <b>Plafond par personne :</b> <code>{html.escape(usr_str)}</code>\n\n"
            "Options opérationnelles :"
        )

        keyboard = [
            [InlineKeyboardButton(f"{toggle_text} LES DEMANDES", callback_data=toggle_callback)],
            [InlineKeyboardButton("🎛️ CANAUX & ORIENTATIONS (ON/OFF)", callback_data="menu_channels")],
            [InlineKeyboardButton("⚙️ LIMITES & QUOTAS", callback_data="menu_limits")],
            [InlineKeyboardButton("⏱️ DÉLAIS & ARCHIVAGE", callback_data="menu_delais")],
            [InlineKeyboardButton("📢 ADHÉSION OBLIGATOIRE (GROUPE)", callback_data="menu_cfg_group")],
            [InlineKeyboardButton("🛠️ MAINTENANCE SYSTÈME", callback_data="maintenance")],
            [InlineKeyboardButton("🔙 Retour", callback_data="parametres")]
        ]

        return message, InlineKeyboardMarkup(keyboard)

    # ========== SOUS-MENU ADHÉSION OBLIGATOIRE GROUPE (Owner Only) ==========

    def get_group_subscription_config_menu(self):
        """Menu interactif de configuration de l'adhésion obligatoire."""
        is_enabled = self.db_manager.is_required_group_enabled()
        group_id = self.db_manager.get_required_group_id()
        link = self.db_manager.get_group_subscription_link()

        statut_badge = "🟢 ACTIVE" if is_enabled else "🔴 DÉSACTIVÉE"
        toggle_btn_label = "🔴 Désactiver l'obligation" if is_enabled else "🟢 Activer l'obligation"
        gid_str = f"<code>{group_id}</code>" if group_id != 0 else "<i>Non configuré (0)</i>"

        text = (
            "📢 <b>Configuration de l'Adhésion Obligatoire</b>\n\n"
            f"• <b>État :</b> {statut_badge}\n"
            f"• <b>Chat ID du groupe :</b> {gid_str}\n"
            f"• <b>Lien / Bot d'inscription :</b> <code>{html.escape(link)}</code>\n\n"
            "<i>Lorsque l'option est active, tout utilisateur non-membre du groupe est bloqué tant qu'il n'a pas validé son inscription.</i>"
        )
        keyboard = [
            [InlineKeyboardButton(toggle_btn_label, callback_data="toggle_cfg_group_enabled")],
            [InlineKeyboardButton("🆔 Modifier l'ID du groupe", callback_data="set_cfg_group_id")],
            [InlineKeyboardButton("🔗 Modifier le Lien / Bot", callback_data="set_cfg_group_link")],
            [InlineKeyboardButton("🔙 Gestion Service", callback_data="gerer_bot")]
        ]
        return text, InlineKeyboardMarkup(keyboard)

    # ========== SOUS-MENU CANAUX & COMBINAISONS (Toggles ON/OFF) ==========

    def get_channels_menu(self):
        """Menu interactif de bascule pour les 4 canaux combinés (Hétéro/Gay × Insta/Snap)."""
        h_insta = str(self.db_manager.get_config_value("allow_hetero_insta", "true")).lower() == "true"
        h_snap = str(self.db_manager.get_config_value("allow_hetero_snap", "true")).lower() == "true"
        g_insta = str(self.db_manager.get_config_value("allow_gay_insta", "true")).lower() == "true"
        g_snap = str(self.db_manager.get_config_value("allow_gay_snap", "true")).lower() == "true"

        b_hi = "🟢 Insta Hétéro" if h_insta else "🔴 Insta Hétéro"
        b_hs = "🟢 Snap Hétéro" if h_snap else "🔴 Snap Hétéro"
        b_gi = "🟢 Insta Gay" if g_insta else "🔴 Insta Gay"
        b_gs = "🟢 Snap Gay" if g_snap else "🔴 Snap Gay"

        keyboard = [
            [
                InlineKeyboardButton(b_hi, callback_data="toggle_allow_hetero_insta"),
                InlineKeyboardButton(b_hs, callback_data="toggle_allow_hetero_snap"),
            ],
            [
                InlineKeyboardButton(b_gi, callback_data="toggle_allow_gay_insta"),
                InlineKeyboardButton(b_gs, callback_data="toggle_allow_gay_snap"),
            ],
            [InlineKeyboardButton("🔙 Gestion Service", callback_data="gerer_bot")]
        ]

        text = (
            "🎛️ <b>Disponibilité des Canaux Combinés</b>\n\n"
            "Activez ou suspendez individuellement chaque flux :\n\n"
            f"• <b>Insta Hétéro :</b> {'✅ Ouvert' if h_insta else '❌ Désactivé'}\n"
            f"• <b>Snap Hétéro :</b> {'✅ Ouvert' if h_snap else '❌ Désactivé'}\n"
            f"• <b>Insta Gay :</b> {'✅ Ouvert' if g_insta else '❌ Désactivé'}\n"
            f"• <b>Snap Gay :</b> {'✅ Ouvert' if g_snap else '❌ Désactivé'}\n\n"
            "<i>(Les demandes Bi utilisent ces canaux selon le réseau sélectionné)</i>"
        )
        return text, InlineKeyboardMarkup(keyboard)

    # ========== SOUS-MENU QUOTAS & LIMITES (Matrice) ==========

    def get_limits_menu(self):
        """Ajustement rapide des quotas globaux, par client et par canal combiné."""
        max_total = self.config.get_max_total_demandes()
        max_user = self.config.get_max_demandes_per_user()

        m_hi = int(self.db_manager.get_config_value("max_hetero_insta", "0") or 0)
        m_hs = int(self.db_manager.get_config_value("max_hetero_snap", "0") or 0)
        m_gi = int(self.db_manager.get_config_value("max_gay_insta", "0") or 0)
        m_gs = int(self.db_manager.get_config_value("max_gay_snap", "0") or 0)

        def fmt(val: int) -> str:
            return f"<b>{val}</b>" if val > 0 else "<i>Illimité</i>"

        message = (
            "⚙️ <b>Limitation & Plafonds des Demandes</b>\n\n"
            f"🌐 <b>Plafond global actif :</b> {fmt(max_total)}\n"
            f"👤 <b>Plafond par client :</b> {fmt(max_user)}\n\n"
            "<b>Plafonds spécifiques par canal :</b>\n"
            f"• 📷 Insta Hétéro : {fmt(m_hi)}\n"
            f"• 👻 Snap Hétéro : {fmt(m_hs)}\n"
            f"• 📷 Insta Gay : {fmt(m_gi)}\n"
            f"• 👻 Snap Gay : {fmt(m_gs)}\n\n"
            "<i>Choisissez un quota à saisir au clavier :</i>"
        )

        keyboard = [
            [
                InlineKeyboardButton("🌐 Global: -5", callback_data="limit_total_sub5"),
                InlineKeyboardButton("Illimité (0)", callback_data="limit_total_0"),
                InlineKeyboardButton("+5", callback_data="limit_total_add5"),
            ],
            [
                InlineKeyboardButton("👤 Client: -1", callback_data="limit_user_sub1"),
                InlineKeyboardButton("Défaut (3)", callback_data="limit_user_3"),
                InlineKeyboardButton("+1", callback_data="limit_user_add1"),
            ],
            [
                InlineKeyboardButton("📷 Max Insta Hétéro", callback_data="limit_input_hetero_insta"),
                InlineKeyboardButton("👻 Max Snap Hétéro", callback_data="limit_input_hetero_snap"),
            ],
            [
                InlineKeyboardButton("📷 Max Insta Gay", callback_data="limit_input_gay_insta"),
                InlineKeyboardButton("👻 Max Snap Gay", callback_data="limit_input_gay_snap"),
            ],
            [
                InlineKeyboardButton("✏️ Saisir Total", callback_data="limit_input_total"),
                InlineKeyboardButton("✏️ Saisir Client", callback_data="limit_input_user"),
            ],
            [
                InlineKeyboardButton("🔙 Retour Gestion Service", callback_data="gerer_bot")
            ]
        ]

        return message, InlineKeyboardMarkup(keyboard)

    # ========== SOUS-MENU GÉRER LE STAFF (Admins & Owner) ==========

    def get_gerer_staff_menu(self):
        """Menu de gestion des employés/opérateurs (table staff)."""
        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT s.user_id, s.alias, s.date_added, s.perm_reseaux, s.perm_type, s.perm_orientation, s.is_paused,
                           u.first_name, u.username,
                           u_add.first_name AS nom_ajouteur
                    FROM staff s
                    LEFT JOIN users u ON s.user_id = u.user_id
                    LEFT JOIN users u_add ON s.added_by = u_add.user_id
                    ORDER BY s.date_added DESC
                    """
                )
                staff_members = cursor.fetchall()

            keyboard = []

            if not staff_members:
                message = "👥 <b>Gestion de l'Équipe Staff</b>\n\n📊 Aucun opérateur configuré pour le moment.\n\n"
            else:
                message = f"👥 <b>Gestion de l'Équipe Staff ({len(staff_members)})</b>\n\n"
                for st in staff_members:
                    raw_pseudo = f"@{st['username']}" if st.get("username") else "Sans pseudo"
                    pseudo = html.escape(str(raw_pseudo))

                    dt_added = st.get("date_added")
                    date_str = convert_utc_to_paris(dt_added).strftime("%d/%m/%Y") if dt_added else "Inconnue"
                    par_qui = html.escape(str(st.get("nom_ajouteur") or "Direction"))
                    alias_esc = html.escape(str(st.get("alias") or f"Staff_{st['user_id']}"))

                    res_tag = st.get("perm_reseaux") or "all"
                    type_tag = st.get("perm_type") or "all"
                    ori_tag = st.get("perm_orientation") or "all"

                    res_label = {"all": "Insta & Snap", "insta": "Insta seul", "snap": "Snap seul"}.get(res_tag, str(res_tag))
                    type_label = {"all": "Tous types", "prio_only": "Payantes", "standard_only": "Gratuites"}.get(type_tag, str(type_tag))
                    ori_label = {"all": "Toutes", "hetero": "Hétéro/Bi", "gay": "Gay/Bi", "bi": "Bi"}.get(ori_tag, str(ori_tag))
                    statut_dispo = "⏸️ <i>(En pause)</i>" if st.get("is_paused") else "🟢 <i>(En service)</i>"

                    message += (
                        f"• <b>{alias_esc}</b> {statut_dispo} ({pseudo})\n"
                        f"  ID : <code>{st['user_id']}</code> | Recruté le {date_str} par {par_qui}\n"
                        f"  🛡️ <i>Accès : {html.escape(res_label)} | {html.escape(type_label)} | {html.escape(ori_label)}</i>\n\n"
                    )

                    keyboard.append([
                        InlineKeyboardButton(f"🛡️ Droits : {st.get('alias', st['user_id'])}", callback_data=f"perm_staff_{st['user_id']}"),
                        InlineKeyboardButton("📊 Stats", callback_data=f"profil_admin_{st['user_id']}")
                    ])

            keyboard.append([
                InlineKeyboardButton("➕ RECRUTER STAFF", callback_data="staff_ajouter"),
                InlineKeyboardButton("➖ RÉVOQUER STAFF", callback_data="staff_supprimer")
            ])
            keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data="parametres")])

        except Exception as exc:
            logger.error("Erreur menu gestion staff : %s", exc, exc_info=True)
            message = "👥 <b>Gestion de l'Équipe Staff</b>\n\n❌ Erreur de lecture de la base."
            keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="parametres")]]

        return message, InlineKeyboardMarkup(keyboard)

    # ========== SOUS-MENU GÉRER LES ADMINS / MANAGERS (Owner Only) ==========

    def get_gerer_admins_menu(self):
        """Menu de gestion des administrateurs/managers (table admins)."""
        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT a.user_id, a.alias, a.is_owner, a.date_added,
                           a.can_view_archives,
                           u.username, u.first_name
                    FROM admins a
                    LEFT JOIN users u ON a.user_id = u.user_id
                    ORDER BY a.is_owner DESC, a.date_added DESC
                    """
                )
                admins = cursor.fetchall()

            keyboard = []

            if not admins:
                message = "🛡️ <b>Gestion des Administrateurs</b>\n\n📊 Aucun administrateur secondaire configuré.\n\n"
            else:
                message = f"🛡️ <b>Gestion des Administrateurs ({len(admins)})</b>\n\n"
                for admin in admins:
                    raw_pseudo = f"@{admin['username']}" if admin.get("username") else "Sans pseudo"
                    pseudo = html.escape(str(raw_pseudo))
                    alias_esc = html.escape(str(admin.get("alias") or f"Admin_{admin['user_id']}"))
                    role_badge = "👑 <b>[Super-Admin]</b>" if admin.get("is_owner") else "🛡️ <b>[Manager]</b>"

                    dt_added = admin.get("date_added")
                    date_str = convert_utc_to_paris(dt_added).strftime("%d/%m/%Y") if dt_added else "Inconnue"

                    arch_badge = "✅" if admin.get("can_view_archives") else "❌"
                    perm_info = f" | Archives: {arch_badge}" if not admin.get("is_owner") else ""

                    message += (
                        f"• {role_badge} <b>{alias_esc}</b> ({pseudo})\n"
                        f"  ID : <code>{admin['user_id']}</code> | Date d'entrée : {date_str}{perm_info}\n\n"
                    )

                    if not admin.get("is_owner"):
                        keyboard.append([
                            InlineKeyboardButton(f"⚙️ Droits : {admin.get('alias', admin['user_id'])}", callback_data=f"perm_admin_{admin['user_id']}")
                        ])

            keyboard.append([
                InlineKeyboardButton("➕ NOMMER ADMIN", callback_data="admin_ajouter"),
                InlineKeyboardButton("➖ RÉVOQUER ADMIN", callback_data="admin_supprimer")
            ])
            keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data="parametres")])

        except Exception as exc:
            logger.error("Erreur génération menu admins : %s", exc, exc_info=True)
            message = "🛡️ <b>Gestion des Administrateurs</b>\n\n❌ Erreur de lecture des données."
            keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="parametres")]]

        return message, InlineKeyboardMarkup(keyboard)

    # ========== SOUS-MENU GÉRER LES MEMBRES VIP ==========

    def get_gerer_vips_menu(self):
        """Affiche la liste des membres VIP et les outils d'attribution."""
        try:
            vips = self.db_manager.get_vip_users_list()
            keyboard = []

            if not vips:
                message = "⭐ <b>Gestion des Membres VIP</b>\n\n📭 Aucun membre VIP actif actuellement.\n\n"
            else:
                message = f"⭐ <b>Gestion des Membres VIP ({len(vips)})</b>\n\n"
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
            logger.error("Erreur génération menu VIP : %s", exc, exc_info=True)
            message = "⭐ <b>Gestion des Membres VIP</b>\n\n❌ Erreur de lecture des données."
            keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="parametres")]]

        return message, InlineKeyboardMarkup(keyboard)

    # ========== SOUS-MENU BOUTIQUE VIP (Telegram Stars) ==========

    def get_vip_shop_menu(self, is_vip: bool = False):
        """Affiche l'offre d'abonnement VIP mensuel payable en Telegram Stars."""
        message = (
            "⭐ <b>Devenez Membre VIP via Telegram Stars !</b>\n\n"
            "Débloquez instantanément tous les privilèges premium du bot pour <b>30 jours</b> :\n\n"
            "• 🚀 <b>Demandes illimitées :</b> Aucun quota ne vous bloque, même si le service est saturé.\n"
            "• 🎯 <b>Choix du référent :</b> Choisissez quel opérateur s'occupe de vos demandes.\n"
            "• 💬 <b>Ligne directe :</b> Contactez votre référent à tout moment via le bot.\n"
            "• 🔔 <b>Relance hebdomadaire gratuite :</b> Relancez votre référent une fois par semaine.\n\n"
            "<i>Paiement sécurisé via Telegram Stars. Activation immédiate pour 30 jours.</i>"
        )
        keyboard = []

        if is_vip:
            keyboard.append([
                InlineKeyboardButton("⚙️ Mes Préférences d'Attribution", callback_data="menu_vip_settings")
            ])

        keyboard.extend([
            [InlineKeyboardButton("⭐ S'abonner 1 Mois (250 ⭐️)", callback_data="buy_vip_month")],
            [InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")]
        ])
        return message, InlineKeyboardMarkup(keyboard)

    # ========== RÔLE UTILISATEUR ==========

    def _get_user_role(self, user_id: int) -> str:
        """Détermine le rôle précis selon la hiérarchie RBAC."""
        try:
            uid = int(user_id)
        except (ValueError, TypeError):
            return "user"

        if self.config.is_owner(uid):
            return "owner"
        if self.config.is_admin(uid):
            return "admin"
        if self.config.is_staff(uid):
            return "staff"
        return "user"

    # ========== ROUTEUR CENTRAL DES MENUS ==========

    def route_callback(self, callback_data: str, user_id: int, first_name: str):
        """Aiguillage des callbacks d'interface vers le bon générateur de vue."""
        is_vip = self.db_manager.is_user_vip(user_id)

        routing_map = {
            "start_menu": lambda: self.get_start_interface(user_id, first_name),
            "gerer_demandes": self.get_gerer_demandes_menu,
            "parametres": lambda: self.get_parametres_menu(user_id),
            "staff_payment_settings": lambda: self.get_staff_payment_settings_menu(user_id),
            "gerer_staff": self.get_gerer_staff_menu,
            "gerer_admins": self.get_gerer_admins_menu,
            "gerer_vips": self.get_gerer_vips_menu,
            "menu_vip_shop": lambda: self.get_vip_shop_menu(is_vip=is_vip),
            "gerer_bot": self.get_gerer_bot_menu,
            "menu_cfg_group": self.get_group_subscription_config_menu,
            "menu_channels": self.get_channels_menu,
            "menu_limits": self.get_limits_menu,
        }

        handler = routing_map.get(callback_data)
        if handler:
            return handler()
        return None, None