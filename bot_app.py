import logging
from config import Config
from database import DatabaseManager
from main import TelegramBot

logger = logging.getLogger(__name__)


def create_telegram_app():
    """Initialise la configuration, la base de données et configure l'application Telegram."""
    config = Config()

    # Maintient un pool réduit pour ne pas saturer la limite MySQL (9 connexions max)
    db_manager = DatabaseManager(config, pool_size=2)
    config.set_db_manager(db_manager)

    bot = TelegramBot(config, db_manager)
    app = bot.setup_application()
    return app