"""Gestionnaire de navigation pour le formulaire de demande."""

import html
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

    def create_vip_admin_choice_keyboard(self):
        """Génère la liste dynamique des référents pour le membre VIP."""
        equipe = self.form.db_manager.get_available_admins_for_selection()
        kb_rows = []

        for member in equipe:
            role_icon = "👑" if member.get("role") == "Owner" else "🦈"
            raw_alias = member.get("alias") or f"Admin_{member['user_id']}"
            kb_rows.append([
                InlineKeyboardButton(
                    f"{role_icon} {raw_alias}",
                    callback_data=f"vip_assign_admin_{member['user_id']}"
                )
            ])

        kb_rows.append([InlineKeyboardButton("🎲 Premier disponible (Aléatoire)", callback_data="vip_assign_admin_0")])
        kb_rows.append([
            InlineKeyboardButton(self.navigation_config["back_text"], callback_data=f"form_back_{self.form.CHOIX_ADMIN}"),
            InlineKeyboardButton(self.navigation_config["cancel_text"], callback_data="form_cancel")
        ])
        return InlineKeyboardMarkup(kb_rows)

    async def handle_form_navigation(self, update, context):
        """Point d'entrée du routage navigationnel."""
        query = update.callback_query
        if not query or not query.data:
            return None

        await query.answer()
        parts = query.data.split("_")
        if len(parts) < 2:
            return None

        action = parts[1]  # back, skip, cancel

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

        # Gestion spécifique du retour depuis le choix d'admin VIP
        if current_state == self.form.CHOIX_ADMIN:
            if demande.get("prioritaire"):
                previous_state = self.form.MONTANT
            else:
                previous_state = self.form.PRIORITAIRE
        else:
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
                "text": (
                    "📝 <b>Retour - Snapchat</b>\n\n"
                    + ("Son compte Snapchat (ou passez) :" if has_insta else "⚠️ <b>Au moins un réseau est requis.</b>\nSon compte Snapchat :")
                ),
                "keyboard": self.create_navigation_keyboard(self.form.SNAPCHAT, include_skip=has_insta),
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
            self.form.CHOIX_ADMIN: {
                "text": (
                    "⭐ <b>Avantage Membre VIP : Choix du Référent</b>\n\n"
                    "Sélectionnez le membre de l'équipe qui prendra personnellement en charge votre demande :"
                ),
                "keyboard": self.create_vip_admin_choice_keyboard(),
            },
        }

        screen = back_screens.get(previous_state)
        if screen:
            is_current_photo = bool(query.message and query.message.photo)
            chat_id = query.message.chat_id if query.message else None

            if is_current_photo and chat_id:
                try:
                    await query.message.delete()
                except Exception:
                    pass
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=screen["text"],
                    parse_mode="HTML",
                    reply_markup=screen["keyboard"],
                )
            else:
                try:
                    await query.edit_message_text(
                        screen["text"],
                        parse_mode="HTML",
                        reply_markup=screen["keyboard"],
                    )
                except Exception:
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
        text = (
            "⏭️ <b>Instagram ignoré</b>\n\n"
            "⚠️ <b>Au moins un réseau social est obligatoire.</b>\n"
            "Indiquez son compte <b>Snapchat</b> :"
        )
        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=self.create_navigation_keyboard(self.form.SNAPCHAT, include_skip=False),
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
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Retourner à Instagram", callback_data=f"form_back_{self.form.SNAPCHAT}")],
                [InlineKeyboardButton("❌ Annuler la demande", callback_data="form_cancel")]
            ])
            await query.edit_message_text(msg, parse_mode="HTML", reply_markup=kb)
            return self.form.SNAPCHAT

        demande["snapchat"] = None
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
        context.user_data.pop("user_id", None)
        await query.edit_message_text(
            "❌ <b>Création de demande annulée</b>\n\n"
            "Tapez /start pour revenir au menu principal.",
            parse_mode="HTML",
        )
        return ConversationHandler.END