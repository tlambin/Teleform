#!/usr/bin/env python3
"""Point d'entrée principal de l'application Telegram avec architecture RBAC (Client, Staff, Admin, Owner)."""

import asyncio
from datetime import datetime
import html
import logging
from logging.handlers import RotatingFileHandler
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
    PreCheckoutQueryHandler,
    filters,
)

from config import Config
from database import DatabaseManager
from handlers.admin_handlers import AdminHandlers
from handlers.staff_handlers import StaffHandlers
from handlers.user_handlers import UserHandlers
from utils.interface_manager import InterfaceManager
from utils.session import clear_transient_user_data

# ==================== CONFIGURATION DES LOGS (ROTATION DISQUE) ====================
log_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "bot.log")

rotating_handler = RotatingFileHandler(
    log_file,
    maxBytes=2 * 1024 * 1024,
    backupCount=4,
    encoding="utf-8",
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
    """Vérifie la possibilité d'écrire dans le fichier de log rotatif."""
    try:
        with open(log_file, "a", encoding="utf-8"):
            pass
        logger.info("Permissions logs vérifiées avec rotation active (2 Mo x 4) : %s", log_file)
        return True
    except Exception as exc:
        logger.warning("Erreur accès logs fichier (%s). Bascule sur console uniquement.", exc)
        return True


# ==================== GESTIONNAIRE D'ERREURS GLOBAL PTB ====================

async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Capture proprement toutes les exceptions non gérées pour éviter la pollution des logs et crashs."""
    err = context.error

    # 1. Utilisateur ayant bloqué le bot ou compte supprimé
    if isinstance(err, Forbidden):
        target = "inconnu"
        if isinstance(update, Update) and update.effective_user:
            target = f"{update.effective_user.id} (@{update.effective_user.username or 'sans_tag'})"
        logger.warning("🚫 Action ignorée : le bot a été bloqué par l'utilisateur %s.", target)
        return

    # 2. Requêtes Telegram obsolètes ou messages identiques
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

    # 3. Problèmes temporaires réseau / timeouts Telegram
    if isinstance(err, (TimedOut, NetworkError)):
        logger.warning("🌐 Incident réseau passager Telegram : %s", err)
        return

    # 4. Conflit d'instances (si un polling et un webhook tournent en même temps)
    if isinstance(err, Conflict):
        logger.critical("💥 Conflit de polling détecté (une autre instance utilise ce token) : %s", err)
        return

    # 5. Erreurs applicatives non gérées (stacktrace complète)
    update_id = update.update_id if isinstance(update, Update) else "N/A"
    logger.error("💥 Exception non interceptée lors de l'update #%s : %s", update_id, err, exc_info=err)

    # Réponse polie à l'utilisateur si possible
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "⚠️ <b>Une erreur technique inattendue est survenue.</b>\n"
                "L'équipe technique a été informée. Tapez /start pour réinitialiser le menu.",
                parse_mode="HTML"
            )
        except Exception:
            pass


# ==================== TÂCHES DE DIFFUSION PARALLÉLISÉES ====================

async def _send_single_admin_reminder(context: ContextTypes.DEFAULT_TYPE, db_manager, user_id: int, active_demandes: list, is_silent: bool):
    """Envoi unitaire sécurisé d'un rappel au staff."""
    count = len(active_demandes)
    lines = [
        f"⏰ <b>Rappel de vos demandes suivies ({count})</b>\n",
        "Voici les demandes en attente sous votre responsabilité :",
    ]
    for d in active_demandes[:8]:
        prenom_esc = html.escape(str(d.get("prenom") or "Inconnu"))
        nom_esc = html.escape(str(d.get("nom") or ""))
        nom_aff = f"{prenom_esc} {nom_esc}".strip()
        num = html.escape(str(d.get("request_number") or d["id"]))
        statut_esc = html.escape(str(d.get("statut") or "En cours"))
        lines.append(f"• <b>#{num}</b> - {nom_aff} (<code>{statut_esc}</code>)")

    if count > 8:
        lines.append(f"\n<i>... et {count - 8} autre(s) demande(s).</i>")

    text_rappel = "\n".join(lines)
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("💌 MES SUIVIS 💌", callback_data="demandes_suivies")
    ]])

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=text_rappel,
            parse_mode="HTML",
            reply_markup=keyboard,
            disable_notification=is_silent,
        )
        db_manager.mark_admin_reminder_sent(user_id)
        logger.info("Rappel automatique envoyé au staff %s (silencieux: %s)", user_id, is_silent)
    except Forbidden:
        logger.warning("Rappel staff non remis : l'opérateur %s a bloqué le bot.", user_id)
    except Exception as err:
        logger.warning("Erreur envoi rappel programmé au staff %s : %s", user_id, err)


