"""Module de gestion des états de session en mémoire vive."""

import logging
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

# Clés temporaires à éliminer lors d'un retour au menu ou reset
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
}


def clear_transient_user_data(context: ContextTypes.DEFAULT_TYPE) -> int:
    """Purge les clés de saisie temporaires orphelines dans context.user_data tout en préservant les filtres et caches."""
    if not context or not hasattr(context, "user_data") or not isinstance(context.user_data, dict):
        return 0

    purged_count = 0
    # Suppression par liste exacte
    for key in TRANSIENT_USER_DATA_KEYS:
        if key in context.user_data:
            context.user_data.pop(key, None)
            purged_count += 1

    # Suppression préventive par motif (toute clé 'waiting_' non listée)
    keys_to_delete = [k for k in context.user_data.keys() if str(k).startswith("waiting_")]
    for k in keys_to_delete:
        context.user_data.pop(k, None)
        purged_count += 1

    if purged_count > 0:
        logger.debug("Purge de session context.user_data : %d clé(s) temporaire(s) nettoyée(s).", purged_count)

    return purged_count