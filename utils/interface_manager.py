"""Interface Manager - Gestionnaire centralisé des claviers et menus du bot selon la hiérarchie RBAC."""

import logging
from ui.user import compte as user_compte_ui
from ui.staff import demandes as staff_demandes_ui
from ui.staff import profil as staff_profil_ui
from ui.admin import system as admin_system_ui
from ui.admin import users as admin_users_ui

logger = logging.getLogger(__name__)


class InterfaceManager:
    """Gestionnaire centralisé des interfaces adaptées aux rôles : Client, Staff, Admin et Owner."""

    def __init__(self, config, db_manager):
        self.config = config
        self.db_manager = db_manager

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

    # ==================== DÉLÉGATION CLIENT ====================

    def get_start_interface(self, user_id: int, first_name: str):
        role = self._get_user_role(user_id)
        is_vip = self.db_manager.is_user_vip(user_id)
        return user_compte_ui.build_start_interface(user_id, first_name, role, is_vip)

    def get_vip_shop_menu(self, is_vip: bool = False):
        return user_compte_ui.build_vip_shop_menu(is_vip=is_vip)

    def get_client_parametres_menu(self, user_id: int):
        is_vip = self.db_manager.is_user_vip(user_id)
        support_contact = self.db_manager.get_support_contact()
        return user_compte_ui.build_client_parametres_menu(user_id, is_vip, support_contact)

    # ==================== DÉLÉGATION STAFF ====================

    def get_gerer_demandes_menu(self, user_id: int):
        counts = self.db_manager.get_staff_demandes_counts(user_id)
        nb_dispo = counts.get("dispo", 0)
        nb_suivies = counts.get("suivies", 0)
        nb_archives = counts.get("archives", 0)
        return staff_demandes_ui.get_gerer_demandes_menu(nb_dispo, nb_suivies, nb_archives)

    def get_mon_profil_menu(self, user_id: int):
        user_role = self._get_user_role(user_id)
        is_paused = self.db_manager.is_staff_paused(user_id)
        alias = self.db_manager.get_staff_alias(user_id) or f"Membre_{user_id}"

        primary_owner_id = self.db_manager.get_owner_id() or getattr(self.config, "OWNER_ID", 0)
        is_primary_owner = (int(user_id) == int(primary_owner_id))
        can_edit_alias = self.db_manager.can_staff_edit_alias(user_id)

        return staff_profil_ui.get_mon_profil_menu(
            user_id=user_id,
            user_role=user_role,
            is_paused=is_paused,
            alias=alias,
            is_primary_owner=is_primary_owner,
            can_edit_alias=can_edit_alias,
        )

    def get_demission_choice_menu(self):
        return staff_profil_ui.get_demission_choice_menu()

    def get_demission_confirm_menu(self, scope: str):
        return staff_profil_ui.get_demission_confirm_menu(scope)

    def get_staff_self_preferences_menu(self, user_id: int):
        can_edit = self.db_manager.can_staff_edit_preferences(user_id)
        perms = self.db_manager.get_staff_permissions(user_id)
        return staff_profil_ui.get_staff_self_preferences_menu(perms, can_edit)

    def get_staff_payment_settings_menu(self, staff_id: int):
        methods = self.db_manager.get_staff_payment_methods(staff_id)
        accept_stars = bool(methods.get("accept_stars", True))
        accept_direct = bool(methods.get("accept_direct", True))
        return staff_profil_ui.get_staff_payment_settings_menu(accept_stars, accept_direct)

    # ==================== DÉLÉGATION ADMIN ====================

    def get_gerer_bot_menu(self):
        val_demandes = str(self.db_manager.get_config_value("demandes_enabled", "true")).lower()
        demandes_ouvertes = val_demandes in ("true", "1", "yes")
        return admin_system_ui.build_gerer_bot_menu(demandes_ouvertes)

    def get_danger_zone_menu(self):
        return admin_system_ui.build_danger_zone_menu()

    def get_group_subscription_config_menu(self):
        is_enabled = self.db_manager.is_required_group_enabled()
        group_id = self.db_manager.get_required_group_id()
        link = self.db_manager.get_group_subscription_link()
        return admin_system_ui.build_group_subscription_config_menu(is_enabled, group_id, link)

    def get_support_config_menu(self):
        contact = self.db_manager.get_support_contact()
        return admin_system_ui.build_support_config_menu(contact)

    def get_channels_menu(self):
        hi = self.db_manager.is_channel_combination_allowed("hetero", "insta")
        hs = self.db_manager.is_channel_combination_allowed("hetero", "snap")
        gi = self.db_manager.is_channel_combination_allowed("gay", "insta")
        gs = self.db_manager.is_channel_combination_allowed("gay", "snap")
        return admin_system_ui.build_channels_menu(hi, hs, gi, gs)

    def get_limits_menu(self):
        max_total = self.config.get_max_total_demandes()
        max_user = self.config.get_max_demandes_per_user()
        m_hi = int(self.db_manager.get_config_value("max_hetero_insta", "0") or 0)
        m_hs = int(self.db_manager.get_config_value("max_hetero_snap", "0") or 0)
        m_gi = int(self.db_manager.get_config_value("max_gay_insta", "0") or 0)
        m_gs = int(self.db_manager.get_config_value("max_gay_snap", "0") or 0)
        return admin_system_ui.build_limits_menu(max_total, max_user, m_hi, m_hs, m_gi, m_gs)

    def get_membres_menu(self):
        return admin_users_ui.build_membres_menu()

    def get_gerer_staff_menu(self):
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
        return admin_users_ui.build_gerer_staff_menu(staff_members)

    def get_gerer_admins_menu(self):
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
        return admin_users_ui.build_gerer_admins_menu(admins)

    def get_gerer_vips_menu(self):
        vips = self.db_manager.get_vip_users_list()
        return admin_users_ui.build_gerer_vips_menu(vips)

    # ==================== MENU PARAMÈTRES (AIGUILLAGE RBAC) ====================

    def get_parametres_menu(self, user_id: int):
        """Construit le panneau Paramètres selon le rôle (Client vs Staff/Admin)."""
        user_role = self._get_user_role(user_id)
        if user_role not in ["staff", "admin", "owner"]:
            return self.get_client_parametres_menu(user_id)

        is_vip = self.db_manager.is_user_vip(user_id)
        privs = self.db_manager.get_admin_privileges(user_id)
        return admin_users_ui.build_admin_parametres_menu(user_id, user_role, is_vip, privs)

    # ==================== ROUTEUR CENTRAL DES MENUS ====================

    def route_callback(self, callback_data: str, user_id: int, first_name: str):
        """Aiguillage des callbacks d'interface vers le bon générateur de vue."""
        is_vip = self.db_manager.is_user_vip(user_id)

        def toggle_suspension_handler():
            val_actuelle = str(self.db_manager.get_config_value("demandes_enabled", "true")).lower()
            nouvel_etat = "false" if val_actuelle in ("true", "1", "yes") else "true"
            self.db_manager.set_config_value("demandes_enabled", nouvel_etat)
            return self.get_gerer_bot_menu()

        def demission_handler():
            is_adm = self.db_manager.is_admin(user_id)
            is_stf = False
            with self.db_manager.get_cursor() as cursor:
                cursor.execute("SELECT user_id FROM staff WHERE user_id = %s", (int(user_id),))
                is_stf = bool(cursor.fetchone())

            if is_adm and is_stf:
                return self.get_demission_choice_menu()
            elif is_adm:
                return self.get_demission_confirm_menu("admin")
            else:
                return self.get_demission_confirm_menu("staff")

        routing_map = {
            "start_menu": lambda: self.get_start_interface(user_id, first_name),
            "gerer_demandes": lambda: self.get_gerer_demandes_menu(user_id),
            "parametres": lambda: self.get_parametres_menu(user_id),
            "menu_mon_profil": lambda: self.get_mon_profil_menu(user_id),
            "menu_demission": demission_handler,
            "demission_confirm_admin": lambda: self.get_demission_confirm_menu("admin"),
            "demission_confirm_staff": lambda: self.get_demission_confirm_menu("staff"),
            "demission_confirm_all": lambda: self.get_demission_confirm_menu("all"),
            "staff_self_prefs": lambda: self.get_staff_self_preferences_menu(user_id),
            "staff_payment_settings": lambda: self.get_staff_payment_settings_menu(user_id),
            "gerer_staff": self.get_gerer_staff_menu,
            "gerer_admins": self.get_gerer_admins_menu,
            "menu_membres": self.get_membres_menu,
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