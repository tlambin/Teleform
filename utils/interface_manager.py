"""Interface Manager - Gestionnaire centralisé des claviers et menus du bot selon la hiérarchie RBAC."""

import logging
from .keyboards.helpers import format_datetime_fr
from .keyboards.client import ClientKeyboards
from .keyboards.staff import StaffKeyboards
from .keyboards.admin import AdminKeyboards

logger = logging.getLogger(__name__)


class InterfaceManager:
    """Gestionnaire centralisé des interfaces adaptées aux rôles : Client, Staff, Admin et Owner."""

    def __init__(self, config, db_manager):
        self.config = config
        self.db_manager = db_manager

        self.client_ui = ClientKeyboards(config, db_manager, self._get_user_role)
        self.staff_ui = StaffKeyboards(config, db_manager, self._get_user_role)
        self.admin_ui = AdminKeyboards(config, db_manager, self._get_user_role)

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

    # ========== DÉLÉGATION CLIENT ==========

    def get_start_interface(self, user_id: int, first_name: str):
        return self.client_ui.get_start_interface(user_id, first_name)

    def get_vip_shop_menu(self, is_vip: bool = False):
        return self.client_ui.get_vip_shop_menu(is_vip=is_vip)

    # ========== DÉLÉGATION STAFF ==========

    def get_gerer_demandes_menu(self, user_id: int):
        return self.staff_ui.get_gerer_demandes_menu(user_id)

    def get_mon_profil_menu(self, user_id: int):
        return self.staff_ui.get_mon_profil_menu(user_id)

    def get_demission_choice_menu(self):
        return self.staff_ui.get_demission_choice_menu()

    def get_demission_confirm_menu(self, scope: str):
        return self.staff_ui.get_demission_confirm_menu(scope)

    def get_staff_self_preferences_menu(self, user_id: int):
        return self.staff_ui.get_staff_self_preferences_menu(user_id)

    def get_staff_payment_settings_menu(self, staff_id: int):
        return self.staff_ui.get_staff_payment_settings_menu(staff_id)

    # ========== DÉLÉGATION ADMIN ==========

    def get_gerer_bot_menu(self):
        return self.admin_ui.get_gerer_bot_menu()

    def get_danger_zone_menu(self):
        return self.admin_ui.get_danger_zone_menu()

    def get_group_subscription_config_menu(self):
        return self.admin_ui.get_group_subscription_config_menu()

    def get_support_config_menu(self):
        return self.admin_ui.get_support_config_menu()

    def get_channels_menu(self):
        return self.admin_ui.get_channels_menu()

    def get_limits_menu(self):
        return self.admin_ui.get_limits_menu()

    def get_membres_menu(self):
        return self.admin_ui.get_membres_menu()

    def get_gerer_staff_menu(self):
        return self.admin_ui.get_gerer_staff_menu()

    def get_gerer_admins_menu(self):
        return self.admin_ui.get_gerer_admins_menu()

    def get_gerer_vips_menu(self):
        return self.admin_ui.get_gerer_vips_menu()

    # ========== MENU PARAMÈTRES (AIGUILLAGE RBAC) ==========

    def get_parametres_menu(self, user_id: int):
        """Construit le panneau Paramètres selon le rôle (Client vs Staff/Admin)."""
        user_role = self._get_user_role(user_id)
        if user_role not in ["staff", "admin", "owner"]:
            return self.client_ui.get_client_parametres_menu(user_id)
        return self.admin_ui.get_admin_parametres_menu(user_id)

    # ========== ROUTEUR CENTRAL DES MENUS ==========

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