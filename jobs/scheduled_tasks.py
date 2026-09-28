"""Tâches planifiées en arrière-plan (JobQueue) pour les rappels et archivages automatiques."""

import asyncio
from datetime import datetime
import html
import logging
import pytz
import calendar
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import Forbidden
from telegram.ext import ContextTypes
from utils.session import session_manager

logger = logging.getLogger(__name__)
PARIS_TZ = pytz.timezone("Europe/Paris")


# ==================== RAPPELS ADMIN / STAFF ====================

async def _send_single_admin_reminder(context: ContextTypes.DEFAULT_TYPE, db_manager, user_id: int, active_demandes: list, is_silent: bool):
    if hasattr(db_manager, "is_bot_blocked") and db_manager.is_bot_blocked(user_id):
        return

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
        if hasattr(db_manager, "mark_bot_blocked"):
            db_manager.mark_bot_blocked(user_id, is_blocked=True)
    except Exception as err:
        logger.warning("Erreur envoi rappel programmé au staff %s : %s", user_id, err)


async def check_and_send_admin_reminders(context: ContextTypes.DEFAULT_TYPE):
    db_manager = context.application.bot_data.get("db_manager")
    if not db_manager:
        logger.warning("Vérification des rappels abandonnée : db_manager introuvable.")
        return

    now_paris = datetime.now(PARIS_TZ)
    current_hour = now_paris.hour
    current_weekday = now_paris.weekday()  # 6 = Dimanche
    current_monthday = now_paris.day
    today_date = now_paris.date()

    admin_prefs_list = db_manager.get_all_admin_preferences()
    tasks = []

    for pref in admin_prefs_list:
        user_id = pref["user_id"]

        # Seule la mise en pause coupe les relances de suivi
        if db_manager.is_staff_paused(user_id):
            continue

        rappel_mode = pref.get("rappel_mode", "silent")
        freq = pref.get("rappel_freq", "weekly")
        heure = int(pref.get("rappel_heure", 21))
        last_date = pref.get("last_rappel_date")

        if current_hour != heure:
            continue

        if str(last_date) == str(today_date):
            continue

        if freq == "weekly" and current_weekday != int(pref.get("rappel_jour_semaine", 6)):
            continue
        elif freq == "monthly":
            target_day = int(pref.get("rappel_jour_mois", 1))
            # Récupère le dernier jour du mois en cours (ex: 30 en juin, 28/29 en février)
            _, max_days_in_month = calendar.monthrange(now_paris.year, now_paris.month)
            effective_day = min(target_day, max_days_in_month)

            if current_monthday != effective_day:
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
                is_silent = (rappel_mode != "sound")
                tasks.append(_send_single_admin_reminder(context, db_manager, user_id, active_demandes, is_silent))
        except Exception as db_err:
            logger.error("Erreur lecture suivis pour rappel staff %s : %s", user_id, db_err)

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


# ==================== AUTO-ARCHIVAGE & MAINTENANCE DISQUE ====================

async def check_and_auto_archive_demandes(context: ContextTypes.DEFAULT_TYPE):
    db_manager = context.application.bot_data.get("db_manager")
    if not db_manager:
        return

    # Maintenance disque et nettoyage des sessions orphelines / temporaires
    try:
        session_manager.cleanup_disk()
    except Exception as sess_err:
        logger.debug("Erreur maintenance disque sessions : %s", sess_err)

    try:
        if hasattr(db_manager, "get_auto_archive_hours"):
            hours = db_manager.get_auto_archive_hours()
        elif hasattr(db_manager, "get_config_value"):
            hours = int(db_manager.get_config_value("auto_archive_hours", 72) or 72)
        else:
            hours = 72

        expired_demandes = db_manager.get_expired_delivered_demandes(hours=hours)
        for dem in expired_demandes:
            dem_id = dem["id"]
            req_num = dem.get("request_number") or dem_id
            if db_manager.archiver_demande_reussie(dem_id):
                logger.info("📦 Demande #%s archivée automatiquement après %sh post-livraison.", req_num, hours)
    except Exception as exc:
        logger.error("Erreur exécution auto-archivage : %s", exc)


# ==================== RAPPELS DE LIVRAISON ====================

async def _send_single_delivery_reminder(context: ContextTypes.DEFAULT_TYPE, db_manager, dem: dict, days: int):
    admin_id = dem["admin_id"]
    if hasattr(db_manager, "is_bot_blocked") and db_manager.is_bot_blocked(admin_id):
        return

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
        if hasattr(db_manager, "mark_bot_blocked"):
            db_manager.mark_bot_blocked(admin_id, is_blocked=True)
    except Exception as notif_err:
        logger.warning("Impossible d'envoyer le rappel de livraison à %s : %s", admin_id, notif_err)


