#!/usr/bin/env python3
# Configuration timezone Paris
import os
import time
os.environ["TZ"] = "Europe/Paris"
time.tzset()

import logging
from telegram.ext import (Application, CommandHandler, ConversationHandler, MessageHandler, filters, CallbackQueryHandler)
from telegram import Update, BotCommand, BotCommandScopeDefault, BotCommandScopeChat
from config import Config
from handlers.user_handlers import UserHandlers
from handlers.admin_handlers import AdminHandlers
from handlers.owner_handlers import OwnerHandlers
from database import get_db_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

def check_log_permissions():
    """Vérifie les permissions d'écriture pour les logs"""
    log_file = '/tmp/bot_output.log'
    try:
        with open(log_file, 'a') as _:
            pass
        logger.info(f"✅ Permissions logs vérifiées : {log_file}")
        return True
    except PermissionError:
        print(f"⚠️ Permissions insuffisantes pour écrire dans {log_file}")
        return False
    except Exception as e:
        print(f"❌ Erreur vérification logs : {e}")
        return False

class TelegramBot:
    def __init__(self, config, db_manager):
        self.db_manager = db_manager
        self.config = config
        self.user_handlers = UserHandlers(self.config, db_manager)
        self.admin_handlers = AdminHandlers(self.config, db_manager)
        self.owner_handlers = OwnerHandlers(self.config, db_manager)

    async def setup_bot_commands(self, app):
        """Configure les commandes visibles selon les rôles"""
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
        # Commandes pour tous
        await app.bot.set_my_commands(user_commands, scope=BotCommandScopeDefault())
        # Commandes pour chaque admin
        for admin_id in self.config.get_all_admins():
            try:
                await app.bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=int(admin_id)))
                logger.info(f"Commandes admin configurées pour {admin_id}")
            except Exception as e:
                logger.warning(f"Impossible de configurer les commandes pour admin {admin_id}: {e}")

    def create_conversation_handlers(self):
        """Crée les ConversationHandlers utilisateur"""
        handlers = []

        # ✅ CONVERSATION HANDLER via FormulaireManager selon ÉTAPE 3.4
        demande_handler = self.user_handlers.formulaire.get_conversation_handler()
        handlers.append(demande_handler)

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

        handlers.extend([modify_alias_conv, add_admin_conv, remove_admin_conv])
        return handlers

    def setup_application(self):
        """Configure l'application Telegram"""
        app = Application.builder().token(self.config.BOT_TOKEN).build()

        # ConversationHandlers utilisateur
        for handler in self.create_conversation_handlers():
            app.add_handler(handler)

        # Commandes utilisateur
        app.add_handler(CommandHandler("start", self.user_handlers.start))
        app.add_handler(CommandHandler("demandes", self.user_handlers.voir_demandes))

        # Commandes admin

        # Commandes super admin
        app.add_handler(CommandHandler("toggle_demandes", self.owner_handlers.toggle_demandes))
        app.add_handler(CommandHandler("maintenance", self.owner_handlers.run_maintenance))


        # Handlers callback séparés

        app.add_handler(CallbackQueryHandler(
            self.user_handlers.handle_interface_callbacks,
            pattern="^(voir_demandes|start_menu|gerer_demandes|parametres|modifier_alias|gerer_admins|gerer_bot)$"
        ))

        #  Callbacks admin
        app.add_handler(CallbackQueryHandler(
            self.admin_handlers.handle_admin_callbacks,
            pattern=r"^(admin_|demandes_disponibles|dispo_|demandes_suivies|suivi_|mark_treated_menu|change_status_|set_status_|voir_photo_|retour_texte_|suivre_demande_|contacter_)"
        ))

        #  Callbacks owner
        app.add_handler(CallbackQueryHandler(
            self.owner_handlers.handle_owner_callbacks,
            pattern=r"^(bot_on|bot_off|confirm_bot_off|cancel_bot_off|maintenance|bot_stats)$"
        ))

        #  Callbacks utilisateur
        app.add_handler(CallbackQueryHandler(
            self.user_handlers.handle_callbacks,
            pattern=r"^(nav_|modify_|edit_|delete_|confirm_delete_|cancel_demande_|form_|cancel_edit)"
        ))

        # MessageHandlers génériques
        app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            self.user_handlers.handle_text_messages
        ))

        # Configuration des commandes (au démarrage)
        # Utilise un job pour lancer la tâche asynchrone après le démarrage de l'app
        async def post_init(application):
            await self.setup_bot_commands(application)
        app.post_init = post_init

        return app

    def run(self):
        """Démarre le bot"""
        app = self.setup_application()
        logger.info("🚀 Bot Telegram démarré")
        app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    try:
        if not check_log_permissions():
            print("❌ Impossible de démarrer le bot - problème d'accès aux logs")
            exit(1)

        # 1. Initialisation de la base de données
        logger.info("Initialisation de la base de données...")
        db_manager = get_db_manager()
        db_manager.create_tables()
        logger.info("✅ Base de données initialisée")

        # 2. Configuration avec cache intelligent
        logger.info("Configuration du cache intelligent...")
        config = Config()

        # Liaison et chargement forcé du cache
        config.set_db_manager(db_manager)
        logger.info(f"Admins chargés au démarrage : {config.admin_ids}")

        if len(config.admin_ids) == 0:
            logger.warning("⚠️ Aucun admin trouvé au démarrage !")

        # 4. Initialisation du bot avec config partagé
        logger.info("Initialisation du bot Telegram...")
        bot = TelegramBot(config, db_manager)
        bot.run()

    except Exception as e:
        logger.error(f"Erreur critique au démarrage: {e}")
        logger.error(f"Type d'erreur: {type(e).__name__}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise