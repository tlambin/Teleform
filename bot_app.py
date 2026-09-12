"""Initialisation de l'instance d'application Telegram."""

import logging
import os
from config import Config
from database import DatabaseManager
from main import TelegramBot
from telegram.request import HTTPXRequest

logger = logging.getLogger(__name__)


def create_telegram_app():
    """Initialise la configuration, la base de données et configure l'application Telegram."""
    config = Config()

    # Détection du proxy obligatoire pour PythonAnywhere
    proxy_url = os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
    if not proxy_url and "pythonanywhere" in os.getenv("PYTHONANYWHERE_SITE", ""):
        proxy_url = "http://proxy.server:3128"

    request = HTTPXRequest(proxy=proxy_url) if proxy_url else None

    # Maintient un pool réduit pour respecter la limite MySQL
    db_manager = DatabaseManager(config, pool_size=2)

    # Vérification et auto-migration automatique des tables et colonnes
    db_manager.create_tables()

    config.set_db_manager(db_manager)

    bot = TelegramBot(config, db_manager, request=request)
    app = bot.setup_application()

    # Injection dans bot_data pour les tâches d'arrière-plan/cron
    app.bot_data["db_manager"] = db_manager

    return app