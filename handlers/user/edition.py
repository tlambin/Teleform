"""Gestion de l'édition et de la suppression des demandes par les utilisateurs."""

import html
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from utils.validators import ValidationError, Validators
from ui.user import demandes as ui

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
        "montant": "Tarif de la prestation",
    }

    _UPDATE_QUERIES = {
        "prenom": "UPDATE demandes SET `prenom` = %s, date_modification = NOW() WHERE id = %s",
        "nom": "UPDATE demandes SET `nom` = %s, date_modification = NOW() WHERE id = %s",
        "age": "UPDATE demandes SET `age` = %s, date_modification = NOW() WHERE id = %s",
        "localisation": "UPDATE demandes SET `localisation` = %s, date_modification = NOW() WHERE id = %s",
        "instagram": "UPDATE demandes SET `instagram` = %s, date_modification = NOW() WHERE id = %s",
        "snapchat": "UPDATE demandes SET `snapchat` = %s, date_modification = NOW() WHERE id = %s",
        "details": "UPDATE demandes SET `details` = %s, date_modification = NOW() WHERE id = %s",
        "montant": "UPDATE demandes SET `montant` = %s, date_modification = NOW() WHERE id = %s",
    }

    def __init__(self, db_manager, config):
        self.db_manager = db_manager
        self.config = config
        logger.info("EditionManager initialisé avec support du prix plancher prioritaire et requêtes précompilées")

    async def handle_modify_request(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Affiche le menu de sélection du champ à modifier."""
        query = update.callback_query
        if not query or not update.effective_user:
            return

        await query.answer()
        try:
            demande_id = int(data.replace("modify_", ""))
        except (ValueError, TypeError):
            await query.answer("❌ Identifiant de demande invalide.", show_alert=True)
            return

        if not self._verify_request_ownership(demande_id, update.effective_user.id):
            await self._update_view(query, "❌ Vous n'êtes pas autorisé à modifier cette demande.")
            return

        demande = self._get_request_details(demande_id)
        if not demande:
            await self._update_view(query, "❌ Demande introuvable.")
            return

        statut = demande.get("statut", "")
        is_prio = bool(demande.get("prioritaire"))

        if statut not in ("📥 Reçue", "📨 Reçue", "🎯 Assignée (VIP)"):
            if not (statut in ("⏳ En attente", "🔄 En cours") and is_prio):
                kb = InlineKeyboardMarkup([[
                    InlineKeyboardButton("📋 Retour à mes demandes", callback_data="voir_demandes")
                ]])
                await self._update_view(
                    query,
                    "⚠️ Cette demande est déjà en cours de traitement et ne peut plus être modifiée.",
                    reply_markup=kb
                )
                return

        text, keyboard = ui.build_modify_menu_content(demande)
        await self._update_view(query, text, reply_markup=keyboard)

    async def handle_edit_field(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Enclenche le mode écoute pour la modification d'un champ précis."""
        query = update.callback_query
        if not query or not update.effective_user:
            return

        await query.answer()
        parts = data.split("_")
        if len(parts) != 3 or not parts[2].isdigit():
            await query.answer("❌ Requête invalide", show_alert=True)
            return

        field_name = parts[1]
        demande_id = int(parts[2])

        if field_name not in self.ALLOWED_FIELDS:
            await query.answer("❌ Champ non modifiable", show_alert=True)
            return

        if not self._verify_request_ownership(demande_id, update.effective_user.id):
            await self._update_view(query, "❌ Action non autorisée.")
            return

        demande = self._get_request_details(demande_id)
        if not demande:
            await self._update_view(query, "❌ Demande introuvable.")
            return

        if demande.get("statut") in ("⏳ En attente", "🔄 En cours") and field_name != "montant":
            await query.answer("🔒 Seul le tarif peut être rehaussé sur une demande en cours.", show_alert=True)
            return

        context.user_data["editing"] = {
            "demande_id": demande_id,
            "field": field_name,
            "current_montant": float(demande.get("montant") or 0.0),
        }

        text, keyboard = ui.build_edit_prompt_content(field_name, demande_id, demande, self.ALLOWED_FIELDS)
        await self._update_view(query, text, reply_markup=keyboard)

    async def handle_delete_request(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Demande confirmation avant suppression définitive."""
        query = update.callback_query
        if not query or not update.effective_user:
            return

        await query.answer()
        try:
            demande_id = int(data.replace("delete_", ""))
        except (ValueError, TypeError):
            await query.answer("❌ Identifiant invalide.", show_alert=True)
            return

        if not self._verify_request_ownership(demande_id, update.effective_user.id):
            await self._update_view(query, "❌ Action non autorisée.")
            return

        demande = self._get_request_details(demande_id)
        if not demande:
            await self._update_view(query, "❌ Demande introuvable.")
            return

        if demande.get("statut") not in ("📥 Reçue", "📨 Reçue", "🎯 Assignée (VIP)"):
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("📋 Mes demandes", callback_data="voir_demandes")
            ]])
            await self._update_view(
                query,
                "⚠️ Cette demande est déjà prise en charge et ne peut plus être supprimée directement.\n"
                "Utilisez le bouton d'annulation pour soumettre votre demande à l'opérateur.",
                reply_markup=kb
            )
            return

        text, keyboard = ui.build_delete_confirmation_content(demande)
        await self._update_view(query, text, reply_markup=keyboard)

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
                text, keyboard = ui.build_modify_menu_content(demande)
                await self._update_view(query, text, reply_markup=keyboard)
                return

        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")
        ]])
        await self._update_view(query, "❌ <b>Édition annulée.</b>", reply_markup=kb)

    async def handle_edit_text_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Intercepte la saisie texte transmise lorsque 'editing' est présent."""
        if not update.message or not update.message.text:
            return

        editing_data = context.user_data.get("editing")
        if not editing_data:
            return

        demande_id = editing_data["demande_id"]
        field_name = editing_data["field"]
        raw_text = update.message.text.strip()
        user_input = Validators.clean_input(raw_text)

        if field_name == "montant":
            try:
                nouveau_prix = float(user_input.replace(",", ".").replace("€", "").strip())
            except ValueError:
                await update.message.reply_text(
                    "❌ <b>Montant invalide.</b> Entrez un montant numérique (ex: <code>25</code> ou <code>30.50</code>) :",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="cancel_edit")]])
                )
                return

            ok, err_or_succ = self.db_manager.update_demande_montant(demande_id, nouveau_prix)
            if not ok:
                await update.message.reply_text(
                    f"⚠️ <b>Modification refusée :</b>\n{err_or_succ}\n\nRessaisissez une valeur valide ou annulez :",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="cancel_edit")]])
                )
                return

            context.user_data.pop("editing", None)

            demande = self._get_request_details(demande_id)
            if demande and demande.get("admin_en_charge"):
                try:
                    admin_id = demande["admin_en_charge"]
                    req_num = demande.get("request_number", demande_id)
                    prenom_c = html.escape(str(demande.get("prenom") or ""))
                    msg_staff = (
                        f"💰 <b>Revalorisation du tarif (Dossier #{req_num})</b>\n\n"
                        f"Le client a augmenté sa gratification pour le dossier de <b>{prenom_c}</b> !\n"
                        f"• Nouveau montant : <b>{nouveau_prix:.2f} €</b>"
                    )
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=msg_staff,
                        parse_mode="HTML",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("📄 Ouvrir le dossier", callback_data=f"retour_texte_{demande_id}")
                        ]])
                    )
                except Exception as notif_exc:
                    logger.warning("Notification réévaluation montant vers staff impossible : %s", notif_exc)

            await update.message.reply_text(
                f"✅ <b>Tarif mis à jour :</b> {nouveau_prix:.2f} € !\n"
                "La modification a été prise en compte avec succès.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("↩️ Retour à la demande", callback_data=f"modify_{demande_id}")
                ]])
            )
            return

        try:
            validated_value = self._validate_field_input(field_name, user_input)
            success = self._update_field_in_database(demande_id, field_name, validated_value)

            if success:
                context.user_data.pop("editing", None)
                field_label = self.ALLOWED_FIELDS.get(field_name, field_name)
                await update.message.reply_text(
                    f"✅ <b>{html.escape(field_label)}</b> mis à jour avec succès !",
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
                f"❌ <b>Saisie invalide :</b> {html.escape(str(err))}\n\n{help_text}\n\n"
                "Ressaisissez la valeur ou cliquez sur Annuler :",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("❌ Annuler", callback_data="cancel_edit")
                ]])
            )

    async def handle_confirm_delete(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Archive définitivement la demande sous le statut '🗑️ Supprimée'."""
        query = update.callback_query
        if not query or not update.effective_user:
            return

        await query.answer()
        try:
            demande_id = int(data.replace("confirm_delete_", ""))
        except (ValueError, TypeError):
            await query.answer("❌ Identifiant invalide.", show_alert=True)
            return

        if not self._verify_request_ownership(demande_id, update.effective_user.id):
            await self._update_view(query, "❌ Action non autorisée.")
            return

        demande = self.db_manager.archiver_demande_supprimee(
            demande_id=demande_id,
            raison="Supprimée par le demandeur"
        )

        if demande:
            logger.info("Demande #%s archivée sous '🗑️ Supprimée' par l'utilisateur %s", demande_id, update.effective_user.id)
            num_demande = demande.get("request_number", demande_id)
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("📋 Voir mes demandes", callback_data="voir_demandes"),
                InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")
            ]])
            await self._update_view(
                query,
                f"🗑️ <b>Demande n°{html.escape(str(num_demande))} supprimée et archivée sous « 🗑️ Supprimée ».</b>\n\n"
                "Une place vient d'être libérée dans votre quota.",
                reply_markup=kb
            )
        else:
            await self._update_view(query, "❌ Demande introuvable ou déjà prise en charge.")

    def _verify_request_ownership(self, demande_id: int, user_id: int) -> bool:
        """Contrôle la correspondance entre l'utilisateur et le créateur de la demande."""
        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute("SELECT user_id FROM demandes WHERE id = %s", (int(demande_id),))
                row = cursor.fetchone()
                return bool(row and int(row["user_id"]) == int(user_id))
        except Exception as exc:
            logger.error("Erreur contrôle propriété demande %s : %s", demande_id, exc)
            return False

    def _get_request_details(self, demande_id: int) -> dict:
        """Récupère l'intégralité d'un enregistrement de demande."""
        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute("SELECT * FROM demandes WHERE id = %s", (int(demande_id),))
                return cursor.fetchone()
        except Exception as exc:
            logger.error("Erreur extraction détails demande %s : %s", demande_id, exc)
            return None

    def _update_field_in_database(self, demande_id: int, field_name: str, value) -> bool:
        """Met à jour un champ autorisé en base à l'aide d'une requête statique précompilée."""
        sql_query = self._UPDATE_QUERIES.get(field_name)
        if not sql_query:
            logger.warning("Tentative de mise à jour sur un champ non autorisé : '%s'", field_name)
            return False

        try:
            with self.db_manager.transaction() as cursor:
                cursor.execute(sql_query, (value, int(demande_id)))
                return cursor.rowcount > 0
        except Exception as exc:
            logger.error("Erreur mise à jour SQL (%s) sur demande %s : %s", field_name, demande_id, exc)
            return False

    def _validate_field_input(self, field_name: str, user_input: str):
        """Valide et nettoie la valeur saisie selon les règles métier."""
        if user_input in ("-", "/skip", "skip", ""):
            if field_name in ("nom", "instagram", "snapchat", "details"):
                return None

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

    async def _update_view(self, query, text: str, reply_markup=None):
        """Met à jour le message qu'il s'agisse d'un message photo (caption) ou d'un message texte."""
        if query.message and query.message.photo:
            await query.edit_message_caption(
                caption=text,
                parse_mode="HTML",
                reply_markup=reply_markup
            )
        else:
            await query.edit_message_text(
                text=text,
                parse_mode="HTML",
                reply_markup=reply_markup
            )