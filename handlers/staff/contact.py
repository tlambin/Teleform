"""Module de messagerie interne permettant au staff et administrateurs de contacter la direction/propriétaires."""

import html
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

logger = logging.getLogger(__name__)


class ContactManager:
    """Gère l'envoi de messages d'un opérateur/admin vers les propriétaires et le traitement des réponses."""

    WAITING_ADMIN_MSG = 1
    WAITING_OWNER_REPLY = 2

    def __init__(self, db_manager, config):
        self.db_manager = db_manager
        self.config = config
        logger.info("ContactManager initialisé avec support Multi-Owner")

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

    # ========== STAFF -> DIRECTION (OWNERS) ==========

    async def start_contact_owner(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Déclenche la saisie du message destiné aux propriétaires."""
        query = update.callback_query
        if not query or not update.effective_user:
            return ConversationHandler.END

        user_id = update.effective_user.id
        if not self.config.is_staff(user_id) or self.config.is_owner(user_id):
            await query.answer("Action réservée aux membres de l'équipe.", show_alert=True)
            return ConversationHandler.END

        await query.answer()

        owner_alias = html.escape(str(self.db_manager.get_owner_alias() or "Direction"))
        staff_alias = html.escape(str(self.db_manager.get_staff_alias(user_id) or f"Membre_{user_id}"))

        text = (
            f"👑 <b>Contacter la Direction ({owner_alias})</b>\n\n"
            f"Votre message sera transmis avec votre alias officiel <b>{staff_alias}</b>.\n\n"
            "Envoyez votre message ci-dessous (texte, photo ou document) :"
        )
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Annuler", callback_data="cancel_contact_owner")
        ]])

        await self._safe_edit_or_send(query, context, text, reply_markup=keyboard)
        return self.WAITING_ADMIN_MSG

    async def send_to_owner(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Transmet le message aux propriétaires du bot."""
        msg = update.message
        if not msg:
            return self.WAITING_ADMIN_MSG

        staff_id = update.effective_user.id
        raw_staff_alias = self.db_manager.get_staff_alias(staff_id) or f"Staff_{staff_id}"
        staff_alias_esc = html.escape(str(raw_staff_alias))

        owners_list = set()
        if hasattr(self.config, "owner_ids") and self.config.owner_ids:
            owners_list.update(self.config.owner_ids)
        elif getattr(self.config, "OWNER_ID", 0):
            owners_list.add(int(self.config.OWNER_ID))
        else:
            db_owner = self.db_manager.get_owner_id()
            if db_owner:
                owners_list.add(int(db_owner))

        if not owners_list:
            await msg.reply_text("❌ Aucun propriétaire n'est configuré sur le bot.")
            return ConversationHandler.END

        header = (
            f"📨 <b>Message interne du membre : {staff_alias_esc}</b>\n"
            f"🆔 ID : <code>{staff_id}</code>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        owner_keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(f"💬 Répondre à {raw_staff_alias}", callback_data=f"owner_reply_to_{staff_id}")
        ]])

        sent_count = 0
        for owner_id in owners_list:
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
                sent_count += 1
            except Exception as send_err:
                logger.warning("Échec envoi vers l'owner %s : %s", owner_id, send_err)

        if sent_count > 0:
            await msg.reply_text(
                "✅ <b>Votre message a été transmis directement à la direction !</b>\n"
                "Vous recevrez une réponse ici dès consultation.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Menu Paramètres", callback_data="parametres")
                ]])
            )
        else:
            await msg.reply_text("❌ Erreur technique lors de la transmission aux propriétaires.")

        return ConversationHandler.END

    async def cancel_contact_owner(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Annule l'envoi de message à la direction."""
        query = update.callback_query
        if query:
            await query.answer()
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Paramètres", callback_data="parametres")]])
            await self._safe_edit_or_send(query, context, "❌ Envoi annulé.", reply_markup=kb)
        return ConversationHandler.END

    # ========== DIRECTION -> STAFF ==========

    async def start_owner_reply(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Déclenche la saisie de la réponse de la direction vers un membre de l'équipe."""
        query = update.callback_query
        if not query or not self.config.is_owner(update.effective_user.id):
            return ConversationHandler.END

        await query.answer()

        try:
            target_staff_id = int(query.data.replace("owner_reply_to_", ""))
        except (ValueError, TypeError):
            await query.answer("❌ Identifiant membre invalide.", show_alert=True)
            return ConversationHandler.END

        context.user_data["target_admin_reply_id"] = target_staff_id
        staff_alias_esc = html.escape(str(self.db_manager.get_staff_alias(target_staff_id) or f"Membre_{target_staff_id}"))

        text = (
            f"💬 <b>Répondre au membre {staff_alias_esc}</b> (ID : <code>{target_staff_id}</code>)\n\n"
            "Tapez votre réponse au clavier (votre alias officiel de direction sera utilisé) :"
        )
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Annuler", callback_data="cancel_owner_reply")
        ]])

        await self._safe_edit_or_send(query, context, text, reply_markup=keyboard)
        return self.WAITING_OWNER_REPLY

    async def send_owner_reply(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Transmet la réponse de la direction au membre cible."""
        msg = update.message
        if not msg or not msg.text:
            return self.WAITING_OWNER_REPLY

        target_staff_id = context.user_data.pop("target_admin_reply_id", None)
        if not target_staff_id:
            await msg.reply_text("❌ Erreur : destinataire introuvable.")
            return ConversationHandler.END

        owner_alias_esc = html.escape(str(self.db_manager.get_owner_alias() or "Direction"))
        texte_reponse = html.escape(msg.text.strip())

        notification_text = (
            f"👑 <b>Réponse de la Direction ({owner_alias_esc})</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"« {texte_reponse} »"
        )
        staff_kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("💬 Répondre à la direction", callback_data="contacter_owner")
        ]])

        try:
            await context.bot.send_message(
                chat_id=target_staff_id,
                text=notification_text,
                parse_mode="HTML",
                reply_markup=staff_kb
            )

            raw_staff_alias = self.db_manager.get_staff_alias(target_staff_id) or f"Membre_{target_staff_id}"
            await msg.reply_text(
                f"✅ <b>Réponse envoyée à {html.escape(str(raw_staff_alias))} avec succès !</b>",
                parse_mode="HTML"
            )
            return ConversationHandler.END

        except Exception as exc:
            logger.error("Erreur envoi réponse propriétaire vers membre %s : %s", target_staff_id, exc)
            await msg.reply_text("❌ Échec lors de la remise du message.")
            return ConversationHandler.END

    async def cancel_owner_reply(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Annule la réponse."""
        context.user_data.pop("target_admin_reply_id", None)
        query = update.callback_query
        if query:
            await query.answer()
            await self._safe_edit_or_send(query, context, "❌ Réponse annulée.")
        return ConversationHandler.END