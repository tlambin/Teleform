# handlers/admin/__init__.py
"""Module administration"""

from .suivi import SuiviManager
from .statuts import StatutsManager
from .photos import PhotosManager
from .dispo import DispoManager
from .alias import AliasManager

__all__ = [
    'SuiviManager',
    'StatutsManager',
    'PhotosManager',
    'DispoManager',
    'AliasManager'
]