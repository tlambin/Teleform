"""Gestionnaire de navigation pour le formulaire de demande."""

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler

logger = logging.getLogger(__name__)


class NavigationManager:
    """Gère les boutons Retour, Passer et Annuler du flux de formulaire."""

    def __init__(self, formulaire_manager):
        self.form = formulaire_manager
        self.navigation_config = {
            "back_text": "⬅️ Retour",
            "skip_text": "⏭️ Passer",
            "cancel_text": "❌ Annuler",
        }
        logger.info("NavigationManager initialisé")

    def create_navigation_keyboard(self, current_state, include_skip=False):
        """Construit le clavier dynamique adapté à l'étape courante."""
        keyboard = []
        action_row = []

        # Bouton Retour (si l'état a un précédent)
        if current_state in self.form.state_history:
            action_row.append(
                InlineKeyboardButton(
                    self.navigation_config["back_text"],
                    callback_data=f"form_back_{current_state}",
                )
            )

        # Bouton Passer (si le champ est optionnel)
        if include_skip and current_state in self.form.skippable_fields:
            action_row.append(
                InlineKeyboardButton(
                    self.navigation_config["skip_text"],
                    callback_data=f"form_skip_{current_state}",
                )
            )

        if action_row:
            keyboard.append(action_row)

        # Bouton Annuler systématique
        keyboard.append([
            InlineKeyboardButton(
                self.navigation_config["cancel_text"],
                callback_data="form_cancel",
            )
        ])

        return InlineKeyboardMarkup(keyboard)

    def create_priority_keyboard(self, include_navigation=True):
        """Clavier pour le choix Standard vs Prioritaire."""
        keyboard = [
            [InlineKeyboardButton("⭐ Oui - Prioritaire", callback_data="priorite_oui")],
            [InlineKeyboardButton("📝 Non - Standard", callback_data="priorite_non")],
        ]
        if include_navigation:
            keyboard.append([
                InlineKeyboardButton(
                    self.navigation_config["back_text"],
                    callback_data=f"form_back_{self.form.PRIORITAIRE}",
                ),
                InlineKeyboardButton(
                    self.navigation_config["cancel_text"],
                    callback_data="form_cancel",
                ),
            ])
        return InlineKeyboardMarkup(keyboard)

    async def handle_form_navigation(self, update, context):
        """Point d'entrée du routage navigationnel."""
        query = update.callback_query
        if not query or not query.data:
            return None

        await query.answer()
        parts = query.data.split("_")
        action = parts[1]  # back, skip, cancel

        if action == "cancel":
            return await self.handle_cancel(query, context)

        current_state = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
        if current_state is None:
            return None

        if action == "back":
            return await self.handle_back(query, context, current_state)
        elif action == "skip":
            return await self.handle_skip(query, context, current_state)

        return current_state

    async def handle_back(self, query, context, current_state):
        """Recule d'une étape dans la FSM."""
        previous_state = self.form.state_history.get(current_state)
        if not previous_state:
            await query.answer("❌ Début du formulaire atteint", show_alert=True)
            return current_state

        back_screens = {
            self.form.PRENOM: {
                "text": "📝 <b>Retour - Prénom</b>\n\nQuel est son <b>prénom</b> ?",
                "keyboard": self.create_navigation_keyboard(self.form.PRENOM),
            },
            self.form.NOM: {
                "text": "📝 <b>Retour - Nom</b>\n\nSon nom de famille :",
                "keyboard": self.create_navigation_keyboard(self.form.NOM, include_skip=True),
            },
            self.form.AGE: {
                "text": "📝 <b>Retour - Âge</b>\n\nSon âge (18-40 ans) :",
                "keyboard": self.create_navigation_keyboard(self.form.AGE),
            },
            self.form.LOCALISATION: {
                "text": "📝 <b>Retour - Localisation</b>\n\nSa localisation (ville, région ou pays) :",
                "keyboard": self.create_navigation_keyboard(self.form.LOCALISATION),
            },
            self.form.PHOTO: {
                "text": "📝 <b>Retour - Photo</b>\n\n📸 Envoyez une photo :",
                "keyboard": self.create_navigation_keyboard(self.form.PHOTO),
            },
            self.form.INSTAGRAM: {
                "text": "📝 <b>Retour - Instagram</b>\n\nSon profil Instagram :",
                "keyboard": self.create_navigation_keyboard(self.form.INSTAGRAM, include_skip=True),
            },
            self.form.SNAPCHAT: {
                "text": "📝 <b>Retour - Snapchat</b>\n\nSon compte Snapchat :",
                "keyboard": self.create_navigation_keyboard(self.form.SNAPCHAT, include_skip=True),
            },
            self.form.DETAILS: {
                "text": "📝 <b>Retour - Détails</b>\n\nDes précisions ou remarques à apporter ?",
                "keyboard": self.create_navigation_keyboard(self.form.DETAILS, include_skip=True),
            },
            self.form.PRIORITAIRE: {
                "text": (
                    "📝 <b>Retour - Priorité</b>\n\n"
                    "💎 <b>Demande prioritaire ?</b>\n\n"
                    "Les demandes prioritaires nécessitent un montant et sont traitées en premier."
                ),
                "keyboard": self.create_priority_keyboard(),
            },
            self.form.MONTANT: {
                "text": "💰 <b>Retour - Montant</b>\n\nIndiquez le montant (en euros) :",
                "keyboard": self.create_navigation_keyboard(self.form.MONTANT),
            },
        }

        screen = back_screens.get(previous_state)
        if screen:
            try:
                await query.edit_message_text(
                    screen["text"],
                    parse_mode="HTML",
                    reply_markup=screen["keyboard"],
                )
            except Exception:
                # Si le message source était une photo ou non éditable en texte
                if query.message:
                    await query.message.reply_text(
                        screen["text"],
                        parse_mode="HTML",
                        reply_markup=screen["keyboard"],
                    )
            return previous_state

        return current_state

    async def handle_skip(self, query, context, current_state):
        """Délègue l'action de passer un champ optionnel."""
        skip_map = {
            self.form.NOM: self._skip_nom,
            self.form.INSTAGRAM: self._skip_instagram,
            self.form.SNAPCHAT: self._skip_snapchat,
            self.form.DETAILS: self._skip_details,
        }
        handler = skip_map.get(current_state)
        if handler:
            return await handler(query, context)
        return current_state

    async def _skip_nom(self, query, context):
        context.user_data.setdefault("demande", {})["nom"] = None
        await query.edit_message_text(
            "⏭️ <b>Nom ignoré</b>\n\nIndiquez son âge (entre 18 et 40 ans) :",
            parse_mode="HTML",
            reply_markup=self.create_navigation_keyboard(self.form.AGE),
        )
        return self.form.AGE

    async def _skip_instagram(self, query, context):
        context.user_data.setdefault("demande", {})["instagram"] = None
        await query.edit_message_text(
            "⏭️ <b>Instagram ignoré</b>\n\nIndiquez son compte <b>Snapchat</b> (ou passez) :",
            parse_mode="HTML",
            reply_markup=self.create_navigation_keyboard(self.form.SNAPCHAT, include_skip=True),
        )
        return self.form.SNAPCHAT

    async def _skip_snapchat(self, query, context):
        context.user_data.setdefault("demande", {})["snapchat"] = None
        await query.edit_message_text(
            "⏭️ <b>Snapchat ignoré</b>\n\nAvez-vous des détails ou remarques supplémentaires à ajouter ?",
            parse_mode="HTML",
            reply_markup=self.create_navigation_keyboard(self.form.DETAILS, include_skip=True),
        )
        return self.form.DETAILS

    async def _skip_details(self, query, context):
        context.user_data.setdefault("demande", {})["details"] = None
        await query.edit_message_text(
            "⏭️ <b>Détails ignorés</b>\n\n"
            "💎 <b>Souhaitez-vous une demande prioritaire ?</b>\n\n"
            "Les demandes prioritaires nécessitent un montant et sont examinées en premier.",
            parse_mode="HTML",
            reply_markup=self.create_priority_keyboard(),
        )
        return self.form.PRIORITAIRE

    async def handle_cancel(self, query, context):
        """Nettoie le contexte et clôt le ConversationHandler."""
        context.user_data.pop("demande", None)
        await query.edit_message_text(
            "❌ <b>Création de demande annulée</b>\n\n"
            "Tapez /start pour revenir au menu principal.",
            parse_mode="HTML",
        )
        return ConversationHandler.END