async def check_and_send_admin_reminders(context: ContextTypes.DEFAULT_TYPE):
    """Vérifie chaque heure si des opérateurs doivent recevoir un rappel et les diffuse en parallèle."""
    db_manager = context.application.bot_data.get("db_manager")
    if not db_manager:
        logger.warning("Vérification des rappels abandonnée : db_manager introuvable.")
        return

    now_paris = datetime.now(PARIS_TZ)
    current_hour = now_paris.hour
    current_weekday = now_paris.weekday()
    current_monthday = now_paris.day
    today_date = now_paris.date()

    admin_prefs_list = db_manager.get_all_admin_preferences()
    tasks = []

    for pref in admin_prefs_list:
        user_id = pref["user_id"]

        if db_manager.is_staff_paused(user_id):
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

            if active_demandes:
                is_silent = (rappel_mode == "silent")
                tasks.append(_send_single_admin_reminder(context, db_manager, user_id, active_demandes, is_silent))
        except Exception as db_err:
            logger.error("Erreur lecture suivis pour rappel staff %s : %s", user_id, db_err)

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


async def check_and_auto_archive_demandes(context: ContextTypes.DEFAULT_TYPE):
    """Archive automatiquement les demandes terminées et livrées selon le délai configuré."""
    db_manager = context.application.bot_data.get("db_manager")
    if not db_manager:
        return

    try:
        hours = db_manager.get_auto_archive_hours()
        expired_demandes = db_manager.get_expired_delivered_demandes(hours=hours)
        for dem in expired_demandes:
            dem_id = dem["id"]
            req_num = dem.get("request_number") or dem_id
            if db_manager.archiver_demande_reussie(dem_id):
                logger.info("📦 Demande #%s archivée automatiquement après %sh post-livraison.", req_num, hours)
    except Exception as exc:
        logger.error("Erreur exécution auto-archivage : %s", exc)


async def _send_single_delivery_reminder(context: ContextTypes.DEFAULT_TYPE, db_manager, dem: dict, days: int):
    """Envoi unitaire sécurisé d'un rappel de livraison à un opérateur."""
    admin_id = dem["admin_id"]
    dem_id = dem["id"]
    req_num = html.escape(str(dem.get("request_number") or dem_id))
    prenom = html.escape(str(dem.get("prenom") or "la cible"))

    msg = (
        f"⚠️ <b>Rappel de livraison (Demande #{req_num})</b>\n\n"
        f"Le dossier concernant <b>{prenom}</b> est passé en <b>✅ Réussie (Terminée)</b> "
        f"depuis plus de {days} jours, mais <b>aucun contenu n'a encore été transmis</b> au demandeur.\n\n"
        "👉 Pensez à lui envoyer ses fichiers afin de finaliser la prestation et débloquer l'archivage du dossier."
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 TRANSMETTRE LE CONTENU 💬", callback_data=f"contacter_{dem_id}")],
        [InlineKeyboardButton("📋 OUVRIR MES SUIVIS 📋", callback_data="demandes_suivies")]
    ])

    try:
        await context.bot.send_message(
            chat_id=admin_id,
            text=msg,
            parse_mode="HTML",
            reply_markup=kb,
        )
        db_manager.mark_delivery_reminder_sent(dem_id)
        logger.info("Rappel de livraison (%sj) envoyé au staff %s pour la demande #%s", days, admin_id, req_num)
    except Forbidden:
        logger.warning("Rappel livraison non remis : le staff %s a bloqué le bot.", admin_id)
    except Exception as notif_err:
        logger.warning("Impossible d'envoyer le rappel de livraison à %s : %s", admin_id, notif_err)


async def check_and_send_delivery_reminders(context: ContextTypes.DEFAULT_TYPE):
    """Envoie en parallèle un rappel aux opérateurs pour les demandes terminées sans livraison."""
    db_manager = context.application.bot_data.get("db_manager")
    if not db_manager:
        return

    try:
        days = db_manager.get_delivery_reminder_days()
        undelivered = db_manager.get_undelivered_terminee_demandes_for_reminder(days=days)
        tasks = [_send_single_delivery_reminder(context, db_manager, dem, days) for dem in undelivered]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as exc:
        logger.error("Erreur lors de la vérification des rappels de livraison : %s", exc)


