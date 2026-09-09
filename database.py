"""Module centralisé de gestion de la base de données MySQL avec pool de connexions et transactions."""

from contextlib import contextmanager
from datetime import datetime
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple
from dotenv import load_dotenv
import mysql.connector
from mysql.connector import Error, pooling

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Gestionnaire de persistance MySQL avec pool de connexions réutilisables et cache applicatif."""

    def __init__(self, config, pool_size: int = 5):
        self.config = config
        self.pool_size = pool_size
        self._pool: Optional[pooling.MySQLConnectionPool] = None
        self._cache: Dict[str, Any] = {}
        self._cache_timestamp: Dict[str, float] = {}
        self._cache_ttl = 300.0

        self._init_connection_pool()
        logger.info("DatabaseManager initialisé avec pool de %d connexions.", self.pool_size)

    def _init_connection_pool(self):
        """Initialise le pool de connexions MySQL avec chargement direct du .env."""
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        if os.path.exists(env_path):
            load_dotenv(dotenv_path=env_path, override=True)

        host = (
            os.getenv("DB_HOST")
            or getattr(self.config, "DB_HOST", None)
            or getattr(self.config, "db_host", None)
            or "paraworld.mysql.eu.pythonanywhere-services.com"
        )
        user = (
            os.getenv("DB_USER")
            or getattr(self.config, "DB_USER", None)
            or getattr(self.config, "db_user", None)
            or "paraworld"
        )
        password = (
            os.getenv("DB_PASSWORD")
            or getattr(self.config, "DB_PASSWORD", None)
            or getattr(self.config, "db_password", None)
            or ""
        )
        database = (
            os.getenv("DB_NAME")
            or getattr(self.config, "DB_NAME", None)
            or getattr(self.config, "db_name", None)
            or "paraworld$telegramDB"
        )
        port = int(os.getenv("DB_PORT", 3306))

        db_config = {
            "host": host,
            "user": user,
            "password": password,
            "database": database,
            "port": port,
            "autocommit": False,
            "buffered": True,
            "connect_timeout": 10,
        }

        pool_name = f"bot_pool_{int(time.time())}"
        try:
            self._pool = pooling.MySQLConnectionPool(
                pool_name=pool_name,
                pool_size=self.pool_size,
                pool_reset_session=True,
                **db_config,
            )
            logger.info("Pool MySQL établi sur %s (base: %s)", host, database)
        except Error as exc:
            logger.critical("Échec de connexion MySQL au serveur %s : %s", host, exc, exc_info=True)
            raise

    def _get_connection(self):
        """Récupère une connexion disponible depuis le pool ou réinitialise si épuisé."""
        try:
            if not self._pool:
                self._init_connection_pool()
            conn = self._pool.get_connection()
            if not conn.is_connected():
                conn.reconnect(attempts=3, delay=1)
            return conn
        except (Error, Exception) as exc:
            logger.warning("Connexion perdue ou pool saturé (%s), tentative de réinitialisation...", exc)
            self._init_connection_pool()
            return self._pool.get_connection()

    @contextmanager
    def get_cursor(self, dictionary: bool = True):
        """Gestionnaire de contexte pour requêtes unitaires avec commit automatique."""
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=dictionary)
        try:
            yield cursor
            conn.commit()
        except Exception as exc:
            conn.rollback()
            logger.error("Erreur SQL dans get_cursor: %s", exc)
            raise
        finally:
            try:
                cursor.close()
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass

    @contextmanager
    def transaction(self, dictionary: bool = True):
        """Gestionnaire de contexte pour transactions atomiques multi-tables."""
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=dictionary)
        try:
            yield cursor
            conn.commit()
            logger.debug("Transaction SQL validée avec succès (commit).")
        except Exception as exc:
            conn.rollback()
            logger.error("Échec transaction SQL. Annulation complète exécutée (rollback): %s", exc)
            raise
        finally:
            try:
                cursor.close()
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass

    def create_tables(self):
        """Crée ou met à jour les tables nécessaires au fonctionnement du bot."""
        tables = [
            """
            CREATE TABLE IF NOT EXISTS config (
                key_name VARCHAR(64) PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """,
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username VARCHAR(64),
                first_name VARCHAR(64),
                is_vip BOOLEAN DEFAULT FALSE,
                vip_until DATETIME DEFAULT NULL,
                derniere_activite DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                date_inscription DATETIME DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """,
            """
            CREATE TABLE IF NOT EXISTS admins (
                user_id BIGINT PRIMARY KEY,
                alias VARCHAR(64) NOT NULL,
                added_by BIGINT,
                perm_reseaux VARCHAR(16) DEFAULT 'all',
                perm_type VARCHAR(16) DEFAULT 'all',
                alias_locked BOOLEAN DEFAULT FALSE,
                is_paused BOOLEAN DEFAULT FALSE,
                date_added DATETIME DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """,
            """
            CREATE TABLE IF NOT EXISTS demandes (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                prenom VARCHAR(64) NOT NULL,
                nom VARCHAR(64),
                age INT,
                localisation VARCHAR(128),
                photo_id VARCHAR(256),
                instagram VARCHAR(64),
                snapchat VARCHAR(64),
                details TEXT,
                prioritaire BOOLEAN DEFAULT FALSE,
                montant DECIMAL(10, 2) DEFAULT 0.00,
                statut VARCHAR(32) DEFAULT '📨 Reçue',
                admin_en_charge BIGINT DEFAULT NULL,
                ancien_admin_alias VARCHAR(64) DEFAULT NULL,
                raison_abandon TEXT DEFAULT NULL,
                last_vip_reminder DATETIME DEFAULT NULL,
                date_creation DATETIME DEFAULT CURRENT_TIMESTAMP,
                date_modification DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                request_number INT DEFAULT NULL,
                INDEX idx_user (user_id),
                INDEX idx_statut (statut)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """,
            """
            CREATE TABLE IF NOT EXISTS demandes_suivi (
                id INT AUTO_INCREMENT PRIMARY KEY,
                demande_id INT NOT NULL,
                admin_id BIGINT NOT NULL,
                date_suivi DATETIME DEFAULT CURRENT_TIMESTAMP,
                derniere_action DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                statut_suivi VARCHAR(32) DEFAULT 'active',
                UNIQUE KEY unique_demande_admin (demande_id, admin_id),
                INDEX idx_admin (admin_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """,
            """
            CREATE TABLE IF NOT EXISTS archives (
                id INT AUTO_INCREMENT PRIMARY KEY,
                original_id INT NOT NULL,
                user_id BIGINT NOT NULL,
                prenom VARCHAR(64),
                nom VARCHAR(64),
                age INT,
                localisation VARCHAR(128),
                photo_id VARCHAR(256),
                instagram VARCHAR(64),
                snapchat VARCHAR(64),
                details TEXT,
                prioritaire BOOLEAN DEFAULT FALSE,
                montant DECIMAL(10, 2) DEFAULT 0.00,
                statut VARCHAR(32),
                date_creation DATETIME,
                date_archivage DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_archive_user (user_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """,
            """
            CREATE TABLE IF NOT EXISTS admin_preferences (
                user_id BIGINT PRIMARY KEY,
                notif_new_mode VARCHAR(16) DEFAULT 'sound',
                rappel_mode VARCHAR(16) DEFAULT 'sound',
                rappel_freq VARCHAR(16) DEFAULT 'daily',
                rappel_heure INT DEFAULT 18,
                rappel_jour_semaine INT DEFAULT 6,
                rappel_jour_mois INT DEFAULT 1,
                last_rappel_date DATE DEFAULT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """
        ]
        try:
            with self.get_cursor() as cursor:
                for query in tables:
                    cursor.execute(query)

                columns_to_add = [
                    ("admins", "perm_reseaux", "VARCHAR(16) DEFAULT 'all'"),
                    ("admins", "perm_type", "VARCHAR(16) DEFAULT 'all'"),
                    ("admins", "alias_locked", "BOOLEAN DEFAULT FALSE"),
                    ("admins", "is_paused", "BOOLEAN DEFAULT FALSE"),
                    ("demandes", "admin_en_charge", "BIGINT DEFAULT NULL"),
                    ("demandes", "ancien_admin_alias", "VARCHAR(64) DEFAULT NULL"),
                    ("demandes", "raison_abandon", "TEXT DEFAULT NULL"),
                    ("demandes", "request_number", "INT DEFAULT NULL"),
                    ("demandes", "date_modification", "DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
                    ("demandes", "last_vip_reminder", "DATETIME DEFAULT NULL"),
                    ("admin_preferences", "notif_new_mode", "VARCHAR(16) DEFAULT 'sound'"),
                    ("admin_preferences", "rappel_mode", "VARCHAR(16) DEFAULT 'sound'"),
                    ("admin_preferences", "rappel_freq", "VARCHAR(16) DEFAULT 'daily'"),
                    ("admin_preferences", "rappel_heure", "INT DEFAULT 18"),
                    ("admin_preferences", "rappel_jour_semaine", "INT DEFAULT 6"),
                    ("admin_preferences", "rappel_jour_mois", "INT DEFAULT 1"),
                    ("admin_preferences", "last_rappel_date", "DATE DEFAULT NULL"),
                    ("users", "is_vip", "BOOLEAN DEFAULT FALSE"),
                    ("users", "vip_until", "DATETIME DEFAULT NULL"),
                ]
                for table, col, col_def in columns_to_add:
                    try:
                        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}")
                        logger.info("Colonne %s.%s vérifiée/ajoutée.", table, col)
                    except Error as e:
                        if getattr(e, "errno", None) != 1060:
                            logger.debug("Info colonne %s.%s : %s", table, col, e)

            logger.info("Vérification et création des tables terminées avec succès.")
        except Exception as exc:
            logger.error("Erreur lors de la création des tables : %s", exc)
            raise

    # ==================== GESTION DU CACHE EN MÉMOIRE ====================

    def _get_cached_value(self, key: str) -> Optional[Any]:
        """Retourne la valeur en cache si elle n'a pas expiré."""
        now = time.time()
        if key in self._cache and (now - self._cache_timestamp.get(key, 0)) < self._cache_ttl:
            return self._cache[key]
        return None

    def _set_cached_value(self, key: str, value: Any):
        """Met en cache une valeur avec horodatage."""
        self._cache[key] = value
        self._cache_timestamp[key] = time.time()

    def clear_cache(self, key: Optional[str] = None):
        """Purge une clé spécifique ou l'intégralité du cache."""
        if key:
            self._cache.pop(key, None)
            self._cache_timestamp.pop(key, None)
        else:
            self._cache.clear()
            self._cache_timestamp.clear()

    # ==================== TABLE CONFIG ====================

    def get_config_value(self, key_name: str, default: Optional[str] = None) -> Optional[str]:
        """Récupère une valeur de configuration depuis la table config."""
        cache_key = f"cfg_{key_name}"
        cached = self._get_cached_value(cache_key)
        if cached is not None:
            return cached

        try:
            with self.get_cursor() as cursor:
                cursor.execute(
                    "SELECT value FROM config WHERE key_name = %s",
                    (key_name,),
                )
                row = cursor.fetchone()
                val = row["value"] if row else default
                self._set_cached_value(cache_key, val)
                return val
        except Exception as exc:
            logger.error("Erreur lecture config '%s': %s", key_name, exc)
            return default

    def set_config_value(self, key_name: str, value: str) -> bool:
        """Met à jour ou insère un paramètre dans la table config avec invalidation du cache."""
        try:
            with self.get_cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO config (key_name, value, updated_at)
                    VALUES (%s, %s, NOW())
                    ON DUPLICATE KEY UPDATE value = VALUES(value), updated_at = NOW()
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
        """Retourne l'ensemble des clés de configuration sous forme de dictionnaire."""
        cached = self._get_cached_value("cfg_all")
        if cached is not None:
            return cached

        try:
            with self.get_cursor() as cursor:
                cursor.execute("SELECT key_name, value FROM config")
                rows = cursor.fetchall()
                result = {r["key_name"]: r["value"] for r in rows}
                self._set_cached_value("cfg_all", result)
                return result
        except Exception as exc:
            logger.error("Erreur lecture globale config: %s", exc)
            return {}

    def is_bot_active(self) -> bool:
        """Indique si la création de demandes est activée."""
        val = self.get_config_value("bot_active", "true")
        return str(val).lower() == "true"

    def set_bot_active(self, active: bool) -> bool:
        """Bascule l'acceptation globale des demandes."""
        return self.set_config_value("bot_active", "true" if active else "false")

    def get_max_total_demandes(self) -> int:
        """Retourne la limite globale de demandes (0 = illimité)."""
        val = self.get_config_value("max_total_demandes", "0")
        try:
            return int(val)
        except (ValueError, TypeError):
            return 0

    def set_max_total_demandes(self, limit: int) -> bool:
        """Met à jour le plafond global de demandes."""
        return self.set_config_value("max_total_demandes", str(max(0, limit)))

    def get_max_demandes_per_user(self) -> int:
        """Retourne la limite par utilisateur (3 par défaut, 0 = illimité)."""
        val = self.get_config_value("max_demandes_per_user", "3")
        try:
            return int(val)
        except (ValueError, TypeError):
            return 3

    def set_max_demandes_per_user(self, limit: int) -> bool:
        """Met à jour le plafond par utilisateur."""
        return self.set_config_value("max_demandes_per_user", str(max(0, limit)))

    def get_owner_id(self) -> int:
        """Retourne l'identifiant du compte propriétaire configuré."""
        val = self.get_config_value("owner_id", str(getattr(self.config, "OWNER_ID", 0)))
        return int(val) if str(val).isdigit() else 0

    def get_owner_alias(self) -> str:
        """Retourne l'alias configuré du propriétaire."""
        return self.get_config_value("owner_alias", "Propriétaire")

    def set_owner_alias(self, alias: str) -> bool:
        """Définit l'alias du propriétaire."""
        return self.set_config_value("owner_alias", alias)

    # ==================== TABLE ADMINS ====================

    def get_admin_alias(self, user_id: int) -> str:
        """Retourne le pseudonyme officiel de l'administrateur ou du propriétaire."""
        cache_key = f"alias_{user_id}"
        cached = self._get_cached_value(cache_key)
        if cached:
            return cached

        if self.config.is_owner(user_id):
            alias = self.get_config_value("owner_alias", "Propriétaire")
            self._set_cached_value(cache_key, alias)
            return alias

        try:
            with self.get_cursor() as cursor:
                cursor.execute(
                    "SELECT alias FROM admins WHERE user_id = %s",
                    (user_id,),
                )
                row = cursor.fetchone()
                alias = row["alias"] if row and row.get("alias") else "Admin"
                self._set_cached_value(cache_key, alias)
                return alias
        except Exception as exc:
            logger.error("Erreur extraction alias admin %s: %s", user_id, exc)
            return "Admin"

    def set_admin_alias(self, user_id: int, new_alias: str) -> bool:
        """Met à jour le pseudonyme d'un administrateur ou du propriétaire."""
        clean_alias = new_alias.strip()

        if self.config.is_owner(user_id):
            ok = self.set_config_value("owner_alias", clean_alias)
            if ok:
                self.clear_cache(f"alias_{user_id}")
            return ok

        try:
            with self.get_cursor() as cursor:
                cursor.execute(
                    "UPDATE admins SET alias = %s WHERE user_id = %s",
                    (clean_alias, user_id),
                )
            self.clear_cache(f"alias_{user_id}")
            return True
        except Exception as exc:
            logger.error("Erreur mise à jour alias admin %s: %s", user_id, exc)
            return False

    def can_admin_edit_alias(self, user_id: int) -> bool:
        """Indique si l'admin peut encore définir son alias (l'owner peut toujours)."""
        if self.config.is_owner(user_id):
            return True
        try:
            with self.get_cursor() as cursor:
                cursor.execute("SELECT alias_locked FROM admins WHERE user_id = %s", (user_id,))
                row = cursor.fetchone()
                return not bool(row.get("alias_locked")) if row else False
        except Exception as exc:
            logger.error("Erreur vérification verrou alias pour %s: %s", user_id, exc)
            return False

    def lock_admin_alias(self, user_id: int):
        """Verrouille définitivement l'alias pour un administrateur."""
        try:
            with self.get_cursor() as cursor:
                cursor.execute("UPDATE admins SET alias_locked = TRUE WHERE user_id = %s", (user_id,))
            self.clear_cache(f"alias_{user_id}")
        except Exception as exc:
            logger.error("Erreur verrouillage alias %s: %s", user_id, exc)

    # ==================== MODE PAUSE ADMINISTRATEUR ====================

    def is_admin_paused(self, user_id: int) -> bool:
        """Indique si un administrateur est actuellement en mode pause."""
        cache_key = f"admin_paused_{user_id}"
        cached = self._get_cached_value(cache_key)
        if cached is not None:
            return cached

        try:
            with self.get_cursor() as cursor:
                cursor.execute("SELECT is_paused FROM admins WHERE user_id = %s", (int(user_id),))
                row = cursor.fetchone()
                val = bool(row.get("is_paused")) if row else False
                self._set_cached_value(cache_key, val)
                return val
        except Exception as exc:
            logger.error("Erreur vérification mode pause pour %s : %s", user_id, exc)
            return False

    def set_admin_pause_status(self, user_id: int, paused: bool) -> bool:
        """Active ou désactive le mode pause d'un administrateur."""
        try:
            with self.get_cursor() as cursor:
                cursor.execute(
                    "UPDATE admins SET is_paused = %s WHERE user_id = %s",
                    (paused, int(user_id))
                )
            self.clear_cache(f"admin_paused_{user_id}")
            return True
        except Exception as exc:
            logger.error("Erreur modification mode pause pour %s : %s", user_id, exc)
            return False

    def get_admin_active_demandes(self, admin_id: int) -> List[Dict[str, Any]]:
        """Récupère les demandes en cours prises en charge par un administrateur."""
        try:
            with self.get_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT d.id, d.user_id, d.request_number, d.prenom, d.nom, d.statut
                    FROM demandes d
                    JOIN demandes_suivi ds ON d.id = ds.demande_id
                    WHERE ds.admin_id = %s AND d.statut IN ('🔄 En cours', '⏳ En attente', '⚠️ Difficile')
                    """,
                    (int(admin_id),)
                )
                return cursor.fetchall()
        except Exception as exc:
            logger.error("Erreur récupération demandes actives admin %s : %s", admin_id, exc)
            return []

    def abandon_admin_demandes_for_pause(self, admin_id: int) -> List[Dict[str, Any]]:
        """Passe toutes les demandes actives d'un admin en statut abandonné pour cause d'arrêt."""
        alias = self.get_admin_alias(admin_id)
        reason = f"Piégeur ({alias}) actuellement à l'arrêt / en pause."

        try:
            with self.transaction() as cursor:
                cursor.execute(
                    """
                    SELECT d.id, d.user_id, d.request_number, d.prenom
                    FROM demandes d
                    JOIN demandes_suivi ds ON d.id = ds.demande_id
                    WHERE ds.admin_id = %s AND d.statut IN ('🔄 En cours', '⏳ En attente', '⚠️ Difficile')
                    """,
                    (int(admin_id),)
                )
                rows = cursor.fetchall()

                if rows:
                    ids = [r["id"] for r in rows]
                    placeholders = ", ".join(["%s"] * len(ids))

                    cursor.execute(
                        f"""
                        UPDATE demandes
                        SET statut = '❌ Abandonnée',
                            ancien_admin_alias = %s,
                            admin_en_charge = NULL,
                            raison_abandon = %s,
                            date_modification = NOW()
                        WHERE id IN ({placeholders})
                        """,
                        (alias, reason, *ids)
                    )
                    cursor.execute(f"DELETE FROM demandes_suivi WHERE demande_id IN ({placeholders})", ids)

            return rows
        except Exception as exc:
            logger.error("Erreur abandon des demandes suite pause admin %s : %s", admin_id, exc)
            return []

    # ==================== GESTION DES PERMISSIONS ADMIN ====================

    def get_admin_permissions(self, user_id: int) -> Dict[str, str]:
        """Retourne les permissions de traitement d'un admin (l'owner a toujours accès total)."""
        if self.config.is_owner(user_id):
            return {"perm_reseaux": "all", "perm_type": "all"}

        cache_key = f"perm_{user_id}"
        cached = self._get_cached_value(cache_key)
        if cached is not None:
            return cached

        default_perms = {"perm_reseaux": "all", "perm_type": "all"}
        try:
            with self.get_cursor() as cursor:
                cursor.execute(
                    "SELECT perm_reseaux, perm_type FROM admins WHERE user_id = %s",
                    (user_id,)
                )
                row = cursor.fetchone()
                if row:
                    default_perms["perm_reseaux"] = row.get("perm_reseaux") or "all"
                    default_perms["perm_type"] = row.get("perm_type") or "all"
            self._set_cached_value(cache_key, default_perms)
            return default_perms
        except Exception as exc:
            logger.error("Erreur lecture permissions admin %s: %s", user_id, exc)
            return default_perms

    def update_admin_permission(self, user_id: int, perm_key: str, perm_value: str) -> bool:
        """Met à jour une permission spécifique d'un admin."""
        if perm_key not in ("perm_reseaux", "perm_type"):
            return False
        try:
            with self.get_cursor() as cursor:
                cursor.execute(
                    f"UPDATE admins SET {perm_key} = %s WHERE user_id = %s",
                    (perm_value, user_id)
                )
            self.clear_cache(f"perm_{user_id}")
            return True
        except Exception as exc:
            logger.error("Erreur mise à jour permission %s pour admin %s: %s", perm_key, user_id, exc)
            return False

    # ==================== PRÉFÉRENCES NOTIFICATIONS & RAPPELS ====================

    def get_admin_preferences(self, user_id: int) -> Dict[str, Any]:
        """Retourne les réglages de notifications d'un administrateur avec valeurs par défaut."""
        default_prefs = {
            "user_id": user_id,
            "notif_new_mode": "sound",
            "rappel_mode": "sound",
            "rappel_freq": "daily",
            "rappel_heure": 18,
            "rappel_jour_semaine": 6,
            "rappel_jour_mois": 1,
            "last_rappel_date": None
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
                            rappel_heure, rappel_jour_semaine, rappel_jour_mois
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE user_id = VALUES(user_id)
                        """,
                        (user_id, "sound", "sound", "daily", 18, 6, 1)
                    )
            self._set_cached_value(cache_key, default_prefs)
            return default_prefs
        except Exception as exc:
            logger.error("Erreur récupération préférences admin %s: %s", user_id, exc)
            return default_prefs

    def update_admin_preference(self, user_id: int, key: str, value: Any) -> bool:
        """Met à jour un paramètre des préférences d'un administrateur avec invalidation du cache."""
        allowed_keys = {
            "notif_new_mode", "rappel_mode", "rappel_freq", "rappel_heure",
            "rappel_jour_semaine", "rappel_jour_mois", "last_rappel_date"
        }
        if key not in allowed_keys:
            logger.warning("Clé de préférence admin non autorisée : %s", key)
            return False

        try:
            with self.get_cursor() as cursor:
                cursor.execute(
                    f"""
                    INSERT INTO admin_preferences (user_id, {key})
                    VALUES (%s, %s)
                    ON DUPLICATE KEY UPDATE {key} = VALUES({key})
                    """,
                    (user_id, value)
                )
            self.clear_cache(f"admin_prefs_{user_id}")
            return True
        except Exception as exc:
            logger.error("Erreur mise à jour préférence %s pour admin %s: %s", key, user_id, exc)
            return False

    def mark_admin_reminder_sent(self, user_id: int):
        """Met à jour la date du dernier rappel envoyé à la date du jour."""
        try:
            with self.get_cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE admin_preferences 
                    SET last_rappel_date = CURRENT_DATE() 
                    WHERE user_id = %s
                    """,
                    (user_id,)
                )
            self.clear_cache(f"admin_prefs_{user_id}")
        except Exception as exc:
            logger.error("Erreur mise à jour last_rappel_date pour %s: %s", user_id, exc)

    def get_all_admin_preferences(self) -> List[Dict[str, Any]]:
        """Récupère l'ensemble des préférences des administrateurs dont les rappels sont actifs."""
        try:
            with self.get_cursor() as cursor:
                cursor.execute("SELECT * FROM admin_preferences WHERE rappel_mode != 'off'")
                return cursor.fetchall()
        except Exception as exc:
            logger.error("Erreur lecture globale des préférences admins : %s", exc)
            return []

    # ==================== GESTION CLIENTS VIP & STARS ====================

    def is_user_vip(self, user_id: int) -> bool:
        """Vérifie si un utilisateur dispose du statut VIP actif (permanent ou non expiré)."""
        cache_key = f"vip_{user_id}"
        cached = self._get_cached_value(cache_key)
        if cached is not None:
            return cached

        try:
            with self.get_cursor() as cursor:
                cursor.execute(
                    "SELECT is_vip, vip_until FROM users WHERE user_id = %s",
                    (int(user_id),)
                )
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
        """Active ou désactive le statut VIP pour un utilisateur."""
        try:
            with self.get_cursor() as cursor:
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
                        cursor.execute(
                            "UPDATE users SET is_vip = TRUE, vip_until = NULL WHERE user_id = %s",
                            (int(user_id),)
                        )
                else:
                    cursor.execute(
                        "UPDATE users SET is_vip = FALSE, vip_until = NULL WHERE user_id = %s",
                        (int(user_id),)
                    )

            self.clear_cache(f"vip_{user_id}")
            return True
        except Exception as exc:
            logger.error("Erreur mise à jour VIP %s : %s", user_id, exc)
            return False

    def get_vip_users_list(self) -> List[Dict[str, Any]]:
        """Retourne la liste des membres VIP actifs."""
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

    def get_available_admins_for_selection(self) -> List[Dict[str, Any]]:
        """Retourne la liste des membres disponibles (non en pause) pour le choix VIP."""
        equipe = []
        try:
            owner_id = self.get_owner_id() or getattr(self.config, "OWNER_ID", 0)
            owner_alias = self.get_owner_alias()
            owner_paused = self.is_admin_paused(owner_id)

            if owner_id and not owner_paused:
                equipe.append({"user_id": owner_id, "alias": owner_alias, "role": "Owner"})

            with self.get_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT user_id, alias FROM admins 
                    WHERE (is_paused IS FALSE OR is_paused IS NULL)
                    ORDER BY alias ASC
                    """
                )
                for r in cursor.fetchall():
                    if r["user_id"] != owner_id:
                        equipe.append({"user_id": r["user_id"], "alias": r["alias"], "role": "Admin"})
            return equipe
        except Exception as exc:
            logger.error("Erreur extraction équipe VIP : %s", exc)
            return equipe

    # ==================== RAPPELS DEMANDES (VIP, PAYANTES & STANDARDS) ====================

    def can_send_demande_reminder(self, demande_id: int) -> Tuple[bool, Optional[str]]:
        """Vérifie si le rappel hebdomadaire peut être envoyé (limité à 1 fois par semaine)."""
        try:
            with self.get_cursor() as cursor:
                cursor.execute(
                    "SELECT last_vip_reminder, admin_en_charge FROM demandes WHERE id = %s",
                    (int(demande_id),)
                )
                row = cursor.fetchone()
                if not row:
                    return False, "Demande introuvable."
                if not row.get("admin_en_charge"):
                    return False, "Aucun référent n'est actuellement assigné à cette demande."

                last_rem = row.get("last_vip_reminder")
                if not last_rem:
                    return True, None

                diff_seconds = (datetime.now() - last_rem).total_seconds()
                sept_jours_sec = 7 * 86400
                if diff_seconds < sept_jours_sec:
                    jours_restants = max(1, int((sept_jours_sec - diff_seconds) // 86400))
                    return False, f"Rappel déjà envoyé cette semaine. Nouveau rappel possible dans {jours_restants} jour(s)."

                return True, None
        except Exception as exc:
            logger.error("Erreur contrôle rappel demande %s : %s", demande_id, exc)
            return False, "Erreur technique."

    def record_demande_reminder_sent(self, demande_id: int):
        """Enregistre l'horodatage du rappel envoyé pour la demande."""
        try:
            with self.get_cursor() as cursor:
                cursor.execute(
                    "UPDATE demandes SET last_vip_reminder = NOW() WHERE id = %s",
                    (int(demande_id),)
                )
        except Exception as exc:
            logger.error("Erreur enregistrement rappel demande %s : %s", demande_id, exc)

    # ==================== STATISTIQUES & PROFILS ====================

    def get_admin_stats(self, admin_id: int) -> Dict[str, Any]:
        """Calcule l'ensemble des métriques de performance et de charge d'un administrateur ou du propriétaire."""
        try:
            admin_id = int(admin_id)
        except (ValueError, TypeError):
            pass

        is_owner = self.config.is_owner(admin_id)

        stats = {
            "user_id": admin_id,
            "alias": self.get_admin_alias(admin_id),
            "date_added": None,
            "perm_reseaux": "all",
            "perm_type": "all",
            "en_cours": 0,
            "reussies": 0,
            "abandonnees": 0,
            "total_traitees": 0,
            "taux_reussite": 0.0,
            "prioritaires_traitees": 0,
            "montant_total": 0.0,
        }

        try:
            with self.get_cursor() as cursor:
                if is_owner:
                    stats["alias"] = self.get_owner_alias()
                    stats["perm_reseaux"] = "all"
                    stats["perm_type"] = "all"
                else:
                    cursor.execute(
                        "SELECT alias, date_added, perm_reseaux, perm_type FROM admins WHERE user_id = %s",
                        (admin_id,)
                    )
                    admin_row = cursor.fetchone()
                    if admin_row:
                        stats["alias"] = admin_row.get("alias") or stats["alias"]
                        stats["date_added"] = admin_row.get("date_added")
                        stats["perm_reseaux"] = admin_row.get("perm_reseaux") or "all"
                        stats["perm_type"] = admin_row.get("perm_type") or "all"

                cursor.execute(
                    """
                    SELECT COUNT(*) AS total
                    FROM demandes d
                    JOIN demandes_suivi ds ON d.id = ds.demande_id
                    WHERE ds.admin_id = %s AND d.statut IN ('🔄 En cours', '⏳ En attente', '⚠️ Difficile')
                    """,
                    (admin_id,)
                )
                r_encours = cursor.fetchone()
                stats["en_cours"] = int(r_encours["total"]) if r_encours and r_encours.get("total") else 0

                cursor.execute(
                    """
                    SELECT 
                        SUM(CASE WHEN d.statut = '✅ Réussie' THEN 1 ELSE 0 END) AS reussies,
                        SUM(CASE WHEN d.statut = '❌ Abandonnée' THEN 1 ELSE 0 END) AS abandonnees,
                        SUM(CASE WHEN d.prioritaire = 1 THEN 1 ELSE 0 END) AS nb_prio,
                        COALESCE(SUM(CASE WHEN d.prioritaire = 1 THEN d.montant ELSE 0 END), 0) AS montant_cumule
                    FROM demandes d
                    JOIN demandes_suivi ds ON d.id = ds.demande_id
                    WHERE ds.admin_id = %s
                    """,
                    (admin_id,)
                )
                r_term = cursor.fetchone()
                if r_term:
                    stats["reussies"] = int(r_term.get("reussies") or 0)
                    stats["abandonnees"] = int(r_term.get("abandonnees") or 0)
                    stats["prioritaires_traitees"] = int(r_term.get("nb_prio") or 0)
                    stats["montant_total"] = float(r_term.get("montant_cumule") or 0.0)

                total_fermees = stats["reussies"] + stats["abandonnees"]
                stats["total_traitees"] = total_fermees
                if total_fermees > 0:
                    stats["taux_reussite"] = round((stats["reussies"] / total_fermees) * 100, 1)

            return stats
        except Exception as exc:
            logger.error("Erreur calcul statistiques admin %s: %s", admin_id, exc, exc_info=True)
            return stats

    def get_user_stats(self, user_id: int, demande_id: Optional[int] = None) -> Dict[str, Any]:
        """Calcule le profil statistique complet d'un demandeur avec statut VIP."""
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
                    logger.debug("Info lecture table users: %s", e_user)

                cursor.execute(
                    """
                    SELECT 
                        COUNT(*) AS total,
                        SUM(CASE WHEN statut IN ('🔄 En cours', '⚠️ Difficile') THEN 1 ELSE 0 END) AS en_cours,
                        SUM(CASE WHEN statut IN ('📨 Reçue', '⏳ En attente') THEN 1 ELSE 0 END) AS en_attente,
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
            logger.error("Erreur calcul statistiques utilisateur %s: %s", user_id, exc, exc_info=True)
            return stats

    # ==================== UTILITAIRE / MÉTRIQUES ====================

    def get_database_size(self) -> Dict[str, Any]:
        """Calcule le volume occupé par la base de données et le détail des tables en Mo."""
        try:
            with self.get_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        table_name AS table_name,
                        ROUND(((data_length + index_length) / 1024 / 1024), 2) AS size_mb,
                        table_rows AS row_count
                    FROM information_schema.TABLES
                    WHERE table_schema = %s
                    ORDER BY (data_length + index_length) DESC
                    """,
                    (self.config.DB_NAME,),
                )
                tables = cursor.fetchall()
                total_size = sum(float(t.get("size_mb", 0) or 0) for t in tables)

            return {
                "total_size_mb": round(total_size, 2),
                "tables": tables,
            }
        except Exception as exc:
            logger.error("Erreur calcul taille base de données: %s", exc)
            return {"total_size_mb": 0.0, "tables": []}


_global_db_manager = None

def get_db_manager(config=None):
    """Fournit une instance singleton de DatabaseManager."""
    global _global_db_manager
    if _global_db_manager is None:
        if config is None:
            from config import Config
            config = Config()
        _global_db_manager = DatabaseManager(config)
    return _global_db_manager