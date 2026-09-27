"""Module d'exécution sécurisée des rappels périodiques (Cron horaire)."""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Any
from telegram import Bot
from telegram.error import Forbidden, BadRequest, TelegramError

logger = logging.getLogger(__name__)

# Limite stricte pour respecter les quotas CPU et le timeout WSGI (300 s)
BATCH_LIMIT = 30
INTER_MESSAGE_DELAY = 0.05  # 50 ms entre chaque envoi pour lisser le débit


async def run_hourly_reminders(bot: Bot, db_manager, config) -> Dict[str, Any]:
    """Exécute l'ensemble des contrôles et relances avec mise à jour immédiate."""
    summary = {
        "paiements_relances": 0,
        "livraisons_relancees": 0,
        "abandons_executes": 0,
        "bloques": 0,
        "erreurs": 0,
    }

    # Récupération des délais dynamiques depuis la configuration SQL
    pay_reminder_days = db_manager.get_payment_reminder_days()
    delivery_reminder_days = db_manager.get_delivery_reminder_days()
    remun_expiration_days = db_manager.get_remun_expiration_days()

    # 1. Traitement des abandons automatiques (demandeurs inactifs après proposition tarifaire)
    summary["abandons_executes"] = await _process_expired_remunerations(
        bot, db_manager, remun_expiration_days
    )

    # 2. Relances des paiements en attente (demandeurs)
    pay_count, pay_blocked = await _process_payment_reminders(
        bot, db_manager, pay_reminder_days
    )
    summary["paiements_relances"] += pay_count
    summary["bloques"] += pay_blocked

    # 3. Relances des livraisons en retard (staff)
    deliv_count, deliv_blocked = await _process_delivery_reminders(
        bot, db_manager, delivery_reminder_days
    )
    summary["livraisons_relancees"] += deliv_count
    summary["bloques"] += deliv_blocked

    return summary


# ==================== SOUS-FONCTIONS MÉTIER ====================

async def _process_payment_reminders(bot: Bot, db_manager, days_interval: int) -> tuple[int, int]:
    """Relance les clients ayant un paiement prioritaire en suspens."""
    sent = 0
    blocked = 0

    with db_manager.get_cursor() as cursor:
        cursor.execute(
            """
            SELECT d.id, d.user_id, d.prenom, d.nom, d.montant
            FROM demandes d
            LEFT JOIN users u ON d.user_id = u.user_id
            WHERE d.prioritaire = 1
              AND d.statut = 'en_attente_paiement'
              AND (u.is_bot_blocked IS NULL OR u.is_bot_blocked = 0)
              AND (
                  d.date_dernier_rappel IS NULL 
                  OR d.date_dernier_rappel <= NOW() - INTERVAL %s DAY
              )
            ORDER BY COALESCE(d.date_dernier_rappel, d.date_creation) ASC
            LIMIT %s
            """,
            (days_interval, BATCH_LIMIT)
        )
        demandes = cursor.fetchall()

    for row in demandes:
        d_id = row["id"]
        u_id = row["user_id"]
        nom_cible = f"{row.get('prenom') or ''} {row.get('nom') or ''}".strip() or "Votre demande"
        montant = float(row.get("montant") or 0.0)

        msg = (
            "🔔 <b>Rappel de règlement — Demande prioritaire</b>\n\n"
            f"Votre dossier <b>#{d_id}</b> ({nom_cible}) est actuellement en attente de paiement.\n"
            f"• <b>Montant :</b> {montant:.2f} €\n\n"
            "Merci de finaliser le règlement afin qu'un opérateur puisse traiter votre demande."
        )

        try:
            await bot.send_message(chat_id=u_id, text=msg, parse_mode="HTML")
            # Mise à jour immédiate pour garantir l'idempotence
            db_manager.execute_query(
                "UPDATE demandes SET date_dernier_rappel = NOW() WHERE id = %s",
                (d_id,)
            )
            sent += 1
            await asyncio.sleep(INTER_MESSAGE_DELAY)
        except Forbidden:
            logger.warning("Bot bloqué par le client %s sur rappel paiement dossier #%s", u_id, d_id)
            _mark_user_blocked(db_manager, u_id)
            blocked += 1
        except TelegramError as exc:
            logger.error("Erreur Telegram envoi rappel client %s : %s", u_id, exc)

    return sent, blocked


