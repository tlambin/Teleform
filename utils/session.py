"""Module de gestion des états de session en mémoire vive."""

import logging
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

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


def clear_transient_user_data(context: ContextTypes.DEFAULT_TYPE) -> int:
    """Purge les clés de saisie temporaires orphelines dans context.user_data tout en préservant les filtres et caches."""
    if not context or not hasattr(context, "user_data") or not isinstance(context.user_data, dict):
        return 0

    purged_count = 0

    # 1. Suppression par liste blanche exacte
    for key in TRANSIENT_USER_DATA_KEYS:
        if key in context.user_data:
            context.user_data.pop(key, None)
            purged_count += 1

    # 2. Suppression préventive par motifs dynamiques (waiting_* et cancel_reason_*)
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