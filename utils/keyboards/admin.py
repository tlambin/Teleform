"""Constructeur des menus d'administration, supervision et gouvernance globale."""

import html
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from .helpers import format_datetime_fr

logger = logging.getLogger(__name__)


class AdminKeyboards:
    """Génère les vues de contrôle du bot, quotas, canaux, gestion d'équipe et purges."""

    def __init__(self, config, db_manager, role_resolver):
        self.config = config
        self.db_manager = db_manager
        self._get_user_role = role_resolver

    def get_admin_parametres_menu(self, user_id: int):
        """Construit le panneau Paramètres complet pour Staff, Admins et Owners."""
        user_role = self._get_user_role(user_id)
        is_admin = user_role in ["admin", "owner"]
        is_vip = self.db_manager.is_user_vip(user_id)

        message = (
            "⚙️ <b>PARAMÈTRES</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Sélectionnez une rubrique :"
        )
        keyboard = []

        if is_admin:
            keyboard.append([InlineKeyboardButton("🤖 GESTION DU BOT 🤖", callback_data="gerer_bot")])
            keyboard.append([
                InlineKeyboardButton("🧠 ADMINS", callback_data="gerer_admins"),
                InlineKeyboardButton("🎣 PIÉGEURS", callback_data="gerer_staff"),
            ])

        keyboard.append([InlineKeyboardButton("👤 MON PROFIL 👤", callback_data="menu_mon_profil")])

        privs = self.db_manager.get_admin_privileges(user_id)
        can_see_stats = is_admin and (privs.get("is_owner") or privs.get("can_view_stats"))
        can_see_archives = is_admin and (privs.get("is_owner") or privs.get("can_view_archives"))

        if can_see_stats or can_see_archives:
            stats_btn = InlineKeyboardButton(
                "🧮 STATS",
                callback_data="bot_stats" if can_see_stats else "stat_access_denied",
            )
            archives_btn = InlineKeyboardButton(
                "📦 ARCHIVES",
                callback_data="admin_global_archives" if can_see_archives else "arch_access_denied",
            )
            keyboard.append([stats_btn, archives_btn])

        if is_admin:
            keyboard.append([InlineKeyboardButton("👥 MEMBRES 👥", callback_data="menu_membres")])

        if is_vip:
            keyboard.append([InlineKeyboardButton("✨ PRÉFÉRENCES VIP ✨", callback_data="menu_vip_settings")])
        else:
            keyboard.append([InlineKeyboardButton("⭐ DEVENIR VIP ⭐", callback_data="menu_vip_shop")])

        if user_role == "staff":
            keyboard.append([InlineKeyboardButton("💬 CONTACTER UN ADMIN", callback_data="contacter_owner")])

        keyboard.append([InlineKeyboardButton("⬅️ RETOUR", callback_data="start_menu")])
        return message, InlineKeyboardMarkup(keyboard)

    def get_gerer_bot_menu(self):
        """Menu de contrôle du bot système."""
        val_demandes = str(self.db_manager.get_config_value("demandes_enabled", "true")).lower()
        demandes_ouvertes = val_demandes in ("true", "1", "yes")

        etat_badge = "🟢 <b>OUVERTES (Actives)</b>" if demandes_ouvertes else "🔴 <b>SUSPENDUES (Fermées)</b>"
        label_suspension = (
            "❌ SUSPENDRE LES DEMANDES ❌" if demandes_ouvertes else "✅ RÉACTIVER LES DEMANDES ✅"
        )

        message = (
            "🤖 <b>GESTION DU BOT</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>État des demandes :</b> {etat_badge}\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "Panneau de contrôle système de la plateforme :"
        )
        keyboard = [
            [InlineKeyboardButton(label_suspension, callback_data="bot_toggle_suspension")],
            [
                InlineKeyboardButton("🌡️ QUOTAS", callback_data="menu_limits"),
                InlineKeyboardButton("🎯 CIBLES", callback_data="menu_channels"),
            ],
            [
                InlineKeyboardButton("⏳ DÉLAIS", callback_data="menu_delais"),
                InlineKeyboardButton("🛠️ MAINTENANCE", callback_data="maintenance"),
            ],
            [
                InlineKeyboardButton("🔑 ADHÉSION", callback_data="menu_cfg_group"),
                InlineKeyboardButton("📢 CONTACT", callback_data="menu_cfg_support"),
            ],
            [InlineKeyboardButton("⛔ ZONE DE DANGER ⛔", callback_data="menu_danger_zone")],
            [InlineKeyboardButton("⬅️ RETOUR", callback_data="parametres")],
        ]
        return message, InlineKeyboardMarkup(keyboard)

    def get_danger_zone_menu(self):
        """Affiche le menu de purge de la zone de danger (Owner only)."""
        text = (
            "🚨 <b>ZONE DE DANGER — PURGE DES DONNÉES</b> 🚨\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "⚠️ <b>Attention :</b> Les actions lancées ici effacent immédiatement et définitivement les données ciblées dans MySQL.\n\n"
            "<i>Sélectionnez le lot de données à vider :</i>"
        )
        keyboard = [
            [
                InlineKeyboardButton("📦 VIDER ARCHIVES", callback_data="danger_purge_archives"),
                InlineKeyboardButton("📋 VIDER DEMANDES", callback_data="danger_purge_demandes"),
            ],
            [
                InlineKeyboardButton("👤 VIDER CLIENTS", callback_data="danger_purge_users"),
                InlineKeyboardButton("🦈 VIDER STAFF", callback_data="danger_purge_staff"),
            ],
            [
                InlineKeyboardButton("🛡️ VIDER MANAGERS", callback_data="danger_purge_admins"),
                InlineKeyboardButton("⚙️ VIDER CONFIG", callback_data="danger_purge_config"),
            ],
            [InlineKeyboardButton("💥 PURGE TOTALE 💥", callback_data="danger_purge_totale")],
            [InlineKeyboardButton("⬅️ RETOUR ⬅️", callback_data="gerer_bot")],
        ]
        return text, InlineKeyboardMarkup(keyboard)

    def get_group_subscription_config_menu(self):
        """Menu de configuration de l'adhésion obligatoire."""
        is_enabled = self.db_manager.is_required_group_enabled()
        group_id = self.db_manager.get_required_group_id()
        link = self.db_manager.get_group_subscription_link()

        statut_badge = "🟢 <b>ACTIVE</b>" if is_enabled else "🔴 <b>DÉSACTIVÉE</b>"
        toggle_btn_label = "🔴 DÉSACTIVER LE CONTRÔLE" if is_enabled else "🟢 ACTIVER LE CONTRÔLE"
        gid_str = f"<code>{group_id}</code>" if group_id != 0 else "<i>Non configuré (0)</i>"

        text = (
            "📢 <b>ADHÉSION OBLIGATOIRE</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "<i>Si activé, tout utilisateur absent du groupe ne peut pas utiliser le bot.</i>\n\n"
            f"{statut_badge}\n\n"
            f"<b>GROUPE :</b> {gid_str}\n"
            f"<b>LIEN :</b> <code>{html.escape(link)}</code>\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )
        keyboard = [
            [InlineKeyboardButton(toggle_btn_label, callback_data="toggle_cfg_group_enabled")],
            [
                InlineKeyboardButton("🆔 GROUPE", callback_data="set_cfg_group_id"),
                InlineKeyboardButton("🔗 LIEN", callback_data="set_cfg_group_link"),
            ],
            [InlineKeyboardButton("⬅️ RETOUR", callback_data="gerer_bot")],
        ]
        return text, InlineKeyboardMarkup(keyboard)

    def get_support_config_menu(self):
        """Menu de configuration du canal support officiel."""
        contact = self.db_manager.get_support_contact()
        text = (
            "🎧 <b>CANAL DU SUPPORT OFFICIEL</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Contact actuel :</b> <code>{html.escape(contact)}</code>\n\n"
            "<i>Ce lien/pseudo est communiqué aux demandeurs en cas d'interrogation ou de blocage.</i>"
        )
        keyboard = [
            [InlineKeyboardButton("✏️ MODIFIER", callback_data="set_cfg_support_contact")],
            [InlineKeyboardButton("⬅️ RETOUR", callback_data="gerer_bot")],
        ]
        return text, InlineKeyboardMarkup(keyboard)

    def get_channels_menu(self):
        """Menu de gestion et d'activation des cibles avec voyants préfixés."""
        hi = self.db_manager.is_channel_combination_allowed("hetero", "insta")
        hs = self.db_manager.is_channel_combination_allowed("hetero", "snap")
        gi = self.db_manager.is_channel_combination_allowed("gay", "insta")
        gs = self.db_manager.is_channel_combination_allowed("gay", "snap")

        def s_badge(val: bool) -> str:
            return "🟢" if val else "🔴"

        message = (
            "🎯 <b>GESTION DES CIBLES</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Activer / Désactiver les demandes par cible :\n\n"
            f"{s_badge(hi)} HÉTÉRO - INSTA\n"
            f"{s_badge(hs)} HÉTÉRO - SNAP\n\n"
            f"{s_badge(gi)} GAY - INSTA\n"
            f"{s_badge(gs)} GAY - SNAP\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "<i>Les Bi s'orientent selon le réseau concerné.</i>"
        )
        keyboard = [
            [
                InlineKeyboardButton(f"{s_badge(hi)} HÉTÉRO - INSTA", callback_data="toggle_allow_hetero_insta"),
                InlineKeyboardButton(f"{s_badge(hs)} HÉTÉRO - SNAP", callback_data="toggle_allow_hetero_snap"),
            ],
            [
                InlineKeyboardButton(f"{s_badge(gi)} GAY - INSTA", callback_data="toggle_allow_gay_insta"),
                InlineKeyboardButton(f"{s_badge(gs)} GAY - SNAP", callback_data="toggle_allow_gay_snap"),
            ],
            [InlineKeyboardButton("⬅️ RETOUR", callback_data="gerer_bot")],
        ]
        return message, InlineKeyboardMarkup(keyboard)

    def get_limits_menu(self):
        """Ajustement des quotas avec contrôle par réseau."""
        max_total = self.config.get_max_total_demandes()
        max_user = self.config.get_max_demandes_per_user()

        m_hi = int(self.db_manager.get_config_value("max_hetero_insta", "0") or 0)
        m_hs = int(self.db_manager.get_config_value("max_hetero_snap", "0") or 0)
        m_gi = int(self.db_manager.get_config_value("max_gay_insta", "0") or 0)
        m_gs = int(self.db_manager.get_config_value("max_gay_snap", "0") or 0)

        def fmt(val: int) -> str:
            return f"<b>{val}</b>" if val > 0 else "<i>Illimité</i>"

        message = (
            "🌡️ <b>GESTION DES QUOTAS :</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🌐 <b>TOTAL :</b> {fmt(max_total)}\n"
            f"👤 <b>CLIENT :</b> {fmt(max_user)}\n\n"
            f"🕺 <b>HÉTÉRO :</b> {m_hi} INSTA | {m_hs} SNAP\n"
            f"🏳️‍🌈 <b>GAY :</b> {m_gi} INSTA | {m_gs} SNAP\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "<i>Ajustez via les boutons ou saisissez une valeur précise :</i>"
        )
        keyboard = [
            [InlineKeyboardButton("🌐 TOTAL", callback_data="limit_input_total")],
            [
                InlineKeyboardButton("- 5", callback_data="limit_total_sub5"),
                InlineKeyboardButton("ILLIMITÉ", callback_data="limit_total_0"),
                InlineKeyboardButton("+ 5", callback_data="limit_total_add5"),
            ],
            [InlineKeyboardButton("👤 CLIENT", callback_data="limit_input_user")],
            [
                InlineKeyboardButton("- 1", callback_data="limit_user_sub1"),
                InlineKeyboardButton("DÉFAUT (3)", callback_data="limit_user_3"),
                InlineKeyboardButton("+ 1", callback_data="limit_user_add1"),
            ],
            [
                InlineKeyboardButton("🕺 INSTA", callback_data="limit_input_hetero_insta"),
                InlineKeyboardButton("🕺 SNAP", callback_data="limit_input_hetero_snap"),
            ],
            [
                InlineKeyboardButton("🏳️‍🌈 INSTA", callback_data="limit_input_gay_insta"),
                InlineKeyboardButton("🏳️‍🌈 SNAP", callback_data="limit_input_gay_snap"),
            ],
            [InlineKeyboardButton("⬅️ RETOUR", callback_data="gerer_bot")],
        ]
        return message, InlineKeyboardMarkup(keyboard)

    def get_membres_menu(self):
        """Sous-menu unifié regroupant la recherche, la gestion VIP et les bannis."""
        text = (
            "👥 <b>GESTION DES MEMBRES</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Sélectionnez une catégorie pour gérer les comptes de la plateforme :\n\n"
            "• <b>Rechercher un membre :</b> Trouver un utilisateur par ID ou pseudo pour consulter sa fiche et le gérer.\n"
            "• <b>Membres VIP :</b> Gérer les privilèges et abonnements VIP.\n"
            "• <b>Liste des bannis :</b> Consulter et réhabiliter les comptes révoqués."
        )
        keyboard = [
            [InlineKeyboardButton("🔍 RECHERCHER UN MEMBRE 🔍", callback_data="search_member_prompt")],
            [InlineKeyboardButton("⭐ MEMBRES VIP ⭐", callback_data="gerer_vips")],
            [InlineKeyboardButton("🚫 LISTE DES BANNIS 🚫", callback_data="liste_bannis_0")],
            [InlineKeyboardButton("⬅️ RETOUR ⬅️", callback_data="parametres")],
        ]
        return text, InlineKeyboardMarkup(keyboard)

    def get_gerer_staff_menu(self):
        """Menu de gestion des employés/opérateurs (table staff)."""
        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT s.user_id, s.alias, s.date_added, s.perm_reseaux, s.perm_type, s.perm_orientation, s.is_paused, s.allow_self_prefs,
                           u.first_name, u.username,
                           u_add.first_name AS nom_ajouteur
                    FROM staff s
                    LEFT JOIN users u ON s.user_id = u.user_id
                    LEFT JOIN users u_add ON s.added_by = u_add.user_id
                    ORDER BY s.date_added DESC
                    """
                )
                staff_members = cursor.fetchall()

            keyboard = [
                [
                    InlineKeyboardButton("➕ RECRUTER", callback_data="staff_ajouter"),
                    InlineKeyboardButton("➖ VIRER", callback_data="staff_supprimer"),
                ]
            ]
            nb_membres = len(staff_members)

            if not staff_members:
                message = (
                    f"🎣 <b>GESTION DES PIÉGEURS ({nb_membres})</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "📭 Aucun piégeur enregistré dans l'équipe."
                )
            else:
                message = (
                    f"🎣 <b>GESTION DES PIÉGEURS ({nb_membres})</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━\n\n"
                )
                for st in staff_members:
                    raw_pseudo = f"@{st['username']}" if st.get("username") else "Sans pseudo"
                    pseudo = html.escape(str(raw_pseudo))
                    dt_added = st.get("date_added")
                    date_str = format_datetime_fr(dt_added)
                    par_qui = html.escape(str(st.get("nom_ajouteur") or "Direction"))
                    alias_raw = str(st.get("alias") or f"Piégeur_{st['user_id']}")
                    alias_esc = html.escape(alias_raw)

                    res_tag = str(st.get("perm_reseaux") or "all").lower()
                    type_tag = str(st.get("perm_type") or "all").lower()
                    ori_tag = str(st.get("perm_orientation") or "all").lower()

                    res_map = {"insta": "sur Insta", "snap": "sur Snap", "all": "sur Insta et Snap"}
                    ori_map = {"hetero": "Hétéro", "gay": "Gay", "bi": "Bi", "all": "Hétéro et Gay"}

                    r_txt = res_map.get(res_tag, "sur Insta et Snap")
                    o_txt = ori_map.get(ori_tag, "Hétéro et Gay")
                    perm_readable = f"{o_txt} {r_txt}"
                    if type_tag == "prio_only":
                        perm_readable += ", prioritaire"
                    elif type_tag == "standard_only":
                        perm_readable += ", standard"

                    statut_emoji = "⏸️" if st.get("is_paused") else "🟢"
                    statut_texte = "En pause" if st.get("is_paused") else "En service"

                    message += (
                        f"{statut_emoji} <b>{alias_esc}</b> (<i>{statut_texte}</i>)\n"
                        f"🆔 <code>{st['user_id']}</code> - {pseudo}\n"
                        f"Recruté le {date_str} par {par_qui}\n"
                        f"🛡️ <i>{html.escape(perm_readable)}</i>\n\n"
                    )

                    keyboard.append([
                        InlineKeyboardButton(f"📂 DOSSIERS : {alias_raw.upper()}", callback_data=f"staff_view_demandes_{st['user_id']}_0")
                    ])
                    keyboard.append([
                        InlineKeyboardButton("🛡️ PERMISSIONS", callback_data=f"perm_staff_{st['user_id']}"),
                        InlineKeyboardButton("📊 STATS", callback_data=f"profil_admin_{st['user_id']}"),
                    ])

            keyboard.append([InlineKeyboardButton("⬅️ RETOUR", callback_data="parametres")])

        except Exception as exc:
            logger.error("Erreur menu gestion staff : %s", exc, exc_info=True)
            message = "🎣 <b>GESTION DES PIÉGEURS</b>\n━━━━━━━━━━━━━━━━━━━━\n❌ Erreur de lecture de la base."
            keyboard = [[InlineKeyboardButton("⬅️ RETOUR", callback_data="parametres")]]

        return message, InlineKeyboardMarkup(keyboard)

    def get_gerer_admins_menu(self):
        """Menu de gestion des administrateurs/managers (table admins)."""
        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT a.user_id, a.alias, a.is_owner, a.date_added,
                           a.can_view_archives, a.can_monitor_staff, a.can_ban_users,
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
                    ban_badge = "✅" if admin.get("can_ban_users") else "❌"
                    perm_info = f" | Archives: {arch_badge} | Suivi: {mon_badge} | Ban: {ban_badge}" if not admin.get("is_owner") else ""

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
                InlineKeyboardButton("➖ Révoquer un manager", callback_data="admin_supprimer"),
            ])
            keyboard.append([InlineKeyboardButton("⬅️ RETOUR", callback_data="parametres")])

        except Exception as exc:
            logger.error("Erreur génération menu admins : %s", exc, exc_info=True)
            message = "🛡️ <b>Gestion des Administrateurs</b>\n\n❌ Erreur de lecture des données."
            keyboard = [[InlineKeyboardButton("⬅️ RETOUR", callback_data="parametres")]]

        return message, InlineKeyboardMarkup(keyboard)

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
                    status_str = f"Expire le {format_datetime_fr(until)}" if until else "👑 À vie"

                    message += (
                        f"• <b>{nom}</b> {pseudo}\n"
                        f"  🆔 <code>{v['user_id']}</code> | <i>{status_str}</i>\n\n"
                    )

            keyboard.append([
                InlineKeyboardButton("➕ Promouvoir un membre", callback_data="owner_add_vip"),
                InlineKeyboardButton("➖ Révoquer un accès VIP", callback_data="owner_remove_vip"),
            ])
            keyboard.append([InlineKeyboardButton("⬅️ RETOUR", callback_data="menu_membres")])

        except Exception as exc:
            logger.error("Erreur génération menu VIP : %s", exc, exc_info=True)
            message = "⭐ <b>Gestion des Membres VIP</b>\n\n❌ Erreur de lecture des données."
            keyboard = [[InlineKeyboardButton("⬅️ RETOUR", callback_data="menu_membres")]]

        return message, InlineKeyboardMarkup(keyboard)