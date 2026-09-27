"""Dépôt de gestion des utilisateurs, bannissements, VIPs et préférences."""

from datetime import datetime
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class UserRepository:
    """Méthodes CRUD relatives aux utilisateurs, VIPs et bannissements."""

    # ==================== BANNISSEMENTS ====================

    def is_user_banned(self, user_id: int) -> bool:
        try:
            uid = int(user_id)
        except (ValueError, TypeError):
            return False

        cache_key = f"is_banned_{uid}"
        cached = self._get_cached_value(cache_key)
        if cached is not None:
            return cached

        try:
            with self.get_cursor() as cursor:
                cursor.execute("SELECT user_id FROM banned_users WHERE user_id = %s", (uid,))
                val = bool(cursor.fetchone())
                self._set_cached_value(cache_key, val)
                return val
        except Exception as exc:
            logger.error("Erreur contrôle bannissement pour %s : %s", uid, exc)
            return False

    def ban_user(self, user_id: int, banned_by: Optional[int] = None, reason: str = "Non spécifié") -> bool:
        try:
            uid = int(user_id)
            by_id = int(banned_by) if banned_by else None
            clean_reason = str(reason or "Non spécifié").strip()

            with self.transaction() as cursor:
                cursor.execute(
                    """
                    INSERT INTO banned_users (user_id, banned_by, reason, date_ban)
                    VALUES (%s, %s, %s, NOW())
                    ON DUPLICATE KEY UPDATE banned_by = VALUES(banned_by), reason = VALUES(reason), date_ban = NOW()
                    """,
                    (uid, by_id, clean_reason)
                )

            self.clear_cache(f"is_banned_{uid}")
            logger.warning("Utilisateur %s banni par %s (Motif: %s)", uid, by_id, clean_reason)
            return True
        except Exception as exc:
            logger.error("Erreur enregistrement ban pour %s : %s", user_id, exc)
            return False

    def unban_user(self, user_id: int) -> bool:
        try:
            uid = int(user_id)
            with self.transaction() as cursor:
                cursor.execute("DELETE FROM banned_users WHERE user_id = %s", (uid,))
            self.clear_cache(f"is_banned_{uid}")
            logger.info("Utilisateur %s débanni avec succès", uid)
            return True
        except Exception as exc:
            logger.error("Erreur débannissement pour %s : %s", user_id, exc)
            return False

    def get_banned_users_count(self) -> int:
        try:
            with self.get_cursor() as cursor:
                cursor.execute("SELECT COUNT(*) AS total FROM banned_users")
                row = cursor.fetchone()
                return int(row["total"]) if row else 0
        except Exception as exc:
            logger.error("Erreur comptage bannis : %s", exc)
            return 0

    def get_banned_users_list(self, limit: int = 5, offset: int = 0) -> List[Dict[str, Any]]:
        try:
            with self.get_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT b.user_id, b.banned_by, b.reason, b.date_ban,
                           u.first_name, u.username,
                           a.alias AS admin_alias
                    FROM banned_users b
                    LEFT JOIN users u ON b.user_id = u.user_id
                    LEFT JOIN admins a ON b.banned_by = a.user_id
                    ORDER BY b.date_ban DESC
                    LIMIT %s OFFSET %s
                    """,
                    (max(1, limit), max(0, offset))
                )
                return cursor.fetchall()
        except Exception as exc:
            logger.error("Erreur lecture liste bannis : %s", exc)
            return []

    # ==================== PRÉFÉRENCES DEMANDEUR ====================

    def get_user_preferences(self, user_id: int) -> Dict[str, Any]:
        default_prefs = {
            "user_id": int(user_id),
            "notif_status_mode": "sound",
            "notif_prise_en_charge": "sound",
            "notif_messages": "sound",
        }
        cache_key = f"user_prefs_{user_id}"
        cached = self._get_cached_value(cache_key)
        if cached is not None:
            return cached

        try:
            with self.get_cursor() as cursor:
                cursor.execute("SELECT * FROM user_preferences WHERE user_id = %s", (int(user_id),))
                row = cursor.fetchone()
                if row:
                    default_prefs.update(row)
                else:
                    cursor.execute(
                        """
                        INSERT INTO user_preferences (user_id, notif_status_mode, notif_prise_en_charge, notif_messages)
                        VALUES (%s, 'sound', 'sound', 'sound')
                        ON DUPLICATE KEY UPDATE user_id = VALUES(user_id)
                        """,
                        (int(user_id),)
                    )
            self._set_cached_value(cache_key, default_prefs)
            return default_prefs
        except Exception as exc:
            logger.error("Erreur récupération préférences client %s : %s", user_id, exc)
            return default_prefs

    def update_user_preference(self, user_id: int, key: str, value: str) -> bool:
        allowed_keys = {"notif_status_mode", "notif_prise_en_charge", "notif_messages"}
        if key not in allowed_keys or value not in ("sound", "silent", "off"):
            return False

        try:
            with self.transaction() as cursor:
                cursor.execute(
                    f"""
                    INSERT INTO user_preferences (user_id, `{key}`)
                    VALUES (%s, %s)
                    ON DUPLICATE KEY UPDATE `{key}` = VALUES(`{key}`)
                    """,
                    (int(user_id), value)
                )
            self.clear_cache(f"user_prefs_{user_id}")
            return True
        except Exception as exc:
            logger.error("Erreur mise à jour préférence client %s (%s=%s) : %s", user_id, key, value, exc)
            return False

    # ==================== VIP & AUTO-ASSIGN ====================

    def is_user_vip(self, user_id: int) -> bool:
        try:
            uid = int(user_id)
        except (ValueError, TypeError):
            return False

        if self.is_owner(uid):
            return True

        cache_key = f"vip_{uid}"
        cached = self._get_cached_value(cache_key)
        if cached is not None:
            return cached

        try:
            with self.get_cursor() as cursor:
                cursor.execute("SELECT is_vip FROM admins WHERE user_id = %s", (uid,))
                admin_row = cursor.fetchone()
                if admin_row and bool(admin_row.get("is_vip")):
                    self._set_cached_value(cache_key, True)
                    return True

                cursor.execute("SELECT is_vip, vip_until FROM users WHERE user_id = %s", (uid,))
                row = cursor.fetchone()
                if not row or not row.get("is_vip"):
                    self._set_cached_value(cache_key, False)
                    return False

                vip_until = row.get("vip_until")
                if vip_until is None:
                    self._set_cached_value(cache_key, True)
                    return True

                now_ts = time.time()
                is_active = vip_until.timestamp() > now_ts
                self._set_cached_value(cache_key, is_active)
                return is_active
        except Exception as exc:
            logger.error("Erreur vérification statut VIP %s : %s", user_id, exc)
            return False

    def set_user_vip(self, user_id: int, is_vip: bool, duration_days: Optional[int] = None) -> bool:
        try:
            with self.transaction() as cursor:
                if is_vip:
                    if duration_days and duration_days > 0:
                        cursor.execute(
                            """
                            UPDATE users
                            SET is_vip = TRUE,
                                vip_until = DATE_ADD(NOW(), INTERVAL %s DAY)
                            WHERE user_id = %s
                            """,
                            (duration_days, int(user_id))
                        )
                    else:
                        cursor.execute("UPDATE users SET is_vip = TRUE, vip_until = NULL WHERE user_id = %s", (int(user_id),))
                else:
                    cursor.execute("UPDATE users SET is_vip = FALSE, vip_until = NULL WHERE user_id = %s", (int(user_id),))

            self.clear_cache(f"vip_{user_id}")
            return True
        except Exception as exc:
            logger.error("Erreur mise à jour VIP %s : %s", user_id, exc)
            return False

    def get_vip_users_list(self) -> List[Dict[str, Any]]:
        try:
            with self.get_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT user_id, username, first_name, is_vip, vip_until, date_inscription
                    FROM users
                    WHERE is_vip = TRUE AND (vip_until IS NULL OR vip_until > NOW())
                    ORDER BY vip_until ASC
                    """
                )
                return cursor.fetchall()
        except Exception as exc:
            logger.error("Erreur lecture VIPs : %s", exc)
            return []

    def get_user_vip_auto_assign(self, user_id: int) -> str:
        cache_key = f"vip_auto_assign_{user_id}"
        cached = self._get_cached_value(cache_key)
        if cached is not None:
            return cached

        try:
            with self.get_cursor() as cursor:
                cursor.execute("SELECT vip_auto_assign FROM users WHERE user_id = %s", (int(user_id),))
                row = cursor.fetchone()
                val = str(row.get("vip_auto_assign") or "prompt") if row else "prompt"
                self._set_cached_value(cache_key, val)
                return val
        except Exception as exc:
            logger.error("Erreur lecture vip_auto_assign pour %s : %s", user_id, exc)
            return "prompt"

    def set_user_vip_auto_assign(self, user_id: int, setting: str) -> bool:
        try:
            with self.transaction() as cursor:
                cursor.execute("UPDATE users SET vip_auto_assign = %s WHERE user_id = %s", (str(setting), int(user_id)))
            self.clear_cache(f"vip_auto_assign_{user_id}")
            return True
        except Exception as exc:
            logger.error("Erreur écriture vip_auto_assign (%s) pour %s : %s", setting, user_id, exc)
            return False

    # ==================== STATISTIQUES UTILISATEUR ====================

    def get_user_stats(self, user_id: int, demande_id: Optional[int] = None) -> Dict[str, Any]:
        try:
            user_id = int(user_id)
        except (ValueError, TypeError):
            pass

        stats = {
            "user_id": user_id,
            "username": None,
            "prenom": "Utilisateur",
            "is_vip": False,
            "vip_until": None,
            "date_inscription": None,
            "derniere_activite": None,
            "total_demandes": 0,
            "en_cours": 0,
            "reussies": 0,
            "abandonnees": 0,
            "en_attente": 0,
            "total_prio": 0,
            "montant_total_investi": 0.0,
        }

        try:
            with self.get_cursor() as cursor:
                if demande_id:
                    cursor.execute("SELECT user_id, prenom, nom, date_creation FROM demandes WHERE id = %s", (demande_id,))
                    d_origin = cursor.fetchone()
                    if d_origin and d_origin.get("user_id"):
                        user_id = int(d_origin["user_id"])
                        stats["user_id"] = user_id
                        stats["date_inscription"] = d_origin.get("date_creation")

                try:
                    cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
                    u_row = cursor.fetchone()
                    if u_row:
                        stats["username"] = u_row.get("username")
                        stats["prenom"] = u_row.get("first_name") or u_row.get("prenom") or "Utilisateur"
                        stats["is_vip"] = bool(u_row.get("is_vip"))
                        stats["vip_until"] = u_row.get("vip_until")
                        stats["date_inscription"] = u_row.get("date_inscription") or stats["date_inscription"]
                        stats["derniere_activite"] = u_row.get("derniere_activite")
                except Exception as e_user:
                    logger.debug("Info lecture table users : %s", e_user)

                cursor.execute(
                    """
                    SELECT
                        COUNT(*) AS total,
                        SUM(CASE WHEN statut = '🔄 En cours' THEN 1 ELSE 0 END) AS en_cours,
                        SUM(CASE WHEN statut IN ('📥 Reçue', '⏳ En attente', '🎯 Assignée (VIP)') THEN 1 ELSE 0 END) AS en_attente,
                        SUM(CASE WHEN statut = '✅ Réussie' THEN 1 ELSE 0 END) AS reussies,
                        SUM(CASE WHEN statut = '❌ Abandonnée' THEN 1 ELSE 0 END) AS abandonnees,
                        SUM(CASE WHEN prioritaire = 1 THEN 1 ELSE 0 END) AS total_prio,
                        COALESCE(SUM(CASE WHEN prioritaire = 1 THEN montant ELSE 0 END), 0) AS montant_total
                    FROM demandes
                    WHERE user_id = %s
                    """,
                    (user_id,)
                )
                d_row = cursor.fetchone()

                cursor.execute(
                    """
                    SELECT
                        COUNT(*) AS total_archives,
                        SUM(CASE WHEN statut = '✅ Réussie' THEN 1 ELSE 0 END) AS reussies_arch,
                        SUM(CASE WHEN statut = '❌ Abandonnée' THEN 1 ELSE 0 END) AS abandonnees_arch,
                        COALESCE(SUM(CASE WHEN prioritaire = 1 THEN montant ELSE 0 END), 0) AS montant_arch
                    FROM archives
                    WHERE user_id = %s
                    """,
                    (user_id,)
                )
                a_row = cursor.fetchone()

                tot_actives = int(d_row["total"]) if d_row and d_row.get("total") else 0
                tot_archives = int(a_row["total_archives"]) if a_row and a_row.get("total_archives") else 0
                stats["total_demandes"] = tot_actives + tot_archives

                if d_row:
                    stats["en_cours"] = int(d_row.get("en_cours") or 0)
                    stats["en_attente"] = int(d_row.get("en_attente") or 0)
                    stats["reussies"] = int(d_row.get("reussies") or 0)
                    stats["abandonnees"] = int(d_row.get("abandonnees") or 0)
                    stats["total_prio"] = int(d_row.get("total_prio") or 0)
                    montant_actif = float(d_row.get("montant_total") or 0.0)
                else:
                    montant_actif = 0.0

                if a_row:
                    stats["reussies"] += int(a_row.get("reussies_arch") or 0)
                    stats["abandonnees"] += int(a_row.get("abandonnees_arch") or 0)
                    montant_arch = float(a_row.get("montant_arch") or 0.0)
                else:
                    montant_arch = 0.0

                stats["montant_total_investi"] = round(montant_actif + montant_arch, 2)

            return stats
        except Exception as exc:
            logger.error("Erreur calcul statistiques utilisateur %s : %s", user_id, exc, exc_info=True)
            return stats