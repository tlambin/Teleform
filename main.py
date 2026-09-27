#!/usr/bin/env python3
"""Point d'entrée principal de l'application Telegram avec architecture RBAC et persistance."""

import asyncio
from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler
import os
import sys
import time
import pytz

os.environ["TZ"] = "Europe/Paris"
if hasattr(time, "tzset"):
    time.tzset()

from telegram import (
    BotCommand,
    BotCommandScopeChat,
    BotCommandScopeDefault,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.error import (
    BadRequest,
    Conflict,
    Forbidden,
    NetworkError,
    TimedOut,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    PicklePersistence,
    PreCheckoutQueryHandler,
    filters,
)

from config import Config
from database import DatabaseManager
from handlers.admin_handlers import AdminHandlers
from handlers.staff_handlers import StaffHandlers
from handlers.user_handlers import UserHandlers
from jobs.scheduled_tasks import (
    check_and_auto_abandon_expired_remun_demandes,
    check_and_auto_archive_demandes,
    check_and_send_admin_reminders,
    check_and_send_delivery_reminders,
    check_and_send_paid_delivery_reminders,
    check_and_send_unpaid_demande_reminders,
)
from utils.interface_manager import InterfaceManager
from utils.session import clear_transient_user_data, session_manager

# ==================== CONFIGURATION DES LOGS ====================
log_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "bot.log")

rotating_handler = RotatingFileHandler(
    log_file,
    maxBytes=2 * 1024 * 1024,
    backupCount=4,
    encoding="utf-8",
    delay=True,
)
stream_handler = logging.StreamHandler(sys.stdout)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[stream_handler, rotating_handler],
)
logger = logging.getLogger(__name__)
PARIS_TZ = pytz.timezone("Europe/Paris")


def check_log_permissions() -> bool:
    try:
        with open(log_file, "a", encoding="utf-8"):
            pass
        logger.info("Permissions logs vérifiées avec rotation active (2 Mo x 4) : %s", log_file)
        return True
    except Exception as exc:
        logger.warning("Erreur accès logs fichier (%s). Bascule sur console uniquement.", exc)
        return True


# ==================== GESTIONNAIRE D'ERREURS GLOBAL ====================

async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    err = context.error

    if isinstance(err, Forbidden):
        target = "inconnu"
        if isinstance(update, Update) and update.effective_user:
            target = f"{update.effective_user.id} (@{update.effective_user.username or 'sans_tag'})"
        logger.warning("🚫 Action ignorée : le bot a été bloqué par l'utilisateur %s.", target)
        return

    if isinstance(err, BadRequest):
        err_msg = str(err)
        if "Message is not modified" in err_msg:
            return
        if "Query is too old" in err_msg:
            logger.warning("⏳ CallbackQuery expiré : %s", err_msg)
            return
        if "Chat not found" in err_msg:
            logger.warning("❓ Chat introuvable : %s", err_msg)
            return

    if isinstance(err, (TimedOut, NetworkError)):
        logger.warning("🌐 Incident réseau passager Telegram : %s", err)
        return

    if isinstance(err, Conflict):
        logger.critical("💥 Conflit de polling détecté (une autre instance utilise ce token) : %s", err)
        return

    update_id = update.update_id if isinstance(update, Update) else "N/A"
    logger.error("💥 Exception non interceptée lors de l'update #%s : %s", update_id, err, exc_info=err)

    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "⚠️ <b>Une erreur technique inattendue est survenue.</b>\n"
                "L'équipe technique a été informée. Tapez /start pour réinitialiser le menu.",
                parse_mode="HTML"
            )
        except Exception:
            pass