async def check_and_send_delivery_reminders(context: ContextTypes.DEFAULT_TYPE):
    db_manager = context.application.bot_data.get("db_manager")
    if not db_manager:
        return

    try:
        if hasattr(db_manager, "get_delivery_reminder_days"):
            days = db_manager.get_delivery_reminder_days()
        elif hasattr(db_manager, "get_config_value"):
            days = int(db_manager.get_config_value("delai_livraison_jours", 3) or 3)
        else:
            days = 3

        undelivered = db_manager.get_undelivered_terminee_demandes_for_reminder(days=days)
        tasks = [_send_single_delivery_reminder(context, db_manager, dem, days) for dem in undelivered]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as exc:
        logger.error("Erreur lors de la vérification des rappels de livraison : %s", exc)


# ==================== RAPPELS POST-PAIEMENT ====================

async def _send_single_paid_delivery_reminder(context: ContextTypes.DEFAULT_TYPE, db_manager, dem: dict):
    admin_id = dem["admin_id"]
    if hasattr(db_manager, "is_bot_blocked") and db_manager.is_bot_blocked(admin_id):
        return

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
        if hasattr(db_manager, "mark_bot_blocked"):
            db_manager.mark_bot_blocked(admin_id, is_blocked=True)
    except Exception as err:
        logger.warning("Erreur relance livraison payée à %s : %s", admin_id, err)


async def check_and_send_paid_delivery_reminders(context: ContextTypes.DEFAULT_TYPE):
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


# ==================== RAPPELS IMPAYÉS CLIENT ====================

async def _send_single_unpaid_demande_reminder(context: ContextTypes.DEFAULT_TYPE, db_manager, dem: dict):
    user_id = dem["user_id"]
    if hasattr(db_manager, "is_bot_blocked") and db_manager.is_bot_blocked(user_id):
        return

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
        if hasattr(db_manager, "mark_bot_blocked"):
            db_manager.mark_bot_blocked(user_id, is_blocked=True)
    except Exception as notif_err:
        logger.warning("Impossible d'envoyer le rappel d'impayé au client %s : %s", user_id, notif_err)


async def check_and_send_unpaid_demande_reminders(context: ContextTypes.DEFAULT_TYPE):
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


# ==================== EXPIRATION PROPOSITION RÉMUNÉRATION ====================

async def _process_single_remun_abandon(context: ContextTypes.DEFAULT_TYPE, db_manager, dem: dict, days: int):
    dem_id = dem["id"]
    user_id = dem["user_id"]
    req_num = html.escape(str(dem.get("request_number") or dem_id))
    prenom = html.escape(str(dem.get("prenom") or "la cible"))
    staff_id = dem.get("proposed_by")

    raison = f"Délai expiré : absence de réponse à la demande de rémunération ({days} jours)"
    archived = db_manager.archiver_demande_annulee(demande_id=dem_id, raison=raison)

    if archived:
        logger.info("❌ Demande #%s abandonnée automatiquement pour délai de rémunération expiré (%sj).", req_num, days)

        if not (hasattr(db_manager, "is_bot_blocked") and db_manager.is_bot_blocked(user_id)):
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
                if hasattr(db_manager, "mark_bot_blocked"):
                    db_manager.mark_bot_blocked(user_id, is_blocked=True)
            except Exception as notif_user_err:
                logger.warning("Impossible de notifier le client %s de l'abandon de rémunération : %s", user_id, notif_user_err)

        if staff_id and not (hasattr(db_manager, "is_bot_blocked") and db_manager.is_bot_blocked(staff_id)):
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
                if hasattr(db_manager, "mark_bot_blocked"):
                    db_manager.mark_bot_blocked(staff_id, is_blocked=True)
            except Exception as notif_staff_err:
                logger.warning("Impossible de notifier le staff %s de l'abandon de rémunération : %s", staff_id, notif_staff_err)


async def check_and_auto_abandon_expired_remun_demandes(context: ContextTypes.DEFAULT_TYPE):
    db_manager = context.application.bot_data.get("db_manager")
    if not db_manager:
        return

    try:
        if hasattr(db_manager, "get_remun_expiration_days"):
            days = db_manager.get_remun_expiration_days()
        elif hasattr(db_manager, "get_config_value"):
            days = int(db_manager.get_config_value("delai_remun_expire_jours", 2) or 2)
        else:
            days = 2

        expired = db_manager.get_expired_remun_demandes_for_abandon(days=days)
        tasks = [_process_single_remun_abandon(context, db_manager, dem, days) for dem in expired]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as exc:
        logger.error("Erreur lors de la vérification de l'abandon automatique pour délai de rémunération : %s", exc)