"""Module de gestion et de contrôle opérationnel du bot (Direction / Super-Admins)."""

import asyncio
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest, Forbidden, RetryAfter, TelegramError
from telegram.ext import ContextTypes
from utils.session import session_manager
from ui.admin import system as ui

logger = logging.getLogger(__name__)


class BotManager:
    """Gestionnaire d'état opérationnel et de diffusion broadcast avec capture Forbidden."""

    def __init__(self, db_manager, config, interface_manager=None):
        self.db_manager = db_manager
        self.config = config
        self.interface = interface_manager
        logger.info("BotManager initialisé avec support Multi-Owner et broadcast résilient.")

    def set_interface_manager(self, interface_manager):
        """Injecte l'InterfaceManager si nécessaire."""
        self.interface = interface_manager

    async def _safe_edit_or_send(self, query, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None):
        """Met à jour le message ou supprime la photo existante pour émettre du texte."""
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

    async def bot_on(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Active l'acceptation globale des demandes et coupe le mode maintenance."""
        query = update.callback_query
        user = update.effective_user
        if not query or not user or not self.config.is_owner(user.id):
            if query:
                await query.answer("❌ Action réservée à la direction.", show_alert=True)
            return

        await query.answer()

        try:
            self.config.enable_demandes()
            logger.info("Bot activé par le propriétaire %s", user.id)

            text, keyboard = ui.get_bot_on_content()
            await self._safe_edit_or_send(query, context, text, reply_markup=keyboard)

        except Exception as exc:
            logger.error("Erreur activation bot : %s", exc, exc_info=True)
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Retour", callback_data="gerer_bot")]])
            await self._safe_edit_or_send(query, context, "❌ Erreur technique lors de l'activation.", reply_markup=kb)

    async def bot_off(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Désactive la prise de demandes avec message d'information."""
        query = update.callback_query
        user = update.effective_user
        if not query or not user or not self.config.is_owner(user.id):
            if query:
                await query.answer("❌ Action réservée à la direction.", show_alert=True)
            return

        await query.answer()

        try:
            self.config.disable_demandes()
            logger.info("Demandes suspendues par le propriétaire %s", user.id)

            text, keyboard = ui.get_bot_off_content()
            await self._safe_edit_or_send(query, context, text, reply_markup=keyboard)

        except Exception as exc:
            logger.error("Erreur désactivation bot : %s", exc, exc_info=True)
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Retour", callback_data="gerer_bot")]])
            await self._safe_edit_or_send(query, context, "❌ Erreur technique lors de la désactivation.", reply_markup=kb)

    async def bot_maintenance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Active l'état de maintenance restreint."""
        query = update.callback_query
        user = update.effective_user
        if not query or not user or not self.config.is_owner(user.id):
            if query:
                await query.answer("❌ Action réservée à la direction.", show_alert=True)
            return

        await query.answer()

        try:
            self.config.disable_demandes()
            self.db_manager.set_config_value("maintenance_mode", "true")
            logger.info("Mode maintenance enclenché par le propriétaire %s", user.id)

            text, keyboard = ui.get_bot_maintenance_content()
            await self._safe_edit_or_send(query, context, text, reply_markup=keyboard)

        except Exception as exc:
            logger.error("Erreur passage en mode maintenance : %s", exc, exc_info=True)
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Retour", callback_data="gerer_bot")]])
            await self._safe_edit_or_send(query, context, "❌ Erreur lors de l'activation de la maintenance.", reply_markup=kb)

    async def get_bot_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Affiche l'état courant du service et des paramètres."""
        user = update.effective_user
        if not user or not self.config.is_admin(user.id):
            return

        try:
            is_active = self.config.are_demandes_enabled()
            is_maint = str(self.db_manager.get_config_value("maintenance_mode", "false")).lower() in ("true", "1")

            text, keyboard = ui.build_bot_status_content(is_active, is_maint)

            if update.callback_query:
                await update.callback_query.answer()
                await self._safe_edit_or_send(update.callback_query, context, text, reply_markup=keyboard)
            elif update.message:
                await update.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)

        except Exception as exc:
            logger.error("Erreur extraction statut bot : %s", exc, exc_info=True)
            err = "❌ Impossible de lire le statut du bot."
            if update.callback_query:
                await self._safe_edit_or_send(update.callback_query, context, err)
            elif update.message:
                await update.message.reply_text(err)

    # ==================== DIFFUSION BROADCAST SÉCURISÉE ====================

    async def prompt_broadcast(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Demande le texte de diffusion générale à l'administrateur."""
        await query.answer()
        user_id = query.from_user.id
        if not self.config.is_owner(user_id):
            return

        context.user_data["waiting_broadcast_text"] = True
        session_manager.set_state(user_id, "waiting_broadcast_text", True, ttl=600.0)

        msg = (
            "📢 <b>Diffusion générale (Broadcast)</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Veuillez saisir le message à envoyer à l'ensemble des utilisateurs enregistrés.\n"
            "<i>(Formatage HTML supporté).</i>\n\n"
            "Tapez /stop pour annuler."
        )
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="gerer_bot")]])
        await self._safe_edit_or_send(query, context, msg, reply_markup=kb)

    async def execute_broadcast(self, update: Update, context: ContextTypes.DEFAULT_TYPE, message_text: str):
        """Distribue le message aux utilisateurs éligibles en excluant et flaggant les blocages."""
        admin_id = update.effective_user.id
        eligible_users = self.db_manager.get_active_broadcast_users()
        total_targets = len(eligible_users)

        status_msg = await update.message.reply_text(
            f"🚀 <b>Démarrage de la diffusion...</b>\n\n"
            f"Destinataires éligibles : <b>{total_targets}</b>\n"
            "<i>Progression : 0%</i>",
            parse_mode="HTML"
        )

        sent_count = 0
        blocked_count = 0
        error_count = 0

        for idx, target_id in enumerate(eligible_users, start=1):
            try:
                await context.bot.send_message(
                    chat_id=target_id,
                    text=message_text,
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
                sent_count += 1
            except Forbidden:
                blocked_count += 1
                self.db_manager.mark_bot_blocked(target_id, is_blocked=True)
            except RetryAfter as e:
                await asyncio.sleep(e.retry_after + 1)
                try:
                    await context.bot.send_message(
                        chat_id=target_id,
                        text=message_text,
                        parse_mode="HTML",
                        disable_web_page_preview=True
                    )
                    sent_count += 1
                except Exception:
                    error_count += 1
            except (BadRequest, TelegramError) as tg_err:
                logger.debug("Échec broadcast vers %s : %s", target_id, tg_err)
                error_count += 1
            except Exception as e:
                logger.error("Erreur inattendue broadcast %s : %s", target_id, e)
                error_count += 1

            # Limitation de débit pour éviter les sanctions Telegram (~25 messages/sec)
            await asyncio.sleep(0.04)

            # Rafraîchissement régulier du rapport tous les 25 envois
            if idx % 25 == 0 or idx == total_targets:
                percent = int((idx / total_targets) * 100) if total_targets > 0 else 100
                try:
                    await status_msg.edit_text(
                        f"📢 <b>Diffusion en cours...</b>\n\n"
                        f"• Progression : <b>{percent}%</b> ({idx}/{total_targets})\n"
                        f"• Livrés avec succès : <b>{sent_count}</b>\n"
                        f"• Bots bloqués détectés : <b>{blocked_count}</b>\n"
                        f"• Erreurs diverses : <b>{error_count}</b>",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass

        recap = (
            "✅ <b>Diffusion terminée !</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"• 👥 Destinataires ciblés : <b>{total_targets}</b>\n"
            f"• ✉️ Messages remis : <b>{sent_count}</b>\n"
            f"• 🚫 Comptes ayant bloqué le bot : <b>{blocked_count}</b> (mis à jour en BDD)\n"
            f"• ⚠️ Autres échecs : <b>{error_count}</b>"
        )
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Bot", callback_data="gerer_bot")]])
        await status_msg.edit_text(recap, parse_mode="HTML", reply_markup=kb)