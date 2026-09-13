"""Système de gestion des pseudonymes du staff et des notifications."""

import html
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import Forbidden, TelegramError
from telegram.ext import ContextTypes, ConversationHandler

logger = logging.getLogger(__name__)


class AliasManager:
    """Gestionnaire d'alias, d'unicité et de notification pour le staff et les administrateurs."""

    WAITING_ALIAS = 1
    DEFAULT_OWNER_ALIAS = "Propriétaire"
    DEFAULT_STAFF_PREFIX = "Baiter"

    def __init__(self, db_manager, config):
        self.db_manager = db_manager
        self.config = config
        logger.info("AliasManager initialisé avec support Staff/Admin")

    async def _safe_edit_or_send(self, query, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None):
        """Met à jour le message ou supprime la photo existante pour envoyer le texte."""
        if query.message and query.message.photo:
            chat_id = query.message.chat_id
            try:
                await query.message.delete()
            except Exception:
                pass
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="HTML",
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
        else:
            try:
                await query.edit_message_text(
                    text=text,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                    disable_web_page_preview=True
                )
            except Exception:
                if query.message:
                    await query.message.reply_text(
                        text=text,
                        parse_mode="HTML",
                        reply_markup=reply_markup,
                        disable_web_page_preview=True
                    )

    def get_staff_alias(self, staff_user_id: int) -> str:
        """Récupère l'alias via DatabaseManager (gère staff, admins et owner)."""
        try:
            return self.db_manager.get_staff_alias(int(staff_user_id))
        except Exception as exc:
            logger.error("Erreur récupération alias staff %s : %s", staff_user_id, exc)
            return f"Staff_{staff_user_id}"

    # Rétrocompatibilité
    get_admin_alias = get_staff_alias

    def _save_staff_alias(self, staff_user_id: int, alias: str):
        """Sauvegarde l'alias en base via la méthode unifiée du db_manager."""
        self.db_manager.set_staff_alias(staff_user_id, alias)

    def _is_alias_unique(self, new_alias: str, current_user_id: int) -> bool:
        """Contrôle la disponibilité d'un pseudonyme sur l'ensemble de l'équipe (staff + admins + owner)."""
        try:
            current_user_id = int(current_user_id)
            clean_alias = new_alias.strip().lower()

            owner_alias = self.db_manager.get_owner_alias() or self.DEFAULT_OWNER_ALIAS
            if owner_alias.lower() == clean_alias and not self.config.is_owner(current_user_id):
                return False

            with self.db_manager.get_cursor() as cursor:
                # 1. Vérification dans staff
                cursor.execute(
                    "SELECT user_id FROM staff WHERE LOWER(alias) = %s AND user_id != %s",
                    (clean_alias, current_user_id),
                )
                if cursor.fetchone() is not None:
                    return False

                # 2. Vérification dans admins
                cursor.execute(
                    "SELECT user_id FROM admins WHERE LOWER(alias) = %s AND user_id != %s",
                    (clean_alias, current_user_id),
                )
                if cursor.fetchone() is not None:
                    return False

            return True
        except Exception as exc:
            logger.error("Erreur contrôle unicité alias : %s", exc)
            return False

    async def modifier_alias(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Déclenche la conversation de saisie d'un nouvel alias."""
        query = update.callback_query
        user = update.effective_user
        if not user:
            return ConversationHandler.END

        user_id = user.id
        is_owner = self.config.is_owner(user_id)

        # Vérification des droits : accessible à tout le staff (opérateurs, managers, owners)
        if not self.config.is_staff(user_id):
            if query:
                await query.answer("❌ Accès réservé à l'équipe.", show_alert=True)
            return ConversationHandler.END

        data = query.data if query and query.data else ""
        if is_owner and data.startswith("owner_edit_alias_"):
            try:
                target_id = int(data.replace("owner_edit_alias_", ""))
            except (IndexError, ValueError):
                target_id = user_id
            context.user_data["target_alias_user_id"] = target_id
        else:
            target_id = context.user_data.get("target_alias_user_id", user_id)
            context.user_data["target_alias_user_id"] = target_id

        # Si un opérateur standard tente de modifier son alias déjà verrouillé
        if not is_owner and target_id == user_id:
            if not self.db_manager.can_staff_edit_alias(user_id):
                alert_msg = (
                    "🔒 <b>Alias verrouillé</b>\n\n"
                    "Vous avez déjà configuré votre alias officiel. "
                    "Seule la direction peut le modifier désormais."
                )
                kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Paramètres", callback_data="parametres")]])
                if query:
                    await query.answer("🔒 Alias déjà configuré.", show_alert=True)
                    await self._safe_edit_or_send(query, context, alert_msg, reply_markup=kb)
                elif update.message:
                    await update.message.reply_text(alert_msg, parse_mode="HTML", reply_markup=kb)
                return ConversationHandler.END

        target_alias = self.get_staff_alias(target_id)
        target_alias_esc = html.escape(target_alias)

        if not is_owner and target_id == user_id:
            avertissement = (
                "⚠️ <b>Attention :</b> Vous ne disposez que d'<b>une seule modification</b> pour définir votre alias. "
                "Une fois validé, il sera définitivement verrouillé.\n\n"
            )
            retour_btn = InlineKeyboardButton("❌ Annuler", callback_data="cancel_alias_change")
        elif is_owner and target_id != user_id:
            avertissement = (
                "👑 <b>Gestion Propriétaire</b>\n"
                f"Modification forcée de l'alias pour le membre (ID : <code>{target_id}</code>).\n\n"
            )
            retour_btn = InlineKeyboardButton("❌ Annuler", callback_data="gerer_staff")
        else:
            avertissement = ""
            retour_btn = InlineKeyboardButton("❌ Annuler", callback_data="cancel_alias_change")

        text = (
            f"✏️ <b>Configuration de l'alias</b>\n\n"
            f"Alias actuel : <code>{target_alias_esc}</code>\n\n"
            f"{avertissement}"
            "Envoyez le nouveau pseudonyme en réponse à ce message :\n"
            "• 2 à 30 caractères\n"
            "• Lettres, chiffres, espaces, tirets et underscores autorisés\n"
            "• Doit être unique au sein de toute l'équipe"
        )
        keyboard = InlineKeyboardMarkup([[retour_btn]])

        if query:
            await query.answer()
            await self._safe_edit_or_send(query, context, text, reply_markup=keyboard)
        elif update.message:
            await update.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)

        return self.WAITING_ALIAS

    async def traiter_nouveau_alias(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Valide et enregistre le nouvel alias transmis par message texte."""
        if not update.message or not update.message.text:
            return self.WAITING_ALIAS

        user_id = update.effective_user.id
        is_owner = self.config.is_owner(user_id)
        if not self.config.is_staff(user_id):
            return ConversationHandler.END

        target_id = context.user_data.get("target_alias_user_id", user_id)
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

        if not self._is_alias_unique(new_alias, target_id):
            await update.message.reply_text(
                "❌ Cet alias est déjà réservé au sein de l'équipe. Choisissez-en un autre :"
            )
            return self.WAITING_ALIAS

        try:
            self._save_staff_alias(target_id, new_alias)
            context.user_data.pop("target_alias_user_id", None)

            verrou_txt = ""
            if not is_owner and target_id == user_id:
                self.db_manager.lock_staff_alias(user_id)
                verrou_txt = "\n\n🔒 <i>Votre alias est désormais verrouillé et ne peut plus être modifié.</i>"

            new_alias_esc = html.escape(new_alias)

            if is_owner and target_id != user_id:
                retour_kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("👥 Équipe Staff", callback_data="gerer_staff")],
                    [InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")]
                ])
                succes_msg = (
                    f"✅ <b>Alias mis à jour avec succès !</b>\n\n"
                    f"👤 <b>Membre (ID {target_id}) :</b> <code>{new_alias_esc}</code>"
                )
            else:
                retour_kb = InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Menu Paramètres", callback_data="parametres")
                ]])
                succes_msg = f"✅ <b>Alias mis à jour :</b> <code>{new_alias_esc}</code>{verrou_txt}"

            await update.message.reply_text(
                succes_msg,
                parse_mode="HTML",
                reply_markup=retour_kb
            )
            logger.info("Alias de %s mis à jour par %s : '%s'", target_id, user_id, new_alias)
            return ConversationHandler.END

        except Exception as exc:
            logger.error("Erreur enregistrement alias %s : %s", target_id, exc)
            await update.message.reply_text("❌ Une erreur est survenue lors de l'enregistrement.")
            return ConversationHandler.END

    async def cancel_alias_change(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Interrompt la saisie de l'alias et revient au menu approprié."""
        target_id = context.user_data.pop("target_alias_user_id", None)
        user_id = update.effective_user.id if update.effective_user else 0
        is_owner = self.config.is_owner(user_id)

        if is_owner and target_id and target_id != user_id:
            callback_target = "gerer_staff"
            btn_label = "👥 Équipe Staff"
        else:
            callback_target = "parametres"
            btn_label = "🔙 Paramètres"

        msg = "❌ <b>Modification d'alias annulée.</b>"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(btn_label, callback_data=callback_target)]])

        if update.callback_query:
            await update.callback_query.answer()
            await self._safe_edit_or_send(update.callback_query, context, msg, reply_markup=kb)
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
        """Envoie la notification de changement de statut au demandeur avec protection HTML."""
        try:
            prenom_esc = html.escape(str(prenom or ""))
            old_esc = html.escape(str(old_status or ""))
            new_esc = html.escape(str(new_status or ""))
            alias_esc = html.escape(str(admin_alias or ""))

            text = (
                f"📢 <b>Notification de suivi</b>\n\n"
                f"Bonjour <b>{prenom_esc}</b>, le statut de votre demande <b>#{request_number}</b> a évolué :\n\n"
                f"Ancien statut : <s>{old_esc}</s>\n"
                f"Nouveau statut : <b>{new_esc}</b>\n\n"
                f"👨‍💼 <b>Opérateur en charge :</b> {alias_esc}\n\n"
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
            logger.warning("Erreur Telegram lors de l'envoi de la notification à %s : %s", user_id, exc)
        except Exception as exc:
            logger.error("Erreur inattendue envoi notification : %s", exc, exc_info=True)