async def _send_single_paid_delivery_reminder(context: ContextTypes.DEFAULT_TYPE, db_manager, dem: dict):
    """Envoi unitaire sécurisé d'une relance pour livraison post-paiement."""
    admin_id = dem["admin_id"]
    dem_id = dem["id"]
    req_num = html.escape(str(dem.get("request_number") or dem_id))
    prenom = html.escape(str(dem.get("prenom") or "la cible"))
    montant = float(dem.get("montant") or 0.0)

    msg = (
        f"🚨 <b>RAPPEL QUOTIDIEN : Paiement reçu sans livraison (#{req_num})</b>\n\n"
        f"Le client a validé le règlement de sa demande prioritaire pour <b>{prenom}</b> ({montant:.2f} €).\n\n"
        "👉 <b>Le contenu obtenu n'a toujours pas été transmis au client.</b>\n"
        "Merci de lui envoyer les fichiers sans attendre pour clore la prestation."
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 TRANSMETTRE LES FICHIERS MAINTENANT 💬", callback_data=f"contacter_{dem_id}")],
        [InlineKeyboardButton("📋 OUVRIR MES SUIVIS 📋", callback_data="demandes_suivies")]
    ])

    try:
        await context.bot.send_message(
            chat_id=admin_id,
            text=msg,
            parse_mode="HTML",
            reply_markup=kb,
        )
        db_manager.mark_payment_delivery_reminder_sent(dem_id)
        logger.info("Relance quotidienne livraison post-paiement envoyée à %s pour #%s", admin_id, req_num)
    except Forbidden:
        logger.warning("Relance livraison payée non remise : le staff %s a bloqué le bot.", admin_id)
    except Exception as err:
        logger.warning("Erreur relance livraison payée à %s : %s", admin_id, err)


async def check_and_send_paid_delivery_reminders(context: ContextTypes.DEFAULT_TYPE):
    """Rappel quotidien en parallèle aux opérateurs pour les demandes payées non livrées."""
    db_manager = context.application.bot_data.get("db_manager")
    if not db_manager:
        return

    try:
        paid_undelivered = db_manager.get_paid_undelivered_demandes_for_reminder()
        tasks = [_send_single_paid_delivery_reminder(context, db_manager, dem) for dem in paid_undelivered]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as exc:
        logger.error("Erreur lors de la vérification des rappels de livraison payée : %s", exc)


async def _send_single_unpaid_demande_reminder(context: ContextTypes.DEFAULT_TYPE, db_manager, dem: dict):
    """Envoi unitaire sécurisé d'une relance d'impayé au client."""
    user_id = dem["user_id"]
    dem_id = dem["id"]
    req_num = html.escape(str(dem.get("request_number") or dem_id))
    prenom = html.escape(str(dem.get("prenom") or "votre contact"))
    montant = float(dem.get("montant") or 0.0)
    stars_amount = max(1, int(montant * 50))

    msg = (
        f"🔔 <b>Rappel : Règlement de votre demande #{req_num}</b>\n\n"
        f"La prestation concernant <b>{prenom}</b> est terminée avec succès ({montant:.2f} €).\n\n"
        "👉 <b>Votre règlement est en attente :</b>\n"
        "Dès confirmation de votre paiement, votre référent vous transmettra l'ensemble des contenus obtenus."
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"⭐ RÉGLER EN STARS ({stars_amount} ⭐) ⭐", callback_data=f"pay_stars_prio_{dem_id}")],
        [InlineKeyboardButton("💬 CONVENIR D'UN AUTRE PAIEMENT 💬", callback_data=f"pay_contact_prio_{dem_id}")],
        [InlineKeyboardButton("🗂️ MES DEMANDES 🗂️", callback_data="voir_demandes")]
    ])

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=msg,
            parse_mode="HTML",
            reply_markup=kb,
        )
        db_manager.mark_user_payment_reminder_sent(dem_id)
        logger.info("Rappel d'impayé envoyé au demandeur %s pour le dossier #%s", user_id, req_num)
    except Forbidden:
        logger.warning("Rappel impayé non remis : le demandeur %s a bloqué le bot.", user_id)
    except Exception as notif_err:
        logger.warning("Impossible d'envoyer le rappel d'impayé au client %s : %s", user_id, notif_err)


