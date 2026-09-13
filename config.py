"""Configuration centralisée avec synchronisation base de données et cache multi-rôles (Multi-Owner supporté)."""

import logging
import os
import threading
from dotenv import load_dotenv

# Chargement robuste du .env depuis le même dossier que config.py
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_path):
    load_dotenv(dotenv_path=_env_path, override=True)
else:
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
        """Configuration des identifiants principaux et jetons webhook."""
        self.BOT_TOKEN = os.getenv("BOT_TOKEN")

        owner_id_str = os.getenv("OWNER_ID", "0")
        if not owner_id_str.isdigit():
            raise ValueError("OWNER_ID doit être un entier valide")
        self.OWNER_ID = int(owner_id_str)
        self.OWNER_ALIAS = os.getenv("OWNER_ALIAS", "Propriétaire")
        self.CRON_SECRET_TOKEN = os.getenv("CRON_SECRET_TOKEN")
        self.TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET")

    def _setup_cache_system(self):
        """Initialise les structures de cache en mémoire pour owners, admins et staff."""
        self.owner_ids = {self.OWNER_ID}  # Contient au minimum le propriétaire racine (.env)
        self.admin_ids = set()
        self.staff_ids = set()
        self._cache_loaded = False
        self._db_manager = None
        self._cache_lock = threading.Lock()

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
        """Associe le gestionnaire de base de données et précharge les caches."""
        self._db_manager = db_manager
        self.load_roles(db_manager)
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

    def load_roles(self, db_manager=None):
        """Charge simultanément les owners, admins et le staff depuis MySQL."""
        mgr = db_manager or self._db_manager
        if not mgr:
            return

        with self._cache_lock:
            try:
                with mgr.get_cursor() as cursor:
                    # 1. Chargement des admins et détection des co-gérants (owners)
                    cursor.execute("SELECT user_id, is_owner FROM admins")
                    admin_rows = cursor.fetchall()
                    
                    new_admins = set()
                    new_owners = {self.OWNER_ID}  # On inclut toujours le propriétaire racine
                    
                    for row in admin_rows:
                        try:
                            uid = int(row["user_id"])
                            new_admins.add(uid)
                            if row.get("is_owner"):
                                new_owners.add(uid)
                        except (ValueError, TypeError):
                            continue

                    # 2. Chargement du staff
                    cursor.execute("SELECT user_id FROM staff")
                    staff_rows = cursor.fetchall()
                    new_staff = set()
                    for row in staff_rows:
                        try:
                            new_staff.add(int(row["user_id"]))
                        except (ValueError, TypeError):
                            continue

                    self.admin_ids = new_admins
                    self.owner_ids = new_owners
                    self.staff_ids = new_staff
                    self._cache_loaded = True
                    logger.info(
                        "Cache rôles chargé : %d owners, %d admins (managers) et %d staff (opérateurs)",
                        len(self.owner_ids),
                        len(self.admin_ids),
                        len(self.staff_ids),
                    )

            except Exception as e:
                logger.error("Erreur critique load_roles : %s", e)
                self.admin_ids = set()
                self.owner_ids = {self.OWNER_ID}
                self.staff_ids = set()
                self._cache_loaded = False

    # Alias rétrocompatible
    load_admins = load_roles

    def reload_roles(self):
        """Recharge les rôles à chaud."""
        self.load_roles(self._db_manager)

    reload_admins = reload_roles

    # ==================== VÉRIFICATIONS DES RÔLES ====================

    def is_owner(self, user_id) -> bool:
        """Vérifie si l'utilisateur est le Super-Admin suprême (Owner racine ou co-gérant)."""
        try:
            uid = int(user_id)
            if uid == self.OWNER_ID:
                return True
            return uid in self.owner_ids
        except (ValueError, TypeError):
            return False

    def is_admin(self, user_id, secure_mode=False) -> bool:
        """Vérifie si l'utilisateur est administrateur (Manager ou Owner)."""
        try:
            uid = int(user_id)
        except (ValueError, TypeError):
            return False

        if self.is_owner(uid):
            return True

        if not self._cache_loaded and self._db_manager:
            self.load_roles(self._db_manager)

        if secure_mode or len(self.admin_ids) == 0:
            if uid in self.admin_ids:
                return True
            if self._db_manager:
                try:
                    with self._db_manager.get_cursor() as cursor:
                        cursor.execute("SELECT user_id FROM admins WHERE user_id = %s", (uid,))
                        if cursor.fetchone() is not None:
                            self.load_roles(self._db_manager)
                            return True
                except Exception as e:
                    logger.error("Erreur vérification admin DB : %s", e)
            return False

        return uid in self.admin_ids

    def is_staff(self, user_id, secure_mode=False) -> bool:
        """Vérifie si l'utilisateur peut traiter des demandes (Staff, Admin ou Owner)."""
        try:
            uid = int(user_id)
        except (ValueError, TypeError):
            return False

        # Les admins et les owners ont automatiquement accès aux prérogatives du staff
        if self.is_admin(uid, secure_mode=secure_mode):
            return True

        if not self._cache_loaded and self._db_manager:
            self.load_roles(self._db_manager)

        if secure_mode or len(self.staff_ids) == 0:
            if uid in self.staff_ids:
                return True
            if self._db_manager:
                try:
                    with self._db_manager.get_cursor() as cursor:
                        cursor.execute("SELECT user_id FROM staff WHERE user_id = %s", (uid,))
                        if cursor.fetchone() is not None:
                            self.load_roles(self._db_manager)
                            return True
                except Exception as e:
                    logger.error("Erreur vérification staff DB : %s", e)
            return False

        return uid in self.staff_ids

    # ==================== LISTES D'IDENTIFIANTS ====================

    def get_all_admins(self):
        """Retourne l'ensemble des IDs administrateurs (Owners + Managers)."""
        all_admins = set(self.owner_ids)
        all_admins.update(self.admin_ids)
        return all_admins

    def get_all_staff(self):
        """Retourne l'ensemble des membres habilités à traiter les demandes."""
        all_staff = set(self.owner_ids)
        all_staff.update(self.admin_ids)
        all_staff.update(self.staff_ids)
        return all_staff

    # ==================== MUTATEURS DE CACHE ====================

    def add_admin(self, user_id):
        """Ajoute un administrateur au cache local."""
        with self._cache_lock:
            try:
                self.admin_ids.add(int(user_id))
            except (ValueError, TypeError):
                pass

    def remove_admin(self, user_id):
        """Retire un administrateur du cache local."""
        with self._cache_lock:
            try:
                self.admin_ids.discard(int(user_id))
            except (ValueError, TypeError):
                pass

    def add_staff(self, user_id):
        """Ajoute un employé au cache local."""
        with self._cache_lock:
            try:
                self.staff_ids.add(int(user_id))
            except (ValueError, TypeError):
                pass

    def remove_staff(self, user_id):
        """Retire un employé du cache local."""
        with self._cache_lock:
            try:
                self.staff_ids.discard(int(user_id))
            except (ValueError, TypeError):
                pass

    # ==================== CONTRÔLE DU SERVICE ====================

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
        """Vérifie si les demandes sont acceptées."""
        if self._db_manager:
            maint = str(self._db_manager.get_config_value("maintenance_mode", "false")).lower()
            if maint in ("true", "1", "yes"):
                return False

            val = str(self._db_manager.get_config_value("bot_active", "true")).lower()
            return val in ("true", "1", "yes")
        return True

    # ==================== GESTION DES LIMITES & QUOTAS ====================

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