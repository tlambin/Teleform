"""Gestion de l'édition et de la suppression des demandes par les utilisateurs."""

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from utils.validators import ValidationError, Validators

logger = logging.getLogger(__name__)


class EditionManager:
    """Gestionnaire des modifications de champs et de suppressions de demandes."""

    ALLOWED_FIELDS = {
        "prenom": "Prénom",
        "nom": "Nom",
        "age": "Âge",
        "localisation": "Localisation",
        "instagram": "Instagram",
        "snapchat": "Snapchat",
        "details": "Détails",
    }

    def __init__(self, db_manager, config):
        self.db_manager = db_manager
        self.config = config
        logger.info("EditionManager initialisé")

    async def handle_modify_request(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Affiche le menu de sélection du champ à modifier."""
        query = update.callback_query
        if not query:
            return

        await query.answer()
        demande_id = int(data.replace("modify_", ""))

        if not self._verify_request_ownership(demande_id, query.from_user.id):
            await query.edit_message_text("❌ Vous n'êtes pas autorisé à modifier cette demande.")
            return

        demande = self._get_request_details(demande_id)
        if not demande:
            await query.edit_message_text("❌ Demande introuvable.")
            return

        if demande.get("statut") != "📨 Reçue":
            await query.edit_message_text(
                "⚠️ Cette demande est déjà en cours de traitement ou traitée et ne peut plus être modifiée.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("📋 Retour à mes demandes", callback_data="voir_demandes")
                ]])
            )
            return

        await self._show_modify_menu(query, demande)

    async def handle_edit_field(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Enclenche le mode écoute pour la modification d'un champ précis."""
        query = update.callback_query
        if not query:
            return

        await query.answer()
        parts = data.split("_")
        if len(parts) != 3:
            await query.answer("❌ Requête invalide", show_alert=True)
            return

        field_name = parts[1]
        demande_id = int(parts[2])

        if field_name not in self.ALLOWED_FIELDS:
            await query.answer("❌ Champ non modifiable", show_alert=True)
            return

        if not self._verify_request_ownership(demande_id, query.from_user.id):
            await query.edit_message_text("❌ Action non autorisée.")
            return

        context.user_data["editing"] = {
            "demande_id": demande_id,
            "field": field_name,
        }

        await self._show_edit_prompt(query, field_name, demande_id)

    async def handle_delete_request(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Demande confirmation avant suppression définitive."""
        query = update.callback_query
        if not query:
            return

        await query.answer()
        demande_id = int(data.replace("delete_", ""))

        if not self._verify_request_ownership(demande_id, query.from_user.id):
            await query.edit_message_text("❌ Action non autorisée.")
            return

        demande = self._get_request_details(demande_id)
        if not demande:
            await query.edit_message_text("❌ Demande introuvable.")
            return

        if demande.get("statut") != "📨 Reçue":
            await query.edit_message_text(
                "⚠️ Cette demande est déjà prise en charge et ne peut plus être supprimée directement.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("📋 Mes demandes", callback_data="voir_demandes")
                ]])
            )
            return

        await self._show_delete_confirmation(query, demande)

    async def handle_cancel_edit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Annule l'édition en cours et nettoie l'état."""
        query = update.callback_query
        if not query:
            return

        await query.answer()
        editing_data = context.user_data.pop("editing", None)

        if editing_data and editing_data.get("demande_id"):
            demande = self._get_request_details(editing_data["demande_id"])
            if demande:
                await self._show_modify_menu(query, demande)
                return

        await query.edit_message_text(
            "❌ <b>Édition annulée.</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")
            ]])
        )

    async def handle_edit_text_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Intercepte la saisie texte transmise par UserHandlers lorsque 'editing' est présent."""
        if not update.message or not update.message.text:
            return

        editing_data = context.user_data.get("editing")
        if not editing_data:
            return

        demande_id = editing_data["demande_id"]
        field_name = editing_data["field"]
        user_input = Validators.clean_input(update.message.text)

        try:
            validated_value = self._validate_field_input(field_name, user_input)
            success = self._update_field_in_database(demande_id, field_name, validated_value)

            if success:
                context.user_data.pop("editing", None)
                field_label = self.ALLOWED_FIELDS.get(field_name, field_name)
                await update.message.reply_text(
                    f"✅ <b>{field_label}</b> mis à jour avec succès !",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("↩️ Retour à la demande", callback_data=f"modify_{demande_id}")
                    ]])
                )
            else:
                await update.message.reply_text("❌ Échec lors de la mise à jour en base de données.")

        except ValidationError as err:
            help_text = Validators.get_validation_help(field_name)
            await update.message.reply_text(
                f"❌ <b>Saisie invalide :</b> {err}\n\n{help_text}\n\n"
                "Ressaisissez la valeur ou cliquez sur Annuler :",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("❌ Annuler", callback_data="cancel_edit")
                ]])
            )

    async def handle_confirm_delete(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Supprime la demande et ses dépendances après confirmation."""
        query = update.callback_query
        if not query:
            return

        await query.answer()
        demande_id = int(data.replace("confirm_delete_", ""))

        if not self._verify_request_ownership(demande_id, query.from_user.id):
            await query.edit_message_text("❌ Action non autorisée.")
            return

        demande = self._get_request_details(demande_id)
        if not demande:
            await query.edit_message_text("❌ Demande introuvable.")
            return

        try:
            with self.db_manager.get_cursor() as cursor:
                # Nettoyage préventif des suivis associés
                cursor.execute("DELETE FROM demandes_suivi WHERE demande_id = %s", (demande_id,))
                cursor.execute("DELETE FROM demandes WHERE id = %s", (demande_id,))

            logger.info("Demande #%s supprimée par l'utilisateur %s", demande_id, query.from_user.id)
            await query.edit_message_text(
                f"✅ <b>Demande n°{demande.get('request_number', demande_id)} supprimée avec succès.</b>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("📋 Voir mes demandes", callback_data="voir_demandes"),
                    InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")
                ]])
            )
        except Exception as exc:
            logger.error("Erreur suppression demande %s: %s", demande_id, exc, exc_info=True)
            await query.edit_message_text("❌ Une erreur technique est survenue lors de la suppression.")

    def _verify_request_ownership(self, demande_id: int, user_id: int) -> bool:
        """Contrôle la correspondance entre l'utilisateur et le créateur de la demande."""
        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute("SELECT user_id FROM demandes WHERE id = %s", (demande_id,))
                row = cursor.fetchone()
                return bool(row and row["user_id"] == user_id)
        except Exception as exc:
            logger.error("Erreur contrôle propriété demande %s: %s", demande_id, exc)
            return False

    def _get_request_details(self, demande_id: int) -> dict:
        """Récupère l'intégralité d'un enregistrement de demande."""
        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute("SELECT * FROM demandes WHERE id = %s", (demande_id,))
                return cursor.fetchone()
        except Exception as exc:
            logger.error("Erreur extraction détails demande %s: %s", demande_id, exc)
            return None

    def _update_field_in_database(self, demande_id: int, field_name: str, value) -> bool:
        """Met à jour un champ autorisé en base."""
        if field_name not in self.ALLOWED_FIELDS:
            return False

        query = f"UPDATE demandes SET {field_name} = %s, date_modification = NOW() WHERE id = %s"
        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute(query, (value, demande_id))
                return cursor.rowcount > 0
        except Exception as exc:
            logger.error("Erreur mise à jour SQL (%s) sur demande %s: %s", field_name, demande_id, exc)
            return False

    def _validate_field_input(self, field_name: str, user_input: str):
        """Valide et nettoie la valeur saisie selon les règles métier."""
        if field_name == "prenom":
            return Validators.validate_prenom(user_input)
        if field_name == "nom":
            return Validators.validate_nom(user_input) if user_input else None
        if field_name == "age":
            return Validators.validate_age(user_input)
        if field_name == "localisation":
            return Validators.validate_localisation(user_input)
        if field_name == "instagram":
            return Validators.validate_instagram(user_input) if user_input else None
        if field_name == "snapchat":
            return Validators.validate_snapchat(user_input) if user_input else None
        if field_name == "details":
            return Validators.validate_details(user_input) if user_input else None
        raise ValidationError(f"Champ {field_name} non modifiable")

    async def _show_modify_menu(self, query, demande: dict):
        """Génère l'interface des champs modifiables."""
        nom_complet = f"{demande['prenom']} {demande.get('nom') or ''}".strip()
        text = (
            f"✏️ <b>Modifier la demande n°{demande.get('request_number', demande['id'])}</b>\n\n"
            f"👤 <b>Identité :</b> {nom_complet} ({demande['age']} ans)\n"
            f"📍 <b>Localisation :</b> {demande['localisation']}\n\n"
            "Sélectionnez la donnée à modifier :"
        )

        d_id = demande["id"]
        keyboard = [
            [
                InlineKeyboardButton("👤 Prénom", callback_data=f"edit_prenom_{d_id}"),
                InlineKeyboardButton("📝 Nom", callback_data=f"edit_nom_{d_id}")
            ],
            [
                InlineKeyboardButton("🎂 Âge", callback_data=f"edit_age_{d_id}"),
                InlineKeyboardButton("📍 Ville", callback_data=f"edit_localisation_{d_id}")
            ],
            [
                InlineKeyboardButton("📷 Instagram", callback_data=f"edit_instagram_{d_id}"),
                InlineKeyboardButton("👻 Snapchat", callback_data=f"edit_snapchat_{d_id}")
            ],
            [InlineKeyboardButton("💬 Remarques / Détails", callback_data=f"edit_details_{d_id}")],
            [InlineKeyboardButton("🗑️ Supprimer la demande", callback_data=f"delete_{d_id}")],
            [InlineKeyboardButton("🔙 Retour aux demandes", callback_data="voir_demandes")]
        ]

        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

    async def _show_edit_prompt(self, query, field_name: str, demande_id: int):
        """Affiche les instructions de saisie pour le champ sélectionné."""
        field_label = self.ALLOWED_FIELDS.get(field_name, field_name)
        help_text = Validators.get_validation_help(field_name)

        text = (
            f"✏️ <b>Modification : {field_label}</b>\n\n"
            f"{help_text}\n\n"
            "Envoyez votre nouveau texte ci-dessous :"
        )
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Annuler", callback_data="cancel_edit")
        ]])
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)

    async def _show_delete_confirmation(self, query, demande: dict):
        """Affiche l'écran d'avertissement avant suppression."""
        nom_complet = f"{demande['prenom']} {demande.get('nom') or ''}".strip()
        text = (
            f"⚠️ <b>Confirmation de suppression</b>\n\n"
            f"Demande n°<b>{demande.get('request_number', demande['id'])}</b> ({nom_complet})\n\n"
            "Cette action est irréversible. Confirmez-vous la suppression ?"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🗑️ Confirmer la suppression", callback_data=f"confirm_delete_{demande['id']}")],
            [InlineKeyboardButton("❌ Annuler", callback_data=f"modify_{demande['id']}")]
        ])
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)