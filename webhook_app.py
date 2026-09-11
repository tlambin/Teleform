# webhook_app.py
import asyncio
import logging
import os
from flask import Flask, request, jsonify
from telegram import Update
from config import Config
from bot_app import create_telegram_app

logger = logging.getLogger(__name__)

flask_app = Flask(__name__)

# Initialisation de la config et de l'app Telegram
config = Config()
bot_app = create_telegram_app()

# Récupération sécurisée depuis le fichier .env (aucune valeur par défaut sensible)
CRON_SECRET = os.getenv("CRON_SECRET_TOKEN")

# Création et démarrage de la boucle asyncio globale
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# Initialisation asynchrone du bot au démarrage du worker
loop.run_until_complete(bot_app.initialize())
loop.run_until_complete(bot_app.start())


@flask_app.route('/', methods=['GET'])
def index():
    return "Bot is running.", 200


@flask_app.route(f'/{config.BOT_TOKEN}', methods=['POST'])
def webhook():
    if request.method == 'POST':
        json_data = request.get_json(force=True)
        update = Update.de_json(json_data, bot_app.bot)
        
        # Traitement asynchrone du message
        loop.run_until_complete(bot_app.process_update(update))
        return jsonify(status="ok"), 200

    return "Method not allowed", 405


@flask_app.route('/api/cron/reminders', methods=['GET'])
def trigger_hourly_reminders():
    token = request.args.get("token")
    
    # Vérifie qu'un token est bien défini en env et correspond à la requête
    if not CRON_SECRET or token != CRON_SECRET:
        return jsonify(status="forbidden", error="Jeton invalide"), 403

    try:
        db_manager = bot_app.bot_data.get("db_manager")
        if not db_manager:
            from database import get_db_manager
            db_manager = get_db_manager(config)

        import main as bot_main

        class DummyJob:
            data = {"db_manager": db_manager}

        class DummyContext:
            job = DummyJob()
            bot = bot_app.bot

        loop.run_until_complete(bot_main.check_and_send_admin_reminders(DummyContext()))
        return jsonify(status="ok", message="Rappels vérifiés et envoyés."), 200
    except Exception as exc:
        logger.error("Erreur exécution cron reminders : %s", exc, exc_info=True)
        return jsonify(status="error", message=str(exc)), 500