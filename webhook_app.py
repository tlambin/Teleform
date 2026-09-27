"""Application Webhook Flask compatible uWSGI / PythonAnywhere."""

import asyncio
import hmac
import logging
import os
import threading
from flask import Flask, jsonify, request
from telegram import Update
from config import Config
from bot_app import create_telegram_app

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

flask_app = Flask(__name__)
config = Config()

CRON_SECRET = os.getenv("CRON_SECRET_TOKEN")
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET")

# Variables gérées par worker (post-fork)
_bot_app = None
_loop = None
_init_lock = threading.Lock()
_cron_is_running = False  # Flag anti-chevauchement des tâches cron


def get_bot_and_loop():
    """Garantit que la boucle asyncio et le bot tournent dans le processus worker réel."""
    global _bot_app, _loop
    if _bot_app is None or _loop is None or not _loop.is_running():
        with _init_lock:
            if _bot_app is None or _loop is None or not _loop.is_running():
                logger.info("⚡ Initialisation post-fork du Bot et de l'Event Loop (PID: %s)", os.getpid())
                _loop = asyncio.new_event_loop()
                t = threading.Thread(target=_loop.run_forever, daemon=True)
                t.start()

                _bot_app = create_telegram_app()

                # Démarrage propre des composants asynchrones PTB
                future_init = asyncio.run_coroutine_threadsafe(_bot_app.initialize(), _loop)
                future_init.result(timeout=15)

                future_start = asyncio.run_coroutine_threadsafe(_bot_app.start(), _loop)
                future_start.result(timeout=15)

                logger.info("✅ Bot Telegram opérationnel dans le worker PID %s", os.getpid())

    return _bot_app, _loop


@flask_app.route('/', methods=['GET'])
def index():
    return "Bot is running.", 200


@flask_app.route(f'/{config.BOT_TOKEN}', methods=['POST'])
def webhook():
    if TELEGRAM_WEBHOOK_SECRET:
        secret_header = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if secret_header != TELEGRAM_WEBHOOK_SECRET:
            return jsonify(status="forbidden"), 403

    json_data = request.get_json(force=True, silent=True)
    if not json_data:
        return jsonify(status="bad_request"), 400

    try:
        app_instance, loop = get_bot_and_loop()
        update = Update.de_json(json_data, app_instance.bot)

        future = asyncio.run_coroutine_threadsafe(app_instance.process_update(update), loop)

        def _log_task_result(fut):
            try:
                fut.result()
            except Exception as exc:
                logger.error("💥 Erreur lors du traitement de l'update %s : %s", update.update_id, exc, exc_info=exc)

        future.add_done_callback(_log_task_result)
        return jsonify(status="ok"), 200

    except Exception as exc:
        logger.error("Erreur réception webhook : %s", exc, exc_info=True)
        return jsonify(status="error", message=str(exc)), 500


@flask_app.route('/api/cron/reminders', methods=['GET', 'POST'])
def trigger_hourly_reminders():
    global _cron_is_running

    # Extraction sécurisée du token (URL Query, Authorization Bearer ou X-Cron-Token)
    token = request.args.get("token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:].strip()
        else:
            token = request.headers.get("X-Cron-Token", "").strip()

    if not CRON_SECRET or not token or not hmac.compare_digest(token, CRON_SECRET):
        return jsonify(status="forbidden"), 403

    # Anti-chevauchement : éviter d'accumuler des tâches identiques si la précédente tourne encore
    if _cron_is_running:
        logger.warning("⏳ Cycle cron précédent encore en cours, requête ignorée.")
        return jsonify(status="skipped", message="Tâches précédentes toujours actives."), 429

    try:
        app_instance, loop = get_bot_and_loop()
        db_manager = app_instance.bot_data.get("db_manager")
        if not db_manager:
            from database import DatabaseManager
            db_manager = DatabaseManager(config)

        import main as bot_main

        class DummyJob:
            data = {"db_manager": db_manager}

        class DummyContext:
            job = DummyJob()
            bot = app_instance.bot
            application = app_instance

        async def _run_all_maintenance_tasks():
            global _cron_is_running
            _cron_is_running = True
            ctx = DummyContext()
            logger.info("🚀 Démarrage des tâches périodiques en arrière-plan...")
            try:
                await asyncio.gather(
                    bot_main.check_and_send_admin_reminders(ctx),
                    bot_main.check_and_auto_archive_demandes(ctx),
                    bot_main.check_and_send_delivery_reminders(ctx),
                    bot_main.check_and_send_paid_delivery_reminders(ctx),
                    bot_main.check_and_send_unpaid_demande_reminders(ctx),
                    bot_main.check_and_auto_abandon_expired_remun_demandes(ctx),
                    return_exceptions=True
                )
                logger.info("🏁 Fin de l'exécution des tâches périodiques.")
            finally:
                _cron_is_running = False

        # Lancement non bloquant dans l'Event Loop
        future = asyncio.run_coroutine_threadsafe(_run_all_maintenance_tasks(), loop)

        def _log_cron_result(fut):
            try:
                fut.result()
            except Exception as e:
                logger.error("💥 Erreur d'exécution de la boucle cron : %s", e, exc_info=True)

        future.add_done_callback(_log_cron_result)

        return jsonify(status="ok", message="Tâches cron lancées en arrière-plan."), 200

    except Exception as exc:
        _cron_is_running = False
        logger.error("Erreur lancement cron reminders : %s", exc, exc_info=True)
        return jsonify(status="error", message=str(exc)), 500