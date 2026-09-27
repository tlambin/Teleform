"""Contrôleur HTTP pour le déclenchement périodique des tâches de maintenance."""

import hmac
import asyncio
import logging
from flask import Blueprint, request, jsonify, abort
from telegram import Bot
from utils.reminders_task import run_hourly_reminders

logger = logging.getLogger(__name__)
cron_bp = Blueprint("cron_bp", __name__)


def extract_token_from_request() -> str:
    """Extrait le jeton de sécurité depuis les en-têtes ou la query string."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()

    custom_header = request.headers.get("X-Cron-Token", "").strip()
    if custom_header:
        return custom_header

    return request.args.get("token", "").strip()


@cron_bp.route("/api/cron/reminders", methods=["GET", "POST"])
def handle_cron_reminders():
    """Déclencheur d'exécution sécurisé par comparaison à temps constant."""
    from config import config  # Instance de ta configuration
    from database.db_manager import db_manager  # Instance DB Manager

    token_recu = extract_token_from_request()
    expected_token = getattr(config, "CRON_SECRET_TOKEN", None)

    if not expected_token or not token_recu or not hmac.compare_digest(token_recu, expected_token):
        logger.warning("Tentative d'accès non autorisée à la route cron depuis %s", request.remote_addr)
        abort(403)

    async def execute_task():
        bot = Bot(token=config.BOT_TOKEN)
        async with bot:
            return await run_hourly_reminders(bot, db_manager, config)

    try:
        report = asyncio.run(execute_task())
        logger.info("Cron horaire terminé avec succès : %s", report)
        return jsonify({
            "status": "success",
            "timestamp": datetime.utcnow().isoformat(),
            "report": report
        }), 200

    except Exception as exc:
        logger.error("Échec critique lors de l'exécution du cron : %s", exc, exc_info=True)
        return jsonify({
            "status": "error",
            "message": "Erreur interne lors du traitement",
            "details": str(exc)
        }), 500