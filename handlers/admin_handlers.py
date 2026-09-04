import logging
from telegram import Update
from telegram.ext import ContextTypes
from utils.interface_manager import InterfaceManager

from .admin.suivi import SuiviManager
from .admin.statuts import StatutsManager
from .admin.photos import PhotosManager
from .admin.dispo import DispoManager
from .admin.alias import AliasManager

logger = logging.getLogger(__name__)

class AdminHandlers:
    def __init__(self, config, db_manager):
        self.config = config
        self.db_manager = db_manager
        self.interface = InterfaceManager(config, db_manager)

        # États pour les demandes
        self.statuts_disponibles = [
            '📨 Reçue', '⏳ En attente', '🔄 En cours',
            '✅ Réussie', '⚠️ Difficile', '❌ Abandonnée'
        ]

        # INSTANCIATION des gestionnaires spécialisés
        self.suivi = SuiviManager(db_manager, config)
        self.statuts = StatutsManager(db_manager, config, self.statuts_disponibles)
        self.photos = PhotosManager(db_manager, config)
        self.dispo = DispoManager(db_manager, config)
        self.alias = AliasManager(db_manager, config)


    async def handle_admin_callbacks(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Gère tous les callbacks des boutons admin"""
        query = update.callback_query
        user_id = update.effective_user.id
        data = query.data

        if not self.config.is_admin(user_id, secure_mode=True):
            logger.error(f"❌ ACCÈS REFUSÉ pour {user_id}")
            await query.answer("❌ Accès non autorisé")
            return

        await query.answer()

        try:
            if query.data == "demandes_disponibles":
                await self.dispo.show_demandes_disponibles(update, context)
            elif query.data.startswith("dispo_"):
                # Navigation pagination demandes disponibles
                if "prev_" in query.data:
                    page = int(query.data.split("_")[-1]) - 1
                elif "next_" in query.data:
                    page = int(query.data.split("_")[-1]) + 1
                else:
                    page = 0
                await self.dispo.show_demandes_disponibles_page(update, context, page)
            elif query.data == "demandes_suivies":
                await self.suivi.show_demandes_suivies(update, context)
            elif query.data.startswith("suivi_"):
                # Navigation pagination demandes suivies
                if "prev_" in query.data:
                    page = int(query.data.split("_")[-1]) - 1
                elif "next_" in query.data:
                    page = int(query.data.split("_")[-1]) + 1
                else:
                    page = 0
                await self.suivi.show_demandes_suivies_page(update, context, page)
            elif data.startswith("voir_photo_"):
                await self.photos.voir_photo_demande(update, context)
            elif data.startswith("retour_texte_"):
                await self.photos.retour_texte_demande(update, context)
            elif data.startswith("suivre_demande_"):
                await self.suivi.suivre_demande(update, context)
            elif data.startswith("change_status_"):
                demande_id = int(data.split('_')[2])
                await self.statuts.show_status_change_menu(update, context, demande_id)
            elif data.startswith("set_status_"):
                await self.statuts.set_status_demande(update, context)

        except Exception as e:
            logger.error(f"Erreur callback admin {data}: {e}")
            try:
                is_photo_message = bool(query.message.photo)
                if is_photo_message:
                    await query.answer("❌ Erreur lors du traitement", show_alert=True)
                else:
                    await query.edit_message_text("❌ Erreur lors du traitement")
            except Exception as e2:
                logger.error(f"Erreur gestion erreur callback: {e2}")
                await query.answer("❌ Erreur système")
