"""Configuration centralisée avec synchronisation base de données et cache."""

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
        self._setup_paths()

    def _validate_required_env_vars(self):
        """Valide la présence des variables d'environnement critiques."""
        required_vars = ["BOT_TOKEN", "OWNER_ID", "DB_HOST", "DB_USER", "DB_PASSWORD", "DB_NAME"]
        missing_vars = [var for var in required_vars if not os.getenv(var)]

        if missing_vars:
            raise ValueError(f"Variables d'environnement manquantes : {missing_vars}")

        logger.info("Toutes les variables d'environnement requises sont présentes")

    def _setup_basic_config(self):
        """Configuration des identifiants principaux."""
        self.BOT_TOKEN = os.getenv("BOT_TOKEN")

        owner_id_str = os.getenv("OWNER_ID", "0")
        if not owner_id_str.isdigit():
            raise ValueError("OWNER_ID doit être un entier valide")
        self.OWNER_ID = int(owner_id_str)
        self.OWNER_ALIAS = os.getenv("OWNER_ALIAS", "Propriétaire")

    def _setup_cache_system(self):
        """Initialise les structures de cache en mémoire."""
        self.admin_ids = set()
        self._admin_cache_loaded = False
        self._db_manager = None
        self._admin_cache_lock = threading.Lock()

    def _setup_database_config(self):
        """Configuration de connexion pour DatabaseManager."""
        port_str = os.getenv("DB_PORT", "3306")
        port = int(port_str) if port_str.isdigit() else 3306

        self.DB_CONFIG = {
            "host": os.getenv("DB_HOST", "localhost"),
            "port": port,
            "user": os.getenv("DB_USER"),
            "password": os.getenv("DB_PASSWORD"),
            "database": os.getenv("DB_NAME"),
            "connect_timeout": 10,
            "charset": "utf8mb4",
        }

    def _setup_paths(self):
        """Initialise les dossiers système."""
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
            logger.error("Erreur chargement owner alias : %s", e)

    def load_admins(self, db_manager=None):
        """Charge la liste des administrateurs depuis MySQL."""
        mgr = db_manager or self._db_manager
        if not mgr:
            return

        with self._admin_cache_lock:
            try:
                with mgr.get_cursor() as cursor:
                    cursor.execute("SELECT user_id FROM admins")
                    rows = cursor.fetchall()

                    new_admins = set()
                    for row in rows:
                        try:
                            new_admins.add(int(row["user_id"]))
                        except (ValueError, TypeError):
                            continue

                    self.admin_ids = new_admins
                    self._admin_cache_loaded = True
                    logger.info("Cache admin rechargé : %d administrateurs", len(self.admin_ids))

            except Exception as e:
                logger.error("Erreur critique load_admins : %s", e)
                self.admin_ids = set()
                self._admin_cache_loaded = False

    def reload_admins(self):
        """Recharge les administrateurs à chaud."""
        self.load_admins(self._db_manager)

    def is_owner(self, user_id):
        """Vérifie si l'utilisateur est le propriétaire."""
        try:
            return int(user_id) == self.OWNER_ID
        except (ValueError, TypeError):
            return False

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

    def _verify_admin_hybrid(self, user_id_int: int):
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
            try:
                self.admin_ids.add(int(user_id))
            except (ValueError, TypeError):
                pass

    def remove_admin(self, user_id):
        """Retire un admin du cache local."""
        with self._admin_cache_lock:
            try:
                self.admin_ids.discard(int(user_id))
            except (ValueError, TypeError):
                pass

    # ========== CONTRÔLE DES DEMANDES (Clé unique "bot_active") ==========

    def enable_demandes(self):
        """Active l'acceptation des demandes en base."""
        if self._db_manager:
            self._db_manager.set_config_value("bot_active", "true")
            self._db_manager.set_config_value("demandes_enabled", "true")
            self._db_manager.set_config_value("maintenance_mode", "false")
        logger.info("Service demandes activé")

    def disable_demandes(self):
        """Désactive l'acceptation des demandes en base."""
        if self._db_manager:
            self._db_manager.set_config_value("bot_active", "false")
            self._db_manager.set_config_value("demandes_enabled", "false")
        logger.info("Service demandes désactivé")

    def are_demandes_enabled(self) -> bool:
        """Vérifie si les demandes sont acceptées (lecture directe avec fallback)."""
        if self._db_manager:
            # Vérification du mode maintenance d'abord
            maint = str(self._db_manager.get_config_value("maintenance_mode", "false")).lower()
            if maint in ("true", "1", "yes"):
                return False

            val = str(self._db_manager.get_config_value("bot_active", "true")).lower()
            return val in ("true", "1", "yes")
        return True

    # ========== GESTION DES LIMITES & QUOTAS ==========

    def get_max_total_demandes(self) -> int:
        """Retourne le plafond global (0 = illimité)."""
        if self._db_manager:
            val = self._db_manager.get_config_value("max_total_demandes", "0")
            try:
                return int(val)
            except (ValueError, TypeError):
                return 0
        return 0

    def set_max_total_demandes(self, limit: int) -> bool:
        """Fixe le plafond global en base."""
        if self._db_manager:
            val = max(0, int(limit))
            return self._db_manager.set_config_value("max_total_demandes", str(val))
        return False

    def get_max_demandes_per_user(self) -> int:
        """Retourne le quota par utilisateur (0 = illimité, défaut 3)."""
        if self._db_manager:
            val = self._db_manager.get_config_value("max_demandes_per_user", "3")
            try:
                return int(val)
            except (ValueError, TypeError):
                return 3
        return 3

    def set_max_demandes_per_user(self, limit: int) -> bool:
        """Fixe le quota individuel en base."""
        if self._db_manager:
            val = max(0, int(limit))
            return self._db_manager.set_config_value("max_demandes_per_user", str(val))
        return False