"""Module de gestion des états de session en mémoire vive et persistance sur disque."""

import json
import logging
import os
import time
from typing import Any, Optional
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

# Fichier de persistance stocké à la racine du projet
SESSION_FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data_sessions.json")

# Clés temporaires à éliminer lors d'un retour au menu ou reset (/stop, /start, etc.)
TRANSIENT_USER_DATA_KEYS = {
    # Flux création de demande
    "demande",
    "waiting_details",
    "waiting_photo",
    # Flux staff / statuts / gestion
    "waiting_abandon_reason",
    "waiting_staff_report_reason",
    "waiting_admin_del_reason",
    "waiting_staff_revalorisation_prix",
    "waiting_dispo_search",
    "waiting_suivi_search",
    # Flux contact staff <-> client & staff <-> direction
    "contact_session",
    "replying_to_admin",
    "target_admin_reply_id",
    # Flux rémunération & upgrade
    "waiting_upgrade_prio_amount",
    "waiting_client_std_remun_amount",
    # Flux annulation client
    "waiting_cancel_reason_demande_id",
    # Flux zone de danger & limites
    "waiting_danger_confirmation",
    "pending_danger_target",
    "waiting_limit_input",
    "waiting_owner_input",
    # Flux édition
    "editing",
    "editing_field",
    "editing_demande_id",
    # Flux admin / staff
    "waiting_new_staff_alias",
    "waiting_custom_quota",
    "waiting_custom_hours",
    "waiting_custom_days",
    "waiting_broadcast_text",
    "admin_remove_list",
    "target_admin_to_remove",
    "target_vip_user",
    "vip_remove_list",
}


# ==================== PERSISTANCE DISQUE (ANTI-RELOAD UWSGI) ====================

class StateSessionManager:
    """Stocke temporairement les états sensibles (purges, saisies admin) sur disque."""

    def __init__(self, filepath: str = SESSION_FILE_PATH, default_ttl: float = 900.0):
        self.filepath = os.path.abspath(filepath)
        self.default_ttl = default_ttl  # 15 minutes par défaut
        self._data: dict = {}

    def _load(self):
        """Charge les sessions actives depuis le disque."""
        if not os.path.exists(self.filepath):
            self._data = {}
            return

        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                content = f.read().strip()
                self._data = json.loads(content) if content else {}
            self._purge_expired()
        except Exception as exc:
            logger.warning("Échec lecture sessions disque (%s), réinitialisation.", exc)
            self._data = {}

    def _save(self):
        """Sauvegarde atomique sur disque pour éviter toute corruption concurrente."""
        self._purge_expired()
        tmp_file = f"{self.filepath}.tmp_{os.getpid()}"
        try:
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_file, self.filepath)
        except Exception as exc:
            logger.error("Erreur écriture sessions persistantes : %s", exc)
            if os.path.exists(tmp_file):
                try:
                    os.remove(tmp_file)
                except Exception:
                    pass

    def _purge_expired(self):
        """Nettoie les états dont le délai de validation est écoulé."""
        now = time.time()
        expired_keys = [k for k, val in self._data.items() if val.get("expires_at", 0) < now]
        for k in expired_keys:
            del self._data[k]

    def set_state(self, user_id: int, action_key: str, payload: Any, ttl: Optional[float] = None):
        """Enregistre un état sensible sur disque."""
        self._load()
        key = f"{user_id}:{action_key}"
        expires_at = time.time() + (ttl or self.default_ttl)
        self._data[key] = {
            "payload": payload,
            "expires_at": expires_at,
        }
        self._save()

    def get_state(self, user_id: int, action_key: str) -> Optional[Any]:
        """Récupère l'état si le délai est toujours valide."""
        self._load()
        key = f"{user_id}:{action_key}"
        record = self._data.get(key)
        if not record:
            return None
        if record.get("expires_at", 0) < time.time():
            self.clear_state(user_id, action_key)
            return None
        return record.get("payload")

    def clear_state(self, user_id: int, action_key: Optional[str] = None):
        """Supprime un état spécifique ou tous les états d'un utilisateur."""
        self._load()
        if action_key:
            key = f"{user_id}:{action_key}"
            self._data.pop(key, None)
        else:
            prefix = f"{user_id}:"
            keys_to_del = [k for k in self._data if k.startswith(prefix)]
            for k in keys_to_del:
                del self._data[k]
        self._save()

    def cleanup_disk(self):
        """Purge les entrées expirées et supprime les résidus atomiques temporaires orphelins."""
        self._load()
        self._save()

        base_dir = os.path.dirname(self.filepath)
        filename = os.path.basename(self.filepath)
        now = time.time()

        try:
            if os.path.exists(base_dir):
                for entry in os.listdir(base_dir):
                    if entry.startswith(f"{filename}.tmp_"):
                        full_path = os.path.join(base_dir, entry)
                        try:
                            # Fichier temporaire vieux de plus d'une heure supprimé
                            if now - os.path.getmtime(full_path) > 3600:
                                os.remove(full_path)
                                logger.debug("Fichier temporaire orphelin supprimé : %s", entry)
                        except OSError:
                            pass
        except Exception as exc:
            logger.debug("Erreur lors du nettoyage des temporaires de session : %s", exc)


session_manager = StateSessionManager()


# ==================== NETTOYAGE RAM (CONTEXT.USER_DATA) ====================

def clear_transient_user_data(context: ContextTypes.DEFAULT_TYPE, user_id: Optional[int] = None) -> int:
    """Purge les clés de saisie temporaires orphelines dans context.user_data et sur disque."""
    purged_count = 0

    # 1. Purge du fichier persistant si user_id fourni
    if user_id:
        try:
            session_manager.clear_state(user_id)
        except Exception as exc:
            logger.debug("Erreur purge sessions disque utilisateur %s : %s", user_id, exc)

    # 2. Purge de la mémoire vive
    if not context or not hasattr(context, "user_data") or not isinstance(context.user_data, dict):
        return purged_count

    for key in TRANSIENT_USER_DATA_KEYS:
        if key in context.user_data:
            context.user_data.pop(key, None)
            purged_count += 1

    dynamic_prefixes = ("waiting_", "cancel_reason_")
    keys_to_delete = [
        k for k in context.user_data.keys()
        if any(str(k).startswith(prefix) for prefix in dynamic_prefixes)
    ]

    for k in keys_to_delete:
        context.user_data.pop(k, None)
        purged_count += 1

    if purged_count > 0:
        logger.debug("Purge de session context.user_data : %d clé(s) temporaire(s) nettoyée(s).", purged_count)

    return purged_count