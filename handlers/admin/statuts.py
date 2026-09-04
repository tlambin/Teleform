# handlers/admin/statuts.py
"""Module de gestion des statuts selon administration_système"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from .alias import AliasManager

logger = logging.getLogger(__name__)

class StatutsManager:
    """Gestionnaire des changements de statuts selon [source 4]"""

    def __init__(self, db_manager, config, statuts_disponibles):
        self.db_manager = db_manager
        self.config = config
        self.statuts_disponibles = statuts_disponibles
        self.alias_manager = AliasManager(db_manager, config)

    async def show_status_change_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE, demande_id: int):
        """Menu changement statut"""
        query = update.callback_query

        if not self.config.is_admin(query.from_user.id):
            await query.answer("❌ Accès non autorisé")
            return

        try:
            # RÉCUPÉRER info demande
            with self.db_manager.get_cursor() as cursor:
                cursor.execute("""
                    SELECT request_number, prenom, nom, statut
                    FROM demandes WHERE id = %s
                """, (demande_id,))

                demande = cursor.fetchone()

                if not demande:
                    await query.answer("❌ Demande non trouvée")
                    return

                nom_complet = f"{demande['prenom']} {demande['nom'] or ''}".strip()

            # Menu statut
            keyboard = []
            for i, statut in enumerate(self.statuts_disponibles):
                keyboard.append([
                    InlineKeyboardButton(statut, callback_data=f"set_status_{demande_id}_{i}")
                ])

            keyboard.append([
                InlineKeyboardButton("🔙 Retour", callback_data=f"voir_photo_{demande_id}")
            ])

            message = (
                f"📊 <b>Changer le Statut</b>\n\n"
                f"📝 <b>Demande #{demande['request_number']}</b> - {nom_complet}\n"
                f"📊 <b>Statut actuel :</b> {demande['statut']}\n\n"
                f"Sélectionnez le nouveau statut :"
            )

            # ✅ MODIFICATION selon type selon [source 1]
            if hasattr(query.message, 'photo') and query.message.photo:
                # Photo → editMessageCaption selon [source 1]
                await query.edit_message_caption(
                    caption=message,
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            else:
                # Texte → editMessageText
                await query.edit_message_text(
                    text=message,
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )

        except Exception as e:
            logger.error(f"Erreur menu statut photo/texte: {e}")
            await query.answer("❌ Erreur affichage menu statut")

    async def set_status_demande(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Application changement statut]"""
        query = update.callback_query
        admin_user_id = query.from_user.id

        if not self.config.is_admin(admin_user_id):
            await query.answer("❌ Accès non autorisé")
            return

        try:
            parts = query.data.split('_')
            demande_id = int(parts[2])        # "set_status_123_2" → parts[2] = "123"
            status_index = int(parts[3])      # "set_status_123_2" → parts[3] = "2"

            # VÉRIFICATION
            if status_index >= len(self.statuts_disponibles):
                await query.answer("❌ Index statut invalide")
                return

            nouveau_statut = self.statuts_disponibles[status_index]

            with self.db_manager.get_cursor() as cursor:
                admin_alias = await self.alias_manager.get_admin_alias(admin_user_id)

                # Récupérer les infos de la demande
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

                old_status = demande['statut']
                user_id_demande = demande['user_id']
                prenom = demande['prenom']
                request_number = demande['request_number']

                # Mettre à jour le statut
                cursor.execute("""
                    UPDATE demandes
                    SET statut = %s, admin_en_charge = %s, date_modification = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (nouveau_statut, admin_user_id, demande_id))

                if cursor.rowcount > 0:
                    # NOTIFICATION
                    await self.alias_manager.send_status_notification(
                        context, user_id_demande, request_number, prenom, old_status, nouveau_statut, admin_alias
                    )

                    # CACHE
                    self.db_manager.clear_cache()

                    # CONFIRMATION
                    if hasattr(query.message, 'photo') and query.message.photo:
                        # 📷 MESSAGE PHOTO OUVERT → Modifier directement
                        await self._update_photo_caption(query, demande, nouveau_statut, request_number)
                    else:
                        # 📝 MESSAGE TEXTE → Modifier directement selon [source 1]
                        await self._update_existing_text_message(query, demande, nouveau_statut, request_number)

                else:
                    await query.answer("❌ Demande non trouvée")

        except (IndexError, ValueError) as e:
            logger.error(f"Erreur parsing callback statut adapté {query.data}: {e}")
            await query.answer("❌ Erreur format callback")
        except Exception as e:
            logger.error(f"Erreur application statut adapté: {e}")
            await query.answer("❌ Erreur lors de la mise à jour")

    async def _update_existing_text_message(self, query, demande, nouveau_statut, request_number):
        """Met à jour le message texte existant selon [source 1]"""
        from utils.validators import convert_utc_to_paris

        priorite_icon = "💎" if demande['prioritaire'] else "📝"
        montant_text = f" - {demande['montant']:.2f}€" if demande['prioritaire'] else ""

        nom_complet = demande['prenom']
        if demande['nom']:
            nom_complet += f" {demande['nom']}"

        date_paris = convert_utc_to_paris(demande['date_creation'])
        user_display = f"@{demande['username']}" if demande['username'] else demande['user_first_name']

        # ✅ MESSAGE MODIFIÉ avec nouveau statut selon [source 1]
        message = (
            f"{priorite_icon} <b>#{demande['request_number']}</b> - {nom_complet}\n"
            f"🎂 {demande['age']} ans - 📍 {demande['localisation']}\n"
            f"📱 Instagram: {demande['instagram'] or 'Non renseigné'}\n"
            f"👻 Snapchat: {demande['snapchat'] or 'Non renseigné'}\n"
            f"<b>{nouveau_statut}</b>{montant_text}\n"
            f"👤 Demandeur: {user_display}\n"
            f"📅 <b>Date:</b> {date_paris.strftime('%d/%m/%Y %H:%M')}"
        )

        if demande['details']:
            details_court = demande['details'][:100] + "..." if len(demande['details']) > 100 else demande['details']
            message += f"\n💬 <b>Détails:</b> {details_court}"

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📷 PHOTO", callback_data=f"voir_photo_{demande['id']}"),
                InlineKeyboardButton("🔄 STATUT", callback_data=f"change_status_{demande['id']}")
            ],
            [
                InlineKeyboardButton("💬 CONTACTER", callback_data=f"contacter_{demande['id']}")
            ]
        ])

        await query.edit_message_text(
            text=message,
            parse_mode='HTML',
            reply_markup=keyboard
        )

        await query.answer(f"✅ Statut demande #{request_number} → {nouveau_statut}")

    async def _update_photo_caption(self, query, demande, nouveau_statut, request_number):
        """Modifie caption photo avec nouveau statut selon [source 1]"""
        from utils.validators import convert_utc_to_paris

        priorite_icon = "💎" if demande['prioritaire'] else "📝"
        montant_text = f" - {demande['montant']:.2f}€" if demande['prioritaire'] else ""

        nom_complet = demande['prenom']
        if demande['nom']:
            nom_complet += f" {demande['nom']}"

        date_paris = convert_utc_to_paris(demande['date_creation'])
        user_display = f"@{demande['username']}" if demande['username'] else demande['user_first_name']

        caption = (
            f"📷 <b>PHOTO DEMANDE</b>\n\n"
            f"{priorite_icon} <b>#{demande['request_number']}</b> - {nom_complet}\n"
            f"🎂 {demande['age']} ans - 📍 {demande['localisation']}\n"
            f"📱 Instagram: {demande['instagram'] or 'Non renseigné'}\n"
            f"👻 Snapchat: {demande['snapchat'] or 'Non renseigné'}\n"
            f"<b>{nouveau_statut}</b>{montant_text}\n"
            f"👤 Demandeur: {user_display}\n"
            f"📅 <b>Date:</b> {date_paris.strftime('%d/%m/%Y %H:%M')}"
        )

        if demande['details']:
            details_court = demande['details'][:100] + "..." if len(demande['details']) > 100 else demande['details']
            caption += f"\n💬 <b>Détails:</b> {details_court}"

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔄 STATUT", callback_data=f"change_status_{demande['id']}"),
                InlineKeyboardButton("💬 CONTACTER", callback_data=f"contacter_{demande['id']}")
            ]
        ])

        try:
            await query.edit_message_caption(
                caption=caption,
                parse_mode='HTML',
                reply_markup=keyboard
            )

            await query.answer(f"✅ Statut demande #{request_number} → {nouveau_statut}")

        except Exception as e:
            logger.error(f"Erreur modification caption: {e}")
            await query.answer("❌ Erreur mise à jour caption")

