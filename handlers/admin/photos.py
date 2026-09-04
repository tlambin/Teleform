# handlers/admin/photos.py
"""Module de gestion des photos selon interface moderne"""

import logging
from telegram import Update, InputMediaPhoto, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from utils.validators import convert_utc_to_paris

logger = logging.getLogger(__name__)

class PhotosManager:
    """Gestionnaire des photos intégrées selon interface moderne"""

    def __init__(self, db_manager, config):
        self.db_manager = db_manager
        self.config = config

    async def voir_photo_demande(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Affiche photo intégrée"""
        query = update.callback_query
        user_id = query.from_user.id

        if not self.config.is_admin(user_id):
            await query.answer("❌ Accès non autorisé")
            return

        # Extraire ID demande du callback
        try:
            demande_id = int(query.data.split('_')[2])
        except (IndexError, ValueError):
            await query.answer("❌ Erreur format callback")
            return

        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute("""
                    SELECT d.*, u.username, u.first_name as user_first_name
                    FROM demandes d
                    JOIN users u ON d.user_id = u.user_id
                    WHERE d.id = %s
                """, (demande_id,))

                demande = cursor.fetchone()

                if not demande:
                    await query.answer("❌ Demande non trouvée")
                    return

                if not demande['photo_id']:
                    await query.answer("📷 Aucune photo disponible pour cette demande")
                    return

                # CRÉER CAPTION avec détails demande selon traitement_image [source 6]
                priorite_icon = "💎" if demande['prioritaire'] else "📝"
                montant_text = f" - {demande['montant']:.2f}€" if demande['prioritaire'] else ""

                nom_complet = demande['prenom']
                if demande['nom']:
                    nom_complet += f" {demande['nom']}"

                date_paris = convert_utc_to_paris(demande['date_creation'])

                user_display = f"@{demande['username']}" if demande['username'] else demande['user_first_name']

                # CAPTION COMPLÈTE selon amélioration_interfaces [source 5]
                caption = (
                    f"📷 <b>PHOTO DEMANDE</b>\n\n"
                    f"{priorite_icon} <b>#{demande['request_number']}</b> - {nom_complet}\n"
                    f"🎂 {demande['age']} ans - 📍 {demande['localisation']}\n"
                    f"📱 Instagram: {demande['instagram'] or 'Non renseigné'}\n"
                    f"👻 Snapchat: {demande['snapchat'] or 'Non renseigné'}\n"
                    f"📊 {demande['statut']}{montant_text}\n"
                    f"👤 Demandeur: {user_display}\n"
                    f"📅 <b>Date:</b> {date_paris.strftime('%d/%m/%Y %H:%M')}"
                )

                if demande['details']:
                    details_court = demande['details'][:100] + "..." if len(demande['details']) > 100 else demande['details']
                    caption += f"\n💬 <b>Détails:</b> {details_court}"

                # BOUTONS selon visualisation_images [source 5]
                keyboard = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("🔄 STATUT", callback_data=f"change_status_{demande['id']}"),
                        InlineKeyboardButton("💬 CONTACTER", callback_data=f"contacter_{demande['id']}")
                    ]
                ])

                # REMPLACER MESSAGE PAR PHOTO selon editMessageMedia [source 3]
                media = InputMediaPhoto(
                    media=demande['photo_id'],
                    caption=caption,
                    parse_mode='HTML'
                )

                await query.edit_message_media(
                    media=media,
                    reply_markup=keyboard
                )

                await query.answer("📷 Photo affichée dans le message !")

        except Exception as e:
            logger.error(f"Erreur affichage photo intégrée {demande_id}: {e}")
            await query.answer("❌ Erreur lors de l'affichage de la photo")
