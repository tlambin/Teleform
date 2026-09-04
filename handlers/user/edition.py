"""Gestion édition et suppression demandes selon architecture modulaire"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from utils.validators import Validators, ValidationError

logger = logging.getLogger(__name__)

class EditionManager:
    """Gestionnaire édition/suppression demandes"""
    
    def __init__(self, db_manager, config):
        """Initialisation EditionManager"""
        self.db_manager = db_manager
        self.config = config
        
        logger.info("EditionManager initialisé")

    async def handle_modify_request(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Gestion callbacks modify_X - Affichage menu modification"""
        query = update.callback_query
        await query.answer()
        
        # Extraire ID demande depuis callback_data
        demande_id = int(data.replace("modify_", ""))
        
        # Vérifier propriété de la demande
        if not await self._verify_request_ownership(demande_id, query.from_user.id):
            await query.edit_message_text("❌ Cette demande ne vous appartient pas.")
            return
        
        # Récupérer infos demande
        demande = await self._get_request_details(demande_id)
        if not demande:
            await query.edit_message_text("❌ Demande introuvable.")
            return
        
        # Afficher menu modification
        await self._show_modify_menu(query, demande)

    async def handle_edit_field(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Gestion callbacks edit_X - Édition champ spécifique"""
        query = update.callback_query
        await query.answer()
        
        # Parser callback_data : edit_field_demandeid
        parts = data.split("_")
        if len(parts) != 3:
            await query.answer("❌ Format callback invalide")
            return
            
        field_name = parts[1]
        demande_id = int(parts[2])
        
        # Vérifier propriété
        if not await self._verify_request_ownership(demande_id, query.from_user.id):
            await query.edit_message_text("❌ Cette demande ne vous appartient pas.")
            return
        
        # Stocker context pour la modification
        context.user_data['editing'] = {
            'demande_id': demande_id,
            'field': field_name,
            'returning_to': 'modify_menu'
        }
        
        # Afficher prompt édition selon le champ
        await self._show_edit_prompt(query, field_name, demande_id)

    async def handle_delete_request(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Gestion callbacks delete_X - Suppression avec confirmation"""
        query = update.callback_query
        await query.answer()
        
        # Extraire ID demande
        demande_id = int(data.replace("delete_", ""))
        
        # Vérifier propriété
        if not await self._verify_request_ownership(demande_id, query.from_user.id):
            await query.edit_message_text("❌ Cette demande ne vous appartient pas.")
            return
        
        # Récupérer infos pour confirmation
        demande = await self._get_request_details(demande_id)
        if not demande:
            await query.edit_message_text("❌ Demande introuvable.")
            return
        
        # Afficher confirmation suppression
        await self._show_delete_confirmation(query, demande)

    async def handle_cancel_edit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Gestion cancel_edit - Annulation édition"""
        query = update.callback_query
        await query.answer()
        
        # Nettoyer context édition
        editing_data = context.user_data.pop('editing', None)
        
        if editing_data and editing_data.get('demande_id'):
            # Retourner au menu modification de la demande
            demande_id = editing_data['demande_id']
            demande = await self._get_request_details(demande_id)
            if demande:
                await self._show_modify_menu(query, demande)
            else:
                await query.edit_message_text("❌ Demande introuvable.")
        else:
            # Retourner au menu principal
            await query.edit_message_text(
                "❌ Édition annulée.\n\nRetour au menu principal.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")
                ]])
            )

    async def handle_edit_text_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Traitement saisie texte pour édition de champ"""
        if 'editing' not in context.user_data:
            return  # Pas en mode édition
        
        editing_data = context.user_data['editing']
        demande_id = editing_data['demande_id']
        field_name = editing_data['field']
        user_input = Validators.clean_input(update.message.text)
        
        try:
            # Validation selon le champ
            validated_value = await self._validate_field_input(field_name, user_input)
            
            # Mise à jour en base
            success = await self._update_field_in_database(demande_id, field_name, validated_value)
            
            if success:
                # Nettoyer context
                context.user_data.pop('editing', None)
                
                # Afficher confirmation et retourner au menu modification
                await update.message.reply_text(
                    f"✅ {self._get_field_display_name(field_name)} modifié avec succès !",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("↩️ Retour à la demande", callback_data=f"modify_{demande_id}")
                    ]])
                )
            else:
                await update.message.reply_text("❌ Erreur lors de la mise à jour.")
                
        except ValidationError as e:
            await update.message.reply_text(
                f"❌ {str(e)}\n\n"
                f"{Validators.get_validation_help(field_name)}\n\n"
                "Veuillez ressaisir ou tapez /cancel pour annuler :"
            )

    # === MÉTHODES PRIVÉES === 

    async def _verify_request_ownership(self, demande_id: int, user_id: int) -> bool:
        """Vérifie que la demande appartient à l'utilisateur"""
        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute("""
                    SELECT user_id FROM demandes WHERE id = %s
                """, (demande_id,))
                result = cursor.fetchone()
                return result and result['user_id'] == user_id
        except Exception as e:
            logger.error(f"Erreur vérification propriété demande {demande_id}: {e}")
            return False

    async def _get_request_details(self, demande_id: int) -> dict:
        """Récupère les détails d'une demande"""
        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute("""
                    SELECT * FROM demandes WHERE id = %s
                """, (demande_id,))
                return cursor.fetchone()
        except Exception as e:
            logger.error(f"Erreur récupération demande {demande_id}: {e}")
            return None

    async def _show_modify_menu(self, query, demande: dict):
        """Affiche le menu de modification d'une demande"""
        nom_complet = demande['prenom']
        if demande['nom']:
            nom_complet += f" {demande['nom']}"
        
        message = (
            f"✏️ <b>Modifier Demande n°{demande['request_number']}</b>\n\n"
            f"👤 <b>Actuellement :</b> {nom_complet} ({demande['age']} ans)\n"
            f"📍 <b>Localisation :</b> {demande['localisation']}\n\n"
            "Que souhaitez-vous modifier ?"
        )
        
        keyboard = [
            [InlineKeyboardButton("👤 Prénom", callback_data=f"edit_prenom_{demande['id']}")],
            [InlineKeyboardButton("📝 Nom", callback_data=f"edit_nom_{demande['id']}")],
            [InlineKeyboardButton("🎂 Âge", callback_data=f"edit_age_{demande['id']}")],
            [InlineKeyboardButton("📍 Localisation", callback_data=f"edit_localisation_{demande['id']}")],
            [InlineKeyboardButton("📱 Instagram", callback_data=f"edit_instagram_{demande['id']}")],
            [InlineKeyboardButton("👻 Snapchat", callback_data=f"edit_snapchat_{demande['id']}")],
            [InlineKeyboardButton("📝 Détails", callback_data=f"edit_details_{demande['id']}")],
            [],
            [InlineKeyboardButton("🗑️ Supprimer cette demande", callback_data=f"delete_{demande['id']}")],
            [InlineKeyboardButton("🔙 Retour à mes demandes", callback_data="voir_demandes")]
        ]
        
        await query.edit_message_text(
            message,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _show_edit_prompt(self, query, field_name: str, demande_id: int):
        """Affiche le prompt d'édition pour un champ"""
        field_display = self._get_field_display_name(field_name)
        help_text = Validators.get_validation_help(field_name)
        
        message = (
            f"✏️ <b>Modifier {field_display}</b>\n\n"
            f"{help_text}\n\n"
            f"Saisissez la nouvelle valeur :"
        )
        
        await query.edit_message_text(
            message,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Annuler", callback_data="cancel_edit")
            ]])
        )

    async def _show_delete_confirmation(self, query, demande: dict):
        """Affiche la confirmation de suppression"""
        nom_complet = demande['prenom']
        if demande['nom']:
            nom_complet += f" {demande['nom']}"
        
        message = (
            f"🗑️ <b>Supprimer Demande n°{demande['request_number']}</b>\n\n"
            f"👤 {nom_complet} ({demande['age']} ans)\n"
            f"📍 {demande['localisation']}\n\n"
            f"⚠️ <b>Cette action est irréversible !</b>\n"
            f"Êtes-vous sûr de vouloir supprimer cette demande ?"
        )
        
        keyboard = [
            [InlineKeyboardButton("✅ Oui, supprimer", callback_data=f"confirm_delete_{demande['id']}")],
            [InlineKeyboardButton("❌ Non, annuler", callback_data=f"modify_{demande['id']}")]
        ]
        
        await query.edit_message_text(
            message,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _validate_field_input(self, field_name: str, user_input: str):
        """Valide la saisie selon le champ"""
        if field_name == "prenom":
            return Validators.validate_prenom(user_input)
        elif field_name == "nom":
            return Validators.validate_nom(user_input) if user_input else None
        elif field_name == "age":
            return Validators.validate_age(user_input)
        elif field_name == "localisation":
            return Validators.validate_localisation(user_input)
        elif field_name == "instagram":
            return Validators.validate_instagram(user_input) if user_input else None
        elif field_name == "snapchat":
            return Validators.validate_snapchat(user_input) if user_input else None
        elif field_name == "details":
            return Validators.validate_details(user_input) if user_input else None
        else:
            raise ValidationError(f"Champ {field_name} non supporté")

    async def _update_field_in_database(self, demande_id: int, field_name: str, value) -> bool:
        """Met à jour un champ en base de données"""
        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute(f"""
                    UPDATE demandes 
                    SET {field_name} = %s, date_modification = NOW()
                    WHERE id = %s
                """, (value, demande_id))
                
                return cursor.rowcount > 0
                
        except Exception as e:
            logger.error(f"Erreur mise à jour {field_name} demande {demande_id}: {e}")
            return False

    def _get_field_display_name(self, field_name: str) -> str:
        """Retourne le nom d'affichage d'un champ"""
        field_names = {
            "prenom": "Prénom",
            "nom": "Nom",
            "age": "Âge", 
            "localisation": "Localisation",
            "instagram": "Instagram",
            "snapchat": "Snapchat",
            "details": "Détails"
        }
        return field_names.get(field_name, field_name.title())

    async def handle_confirm_delete(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Traite la confirmation de suppression"""
        query = update.callback_query
        await query.answer()
        
        # Extraire ID demande
        demande_id = int(data.replace("confirm_delete_", ""))
        
        # Vérifier propriété une dernière fois
        if not await self._verify_request_ownership(demande_id, query.from_user.id):
            await query.edit_message_text("❌ Cette demande ne vous appartient pas.")
            return
        
        # Récupérer infos avant suppression
        demande = await self._get_request_details(demande_id)
        if not demande:
            await query.edit_message_text("❌ Demande introuvable.")
            return
        
        # Supprimer de la base
        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute("DELETE FROM demandes WHERE id = %s", (demande_id,))
                
                if cursor.rowcount > 0:
                    logger.info(f"Demande {demande_id} supprimée par utilisateur {query.from_user.id}")
                    
                    await query.edit_message_text(
                        f"✅ <b>Demande n°{demande['request_number']} supprimée</b>\n\n"
                        f"La demande de {demande['prenom']} a été supprimée définitivement.",
                        parse_mode='HTML',
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("📋 Voir mes demandes", callback_data="voir_demandes"),
                            InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")
                        ]])
                    )
                else:
                    await query.edit_message_text("❌ Erreur lors de la suppression.")
                    
        except Exception as e:
            logger.error(f"Erreur suppression demande {demande_id}: {e}")
            await query.edit_message_text("❌ Erreur lors de la suppression.")
