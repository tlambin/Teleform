# handlers/admin/suivi.py
"""Module de gestion du suivi des demandes selon organisation_du_code [source 3]"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from utils.validators import convert_utc_to_paris

logger = logging.getLogger(__name__)

class SuiviManager:
    """Gestionnaire du suivi des demandes selon hiérarchie_administrative [source 6]"""

    def __init__(self, db_manager, config):
        self.db_manager = db_manager
        self.config = config

    async def suivre_demande(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Permet à un admin de suivre une demande"""
        query = update.callback_query
        user_id = query.from_user.id

        if not self.config.is_admin(user_id):
            await query.answer("❌ Accès non autorisé")
            return

        try:
            demande_id = int(query.data.split('_')[-1])  # "suivre_demande_123" → 123
        except (IndexError, ValueError) as e:
            logger.error(f"Erreur parsing callback {query.data}: {e}")
            await query.answer("❌ Erreur format callback")
            return

        try:
            with self.db_manager.get_cursor() as cursor:
                # Vérifier si déjà suivi
                cursor.execute("""
                    SELECT id FROM demandes_suivi
                    WHERE demande_id = %s AND admin_id = %s
                """, (demande_id, user_id))

                if cursor.fetchone():
                    await query.answer("❤️️ Vous suivez déjà cette demande")
                    return

                # Ajouter suivi
                cursor.execute("""
                    INSERT INTO demandes_suivi (demande_id, admin_id, date_suivi)
                    VALUES (%s, %s, NOW())
                """, (demande_id, user_id))

                # Changer statut demande selon workflow
                cursor.execute("""
                    UPDATE demandes
                    SET statut = '⏳ En attente', admin_en_charge = %s
                    WHERE id = %s AND statut = '📨 Reçue'
                """, (user_id, demande_id))

                # Récupérer numéro demande pour confirmation
                cursor.execute("SELECT request_number FROM demandes WHERE id = %s", (demande_id,))
                result = cursor.fetchone()

                if result:
                    await query.answer(f"✅ Demande #{result['request_number']} ajoutée à vos suivis")
                else:
                    await query.answer("✅ Demande ajoutée à vos suivis")

        except Exception as e:
            logger.error(f"Erreur suivi demande {demande_id}: {e}")
            await query.answer("❌ Erreur lors du suivi de la demande")

    async def show_demandes_suivies(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Affiche demandes suivies - Messages séparés"""
        query = update.callback_query
        user_id = query.from_user.id

        if not self.config.is_admin(user_id, secure_mode=True):
            await query.answer("❌ Accès non autorisé")
            return

        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute("""
                    SELECT d.*, u.username, u.first_name as user_first_name,
                           ds.date_suivi, ds.notes_admin
                    FROM demandes d
                    JOIN demandes_suivi ds ON d.id = ds.demande_id
                    JOIN users u ON d.user_id = u.user_id
                    WHERE ds.admin_id = %s
                    ORDER BY ds.date_suivi DESC
                    LIMIT 15
                """, (user_id,))

                demandes = cursor.fetchall()

            await query.answer("🔄 Chargement de vos demandes suivies...")

            if not demandes:
                message = (
                    "💌 <b>Mes Demandes Suivies :</b>\n\n"
                    "❤️️ Vous ne suivez aucune demande actuellement."
                )
                keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton("📮 Disponibles", callback_data="demandes_disponibles"),
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
            header_message = f"📋 <b>Mes Demandes Suivies :</b>\n ({len(demandes)} demandes)\n"
            header_keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Actualiser", callback_data="demandes_suivies")
            ]])

            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=header_message,
                parse_mode='HTML',
                reply_markup=header_keyboard
            )

            # UN MESSAGE PAR DEMANDE SUIVIE
            for demande in demandes:
                priorite_icon = "💎" if demande['prioritaire'] else "📝"
                montant_text = f" - {demande['montant']:.2f}€" if demande['prioritaire'] else ""

                nom_complet = demande['prenom']
                if demande['nom']:
                    nom_complet += f" {demande['nom']}"

                date_paris = convert_utc_to_paris(demande['date_creation'])
                date_suivi = convert_utc_to_paris(demande['date_suivi'])

                user_display = f"@{demande['username']}" if demande['username'] else demande['user_first_name']

                message = (
                    f"{priorite_icon} <b>#{demande['request_number']}</b> - {nom_complet}\n"
                    f"🎂 {demande['age']} ans - 📍 {demande['localisation']}\n"
                    f"📷 Instagram: {demande['instagram'] or 'Non renseigné'}\n"
                    f"👻 Snapchat: {demande['snapchat'] or 'Non renseigné'}\n"
                    f"{demande['statut']}{montant_text}\n"
                    f"👤 Demandeur: {user_display}\n"
                    f"📅 <b>Créée le :</b> {date_paris.strftime('%d/%m/%Y %H:%M')}\n"
                    f"💌️ <b>Suivie depuis le :</b> {date_suivi.strftime('%d/%m/%Y %H:%M')}"
                )

                if demande['notes_admin']:
                    notes_court = demande['notes_admin'][:80] + "..." if len(demande['notes_admin']) > 80 else demande['notes_admin']
                    message += f"\n📝 <b>Mes notes:</b> {notes_court}"

                keyboard = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("📷 PHOTO", callback_data=f"voir_photo_{demande['id']}"),
                        InlineKeyboardButton("🔄 STATUT", callback_data=f"change_status_{demande['id']}")
                    ],
                    [
                        InlineKeyboardButton("💬 CONTACTER", callback_data=f"contacter_{demande['id']}")
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
                InlineKeyboardButton("📮 Disponibles", callback_data="demandes_disponibles"),
                InlineKeyboardButton("🔙 Retour", callback_data="start_menu")
            ]])

            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=navigation_message,
                parse_mode='HTML',
                reply_markup=navigation_keyboard
            )

        except Exception as e:
            logger.error(f"Erreur affichage demandes suivies: {e}")
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="❌ Erreur lors de l'affichage des demandes suivies"
            )
