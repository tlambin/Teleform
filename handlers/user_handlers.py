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

        # Sous-modules métier
        self.compte = CompteManager(db_manager, config)
        self.formulaire = FormulaireManager(db_manager, config, self.compte)
        self.demande = DemandeManager(db_manager, config, self.compte)
        self.edition = EditionManager(db_manager, config)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Affiche l'interface d'accueil adaptée au profil de l'utilisateur."""
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
        """Routeur des callbacks utilisateur avec contrôle du statut du service."""
        query = update.callback_query
        if not query or not query.data:
            return

        await query.answer()
        data = query.data

        # Vérification globale de la disponibilité du service pour les créations
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
            if data.startswith("form_"):
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
        """Routeur des boutons de navigation générale (menus, paramètres, panneaux)."""
        query = update.callback_query
        if not query or not query.data:
            return

        await query.answer()
        user_id = query.from_user.id
        first_name = query.from_user.first_name
        data = query.data

        # Contrôles de sécurité
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
        """Aiguillage des messages texte hors commandes vers l'édition ou le compte."""
        if not update.message or not update.message.text:
            return

        # Priorité au mode édition si actif
        if context.user_data and context.user_data.get("editing"):
            await self.edition.handle_edit_text_input(update, context)
            return

        await self.compte.handle_text_messages(update, context)

    async def voir_demandes(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Accès direct à la liste des demandes."""
        await self.demande.voir_demandes(update, context)

    async def _handle_cancel_demande_placeholder(self, update: Update, data: str):
        """Écran d'attente pour l'annulation future d'une demande."""
        query = update.callback_query
        if not query:
            return

        demande_id = data.replace("cancel_demande_", "")
        await query.edit_message_text(
            f"🚧 <b>Annulation de demande</b>\n\n"
            f"L'annulation de la demande n°<code>{demande_id}</code> n'est pas encore activée.\n"
            f"Cette option sera disponible dans une prochaine mise à jour.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 Mes demandes", callback_data="voir_demandes")],
                [InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")],
            ]),
        )