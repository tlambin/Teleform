"""Package des gestionnaires opérationnels Staff."""

from .alias import AliasManager
from .archives import ArchivesManager
from .contact import ContactManager
from .dispo import DispoManager
from .notifs import NotifsManager
from .photos import PhotosManager
from .profils import ProfilsManager
from .statuts import StatutsManager
from .suivi import SuiviManager

__all__ = [
    "AliasManager",
    "ArchivesManager",
    "ContactManager",
    "DispoManager",
    "NotifsManager",
    "PhotosManager",
    "ProfilsManager",
    "StatutsManager",
    "SuiviManager",
]