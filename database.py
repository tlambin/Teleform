import logging
import threading
import time
from contextlib import contextmanager
from mysql.connector import pooling
from config import Config

logger = logging.getLogger(__name__)

class DatabaseManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, config=None):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, config: Config):
        if not getattr(self, "_initialized", False):
            self.config = config
            self._pool = None
            self._cache = {}
            self._cache_timeout = getattr(config, "CACHE_TIMEOUT", 300)
            self._initialized = True

    def get_connection_pool(self):
        """Crée ou retourne le pool de connexions MySQL."""
        if not self._pool:
            try:
                self._pool = pooling.MySQLConnectionPool(
                    pool_name="bot_pool",
                    pool_size=3,
                    pool_reset_session=True,
                    use_pure=True,
                    **self.config.DB_CONFIG
                )
            except Exception as e:
                logger.error("Erreur création pool DB: %s", e)
                raise ConnectionError(f"Impossible de créer le pool MySQL : {e}") from e
        return self._pool

    def get_connection_with_retry(self, max_retries=3):
        """Connexion avec retry automatique et backoff exponentiel."""
        for attempt in range(max_retries):
            try:
                pool = self.get_connection_pool()
                return pool.get_connection()
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error("Échec connexion après %s tentatives : %s", max_retries, e)
                    raise
                wait_time = 2 ** attempt
                logger.warning("Tentative %s échouée, retry dans %ss", attempt + 1, wait_time)
                time.sleep(wait_time)

    @contextmanager
    def get_cursor(self):
        """Context manager pour gérer proprement curseur, transaction et fermeture."""
        connection = None
        cursor = None
        try:
            connection = self.get_connection_with_retry()
            cursor = connection.cursor(dictionary=True, buffered=True)
            yield cursor
            connection.commit()
        except Exception as e:
            if connection:
                connection.rollback()
            logger.error("Erreur DB pendant la transaction: %s", e)
            raise
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def cache_result(self, key, result):
        """Met en cache un résultat avec timestamp."""
        self._cache[key] = {
            'data': result,
            'timestamp': time.time()
        }

    def get_cached_result(self, key):
        """Récupère une donnée en cache si la durée de vie n'est pas dépassée."""
        if len(self._cache) > 100:
            self.cleanup_expired_cache()

        if key in self._cache:
            cache_entry = self._cache[key]
            if time.time() - cache_entry['timestamp'] < self._cache_timeout:
                return cache_entry['data']
            del self._cache[key]
        return None

    def clear_cache(self):
        """Vide l'ensemble du cache mémoire."""
        self._cache.clear()

    def cleanup_expired_cache(self):
        """Nettoie les entrées expirées."""
        current_time = time.time()
        expired_keys = [
            key for key, entry in self._cache.items()
            if current_time - entry['timestamp'] >= self._cache_timeout
        ]
        for key in expired_keys:
            del self._cache[key]

    def create_tables(self):
        """Crée l'ensemble des tables en assurant l'alignement des clés primaires et étrangères."""
        tables = {
            'config': '''
                CREATE TABLE IF NOT EXISTS config (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    key_name VARCHAR(50) NOT NULL UNIQUE,
                    value VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_key_name (key_name)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            ''',

            'users': '''
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username VARCHAR(50),
                    first_name VARCHAR(50),
                    last_name VARCHAR(50),
                    date_inscription TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    derniere_activite TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            ''',

            'admins': '''
                CREATE TABLE IF NOT EXISTS admins (
                    user_id BIGINT PRIMARY KEY,
                    username VARCHAR(255),
                    first_name VARCHAR(255),
                    alias VARCHAR(50) NOT NULL,
                    added_by BIGINT NOT NULL,
                    date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (added_by) REFERENCES users(user_id),
                    UNIQUE KEY unique_alias (alias),
                    INDEX idx_admins_alias (alias)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            ''',

            'demandes': '''
                CREATE TABLE IF NOT EXISTS demandes (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    request_number INT NOT NULL DEFAULT 1,
                    prenom VARCHAR(50) NOT NULL,
                    nom VARCHAR(50),
                    age INT NOT NULL,
                    localisation VARCHAR(100) NOT NULL,
                    photo_id VARCHAR(255),
                    instagram VARCHAR(50),
                    snapchat VARCHAR(50),
                    details TEXT,
                    prioritaire BOOLEAN DEFAULT FALSE,
                    montant DECIMAL(10,2) DEFAULT 0,
                    statut VARCHAR(20) DEFAULT '📨 Reçue',
                    admin_en_charge BIGINT DEFAULT NULL,
                    date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    date_modification TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_user_id (user_id),
                    INDEX idx_request_number (user_id, request_number),
                    INDEX idx_demandes_photo_id (photo_id),
                    INDEX idx_prioritaire (prioritaire),
                    INDEX idx_date_creation (date_creation),
                    INDEX idx_admin_en_charge (admin_en_charge)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            ''',

            'archives': '''
                CREATE TABLE IF NOT EXISTS archives (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    original_id BIGINT,
                    user_id BIGINT NOT NULL,
                    prenom VARCHAR(50),
                    nom VARCHAR(50),
                    age INT,
                    localisation VARCHAR(100),
                    photo_id VARCHAR(255),
                    instagram VARCHAR(50),
                    snapchat VARCHAR(50),
                    details TEXT,
                    prioritaire BOOLEAN DEFAULT FALSE,
                    montant DECIMAL(10,2) DEFAULT 0,
                    statut VARCHAR(20),
                    request_number INT,
                    admin_en_charge BIGINT DEFAULT NULL,
                    admin_alias_archive VARCHAR(50),
                    date_creation TIMESTAMP,
                    date_archivage TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_user_id (user_id),
                    INDEX idx_archives_photo_id (photo_id),
                    INDEX idx_date_archivage (date_archivage),
                    INDEX idx_original_id (original_id),
                    INDEX idx_admin_archive (admin_en_charge)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            ''',

            'demandes_suivi': '''
                CREATE TABLE IF NOT EXISTS demandes_suivi (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    demande_id BIGINT NOT NULL,
                    admin_id BIGINT NOT NULL,
                    date_suivi TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    notes_admin TEXT DEFAULT NULL,
                    statut_suivi VARCHAR(50) DEFAULT 'active',
                    derniere_action TIMESTAMP NULL DEFAULT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY unique_suivi (demande_id, admin_id),
                    KEY idx_admin_id (admin_id),
                    KEY idx_demande_id (demande_id),
                    KEY idx_date_suivi (date_suivi),
                    KEY idx_statut_suivi (statut_suivi)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            '''
        }

        try:
            with self.get_cursor() as cursor:
                for table_name, create_sql in tables.items():
                    cursor.execute(create_sql)
                    logger.info("Table %s créée/vérifiée", table_name)
                self._initialize_default_config(cursor)
        except Exception as e:
            logger.error("Erreur création tables: %s", e)
            raise

    def get_database_size(self):
        """Retourne l'empreinte disque de la base MySQL."""
        try:
            with self.get_cursor() as cursor:
                cursor.execute("""
                    SELECT ROUND(SUM(data_length + index_length) / (1024 * 1024), 2) as size_mb
                    FROM information_schema.TABLES
                    WHERE table_schema = DATABASE()
                """)
                total_size = cursor.fetchone()

                cursor.execute("""
                    SELECT
                        table_name,
                        ROUND((data_length + index_length) / (1024 * 1024), 2) as size_mb,
                        table_rows as row_count
                    FROM information_schema.TABLES
                    WHERE table_schema = DATABASE()
                    AND table_type = 'BASE TABLE'
                    ORDER BY (data_length + index_length) DESC
                """)
                tables_info = cursor.fetchall()

                return {
                    'total_size_mb': total_size['size_mb'] if total_size else 0,
                    'tables': tables_info
                }
        except Exception as e:
            logger.error("Erreur calcul taille DB: %s", e)
            return {'total_size_mb': 0, 'tables': []}

    def _initialize_default_config(self, cursor):
        """Insère les variables par défaut si absentes."""
        default_configs = [
            ('bot_active', 'true'),
            ('max_requests_per_user', '3'),
            ('admin_notifications', 'true')
        ]
        for key_name, value in default_configs:
            cursor.execute("""
                INSERT INTO config (key_name, value)
                VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE key_name = key_name
            """, (key_name, value))

    def get_config_value(self, key_name, default_value=None, use_cache=True):
        cache_key = f"config_{key_name}"
        if use_cache:
            cached_result = self.get_cached_result(cache_key)
            if cached_result is not None:
                return cached_result

        try:
            with self.get_cursor() as cursor:
                cursor.execute("SELECT value FROM config WHERE key_name = %s", (key_name,))
                result = cursor.fetchone()
                value = result['value'] if result else default_value
                if use_cache and value is not None:
                    self.cache_result(cache_key, value)
                return value
        except Exception as e:
            logger.error("Erreur récupération config %s: %s", key_name, e)
            return default_value

    def set_config_value(self, key_name, value):
        try:
            with self.get_cursor() as cursor:
                cursor.execute("""
                    INSERT INTO config (key_name, value)
                    VALUES (%s, %s)
                    ON DUPLICATE KEY UPDATE value = %s, updated_at = CURRENT_TIMESTAMP
                """, (key_name, value, value))

                cache_key = f"config_{key_name}"
                if cache_key in self._cache:
                    del self._cache[cache_key]
                return True
        except Exception as e:
            logger.error("Erreur mise à jour config %s: %s", key_name, e)
            return False

    def is_bot_active(self):
        return self.get_config_value('bot_active', 'true') == 'true'

    def set_bot_active(self, active):
        return self.set_config_value('bot_active', 'true' if active else 'false')

    def get_owner_id(self):
        owner_id_str = self.get_config_value('owner_id')
        return int(owner_id_str) if owner_id_str else None

    def set_owner_id(self, owner_id):
        return self.set_config_value('owner_id', str(owner_id))

    def get_owner_alias(self):
        return self.get_config_value('owner_alias', 'Propriétaire')

    def set_owner_alias(self, alias):
        return self.set_config_value('owner_alias', alias)

    def get_owner_info(self):
        return {
            'owner_id': self.get_owner_id(),
            'owner_alias': self.get_owner_alias()
        }

    def get_admin_alias(self, user_id):
        cache_key = f"admin_alias_{user_id}"
        cached_result = self.get_cached_result(cache_key)
        if cached_result is not None:
            return cached_result

        try:
            with self.get_cursor() as cursor:
                cursor.execute("SELECT alias FROM admins WHERE user_id = %s", (user_id,))
                result = cursor.fetchone()
                alias = result['alias'] if result else "Admin"
                self.cache_result(cache_key, alias)
                return alias
        except Exception as e:
            logger.error("Erreur récupération alias admin %s: %s", user_id, e)
            return "Admin"

    def set_admin_alias(self, user_id, alias):
        try:
            with self.get_cursor() as cursor:
                cursor.execute("UPDATE admins SET alias = %s WHERE user_id = %s", (alias, user_id))
                cache_key = f"admin_alias_{user_id}"
                if cache_key in self._cache:
                    del self._cache[cache_key]
                return cursor.rowcount > 0
        except Exception as e:
            logger.error("Erreur mise à jour alias admin %s: %s", user_id, e)
            return False

    def get_all_admin_aliases(self):
        cache_key = "all_admin_aliases"
        cached_result = self.get_cached_result(cache_key)
        if cached_result is not None:
            return cached_result

        try:
            with self.get_cursor() as cursor:
                cursor.execute("SELECT user_id, alias FROM admins ORDER BY alias")
                result = {row['user_id']: row['alias'] for row in cursor.fetchall()}
                self.cache_result(cache_key, result)
                return result
        except Exception as e:
            logger.error("Erreur récupération tous alias admins: %s", e)
            return {}

    def get_user_alias_unified(self, user_id):
        owner_id = self.get_owner_id()
        if owner_id and user_id == owner_id:
            return self.get_owner_alias()
        return self.get_admin_alias(user_id)

    def set_user_alias_unified(self, user_id, alias):
        owner_id = self.get_owner_id()
        if owner_id and user_id == owner_id:
            return self.set_owner_alias(alias)
        return self.set_admin_alias(user_id, alias)

    def get_all_config(self, use_cache=True):
        cache_key = "all_config"
        if use_cache:
            cached_result = self.get_cached_result(cache_key)
            if cached_result is not None:
                return cached_result

        try:
            with self.get_cursor() as cursor:
                cursor.execute("SELECT key_name, value FROM config ORDER BY key_name")
                result = {row['key_name']: row['value'] for row in cursor.fetchall()}
                if use_cache:
                    self.cache_result(cache_key, result)
                return result
        except Exception as e:
            logger.error("Erreur récupération toutes configs: %s", e)
            return {}

    def delete_config_value(self, key_name):
        try:
            with self.get_cursor() as cursor:
                cursor.execute("DELETE FROM config WHERE key_name = %s", (key_name,))
                cache_key = f"config_{key_name}"
                if cache_key in self._cache:
                    del self._cache[cache_key]
                if "all_config" in self._cache:
                    del self._cache["all_config"]
                return cursor.rowcount > 0
        except Exception as e:
            logger.error("Erreur suppression config %s: %s", key_name, e)
            return False


def get_db_manager():
    return DatabaseManager(Config())