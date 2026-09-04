"""Routeur principal des actions et callbacks d'administration."""

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from utils.interface_manager import InterfaceManager

from .admin.alias import AliasManager
from .admin.dispo import DispoManager
from .admin.photos import PhotosManager
from .admin.statuts import StatutsManager
from .admin.suivi import SuiviManager

logger = logging.getLogger(__name__)


class AdminHandlers:
    """Gestionnaire central des fonctionnalités administrateur."""

    def __init__(self, config, db_manager):
        self.config = config
        self.db_manager = db_manager
        self.interface = InterfaceManager(config, db_manager)

        # Liste unifiée des statuts
        self.statuts_disponibles = [
            "📨 Reçue",
            "⏳ En attente",
            "🔄 En cours",
            "✅ Réussie",
            "⚠️ Difficile",
            "❌ Abandonnée",
        ]

        # Sous-modules administrateur
        self.suivi = SuiviManager(db_manager, config)
        self.statuts = StatutsManager(db_manager, config, self.statuts_disponibles)
        self.photos = PhotosManager(db_manager, config)
        self.dispo = DispoManager(db_manager, config)
        self.alias = AliasManager(db_manager, config)

    async def handle_admin_callbacks(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Aiguillage sécurisé des callbacks administrateurs."""
        query = update.callback_query
        if not query or not update.effective_user:
            return

        user_id = update.effective_user.id
        data = query.data or ""

        # Contrôle strict des privilèges
        if not self.config.is_admin(user_id, secure_mode=True):
            logger.warning("Tentative d'accès administrateur refusée pour l'utilisateur %s", user_id)
            await query.answer("❌ Accès non autorisé.", show_alert=True)
            return

        await query.answer()

        try:
            # 1. Demandes disponibles (non assignées)
            if data == "demandes_disponibles":
                await self.dispo.show_demandes_disponibles(update, context)

            elif data.startswith("dispo_"):
                await self._route_dispo_pagination(update, context, data)

            # 2. Demandes suivies (prises en charge par l'admin)
            elif data == "demandes_suivies":
                await self.suivi.show_demandes_suivies(update, context)

            elif data.startswith("suivi_"):
                await self._route_suivi_pagination(update, context, data)

            # 3. Gestion des photos et médias
            elif data.startswith("voir_photo_"):
                await self.photos.voir_photo_demande(update, context)

            elif data.startswith("retour_texte_"):
                await self.photos.retour_texte_demande(update, context)

            # 4. Prise en charge et assignation
            elif data.startswith("suivre_demande_"):
                await self.suivi.suivre_demande(update, context)

            # 5. Modification de statut
            elif data.startswith("change_status_"):
                demande_id = int(data.split("_")[2])
                await self.statuts.show_status_change_menu(update, context, demande_id)

            elif data.startswith("set_status_"):
                await self.statuts.set_status_demande(update, context)

            # 6. Actions rapides et contact
            elif data.startswith("mark_treated_menu_"):
                demande_id = int(data.replace("mark_treated_menu_", ""))
                await self.statuts.show_status_change_menu(update, context, demande_id)

            elif data.startswith("contacter_"):
                demande_id = int(data.replace("contacter_", ""))
                await self._handle_contact_user(update, demande_id)

            else:
                logger.warning("Callback admin non intercepté: %s", data)
                await query.answer("Action non reconnue.", show_alert=True)

        except Exception as exc:
            logger.error("Erreur lors du traitement du callback admin '%s': %s", data, exc, exc_info=True)
            await self._handle_callback_error(query)

    async def _route_dispo_pagination(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Gère la pagination des demandes disponibles."""
        parts = data.split("_")
        page = 0
        if len(parts) >= 3 and parts[-1].isdigit():
            current_idx = int(parts[-1])
            if "prev" in data:
                page = max(0, current_idx - 1)
            elif "next" in data:
                page = current_idx + 1
        await self.dispo.show_demandes_disponibles_page(update, context, page)

    async def _route_suivi_pagination(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Gère la pagination des demandes suivies."""
        parts = data.split("_")
        page = 0
        if len(parts) >= 3 and parts[-1].isdigit():
            current_idx = int(parts[-1])
            if "prev" in data:
                page = max(0, current_idx - 1)
            elif "next" in data:
                page = current_idx + 1
        await self.suivi.show_demandes_suivies_page(update, context, page)

    async def _handle_contact_user(self, update: Update, demande_id: int):
        """Affiche les coordonnées directes de l'utilisateur pour prise de contact."""
        query = update.callback_query
        if not query:
            return

        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT d.id, d.user_id, d.prenom, d.nom, d.instagram, d.snapchat,
                           u.username, u.first_name
                    FROM demandes d
                    LEFT JOIN users u ON d.user_id = u.user_id
                    WHERE d.id = %s
                    """,
                    (demande_id,),
                )
                row = cursor.fetchone()

            if not row:
                await query.answer("❌ Demande introuvable.", show_alert=True)
                return

            contact_lines = [f"📞 <b>Contact pour la demande #{row['id']}</b>\n"]
            if row.get("username"):
                contact_lines.append(f"🔹 <b>Telegram :</b> @{row['username']}")
            else:
                contact_lines.append(f"🔹 <b>Telegram ID :</b> <code>{row['user_id']}</code>")

            if row.get("instagram"):
                contact_lines.append(f"📷 <b>Instagram :</b> @{row['instagram']}")
            if row.get("snapchat"):
                contact_lines.append(f"👻 <b>Snapchat :</b> {row['snapchat']}")

            await query.edit_message_text(
                "\n".join(contact_lines),
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("↩️ Retour aux détails", callback_data=f"retour_texte_{demande_id}")
                ]])
            )
        except Exception as exc:
            logger.error("Erreur contact utilisateur: %s", exc)
            await query.answer("❌ Impossible de charger les contacts.", show_alert=True)

    async def _handle_callback_error(self, query):
        """Gère proprement l'affichage des erreurs que le message soit un texte ou une photo."""
        try:
            if query.message and query.message.photo:
                await query.answer("❌ Une erreur technique est survenue.", show_alert=True)
            else:
                await query.edit_message_text(
                    "❌ <b>Erreur technique</b> lors du traitement de l'action admin.",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 Menu Admin", callback_data="gerer_demandes")
                    ]])
                )
        except Exception as fallback_exc:
            logger.error("Échec notification erreur admin: %s", fallback_exc)
            await query.answer("❌ Erreur système.")