"""Système de gestion des pseudonymes administrateurs et des notifications."""

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import Forbidden, TelegramError
from telegram.ext import ContextTypes, ConversationHandler

logger = logging.getLogger(__name__)


class AliasManager:
    """Gestionnaire d'alias, d'unicité et de notification pour les administrateurs."""

    def __init__(self, db_manager, config):
        self.db_manager = db_manager
        self.config = config

        self.WAITING_ALIAS = 1
        self.DEFAULT_OWNER_ALIAS = "Propriétaire"
        self.DEFAULT_ADMIN_PREFIX = "Baiter"
        logger.info("AliasManager initialisé")

    def get_admin_alias(self, admin_user_id: int) -> str:
        """Récupère l'alias de l'administrateur avec génération automatique en fallback."""
        try:
            if self.config.is_owner(admin_user_id):
                return self.db_manager.get_config_value("owner_alias", self.DEFAULT_OWNER_ALIAS)

            with self.db_manager.get_cursor() as cursor:
                cursor.execute("SELECT alias FROM admins WHERE user_id = %s", (admin_user_id,))
                result = cursor.fetchone()

                if result and result.get("alias"):
                    return result["alias"]

                alias_auto = self._generate_default_admin_alias(admin_user_id)
                self._save_admin_alias(admin_user_id, alias_auto)
                return alias_auto

        except Exception as exc:
            logger.error("Erreur récupération alias admin %s: %s", admin_user_id, exc)
            return f"Admin_{admin_user_id}"

    def _generate_default_admin_alias(self, admin_user_id: int) -> str:
        """Génère un identifiant séquentiel par défaut 'Baiter X'."""
        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT ROW_NUMBER() OVER (ORDER BY date_added ASC) AS ordre
                    FROM admins
                    WHERE user_id = %s
                    """,
                    (admin_user_id,),
                )
                result = cursor.fetchone()

                if result and result.get("ordre"):
                    return f"{self.DEFAULT_ADMIN_PREFIX} {result['ordre']}"

                cursor.execute("SELECT COUNT(*) AS total FROM admins")
                count_res = cursor.fetchone()
                total = count_res["total"] if count_res else 1
                return f"{self.DEFAULT_ADMIN_PREFIX} {total}"

        except Exception as exc:
            logger.error("Erreur génération alias par défaut: %s", exc)
            return f"{self.DEFAULT_ADMIN_PREFIX} 1"

    def _save_admin_alias(self, admin_user_id: int, alias: str):
        """Sauvegarde l'alias en base de données."""
        if self.config.is_owner(admin_user_id):
            self.db_manager.set_config_value("owner_alias", alias)
        else:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    "UPDATE admins SET alias = %s WHERE user_id = %s",
                    (alias, admin_user_id),
                )

    def _is_alias_unique(self, new_alias: str, current_user_id: int) -> bool:
        """Contrôle la disponibilité d'un pseudonyme."""
        try:
            owner_alias = self.db_manager.get_config_value("owner_alias", self.DEFAULT_OWNER_ALIAS)
            if owner_alias.lower() == new_alias.lower() and not self.config.is_owner(current_user_id):
                return False

            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT user_id FROM admins
                    WHERE LOWER(alias) = LOWER(%s) AND user_id != %s
                    """,
                    (new_alias, current_user_id),
                )
                return cursor.fetchone() is None

        except Exception as exc:
            logger.error("Erreur contrôle unicité alias: %s", exc)
            return False

    async def modifier_alias(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Déclenche la conversation de saisie d'un nouvel alias."""
        query = update.callback_query
        if not query or not update.effective_user:
            return ConversationHandler.END

        await query.answer()
        user_id = update.effective_user.id

        if not self.config.is_admin(user_id):
            return ConversationHandler.END

        current_alias = self.get_admin_alias(user_id)
        text = (
            "✏️ <b>Modification de votre Alias</b>\n\n"
            f"👤 <b>Alias actuel :</b> <code>{current_alias}</code>\n\n"
            "Envoyez votre nouveau pseudonyme en réponse à ce message :\n"
            "• 2 à 30 caractères\n"
            "• Lettres, chiffres, espaces, tirets autorisés\n"
            "• Doit être unique au sein de l'équipe"
        )
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Annuler", callback_data="cancel_alias_change")
        ]])

        await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)
        return self.WAITING_ALIAS

    async def traiter_nouveau_alias(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Valide et enregistre le nouvel alias transmis par message texte."""
        if not update.message or not update.message.text:
            return self.WAITING_ALIAS

        user_id = update.effective_user.id
        if not self.config.is_admin(user_id):
            return ConversationHandler.END

        new_alias = update.message.text.strip()

        if len(new_alias) < 2 or len(new_alias) > 30:
            await update.message.reply_text(
                "❌ L'alias doit comporter entre 2 et 30 caractères. Veuillez réessayer :"
            )
            return self.WAITING_ALIAS

        clean_test = new_alias.replace(" ", "").replace("-", "").replace("_", "")
        if not clean_test.isalnum():
            await update.message.reply_text(
                "❌ Caractères autorisés : lettres, chiffres, espaces, tirets et underscores. Veuillez réessayer :"
            )
            return self.WAITING_ALIAS

        if not self._is_alias_unique(new_alias, user_id):
            await update.message.reply_text(
                "❌ Cet alias est déjà réservé par un autre administrateur. Choisissez-en un autre :"
            )
            return self.WAITING_ALIAS

        try:
            self._save_admin_alias(user_id, new_alias)
            self.db_manager.clear_cache()

            await update.message.reply_text(
                f"✅ <b>Alias mis à jour :</b> <code>{new_alias}</code>\n\n"
                "Ce pseudonyme sera affiché aux utilisateurs lors de la prise en charge de leurs demandes.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")
                ]])
            )
            logger.info("Admin %s a changé son alias pour '%s'", user_id, new_alias)
            return ConversationHandler.END

        except Exception as exc:
            logger.error("Erreur enregistrement alias %s: %s", user_id, exc)
            await update.message.reply_text("❌ Une erreur est survenue lors de l'enregistrement.")
            return ConversationHandler.END

    async def cancel_alias_change(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Interrompt la saisie de l'alias et revient au menu."""
        msg = "❌ <b>Modification d'alias annulée.</b>"
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")
        ]])

        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(msg, parse_mode="HTML", reply_markup=kb)
        elif update.message:
            await update.message.reply_text(msg, parse_mode="HTML", reply_markup=kb)

        return ConversationHandler.END

    async def send_status_notification(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        user_id: int,
        request_number: int,
        prenom: str,
        old_status: str,
        new_status: str,
        admin_alias: str,
    ):
        """Envoie la notification de changement de statut au demandeur."""
        try:
            text = (
                f"📢 <b>Notification de suivi</b>\n\n"
                f"Bonjour <b>{prenom}</b>, le statut de votre demande <b>#{request_number}</b> a évolué :\n\n"
                f"Ancien statut : <s>{old_status}</s>\n"
                f"Nouveau statut : <b>{new_status}</b>\n\n"
                f"👨‍💼 <b>Référent en charge :</b> {admin_alias}\n\n"
                "Tapez /demandes pour afficher l'ensemble de vos demandes."
            )

            await context.bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            logger.info("Notification envoyée à %s pour la demande #%s", user_id, request_number)

        except Forbidden:
            logger.warning("Notification non délivrée : le bot a été bloqué par l'utilisateur %s", user_id)
        except TelegramError as exc:
            logger.warning("Erreur Telegram lors de l'envoi de la notification à %s: %s", user_id, exc)
        except Exception as exc:
            logger.error("Erreur inattendue envoi notification: %s", exc, exc_info=True)