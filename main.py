#!/usr/bin/env python3
import logging
import os
import sys
import time

# Configuration timezone (protégée pour supporter Windows et Unix)
os.environ["TZ"] = "Europe/Paris"
if hasattr(time, "tzset"):
    time.tzset()

from telegram import BotCommand, BotCommandScopeChat, BotCommandScopeDefault, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from config import Config
from database import DatabaseManager
from handlers.admin_handlers import AdminHandlers
from handlers.owner_handlers import OwnerHandlers
from handlers.user_handlers import UserHandlers

# Logs console propres avec fallback fichier local
log_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "bot.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)


def check_log_permissions() -> bool:
    """Vérifie la possibilité d'écrire dans le fichier de log local."""
    try:
        with open(log_file, "a", encoding="utf-8") as _:
            pass
        logger.info("Permissions logs vérifiées : %s", log_file)
        return True
    except Exception as exc:
        logger.warning("Erreur lors de l'accès aux logs fichier (%s). Bascule sur console uniquement.", exc)
        return True


class TelegramBot:
    def __init__(self, config: Config, db_manager):
        self.db_manager = db_manager
        self.config = config
        self.user_handlers = UserHandlers(self.config, db_manager)
        self.admin_handlers = AdminHandlers(self.config, db_manager)
        self.owner_handlers = OwnerHandlers(self.config, db_manager)

    async def setup_bot_commands(self, app: Application):
        """Configure les commandes visibles selon les rôles."""
        user_commands = [
            BotCommand("start", "🎯 Démarrer le bot"),
            BotCommand("new", "📝 Créer une demande"),
            BotCommand("demandes", "📋 Mes demandes"),
            BotCommand("stop", "❌ Annuler l'opération")
        ]
        admin_commands = user_commands + [
            BotCommand("gestion", "🔧 Gérer les demandes"),
            BotCommand("archives", "📦 Archives"),
            BotCommand("alias", "🏷️ Modifier son alias"),
            BotCommand("power", "🔄 Activer/Désactiver"),
            BotCommand("maintenance", "🛠️ Maintenance")
        ]

        await app.bot.set_my_commands(user_commands, scope=BotCommandScopeDefault())

        for admin_id in self.config.get_all_admins():
            try:
                await app.bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=int(admin_id)))
                logger.info("Commandes admin configurées pour %s", admin_id)
            except Exception as exc:
                logger.warning("Impossible de configurer les commandes pour admin %s: %s", admin_id, exc)

    def create_conversation_handlers(self):
        """Crée les ConversationHandlers du bot."""
        demande_handler = self.user_handlers.formulaire.get_conversation_handler()

        modify_alias_conv = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(
                    self.admin_handlers.alias.modifier_alias,
                    pattern="^modifier_alias$"
                )
            ],
            states={
                self.admin_handlers.alias.WAITING_ALIAS: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.admin_handlers.alias.traiter_nouveau_alias)
                ]
            },
            fallbacks=[
                CallbackQueryHandler(self.admin_handlers.alias.cancel_alias_change, pattern="^cancel_alias_change$"),
                CommandHandler("stop", self.admin_handlers.alias.cancel_alias_change)
            ],
            allow_reentry=True,
            per_user=True
        )

        add_admin_conv = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(
                    self.owner_handlers.admin_ajouter,
                    pattern="^admin_ajouter$"
                )
            ],
            states={
                self.owner_handlers.WAITING_ADMIN_ID: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.owner_handlers.traiter_admin_ajouter)
                ]
            },
            fallbacks=[
                CallbackQueryHandler(self.owner_handlers.cancel_admin_add, pattern="^cancel_admin_add$"),
                CommandHandler("stop", self.owner_handlers.cancel_admin_add)
            ],
            allow_reentry=True,
            per_user=True
        )

        remove_admin_conv = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(
                    self.owner_handlers.admin_supprimer,
                    pattern="^admin_supprimer$"
                )
            ],
            states={
                self.owner_handlers.WAITING_ADMIN_REMOVE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.owner_handlers.traiter_admin_supprimer)
                ],
                self.owner_handlers.WAITING_CONFIRMATION: [
                    CallbackQueryHandler(
                        self.owner_handlers.confirmer_admin_suppression,
                        pattern="^confirm_admin_remove$"
                    )
                ]
            },
            fallbacks=[
                CallbackQueryHandler(self.owner_handlers.cancel_admin_remove, pattern="^cancel_admin_remove$"),
                CommandHandler("stop", self.owner_handlers.cancel_admin_remove)
            ],
            allow_reentry=True,
            per_user=True
        )

        return [demande_handler, modify_alias_conv, add_admin_conv, remove_admin_conv]

    def setup_application(self) -> Application:
        """Configure et câble tous les handlers du bot."""
        app = Application.builder().token(self.config.BOT_TOKEN).build()

        # Enregistrement prioritaire des ConversationHandlers
        for handler in self.create_conversation_handlers():
            app.add_handler(handler)

        # Commandes standard
        app.add_handler(CommandHandler("start", self.user_handlers.start))
        app.add_handler(CommandHandler("demandes", self.user_handlers.voir_demandes))
        app.add_handler(CommandHandler("toggle_demandes", self.owner_handlers.toggle_demandes))
        app.add_handler(CommandHandler("maintenance", self.owner_handlers.run_maintenance))

        # Callbacks d'interface générale
        app.add_handler(CallbackQueryHandler(
            self.user_handlers.handle_interface_callbacks,
            pattern=r"^(voir_demandes|start_menu|gerer_demandes|parametres|modifier_alias|gerer_admins|gerer_bot|menu_limits|limit_.*|bot_.*)$"
        ))

        # Callbacks admin
        app.add_handler(CallbackQueryHandler(
            self.admin_handlers.handle_admin_callbacks,
            pattern=r"^(admin_|demandes_disponibles|dispo_|demandes_suivies|suivi_|mark_treated_menu|change_status_|set_status_|voir_photo_|retour_texte_|suivre_demande_|contacter_|contact_mode_|cancel_contact_|send_batch_)"
        ))

        # Callbacks utilisateur
        app.add_handler(CallbackQueryHandler(
            self.user_handlers.handle_callbacks,
            pattern=r"^(nav_|modify_|edit_|delete_|confirm_delete_|cancel_demande_|form_|cancel_edit|reply_to_admin_|cancel_user_reply|quota_reached_info)"
        ))

        # Messages (texte, photos, vidéos, documents) hors commandes
        app.add_handler(MessageHandler(
            (filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL) & ~filters.COMMAND,
            self.user_handlers.handle_text_messages
        ))

        async def post_init(application: Application):
            await self.setup_bot_commands(application)

        app.post_init = post_init
        return app

    def run(self):
        """Démarre le bot en mode polling local."""
        app = self.setup_application()
        logger.info("🚀 Bot Telegram démarré (mode polling)")
        app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    try:
        check_log_permissions()

        logger.info("1. Initialisation de la base de données...")
        config = Config()
        db_manager = DatabaseManager(config)
        db_manager.create_tables()
        logger.info("✅ Base de données initialisée")

        logger.info("2. Configuration avec cache intelligent...")
        config = Config()
        config.set_db_manager(db_manager)
        logger.info("Admins chargés au démarrage : %s", config.admin_ids)

        if not config.admin_ids:
            logger.warning("⚠️ Aucun admin trouvé au démarrage !")

        logger.info("3. Démarrage de l'application...")
        bot = TelegramBot(config, db_manager)
        bot.run()

    except Exception as e:
        logger.critical("Erreur critique au démarrage: %s", e, exc_info=True)
        sys.exit(1)