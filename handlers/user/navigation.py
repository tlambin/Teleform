"""Gestionnaire navigation formulaire selon architecture modulaire"""

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

class NavigationManager:
    """Gestionnaire de navigation pour formulaires - Module dédié"""
    
    def __init__(self, formulaire_manager):
        """Initialisation avec référence au FormulaireManager"""
        self.form = formulaire_manager
        
        # Configuration boutons navigation
        self.navigation_config = {
            "back_text": "⬅️ Retour",
            "skip_text": "⏭️ Passer", 
            "cancel_text": "❌ Annuler"
        }
        
        logger.info("NavigationManager initialisé")

    def create_navigation_keyboard(self, current_state, include_skip=False):
        """Crée le clavier de navigation avec boutons retour et skip"""
        keyboard = []

        # Bouton retour (si pas le premier état)
        if current_state in self.form.state_history:
            keyboard.append([
                InlineKeyboardButton(
                    self.navigation_config["back_text"], 
                    callback_data=f"form_back_{current_state}"
                )
            ])

        # Bouton passer (si champ optionnel)
        if include_skip and current_state in self.form.skippable_fields:
            skip_button = InlineKeyboardButton(
                self.navigation_config["skip_text"], 
                callback_data=f"form_skip_{current_state}"
            )
            
            # Ajouter sur la même ligne que retour si possible
            if keyboard:
                keyboard[0].append(skip_button)
            else:
                keyboard.append([skip_button])

        # Bouton annuler (toujours présent)
        keyboard.append([
            InlineKeyboardButton(
                self.navigation_config["cancel_text"], 
                callback_data="form_cancel"
            )
        ])

        return InlineKeyboardMarkup(keyboard)

    def create_priority_keyboard(self, include_navigation=True):
        """Crée le clavier spécial pour le choix prioritaire"""
        keyboard = [
            [InlineKeyboardButton("⭐ Oui - Prioritaire", callback_data="priorite_oui")],
            [InlineKeyboardButton("📝 Non - Standard", callback_data="priorite_non")]
        ]
        
        if include_navigation:
            keyboard.extend([
                [InlineKeyboardButton("⬅️ Retour", callback_data=f"form_back_{self.form.PRIORITAIRE}")],
                [InlineKeyboardButton("❌ Annuler", callback_data="form_cancel")]
            ])
        
        return InlineKeyboardMarkup(keyboard)

    async def handle_form_navigation(self, update, context):
        """Gère la navigation retour, skip et annulation dans le formulaire"""
        query = update.callback_query
        await query.answer()

        action_data = query.data.split('_')
        action = action_data[1]  # back, skip, cancel

        if action == "cancel":
            return await self.handle_cancel(query, context)
        elif action == "back":
            current_state = int(action_data[2])
            return await self.handle_back(query, context, current_state)
        elif action == "skip":
            current_state = int(action_data[2])
            return await self.handle_skip(query, context, current_state)

    async def handle_back(self, query, context, current_state):
        """Gère le retour à l'état précédent"""
        previous_state = self.form.state_history.get(current_state)
        
        if not previous_state:
            await query.answer("❌ Impossible de revenir en arrière")
            return current_state

        # Messages de retour selon l'état
        back_messages = {
            self.form.PRENOM: {
                "text": "📝 <b>Retour - Prénom</b>\n\nQuel est son <b>prénom</b> ?",
                "keyboard": self.create_navigation_keyboard(self.form.PRENOM)
            },
            self.form.NOM: {
                "text": "📝 <b>Retour - Nom</b>\n\nSon nom de famille :",
                "keyboard": self.create_navigation_keyboard(self.form.NOM, include_skip=True)
            },
            self.form.AGE: {
                "text": "📝 <b>Retour - Âge</b>\n\nSon âge (18-40 ans) :",
                "keyboard": self.create_navigation_keyboard(self.form.AGE)
            },
            self.form.LOCALISATION: {
                "text": "📝 <b>Retour - Localisation</b>\n\nSa localisation (ville, région ou pays) :",
                "keyboard": self.create_navigation_keyboard(self.form.LOCALISATION)
            },
            self.form.PHOTO: {
                "text": "📝 <b>Retour - Photo</b>\n\n📸 Envoyez une photo :",
                "keyboard": self.create_navigation_keyboard(self.form.PHOTO)
            },
            self.form.INSTAGRAM: {
                "text": "📝 <b>Retour - Instagram</b>\n\nSon Instagram :",
                "keyboard": self.create_navigation_keyboard(self.form.INSTAGRAM, include_skip=True)
            },
            self.form.SNAPCHAT: {
                "text": "📝 <b>Retour - Snapchat</b>\n\nSon Snapchat :",
                "keyboard": self.create_navigation_keyboard(self.form.SNAPCHAT, include_skip=True)
            },
            self.form.DETAILS: {
                "text": "📝 <b>Retour - Détails</b>\n\nDes détails supplémentaires ?",
                "keyboard": self.create_navigation_keyboard(self.form.DETAILS, include_skip=True)
            },
            self.form.PRIORITAIRE: {
                "text": "📝 <b>Retour - Priorité</b>\n\n💎 <b>Demande prioritaire ?</b>\n\nLes demandes prioritaires nécessitent un montant et sont traitées en premier.",
                "keyboard": self.create_priority_keyboard()
            },
            self.form.MONTANT: {
                "text": "💰 <b>Retour - Montant</b>\n\nVeuillez indiquer le montant (en euros) :",
                "keyboard": self.create_navigation_keyboard(self.form.MONTANT)
            }
        }

        message_config = back_messages.get(previous_state)
        if message_config:
            await query.edit_message_text(
                message_config["text"],
                parse_mode='HTML',
                reply_markup=message_config["keyboard"]
            )
            return previous_state

        return current_state

    async def handle_skip(self, query, context, current_state):
        """Gère le skip via bouton pour les champs optionnels"""
        skip_handlers = {
            self.form.NOM: self._skip_nom,
            self.form.INSTAGRAM: self._skip_instagram,
            self.form.SNAPCHAT: self._skip_snapchat,
            self.form.DETAILS: self._skip_details
        }

        handler = skip_handlers.get(current_state)
        if handler:
            return await handler(query, context)
        
        return current_state

    async def _skip_nom(self, query, context):
        """Skip nom via bouton"""
        context.user_data['demande']['nom'] = None
        await query.edit_message_text(
            "⏭️ <b>Nom passé</b>\n\nSon âge (18-40 ans) :",
            parse_mode='HTML',
            reply_markup=self.create_navigation_keyboard(self.form.AGE)
        )
        return self.form.AGE

    async def _skip_instagram(self, query, context):
        """Skip Instagram via bouton"""
        context.user_data['demande']['instagram'] = None
        await query.edit_message_text(
            "⏭️ <b>Instagram passé</b>\n\nSon Snapchat :",
            parse_mode='HTML',
            reply_markup=self.create_navigation_keyboard(self.form.SNAPCHAT, include_skip=True)
        )
        return self.form.SNAPCHAT

    async def _skip_snapchat(self, query, context):
        """Skip Snapchat via bouton"""
        context.user_data['demande']['snapchat'] = None
        await query.edit_message_text(
            "⏭️ <b>Snapchat passé</b>\n\nDes détails supplémentaires ?",
            parse_mode='HTML',
            reply_markup=self.create_navigation_keyboard(self.form.DETAILS, include_skip=True)
        )
        return self.form.DETAILS

    async def _skip_details(self, query, context):
        """Skip détails via bouton"""
        context.user_data['demande']['details'] = None
        await query.edit_message_text(
            "⏭️ <b>Détails passés</b>\n\n💎 <b>Demande prioritaire ?</b>\n\nLes demandes prioritaires nécessitent un montant et sont traitées en premier.",
            parse_mode='HTML',
            reply_markup=self.create_priority_keyboard()
        )
        return self.form.PRIORITAIRE

    async def handle_cancel(self, query, context):
        """Annulation via bouton callback"""
        context.user_data.clear()
        await query.edit_message_text(
            "❌ <b>Création annulée</b>\n\nTapez /start pour revenir au menu principal.",
            parse_mode='HTML'
        )
        return -1  # ConversationHandler.END
