"""Interface Manager - Gestionnaire centralisé des claviers et menus du bot selon la hiérarchie RBAC."""

import html
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)


def format_datetime_fr(val) -> str:
    """Convertit une date ou un timestamp au format strict JJ/MM/AAAA."""
    if not val:
        return "Inconnue"
    try:
        if hasattr(val, "strftime"):
            return val.strftime("%d/%m/%Y")
        parts = str(val)[:10].split("-")
        if len(parts) == 3:
            return f"{parts[2]}/{parts[1]}/{parts[0]}"
    except Exception:
        pass
    return str(val)[:10]


class InterfaceManager:
    """Gestionnaire centralisé des interfaces adaptées aux rôles : Client, Staff, Admin et Owner."""

    def __init__(self, config, db_manager):
        self.config = config
        self.db_manager = db_manager

    # ========== INTERFACE PRINCIPALE /start ==========

    def get_start_interface(self, user_id: int, first_name: str):
        """Construit l'interface d'accueil selon la maquette."""
        user_role = self._get_user_role(user_id)
        is_vip = self.db_manager.is_user_vip(user_id)
        first_name_esc = html.escape(str(first_name or "Utilisateur"))

        badge_role_map = {
            "owner": "👑 <b>Direction • Propriétaire</b>",
            "admin": "🛡️ <b>Administration • Manager</b>",
            "staff": "🦈 <b>Équipe • Opérateur</b>",
            "user": "⭐ <b>Membre VIP</b>" if is_vip else "👤 <b>Espace Demandeur</b>"
        }
        role_badge = badge_role_map.get(user_role, "👤 <b>Espace Demandeur</b>")

        welcome_msg = (
            f"⚡ <b>PORTAIL PRINCIPAL</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Bonjour <b>{first_name_esc}</b> !\n"
            f"• <b>Statut :</b> {role_badge}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            "<i>Sélectionnez une option ci-dessous pour continuer :</i>"
        )

        # Ligne 1 : 🗳️ DÉPOSER | 🗂️ MES DEMANDES
        keyboard = [
            [
                InlineKeyboardButton("🗳️ DÉPOSER", callback_data="new_demande"),
                InlineKeyboardButton("🗂️ MES DEMANDES", callback_data="voir_demandes")
            ]
        ]

        # Ligne 2 : 🚦 GÉRER LES DEMANDES 🚦 (Staff, Admin, Owner uniquement)
        if user_role in ["staff", "admin", "owner"]:
            keyboard.append([
                InlineKeyboardButton("🚦 GÉRER LES DEMANDES 🚦", callback_data="gerer_demandes")
            ])

        # Ligne 3 : ⭐ DEVENIR VIP ⭐ (affiché si non-VIP)
        if not is_vip:
            keyboard.append([
                InlineKeyboardButton("⭐ DEVENIR VIP ⭐", callback_data="menu_vip_shop")
            ])

        # Ligne 4 : ⚙️ PARAMÈTRES ⚙️
        keyboard.append([
            InlineKeyboardButton("⚙️ PARAMÈTRES ⚙️", callback_data="parametres")
        ])

        return welcome_msg, InlineKeyboardMarkup(keyboard)

    # ========== SOUS-MENU GÉRER LES DEMANDES ==========

    def get_gerer_demandes_menu(self, user_id: int):
        """Affiche le menu de gestion des demandes avec compteurs dynamiques selon les perms du membre."""
        counts = self.db_manager.get_staff_demandes_counts(user_id)
        nb_dispo = counts.get("dispo", 0)
        nb_suivies = counts.get("suivies", 0)
        nb_archives = counts.get("archives", 0)

        message = (
            "📋 <b>Gestion des demandes</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Accédez aux dossiers selon leur niveau d'assignation :"
        )
        keyboard = [
            # 1. 📮 DISPONIBLE (X)
            [InlineKeyboardButton(f"📮 DISPONIBLE ({nb_dispo})", callback_data="demandes_disponibles")],
            # 2. 💌 SUIVIES (Y)
            [InlineKeyboardButton(f"💌 SUIVIES ({nb_suivies})", callback_data="demandes_suivies")],
            # 3. 📦 ARCHIVÉES (Z)
            [InlineKeyboardButton(f"📦 ARCHIVÉES ({nb_archives})", callback_data="demandes_archives")],
            # Retour
            [InlineKeyboardButton("⬅️ RETOUR", callback_data="start_menu")]
        ]
        return message, InlineKeyboardMarkup(keyboard)

    # ========== SOUS-MENU PARAMÈTRES (CONFORME MAQUETTE) ==========

    def get_parametres_menu(self, user_id: int):
        """Construit le panneau de configuration selon la disposition exacte de la maquette."""
        user_role = self._get_user_role(user_id)
        is_admin = (user_role in ["admin", "owner"])
        is_staff = (user_role in ["staff", "admin", "owner"])
        is_vip = self.db_manager.is_user_vip(user_id)

        # Rôle standard / demandeur
        if not is_staff:
            vip_mention = " <i>(Abonné VIP)</i>" if is_vip else ""
            message = (
                f"⚙️ <b>PARAMÈTRES DU COMPTE{vip_mention}</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Gérez vos options et abonnements :"
            )
            keyboard = []
            if is_vip:
                keyboard.append([InlineKeyboardButton("🎯 Gérer mon attribution VIP", callback_data="menu_vip_settings")])
            else:
                keyboard.append([InlineKeyboardButton("⭐ Boutique VIP", callback_data="menu_vip_shop")])
            keyboard.append([InlineKeyboardButton("🔙 Menu principal", callback_data="start_menu")])
            return message, InlineKeyboardMarkup(keyboard)

        # Rôles opérationnels (Staff / Admin / Owner)
        message = (
            "⚙️ <b>PARAMÈTRES</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Sélectionnez un module de configuration :"
        )
        keyboard = []

        # 1. 🤖 GESTION DU BOT (Admin & Owner)
        if is_admin:
            keyboard.append([
                InlineKeyboardButton("🤖 GESTION DU BOT", callback_data="gerer_bot")
            ])

        # 2. 🧠 ADMINS | 🎣 PIÉGEURS (Staff)
        if is_admin:
            keyboard.append([
                InlineKeyboardButton("🧠 ADMINS", callback_data="gerer_admins"),
                InlineKeyboardButton("🎣 PIÉGEURS", callback_data="gerer_staff")
            ])

        # 3. 🏷️ MODIFIER MON ALIAS 🏷️
        keyboard.append([
            InlineKeyboardButton("🏷️ MODIFIER MON ALIAS 🏷️", callback_data="modifier_alias")
        ])

        # 4. 📦 ARCHIVES | 🧮 STATS
        keyboard.append([
            InlineKeyboardButton("📦 ARCHIVES", callback_data="admin_global_archives" if is_admin else "demandes_archives"),
            InlineKeyboardButton("🧮 STATS", callback_data="bot_stats" if is_admin else f"profil_admin_{user_id}")
        ])

        # 5. 💰 PAIEMENT 💰
        keyboard.append([
            InlineKeyboardButton("💰 PAIEMENT 💰", callback_data="staff_payment_settings")
        ])

        # 6. ⭐ VIP | ✨ OPTIONS
        keyboard.append([
            InlineKeyboardButton("⭐ VIP", callback_data="gerer_vips" if is_admin else "menu_vip_shop"),
            InlineKeyboardButton("✨ OPTIONS", callback_data="menu_vip_settings" if is_vip else "menu_vip_shop")
        ])

        # 7. 🔔 NOTIFICATIONS 🔔
        keyboard.append([
            InlineKeyboardButton("🔔 NOTIFICATIONS 🔔", callback_data="menu_notifs")
        ])

        # Retour
        keyboard.append([
            InlineKeyboardButton("⬅️ RETOUR", callback_data="start_menu")
        ])

        return message, InlineKeyboardMarkup(keyboard)

    # ========== SOUS-MENU MODES DE PAIEMENT DU STAFF ==========

    def get_staff_payment_settings_menu(self, staff_id: int):
        """Affiche les bascules de moyens de paiement pour l'opérateur."""
        methods = self.db_manager.get_staff_payment_methods(staff_id)
        st_stars = "🟢 Activé" if methods["accept_stars"] else "🔴 Désactivé"
        st_direct = "🟢 Activé" if methods["accept_direct"] else "🔴 Désactivé"

        text = (
            "💳 <b>MODES DE PAIEMENT ACCEPTÉS</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Définissez les méthodes de règlement proposées pour les dossiers prioritaires :\n\n"
            f"• <b>Telegram Stars :</b> {st_stars}\n"
            f"• <b>Paiement direct (PayPal, virement, etc.) :</b> {st_direct}\n\n"
            "⚠️ <i>Vous devez conserver au minimum un mode de paiement actif.</i>"
        )
        keyboard = [
            [InlineKeyboardButton(f"⭐ Telegram Stars : {st_stars}", callback_data="toggle_pay_staff_accept_stars")],
            [InlineKeyboardButton(f"💬 Paiement direct : {st_direct}", callback_data="toggle_pay_staff_accept_direct")],
            [InlineKeyboardButton("🔙 Retour aux paramètres", callback_data="parametres")]
        ]
        return text, InlineKeyboardMarkup(keyboard)

    # ========== SOUS-MENU GESTION DU BOT (CONFORME MAQUETTE) ==========

    def get_gerer_bot_menu(self):
        """Menu de contrôle du bot conforme à la maquette GESTION DU BOT."""
        try:
            demandes_ouvertes = self.config.are_demandes_enabled()
        except Exception:
            demandes_ouvertes = True

        demandes_suspendues = not demandes_ouvertes
        label_suspension = (
            "✅ RÉACTIVER LES DEMANDES ✅"
            if demandes_suspendues
            else "❌ SUSPENDRE LES DEMANDES ❌"
        )

        message = (
            "🤖 <b>GESTION DU BOT</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Panneau de contrôle système de la plateforme :"
        )

        keyboard = [
            # 1. SUSPENDRE LES DEMANDES
            [InlineKeyboardButton(label_suspension, callback_data="bot_toggle_suspension")],

            # 2. ⌛ LIMITES | ⚖️ QUOTAS
            [
                InlineKeyboardButton("⌛ LIMITES", callback_data="menu_limits"),
                InlineKeyboardButton("⚖️ QUOTAS", callback_data="menu_channels")
            ],

            # 3. 📦 ARCHIVAGE | 🛠️ MAINTENANCE
            [
                InlineKeyboardButton("📦 ARCHIVAGE", callback_data="menu_delais"),
                InlineKeyboardButton("🛠️ MAINTENANCE", callback_data="maintenance")
            ],

            # 4. 🔑 ADHÉSION | 📢 CONTACT
            [
                InlineKeyboardButton("🔑 ADHÉSION", callback_data="menu_cfg_group"),
                InlineKeyboardButton("📢 CONTACT", callback_data="menu_cfg_support")
            ],

            # 5. ⛔ ZONE DE DANGER ⛔
            [InlineKeyboardButton("⛔ ZONE DE DANGER ⛔", callback_data="menu_danger_zone")],

            # Retour aux paramètres
            [InlineKeyboardButton("⬅️ RETOUR", callback_data="parametres")]
        ]

        return message, InlineKeyboardMarkup(keyboard)

    # ========== SOUS-MENU ZONE DE DANGER (Owner Only) ==========

    def get_danger_zone_menu(self):
        """Affiche le menu de la Zone de Danger (Réservé au Propriétaire)."""
        text = (
            "🚨 <b>ZONE DE DANGER — PURGE DES DONNÉES</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "⚠️ <b>Attention :</b> Les actions lancées ici effacent immédiatement et définitivement les données ciblées dans MySQL.\n\n"
            "<i>Sélectionnez le lot de données à vider :</i>"
        )
        keyboard = [
            [
                InlineKeyboardButton("📦 Vider Archives", callback_data="danger_purge_archives"),
                InlineKeyboardButton("📋 Vider Demandes", callback_data="danger_purge_demandes")
            ],
            [
                InlineKeyboardButton("👤 Vider Clients", callback_data="danger_purge_users"),
                InlineKeyboardButton("🦈 Vider Staff", callback_data="danger_purge_staff")
            ],
            [
                InlineKeyboardButton("🛡️ Vider Managers", callback_data="danger_purge_admins"),
                InlineKeyboardButton("💥 PURGE TOTALE", callback_data="danger_purge_totale")
            ],
            [InlineKeyboardButton("🔙 Retour gestion bot", callback_data="gerer_bot")]
        ]
        return text, InlineKeyboardMarkup(keyboard)

    # ========== SOUS-MENU ADHÉSION OBLIGATOIRE GROUPE (Owner Only) ==========

    def get_group_subscription_config_menu(self):
        """Menu interactif de configuration de l'adhésion obligatoire."""
        is_enabled = self.db_manager.is_required_group_enabled()
        group_id = self.db_manager.get_required_group_id()
        link = self.db_manager.get_group_subscription_link()

        statut_badge = "🟢 <b>Active</b>" if is_enabled else "🔴 <b>Désactivée</b>"
        toggle_btn_label = "🔴 Désactiver le contrôle" if is_enabled else "🟢 Activer le contrôle"
        gid_str = f"<code>{group_id}</code>" if group_id != 0 else "<i>Non configuré (0)</i>"

        text = (
            "📢 <b>ADHÉSION OBLIGATOIRE AU GROUPE</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>État :</b> {statut_badge}\n"
            f"• <b>Chat ID du groupe :</b> {gid_str}\n"
            f"• <b>Lien d'inscription :</b> <code>{html.escape(link)}</code>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "<i>Si activé, tout utilisateur absent du groupe ne peut pas soumettre de demande.</i>"
        )
        keyboard = [
            [InlineKeyboardButton(toggle_btn_label, callback_data="toggle_cfg_group_enabled")],
            [
                InlineKeyboardButton("🆔 Régler Chat ID", callback_data="set_cfg_group_id"),
                InlineKeyboardButton("🔗 Régler Lien / Bot", callback_data="set_cfg_group_link")
            ],
            [InlineKeyboardButton("🔙 Retour gestion bot", callback_data="gerer_bot")]
        ]
        return text, InlineKeyboardMarkup(keyboard)

    # ========== SOUS-MENU CONTACT SUPPORT (Owner Only) ==========

    def get_support_config_menu(self):
        """Menu de configuration du contact support."""
        contact = self.db_manager.get_support_contact()
        text = (
            "🎧 <b>CANAL DU SUPPORT OFFICIEL</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Contact actuel :</b> <code>{html.escape(contact)}</code>\n\n"
            "<i>Ce lien/pseudo est communiqué aux demandeurs en cas d'interrogation ou de blocage.</i>"
        )
        keyboard = [
            [InlineKeyboardButton("✏️ Modifier le contact support", callback_data="set_cfg_support_contact")],
            [InlineKeyboardButton("🔙 Retour gestion bot", callback_data="gerer_bot")]
        ]
        return text, InlineKeyboardMarkup(keyboard)

    # ========== SOUS-MENU CANAUX & COMBINAISONS (Toggles ON/OFF) ==========

    def get_channels_menu(self):
        """Menu interactif de bascule pour les quatre canaux combinés (Hétéro/Gay × Insta/Snap)."""
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
            [InlineKeyboardButton("🔙 Retour gestion bot", callback_data="gerer_bot")]
        ]

        text = (
            "🎛️ <b>FLUX OPÉRATIONNELS COMBINÉS</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Activez ou coupez les nouveaux dépôts par canal spécifique :\n\n"
            f"• <b>Insta Hétéro :</b> {'✅ Ouvert' if h_insta else '❌ Coupé'}\n"
            f"• <b>Snap Hétéro :</b> {'✅ Ouvert' if h_snap else '❌ Coupé'}\n"
            f"• <b>Insta Gay :</b> {'✅ Ouvert' if g_insta else '❌ Coupé'}\n"
            f"• <b>Snap Gay :</b> {'✅ Ouvert' if g_snap else '❌ Coupé'}\n\n"
            "<i>(Les dossiers Bi s'orientent selon le réseau concerné)</i>"
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
            "⚙️ <b>PLAFONDS & QUOTAS APPLICATIFS</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🌐 <b>Plafond total simultané :</b> {fmt(max_total)}\n"
            f"👤 <b>Plafond par demandeur :</b> {fmt(max_user)}\n\n"
            "<b>Plafonds par canal :</b>\n"
            f"• 📷 Insta Hétéro : {fmt(m_hi)} | 👻 Snap Hétéro : {fmt(m_hs)}\n"
            f"• 📷 Insta Gay : {fmt(m_gi)} | 👻 Snap Gay : {fmt(m_gs)}\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "<i>Ajustez via les boutons ou saisissez une valeur précise :</i>"
        )

        keyboard = [
            [
                InlineKeyboardButton("🌐 Total -5", callback_data="limit_total_sub5"),
                InlineKeyboardButton("Illimité (0)", callback_data="limit_total_0"),
                InlineKeyboardButton("Total +5", callback_data="limit_total_add5"),
            ],
            [
                InlineKeyboardButton("👤 Client -1", callback_data="limit_user_sub1"),
                InlineKeyboardButton("Défaut (3)", callback_data="limit_user_3"),
                InlineKeyboardButton("Client +1", callback_data="limit_user_add1"),
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
                InlineKeyboardButton("✏️ Saisie libre Total", callback_data="limit_input_total"),
                InlineKeyboardButton("✏️ Saisie libre Client", callback_data="limit_input_user"),
            ],
            [
                InlineKeyboardButton("🔙 Retour gestion bot", callback_data="gerer_bot")
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
                message = "👥 <b>ÉQUIPE OPÉRATIONNELLE (STAFF)</b>\n━━━━━━━━━━━━━━━━━━━━\n📭 Aucun opérateur enregistré."
            else:
                message = (
                    f"👥 <b>ÉQUIPE OPÉRATIONNELLE ({len(staff_members)} membre{'s' if len(staff_members) > 1 else ''})</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━\n\n"
                )
                for st in staff_members:
                    raw_pseudo = f"@{st['username']}" if st.get("username") else "Sans pseudo"
                    pseudo = html.escape(str(raw_pseudo))

                    dt_added = st.get("date_added")
                    date_str = format_datetime_fr(dt_added)
                    par_qui = html.escape(str(st.get("nom_ajouteur") or "Direction"))
                    alias_esc = html.escape(str(st.get("alias") or f"Staff_{st['user_id']}"))

                    res_tag = st.get("perm_reseaux") or "all"
                    type_tag = st.get("perm_type") or "all"
                    ori_tag = st.get("perm_orientation") or "all"

                    res_label = {"all": "Tous réseaux", "insta": "Insta seul", "snap": "Snap seul"}.get(res_tag, str(res_tag))
                    type_label = {"all": "Tous", "prio_only": "Prio", "standard_only": "Standard"}.get(type_tag, str(type_tag))
                    ori_label = {"all": "Toutes", "hetero": "Hétéro/Bi", "gay": "Gay/Bi", "bi": "Bi"}.get(ori_tag, str(ori_tag))
                    statut_dispo = "⏸️ <i>(En pause)</i>" if st.get("is_paused") else "🟢 <i>(En service)</i>"

                    message += (
                        f"• <b>{alias_esc}</b> {statut_dispo} ({pseudo})\n"
                        f"  🆔 <code>{st['user_id']}</code> | Recruté le {date_str} par {par_qui}\n"
                        f"  🛡️ <i>Accès : {html.escape(res_label)} | {html.escape(type_label)} | {html.escape(ori_label)}</i>\n\n"
                    )

                    keyboard.append([
                        InlineKeyboardButton(f"🛡️ Permissions : {st.get('alias', st['user_id'])}", callback_data=f"perm_staff_{st['user_id']}"),
                        InlineKeyboardButton("📊 Stats", callback_data=f"profil_admin_{st['user_id']}")
                    ])

            keyboard.append([
                InlineKeyboardButton("➕ Recruter un opérateur", callback_data="staff_ajouter"),
                InlineKeyboardButton("➖ Révoquer un opérateur", callback_data="staff_supprimer")
            ])
            keyboard.append([InlineKeyboardButton("🔙 Retour aux paramètres", callback_data="parametres")])

        except Exception as exc:
            logger.error("Erreur menu gestion staff : %s", exc, exc_info=True)
            message = "👥 <b>Gestion de l'Équipe Staff</b>\n\n❌ Erreur de lecture de la base."
            keyboard = [[InlineKeyboardButton("🔙 Retour aux paramètres", callback_data="parametres")]]

        return message, InlineKeyboardMarkup(keyboard)

    # ========== SOUS-MENU GÉRER LES ADMINS / MANAGERS (Owner Only) ==========

    def get_gerer_admins_menu(self):
        """Menu de gestion des administrateurs/managers (table admins)."""
        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT a.user_id, a.alias, a.is_owner, a.date_added,
                           a.can_view_archives, a.can_monitor_staff,
                           u.username, u.first_name
                    FROM admins a
                    LEFT JOIN users u ON a.user_id = u.user_id
                    ORDER BY a.is_owner DESC, a.date_added DESC
                    """
                )
                admins = cursor.fetchall()

            keyboard = []

            if not admins:
                message = "🛡️ <b>CORPS ADMINISTRATIF</b>\n━━━━━━━━━━━━━━━━━━━━\n📭 Aucun administrateur secondaire configuré."
            else:
                message = (
                    f"🛡️ <b>CORPS ADMINISTRATIF ({len(admins)})</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━\n\n"
                )
                for admin in admins:
                    raw_pseudo = f"@{admin['username']}" if admin.get("username") else "Sans pseudo"
                    pseudo = html.escape(str(raw_pseudo))
                    alias_esc = html.escape(str(admin.get("alias") or f"Admin_{admin['user_id']}"))
                    role_badge = "👑 <b>[Co-Gérant]</b>" if admin.get("is_owner") else "🛡️ <b>[Manager]</b>"

                    dt_added = admin.get("date_added")
                    date_str = format_datetime_fr(dt_added)

                    arch_badge = "✅" if admin.get("can_view_archives") else "❌"
                    mon_badge = "✅" if admin.get("can_monitor_staff") else "❌"
                    perm_info = f" | Archives: {arch_badge} | Suivi: {mon_badge}" if not admin.get("is_owner") else ""

                    message += (
                        f"• {role_badge} <b>{alias_esc}</b> ({pseudo})\n"
                        f"  🆔 <code>{admin['user_id']}</code> | Depuis le {date_str}{perm_info}\n\n"
                    )

                    if not admin.get("is_owner"):
                        keyboard.append([
                            InlineKeyboardButton(f"⚙️ Droits : {admin.get('alias', admin['user_id'])}", callback_data=f"perm_admin_{admin['user_id']}")
                        ])

            keyboard.append([
                InlineKeyboardButton("➕ Nommer un manager", callback_data="admin_ajouter"),
                InlineKeyboardButton("➖ Révoquer un manager", callback_data="admin_supprimer")
            ])
            keyboard.append([InlineKeyboardButton("🔙 Retour aux paramètres", callback_data="parametres")])

        except Exception as exc:
            logger.error("Erreur génération menu admins : %s", exc, exc_info=True)
            message = "🛡️ <b>Gestion des Administrateurs</b>\n\n❌ Erreur de lecture des données."
            keyboard = [[InlineKeyboardButton("🔙 Retour aux paramètres", callback_data="parametres")]]

        return message, InlineKeyboardMarkup(keyboard)

    # ========== SOUS-MENU GÉRER LES MEMBRES VIP ==========

    def get_gerer_vips_menu(self):
        """Affiche la liste des membres VIP et les outils d'attribution."""
        try:
            vips = self.db_manager.get_vip_users_list()
            keyboard = []

            if not vips:
                message = "⭐ <b>GESTION DU CERCLE VIP</b>\n━━━━━━━━━━━━━━━━━━━━\n📭 Aucun membre VIP actif pour le moment."
            else:
                message = (
                    f"⭐ <b>CERCLE DES MEMBRES VIP ({len(vips)})</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━\n\n"
                )
                for v in vips:
                    nom = html.escape(str(v.get("first_name") or "Utilisateur"))
                    pseudo = f"(@{html.escape(str(v['username']))})" if v.get("username") else ""
                    until = v.get("vip_until")
                    if until:
                        status_str = f"Expire le {format_datetime_fr(until)}"
                    else:
                        status_str = "👑 À vie"

                    message += (
                        f"• <b>{nom}</b> {pseudo}\n"
                        f"  🆔 <code>{v['user_id']}</code> | <i>{status_str}</i>\n\n"
                    )

            keyboard.append([
                InlineKeyboardButton("➕ Promouvoir un membre", callback_data="owner_add_vip"),
                InlineKeyboardButton("➖ Révoquer un accès VIP", callback_data="owner_remove_vip")
            ])
            keyboard.append([InlineKeyboardButton("🔙 Retour aux paramètres", callback_data="parametres")])

        except Exception as exc:
            logger.error("Erreur génération menu VIP : %s", exc, exc_info=True)
            message = "⭐ <b>Gestion des Membres VIP</b>\n\n❌ Erreur de lecture des données."
            keyboard = [[InlineKeyboardButton("🔙 Retour aux paramètres", callback_data="parametres")]]

        return message, InlineKeyboardMarkup(keyboard)

    # ========== SOUS-MENU BOUTIQUE VIP (Telegram Stars) ==========

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
                InlineKeyboardButton("⚙️ Mes préférences de référent", callback_data="menu_vip_settings")
            ])

        keyboard.extend([
            [InlineKeyboardButton("⭐ S'abonner pour 30 jours (250 ⭐️)", callback_data="buy_vip_month")],
            [InlineKeyboardButton("🔙 Menu principal", callback_data="start_menu")]
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
            "gerer_demandes": lambda: self.get_gerer_demandes_menu(user_id),
            "parametres": lambda: self.get_parametres_menu(user_id),
            "staff_payment_settings": lambda: self.get_staff_payment_settings_menu(user_id),
            "gerer_staff": self.get_gerer_staff_menu,
            "gerer_admins": self.get_gerer_admins_menu,
            "gerer_vips": self.get_gerer_vips_menu,
            "menu_vip_shop": lambda: self.get_vip_shop_menu(is_vip=is_vip),
            "gerer_bot": self.get_gerer_bot_menu,
            "bot_toggle_suspension": lambda: (
                self.config.disable_demandes() if self.config.are_demandes_enabled() else self.config.enable_demandes(),
                self.get_gerer_bot_menu()[0],
                self.get_gerer_bot_menu()[1]
            ),
            "menu_danger_zone": self.get_danger_zone_menu,
            "menu_cfg_group": self.get_group_subscription_config_menu,
            "menu_cfg_support": self.get_support_config_menu,
            "menu_channels": self.get_channels_menu,
            "menu_limits": self.get_limits_menu,
        }

        handler = routing_map.get(callback_data)
        if handler:
            res = handler()
            if isinstance(res, tuple) and len(res) == 3:
                return res[1], res[2]
            return res
        return None, None