async def _process_delivery_reminders(bot: Bot, db_manager, days_interval: int) -> tuple[int, int]:
    """Relance les opérateurs ayant un dossier pris en charge sans livraison."""
    sent = 0
    blocked = 0

    with db_manager.get_cursor() as cursor:
        cursor.execute(
            """
            SELECT d.id, d.prenom, d.nom, ds.staff_id, s.alias
            FROM demandes d
            JOIN demandes_suivi ds ON d.id = ds.demande_id
            JOIN staff s ON ds.staff_id = s.user_id
            WHERE d.statut IN ('en_cours', 'prise_en_charge')
              AND (
                  d.date_dernier_rappel_staff IS NULL 
                  OR d.date_dernier_rappel_staff <= NOW() - INTERVAL %s DAY
              )
              AND ds.date_suivi <= NOW() - INTERVAL %s DAY
            ORDER BY COALESCE(d.date_dernier_rappel_staff, ds.date_suivi) ASC
            LIMIT %s
            """,
            (days_interval, days_interval, BATCH_LIMIT)
        )
        demandes = cursor.fetchall()

    for row in demandes:
        d_id = row["id"]
        staff_id = row["staff_id"]
        cible = f"{row.get('prenom') or ''} {row.get('nom') or ''}".strip() or "Non renseignée"

        msg = (
            "🚚 <b>Rappel de suivi opérationnel</b>\n\n"
            f"Le dossier <b>#{d_id}</b> (Cible : {cible}) est pris en charge depuis plusieurs jours sans rapport de livraison.\n\n"
            "👉 Pensez à faire le point sur vos échanges et à déposer les éléments de preuve requis."
        )

        try:
            await bot.send_message(chat_id=staff_id, text=msg, parse_mode="HTML")
            db_manager.execute_query(
                "UPDATE demandes SET date_dernier_rappel_staff = NOW() WHERE id = %s",
                (d_id,)
            )
            sent += 1
            await asyncio.sleep(INTER_MESSAGE_DELAY)
        except Forbidden:
            logger.warning("Bot bloqué par le membre du staff %s sur dossier #%s", staff_id, d_id)
            _mark_user_blocked(db_manager, staff_id)
            blocked += 1
        except TelegramError as exc:
            logger.error("Erreur Telegram envoi rappel staff %s : %s", staff_id, exc)

    return sent, blocked


async def _process_expired_remunerations(bot: Bot, db_manager, days_interval: int) -> int:
    """Clôture automatiquement les demandes sans retour tarifaire du client."""
    abandoned_count = 0

    with db_manager.get_cursor() as cursor:
        cursor.execute(
            """
            SELECT id, user_id, prenom, nom
            FROM demandes
            WHERE statut = 'attente_validation_montant'
              AND date_modification <= NOW() - INTERVAL %s DAY
            LIMIT %s
            """,
            (days_interval, BATCH_LIMIT)
        )
        expired = cursor.fetchall()

    for row in expired:
        d_id = row["id"]
        u_id = row["user_id"]

        with db_manager.transaction() as cur:
            cur.execute(
                """
                UPDATE demandes 
                SET statut = 'abandonnee', 
                    motif_abandon = 'Délai de réponse dépassé pour la proposition financière',
                    date_modification = NOW()
                WHERE id = %s
                """,
                (d_id,)
            )

        msg = (
            f"❌ <b>Dossier #{d_id} clôturé (Abandon automatique)</b>\n\n"
            f"Le délai de {days_interval} jours accordé pour valider la tarification a expiré sans confirmation de votre part.\n"
            "Vous pouvez soumettre un nouveau dossier depuis le menu principal."
        )

        try:
            await bot.send_message(chat_id=u_id, text=msg, parse_mode="HTML")
            await asyncio.sleep(INTER_MESSAGE_DELAY)
        except Exception:
            pass  # Dossier déjà clôturé de façon sécurisée en SQL

        abandoned_count += 1

    return abandoned_count


def _mark_user_blocked(db_manager, user_id: int):
    """Marque le profil pour ignorer ce compte lors des futures requêtes."""
    try:
        db_manager.execute_query(
            "UPDATE users SET is_bot_blocked = 1 WHERE user_id = %s",
            (user_id,)
        )
    except Exception as exc:
        logger.error("Impossible de marquer l'utilisateur %s comme ayant bloqué le bot : %s", user_id, exc)