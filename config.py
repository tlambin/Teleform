import os
import logging
import threading
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

class Config:
    """Configuration centralisée avec système de cache intelligent unifié"""

    def __init__(self):
        self._validate_required_env_vars()
        self._setup_basic_config()
        self._setup_database_config()
        self._setup_cache_system()
        self._setup_limits_and_paths()
        self.demandes_enabled = True  # État des demandes activé par défaut

    def _validate_required_env_vars(self):
        """Valide la présence des variables d'environnement critiques"""
        required_vars = ['BOT_TOKEN', 'OWNER_ID', 'DB_HOST', 'DB_USER', 'DB_PASSWORD', 'DB_NAME']
        missing_vars = [var for var in required_vars if not os.getenv(var)]

        if missing_vars:
            raise ValueError(f"Variables d'environnement manquantes : {missing_vars}")

        logger.info("Toutes les variables d'environnement requises sont présentes")

    def _setup_basic_config(self):
        """Configuration de base du bot"""
        self.BOT_TOKEN = os.getenv('BOT_TOKEN')

        owner_id_str = os.getenv('OWNER_ID', '0')
        if not owner_id_str.isdigit():
            raise ValueError("OWNER_ID doit être un entier valide")
        self.OWNER_ID = int(owner_id_str)

    def _setup_cache_system(self):
        """Initialise le système de cache intelligent"""
        self.admin_ids = set()
        self._admin_cache_loaded = False
        self._db_manager = None
        self._admin_cache_lock = threading.Lock()

    def _setup_database_config(self):
        """Configuration de la base de données"""
        self.DB_CONFIG = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'user': os.getenv('DB_USER'),
            'password': os.getenv('DB_PASSWORD'),
            'database': os.getenv('DB_NAME'),
            'autocommit': True,
            'connect_timeout': 5,
            'charset': 'utf8mb4'
        }

    def _setup_limits_and_paths(self):
        """Configuration des limites et chemins"""
        self.MAX_STORAGE_MB = 400
        self.CACHE_TIMEOUT = 300
        self.LOG_DIR = '/tmp'

    def set_db_manager(self, db_manager):
        """Définit le gestionnaire de base de données et charge les admins"""
        self._db_manager = db_manager
        self.load_admins(db_manager)
        self._load_owner_alias_if_needed()

    def _load_owner_alias_if_needed(self):
        """Charge l'alias owner depuis config si disponible"""
        if self._db_manager:
            try:
                self.OWNER_ALIAS = self._db_manager.get_owner_alias()
                if not self.OWNER_ALIAS:
                    # Fallback vers variable env ou défaut
                    self.OWNER_ALIAS = os.getenv('OWNER_ALIAS', 'Propriétaire')
                    # Sauvegarder en base pour futures fois
                    self._db_manager.set_owner_alias(self.OWNER_ALIAS)
            except Exception as e:
                logger.error(f"Erreur chargement owner alias: {e}")
                self.OWNER_ALIAS = "Propriétaire"

    def ensure_admin_cache(self):
        """Force le rechargement du cache si nécessaire"""
        if not self._admin_cache_loaded and self._db_manager:
            self.load_admins(self._db_manager)

    def load_admins(self, db_manager):
        """Charge tous les admins avec cache persistant"""
        with self._admin_cache_lock:
            try:
                with db_manager.get_cursor() as cursor:
                    cursor.execute("SELECT user_id FROM admins")
                    rows = cursor.fetchall()

                    # Conversion sécurisée en int
                    self.admin_ids = set()
                    for row in rows:
                        try:
                            admin_id = int(row['user_id'])
                            self.admin_ids.add(admin_id)
                        except (ValueError, TypeError):
                            continue  # Ignorer les erreurs de conversion

                    # ✅ NOUVEAU : Marquer le cache comme chargé
                    self._admin_cache_loaded = True
                    logger.info(f"Cache admin rechargé : {len(self.admin_ids)} administrateurs")

            except Exception as e:
                logger.error(f"Erreur critique load_admins : {e}")
                self.admin_ids = set()
                self._admin_cache_loaded = False

    def is_owner(self, user_id):
        """Vérifie si l'utilisateur est le propriétaire"""
        return user_id == self.OWNER_ID

    def is_admin(self, user_id, secure_mode=False):
        """
        Vérification admin avec modes de sécurité configurables

        Args:
            user_id: ID de l'utilisateur à vérifier
            secure_mode: Si True, force la vérification hybride avec fallback DB

        Returns:
            bool: True si l'utilisateur est admin ou propriétaire
        """
        # Rechargement automatique si cache vide et DB disponible
        if not self._admin_cache_loaded and self._db_manager:
            self.load_admins(self._db_manager)

        # Vérification propriétaire (toujours prioritaire)
        if self.is_owner(user_id):
            return True

        # Conversion en int pour la comparaison
        try:
            user_id_int = int(user_id)

            if secure_mode or len(self.admin_ids) == 0:
                # Mode sécurisé : vérification hybride avec fallback DB
                return self._verify_admin_hybrid(user_id_int)
            else:
                # Mode standard : cache uniquement (performance optimale)
                return user_id_int in self.admin_ids

        except (ValueError, TypeError):
            return self.is_owner(user_id)

    def _verify_admin_hybrid(self, user_id_int):
        """Vérification hybride cache + base de données"""
        # 1. Vérification cache en premier
        if user_id_int in self.admin_ids:
            return True

        # 2. Fallback base de données si cache suspect
        if self._db_manager and (not self._admin_cache_loaded or len(self.admin_ids) == 0):
            try:
                with self._db_manager.get_cursor() as cursor:
                    cursor.execute("SELECT user_id FROM admins WHERE user_id = %s", (user_id_int,))
                    is_admin_db = cursor.fetchone() is not None

                    if is_admin_db:
                        # Recharger tout le cache si admin trouvé en base
                        self.load_admins(self._db_manager)
                        return True

            except Exception as e:
                logger.error(f"Erreur vérification admin DB : {e}")

        return False

    def get_all_admins(self):
        """Retourne tous les admins (pour les commandes bot)"""
        all_admins = set()
        all_admins.add(self.OWNER_ID)  # Le propriétaire
        all_admins.update(self.admin_ids)  # Les admins de la base
        return all_admins

    def add_admin(self, user_id):
        """Ajoute un admin"""
        with self._admin_cache_lock:
            self.admin_ids.add(int(user_id))

    def remove_admin(self, user_id):
        """Supprime un admin"""
        with self._admin_cache_lock:
            self.admin_ids.discard(int(user_id))

    def reload_admins(self, db_manager):
        """Recharge les admins depuis la base (pour synchronisation)"""
        self.load_admins(db_manager)


    def enable_demandes(self):
        """Activer les demandes"""
        self.demandes_enabled = True
        logger.info("✅ Demandes activées")

    def disable_demandes(self):
        """Désactiver les demandes"""
        self.demandes_enabled = False
        logger.info("❌ Demandes désactivées")

    def are_demandes_enabled(self):
        """Vérifier si les demandes sont activées"""
        return self.demandes_enabled