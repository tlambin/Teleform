# handlers/admin/dispo.py
"""Module de gestion des demandes disponibles"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from utils.validators import convert_utc_to_paris

logger = logging.getLogger(__name__)

class DispoManager:
    """Gestionnaire des demandes disponibles """

    def __init__(self, db_manager, config):
        self.db_manager = db_manager
        self.config = config

    async def show_demandes_disponibles(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Affiche demandes disponibles - Messages séparés"""
        query = update.callback_query
        user_id = query.from_user.id

        if not self.config.is_admin(user_id, secure_mode=True):
            await query.answer("❌ Accès non autorisé")
            return

        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute("""
                    SELECT d.*, u.username, u.first_name as user_first_name
                    FROM demandes d
                    JOIN users u ON d.user_id = u.user_id
                    LEFT JOIN demandes_suivi ds ON d.id = ds.demande_id AND ds.admin_id = %s
                    WHERE ds.demande_id IS NULL
                    AND d.statut IN ('📨 Reçue', '⏳ En attente')
                    ORDER BY d.prioritaire DESC, d.date_creation DESC
                    LIMIT 10
                """, (user_id,))

                demandes = cursor.fetchall()

            await query.answer("🔄 Chargement des demandes disponibles...")

            if not demandes:
                message = (
                    "📮 <b>Demandes Disponibles :</b>\n\n"
                    "🔍 Aucune nouvelle demande disponible."
                )
                keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔄 Actualiser", callback_data="demandes_disponibles"),
                    InlineKeyboardButton("🔙 Retour", callback_data="start_menu")
                ]])
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=message,
                    parse_mode='HTML',
                    reply_markup=keyboard
                )
                return

            # EN-TÊTE
            header_message = f"📮 <b>Demandes Disponibles :</b>\n ({len(demandes)} demandes)\n"
            header_keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Actualiser", callback_data="demandes_disponibles")
            ]])

            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=header_message,
                parse_mode='HTML',
                reply_markup=header_keyboard
            )

            # UN MESSAGE PAR DEMANDE
            for demande in demandes:
                priorite_icon = "💎" if demande['prioritaire'] else "📝"
                montant_text = f" - {demande['montant']:.2f}€" if demande['prioritaire'] else ""

                nom_complet = demande['prenom']
                if demande['nom']:
                    nom_complet += f" {demande['nom']}"

                date_paris = convert_utc_to_paris(demande['date_creation'])

                user_display = f"@{demande['username']}" if demande['username'] else demande['user_first_name']

                message = (
                    f"{priorite_icon} <b>#{demande['request_number']}</b> - {nom_complet}\n"
                    f"🎂 {demande['age']} ans - 📍 {demande['localisation']}\n"
                    f"📷 Instagram: {demande['instagram'] or 'Non renseigné'}\n"
                    f"👻 Snapchat: {demande['snapchat'] or 'Non renseigné'}\n"
                    f"{demande['statut']}{montant_text}\n"
                    f"👤 Demandeur: {user_display}\n"
                    f"📅 <b>Date:</b> {date_paris.strftime('%d/%m/%Y %H:%M')}"
                )

                if demande['details']:
                    details_court = demande['details'][:100] + "..." if len(demande['details']) > 100 else demande['details']
                    message += f"\n💬 <b>Détails:</b> {details_court}"

                keyboard = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("📷 PHOTO", callback_data=f"voir_photo_{demande['id']}"),
                        InlineKeyboardButton("❤️️ SUIVRE", callback_data=f"suivre_demande_{demande['id']}")
                    ]
                ])

                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=message,
                    parse_mode='HTML',
                    reply_markup=keyboard
                )

            # NAVIGATION EN BAS
            navigation_message = "🧭 <b>Barre de Navigation</b>"
            navigation_keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("💌 Suivies", callback_data="demandes_suivies"),
                InlineKeyboardButton("🔙 Retour", callback_data="start_menu")
            ]])

            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=navigation_message,
                parse_mode='HTML',
                reply_markup=navigation_keyboard
            )

        except Exception as e:
            logger.error(f"Erreur affichage demandes disponibles: {e}")
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="❌ Erreur lors de l'affichage des demandes disponibles"
            )

