"""Gestion du compte utilisateur et persistance de l'activité."""

import html
import logging
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


class CompteManager:
    """Gestionnaire de persistance et de statut pour les utilisateurs."""

    def __init__(self, db_manager, config):
        self.db_manager = db_manager
        self.config = config
        logger.info("CompteManager initialisé")

    async def ensure_user_registered(self, update: Update) -> bool:
        """Enregistre ou met à jour les informations du profil utilisateur en base."""
        user = update.effective_user
        if not user:
            logger.warning("Impossible d'extraire les données utilisateur depuis la mise à jour.")
            return False

        full_first_name = user.first_name or ""
        if user.last_name:
            full_first_name = f"{full_first_name} {user.last_name}".strip()

        try:
            with self.db_manager.transaction() as cursor:
                cursor.execute(
                    """
                    INSERT INTO users (user_id, username, first_name, date_inscription, derniere_activite)
                    VALUES (%s, %s, %s, NOW(), NOW())
                    ON DUPLICATE KEY UPDATE
                        username = VALUES(username),
                        first_name = VALUES(first_name),
                        derniere_activite = NOW()
                    """,
                    (
                        int(user.id),
                        user.username or None,
                        full_first_name[:64],
                    ),
                )

                if cursor.rowcount == 1:
                    logger.info("Nouvel utilisateur enregistré : %s (%s)", user.id, full_first_name)
                elif cursor.rowcount == 2:
                    logger.debug("Profil utilisateur synchronisé : %s", user.id)

                return True

        except Exception as exc:
            logger.error("Erreur enregistrement utilisateur %s : %s", user.id, exc, exc_info=True)
            return False

    async def update_user_activity(self, user_id: int) -> bool:
        """Met à jour le timestamp de dernière activité."""
        try:
            with self.db_manager.transaction() as cursor:
                cursor.execute(
                    "UPDATE users SET derniere_activite = NOW() WHERE user_id = %s",
                    (int(user_id),),
                )
                return cursor.rowcount > 0
        except Exception as exc:
            logger.error("Erreur mise à jour activité utilisateur %s : %s", user_id, exc)
            return False

    async def get_user_display_name(self, user_id: int) -> str:
        """Retourne un nom d'affichage propre (Prénom, @username ou identifiant)."""
        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    "SELECT first_name, username FROM users WHERE user_id = %s",
                    (int(user_id),),
                )
                row = cursor.fetchone()

                if row:
                    if row.get("first_name"):
                        return html.escape(row["first_name"])
                    if row.get("username"):
                        return f"@{html.escape(row['username'])}"

            return f"User {user_id}"

        except Exception as exc:
            logger.error("Erreur récupération nom utilisateur %s : %s", user_id, exc)
            return f"User {user_id}"

    async def handle_text_messages(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Répond aux messages texte non reconnus hors navigation et édition."""
        if not update.effective_user or not update.message:
            return

        await self.update_user_activity(update.effective_user.id)

        await update.message.reply_text(
            "🤖 Je n'ai pas compris votre message.\n"
            "Utilisez la commande /start ou les boutons de navigation pour interagir.",
            parse_mode="HTML",
        )