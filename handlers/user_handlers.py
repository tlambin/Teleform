import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from utils.interface_manager import InterfaceManager
from .user.compte import CompteManager
from .user.formulaire import FormulaireManager
from .user.demande import DemandeManager
from .user.edition import EditionManager

logger = logging.getLogger(__name__)

class UserHandlers:
    def __init__(self, config, db_manager):
        self.config = config
        self.db_manager = db_manager
        self.interface = InterfaceManager(config, db_manager)

        # Modules spécialisés
        self.compte = CompteManager(db_manager, config)
        self.formulaire = FormulaireManager(db_manager, config, self.compte)
        self.demande = DemandeManager(db_manager, config, self.compte)
        self.edition = EditionManager(db_manager, config)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Interface start adaptative - Version interface manager"""
        await self.compte.ensure_user_registered(update)

        user_id = update.effective_user.id

        # Utilisation du nouveau gestionnaire d'interface
        welcome_msg, reply_markup = self.interface.get_start_interface(user_id, update.effective_user.first_name)

        await update.message.reply_text(
            welcome_msg,
            parse_mode='HTML',
            reply_markup=reply_markup
        )

    async def handle_callbacks(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Routing callbacks CRUD demandes vers modules spécialisés"""
        query = update.callback_query
        await query.answer()
        data = query.data

        try:
            if data.startswith("form_"):
                # Déléguer au NavigationManager du formulaire
                return await self.formulaire.navigation.handle_form_navigation(update, context)
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
                await query.answer("❌ Action non reconnue")

        except Exception as e:
            logger.error(f"Erreur callback {data}: {e}")
            await query.edit_message_text("❌ Erreur lors du traitement")


    async def handle_interface_callbacks(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Routing callbacks interface via InterfaceManager"""
        query = update.callback_query
        await query.answer()

        user_id = query.from_user.id
        first_name = query.from_user.first_name

        # Vérifications de permissions
        if query.data in ["gerer_admins", "admin_ajouter", "admin_supprimer", "gerer_bot", "bot_on", "bot_off", "bot_maintenance"] and not self.config.is_owner(user_id):
            await query.answer("❌ Accès propriétaire requis", show_alert=True)
            return

        if query.data in ["gerer_demandes", "demandes_disponibles", "demandes_suivies", "parametres", "modifier_alias"] and not (self.config.is_admin(user_id) or self.config.is_owner(user_id)):
            await query.answer("❌ Accès administrateur requis", show_alert=True)
            return

        # Routing spécialisé
        if query.data == "voir_demandes":
            await self.demande.voir_demandes(update, context)
            return

        # Délégation InterfaceManager (gère start_menu, retours, etc.)
        message, keyboard = self.interface.route_callback(query.data, user_id, first_name)

        if message and keyboard:
            await query.edit_message_text(
                message,
                parse_mode='HTML',
                reply_markup=keyboard
            )
        else:
            await query.answer("❌ Action non reconnue")

    async def handle_user_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Router principal avec vérification état demandes"""
        query = update.callback_query
        callback_data = query.data

        # Vérification pour les callbacks de création de demandes
        if callback_data.startswith(('form_', 'nav_')):
            if not self.config.are_demandes_enabled():
                await query.answer("🚫 Création de demandes désactivée")
                await query.edit_message_text(
                    "🚫 **Service temporairement indisponible**\n\n"
                    "La création de demandes est actuellement désactivée.",
                    parse_mode='Markdown'
                )
                return

    async def handle_text_messages(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Route vers CompteManager + gestion édition selon ÉTAPE 5"""

        # Mode édition → EditionManager
        if 'editing' in context.user_data:
            await self.edition.handle_edit_text_input(update, context)
            return

        # Messages généraux → CompteManager
        return await self.compte.handle_text_messages(update, context)

    async def voir_demandes(self, update, context):
        """Route vers DemandeManager"""
        return await self.demande.voir_demandes(update, context)

    async def _handle_cancel_demande_placeholder(self, update: Update, data: str):
        """Placeholder pour annulation de demande (fonctionnalité future)"""
        query = update.callback_query

        # Extraire ID demande
        demande_id = data.replace("cancel_demande_", "")

        await query.edit_message_text(
            f"🚧 <b>Annulation Demande</b>\n\n"
            f"La fonctionnalité d'annulation de la demande n°{demande_id} "
            f"sera disponible prochainement.\n\n"
            f"Cette action permettra d'annuler une demande en cours de traitement.",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 Retour à mes demandes", callback_data="voir_demandes")],
                [InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")]
            ])
        )