async def check_and_send_unpaid_demande_reminders(context: ContextTypes.DEFAULT_TYPE):
    """Rappel automatique en parallèle aux demandeurs pour les demandes réussies en attente de paiement."""
    db_manager = context.application.bot_data.get("db_manager")
    if not db_manager:
        return

    try:
        unpaid = db_manager.get_unpaid_reussie_demandes_for_reminder()
        tasks = [_send_single_unpaid_demande_reminder(context, db_manager, dem) for dem in unpaid]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as exc:
        logger.error("Erreur vérification rappels d'impayés demandeurs : %s", exc)


async def _process_single_remun_abandon(context: ContextTypes.DEFAULT_TYPE, db_manager, dem: dict, days: int):
    """Traite l'archivage et les notifications associées pour une demande de rémunération expirée."""
    dem_id = dem["id"]
    user_id = dem["user_id"]
    req_num = html.escape(str(dem.get("request_number") or dem_id))
    prenom = html.escape(str(dem.get("prenom") or "la cible"))
    staff_id = dem.get("proposed_by")

    raison = f"Délai expiré : absence de réponse à la demande de rémunération ({days} jours)"
    archived = db_manager.archiver_demande_annulee(demande_id=dem_id, raison=raison)

    if archived:
        logger.info("❌ Demande #%s abandonnée automatiquement pour délai de rémunération expiré (%sj).", req_num, days)

        try:
            msg_client = (
                f"❌ <b>Dossier #{req_num} abandonné et clôturé</b>\n\n"
                f"Votre demande concernant <b>{prenom}</b> a été clôturée automatiquement suite à l'absence de réponse "
                f"à la proposition de rémunération sous un délai de {days} jours.\n\n"
                "Votre quota de demandes actives a été libéré."
            )
            await context.bot.send_message(
                chat_id=user_id,
                text=msg_client,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🗂️ MES DEMANDES 🗂️", callback_data="voir_demandes")
                ]])
            )
        except Forbidden:
            logger.warning("Notification abandon non remise au client %s (bot bloqué).", user_id)
        except Exception as notif_user_err:
            logger.warning("Impossible de notifier le client %s de l'abandon de rémunération : %s", user_id, notif_user_err)

        if staff_id:
            try:
                msg_staff = (
                    f"ℹ️ <b>Dossier #{req_num} clôturé pour expiration ({days}j)</b>\n\n"
                    f"Le client n'a pas répondu à votre proposition de rémunération concernant <b>{prenom}</b> dans le délai imparti.\n"
                    "Le dossier a été clôturé et archivé sous « ❌ Abandonnée »."
                )
                await context.bot.send_message(
                    chat_id=staff_id,
                    text=msg_staff,
                    parse_mode="HTML"
                )
            except Forbidden:
                logger.warning("Notification abandon non remise au staff %s (bot bloqué).", staff_id)
            except Exception as notif_staff_err:
                logger.warning("Impossible de notifier le staff %s de l'abandon de rémunération : %s", staff_id, notif_staff_err)


async def check_and_auto_abandon_expired_remun_demandes(context: ContextTypes.DEFAULT_TYPE):
    """Archive en parallèle les demandes dont la proposition de rémunération a expiré sans réponse."""
    db_manager = context.application.bot_data.get("db_manager")
    if not db_manager:
        return

    try:
        days = db_manager.get_remun_expiration_days()
        expired = db_manager.get_expired_remun_demandes_for_abandon(days=days)
        tasks = [_process_single_remun_abandon(context, db_manager, dem, days) for dem in expired]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as exc:
        logger.error("Erreur lors de la vérification de l'abandon automatique pour délai de rémunération : %s", exc)


# ==================== HANDLERS TELEGRAM STARS ====================

