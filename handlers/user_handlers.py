import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from utils.interface_manager import InterfaceManager
from .user.compte import CompteManager
from .user.demande import DemandeManager
from .user.edition import EditionManager
from .user.formulaire import FormulaireManager

logger = logging.getLogger(__name__)


class UserHandlers:
    def __init__(self, config, db_manager):
        self.config = config
        self.db_manager = db_manager
        self.interface = InterfaceManager(config, db_manager)

        self.compte = CompteManager(db_manager, config)
        self.formulaire = FormulaireManager(db_manager, config, self.compte)
        self.demande = DemandeManager(db_manager, config, self.compte)
        self.edition = EditionManager(db_manager, config)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.effective_user or not update.message:
            return

        await self.compte.ensure_user_registered(update)
        user_id = update.effective_user.id

        welcome_msg, reply_markup = self.interface.get_start_interface(
            user_id, update.effective_user.first_name
        )

        await update.message.reply_text(
            welcome_msg,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )

    async def handle_callbacks(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if not query or not query.data:
            return

        await query.answer()
        data = query.data

        if data.startswith(("form_", "nav_")) and not self.config.are_demandes_enabled():
            await query.edit_message_text(
                "🚫 <b>Service temporairement indisponible</b>\n\n"
                "La création et la navigation des demandes sont actuellement désactivées par l'administration.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")]
                ]),
            )
            return

        try:
            if data.startswith("reply_to_admin_"):
                # Suppression immédiate du bouton pour garantir l'usage unique
                try:
                    await query.edit_message_reply_markup(reply_markup=None)
                except Exception:
                    pass

                parts = data.split("_")
                demande_id = int(parts[3])
                admin_id = int(parts[4])
                context.user_data["replying_to_admin"] = {
                    "demande_id": demande_id,
                    "admin_id": admin_id,
                }
                await query.message.reply_text(
                    "✍️ <b>Tapez votre réponse ou envoyez votre fichier ci-dessous :</b>\n\n"
                    "⚠️ <i>Attention : vous ne disposez que d'une seule réponse autorisée pour ce message.</i>",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("❌ Annuler", callback_data="cancel_user_reply")
                    ]])
                )
            elif data == "cancel_user_reply":
                context.user_data.pop("replying_to_admin", None)
                await query.edit_message_text("❌ Réponse annulée.")
            elif data.startswith("form_"):
                await self.formulaire.navigation.handle_form_navigation(update, context)
            elif data.startswith("nav_"):
                await self.demande.handle_navigation(update, context, data)
            elif data.startswith("modify_"):
                await self.edition.handle_modify_request(update, context, data)
            elif data.startswith("edit_"):
                await self.edition.handle_edit_field(update, context, data)
            elif data.startswith("delete_"):
                await self.edition.handle_delete_request(update, context, data)
            elif data.startswith("confirm_delete_"):
                await self.edition.handle_confirm_delete(update, context, data)
            elif data.startswith("cancel_demande_"):
                await self._handle_cancel_demande_placeholder(update, data)
            elif data == "cancel_edit":
                await self.edition.handle_cancel_edit(update, context)
            else:
                await query.answer("❌ Action non reconnue", show_alert=True)

        except Exception as exc:
            logger.error("Erreur callback %s: %s", data, exc, exc_info=True)
            await query.edit_message_text(
                "❌ Une erreur est survenue lors du traitement de votre demande.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Retour au menu", callback_data="start_menu")]
                ]),
            )

    async def handle_interface_callbacks(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if not query or not query.data:
            return

        await query.answer()
        user_id = query.from_user.id
        first_name = query.from_user.first_name
        data = query.data

        owner_actions = {
            "gerer_admins", "admin_ajouter", "admin_supprimer",
            "gerer_bot", "bot_on", "bot_off", "bot_maintenance"
        }
        if data in owner_actions and not self.config.is_owner(user_id):
            await query.answer("❌ Accès réservé au propriétaire.", show_alert=True)
            return

        admin_actions = {
            "gerer_demandes", "demandes_disponibles", "demandes_suivies",
            "parametres", "modifier_alias"
        }
        if data in admin_actions and not self.config.is_admin(user_id):
            await query.answer("❌ Accès administrateur requis.", show_alert=True)
            return

        if data == "voir_demandes":
            await self.demande.voir_demandes(update, context)
            return

        message, keyboard = self.interface.route_callback(data, user_id, first_name)
        if message and keyboard:
            await query.edit_message_text(
                message,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
        else:
            await query.answer("❌ Action indisponible.", show_alert=True)

    async def handle_text_messages(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Aiguillage des messages (texte et médias) hors commandes."""
        if not update.message:
            return

        # 1. Collecte des fichiers/messages de l'Admin en cours d'envoi
        if context.user_data and context.user_data.get("contact_session"):
            from handlers.admin_handlers import AdminHandlers
            admin_h = AdminHandlers(self.config, self.db_manager)
            if await admin_h.handle_collect_admin_media(update, context):
                return

        # 2. Réponse du Demandeur vers l'Admin
        if context.user_data and context.user_data.get("replying_to_admin"):
            await self._handle_user_reply_relay(update, context)
            return

        # 3. Édition d'une demande par l'utilisateur (texte)
        if update.message.text and context.user_data and context.user_data.get("editing"):
            await self.edition.handle_edit_text_input(update, context)
            return

        # 4. Fallback compte utilisateur
        await self.compte.handle_text_messages(update, context)

    async def _handle_user_reply_relay(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Transmet la réponse unique de l'utilisateur vers l'admin."""
        reply_info = context.user_data.pop("replying_to_admin", None)
        if not reply_info:
            return

        admin_id = reply_info["admin_id"]
        demande_id = reply_info["demande_id"]
        user = update.effective_user
        msg = update.message

        user_label = f"@{user.username}" if user.username else f"{user.first_name} (ID: {user.id})"
        user_comment = (msg.caption or msg.text or "").strip()
        corps = f"\n\n« {user_comment} »" if user_comment else ""

        admin_keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("💬 Répondre à nouveau", callback_data=f"contacter_{demande_id}"),
            InlineKeyboardButton("📄 Voir la fiche", callback_data=f"retour_texte_{demande_id}")
        ]])

        try:
            caption_text = (
                f"📩 <b>Réponse du demandeur (Demande #{demande_id})</b>\n"
                f"De : {user_label}"
                f"{corps}"
            )

            await context.bot.copy_message(
                chat_id=admin_id,
                from_chat_id=msg.chat_id,
                message_id=msg.message_id,
                caption=caption_text,
                parse_mode="HTML",
                reply_markup=admin_keyboard,
            )

            await msg.reply_text(
                "✅ <b>Votre réponse a été transmise à l'administrateur !</b>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Mes demandes", callback_data="voir_demandes")
                ]])
            )

        except Exception as exc:
            logger.error("Erreur renvoi réponse utilisateur vers admin %s : %s", admin_id, exc)
            await msg.reply_text("❌ Une erreur est survenue lors de la transmission de votre message.")

    async def voir_demandes(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.demande.voir_demandes(update, context)

    async def _handle_cancel_demande_placeholder(self, update: Update, data: str):
        query = update.callback_query
        if not query:
            return

        demande_id = data.replace("cancel_demande_", "")
        await query.edit_message_text(
            f"🚧 <b>Annulation de demande</b>\n\n"
            f"L'annulation de la demande n°<code>{demande_id}</code> n'est pas encore activée.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 Mes demandes", callback_data="voir_demandes")],
                [InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")],
            ]),
        )