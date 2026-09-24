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

        # Ligne 1 : 🗳️ CRÉER | 🗂️ MES DEMANDES
        keyboard = [
            [
                InlineKeyboardButton("🗳️ CRÉER", callback_data="new_demande"),
                InlineKeyboardButton("🗂️ MES DEMANDES", callback_data="voir_demandes")
            ]
        ]

        # Ligne 2 : 🚦 GÉRER LES DEMANDES 🚦 (Staff, Admin, Owner uniquement)
        if user_role in ["staff", "admin", "owner"]:
            keyboard.append([
                InlineKeyboardButton("🚦 GÉRER LES DEMANDES 🚦", callback_data="gerer_demandes")
            ])

        # Ligne 3 : ⭐ DEVENIR VIP ⭐ (affiché UNIQUEMENT pour les demandeurs/clients non-VIP)
        if not is_vip and user_role == "user":
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
            [InlineKeyboardButton(f"📮 DISPONIBLE ({nb_dispo})", callback_data="demandes_disponibles")],
            [InlineKeyboardButton(f"💌 SUIVIES ({nb_suivies})", callback_data="demandes_suivies")],
            [InlineKeyboardButton(f"📦 ARCHIVÉES ({nb_archives})", callback_data="demandes_archives")],
            [InlineKeyboardButton("⬅️ RETOUR", callback_data="start_menu")]
        ]
        return message, InlineKeyboardMarkup(keyboard)

    # ========== MENU PARAMÈTRES ==========

    def get_parametres_menu(self, user_id: int):
        """Construit le panneau Paramètres général avec contact support ou contact admin."""
        user_role = self._get_user_role(user_id)
        is_admin = (user_role in ["admin", "owner"])
        is_staff = (user_role in ["staff", "admin", "owner"])
        is_vip = self.db_manager.is_user_vip(user_id)

        # 1. Demandeur simple / Client
        if not is_staff:
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

            # Bouton Contacter le support (avant RETOUR)
            support_link = self.db_manager.get_support_contact()
            if support_link.startswith("@"):
                support_url = f"https://t.me/{support_link.lstrip('@')}"
            elif support_link.startswith("http://") or support_link.startswith("https://"):
                support_url = support_link
            else:
                support_url = f"https://t.me/{support_link}"

            keyboard.append([InlineKeyboardButton("🎧 CONTACTER LE SUPPORT", url=support_url)])
            keyboard.append([InlineKeyboardButton("⬅️ RETOUR", callback_data="start_menu")])
            return message, InlineKeyboardMarkup(keyboard)

        # 2. Staff / Admin / Owner
        message = (
            "⚙️ <b>PARAMÈTRES</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Sélectionnez une rubrique :"
        )
        keyboard = []

        # 1. 🤖 GESTION DU BOT 🤖 (Admin & Owner)
        if is_admin:
            keyboard.append([
                InlineKeyboardButton("🤖 GESTION DU BOT 🤖", callback_data="gerer_bot")
            ])

        # 2. 🧠 ADMINS | 🎣 PIÉGEURS (Admin & Owner)
        if is_admin:
            keyboard.append([
                InlineKeyboardButton("🧠 ADMINS", callback_data="gerer_admins"),
                InlineKeyboardButton("🎣 PIÉGEURS", callback_data="gerer_staff")
            ])

        # 3. 👤 MON PROFIL 👤 (Accessible à tout le staff / admins)
        keyboard.append([
            InlineKeyboardButton("👤 MON PROFIL 👤", callback_data="menu_mon_profil")
        ])

        # 4. 🧮 STATS | 📦 ARCHIVES (Générales - Uniquement Owner & Admins autorisés)
        privs = self.db_manager.get_admin_privileges(user_id)
        can_see_stats = is_admin and (privs.get("is_owner") or privs.get("can_view_stats"))
        can_see_archives = is_admin and (privs.get("is_owner") or privs.get("can_view_archives"))

        if can_see_stats or can_see_archives:
            stats_btn = InlineKeyboardButton(
                "🧮 STATS",
                callback_data="bot_stats" if can_see_stats else "stat_access_denied"
            )
            archives_btn = InlineKeyboardButton(
                "📦 ARCHIVES",
                callback_data="admin_global_archives" if can_see_archives else "arch_access_denied"
            )
            keyboard.append([stats_btn, archives_btn])

        # 5. ⭐ MEMBRES VIP ⭐ (Gestion du cercle VIP - Admin & Owner)
        if is_admin:
            keyboard.append([
                InlineKeyboardButton("⭐ MEMBRES VIP ⭐", callback_data="gerer_vips")
            ])

        # 6. ✨ PRÉFÉRENCES VIP ✨ (si VIP) OU ⭐ DEVENIR VIP ⭐ (si non VIP)
        if is_vip:
            keyboard.append([
                InlineKeyboardButton("✨ PRÉFÉRENCES VIP ✨", callback_data="menu_vip_settings")
            ])
        else:
            keyboard.append([
                InlineKeyboardButton("⭐ DEVENIR VIP ⭐", callback_data="menu_vip_shop")
            ])

        # 7. Bouton de contact (Staff -> Admin/Direction)
        if user_role == "staff":
            keyboard.append([
                InlineKeyboardButton("💬 CONTACTER UN ADMIN", callback_data="contacter_owner")
            ])

        # 8. ⬅️ RETOUR
        keyboard.append([
            InlineKeyboardButton("⬅️ RETOUR", callback_data="start_menu")
        ])

        return message, InlineKeyboardMarkup(keyboard)

    # ========== SOUS-MENU MON PROFIL ==========

    def get_mon_profil_menu(self, user_id: int):
        """Construit le sous-menu individuel 'MON PROFIL' avec le bouton PRÉFÉRENCES sous NOTIFICATIONS."""
        user_role = self._get_user_role(user_id)
        is_admin = (user_role in ["admin", "owner"])
        is_paused = self.db_manager.is_staff_paused(user_id)
        alias = self.db_manager.get_staff_alias(user_id) or f"Membre_{user_id}"

        statut_dispo = "⏸️ <b>En pause</b>" if is_paused else "🟢 <b>En service</b>"

        message = (
            "👤 <b>MON PROFIL</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Identité :</b> <code>{html.escape(str(alias))}</code>\n"
            f"• <b>Disponibilité :</b> {statut_dispo}\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "Gérez vos paramètres individuels :"
        )
        keyboard = []

        # 1. 🔔 NOTIFICATIONS 🔔
        keyboard.append([
            InlineKeyboardButton("🔔 NOTIFICATIONS 🔔", callback_data="menu_notifs")
        ])

        # 2. 🎯 PRÉFÉRENCES 🎯 (Sous les notifications)
        keyboard.append([
            InlineKeyboardButton("🎯 PRÉFÉRENCES 🎯", callback_data="staff_self_prefs")
        ])

        # 3. ⏸️ SE METTRE EN PAUSE / ▶️ REPRENDRE LE SERVICE
        if is_paused:
            keyboard.append([
                InlineKeyboardButton("▶️ REPRENDRE LE SERVICE ▶️", callback_data="admin_resume")
            ])
        else:
            keyboard.append([
                InlineKeyboardButton("⏸️ SE METTRE EN PAUSE ⏸️", callback_data="admin_pause_prompt")
            ])

        # 4. 🏷️ MODIFIER MON ALIAS 🏷️ (si admin ou staff non encore verrouillé)
        if is_admin or self.db_manager.can_staff_edit_alias(user_id):
            keyboard.append([
                InlineKeyboardButton("🏷️ MODIFIER MON ALIAS 🏷️", callback_data="modifier_alias")
            ])

        # 5. 💰 MOYEN DE PAIEMENT 💰
        keyboard.append([
            InlineKeyboardButton("💰 MOYEN DE PAIEMENT 💰", callback_data="staff_payment_settings")
        ])

        # 6. 🧮 MES STATS | 📦 MES ARCHIVES (Performances individuelles du membre)
        keyboard.append([
            InlineKeyboardButton("🧮 MES STATS", callback_data=f"profil_admin_{user_id}"),
            InlineKeyboardButton("📦 MES ARCHIVES", callback_data="demandes_archives")
        ])

        # 7. ⬅️ RETOUR (vers Paramètres)
        keyboard.append([
            InlineKeyboardButton("⬅️ RETOUR", callback_data="parametres")
        ])

        return message, InlineKeyboardMarkup(keyboard)

    # ========== SOUS-MENU AUTONOMIE PRÉFÉRENCES OPÉRATEUR (CIBLES) ==========

    def get_staff_self_preferences_menu(self, user_id: int):
        """Menu interactif permettant à l'opérateur de configurer lui-même ses cibles avec coches dynamiques."""
        can_edit = self.db_manager.can_staff_edit_preferences(user_id)
        user_role = self._get_user_role(user_id)
        is_admin = (user_role in ["admin", "owner"])

        perms = self.db_manager.get_staff_permissions(user_id)
        reseau = str(perms.get("perm_reseaux") or "all").lower()
        typ = str(perms.get("perm_type") or "all").lower()
        ori = str(perms.get("perm_orientation") or "all").lower()

        # Libellés dynamiques Réseaux
        b_res_all = "✅ Tous réseaux" if reseau == "all" else "Tous réseaux"
        b_res_insta = "✅ Insta seul" if reseau == "insta" else "Insta seul"
        b_res_snap = "✅ Snap seul" if reseau == "snap" else "Snap seul"

        # Libellés dynamiques Orientations
        b_ori_all = "✅ 🔄 Tous / Bi" if ori in ("all", "bi") else "🔄 Tous / Bi"
        b_ori_h = "✅ Hétéro" if ori == "hetero" else "Hétéro"
        b_ori_g = "✅ Gay" if ori == "gay" else "Gay"

        # Libellés dynamiques Formules (Admin)
        b_typ_all = "✅ Tout type" if typ == "all" else "Tout type"
        b_typ_prio = "✅ 💎 Prio" if typ == "prio_only" else "💎 Prio"
        b_typ_std = "✅ 📝 Standard" if typ == "standard_only" else "📝 Standard"

        prefix = "self_pref" if can_edit else "self_pref_locked"

        keyboard = [
            [
                InlineKeyboardButton(b_res_all, callback_data=f"{prefix}_res_all"),
                InlineKeyboardButton(b_res_insta, callback_data=f"{prefix}_res_insta"),
                InlineKeyboardButton(b_res_snap, callback_data=f"{prefix}_res_snap"),
            ],
            [
                InlineKeyboardButton(b_ori_h, callback_data=f"{prefix}_ori_hetero"),
                InlineKeyboardButton(b_ori_g, callback_data=f"{prefix}_ori_gay"),
                InlineKeyboardButton(b_ori_all, callback_data=f"{prefix}_ori_all"),
            ]
        ]

        if is_admin:
            keyboard.append([
                InlineKeyboardButton(b_typ_all, callback_data=f"{prefix}_type_all"),
                InlineKeyboardButton(b_typ_prio, callback_data=f"{prefix}_type_prio_only"),
                InlineKeyboardButton(b_typ_std, callback_data=f"{prefix}_type_standard_only"),
            ])

        keyboard.append([InlineKeyboardButton("⬅️ RETOUR", callback_data="menu_mon_profil")])

        labels_res = {"all": "Tous les réseaux", "insta": "Instagram uniquement", "snap": "Snapchat uniquement"}
        labels_ori = {"all": "Toutes (Hétéro, Gay, Bi)", "hetero": "Hétéro & Bi", "gay": "Gay & Bi", "bi": "Bi uniquement"}
        labels_typ = {"all": "Toutes les demandes", "prio_only": "Prioritaires uniquement", "standard_only": "Standards uniquement"}

        locked_warning = "\n\n🔒 <i>Vos préférences sont actuellement verrouillées par l'administration.</i>" if not can_edit else ""
        prio_info = f"\n• <b>Formule :</b> {labels_typ.get(typ, typ)}" if not is_admin else ""

        text = (
            "🎯 <b>MES PRÉFÉRENCES DE CIBLES</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Voici les critères appliqués à vos demandes disponibles :\n\n"
            f"• <b>Réseaux :</b> {labels_res.get(reseau, reseau)}\n"
            f"• <b>Orientation :</b> {labels_ori.get(ori, ori)}{prio_info}"
            f"{locked_warning}\n\n"
            "<i>Cliquez sur un bouton pour modifier votre sélection :</i>"
        )
        return text, InlineKeyboardMarkup(keyboard)

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
            [InlineKeyboardButton("⬅️ RETOUR", callback_data="menu_mon_profil")]
        ]
        return text, InlineKeyboardMarkup(keyboard)

    # ========== SOUS-MENU GESTION DU BOT (Admin & Owner) ==========

    def get_gerer_bot_menu(self):
        """Menu de contrôle du bot système."""
        val_demandes = str(self.db_manager.get_config_value("demandes_enabled", "true")).lower()
        demandes_ouvertes = val_demandes in ("true", "1", "yes")

        etat_badge = "🟢 <b>OUVERTES (Actives)</b>" if demandes_ouvertes else "🔴 <b>SUSPENDUES (Fermées)</b>"
        label_suspension = (
            "❌ SUSPENDRE LES DEMANDES ❌"
            if demandes_ouvertes
            else "✅ RÉACTIVER LES DEMANDES ✅"
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
                InlineKeyboardButton("🎯 CIBLES", callback_data="menu_channels")
            ],
            [
                InlineKeyboardButton("⏳ DÉLAIS", callback_data="menu_delais"),
                InlineKeyboardButton("🛠️ MAINTENANCE", callback_data="maintenance")
            ],
            [
                InlineKeyboardButton("🔑 ADHÉSION", callback_data="menu_cfg_group"),
                InlineKeyboardButton("📢 CONTACT", callback_data="menu_cfg_support")
            ],
            [InlineKeyboardButton("⛔ ZONE DE DANGER ⛔", callback_data="menu_danger_zone")],
            [InlineKeyboardButton("⬅️ RETOUR", callback_data="parametres")]
        ]

        return message, InlineKeyboardMarkup(keyboard)

    # ========== SOUS-MENU ZONE DE DANGER (Owner Only) ==========

    def get_danger_zone_menu(self):
        """Affiche le menu de la Zone de Danger (Réservé au Propriétaire)."""
        text = (
            "🚨 <b>ZONE DE DANGER — PURGE DES DONNÉES</b> 🚨\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "⚠️ <b>Attention :</b> Les actions lancées ici effacent immédiatement et définitivement les données ciblées dans MySQL.\n\n"
            "<i>Sélectionnez le lot de données à vider :</i>"
        )
        keyboard = [
            [
                InlineKeyboardButton("📦 VIDER ARCHIVES", callback_data="danger_purge_archives"),
                InlineKeyboardButton("📋 VIDER DEMANDES", callback_data="danger_purge_demandes")
            ],
            [
                InlineKeyboardButton("👤 VIDER CLIENTS", callback_data="danger_purge_users"),
                InlineKeyboardButton("🦈 VIDER STAFF", callback_data="danger_purge_staff")
            ],
            [
                InlineKeyboardButton("🛡️ VIDER MANAGERS", callback_data="danger_purge_admins"),
                InlineKeyboardButton("⚙️ VIDER CONFIG", callback_data="danger_purge_config")
            ],
            [
                InlineKeyboardButton("💥 PURGE TOTALE 💥", callback_data="danger_purge_totale")
            ],
            [
                InlineKeyboardButton("⬅️ RETOUR ⬅️", callback_data="gerer_bot")
            ]
        ]
        return text, InlineKeyboardMarkup(keyboard)
    # ========== SOUS-MENU ADHÉSION OBLIGATOIRE GROUPE (Owner Only) ==========

    def get_group_subscription_config_menu(self):
        """Menu interactif de configuration de l'adhésion obligatoire."""
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
                InlineKeyboardButton("🔗 LIEN", callback_data="set_cfg_group_link")
            ],
            [InlineKeyboardButton("⬅️ RETOUR", callback_data="gerer_bot")]
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
            [InlineKeyboardButton("✏️ MODIFIER", callback_data="set_cfg_support_contact")],
            [InlineKeyboardButton("⬅️ RETOUR", callback_data="gerer_bot")]
        ]
        return text, InlineKeyboardMarkup(keyboard)

    # ========== SOUS-MENU GESTION DES CIBLES ==========

    def get_channels_menu(self):
        """Menu de gestion et d'activation des cibles avec les voyants positionnés avant le texte."""
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

        b_hi = f"{s_badge(hi)} HÉTÉRO - INSTA"
        b_hs = f"{s_badge(hs)} HÉTÉRO - SNAP"
        b_gi = f"{s_badge(gi)} GAY - INSTA"
        b_gs = f"{s_badge(gs)} GAY - SNAP"

        keyboard = [
            [
                InlineKeyboardButton(b_hi, callback_data="toggle_allow_hetero_insta"),
                InlineKeyboardButton(b_hs, callback_data="toggle_allow_hetero_snap"),
            ],
            [
                InlineKeyboardButton(b_gi, callback_data="toggle_allow_gay_insta"),
                InlineKeyboardButton(b_gs, callback_data="toggle_allow_gay_snap"),
            ],
            [
                InlineKeyboardButton("⬅️ RETOUR", callback_data="gerer_bot")
            ]
        ]

        return message, InlineKeyboardMarkup(keyboard)

    # ========== SOUS-MENU QUOTAS ==========

    def get_limits_menu(self):
        """Ajustement des quotas avec les blocs de contrôle directs par réseau."""
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
            # 1. Bloc TOTAL
            [
                InlineKeyboardButton("🌐 TOTAL", callback_data="limit_input_total")
            ],
            [
                InlineKeyboardButton("- 5", callback_data="limit_total_sub5"),
                InlineKeyboardButton("ILLIMITÉ", callback_data="limit_total_0"),
                InlineKeyboardButton("+ 5", callback_data="limit_total_add5"),
            ],
            # 2. Bloc CLIENT
            [
                InlineKeyboardButton("👤 CLIENT", callback_data="limit_input_user")
            ],
            [
                InlineKeyboardButton("- 1", callback_data="limit_user_sub1"),
                InlineKeyboardButton("DÉFAUT (3)", callback_data="limit_user_3"),
                InlineKeyboardButton("+ 1", callback_data="limit_user_add1"),
            ],
            # 3. Lignes Cibles (Hétéro puis Gay)
            [
                InlineKeyboardButton("🕺 INSTA", callback_data="limit_input_hetero_insta"),
                InlineKeyboardButton("🕺 SNAP", callback_data="limit_input_hetero_snap"),
            ],
            [
                InlineKeyboardButton("🏳️‍🌈 INSTA", callback_data="limit_input_gay_insta"),
                InlineKeyboardButton("🏳️‍🌈 SNAP", callback_data="limit_input_gay_snap"),
            ],
            # 4. Retour
            [
                InlineKeyboardButton("⬅️ RETOUR", callback_data="gerer_bot")
            ]
        ]

        return message, InlineKeyboardMarkup(keyboard)

    # ========== SOUS-MENU GÉRER LE STAFF (Admins & Owner) ==========

    def get_gerer_staff_menu(self):
        """Menu de gestion des employés/opérateurs (table staff) avec affichage visuel soigné."""
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

            keyboard = []
            nb_membres = len(staff_members)

            # Boutons d'action globale en haut
            keyboard.append([
                InlineKeyboardButton("➕ RECRUTER", callback_data="staff_ajouter"),
                InlineKeyboardButton("➖ VIRER", callback_data="staff_supprimer")
            ])

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

                    # Traduction propre et lisible des permissions (façon maquette)
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

                    # Boutons individuels par piégeur (en majuscules)
                    keyboard.append([
                        InlineKeyboardButton(f"📂 DOSSIERS : {alias_raw.upper()}", callback_data=f"staff_view_demandes_{st['user_id']}_0")
                    ])
                    keyboard.append([
                        InlineKeyboardButton("🛡️ PERMISSIONS", callback_data=f"perm_staff_{st['user_id']}"),
                        InlineKeyboardButton("📊 STATS", callback_data=f"profil_admin_{st['user_id']}")
                    ])

            # Bouton retour en bas
            keyboard.append([InlineKeyboardButton("⬅️ RETOUR", callback_data="parametres")])

        except Exception as exc:
            logger.error("Erreur menu gestion staff : %s", exc, exc_info=True)
            message = "🎣 <b>GESTION DES PIÉGEURS</b>\n━━━━━━━━━━━━━━━━━━━━\n❌ Erreur de lecture de la base."
            keyboard = [[InlineKeyboardButton("⬅️ RETOUR", callback_data="parametres")]]

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
            keyboard.append([InlineKeyboardButton("⬅️ RETOUR", callback_data="parametres")])

        except Exception as exc:
            logger.error("Erreur génération menu admins : %s", exc, exc_info=True)
            message = "🛡️ <b>Gestion des Administrateurs</b>\n\n❌ Erreur de lecture des données."
            keyboard = [[InlineKeyboardButton("⬅️ RETOUR", callback_data="parametres")]]

        return message, InlineKeyboardMarkup(keyboard)

    # ========== SOUS-MENU GÉRER LES MEMBRES VIP (Admin & Owner) ==========

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
            keyboard.append([InlineKeyboardButton("⬅️ RETOUR", callback_data="parametres")])

        except Exception as exc:
            logger.error("Erreur génération menu VIP : %s", exc, exc_info=True)
            message = "⭐ <b>Gestion des Membres VIP</b>\n\n❌ Erreur de lecture des données."
            keyboard = [[InlineKeyboardButton("⬅️ RETOUR", callback_data="parametres")]]

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
                InlineKeyboardButton("✨ PRÉFÉRENCES VIP ✨", callback_data="menu_vip_settings")
            ])

        keyboard.extend([
            [InlineKeyboardButton("⭐ S'abonner pour 30 jours (250 ⭐️)", callback_data="buy_vip_month")],
            [InlineKeyboardButton("⬅️ RETOUR", callback_data="parametres")]
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

        def toggle_suspension_handler():
            val_actuelle = str(self.db_manager.get_config_value("demandes_enabled", "true")).lower()
            nouvel_etat = "false" if val_actuelle in ("true", "1", "yes") else "true"
            self.db_manager.set_config_value("demandes_enabled", nouvel_etat)
            return self.get_gerer_bot_menu()

        routing_map = {
            "start_menu": lambda: self.get_start_interface(user_id, first_name),
            "gerer_demandes": lambda: self.get_gerer_demandes_menu(user_id),
            "parametres": lambda: self.get_parametres_menu(user_id),
            "menu_mon_profil": lambda: self.get_mon_profil_menu(user_id),
            "staff_self_prefs": lambda: self.get_staff_self_preferences_menu(user_id),
            "staff_payment_settings": lambda: self.get_staff_payment_settings_menu(user_id),
            "gerer_staff": self.get_gerer_staff_menu,
            "gerer_admins": self.get_gerer_admins_menu,
            "gerer_vips": self.get_gerer_vips_menu,
            "menu_vip_shop": lambda: self.get_vip_shop_menu(is_vip=is_vip),
            "gerer_bot": self.get_gerer_bot_menu,
            "bot_toggle_suspension": toggle_suspension_handler,
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