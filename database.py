from mysql.connector import pooling
import logging
from contextlib import contextmanager
import time
import threading
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
        if not hasattr(self, '_initialized') or not self._initialized:
            self.config = config
            self._pool = None
            self._cache = {}
            self._cache_timeout = config.CACHE_TIMEOUT
            self._initialized = True

    def get_connection_pool(self):
        """Crée un pool de connexions optimisé"""
        if not self._pool:
            try:
                self._pool = pooling.MySQLConnectionPool(
                    pool_name="bot_pool",
                    pool_size=3,                # Limité pour plan gratuit
                    pool_reset_session=True,    # Sécurité sessions
                    use_pure=True,              # Compatibilité
                    **self.config.DB_CONFIG
                )
            except Exception as e:
                logger.error(f"Erreur création pool DB: {e}")
                return None
        return self._pool

    def get_connection_with_retry(self, max_retries=3):
        """Connexion avec retry automatique et backoff exponentiel"""
        import time

        for attempt in range(max_retries):
            try:
                pool = self.get_connection_pool()
                if pool:
                    return pool.get_connection()
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(f"Échec connexion après {max_retries} tentatives : {e}")
                    raise
                wait_time = 2 ** attempt
                logger.warning(f"Tentative {attempt + 1} échouée, retry dans {wait_time}s")
                time.sleep(wait_time)

    @contextmanager
    def get_cursor(self):
        """Context manager pour les connexions DB"""
        connection = None
        cursor = None
        try:
            pool = self.get_connection_pool()
            if pool:
                connection = pool.get_connection()
                cursor = connection.cursor(dictionary=True, buffered=True)
                yield cursor
                connection.commit()
        except Exception as e:
            if connection:
                connection.rollback()
            logger.error(f"Erreur DB: {e}")
            raise
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def cache_result(self, key, result):
        """Cache simple avec expiration"""
        self._cache[key] = {
            'data': result,
            'timestamp': time.time()
        }

    def get_cached_result(self, key):
        """Récupère un résultat du cache"""
        if len(self._cache) > 100:  # Seuil de nettoyage
            self.cleanup_expired_cache()

        if key in self._cache:
            cache_entry = self._cache[key]
            if time.time() - cache_entry['timestamp'] < self._cache_timeout:
                return cache_entry['data']
            else:
                del self._cache[key]
        return None

    def clear_cache(self):
        """Vide le cache"""
        self._cache.clear()

    def cleanup_expired_cache(self):
        """Nettoie automatiquement les entrées expirées du cache"""
        current_time = time.time()
        expired_keys = [
            key for key, entry in self._cache.items()
            if current_time - entry['timestamp'] >= self._cache_timeout
        ]

        # Catégorisation pour logs
        config_keys = [k for k in expired_keys if k.startswith('config_')]
        admin_keys = [k for k in expired_keys if k.startswith('admin_')]
        other_keys = [k for k in expired_keys if not (k.startswith('config_') or k.startswith('admin_'))]

        for key in expired_keys:
            del self._cache[key]

        if expired_keys:
            logger.debug(f"Cache nettoyé : {len(config_keys)} configs, {len(admin_keys)} admins, {len(other_keys)} autres")

    def create_tables(self):
        """Crée les tables optimisées"""
        tables = {
            'config': '''
                CREATE TABLE IF NOT EXISTS config (
                    id INT AUTO_INCREMENT PRIMARY KEY,
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
                    id INT AUTO_INCREMENT PRIMARY KEY,
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
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    original_id INT,
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
                    id bigint UNSIGNED AUTO_INCREMENT COMMENT 'Identifiant unique du suivi',
                    demande_id bigint UNSIGNED NOT NULL COMMENT 'ID de la demande suivie',
                    admin_id bigint NOT NULL COMMENT 'ID de l admin qui suit la demande',
                    date_suivi timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Date de début du suivi',
                    notes_admin TEXT DEFAULT NULL COMMENT 'Notes privées de l admin sur cette demande',
                    statut_suivi VARCHAR(50) DEFAULT 'active' COMMENT 'Statut du suivi (active, abandonné, terminé)',
                    derniere_action timestamp NULL DEFAULT NULL COMMENT 'Dernière action sur cette demande',
                    created_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Date de création',
                    updated_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Date de mise à jour',

                    PRIMARY KEY (id),
                    UNIQUE KEY unique_suivi (demande_id, admin_id) COMMENT 'Un admin ne peut suivre qu une fois la même demande',
                    KEY idx_admin_id (admin_id) COMMENT 'Index pour recherche par admin',
                    KEY idx_demande_id (demande_id) COMMENT 'Index pour recherche par demande',
                    KEY idx_date_suivi (date_suivi) COMMENT 'Index pour tri chronologique',
                    KEY idx_statut_suivi (statut_suivi) COMMENT 'Index pour filtrage par statut'
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_520_ci
                COMMENT='Table de suivi des demandes par les admins selon conception_de_base_de_données'
            '''
        }

        try:
            with self.get_cursor() as cursor:
                for table_name, create_sql in tables.items():
                    cursor.execute(create_sql)
                    logger.info(f"Table {table_name} créée/vérifiée")

                # Initialiser le statut si nécessaire
                self._initialize_default_config(cursor)

        except Exception as e:
            logger.error(f"Erreur création tables: {e}")

    def get_database_size(self):
        """Retourne la taille de la base de données"""
        try:
            with self.get_cursor() as cursor:
                # Taille totale de la base
                cursor.execute("""
                    SELECT
                        ROUND(SUM(data_length + index_length) / (1024 * 1024), 2) as size_mb
                    FROM information_schema.TABLES
                    WHERE table_schema = DATABASE()
                """)

                total_size = cursor.fetchone()

                # Taille par table principale
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
            logger.error(f"Erreur calcul taille DB: {e}")
            return {'total_size_mb': 0, 'tables': []}


    def _initialize_default_config(self, cursor):
        """Initialise la configuration par défaut"""
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

        logger.info("Configuration par défaut initialisée")

    def get_config_value(self, key_name, default_value=None, use_cache=True):
        """Récupère une valeur de configuration avec cache intégré"""
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
            logger.error(f"Erreur récupération config {key_name}: {e}")
            return default_value

    def set_config_value(self, key_name, value):
        """Définit une valeur de configuration avec invalidation cache"""
        try:
            with self.get_cursor() as cursor:
                cursor.execute("""
                    INSERT INTO config (key_name, value)
                    VALUES (%s, %s)
                    ON DUPLICATE KEY UPDATE value = %s, updated_at = CURRENT_TIMESTAMP
                """, (key_name, value, value))

                # Invalider le cache
                cache_key = f"config_{key_name}"
                if cache_key in self._cache:
                    del self._cache[cache_key]

                logger.info(f"Configuration mise à jour: {key_name} = {value}")
                return True
        except Exception as e:
            logger.error(f"Erreur mise à jour config {key_name}: {e}")
            return False

    def is_bot_active(self):
        """Vérifie si le bot accepte les demandes avec cache"""
        return self.get_config_value('bot_active', 'true') == 'true'

    def set_bot_active(self, active):
        """Active/désactive le bot avec invalidation cache intelligente"""
        value = 'true' if active else 'false'
        return self.set_config_value('bot_active', value)

    # ============ MÉTHODES OWNER selon l'architecture clarifiée ============

    def get_owner_id(self):
        """Récupère l'ID du propriétaire depuis config"""
        owner_id_str = self.get_config_value('owner_id')
        return int(owner_id_str) if owner_id_str else None

    def set_owner_id(self, owner_id):
        """Définit l'ID du propriétaire dans config"""
        return self.set_config_value('owner_id', str(owner_id))

    def get_owner_alias(self):
        """Récupère l'alias du propriétaire depuis config"""
        return self.get_config_value('owner_alias', 'Propriétaire')

    def set_owner_alias(self, alias):
        """Définit l'alias du propriétaire dans config"""
        return self.set_config_value('owner_alias', alias)

    def get_owner_info(self):
        """Récupère toutes les infos owner"""
        return {
            'owner_id': self.get_owner_id(),
            'owner_alias': self.get_owner_alias()
        }

    # ============ MÉTHODES ADMIN selon l'architecture clarifiée ============

    def get_admin_alias(self, user_id):
        """Récupère l'alias d'un admin depuis table admins"""
        cache_key = f"admin_alias_{user_id}"

        # Vérifier cache d'abord
        cached_result = self.get_cached_result(cache_key)
        if cached_result is not None:
            return cached_result

        try:
            with self.get_cursor() as cursor:
                cursor.execute("SELECT alias FROM admins WHERE user_id = %s", (user_id,))
                result = cursor.fetchone()
                alias = result['alias'] if result else "Admin"

                # Mettre en cache
                self.cache_result(cache_key, alias)
                return alias

        except Exception as e:
            logger.error(f"Erreur récupération alias admin {user_id}: {e}")
            return "Admin"

    def set_admin_alias(self, user_id, alias):
        """Modifie l'alias d'un admin dans table admins"""
        try:
            with self.get_cursor() as cursor:
                cursor.execute("UPDATE admins SET alias = %s WHERE user_id = %s", (alias, user_id))

                # Invalider cache admin
                cache_key = f"admin_alias_{user_id}"
                if cache_key in self._cache:
                    del self._cache[cache_key]

                if cursor.rowcount > 0:
                    logger.info(f"Alias admin {user_id} mis à jour: {alias}")
                    return True
                else:
                    logger.warning(f"Admin {user_id} non trouvé pour mise à jour alias")
                    return False

        except Exception as e:
            logger.error(f"Erreur mise à jour alias admin {user_id}: {e}")
            return False

    def get_all_admin_aliases(self):
        """Récupère tous les alias d'admins avec cache"""
        cache_key = "all_admin_aliases"

        cached_result = self.get_cached_result(cache_key)
        if cached_result is not None:
            return cached_result

        try:
            with self.get_cursor() as cursor:
                cursor.execute("SELECT user_id, alias FROM admins ORDER BY alias")
                result = {row['user_id']: row['alias'] for row in cursor.fetchall()}

                # Mettre en cache
                self.cache_result(cache_key, result)
                return result

        except Exception as e:
            logger.error(f"Erreur récupération tous alias admins: {e}")
            return {}

    # ============ MÉTHODES HYBRIDES OWNER/ADMIN ============

    def get_user_alias_unified(self, user_id):
        """Récupère l'alias selon le type d'utilisateur (owner ou admin)"""
        # Vérifier si c'est le propriétaire
        owner_id = self.get_owner_id()
        if owner_id and user_id == owner_id:
            return self.get_owner_alias()
        else:
            # C'est un admin
            return self.get_admin_alias(user_id)

    def set_user_alias_unified(self, user_id, alias):
        """Sauvegarde l'alias selon le type d'utilisateur"""
        # Vérifier si c'est le propriétaire
        owner_id = self.get_owner_id()
        if owner_id and user_id == owner_id:
            return self.set_owner_alias(alias)
        else:
            # C'est un admin
            return self.set_admin_alias(user_id, alias)

    # ============ MÉTHODES UTILITAIRES CONFIG AVANCÉES ============

    def get_all_config(self, use_cache=True):
        """Récupère toutes les configurations avec cache"""
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
            logger.error(f"Erreur récupération toutes configs: {e}")
            return {}

    def delete_config_value(self, key_name):
        """Supprime une configuration avec invalidation cache"""
        try:
            with self.get_cursor() as cursor:
                cursor.execute("DELETE FROM config WHERE key_name = %s", (key_name,))

                # Invalider les caches liés
                cache_key = f"config_{key_name}"
                if cache_key in self._cache:
                    del self._cache[cache_key]
                if "all_config" in self._cache:
                    del self._cache["all_config"]

                if cursor.rowcount > 0:
                    logger.info(f"Configuration supprimée: {key_name}")
                    return True
                else:
                    logger.warning(f"Configuration non trouvée: {key_name}")
                    return False
        except Exception as e:
            logger.error(f"Erreur suppression config {key_name}: {e}")
            return False

def get_db_manager():
    return DatabaseManager(Config())