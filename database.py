"""Module centralisé de gestion de la base de données MySQL avec pool de connexions et transactions."""

import logging
import time
from contextlib import contextmanager
from typing import Any, Dict, List, Optional
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
        self._cache_ttl = 300.0  # Durée de validité du cache : 5 minutes

        self._init_connection_pool()
        logger.info("DatabaseManager initialisé avec pool de %d connexions.", self.pool_size)

    def _init_connection_pool(self):
            """Initialise le pool de connexions MySQL avec chargement direct du .env."""
            import os
            from dotenv import load_dotenv

            # Force le rechargement du fichier .env depuis le dossier racine du bot
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
                prenom VARCHAR(64),
                derniere_activite DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                date_inscription DATETIME DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """,
            """
            CREATE TABLE IF NOT EXISTS admins (
                user_id BIGINT PRIMARY KEY,
                alias VARCHAR(64) NOT NULL,
                added_by BIGINT,
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
                date_creation DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_user (user_id),
                INDEX idx_statut (statut)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """,
            """
            CREATE TABLE IF NOT EXISTS demandes_suivi (
                id INT AUTO_INCREMENT PRIMARY KEY,
                demande_id INT NOT NULL,
                admin_id BIGINT NOT NULL,
                date_prise_en_charge DATETIME DEFAULT CURRENT_TIMESTAMP,
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
            """
        ]
        try:
            with self.get_cursor() as cursor:
                for query in tables:
                    cursor.execute(query)
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

    # ==================== TABLE CONFIG (CENTRALISÉE) ====================

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

    def get_owner_id(self) -> int:
        """Retourne l'identifiant du compte propriétaire configuré."""
        val = self.get_config_value("owner_id", str(getattr(self.config, "OWNER_ID", 0)))
        return int(val) if str(val).isdigit() else 0

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


# Alias global pour rétrocompatibilité
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