"""Dépôt de gouvernance administrative, réglages système, purges et surveillance."""

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class AdminRepository:
    """Méthodes d'administration, surveillance et configuration globale."""

    def is_owner(self, user_id: int) -> bool:
        try:
            uid = int(user_id)
        except (ValueError, TypeError):
            return False

        if uid == getattr(self.config, "OWNER_ID", 0):
            return True

        cache_key = f"is_owner_{uid}"
        cached = self._get_cached_value(cache_key)
        if cached is not None:
            return cached

        try:
            with self.get_cursor() as cursor:
                cursor.execute("SELECT is_owner FROM admins WHERE user_id = %s", (uid,))
                row = cursor.fetchone()
                val = bool(row.get("is_owner")) if row else False
                self._set_cached_value(cache_key, val)
                return val
        except Exception as exc:
            logger.error("Erreur contrôle is_owner pour %s : %s", uid, exc)
            return False

    def is_admin(self, user_id: int) -> bool:
        try:
            uid = int(user_id)
        except (ValueError, TypeError):
            return False

        if self.is_owner(uid):
            return True

        cache_key = f"is_admin_{uid}"
        cached = self._get_cached_value(cache_key)
        if cached is not None:
            return cached

        try:
            with self.get_cursor() as cursor:
                cursor.execute("SELECT user_id FROM admins WHERE user_id = %s", (uid,))
                val = bool(cursor.fetchone())
                self._set_cached_value(cache_key, val)
                return val
        except Exception as exc:
            logger.error("Erreur contrôle is_admin pour %s : %s", uid, exc)
            return False

    def get_owner_id(self) -> int:
        val = self.get_config_value("owner_id", str(getattr(self.config, "OWNER_ID", 0)))
        return int(val) if str(val).isdigit() else 0

    def get_owner_alias(self) -> str:
        return self.get_config_value("owner_alias", "Propriétaire")

    def set_owner_alias(self, alias: str) -> bool:
        return self.set_config_value("owner_alias", alias)

    def get_admin_privileges(self, user_id: int) -> Dict[str, bool]:
        if self.is_owner(user_id):
            return {
                "is_owner": True,
                "is_vip": True,
                "can_manage_staff": True,
                "can_manage_vips": True,
                "can_view_stats": True,
                "can_manage_delais": True,
                "can_view_archives": True,
                "can_monitor_staff": True,
                "can_ban_users": True,
                "can_edit_others_demandes": True,
            }

        try:
            with self.get_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT is_owner, is_vip, can_manage_staff, can_manage_vips, can_view_stats,
                           can_manage_delais, can_view_archives, can_monitor_staff, can_ban_users,
                           can_edit_others_demandes
                    FROM admins WHERE user_id = %s
                    """,
                    (int(user_id),)
                )
                row = cursor.fetchone()
                if row:
                    return {
                        "is_owner": bool(row["is_owner"]),
                        "is_vip": bool(row.get("is_vip", False)),
                        "can_manage_staff": bool(row["can_manage_staff"]),
                        "can_manage_vips": bool(row["can_manage_vips"]),
                        "can_view_stats": bool(row["can_view_stats"]),
                        "can_manage_delais": bool(row["can_manage_delais"]),
                        "can_view_archives": bool(row.get("can_view_archives", False)),
                        "can_monitor_staff": bool(row.get("can_monitor_staff", False)),
                        "can_ban_users": bool(row.get("can_ban_users", False)),
                        "can_edit_others_demandes": bool(row.get("can_edit_others_demandes", False)),
                    }
        except Exception as exc:
            logger.error("Erreur lecture privilèges admin %s : %s", user_id, exc)

        return {
            "is_owner": False,
            "is_vip": False,
            "can_manage_staff": False,
            "can_manage_vips": False,
            "can_view_stats": False,
            "can_manage_delais": False,
            "can_view_archives": False,
            "can_monitor_staff": False,
            "can_ban_users": False,
            "can_edit_others_demandes": False,
        }

    def update_admin_privilege(self, user_id: int, priv_key: str, value: bool) -> bool:
        allowed_keys = {
            "can_manage_staff", "can_manage_vips", "can_view_stats",
            "can_manage_delais", "can_view_archives", "can_monitor_staff",
            "can_ban_users", "can_edit_others_demandes", "is_vip"
        }
        if priv_key not in allowed_keys:
            return False

        try:
            with self.transaction() as cursor:
                cursor.execute(f"UPDATE admins SET `{priv_key}` = %s WHERE user_id = %s", (value, int(user_id)))
            self.clear_cache(f"is_admin_{user_id}")
            self.clear_cache(f"vip_{user_id}")
            return True
        except Exception as exc:
            logger.error("Erreur mise à jour privilège admin %s (%s) : %s", user_id, priv_key, exc)
            return False

    def toggle_admin_privilege(self, user_id: int, priv_key: str) -> bool:
        allowed_keys = {
            "can_manage_staff", "can_manage_vips", "can_view_stats",
            "can_manage_delais", "can_view_archives", "can_monitor_staff",
            "can_ban_users", "can_edit_others_demandes", "is_vip"
        }
        if priv_key not in allowed_keys:
            return False

        try:
            with self.transaction() as cursor:
                cursor.execute(f"UPDATE admins SET `{priv_key}` = NOT COALESCE(`{priv_key}`, FALSE) WHERE user_id = %s", (int(user_id),))
            self.clear_cache(f"is_admin_{user_id}")
            self.clear_cache(f"vip_{user_id}")
            return True
        except Exception as exc:
            logger.error("Erreur bascule privilège admin %s (%s) : %s", user_id, priv_key, exc)
            return False

    def get_monitoring_admins(self, action: Optional[str] = None) -> List[int]:
        admins_eligibles = set()
        primary_owner = self.get_owner_id() or getattr(self.config, "OWNER_ID", 0)
        if primary_owner:
            admins_eligibles.add(int(primary_owner))

        try:
            with self.get_cursor() as cursor:
                cursor.execute("SELECT user_id FROM admins WHERE is_owner = TRUE OR can_monitor_staff = TRUE")
                for r in cursor.fetchall():
                    admins_eligibles.add(int(r["user_id"]))
        except Exception as exc:
            logger.error("Erreur récupération admins moniteurs : %s", exc)
            return []

        if not action:
            return list(admins_eligibles)

        col_map = {
            "prise_en_charge": "monitor_prise_en_charge",
            "changement_statut": "monitor_changement_statut",
            "abandon": "monitor_abandon",
            "reussite": "monitor_reussite",
            "staff_msg": "monitor_staff_msg",
            "user_msg": "monitor_user_msg",
        }
        target_col = col_map.get(action)
        if not target_col:
            return list(admins_eligibles)

        destinataires = []
        try:
            with self.get_cursor() as cursor:
                for uid in admins_eligibles:
                    cursor.execute(f"SELECT `{target_col}` FROM admin_preferences WHERE user_id = %s", (uid,))
                    row = cursor.fetchone()
                    if not row or row.get(target_col) is None or bool(row[target_col]):
                        destinataires.append(uid)
            return destinataires
        except Exception as exc:
            logger.error("Erreur filtrage préférences surveillance (%s) : %s", action, exc)
            return list(admins_eligibles)

    # ==================== PRÉFÉRENCES ADMIN ====================

    def get_admin_preferences(self, user_id: int) -> Dict[str, Any]:
        default_prefs = {
            "user_id": user_id,
            "notif_new_mode": "sound",
            "rappel_mode": "sound",
            "rappel_freq": "daily",
            "rappel_heure": 18,
            "rappel_jour_semaine": 6,
            "rappel_jour_mois": 1,
            "last_rappel_date": None,
            "monitor_prise_en_charge": True,
            "monitor_changement_statut": True,
            "monitor_abandon": True,
            "monitor_reussite": True,
            "monitor_staff_msg": True,
            "monitor_user_msg": True,
        }
        cache_key = f"admin_prefs_{user_id}"
        cached = self._get_cached_value(cache_key)
        if cached is not None:
            return cached

        try:
            with self.get_cursor() as cursor:
                cursor.execute("SELECT * FROM admin_preferences WHERE user_id = %s", (user_id,))
                row = cursor.fetchone()
                if row:
                    default_prefs.update(row)
                else:
                    cursor.execute(
                        """
                        INSERT INTO admin_preferences (
                            user_id, notif_new_mode, rappel_mode, rappel_freq,
                            rappel_heure, rappel_jour_semaine, rappel_jour_mois,
                            monitor_prise_en_charge, monitor_changement_statut,
                            monitor_abandon, monitor_reussite, monitor_staff_msg, monitor_user_msg
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE user_id = VALUES(user_id)
                        """,
                        (user_id, "sound", "sound", "daily", 18, 6, 1, True, True, True, True, True, True)
                    )
            self._set_cached_value(cache_key, default_prefs)
            return default_prefs
        except Exception as exc:
            logger.error("Erreur récupération préférences %s : %s", user_id, exc)
            return default_prefs

    def update_admin_preference(self, user_id: int, key: str, value: Any) -> bool:
        allowed_keys = {
            "notif_new_mode", "rappel_mode", "rappel_freq", "rappel_heure",
            "rappel_jour_semaine", "rappel_jour_mois", "last_rappel_date",
            "monitor_prise_en_charge", "monitor_changement_statut",
            "monitor_abandon", "monitor_reussite", "monitor_staff_msg", "monitor_user_msg"
        }
        if key not in allowed_keys:
            return False

        try:
            with self.transaction() as cursor:
                cursor.execute(
                    f"""
                    INSERT INTO admin_preferences (user_id, `{key}`)
                    VALUES (%s, %s)
                    ON DUPLICATE KEY UPDATE `{key}` = VALUES(`{key}`)
                    """,
                    (user_id, value)
                )
            self.clear_cache(f"admin_prefs_{user_id}")
            return True
        except Exception as exc:
            logger.error("Erreur mise à jour préférence %s pour %s : %s", key, user_id, exc)
            return False

    def mark_admin_reminder_sent(self, user_id: int):
        try:
            with self.transaction() as cursor:
                cursor.execute("UPDATE admin_preferences SET last_rappel_date = CURRENT_DATE() WHERE user_id = %s", (user_id,))
            self.clear_cache(f"admin_prefs_{user_id}")
        except Exception as exc:
            logger.error("Erreur mise à jour last_rappel_date pour %s : %s", user_id, exc)

    def get_all_admin_preferences(self) -> List[Dict[str, Any]]:
        try:
            with self.get_cursor() as cursor:
                cursor.execute("SELECT * FROM admin_preferences WHERE rappel_mode != 'off'")
                return cursor.fetchall()
        except Exception as exc:
            logger.error("Erreur lecture globale préférences : %s", exc)
            return []

    # ==================== CONFIGURATION GLOBALE ====================

    def _get_config_columns(self) -> Tuple[str, str]:
        cached = self._get_cached_value("cfg_col_names")
        if cached:
            return cached

        key_col, val_col = "key_name", "`value`"
        try:
            with self.get_cursor(dictionary=True) as cursor:
                cursor.execute("SHOW COLUMNS FROM config")
                cols = [c["Field"].lower() for c in cursor.fetchall()]

                if "config_key" in cols:
                    key_col = "config_key"
                elif "key_name" in cols:
                    key_col = "key_name"
                elif "key" in cols:
                    key_col = "`key`"

                if "config_value" in cols:
                    val_col = "config_value"
                elif "value" in cols:
                    val_col = "`value`"

            self._set_cached_value("cfg_col_names", (key_col, val_col))
            return key_col, val_col
        except Exception as exc:
            logger.error("Impossible de détecter les colonnes de config : %s", exc)
            return "key_name", "`value`"

    def get_config_value(self, key_name: str, default: Optional[str] = None) -> Optional[str]:
        cache_key = f"cfg_{key_name}"
        cached = self._get_cached_value(cache_key)
        if cached is not None:
            return cached

        k_col, v_col = self._get_config_columns()
        try:
            with self.get_cursor() as cursor:
                cursor.execute(f"SELECT {v_col} AS val FROM config WHERE {k_col} = %s", (key_name,))
                row = cursor.fetchone()
                val = str(row["val"]) if row and row.get("val") is not None else default
                self._set_cached_value(cache_key, val)
                return val
        except Exception as exc:
            logger.error("Erreur lecture config '%s': %s", key_name, exc)
            return default

    def set_config_value(self, key_name: str, value: str) -> bool:
        k_col, v_col = self._get_config_columns()
        try:
            with self.get_cursor() as cursor:
                cursor.execute(
                    f"""
                    INSERT INTO config ({k_col}, {v_col}, updated_at)
                    VALUES (%s, %s, NOW())
                    ON DUPLICATE KEY UPDATE {v_col} = VALUES({v_col}), updated_at = NOW()
                    """,
                    (key_name, str(value)),
                )
            self.clear_cache(f"cfg_{key_name}")
            self.clear_cache("cfg_all")
            return True
        except Exception as exc:
            logger.error("Erreur écriture config '%s': %s", key_name, exc)
            return False

    def get_all_config(self) -> Dict[str, str]:
        cached = self._get_cached_value("cfg_all")
        if cached is not None:
            return cached

        k_col, v_col = self._get_config_columns()
        try:
            with self.get_cursor() as cursor:
                cursor.execute(f"SELECT {k_col} AS k, {v_col} AS v FROM config")
                rows = cursor.fetchall()
                result = {r["k"]: str(r["v"]) for r in rows}
                self._set_cached_value("cfg_all", result)
                return result
        except Exception as exc:
            logger.error("Erreur lecture globale config : %s", exc)
            return {}

    def is_bot_active(self) -> bool:
        maint = str(self.get_config_value("maintenance_mode", "false")).lower()
        if maint in ("true", "1", "yes"):
            return False
        val = str(self.get_config_value("bot_active", "true")).lower()
        return val in ("true", "1", "yes")

    def set_bot_active(self, active: bool) -> bool:
        val_str = "true" if active else "false"
        ok1 = self.set_config_value("bot_active", val_str)
        ok2 = self.set_config_value("demandes_enabled", val_str)
        return ok1 and ok2

    def get_max_total_demandes(self) -> int:
        val = self.get_config_value("max_total_demandes", "0")
        try:
            return int(val)
        except (ValueError, TypeError):
            return 0

    def set_max_total_demandes(self, limit: int) -> bool:
        val = max(0, int(limit))
        return self.set_config_value("max_total_demandes", str(val))

    def get_max_demandes_per_user(self) -> int:
        val = self.get_config_value("max_demandes_per_user", "3")
        try:
            return int(val)
        except (ValueError, TypeError):
            return 3

    def set_max_demandes_per_user(self, limit: int) -> bool:
        val = max(0, int(limit))
        return self.set_config_value("max_demandes_per_user", str(val))

    def is_channel_combination_allowed(self, orientation: str, reseau: str) -> bool:
        ori = orientation.lower()
        res = "insta" if "insta" in reseau.lower() else "snap"

        if ori in ("hetero", "gay"):
            cfg_key = f"allow_{ori}_{res}"
            return str(self.get_config_value(cfg_key, "true")).lower() in ("true", "1", "yes")
        elif ori == "bi":
            allow_h = str(self.get_config_value(f"allow_hetero_{res}", "true")).lower() in ("true", "1", "yes")
            allow_g = str(self.get_config_value(f"allow_gay_{res}", "true")).lower() in ("true", "1", "yes")
            return allow_h or allow_g
        return True

    def get_auto_archive_hours(self) -> int:
        val = self.get_config_value("auto_archive_hours", "72")
        try:
            return max(1, int(val))
        except (ValueError, TypeError):
            return 72

    def set_auto_archive_hours(self, hours: int) -> bool:
        val = max(1, int(hours))
        return self.set_config_value("auto_archive_hours", str(val))

    def get_delivery_reminder_days(self) -> int:
        val = self.get_config_value("delivery_reminder_days", "7")
        try:
            return max(1, int(val))
        except (ValueError, TypeError):
            return 7

    def set_delivery_reminder_days(self, days: int) -> bool:
        val = max(1, int(days))
        return self.set_config_value("delivery_reminder_days", str(val))

    def get_payment_reminder_days(self) -> int:
        val = self.get_config_value("payment_reminder_days", "7")
        try:
            return max(1, int(val))
        except (ValueError, TypeError):
            return 7

    def set_payment_reminder_days(self, days: int) -> bool:
        val = max(1, int(days))
        return self.set_config_value("payment_reminder_days", str(val))

    def get_remun_expiration_days(self) -> int:
        val = self.get_config_value("remun_expiration_days", "7")
        try:
            return max(1, int(val))
        except (ValueError, TypeError):
            return 7

    def set_remun_expiration_days(self, days: int) -> bool:
        val = max(1, int(days))
        return self.set_config_value("remun_expiration_days", str(val))

    def is_required_group_enabled(self) -> bool:
        val = str(self.get_config_value("required_group_enabled", "false")).lower()
        return val in ("true", "1", "yes")

    def toggle_required_group_enabled(self) -> bool:
        new_val = not self.is_required_group_enabled()
        self.set_config_value("required_group_enabled", "true" if new_val else "false")
        return new_val

    def get_required_group_id(self) -> int:
        val = self.get_config_value("required_group_id", "0")
        try:
            return int(val)
        except (ValueError, TypeError):
            return 0

    def set_required_group_id(self, group_id: int) -> bool:
        return self.set_config_value("required_group_id", str(group_id))

    def get_group_subscription_link(self) -> str:
        return self.get_config_value("group_subscription_link", "@parascriptionbot")

    def set_group_subscription_link(self, link: str) -> bool:
        return self.set_config_value("group_subscription_link", str(link).strip())

    def get_support_contact(self) -> str:
        return self.get_config_value("support_contact", "@ContactParaBot")

    def set_support_contact(self, contact: str) -> bool:
        return self.set_config_value("support_contact", str(contact).strip())

    def get_available_admins_for_selection(self) -> List[Dict[str, Any]]:
        equipe = []
        try:
            owner_id = self.get_owner_id() or getattr(self.config, "OWNER_ID", 0)
            owner_alias = self.get_owner_alias()
            owner_paused = self.is_staff_paused(owner_id)

            if owner_id and not owner_paused:
                equipe.append({"user_id": owner_id, "alias": owner_alias, "role": "Owner"})

            with self.get_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT user_id, alias FROM staff
                    WHERE (is_paused IS FALSE OR is_paused IS NULL)
                    ORDER BY alias ASC
                    """
                )
                for r in cursor.fetchall():
                    if r["user_id"] != owner_id:
                        equipe.append({"user_id": r["user_id"], "alias": r["alias"], "role": "Staff"})
            return equipe
        except Exception as exc:
            logger.error("Erreur extraction équipe VIP : %s", exc)
            return equipe

    get_available_staff = get_available_admins_for_selection

    # ==================== PURGES ====================

    def purge_table_data(self, target: str, owner_id: int) -> bool:
        try:
            with self.transaction() as cursor:
                if target == "archives":
                    cursor.execute("DELETE FROM archives")

                elif target == "demandes":
                    cursor.execute("DELETE FROM demandes_suivi")
                    cursor.execute("DELETE FROM demandes")

                elif target == "users":
                    cursor.execute("DELETE FROM user_preferences WHERE user_id != %s", (owner_id,))
                    cursor.execute("DELETE FROM banned_users WHERE user_id != %s", (owner_id,))
                    cursor.execute("DELETE FROM users WHERE user_id != %s", (owner_id,))

                elif target == "staff":
                    cursor.execute("DELETE FROM staff WHERE user_id != %s", (owner_id,))

                elif target == "admins":
                    cursor.execute("DELETE FROM admins WHERE user_id != %s AND is_owner = FALSE", (owner_id,))

                elif target == "totale":
                    cursor.execute("DELETE FROM archives")
                    cursor.execute("DELETE FROM demandes_suivi")
                    cursor.execute("DELETE FROM demandes")
                    cursor.execute("DELETE FROM staff WHERE user_id != %s", (owner_id,))
                    cursor.execute("DELETE FROM admins WHERE user_id != %s AND is_owner = FALSE", (owner_id,))
                    cursor.execute("DELETE FROM user_preferences WHERE user_id != %s", (owner_id,))
                    cursor.execute("DELETE FROM banned_users WHERE user_id != %s", (owner_id,))
                    cursor.execute("DELETE FROM users WHERE user_id != %s", (owner_id,))

                    try:
                        cursor.execute("ALTER TABLE demandes AUTO_INCREMENT = 1")
                        cursor.execute("ALTER TABLE demandes_suivi AUTO_INCREMENT = 1")
                        cursor.execute("ALTER TABLE archives AUTO_INCREMENT = 1")
                        logger.info("Compteurs AUTO_INCREMENT réinitialisés à 1 suite à la purge totale.")
                    except Exception as e_auto:
                        logger.warning("Impossible de réinitialiser l'auto-incrément : %s", e_auto)

                else:
                    logger.warning("Cible de purge inconnue : %s", target)
                    return False

            self.clear_cache()
            logger.warning("PURGE EXÉCUTÉE avec succès sur la cible : %s par owner %s", target, owner_id)
            return True
        except Exception as exc:
            logger.error("Erreur lors de la purge de la table '%s' : %s", target, exc, exc_info=True)
            return False