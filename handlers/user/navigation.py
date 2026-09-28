"""Gestionnaire de navigation pour le formulaire de demande."""

import logging
from telegram.ext import ConversationHandler
from ui.user import creation as ui

logger = logging.getLogger(__name__)


class NavigationManager:
    """Gère les boutons Retour, Passer et Annuler du flux de formulaire."""

    def __init__(self, formulaire_manager):
        self.form = formulaire_manager
        logger.info("NavigationManager initialisé avec support Orientation & Staff")

    def create_navigation_keyboard(self, current_state, include_skip=False):
        """Délègue la construction du clavier de navigation standard."""
        return ui.create_navigation_keyboard(
            current_state,
            self.form.state_history,
            self.form.skippable_fields,
            include_skip=include_skip
        )

    def create_priority_keyboard(self, include_navigation=True):
        """Délègue la construction du clavier de choix de priorité."""
        return ui.create_priority_keyboard(self.form.PRIORITAIRE, include_navigation=include_navigation)

    def create_vip_admin_choice_keyboard(self, target_ori: str = "hetero"):
        """Délègue la génération de la liste dynamique des référents Staff pour VIP."""
        equipe = self.form.db_manager.get_available_staff()
        return ui.create_vip_admin_choice_keyboard(
            equipe,
            target_ori,
            self.form.CHOIX_ADMIN,
            self.form.db_manager
        )

    async def _safe_edit_or_send(self, query, context, text: str, reply_markup=None):
        """Édite le message ou supprime la photo existante pour réémettre du texte."""
        if query.message and query.message.photo:
            chat_id = query.message.chat_id
            try:
                await query.message.delete()
            except Exception:
                pass
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="HTML",
                reply_markup=reply_markup
            )
        else:
            try:
                await query.edit_message_text(
                    text=text,
                    parse_mode="HTML",
                    reply_markup=reply_markup
                )
            except Exception:
                if query.message:
                    await query.message.reply_text(
                        text=text,
                        parse_mode="HTML",
                        reply_markup=reply_markup
                    )

    async def handle_form_navigation(self, update, context):
        """Point d'entrée du routage navigationnel."""
        query = update.callback_query
        if not query or not query.data:
            return None

        await query.answer()
        parts = query.data.split("_")
        if len(parts) < 2:
            return None

        action = parts[1]

        if action == "cancel":
            return await self.handle_cancel(query, context)

        try:
            current_state = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
        except (IndexError, ValueError):
            current_state = None

        if current_state is None:
            return None

        if action == "back":
            return await self.handle_back(query, context, current_state)
        elif action == "skip":
            return await self.handle_skip(query, context, current_state)

        return current_state

    async def handle_back(self, query, context, current_state):
        """Recule d'une étape dans la machine à états."""
        demande = context.user_data.get("demande", {})
        has_insta = bool(demande.get("instagram"))
        target_ori = demande.get("orientation", "hetero")

        # Gestion spécifique du retour depuis le choix d'admin VIP
        if current_state == self.form.CHOIX_ADMIN:
            if demande.get("prioritaire"):
                previous_state = self.form.MONTANT
            else:
                previous_state = self.form.PRIORITAIRE
        else:
            previous_state = self.form.state_history.get(current_state)

        if previous_state is None:
            await query.answer("❌ Début du formulaire atteint", show_alert=True)
            return current_state

        back_screens = ui.get_back_screens_dict(self.form, has_insta, target_ori)
        screen = back_screens.get(previous_state)
        if screen:
            await self._safe_edit_or_send(
                query,
                context,
                screen["text"],
                reply_markup=screen["keyboard"]
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
        await self._safe_edit_or_send(
            query,
            context,
            "⏭️ <b>Nom ignoré</b>\n\nIndiquez son âge (entre 18 et 40 ans) :",
            reply_markup=self.create_navigation_keyboard(self.form.AGE)
        )
        return self.form.AGE

    async def _skip_instagram(self, query, context):
        context.user_data.setdefault("demande", {})["instagram"] = None
        text = (
            "⏭️ <b>Instagram ignoré</b>\n\n"
            "⚠️ <b>Au moins un réseau social est obligatoire.</b>\n"
            "Indiquez son compte <b>Snapchat</b> :"
        )
        await self._safe_edit_or_send(
            query,
            context,
            text,
            reply_markup=self.create_navigation_keyboard(self.form.SNAPCHAT, include_skip=False)
        )
        return self.form.SNAPCHAT

    async def _skip_snapchat(self, query, context):
        demande = context.user_data.setdefault("demande", {})

        if not demande.get("instagram"):
            msg = (
                "🚫 <b>Réseau social obligatoire</b>\n\n"
                "Vous devez obligatoirement fournir au moins un compte (<b>Instagram</b> ou <b>Snapchat</b>).\n\n"
                "Saisissez son identifiant Snapchat ou revenez à l'étape précédente pour renseigner Instagram :"
            )
            kb = ui.get_mandatory_network_keyboard(self.form.SNAPCHAT)
            await self._safe_edit_or_send(query, context, msg, reply_markup=kb)
            return self.form.SNAPCHAT

        demande["snapchat"] = None
        await self._safe_edit_or_send(
            query,
            context,
            "⏭️ <b>Snapchat ignoré</b>\n\nAvez-vous des détails ou remarques supplémentaires à ajouter ?",
            reply_markup=self.create_navigation_keyboard(self.form.DETAILS, include_skip=True)
        )
        return self.form.DETAILS

    async def _skip_details(self, query, context):
        context.user_data.setdefault("demande", {})["details"] = None
        await self._safe_edit_or_send(
            query,
            context,
            "⏭️ <b>Détails ignorés</b>\n\n"
            "💎 <b>Souhaitez-vous une demande prioritaire ?</b>\n\n"
            "Les demandes prioritaires nécessitent un montant et sont examinées en premier.",
            reply_markup=self.create_priority_keyboard()
        )
        return self.form.PRIORITAIRE

    async def handle_cancel(self, query, context):
        """Nettoie le contexte et clôt le ConversationHandler."""
        context.user_data.pop("demande", None)
        context.user_data.pop("user_id", None)
        await self._safe_edit_or_send(
            query,
            context,
            "❌ <b>Création de demande annulée</b>\n\nTapez /start pour revenir au menu principal."
        )
        return ConversationHandler.END