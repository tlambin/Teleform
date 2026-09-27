"""Gestionnaire de persistance MySQL avec pool de connexions et cache applicatif."""

from contextlib import contextmanager
import logging
import os
import time
from typing import Any, Dict, Optional
from dotenv import load_dotenv
import mysql.connector
from mysql.connector import Error, pooling

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Gère le pool de connexions MySQL et le cache applicatif."""

    def __init__(self, config, pool_size: int = 2):
        self.config = config
        self.pool_size = pool_size
        self._pool: Optional[pooling.MySQLConnectionPool] = None
        self._pool_pid: Optional[int] = None
        self._cache: Dict[str, Any] = {}
        self._cache_timestamp: Dict[str, float] = {}
        self._cache_ttl = 300.0
        self.database_name = ""

        self._init_connection_pool()
        logger.info("ConnectionManager initialisé avec pool de %d connexions.", self.pool_size)

    def _get_db_config(self) -> dict:
        """Charge la configuration MySQL depuis l'environnement ou config."""
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
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
        self.database_name = (
            os.getenv("DB_NAME")
            or getattr(self.config, "DB_NAME", None)
            or getattr(self.config, "db_name", None)
            or "paraworld$telegramDB"
        )
        port = int(os.getenv("DB_PORT", 3306))

        return {
            "host": host,
            "user": user,
            "password": password,
            "database": self.database_name,
            "port": port,
            "autocommit": False,
            "buffered": True,
            "connect_timeout": 10,
        }

    def _init_connection_pool(self):
        """Initialise le pool de connexions MySQL pour le PID courant."""
        db_config = self._get_db_config()
        current_pid = os.getpid()
        pool_name = f"bot_pool_{current_pid}_{int(time.time())}"

        try:
            self._pool = pooling.MySQLConnectionPool(
                pool_name=pool_name,
                pool_size=self.pool_size,
                pool_reset_session=True,
                **db_config,
            )
            self._pool_pid = current_pid
            logger.info("Pool MySQL établi sur %s (base : %s) [PID: %d]", db_config["host"], self.database_name, current_pid)
        except Error as exc:
            if getattr(exc, "errno", None) == 1226:
                logger.error("Quota max_user_connections atteint. Utilisation de connexions directes.")
            else:
                logger.critical("Échec initialisation pool MySQL sur %s : %s", db_config.get("host"), exc, exc_info=True)
            self._pool = None
            self._pool_pid = None

    def _apply_session_settings(self, conn):
        """Applique les réglages de session anti-deadlock."""
        try:
            with conn.cursor() as cursor:
                cursor.execute("SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED")
                cursor.execute("SET SESSION innodb_lock_wait_timeout = 10")
                cursor.execute("SET SESSION sql_mode = 'STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION'")
        except Exception as exc:
            logger.debug("Application des réglages de session ignorée ou impossible : %s", exc)

    def _create_direct_connection(self):
        """Établit une connexion MySQL unitaire directe."""
        db_config = self._get_db_config()
        conn = mysql.connector.connect(**db_config)
        self._apply_session_settings(conn)
        return conn

    def _get_connection(self):
        """Récupère une connexion saine avec détection post-fork."""
        if self._pool_pid != os.getpid():
            self._init_connection_pool()

        conn = None
        if self._pool:
            try:
                conn = self._pool.get_connection()
            except Error as pool_err:
                logger.warning("Connexion depuis pool indisponible (%s), bascule en directe.", pool_err)
                conn = None

        if conn is None:
            conn = self._create_direct_connection()

        try:
            conn.ping(reconnect=True, attempts=3, delay=1)
            if not conn.is_connected():
                conn.reconnect(attempts=3, delay=1)
        except Exception as ping_err:
            logger.warning("Connexion perdue (%s), recréation...", ping_err)
            try:
                conn.close()
            except Exception:
                pass
            conn = self._create_direct_connection()

        self._apply_session_settings(conn)
        return conn

    @contextmanager
    def get_cursor(self, dictionary: bool = True):
        """Gestionnaire de contexte sécurisé sans fuite sous uWSGI."""
        conn = self._get_connection()
        cursor = None
        try:
            cursor = conn.cursor(dictionary=dictionary)
            yield cursor
            conn.commit()
        except Exception as exc:
            try:
                conn.rollback()
            except Exception:
                pass
            logger.error("Erreur SQL dans get_cursor : %s", exc)
            raise
        finally:
            if cursor:
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
        """Gestionnaire de contexte pour transactions atomiques."""
        conn = self._get_connection()
        cursor = None
        try:
            cursor = conn.cursor(dictionary=dictionary)
            yield cursor
            conn.commit()
            logger.debug("Transaction SQL validée (commit).")
        except Exception as exc:
            try:
                conn.rollback()
            except Exception:
                pass
            logger.error("Échec transaction SQL. Rollback exécuté : %s", exc)
            raise
        finally:
            if cursor:
                try:
                    cursor.close()
                except Exception:
                    pass
            try:
                conn.close()
            except Exception:
                pass

    # ==================== CACHE EN RAM ====================

    def _get_cached_value(self, key: str) -> Optional[Any]:
        now = time.time()
        if key in self._cache and (now - self._cache_timestamp.get(key, 0)) < self._cache_ttl:
            return self._cache[key]
        return None

    def _set_cached_value(self, key: str, value: Any):
        self._cache[key] = value
        self._cache_timestamp[key] = time.time()

    def clear_cache(self, key: Optional[str] = None):
        if key:
            self._cache.pop(key, None)
            self._cache_timestamp.pop(key, None)
        else:
            self._cache.clear()
            self._cache_timestamp.clear()

    def get_database_size(self) -> Dict[str, Any]:
        """Taille de la base de données."""
        try:
            db_name = getattr(self, "database_name", None) or os.getenv("DB_NAME", "paraworld$telegramDB")
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
                    (db_name,),
                )
                tables = cursor.fetchall()
                total_size = sum(float(t.get("size_mb", 0) or 0) for t in tables)

            return {
                "total_size_mb": round(total_size, 2),
                "tables": tables,
            }
        except Exception as exc:
            logger.error("Erreur calcul taille base de données : %s", exc)
            return {"total_size_mb": 0.0, "tables": []}