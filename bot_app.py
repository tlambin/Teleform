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

    # Détection fiable du proxy sortant PythonAnywhere (comptes gratuits)
    proxy_url = os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
    if not proxy_url:
        is_pa = any("pythonanywhere" in os.getenv(var, "").lower() for var in ("PYTHONANYWHERE_SITE", "PYTHONANYWHERE_DOMAIN"))
        if is_pa:
            proxy_url = "http://proxy.server:3128"

    # Configuration HTTPX avec marges de timeout confortables
    request_kwargs = {
        "connect_timeout": 10.0,
        "read_timeout": 20.0,
        "write_timeout": 20.0,
        "pool_timeout": 10.0,
    }
    if proxy_url:
        request_kwargs["proxy"] = proxy_url

    request = HTTPXRequest(**request_kwargs)

    # Maintient un pool réduit pour respecter le quota max_user_connections
    db_manager = DatabaseManager(config, pool_size=2)

    # Création des tables et index initiaux
    db_manager.init_db()

    config.set_db_manager(db_manager)

    bot = TelegramBot(config, db_manager, request=request)
    app = bot.setup_application()

    # Injection partagée pour les jobs de fond et le cron horaire
    app.bot_data["db_manager"] = db_manager
    app.bot_data["config"] = config

    logger.info("Application Telegram initialisée avec succès.")
    return app