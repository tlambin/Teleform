"""Package centralisé de persistance MySQL pour le bot PARABAIT."""

from .connection import ConnectionManager
from .schema import SchemaManager
from .repositories.users import UserRepository
from .repositories.demandes import DemandeRepository
from .repositories.archives import ArchiveRepository
from .repositories.staff import StaffRepository
from .repositories.admin import AdminRepository


class DatabaseManager(
    ConnectionManager,
    SchemaManager,
    UserRepository,
    DemandeRepository,
    ArchiveRepository,
    StaffRepository,
    AdminRepository,
):
    """Gestionnaire de persistance unifié avec pool réutilisable et cache applicatif."""

    def __init__(self, config, pool_size: int = 2, *args, **kwargs):
        super().__init__(config, pool_size=pool_size, *args, **kwargs)


_global_db_manager = None


def get_db_manager(config=None):
    """Singleton d'accès au gestionnaire de base de données."""
    global _global_db_manager
    if _global_db_manager is None:
        if config is None:
            from config import Config
            config = Config()
        _global_db_manager = DatabaseManager(config)
    return _global_db_manager


__all__ = ["DatabaseManager", "get_db_manager"]