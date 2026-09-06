import logging
import os
import threading
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


class Config:
    """Configuration centralisée avec synchronisation base de données et cache."""

    def __init__(self):
        self._validate_required_env_vars()
        self._setup_basic_config()
        self._setup_database_config()
        self._setup_cache_system()
        self._setup_limits_and_paths()

    def _validate_required_env_vars(self):
        """Valide la présence des variables d'environnement critiques."""
        required_vars = ['BOT_TOKEN', 'OWNER_ID', 'DB_HOST', 'DB_USER', 'DB_PASSWORD', 'DB_NAME']
        missing_vars = [var for var in required_vars if not os.getenv(var)]

        if missing_vars:
            raise ValueError(f"Variables d'environnement manquantes : {missing_vars}")

        logger.info("Toutes les variables d'environnement requises sont présentes")

    def _setup_basic_config(self):
        """Configuration des identifiants principaux."""
        self.BOT_TOKEN = os.getenv('BOT_TOKEN')

        owner_id_str = os.getenv('OWNER_ID', '0')
        if not owner_id_str.isdigit():
            raise ValueError("OWNER_ID doit être un entier valide")
        self.OWNER_ID = int(owner_id_str)
        self.OWNER_ALIAS = os.getenv('OWNER_ALIAS', 'Propriétaire')

    def _setup_cache_system(self):
        """Initialise les structures de cache en mémoire."""
        self.admin_ids = set()
        self._admin_cache_loaded = False
        self._db_manager = None
        self._admin_cache_lock = threading.Lock()

    def _setup_database_config(self):
        """Configuration de la connexion MySQL."""
        port_str = os.getenv('DB_PORT', '3306')
        port = int(port_str) if port_str.isdigit() else 3306

        self.DB_CONFIG = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': port,
            'user': os.getenv('DB_USER'),
            'password': os.getenv('DB_PASSWORD'),
            'database': os.getenv('DB_NAME'),
            'autocommit': True,
            'connect_timeout': 5,
            'charset': 'utf8mb4'
        }

    def _setup_limits_and_paths(self):
        """Configuration des chemins et limites opérationnelles."""
        self.MAX_STORAGE_MB = 400
        self.CACHE_TIMEOUT = 300
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.LOG_DIR = os.path.join(base_dir, "logs")
        os.makedirs(self.LOG_DIR, exist_ok=True)

    def set_db_manager(self, db_manager):
        """Associe le gestionnaire de base de données et précharge le cache."""
        self._db_manager = db_manager
        self.load_admins(db_manager)
        self._load_owner_alias_if_needed()

    def _load_owner_alias_if_needed(self):
        """Synchronise l'alias du propriétaire avec la table config."""
        if not self._db_manager:
            return
        try:
            db_alias = self._db_manager.get_owner_alias()
            if db_alias:
                self.OWNER_ALIAS = db_alias
            else:
                self._db_manager.set_owner_alias(self.OWNER_ALIAS)
        except Exception as e:
            logger.error("Erreur chargement owner alias: %s", e)

    def load_admins(self, db_manager):
        """Charge la liste des administrateurs depuis MySQL."""
        with self._admin_cache_lock:
            try:
                with db_manager.get_cursor() as cursor:
                    cursor.execute("SELECT user_id FROM admins")
                    rows = cursor.fetchall()

                    new_admins = set()
                    for row in rows:
                        try:
                            new_admins.add(int(row['user_id']))
                        except (ValueError, TypeError):
                            continue

                    self.admin_ids = new_admins
                    self._admin_cache_loaded = True
                    logger.info("Cache admin rechargé : %s administrateurs", len(self.admin_ids))

            except Exception as e:
                logger.error("Erreur critique load_admins : %s", e)
                self.admin_ids = set()
                self._admin_cache_loaded = False

    def is_owner(self, user_id):
        """Vérifie si l'utilisateur est le propriétaire."""
        return int(user_id) == self.OWNER_ID

    def is_admin(self, user_id, secure_mode=False):
        """Vérifie si l'utilisateur possède les privilèges d'administration."""
        try:
            user_id_int = int(user_id)
        except (ValueError, TypeError):
            return False

        if self.is_owner(user_id_int):
            return True

        if not self._admin_cache_loaded and self._db_manager:
            self.load_admins(self._db_manager)

        if secure_mode or len(self.admin_ids) == 0:
            return self._verify_admin_hybrid(user_id_int)

        return user_id_int in self.admin_ids

    def _verify_admin_hybrid(self, user_id_int):
        """Contrôle en cache puis fallback direct en base."""
        if user_id_int in self.admin_ids:
            return True

        if self._db_manager:
            try:
                with self._db_manager.get_cursor() as cursor:
                    cursor.execute("SELECT user_id FROM admins WHERE user_id = %s", (user_id_int,))
                    if cursor.fetchone() is not None:
                        self.load_admins(self._db_manager)
                        return True
            except Exception as e:
                logger.error("Erreur vérification admin DB : %s", e)

        return False

    def get_all_admins(self):
        """Retourne l'ensemble des IDs autorisés (Owner + Admins)."""
        all_admins = {self.OWNER_ID}
        all_admins.update(self.admin_ids)
        return all_admins

    def add_admin(self, user_id):
        """Ajoute un admin au cache local."""
        with self._admin_cache_lock:
            self.admin_ids.add(int(user_id))

    def remove_admin(self, user_id):
        """Retire un admin du cache local."""
        with self._admin_cache_lock:
            self.admin_ids.discard(int(user_id))

    def reload_admins(self, db_manager):
        """Recharge les administrateurs à chaud."""
        self.load_admins(db_manager)

    def enable_demandes(self):
        """Active l'acceptation des demandes (synchronisé en base)."""
        if self._db_manager:
            self._db_manager.set_bot_active(True)
        logger.info("Demandes activées")

    def disable_demandes(self):
        """Désactive l'acceptation des demandes (synchronisé en base)."""
        if self._db_manager:
            self._db_manager.set_bot_active(False)
        logger.info("Demandes désactivées")

    def are_demandes_enabled(self):
        """Vérifie si le bot accepte les demandes (lecture base avec cache)."""
        if self._db_manager:
            return self._db_manager.is_bot_active()
        return True

    def get_max_total_demandes(self) -> int:
        """Retourne le quota global via DatabaseManager (fallback 0)."""
        if self._db_manager:
            return self._db_manager.get_max_total_demandes()
        return 0

    def set_max_total_demandes(self, limit: int) -> bool:
        """Modifie le quota global via DatabaseManager."""
        if self._db_manager:
            return self._db_manager.set_max_total_demandes(limit)
        return False

    def get_max_demandes_per_user(self) -> int:
        """Retourne le quota individuel via DatabaseManager (fallback 3)."""
        if self._db_manager:
            return self._db_manager.get_max_demandes_per_user()
        return 3

    def set_max_demandes_per_user(self, limit: int) -> bool:
        """Modifie le quota individuel via DatabaseManager."""
        if self._db_manager:
            return self._db_manager.set_max_demandes_per_user(limit)
        return False