class TelegramBot:
    """Orchestrateur de l'application Telegram."""

    def __init__(self, config: Config, db_manager, request=None):
        self.db_manager = db_manager
        self.config = config
        self.request = request
        self.interface = InterfaceManager(config, db_manager)
        self.user_handlers = UserHandlers(self.config, db_manager)
        self.staff_handlers = StaffHandlers(self.config, db_manager)
        self.admin_handlers = AdminHandlers(self.config, db_manager)

    async def wrapped_start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if self.db_manager.is_user_banned(user_id):
            await update.message.reply_text("🚫 <b>Votre compte a été banni par l'administration.</b>", parse_mode="HTML")
            return
        clear_transient_user_data(context, user_id=user_id)
        return await self.user_handlers.start(update, context)

    async def wrapped_stop_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id if update.effective_user else None
        clear_transient_user_data(context, user_id=user_id)
        msg = (
            "🛑 <b>Opération interrompue</b>\n\n"
            "Toutes vos saisies temporaires en cours ont été annulées.\n"
            "Tapez /start ou cliquez ci-dessous pour revenir au menu d'accueil."
        )
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🏠 MENU PRINCIPAL 🏠", callback_data="start_menu")]])
        if update.message:
            await update.message.reply_text(msg, parse_mode="HTML", reply_markup=kb)

    async def wrapped_interface_callbacks(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user_id = update.effective_user.id if update.effective_user else None
        if query and query.data in ("start_menu", "parametres", "gerer_demandes", "menu_membres", "menu_mon_profil"):
            clear_transient_user_data(context, user_id=user_id)
        return await self.user_handlers.handle_interface_callbacks(update, context)

    async def wrapped_user_callbacks(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user_id = update.effective_user.id if update.effective_user else None
        if query and query.data in ("form_cancel", "cancel_edit", "cancel_user_reply"):
            clear_transient_user_data(context, user_id=user_id)
        return await self.user_handlers.handle_callbacks(update, context)

    async def setup_bot_commands(self, app: Application):
        user_commands = [
            BotCommand("start", "🎯 Démarrer le bot"),
            BotCommand("new", "📝 Créer une demande"),
            BotCommand("demandes", "📋 Mes demandes"),
            BotCommand("stop", "❌ Annuler l'opération"),
        ]
        staff_commands = user_commands + [
            BotCommand("gestion", "🔧 Gérer les demandes"),
            BotCommand("archives", "📦 Archives"),
            BotCommand("alias", "🏷️ Modifier son alias"),
        ]
        admin_commands = staff_commands + [
            BotCommand("power", "🔄 Activer/Désactiver"),
            BotCommand("maintenance", "🛠️ Maintenance"),
        ]

        await app.bot.set_my_commands(user_commands, scope=BotCommandScopeDefault())

        for staff_id in self.config.get_all_staff():
            try:
                await app.bot.set_my_commands(staff_commands, scope=BotCommandScopeChat(chat_id=int(staff_id)))
            except Exception:
                pass

        for admin_id in self.config.get_all_admins():
            try:
                await app.bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=int(admin_id)))
                logger.info("Commandes admin/owner configurées pour %s", admin_id)
            except Exception as exc:
                logger.warning("Impossible de configurer les commandes pour admin %s : %s", admin_id, exc)

    def create_conversation_handlers(self):
        demande_handler = self.user_handlers.formulaire.get_conversation_handler()

        modify_alias_conv = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.staff_handlers.alias.modifier_alias, pattern=r"^modifier_alias$")],
            states={
                self.staff_handlers.alias.WAITING_ALIAS: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.staff_handlers.alias.traiter_nouveau_alias)
                ]
            },
            fallbacks=[
                CallbackQueryHandler(self.staff_handlers.alias.cancel_alias_change, pattern="^cancel_alias_change$"),
                CommandHandler("stop", self.staff_handlers.alias.cancel_alias_change),
            ],
            name="modify_alias_conv",
            persistent=True,
            allow_reentry=True,
            per_user=True,
            per_message=False,
        )

        contact_owner_conv = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.staff_handlers.contact.start_contact_owner, pattern=r"^contacter_owner$")],
            states={
                self.staff_handlers.contact.WAITING_ADMIN_MSG: [
                    MessageHandler(
                        (filters.TEXT | filters.PHOTO | filters.Document.ALL) & ~filters.COMMAND,
                        self.staff_handlers.contact.send_to_owner
                    )
                ]
            },
            fallbacks=[
                CallbackQueryHandler(self.staff_handlers.contact.cancel_contact_owner, pattern="^cancel_contact_owner$"),
                CommandHandler("stop", self.staff_handlers.contact.cancel_contact_owner),
            ],
            name="contact_owner_conv",
            persistent=True,
            allow_reentry=True,
            per_user=True,
            per_message=False,
        )

        owner_reply_conv = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.staff_handlers.contact.start_owner_reply, pattern=r"^owner_reply_to_\d+$")],
            states={
                self.staff_handlers.contact.WAITING_OWNER_REPLY: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.staff_handlers.contact.send_owner_reply)
                ]
            },
            fallbacks=[
                CallbackQueryHandler(self.staff_handlers.contact.cancel_owner_reply, pattern="^cancel_owner_reply$"),
                CommandHandler("stop", self.staff_handlers.contact.cancel_owner_reply),
            ],
            name="owner_reply_conv",
            persistent=True,
            allow_reentry=True,
            per_user=True,
            per_message=False,
        )

        add_staff_conv = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.admin_handlers.staff_ajouter, pattern=r"^staff_ajouter$")],
            states={
                self.admin_handlers.WAITING_STAFF_ID: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.admin_handlers.traiter_staff_ajouter)
                ],
                self.admin_handlers.WAITING_STAFF_CONFIG: [
                    CallbackQueryHandler(self.admin_handlers.handle_recruit_config_callback, pattern=r"^cfgadd_.*$")
                ],
            },
            fallbacks=[
                CallbackQueryHandler(self.admin_handlers.cancel_staff_add, pattern="^cancel_staff_add$"),
                CommandHandler("stop", self.admin_handlers.cancel_staff_add),
            ],
            name="add_staff_conv",
            persistent=True,
            allow_reentry=True,
            per_user=True,
            per_message=False,
        )

        remove_staff_conv = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.admin_handlers.staff_supprimer, pattern=r"^staff_supprimer$")],
            states={
                self.admin_handlers.WAITING_STAFF_REMOVE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.admin_handlers.traiter_staff_supprimer)
                ],
                self.admin_handlers.WAITING_STAFF_CONFIRMATION: [
                    CallbackQueryHandler(self.admin_handlers.confirmer_staff_suppression, pattern=r"^confirm_staff_remove$")
                ],
            },
            fallbacks=[
                CallbackQueryHandler(self.admin_handlers.cancel_staff_remove, pattern="^cancel_staff_remove$"),
                CommandHandler("stop", self.admin_handlers.cancel_staff_remove),
            ],
            name="remove_staff_conv",
            persistent=True,
            allow_reentry=True,
            per_user=True,
            per_message=False,
        )

        add_admin_conv = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.admin_handlers.admin_ajouter, pattern=r"^admin_ajouter$")],
            states={
                self.admin_handlers.WAITING_ADMIN_ID: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.admin_handlers.traiter_admin_ajouter)
                ]
            },
            fallbacks=[
                CallbackQueryHandler(self.admin_handlers.cancel_admin_add, pattern="^cancel_admin_add$"),
                CommandHandler("stop", self.admin_handlers.cancel_admin_add),
            ],
            name="add_admin_conv",
            persistent=True,
            allow_reentry=True,
            per_user=True,
            per_message=False,
        )

        remove_admin_conv = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.admin_handlers.admin_supprimer, pattern=r"^admin_supprimer$")],
            states={
                self.admin_handlers.WAITING_ADMIN_REMOVE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.admin_handlers.traiter_admin_supprimer)
                ],
                self.admin_handlers.WAITING_ADMIN_CONFIRMATION: [
                    CallbackQueryHandler(self.admin_handlers.confirmer_admin_suppression, pattern=r"^confirm_admin_remove$")
                ],
            },
            fallbacks=[
                CallbackQueryHandler(self.admin_handlers.cancel_admin_remove, pattern="^cancel_admin_remove$"),
                CommandHandler("stop", self.admin_handlers.cancel_admin_remove),
            ],
            name="remove_admin_conv",
            persistent=True,
            allow_reentry=True,
            per_user=True,
            per_message=False,
        )

        add_vip_conv = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.admin_handlers.start_add_vip, pattern=r"^owner_add_vip$")],
            states={
                self.admin_handlers.WAITING_VIP_USER: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.admin_handlers.process_vip_target_user)
                ],
                self.admin_handlers.WAITING_VIP_DURATION: [
                    CallbackQueryHandler(self.admin_handlers.process_vip_duration_choice, pattern=r"^vip_dur_.*$"),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.admin_handlers.process_vip_duration_choice),
                ],
            },
            fallbacks=[
                CallbackQueryHandler(self.admin_handlers.cancel_vip_action, pattern="^cancel_vip_action$"),
                CommandHandler("stop", self.admin_handlers.cancel_vip_action),
            ],
            name="add_vip_conv",
            persistent=True,
            allow_reentry=True,
            per_user=True,
            per_message=False,
        )

        remove_vip_conv = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.admin_handlers.start_remove_vip, pattern=r"^owner_remove_vip$")],
            states={
                self.admin_handlers.WAITING_VIP_REMOVE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.admin_handlers.process_vip_remove_choice)
                ]
            },
            fallbacks=[
                CallbackQueryHandler(self.admin_handlers.cancel_vip_action, pattern="^cancel_vip_action$"),
                CommandHandler("stop", self.admin_handlers.cancel_vip_action),
            ],
            name="remove_vip_conv",
            persistent=True,
            allow_reentry=True,
            per_user=True,
            per_message=False,
        )

        return [
            demande_handler,
            modify_alias_conv,
            contact_owner_conv,
            owner_reply_conv,
            add_staff_conv,
            remove_staff_conv,
            add_admin_conv,
            remove_admin_conv,
            add_vip_conv,
            remove_vip_conv,
        ]

    async def handle_self_pref_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if not query or not update.effective_user:
            return

        user_id = update.effective_user.id
        data = query.data or ""

        if data.startswith("self_pref_locked_"):
            await query.answer("🔒 Vos préférences de ciblage sont verrouillées par l'administration.", show_alert=True)
            return

        if not self.db_manager.can_staff_edit_preferences(user_id):
            await query.answer("🔒 Action bloquée : vos préférences sont verrouillées par un administrateur.", show_alert=True)
            return

        if data.startswith("self_pref_res_"):
            val = data.replace("self_pref_res_", "")
            self.db_manager.update_staff_permission(user_id, "perm_reseaux", val)
            await query.answer("✅ Réseaux mis à jour !")
        elif data.startswith("self_pref_ori_"):
            val = data.replace("self_pref_ori_", "")
            self.db_manager.update_staff_permission(user_id, "perm_orientation", val)
            await query.answer("✅ Orientation mise à jour !")
        elif data.startswith("self_pref_type_"):
            if self.db_manager.is_admin(user_id):
                val = data.replace("self_pref_type_", "")
                self.db_manager.update_staff_permission(user_id, "perm_type", val)
                await query.answer("✅ Formule mise à jour !")
            else:
                await query.answer("❌ Seuls les administrateurs peuvent modifier cette option.", show_alert=True)
                return

        self.db_manager.clear_cache()
        text, kb = self.interface.get_staff_self_preferences_menu(user_id)

        try:
            await query.edit_message_text(
                text=text,
                parse_mode="HTML",
                reply_markup=kb,
                disable_web_page_preview=True
            )
        except BadRequest as e:
            if "Message is not modified" in str(e):
                try:
                    await query.edit_message_reply_markup(reply_markup=kb)
                except Exception:
                    pass
            else:
                logger.warning("Erreur lors de l'édition texte des préférences : %s", e)
        except Exception as err:
            logger.warning("Erreur rafraîchissement préférences staff : %s", err)

    def setup_application(self) -> Application:
        persistence_file = os.path.join(os.path.dirname(__file__), "bot_conversations.pickle")
        persistence = PicklePersistence(
            filepath=persistence_file,
            store_data=None,
            update_interval=5,
        )

        builder = (
            Application.builder()
            .token(self.config.BOT_TOKEN)
            .persistence(persistence)
        )
        if self.request:
            builder = builder.request(self.request)

        app = builder.build()
        app.bot_data["db_manager"] = self.db_manager
        app.bot_data["config"] = self.config
        app.bot_data["user_handlers"] = self.user_handlers

        for handler in self.create_conversation_handlers():
            app.add_handler(handler)

        # Enregistrement direct des écouteurs de paiement
        app.add_handler(PreCheckoutQueryHandler(self.user_handlers.paiement.precheckout_callback))
        app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, self.user_handlers.paiement.successful_payment_callback))

        # Commandes textuelles privées
        app.add_handler(CommandHandler("start", self.wrapped_start_command, filters=filters.ChatType.PRIVATE))
        app.add_handler(CommandHandler("stop", self.wrapped_stop_command, filters=filters.ChatType.PRIVATE))
        app.add_handler(CommandHandler("demandes", self.user_handlers.voir_demandes, filters=filters.ChatType.PRIVATE))
        app.add_handler(CommandHandler("archives", lambda u, c: self.staff_handlers.archives.show_archives(u, c, page=0), filters=filters.ChatType.PRIVATE))
        app.add_handler(CommandHandler("toggle_demandes", self.admin_handlers.toggle_demandes, filters=filters.ChatType.PRIVATE))
        app.add_handler(CommandHandler("maintenance", self.admin_handlers.run_maintenance, filters=filters.ChatType.PRIVATE))

        # 1. Clics des préférences autonomes du membre
        app.add_handler(CallbackQueryHandler(self.handle_self_pref_callback, pattern=r"^self_pref_.*$"))

        # 2. Aiguillage Gouvernance & Administration
        app.add_handler(CallbackQueryHandler(
            self.admin_handlers.handle_admin_callbacks,
            pattern=r"^(bot_on|bot_off|confirm_bot_off|cancel_bot_off|maintenance|bot_stats|admin_global_archives|global_arch_page_.*|menu_membres|search_member_prompt|liste_bannis_.*|ban_prompt_.*|unban_.*|gerer_vips|gerer_staff|staff_view_demandes_.*|admin_remind_staff_demande_.*|gerer_admins|menu_channels|toggle_allow_.*|menu_delais|cfg_sub_.*|set_arch_.*|set_rem_.*|set_payrem_.*|set_remun_days_.*|perm_staff_.*|set_permstaff_.*|perm_admin_.*|set_permadmin_.*|menu_cfg_group|toggle_cfg_group_enabled|set_cfg_group_id|set_cfg_group_link|menu_cfg_support|set_cfg_support_contact|menu_danger_zone|danger_purge_.*|danger_confirm_yes_.*|toggle_pay_staff_.*|unarchive_reussie_.*|unarchive_abandon_.*|contacter_archive_.*)$",
        ))

        # 3. Aiguillage Traitement opérationnel des dossiers & Démission
        app.add_handler(CallbackQueryHandler(
            self.staff_handlers.handle_staff_callbacks,
            pattern=r"^(demandes_disponibles|dispo_.*|dispo_remun_pending_info|admin_del_dispo_.*|dispo_ask_remun_.*|staff_report_dispo_.*|demandes_suivies|suivi_.*|confirm_payment_prio_.*|confirm_payment_prio_exec_.*|vip_accept_.*|vip_decline_.*|demandes_archives|archive_page_.*|mark_treated_menu_.*|change_status_.*|set_status_.*|status_.*|voir_photo_.*|retour_texte_.*|suivre_demande_.*|contacter_.*|contact_mode_.*|toggle_contact_content_.*|contact_close_conv_.*|cancel_contact_.*|send_batch_.*|menu_notifs|pref_.*|menu_surveillance_notifs|toggle_mon_.*|profil_.*|staff_list_.*|user_view_demandes_.*|user_list_.*|archive_view_.*|admin_contact_staff_.*|admin_pause_.*|admin_resume|menu_demission|demission_confirm_.*|demission_exec_.*)$",
        ))

        # 4. Menus d'interface et navigation
        app.add_handler(CallbackQueryHandler(
            self.wrapped_interface_callbacks,
            pattern=r"^(voir_demandes|start_menu|gerer_demandes|parametres|menu_mon_profil|menu_demission|staff_self_prefs|staff_payment_settings|modifier_alias|gerer_admins|gerer_staff|gerer_bot|bot_toggle_suspension|menu_danger_zone|menu_channels|menu_limits|menu_cfg_group|menu_cfg_support|menu_membres|limit_.*|stat_access_denied|arch_access_denied)$",
        ))

        # 5. Callbacks utilisateurs / clients
        app.add_handler(CallbackQueryHandler(
            self.wrapped_user_callbacks,
            pattern=r"^(check_subscription|nav_.*|mes_archives|user_arch_page_.*|modify_.*|edit_.*|delete_.*|confirm_delete_.*|cancel_demande_.*|form_.*|cancel_edit|reply_to_admin_.*|cancel_user_reply|quota_reached_info|reprendre_demande_.*|archiver_demande_.*|menu_vip_shop|buy_vip_.*|menu_vip_settings|vip_set_assign_.*|vip_pick_auto_staff|remind_admin_free_.*|remind_admin_pay_.*|vip_contact_admin_.*|vip_assign_admin_.*|ask_cancel_demande_.*|accept_cancel_.*|refuse_cancel_.*|contact_admin_.*|upgrade_prio_.*|pay_stars_prio_.*|pay_contact_prio_.*|user_accept_remun_.*|user_refuse_remun_.*)$",
        ))

        # Réception des messages & médias privés
        app.add_handler(MessageHandler(
            filters.ChatType.PRIVATE & ((filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL) & ~filters.COMMAND),
            self.handle_incoming_messages,
        ))

        app.add_error_handler(global_error_handler)

        if app.job_queue:
            app.job_queue.run_repeating(check_and_send_admin_reminders, interval=3600, first=15)
            app.job_queue.run_repeating(check_and_auto_archive_demandes, interval=3600, first=30)
            app.job_queue.run_repeating(check_and_send_delivery_reminders, interval=21600, first=45)
            app.job_queue.run_repeating(check_and_send_paid_delivery_reminders, interval=86400, first=60)
            app.job_queue.run_repeating(check_and_send_unpaid_demande_reminders, interval=21600, first=75)
            app.job_queue.run_repeating(check_and_auto_abandon_expired_remun_demandes, interval=21600, first=90)
            logger.info("⏰ Tâches JobQueue configurées et actives.")

        async def post_init(application: Application):
            await self.setup_bot_commands(application)

        app.post_init = post_init
        return app

    async def handle_incoming_messages(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.effective_chat or update.effective_chat.type != "private":
            return

        user_id = update.effective_user.id

        if self.db_manager.is_user_banned(user_id):
            await update.message.reply_text(
                "🚫 <b>Votre compte a été banni de la plateforme.</b>\n"
                "L'accès aux services vous est définitivement révoqué.",
                parse_mode="HTML"
            )
            return

        # 1. Zone de danger (purge) : vérification RAM + disque
        if context.user_data.get("waiting_danger_confirmation") or session_manager.get_state(user_id, "danger_purge"):
            handled = await self.admin_handlers.handle_danger_text_input(update, context)
            if handled:
                return

        # 2. Motif de ban : vérification RAM + disque
        if context.user_data.get("waiting_ban_reason") or session_manager.get_state(user_id, "ban_process"):
            handled = await self.admin_handlers.handle_ban_reason_input(update, context)
            if handled:
                return

        # 3. Recherche membre : vérification RAM + disque
        if context.user_data.get("waiting_member_search") or session_manager.get_state(user_id, "waiting_member_search"):
            handled = await self.admin_handlers.handle_member_search_input(update, context)
            if handled:
                return

        # 4. Session de contact staff
        if context.user_data.get("contact_session"):
            handled = await self.staff_handlers.handle_collect_admin_media(update, context)
            if handled:
                return

        # 5. Flux textuels usagers
        await self.user_handlers.handle_text_messages(update, context)

    def run(self):
        app = self.setup_application()
        logger.info("🚀 Bot Telegram démarré avec succès (mode polling local)")
        app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    try:
        check_log_permissions()
        config = Config()
        db_manager = DatabaseManager(config)
        db_manager.create_tables()
        config.set_db_manager(db_manager)

        bot = TelegramBot(config, db_manager)
        bot.run()

    except Exception as e:
        logger.critical("Erreur critique au démarrage : %s", e, exc_info=True)
        sys.exit(1)