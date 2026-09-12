#!/usr/bin/env python3
"""Point d'entrée principal de l'application Telegram avec gestion des VIP, Telegram Stars et mode pause."""

from datetime import datetime
import logging
import os
import sys
import time
import pytz

# Configuration timezone (support multiplateforme)
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
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    PreCheckoutQueryHandler,
    filters,
)

from config import Config
from database import DatabaseManager
from handlers.admin_handlers import AdminHandlers
from handlers.owner_handlers import OwnerHandlers
from handlers.user_handlers import UserHandlers

# Logs console et fichier local
log_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "bot.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

PARIS_TZ = pytz.timezone("Europe/Paris")


def check_log_permissions() -> bool:
    """Vérifie la possibilité d'écrire dans le fichier de log local."""
    try:
        with open(log_file, "a", encoding="utf-8"):
            pass
        logger.info("Permissions logs vérifiées : %s", log_file)
        return True
    except Exception as exc:
        logger.warning("Erreur accès logs fichier (%s). Bascule sur console uniquement.", exc)
        return True


async def check_and_send_admin_reminders(context: ContextTypes.DEFAULT_TYPE):
    """Vérifie chaque heure si des administrateurs doivent recevoir un rappel de leurs suivis."""
    db_manager = getattr(context, "job", None) and context.job.data.get("db_manager")
    if not db_manager and hasattr(context, "application"):
        db_manager = context.application.bot_data.get("db_manager")

    if not db_manager:
        logger.warning("Vérification des rappels abandonnée : db_manager introuvable.")
        return

    now_paris = datetime.now(PARIS_TZ)
    current_hour = now_paris.hour
    current_weekday = now_paris.weekday()  # 0 = Lundi, 6 = Dimanche
    current_monthday = now_paris.day        # 1 à 31
    today_date = now_paris.date()

    admin_prefs_list = db_manager.get_all_admin_preferences()

    for pref in admin_prefs_list:
        user_id = pref["user_id"]

        # Ne pas envoyer de rappel périodique si l'admin est en pause
        if db_manager.is_admin_paused(user_id):
            continue

        rappel_mode = pref.get("rappel_mode", "sound")
        freq = pref.get("rappel_freq", "daily")
        heure = pref.get("rappel_heure", 18)
        last_date = pref.get("last_rappel_date")

        if rappel_mode == "off":
            continue

        if current_hour != heure:
            continue

        if str(last_date) == str(today_date):
            continue

        if freq == "weekly" and current_weekday != pref.get("rappel_jour_semaine", 6):
            continue
        elif freq == "monthly" and current_monthday != pref.get("rappel_jour_mois", 1):
            continue

        active_demandes = []
        try:
            with db_manager.get_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT d.id, d.request_number, d.prenom, d.nom, d.statut, ds.date_suivi
                    FROM demandes d
                    JOIN demandes_suivi ds ON d.id = ds.demande_id
                    WHERE ds.admin_id = %s AND d.statut IN ('🔄 En cours', '⏳ En attente')
                    ORDER BY ds.date_suivi ASC
                    """,
                    (int(user_id),),
                )
                active_demandes = cursor.fetchall()
        except Exception as db_err:
            logger.error("Erreur lecture suivis pour rappel admin %s : %s", user_id, db_err)
            continue

        if not active_demandes:
            continue

        count = len(active_demandes)
        lines = [
            f"⏰ <b>Rappel de vos demandes suivies ({count})</b>\n",
            "Voici les demandes en attente sous votre responsabilité :",
        ]
        for d in active_demandes[:8]:
            nom_aff = f"{d['prenom']} {d.get('nom') or ''}".strip()
            num = d.get("request_number") or d["id"]
            lines.append(f"• <b>#{num}</b> - {nom_aff} (<code>{d['statut']}</code>)")

        if count > 8:
            lines.append(f"\n<i>... et {count - 8} autre(s) demande(s).</i>")

        text_rappel = "\n".join(lines)
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("💌 Ouvrir mes suivis", callback_data="demandes_suivies")
        ]])

        is_silent = (rappel_mode == "silent")

        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=text_rappel,
                parse_mode="HTML",
                reply_markup=keyboard,
                disable_notification=is_silent,
            )
            db_manager.mark_admin_reminder_sent(user_id)
            logger.info("Rappel automatique envoyé à l'admin %s (mode : %s)", user_id, rappel_mode)
        except Exception as err:
            logger.warning("Erreur envoi rappel programmé à l'admin %s : %s", user_id, err)


# ==================== HANDLERS TELEGRAM STARS ====================

async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Valide les commandes Stars (abonnements VIP ou relances)."""
    query = update.pre_checkout_query
    payload = query.invoice_payload

    if payload.startswith("vip_sub_") or payload.startswith("remind_pay_"):
        await query.answer(ok=True)
    else:
        await query.answer(ok=False, error_message="Erreur de validation de la transaction.")