async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Valide les commandes Stars (abonnements VIP, relances ou paiements prioritaires)."""
    query = update.pre_checkout_query
    payload = query.invoice_payload

    if payload.startswith(("vip_sub_", "remind_pay_", "prio_pay_")):
        await query.answer(ok=True)
    else:
        await query.answer(ok=False, error_message="Erreur de validation de la transaction.")


async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère l'activation des achats Stars confirmés (VIP, Relances, Prestations prioritaires)."""
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
            "• 💬 <b>Ligne directe</b> avec l'opérateur en charge de vos demandes\n"
            "• 🔔 <b>Relance prioritaire hebdomadaire gratuite</b> sur chacune de vos fiches\n\n"
            "Merci pour votre confiance !"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🗳️ CRÉER UNE DEMANDE VIP 🗳️", callback_data="new_demande")],
            [InlineKeyboardButton("🔙 MENU PRINCIPAL 🔙", callback_data="start_menu")]
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

    # Cas 3 : Règlement de la prestation prioritaire
    elif payload.startswith("prio_pay_"):
        parts = payload.split("_")
        demande_id = int(parts[2])

        db_manager.set_demande_paiement_statut(demande_id, "paye")

        with db_manager.get_cursor() as cursor:
            cursor.execute(
                "SELECT request_number, prenom, admin_en_charge, montant FROM demandes WHERE id = %s",
                (demande_id,)
            )
            dem = cursor.fetchone()

        req_num = html.escape(str(dem.get("request_number", demande_id) if dem else demande_id))
        prenom_cible = html.escape(str(dem.get("prenom", "") if dem else ""))

        merci_msg = (
            f"🎉 <b>Paiement reçu avec succès pour la demande #{req_num} !</b>\n\n"
            "Votre règlement en Stars a été validé. Votre référent a été averti et va procéder "
            "à la transmission de vos contenus dans les plus brefs délais."
        )
        await update.message.reply_text(
            merci_msg,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📋 CONSULTER MES DEMANDES 📋", callback_data="voir_demandes")
            ]])
        )

        if dem and dem.get("admin_en_charge"):
            admin_id = dem["admin_en_charge"]
            montant = float(dem.get("montant") or 0.0)
            admin_alert = (
                f"💰 <b>RÈGLEMENT CONFIRMÉ (Demande #{req_num})</b>\n\n"
                f"Le client a réglé la prestation prioritaire pour <b>{prenom_cible}</b> ({montant:.2f} €) via Stars Telegram.\n\n"
                "👉 Vous pouvez désormais transmettre les fichiers obtenus au client."
            )
            alert_kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("💬 TRANSMETTRE LE CONTENU MAINTENANT 💬", callback_data=f"contacter_{demande_id}")],
                [InlineKeyboardButton("💌 OUVRIR MES SUIVIS 💌", callback_data="demandes_suivies")]
            ])
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=admin_alert,
                    parse_mode="HTML",
                    reply_markup=alert_kb,
                )
            except Forbidden:
                logger.warning("Alerte règlement non remise au staff %s (bot bloqué).", admin_id)
            except Exception as notif_err:
                logger.warning("Impossible d'avertir l'opérateur %s du paiement Stars : %s", admin_id, notif_err)

        logger.info("Prestation prioritaire #%s payée via Stars par l'utilisateur %s", demande_id, user_id)


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
        """Wrapper pour la commande /start purgeant automatiquement les états temporaires orphelins."""
        user_id = update.effective_user.id
        if self.db_manager.is_user_banned(user_id):
            await update.message.reply_text("🚫 <b>Votre compte a été banni par l'administration.</b>", parse_mode="HTML")
            return
        clear_transient_user_data(context)
        return await self.user_handlers.start(update, context)

    async def wrapped_stop_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Commande /stop réinitialisant immédiatement la session active de l'utilisateur."""
        clear_transient_user_data(context)
        msg = (
            "🛑 <b>Opération interrompue</b>\n\n"
            "Toutes vos saisies temporaires en cours ont été annulées.\n"
            "Tapez /start ou cliquez ci-dessous pour revenir au menu d'accueil."
        )
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🏠 MENU PRINCIPAL 🏠", callback_data="start_menu")]])
        if update.message:
            await update.message.reply_text(msg, parse_mode="HTML", reply_markup=kb)

    async def wrapped_interface_callbacks(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Wrapper des callbacks de navigation d'interface purgeant les états temporaires lors des retours."""
        query = update.callback_query
        if query and query.data in ("start_menu", "parametres", "gerer_demandes", "menu_membres", "menu_mon_profil"):
            clear_transient_user_data(context)
        return await self.user_handlers.handle_interface_callbacks(update, context)

    async def wrapped_user_callbacks(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Wrapper des callbacks utilisateurs purgeant les flux d'annulation explicites."""
        query = update.callback_query
        if query and query.data in ("form_cancel", "cancel_edit", "cancel_user_reply"):
            clear_transient_user_data(context)
        return await self.user_handlers.handle_callbacks(update, context)

    async def setup_bot_commands(self, app: Application):
        """Configure les commandes visibles selon les rôles."""
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
        """Crée les ConversationHandlers du bot."""
        demande_handler = self.user_handlers.formulaire.get_conversation_handler()

        modify_alias_conv = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(
                    self.staff_handlers.alias.modifier_alias,
                    pattern=r"^modifier_alias$",
                )
            ],
            states={
                self.staff_handlers.alias.WAITING_ALIAS: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.staff_handlers.alias.traiter_nouveau_alias)
                ]
            },
            fallbacks=[
                CallbackQueryHandler(self.staff_handlers.alias.cancel_alias_change, pattern="^cancel_alias_change$"),
                CommandHandler("stop", self.staff_handlers.alias.cancel_alias_change),
            ],
            allow_reentry=True,
            per_user=True,
        )

        contact_owner_conv = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(
                    self.staff_handlers.contact.start_contact_owner,
                    pattern=r"^contacter_owner$",
                )
            ],
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
            allow_reentry=True,
            per_user=True,
        )

        owner_reply_conv = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(
                    self.staff_handlers.contact.start_owner_reply,
                    pattern=r"^owner_reply_to_\d+$",
                )
            ],
            states={
                self.staff_handlers.contact.WAITING_OWNER_REPLY: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.staff_handlers.contact.send_owner_reply
                    )
                ]
            },
            fallbacks=[
                CallbackQueryHandler(self.staff_handlers.contact.cancel_owner_reply, pattern="^cancel_owner_reply$"),
                CommandHandler("stop", self.staff_handlers.contact.cancel_owner_reply),
            ],
            allow_reentry=True,
            per_user=True,
        )

        add_staff_conv = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(
                    self.admin_handlers.staff_ajouter,
                    pattern=r"^staff_ajouter$",
                )
            ],
            states={
                self.admin_handlers.WAITING_STAFF_ID: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.admin_handlers.traiter_staff_ajouter)
                ],
                self.admin_handlers.WAITING_STAFF_CONFIG: [
                    CallbackQueryHandler(
                        self.admin_handlers.handle_recruit_config_callback,
                        pattern=r"^cfgadd_.*$"
                    )
                ],
            },
            fallbacks=[
                CallbackQueryHandler(self.admin_handlers.cancel_staff_add, pattern="^cancel_staff_add$"),
                CommandHandler("stop", self.admin_handlers.cancel_staff_add),
            ],
            allow_reentry=True,
            per_user=True,
        )

        remove_staff_conv = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(
                    self.admin_handlers.staff_supprimer,
                    pattern=r"^staff_supprimer$",
                )
            ],
            states={
                self.admin_handlers.WAITING_STAFF_REMOVE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.admin_handlers.traiter_staff_supprimer)
                ],
                self.admin_handlers.WAITING_STAFF_CONFIRMATION: [
                    CallbackQueryHandler(
                        self.admin_handlers.confirmer_staff_suppression,
                        pattern=r"^confirm_staff_remove$",
                    )
                ],
            },
            fallbacks=[
                CallbackQueryHandler(self.admin_handlers.cancel_staff_remove, pattern="^cancel_staff_remove$"),
                CommandHandler("stop", self.admin_handlers.cancel_staff_remove),
            ],
            allow_reentry=True,
            per_user=True,
        )

        add_admin_conv = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(
                    self.admin_handlers.admin_ajouter,
                    pattern=r"^admin_ajouter$",
                )
            ],
            states={
                self.admin_handlers.WAITING_ADMIN_ID: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.admin_handlers.traiter_admin_ajouter)
                ]
            },
            fallbacks=[
                CallbackQueryHandler(self.admin_handlers.cancel_admin_add, pattern="^cancel_admin_add$"),
                CommandHandler("stop", self.admin_handlers.cancel_admin_add),
            ],
            allow_reentry=True,
            per_user=True,
        )

        remove_admin_conv = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(
                    self.admin_handlers.admin_supprimer,
                    pattern=r"^admin_supprimer$",
                )
            ],
            states={
                self.admin_handlers.WAITING_ADMIN_REMOVE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.admin_handlers.traiter_admin_supprimer)
                ],
                self.admin_handlers.WAITING_ADMIN_CONFIRMATION: [
                    CallbackQueryHandler(
                        self.admin_handlers.confirmer_admin_suppression,
                        pattern=r"^confirm_admin_remove$",
                    )
                ],
            },
            fallbacks=[
                CallbackQueryHandler(self.admin_handlers.cancel_admin_remove, pattern="^cancel_admin_remove$"),
                CommandHandler("stop", self.admin_handlers.cancel_admin_remove),
            ],
            allow_reentry=True,
            per_user=True,
        )

        add_vip_conv = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(
                    self.admin_handlers.start_add_vip,
                    pattern=r"^owner_add_vip$",
                )
            ],
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
            allow_reentry=True,
            per_user=True,
        )

        remove_vip_conv = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(
                    self.admin_handlers.start_remove_vip,
                    pattern=r"^owner_remove_vip$",
                )
            ],
            states={
                self.admin_handlers.WAITING_VIP_REMOVE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.admin_handlers.process_vip_remove_choice)
                ]
            },
            fallbacks=[
                CallbackQueryHandler(self.admin_handlers.cancel_vip_action, pattern="^cancel_vip_action$"),
                CommandHandler("stop", self.admin_handlers.cancel_vip_action),
            ],
            allow_reentry=True,
            per_user=True,
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
        """Traite les modifications de préférences de cibles avec actualisation visuelle immédiate."""
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

        # 1. Enregistrement de la nouvelle valeur
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

        # 2. Invalidation totale du cache local
        self.db_manager.clear_cache()

        # 3. Récupération du menu avec les coches actualisées
        text, kb = self.interface.get_staff_self_preferences_menu(user_id)

        # 4. Forçage du rafraîchissement avec gestion d'exception
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

        # Commandes textuelles privées avec nettoyage de session
        app.add_handler(CommandHandler("start", self.wrapped_start_command, filters=filters.ChatType.PRIVATE))
        app.add_handler(CommandHandler("stop", self.wrapped_stop_command, filters=filters.ChatType.PRIVATE))
        app.add_handler(CommandHandler("demandes", self.user_handlers.voir_demandes, filters=filters.ChatType.PRIVATE))
        app.add_handler(CommandHandler("archives", lambda u, c: self.staff_handlers.archives.show_archives(u, c, page=0), filters=filters.ChatType.PRIVATE))
        app.add_handler(CommandHandler("toggle_demandes", self.admin_handlers.toggle_demandes, filters=filters.ChatType.PRIVATE))
        app.add_handler(CommandHandler("maintenance", self.admin_handlers.run_maintenance, filters=filters.ChatType.PRIVATE))

        # 1. Clics des préférences autonomes du membre (en tête de liste absolue)
        app.add_handler(CallbackQueryHandler(
            self.handle_self_pref_callback,
            pattern=r"^self_pref_.*$",
        ))

        # 2. Aiguillage Gouvernance & Administration (Admin/Owner + Délais + Zone de Danger + Dossiers Piégeurs + Purge Config + Membres + Bannissements)
        app.add_handler(CallbackQueryHandler(
            self.admin_handlers.handle_admin_callbacks,
            pattern=r"^(bot_on|bot_off|confirm_bot_off|cancel_bot_off|maintenance|bot_stats|admin_global_archives|global_arch_page_.*|menu_membres|search_member_prompt|liste_bannis_.*|ban_prompt_.*|unban_.*|gerer_vips|gerer_staff|staff_view_demandes_.*|admin_remind_staff_demande_.*|gerer_admins|menu_channels|toggle_allow_.*|menu_delais|cfg_sub_.*|set_arch_.*|set_rem_.*|set_payrem_.*|set_remun_days_.*|perm_staff_.*|set_permstaff_.*|perm_admin_.*|set_permadmin_.*|menu_cfg_group|toggle_cfg_group_enabled|set_cfg_group_id|set_cfg_group_link|menu_cfg_support|set_cfg_support_contact|menu_danger_zone|danger_purge_.*|danger_confirm_yes_.*|toggle_pay_staff_.*|unarchive_reussie_.*|unarchive_abandon_.*|contacter_archive_.*)$",
        ))

        # 3. Aiguillage Traitement opérationnel des dossiers (Staff) & Démission
        app.add_handler(CallbackQueryHandler(
            self.staff_handlers.handle_staff_callbacks,
            pattern=r"^(demandes_disponibles|dispo_.*|dispo_remun_pending_info|admin_del_dispo_.*|dispo_ask_remun_.*|staff_report_dispo_.*|demandes_suivies|suivi_.*|confirm_payment_prio_.*|confirm_payment_prio_exec_.*|vip_accept_.*|vip_decline_.*|demandes_archives|archive_page_.*|mark_treated_menu_.*|change_status_.*|set_status_.*|status_.*|voir_photo_.*|retour_texte_.*|suivre_demande_.*|contacter_.*|contact_mode_.*|toggle_contact_content_.*|contact_close_conv_.*|cancel_contact_.*|send_batch_.*|menu_notifs|pref_.*|menu_surveillance_notifs|toggle_mon_.*|profil_.*|staff_list_.*|user_view_demandes_.*|user_list_.*|archive_view_.*|admin_contact_staff_.*|admin_pause_.*|admin_resume|menu_demission|demission_confirm_.*|demission_exec_.*)$",
        ))

        # 4. Menus d'interface et navigation avec purge de session
        app.add_handler(CallbackQueryHandler(
            self.wrapped_interface_callbacks,
            pattern=r"^(voir_demandes|start_menu|gerer_demandes|parametres|menu_mon_profil|menu_demission|staff_self_prefs|staff_payment_settings|modifier_alias|gerer_admins|gerer_staff|gerer_bot|bot_toggle_suspension|menu_danger_zone|menu_channels|menu_limits|menu_cfg_group|menu_cfg_support|menu_membres|limit_.*|stat_access_denied|arch_access_denied)$",
        ))

        # 5. Callbacks utilisateurs / clients avec purge de session sur les annulations
        app.add_handler(CallbackQueryHandler(
            self.wrapped_user_callbacks,
            pattern=r"^(check_subscription|nav_.*|mes_archives|user_arch_page_.*|modify_.*|edit_.*|delete_.*|confirm_delete_.*|cancel_demande_.*|form_.*|cancel_edit|reply_to_admin_.*|cancel_user_reply|quota_reached_info|reprendre_demande_.*|archiver_demande_.*|menu_vip_shop|buy_vip_.*|menu_vip_settings|vip_set_assign_.*|vip_pick_auto_staff|remind_admin_free_.*|remind_admin_pay_.*|vip_contact_admin_.*|vip_assign_admin_.*|ask_cancel_demande_.*|accept_cancel_.*|refuse_cancel_.*|contact_admin_.*|upgrade_prio_.*|pay_stars_prio_.*|pay_contact_prio_.*|user_accept_remun_.*|user_refuse_remun_.*)$",
        ))

        # Réception des messages & médias privés (avec confirmation de purge et envoi direct / lot)
        app.add_handler(MessageHandler(
            filters.ChatType.PRIVATE & ((filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL) & ~filters.COMMAND),
            self.handle_incoming_messages,
        ))

        # Gestionnaire global d'erreurs (add_error_handler)
        app.add_error_handler(global_error_handler)

        # Tâches d'arrière-plan JobQueue
        if app.job_queue:
            app.job_queue.run_repeating(
                check_and_send_admin_reminders,
                interval=3600,
                first=15,
            )
            app.job_queue.run_repeating(
                check_and_auto_archive_demandes,
                interval=3600,
                first=30,
            )
            app.job_queue.run_repeating(
                check_and_send_delivery_reminders,
                interval=21600,
                first=45,
            )
            app.job_queue.run_repeating(
                check_and_send_paid_delivery_reminders,
                interval=86400,
                first=60,
            )
            app.job_queue.run_repeating(
                check_and_send_unpaid_demande_reminders,
                interval=21600,
                first=75,
            )
            app.job_queue.run_repeating(
                check_and_auto_abandon_expired_remun_demandes,
                interval=21600,
                first=90,
            )
            logger.info("⏰ Tâches JobQueue configurées et actives.")

        async def post_init(application: Application):
            await self.setup_bot_commands(application)

        app.post_init = post_init
        return app

    async def handle_incoming_messages(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Aiguille les messages entrants privés."""
        if not update.effective_chat or update.effective_chat.type != "private":
            return

        user_id = update.effective_user.id

        # 0. Contrôle de bannissement (blocage immédiat de toute interaction)
        if self.db_manager.is_user_banned(user_id):
            await update.message.reply_text(
                "🚫 <b>Votre compte a été banni de la plateforme.</b>\n"
                "L'accès aux services vous est définitivement révoqué.",
                parse_mode="HTML"
            )
            return

        # 1. Confirmation textuelle de purge de la Zone de Danger (Owner only)
        if context.user_data.get("waiting_danger_confirmation"):
            handled = await self.admin_handlers.handle_danger_text_input(update, context)
            if handled:
                return

        # 2. Saisie du motif de bannissement
        if context.user_data.get("waiting_ban_reason"):
            handled = await self.admin_handlers.handle_ban_reason_input(update, context)
            if handled:
                return

        # 3. Saisie de recherche d'un membre (ID ou @username)
        if context.user_data.get("waiting_member_search"):
            handled = await self.admin_handlers.handle_member_search_input(update, context)
            if handled:
                return

        # 4. Collecte de messages/médias par l'opérateur (Mode direct ou lot)
        if context.user_data.get("contact_session"):
            handled = await self.staff_handlers.handle_collect_admin_media(update, context)
            if handled:
                return

        # 5. Messages et réponses des demandeurs / utilisateurs courants
        await self.user_handlers.handle_text_messages(update, context)

    def run(self):
        """Démarre le bot en mode polling local."""
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