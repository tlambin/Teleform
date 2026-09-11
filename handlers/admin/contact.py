"""Module de messagerie interne permettant aux administrateurs de contacter le propriétaire."""

import html
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

logger = logging.getLogger(__name__)


class ContactManager:
    """Gère l'envoi de messages d'un admin vers le propriétaire et les réponses."""

    WAITING_ADMIN_MSG = 1
    WAITING_OWNER_REPLY = 2

    def __init__(self, db_manager, config):
        self.db_manager = db_manager
        self.config = config
        logger.info("ContactManager initialisé")

    # ========== ADMIN -> PROPRIÉTAIRE ==========

    async def start_contact_owner(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Déclenche la saisie du message destiné au propriétaire."""
        query = update.callback_query
        if not query or not update.effective_user:
            return ConversationHandler.END

        user_id = update.effective_user.id
        if not self.config.is_admin(user_id) or self.config.is_owner(user_id):
            await query.answer("Action réservée aux administrateurs.", show_alert=True)
            return ConversationHandler.END

        await query.answer()

        owner_alias = html.escape(str(self.db_manager.get_owner_alias() or "Propriétaire"))
        admin_alias = html.escape(str(self.db_manager.get_admin_alias(user_id) or f"Admin_{user_id}"))

        text = (
            f"👑 <b>Contacter le Propriétaire ({owner_alias})</b>\n\n"
            f"Votre message sera transmis avec votre alias officiel <b>{admin_alias}</b>.\n\n"
            "Envoyez votre message ci-dessous (texte, photo ou document) :"
        )
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Annuler", callback_data="cancel_contact_owner")
        ]])

        if query.message and query.message.photo:
            await query.message.delete()
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=text,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
        else:
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)

        return self.WAITING_ADMIN_MSG

    async def send_to_owner(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Transmet le message au propriétaire."""
        msg = update.message
        if not msg:
            return self.WAITING_ADMIN_MSG

        admin_id = update.effective_user.id
        raw_admin_alias = self.db_manager.get_admin_alias(admin_id) or f"Admin_{admin_id}"
        admin_alias_esc = html.escape(str(raw_admin_alias))

        try:
            owner_id = int(self.config.OWNER_ID or self.db_manager.get_owner_id())
        except (ValueError, TypeError):
            owner_id = 0

        if not owner_id:
            await msg.reply_text("❌ Le propriétaire n'est pas configuré sur le bot.")
            return ConversationHandler.END

        header = (
            f"📨 <b>Message interne de l'administrateur : {admin_alias_esc}</b>\n"
            f"🆔 ID : <code>{admin_id}</code>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        owner_keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(f"💬 Répondre à {raw_admin_alias}", callback_data=f"owner_reply_to_{admin_id}")
        ]])

        try:
            if msg.text:
                full_text = f"{header}\n{html.escape(msg.text)}"
                await context.bot.send_message(
                    chat_id=owner_id,
                    text=full_text,
                    parse_mode="HTML",
                    reply_markup=owner_keyboard
                )
            elif msg.photo:
                caption_content = html.escape(msg.caption) if msg.caption else ""
                caption = f"{header}\n{caption_content}".strip()
                await context.bot.send_photo(
                    chat_id=owner_id,
                    photo=msg.photo[-1].file_id,
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=owner_keyboard
                )
            elif msg.document:
                caption_content = html.escape(msg.caption) if msg.caption else ""
                caption = f"{header}\n{caption_content}".strip()
                await context.bot.send_document(
                    chat_id=owner_id,
                    document=msg.document.file_id,
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=owner_keyboard
                )

            await msg.reply_text(
                "✅ <b>Votre message a été transmis directement au propriétaire !</b>\n"
                "Vous recevrez sa réponse ici dès qu'il l'aura consultée.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Menu Paramètres", callback_data="parametres")
                ]])
            )
            return ConversationHandler.END

        except Exception as exc:
            logger.error("Erreur envoi message admin vers propriétaire: %s", exc)
            await msg.reply_text("❌ Erreur technique lors de la transmission au propriétaire.")
            return ConversationHandler.END

    async def cancel_contact_owner(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Annule l'envoi de message au propriétaire."""
        query = update.callback_query
        if query:
            await query.answer()
            await query.edit_message_text(
                "❌ Envoi annulé.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Paramètres", callback_data="parametres")]])
            )
        return ConversationHandler.END

    # ========== PROPRIÉTAIRE -> ADMIN ==========

    async def start_owner_reply(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Déclenche la saisie de la réponse du propriétaire vers un admin."""
        query = update.callback_query
        if not query or not self.config.is_owner(update.effective_user.id):
            return ConversationHandler.END

        await query.answer()

        try:
            target_admin_id = int(query.data.replace("owner_reply_to_", ""))
        except (ValueError, TypeError):
            await query.answer("❌ ID d'administrateur invalide.", show_alert=True)
            return ConversationHandler.END

        context.user_data["target_admin_reply_id"] = target_admin_id
        admin_alias_esc = html.escape(str(self.db_manager.get_admin_alias(target_admin_id) or f"Admin_{target_admin_id}"))

        text = (
            f"💬 <b>Répondre à l'administrateur {admin_alias_esc}</b> (ID : <code>{target_admin_id}</code>)\n\n"
            "Tapez votre réponse au clavier (votre alias officiel de propriétaire sera utilisé) :"
        )
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Annuler", callback_data="cancel_owner_reply")
        ]])

        if query.message and query.message.photo:
            await query.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)
        else:
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)

        return self.WAITING_OWNER_REPLY

    async def send_owner_reply(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Transmet la réponse du propriétaire à l'administrateur cible."""
        msg = update.message
        if not msg or not msg.text:
            return self.WAITING_OWNER_REPLY

        target_admin_id = context.user_data.pop("target_admin_reply_id", None)
        if not target_admin_id:
            await msg.reply_text("❌ Erreur : destinataire introuvable.")
            return ConversationHandler.END

        owner_alias_esc = html.escape(str(self.db_manager.get_owner_alias() or "Propriétaire"))
        texte_reponse = html.escape(msg.text.strip())

        notification_text = (
            f"👑 <b>Réponse du Propriétaire ({owner_alias_esc})</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"« {texte_reponse} »"
        )
        admin_kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("💬 Répondre au propriétaire", callback_data="contacter_owner")
        ]])

        try:
            await context.bot.send_message(
                chat_id=target_admin_id,
                text=notification_text,
                parse_mode="HTML",
                reply_markup=admin_kb
            )

            raw_admin_alias = self.db_manager.get_admin_alias(target_admin_id) or f"Admin_{target_admin_id}"
            await msg.reply_text(
                f"✅ <b>Réponse envoyée à {html.escape(str(raw_admin_alias))} avec succès !</b>",
                parse_mode="HTML"
            )
            return ConversationHandler.END

        except Exception as exc:
            logger.error("Erreur envoi réponse propriétaire vers admin %s : %s", target_admin_id, exc)
            await msg.reply_text("❌ Échec lors de la remise du message à l'administrateur.")
            return ConversationHandler.END

    async def cancel_owner_reply(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Annule la réponse du propriétaire."""
        context.user_data.pop("target_admin_reply_id", None)
        query = update.callback_query
        if query:
            await query.answer()
            await query.edit_message_text("❌ Réponse annulée.")
        return ConversationHandler.END