async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Active le VIP 30 jours ou envoie le rappel payé dès confirmation Stars."""
    payment = update.message.successful_payment
    payload = payment.invoice_payload
    user_id = update.effective_user.id
    db_manager = context.application.bot_data.get("db_manager")
    user_handlers = context.application.bot_data.get("user_handlers")

    if not db_manager:
        logger.error("DatabaseManager introuvable dans bot_data lors du paiement Stars.")
        return

    # Cas 1 : Abonnement VIP 30 jours
    if payload.startswith(f"vip_sub_{user_id}_"):
        db_manager.set_user_vip(user_id, is_vip=True, duration_days=30)

        merci_msg = (
            "🎉 <b>Félicitations ! Votre abonnement VIP 30 Jours est activé !</b>\n\n"
            "Vos privilèges exclusifs sont disponibles immédiatement :\n"
            "• 🚀 <b>Demandes illimitées</b> sans aucune restriction de quota\n"
            "• 🎯 <b>Choix de votre référent</b> parmi l'équipe lors de la création\n"
            "• 💬 <b>Ligne directe</b> avec l'administrateur en charge de vos demandes\n"
            "• 🔔 <b>Relance prioritaire hebdomadaire gratuite</b> sur chacune de vos fiches\n\n"
            "Merci pour votre confiance !"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🗳️ Créer une demande VIP", callback_data="new_demande")],
            [InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")]
        ])
        await update.message.reply_text(merci_msg, parse_mode="HTML", reply_markup=kb)
        logger.info("Abonnement VIP 30 jours activé via Stars pour l'utilisateur %s", user_id)

    # Cas 2 : Paiement d'une relance hebdomadaire
    elif payload.startswith("remind_pay_"):
        parts = payload.split("_")
        demande_id = int(parts[2])

        if user_handlers:
            await user_handlers._dispatch_admin_reminder(update, context, demande_id, is_paid_boost=True)
            logger.info("Rappel payant validé pour la demande #%s par l'utilisateur %s", demande_id, user_id)
        else:
            logger.error("UserHandlers non trouvé dans bot_data.")


class TelegramBot:
    """Orchestrateur de l'application Telegram."""

    def __init__(self, config: Config, db_manager, request=None):
        self.db_manager = db_manager
        self.config = config
        self.request = request
        self.user_handlers = UserHandlers(self.config, db_manager)
        self.admin_handlers = AdminHandlers(self.config, db_manager)
        self.owner_handlers = OwnerHandlers(self.config, db_manager)

    async def setup_bot_commands(self, app: Application):
        """Configure les commandes visibles selon les rôles."""
        user_commands = [
            BotCommand("start", "🎯 Démarrer le bot"),
            BotCommand("new", "📝 Créer une demande"),
            BotCommand("demandes", "📋 Mes demandes"),
            BotCommand("stop", "❌ Annuler l'opération"),
        ]
        admin_commands = user_commands + [
            BotCommand("gestion", "🔧 Gérer les demandes"),
            BotCommand("archives", "📦 Archives"),
            BotCommand("alias", "🏷️ Modifier son alias"),
            BotCommand("power", "🔄 Activer/Désactiver"),
            BotCommand("maintenance", "🛠️ Maintenance"),
        ]

        await app.bot.set_my_commands(user_commands, scope=BotCommandScopeDefault())

        for admin_id in self.config.get_all_admins():
            try:
                await app.bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=int(admin_id)))
                logger.info("Commandes admin configurées pour %s", admin_id)
            except Exception as exc:
                logger.warning("Impossible de configurer les commandes pour admin %s : %s", admin_id, exc)

    def create_conversation_handlers(self):
        """Crée les ConversationHandlers du bot."""
        demande_handler = self.user_handlers.formulaire.get_conversation_handler()

        # Modification d'alias
        modify_alias_conv = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(
                    self.admin_handlers.alias.modifier_alias,
                    pattern=r"^(modifier_alias|owner_edit_alias_\d+)$",
                )
            ],
            states={
                self.admin_handlers.alias.WAITING_ALIAS: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.admin_handlers.alias.traiter_nouveau_alias)
                ]
            },
            fallbacks=[
                CallbackQueryHandler(self.admin_handlers.alias.cancel_alias_change, pattern="^cancel_alias_change$"),
                CommandHandler("stop", self.admin_handlers.alias.cancel_alias_change),
            ],
            allow_reentry=True,
            per_user=True,
        )

        # Contact Admin -> Propriétaire
        contact_owner_conv = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(
                    self.admin_handlers.contact.start_contact_owner,
                    pattern="^contacter_owner$",
                )
            ],
            states={
                self.admin_handlers.contact.WAITING_ADMIN_MSG: [
                    MessageHandler(
                        (filters.TEXT | filters.PHOTO | filters.Document.ALL) & ~filters.COMMAND,
                        self.admin_handlers.contact.send_to_owner
                    )
                ]
            },
            fallbacks=[
                CallbackQueryHandler(self.admin_handlers.contact.cancel_contact_owner, pattern="^cancel_contact_owner$"),
                CommandHandler("stop", self.admin_handlers.contact.cancel_contact_owner),
            ],
            allow_reentry=True,
            per_user=True,
        )

        # Réponse Propriétaire -> Admin
        owner_reply_conv = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(
                    self.admin_handlers.contact.start_owner_reply,
                    pattern=r"^owner_reply_to_\d+$",
                )
            ],
            states={
                self.admin_handlers.contact.WAITING_OWNER_REPLY: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.admin_handlers.contact.send_owner_reply
                    )
                ]
            },
            fallbacks=[
                CallbackQueryHandler(self.admin_handlers.contact.cancel_owner_reply, pattern="^cancel_owner_reply$"),
                CommandHandler("stop", self.admin_handlers.contact.cancel_owner_reply),
            ],
            allow_reentry=True,
            per_user=True,
        )

        # Ajout d'admin par l'Owner
        add_admin_conv = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(
                    self.owner_handlers.admin_ajouter,
                    pattern="^admin_ajouter$",
                )
            ],
            states={
                self.owner_handlers.WAITING_ADMIN_ID: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.owner_handlers.traiter_admin_ajouter)
                ]
            },
            fallbacks=[
                CallbackQueryHandler(self.owner_handlers.cancel_admin_add, pattern="^cancel_admin_add$"),
                CommandHandler("stop", self.owner_handlers.cancel_admin_add),
            ],
            allow_reentry=True,
            per_user=True,
        )

        # Révocation d'admin par l'Owner
        remove_admin_conv = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(
                    self.owner_handlers.admin_supprimer,
                    pattern="^admin_supprimer$",
                )
            ],
            states={
                self.owner_handlers.WAITING_ADMIN_REMOVE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.owner_handlers.traiter_admin_supprimer)
                ],
                self.owner_handlers.WAITING_CONFIRMATION: [
                    CallbackQueryHandler(
                        self.owner_handlers.confirmer_admin_suppression,
                        pattern="^confirm_admin_remove$",
                    )
                ],
            },
            fallbacks=[
                CallbackQueryHandler(self.owner_handlers.cancel_admin_remove, pattern="^cancel_admin_remove$"),
                CommandHandler("stop", self.owner_handlers.cancel_admin_remove),
            ],
            allow_reentry=True,
            per_user=True,
        )

        # Promotion VIP par l'Owner
        add_vip_conv = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(
                    self.owner_handlers.start_add_vip,
                    pattern="^owner_add_vip$",
                )
            ],
            states={
                self.owner_handlers.WAITING_VIP_USER: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.owner_handlers.process_vip_target_user)
                ],
                self.owner_handlers.WAITING_VIP_DURATION: [
                    CallbackQueryHandler(self.owner_handlers.process_vip_duration_choice, pattern=r"^vip_dur_.*$"),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.owner_handlers.process_vip_duration_choice),
                ],
            },
            fallbacks=[
                CallbackQueryHandler(self.owner_handlers.cancel_vip_action, pattern="^cancel_vip_action$"),
                CommandHandler("stop", self.owner_handlers.cancel_vip_action),
            ],
            allow_reentry=True,
            per_user=True,
        )

        # Révocation VIP par l'Owner
        remove_vip_conv = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(
                    self.owner_handlers.start_remove_vip,
                    pattern="^owner_remove_vip$",
                )
            ],
            states={
                self.owner_handlers.WAITING_VIP_REMOVE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.owner_handlers.process_vip_remove_choice)
                ]
            },
            fallbacks=[
                CallbackQueryHandler(self.owner_handlers.cancel_vip_action, pattern="^cancel_vip_action$"),
                CommandHandler("stop", self.owner_handlers.cancel_vip_action),
            ],
            allow_reentry=True,
            per_user=True,
        )

        return [
            demande_handler,
            modify_alias_conv,
            contact_owner_conv,
            owner_reply_conv,
            add_admin_conv,
            remove_admin_conv,
            add_vip_conv,
            remove_vip_conv,
        ]

    def setup_application(self) -> Application:
        """Configure et câble tous les handlers du bot."""
        builder = Application.builder().token(self.config.BOT_TOKEN)
        if self.request:
            builder = builder.request(self.request)

        app = builder.build()
        app.bot_data["db_manager"] = self.db_manager
        app.bot_data["config"] = self.config
        app.bot_data["user_handlers"] = self.user_handlers

        for handler in self.create_conversation_handlers():
            app.add_handler(handler)

        app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
        app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))

        app.add_handler(CommandHandler("start", self.user_handlers.start))
        app.add_handler(CommandHandler("demandes", self.user_handlers.voir_demandes))
        app.add_handler(CommandHandler("toggle_demandes", self.owner_handlers.toggle_demandes))
        app.add_handler(CommandHandler("maintenance", self.owner_handlers.run_maintenance))

        app.add_handler(CallbackQueryHandler(
            self.owner_handlers.handle_owner_callbacks,
            pattern=r"^(perm_admin_.*|set_perm_.*|bot_on|bot_off|confirm_bot_off|cancel_bot_off|maintenance|bot_stats|gerer_vips)$",
        ))

        # ⚡ AJOUT DE status_.* ICI POUR RÉCEPTIONNER LES BOUTONS DU MENU DE STATUT
        app.add_handler(CallbackQueryHandler(
            self.admin_handlers.handle_admin_callbacks,
            pattern=r"^(demandes_disponibles|dispo_.*|demandes_suivies|suivi_.*|mark_treated_menu_.*|change_status_.*|set_status_.*|status_.*|voir_photo_.*|retour_texte_.*|suivre_demande_.*|contacter_.*|contact_mode_.*|cancel_contact_.*|send_batch_.*|menu_notifs|pref_.*|profil_.*|admin_pause_.*|admin_resume)$",
        ))

        app.add_handler(CallbackQueryHandler(
            self.user_handlers.handle_interface_callbacks,
            pattern=r"^(voir_demandes|start_menu|gerer_demandes|parametres|modifier_alias|gerer_admins|gerer_bot|menu_limits|limit_.*)$",
        ))

        app.add_handler(CallbackQueryHandler(
            self.user_handlers.handle_callbacks,
            pattern=r"^(nav_.*|modify_.*|edit_.*|delete_.*|confirm_delete_.*|cancel_demande_.*|form_.*|cancel_edit|reply_to_admin_.*|cancel_user_reply|quota_reached_info|reprendre_demande_.*|archiver_demande_.*|menu_vip_shop|buy_vip_.*|remind_admin_free_.*|remind_admin_pay_.*|vip_contact_admin_.*|vip_assign_admin_.*)$",
        ))

        app.add_handler(MessageHandler(
            (filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL) & ~filters.COMMAND,
            self.user_handlers.handle_text_messages,
        ))

        if app.job_queue:
            app.job_queue.run_repeating(
                check_and_send_admin_reminders,
                interval=3600,
                first=15,
                data={"db_manager": self.db_manager},
            )
            logger.info("⏰ JobQueue activée : vérification des rappels admins toutes les 3600s.")

        async def post_init(application: Application):
            await self.setup_bot_commands(application)

        app.post_init = post_init
        return app

    def run(self):
        """Démarre le bot en mode polling local."""
        app = self.setup_application()
        logger.info("🚀 Bot Telegram démarré avec succès (mode polling local)")
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
        config.set_db_manager(db_manager)
        logger.info("Admins chargés au démarrage : %s", config.admin_ids)

        if not config.admin_ids:
            logger.warning("⚠️ Aucun admin trouvé au démarrage !")

        logger.info("3. Démarrage de l'application...")
        bot = TelegramBot(config, db_manager)
        bot.run()

    except Exception as e:
        logger.critical("Erreur critique au démarrage : %s", e, exc_info=True)
        sys.exit(1)