"""Formulaire de création de demandes avec vérification des quotas."""

import logging
from functools import wraps
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
from utils.validators import ValidationError, Validators
from .navigation import NavigationManager

logger = logging.getLogger(__name__)


class FormulaireManager:
    """Gestionnaire du formulaire guidé de création de demande."""

    def __init__(self, db_manager, config, account_manager):
        self.db_manager = db_manager
        self.config = config
        self.account_manager = account_manager

        # Constantes d'états
        self.PRENOM = 1
        self.NOM = 2
        self.AGE = 3
        self.LOCALISATION = 4
        self.PHOTO = 5
        self.INSTAGRAM = 6
        self.SNAPCHAT = 7
        self.DETAILS = 8
        self.PRIORITAIRE = 9
        self.MONTANT = 10

        # Historique pour navigation arrière
        self.state_history = {
            self.NOM: self.PRENOM,
            self.AGE: self.NOM,
            self.LOCALISATION: self.AGE,
            self.PHOTO: self.LOCALISATION,
            self.INSTAGRAM: self.PHOTO,
            self.SNAPCHAT: self.INSTAGRAM,
            self.DETAILS: self.SNAPCHAT,
            self.PRIORITAIRE: self.DETAILS,
            self.MONTANT: self.PRIORITAIRE,
        }

        # Champs facultatifs
        self.skippable_fields = {
            self.NOM, self.INSTAGRAM, self.SNAPCHAT, self.DETAILS
        }

        self.navigation = NavigationManager(self)
        logger.info("FormulaireManager initialisé")

    def get_conversation_handler(self):
        """Retourne le ConversationHandler complet du formulaire."""
        nav_pattern = "^form_(back|skip|cancel)($|_.*)"
        return ConversationHandler(
            entry_points=[
                CommandHandler("new", self.new_demande),
                CallbackQueryHandler(self.new_demande_from_callback, pattern="^new_demande$"),
            ],
            states={
                self.PRENOM: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.prenom),
                    CallbackQueryHandler(self.navigation.handle_form_navigation, pattern=nav_pattern),
                ],
                self.NOM: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.nom),
                    CommandHandler("skip", self.skip_nom),
                    CallbackQueryHandler(self.navigation.handle_form_navigation, pattern=nav_pattern),
                ],
                self.AGE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.age),
                    CallbackQueryHandler(self.navigation.handle_form_navigation, pattern=nav_pattern),
                ],
                self.LOCALISATION: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.localisation),
                    CallbackQueryHandler(self.navigation.handle_form_navigation, pattern=nav_pattern),
                ],
                self.PHOTO: [
                    MessageHandler(filters.PHOTO, self.photo),
                    CallbackQueryHandler(self.navigation.handle_form_navigation, pattern=nav_pattern),
                ],
                self.INSTAGRAM: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.instagram),
                    CommandHandler("skip", self.skip_instagram),
                    CallbackQueryHandler(self.navigation.handle_form_navigation, pattern=nav_pattern),
                ],
                self.SNAPCHAT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.snapchat),
                    CommandHandler("skip", self.skip_snapchat),
                    CallbackQueryHandler(self.navigation.handle_form_navigation, pattern=nav_pattern),
                ],
                self.DETAILS: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.details),
                    CommandHandler("skip", self.skip_details),
                    CallbackQueryHandler(self.navigation.handle_form_navigation, pattern=nav_pattern),
                ],
                self.PRIORITAIRE: [
                    CallbackQueryHandler(self.handle_priority_choice, pattern="^(priorite_oui|priorite_non)$"),
                    CallbackQueryHandler(self.navigation.handle_form_navigation, pattern=nav_pattern),
                ],
                self.MONTANT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.montant),
                    CallbackQueryHandler(self.navigation.handle_form_navigation, pattern=nav_pattern),
                ],
            },
            fallbacks=[
                CommandHandler("cancel", self.cancel),
                CommandHandler("stop", self.cancel),
            ],
            name="demande_creation",
            persistent=False,
            allow_reentry=True,
        )

    async def _check_service_active(self, update: Update) -> bool:
        """Vérifie si les demandes sont acceptées actuellement."""
        if not self.config.are_demandes_enabled():
            msg = (
                "🚫 <b>Création de demandes suspendue</b>\n\n"
                "Le service est momentanément désactivé par l'administration. "
                "Merci de retenter ultérieurement."
            )
            if update.callback_query:
                await update.callback_query.answer("🚫 Demandes désactivées", show_alert=True)
                await update.callback_query.edit_message_text(msg, parse_mode="HTML")
            elif update.message:
                await update.message.reply_text(msg, parse_mode="HTML")
            return False
        return True

    async def _check_quotas(self, update: Update, user_id: int) -> bool:
        """Vérifie que les quotas global et personnel ne sont pas atteints."""
        # 1. Vérification du quota global
        max_total = self.config.get_max_total_demandes()
        if max_total > 0:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute("SELECT COUNT(*) AS total FROM demandes WHERE statut NOT IN ('❌ Abandonnée')")
                row = cursor.fetchone()
                total_actif = row["total"] if row else 0

            if total_actif >= max_total:
                msg = (
                    "🚫 <b>Service complet</b>\n\n"
                    "Le plafond global de demandes acceptées sur la plateforme a été atteint.\n"
                    "Merci de réessayer un peu plus tard."
                )
                if update.callback_query:
                    await update.callback_query.answer("Plafond global atteint.", show_alert=True)
                    await update.callback_query.edit_message_text(
                        msg,
                        parse_mode="HTML",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")]])
                    )
                elif update.message:
                    await update.message.reply_text(msg, parse_mode="HTML")
                return False

        # 2. Vérification du quota personnel
        max_user = self.config.get_max_demandes_per_user()
        if max_user > 0:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) AS count_user FROM demandes WHERE user_id = %s AND statut NOT IN ('❌ Abandonnée')",
                    (user_id,)
                )
                row = cursor.fetchone()
                user_actif = row["count_user"] if row else 0

            if user_actif >= max_user:
                msg = (
                    "⚠️ <b>Limite atteinte</b>\n\n"
                    f"Vous avez déjà <b>{user_actif}/{max_user}</b> demande(s) active(s).\n"
                    "Vous devez attendre le traitement d'une demande existante avant d'en créer une nouvelle."
                )
                if update.callback_query:
                    await update.callback_query.answer("Quota individuel atteint.", show_alert=True)
                    await update.callback_query.edit_message_text(
                        msg,
                        parse_mode="HTML",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")]])
                    )
                elif update.message:
                    await update.message.reply_text(msg, parse_mode="HTML")
                return False

        return True

    async def new_demande(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Initialise le formulaire via la commande /new."""
        if not await self._check_service_active(update):
            return ConversationHandler.END

        user_id = update.effective_user.id
        if not await self._check_quotas(update, user_id):
            return ConversationHandler.END

        registered = await self.account_manager.ensure_user_registered(update)
        if not registered:
            if update.message:
                await update.message.reply_text("❌ Impossible d'enregistrer votre compte.")
            return ConversationHandler.END

        context.user_data["demande"] = {}
        context.user_data["user_id"] = user_id

        await update.message.reply_text(
            "📝 <b>Création d'une nouvelle demande</b>\n\n"
            "Pour démarrer, quel est le <b>prénom</b> de la personne ?",
            parse_mode="HTML",
            reply_markup=self.navigation.create_navigation_keyboard(self.PRENOM),
        )
        return self.PRENOM

    async def new_demande_from_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Initialise le formulaire suite à un clic sur bouton Inline."""
        query = update.callback_query
        if not query:
            return ConversationHandler.END

        await query.answer()

        if not await self._check_service_active(update):
            return ConversationHandler.END

        user_id = query.from_user.id
        if not await self._check_quotas(update, user_id):
            return ConversationHandler.END

        registered = await self.account_manager.ensure_user_registered(update)
        if not registered:
            await query.edit_message_text("❌ Impossible d'enregistrer votre compte.")
            return ConversationHandler.END

        context.user_data["demande"] = {}
        context.user_data["user_id"] = user_id

        await query.edit_message_text(
            "📝 <b>Création d'une nouvelle demande</b>\n\n"
            "Pour démarrer, quel est le <b>prénom</b> de la personne ?",
            parse_mode="HTML",
            reply_markup=self.navigation.create_navigation_keyboard(self.PRENOM),
        )
        return self.PRENOM

    async def prenom(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text:
            return self.PRENOM

        user_input = Validators.clean_input(update.message.text)
        try:
            val = Validators.validate_prenom(user_input)
            context.user_data.setdefault("demande", {})["prenom"] = val

            await update.message.reply_text(
                f"✅ Prénom enregistré : <b>{val}</b>\n\n"
                "Indiquez maintenant son nom de famille (ou cliquez sur Passer) :",
                parse_mode="HTML",
                reply_markup=self.navigation.create_navigation_keyboard(self.NOM, include_skip=True),
            )
            return self.NOM
        except ValidationError as err:
            await update.message.reply_text(
                f"❌ {err}\n\nVeuillez ressaisir le prénom :",
                parse_mode="HTML",
                reply_markup=self.navigation.create_navigation_keyboard(self.PRENOM),
            )
            return self.PRENOM

    async def nom(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text:
            return self.NOM

        user_input = Validators.clean_input(update.message.text)
        try:
            val = Validators.validate_nom(user_input)
            context.user_data.setdefault("demande", {})["nom"] = val

            await update.message.reply_text(
                f"✅ Nom enregistré : <b>{val}</b>\n\n"
                "Indiquez maintenant son âge (entre 18 et 40 ans) :",
                parse_mode="HTML",
                reply_markup=self.navigation.create_navigation_keyboard(self.AGE),
            )
            return self.AGE
        except ValidationError as err:
            await update.message.reply_text(
                f"❌ {err}\n\nVeuillez ressaisir le nom ou passer cette étape :",
                parse_mode="HTML",
                reply_markup=self.navigation.create_navigation_keyboard(self.NOM, include_skip=True),
            )
            return self.NOM

    async def skip_nom(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data.setdefault("demande", {})["nom"] = None
        text = "⏭️ Nom ignoré.\n\nIndiquez son âge (entre 18 et 40 ans) :"
        kb = self.navigation.create_navigation_keyboard(self.AGE)

        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=kb)
        else:
            await update.message.reply_text(text, reply_markup=kb)
        return self.AGE

    async def age(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text:
            return self.AGE

        user_input = Validators.clean_input(update.message.text)
        try:
            val = Validators.validate_age(user_input)
            context.user_data.setdefault("demande", {})["age"] = val

            await update.message.reply_text(
                f"✅ Âge enregistré : <b>{val} ans</b>\n\n"
                "Sa localisation (ville, département ou région) :",
                parse_mode="HTML",
                reply_markup=self.navigation.create_navigation_keyboard(self.LOCALISATION),
            )
            return self.LOCALISATION
        except ValidationError as err:
            await update.message.reply_text(
                f"❌ {err}\n\nVeuillez ressaisir un âge valide :",
                parse_mode="HTML",
                reply_markup=self.navigation.create_navigation_keyboard(self.AGE),
            )
            return self.AGE

    async def localisation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text:
            return self.LOCALISATION

        user_input = Validators.clean_input(update.message.text)
        try:
            val = Validators.validate_localisation(user_input)
            context.user_data.setdefault("demande", {})["localisation"] = val

            await update.message.reply_text(
                f"✅ Localisation enregistrée : <b>{val}</b>\n\n"
                "📸 Envoyez une photo pour accompagner la demande :",
                parse_mode="HTML",
                reply_markup=self.navigation.create_navigation_keyboard(self.PHOTO),
            )
            return self.PHOTO
        except ValidationError as err:
            await update.message.reply_text(
                f"❌ {err}\n\nVeuillez ressaisir la localisation :",
                parse_mode="HTML",
                reply_markup=self.navigation.create_navigation_keyboard(self.LOCALISATION),
            )
            return self.LOCALISATION

    async def photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.photo:
            if update.message:
                await update.message.reply_text(
                    "❌ Veuillez envoyer une photo directement via Telegram (fichier compressé standard).",
                    reply_markup=self.navigation.create_navigation_keyboard(self.PHOTO),
                )
            return self.PHOTO

        try:
            photos = update.message.photo
            best = photos[-1]
            for p in sorted(photos, key=lambda x: x.file_size or 0, reverse=True):
                if p.width <= 1280 and p.height <= 1280:
                    best = p
                    break

            context.user_data.setdefault("demande", {})["photo_id"] = best.file_id

            await update.message.reply_text(
                "✅ Photo reçue avec succès !\n\n"
                "Indiquez son profil <b>Instagram</b> (ou passez) :",
                parse_mode="HTML",
                reply_markup=self.navigation.create_navigation_keyboard(self.INSTAGRAM, include_skip=True),
            )
            return self.INSTAGRAM
        except Exception as exc:
            logger.error("Erreur lors de la capture photo: %s", exc)
            await update.message.reply_text(
                "❌ Une erreur est survenue lors de la réception de la photo. Merci de réessayer.",
                reply_markup=self.navigation.create_navigation_keyboard(self.PHOTO),
            )
            return self.PHOTO

    async def instagram(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text:
            return self.INSTAGRAM

        user_input = Validators.clean_input(update.message.text)
        try:
            val = Validators.validate_instagram(user_input)
            if val is None:
                return await self.skip_instagram(update, context)

            context.user_data.setdefault("demande", {})["instagram"] = val
            await update.message.reply_text(
                f"✅ Instagram enregistré : <b>@{val}</b>\n\n"
                "Indiquez son nom d'utilisateur <b>Snapchat</b> (ou passez) :",
                parse_mode="HTML",
                reply_markup=self.navigation.create_navigation_keyboard(self.SNAPCHAT, include_skip=True),
            )
            return self.SNAPCHAT
        except ValidationError as err:
            await update.message.reply_text(
                f"❌ {err}\n\nVeuillez ressaisir son compte Instagram ou passer :",
                parse_mode="HTML",
                reply_markup=self.navigation.create_navigation_keyboard(self.INSTAGRAM, include_skip=True),
            )
            return self.INSTAGRAM

    async def skip_instagram(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data.setdefault("demande", {})["instagram"] = None
        text = "⏭️ Instagram ignoré.\n\nIndiquez son compte <b>Snapchat</b> (ou passez) :"
        kb = self.navigation.create_navigation_keyboard(self.SNAPCHAT, include_skip=True)

        if update.callback_query:
            await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
        else:
            await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb)
        return self.SNAPCHAT

    async def snapchat(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text:
            return self.SNAPCHAT

        user_input = Validators.clean_input(update.message.text)
        try:
            val = Validators.validate_snapchat(user_input)
            if val is None:
                return await self.skip_snapchat(update, context)

            context.user_data.setdefault("demande", {})["snapchat"] = val
            await update.message.reply_text(
                f"✅ Snapchat enregistré : <b>{val}</b>\n\n"
                "Avez-vous des détails ou remarques supplémentaires à ajouter ?",
                parse_mode="HTML",
                reply_markup=self.navigation.create_navigation_keyboard(self.DETAILS, include_skip=True),
            )
            return self.DETAILS
        except ValidationError as err:
            await update.message.reply_text(
                f"❌ {err}\n\nVeuillez ressaisir son compte Snapchat ou passer :",
                parse_mode="HTML",
                reply_markup=self.navigation.create_navigation_keyboard(self.SNAPCHAT, include_skip=True),
            )
            return self.SNAPCHAT

    async def skip_snapchat(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data.setdefault("demande", {})["snapchat"] = None
        text = "⏭️ Snapchat ignoré.\n\nAvez-vous des détails ou remarques supplémentaires à ajouter ?"
        kb = self.navigation.create_navigation_keyboard(self.DETAILS, include_skip=True)

        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=kb)
        else:
            await update.message.reply_text(text, reply_markup=kb)
        return self.DETAILS

    async def details(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text:
            return self.DETAILS

        user_input = Validators.clean_input(update.message.text)
        try:
            if user_input and not Validators.is_skip_command(user_input):
                val = Validators.validate_details(user_input)
                context.user_data.setdefault("demande", {})["details"] = val
                confirm_txt = f"✅ Détails notés : <i>{val}</i>\n\n"
            else:
                context.user_data.setdefault("demande", {})["details"] = None
                confirm_txt = "⏭️ Aucun détail supplémentaire noté.\n\n"

            reply_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("⭐ Oui - Prioritaire", callback_data="priorite_oui")],
                [InlineKeyboardButton("📝 Non - Standard", callback_data="priorite_non")],
                [InlineKeyboardButton("⬅️ Retour", callback_data=f"form_back_{self.PRIORITAIRE}")],
                [InlineKeyboardButton("❌ Annuler", callback_data="form_cancel")],
            ])

            await update.message.reply_text(
                f"{confirm_txt}💎 <b>Souhaitez-vous une demande prioritaire ?</b>\n\n"
                "Les demandes prioritaires nécessitent un montant et sont examinées en priorité.",
                reply_markup=reply_markup,
                parse_mode="HTML",
            )
            return self.PRIORITAIRE
        except ValidationError as err:
            await update.message.reply_text(
                f"❌ {err}\n\nVeuillez ressaisir les détails ou passer :",
                parse_mode="HTML",
                reply_markup=self.navigation.create_navigation_keyboard(self.DETAILS, include_skip=True),
            )
            return self.DETAILS

    async def skip_details(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data.setdefault("demande", {})["details"] = None
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("⭐ Oui - Prioritaire", callback_data="priorite_oui")],
            [InlineKeyboardButton("📝 Non - Standard", callback_data="priorite_non")],
            [InlineKeyboardButton("⬅️ Retour", callback_data=f"form_back_{self.PRIORITAIRE}")],
            [InlineKeyboardButton("❌ Annuler", callback_data="form_cancel")],
        ])
        msg = (
            "⏭️ Détails ignorés.\n\n"
            "💎 <b>Souhaitez-vous une demande prioritaire ?</b>\n\n"
            "Les demandes prioritaires nécessitent un montant et sont examinées en priorité."
        )
        if update.callback_query:
            await update.callback_query.edit_message_text(msg, reply_markup=reply_markup, parse_mode="HTML")
        else:
            await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode="HTML")
        return self.PRIORITAIRE

    async def handle_priority_choice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if not query:
            return self.PRIORITAIRE

        await query.answer()
        if query.data == "priorite_oui":
            await query.edit_message_text(
                "💰 <b>Demande prioritaire</b>\n\n"
                "Indiquez le montant alloué (en €) :",
                parse_mode="HTML",
                reply_markup=self.navigation.create_navigation_keyboard(self.MONTANT),
            )
            return self.MONTANT

        demande = context.user_data.setdefault("demande", {})
        demande["prioritaire"] = False
        demande["montant"] = 0

        await self.save_demande(update, context)
        return ConversationHandler.END

    async def montant(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text:
            return self.MONTANT

        user_input = Validators.clean_input(update.message.text)
        try:
            val = Validators.validate_amount(user_input)
            demande = context.user_data.setdefault("demande", {})
            demande["montant"] = val
            demande["prioritaire"] = True

            await self.save_demande(update, context)
            return ConversationHandler.END
        except ValidationError as err:
            await update.message.reply_text(
                f"❌ {err}\n\nVeuillez ressaisir un montant valide :",
                parse_mode="HTML",
                reply_markup=self.navigation.create_navigation_keyboard(self.MONTANT),
            )
            return self.MONTANT

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data.pop("demande", None)
        msg = "❌ Création de demande annulée.\nTapez /start pour revenir au menu."
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(msg)
        elif update.message:
            await update.message.reply_text(msg)
        return ConversationHandler.END

    async def save_demande(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enregistre définitivement la demande dans MySQL."""
        demande = context.user_data.get("demande", {})
        user_id = update.effective_user.id if update.effective_user else None

        if not user_id or "prenom" not in demande:
            logger.error("Tentative de sauvegarde d'une demande invalide ou incomplète.")
            return

        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    "SELECT COALESCE(MAX(request_number), 0) + 1 AS next_num FROM demandes WHERE user_id = %s",
                    (user_id,),
                )
                next_num = cursor.fetchone()["next_num"]

                cursor.execute(
                    """
                    INSERT INTO demandes (
                        user_id, prenom, nom, age, localisation, photo_id,
                        instagram, snapchat, details, prioritaire, montant, statut, request_number
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        user_id,
                        demande.get("prenom"),
                        demande.get("nom"),
                        demande.get("age"),
                        demande.get("localisation"),
                        demande.get("photo_id"),
                        demande.get("instagram"),
                        demande.get("snapchat"),
                        demande.get("details"),
                        demande.get("prioritaire", False),
                        demande.get("montant", 0),
                        "📨 Reçue",
                        next_num,
                    ),
                )
                demande_id = cursor.lastrowid

            context.user_data.pop("demande", None)
            logger.info("Demande #%s créée (ID: %s) pour l'utilisateur %s", next_num, demande_id, user_id)

            type_txt = "💎 Prioritaire" if demande.get("prioritaire") else "📝 Standard"
            montant_txt = f" ({demande.get('montant', 0):.2f}€)" if demande.get("prioritaire") else ""
            nom_complet = f"{demande['prenom']} {demande.get('nom') or ''}".strip()

            recap = (
                f"✅ <b>Demande n°{next_num} enregistrée avec succès !</b>\n\n"
                f"👤 <b>Identité :</b> {nom_complet}\n"
                f"🎂 <b>Âge :</b> {demande.get('age')} ans\n"
                f"📍 <b>Localisation :</b> {demande.get('localisation')}\n"
                f"🎯 <b>Type :</b> {type_txt}{montant_txt}\n\n"
                "Elle sera prise en charge prochainement.\n"
                "Tapez /demandes pour suivre son avancement."
            )

            if update.callback_query:
                await update.callback_query.edit_message_text(recap, parse_mode="HTML")
            elif update.message:
                await update.message.reply_text(recap, parse_mode="HTML")

        except Exception as exc:
            logger.error("Erreur lors de la sauvegarde de la demande: %s", exc, exc_info=True)
            err_msg = "❌ Erreur technique lors de la sauvegarde. Veuillez contacter un administrateur."
            if update.callback_query:
                await update.callback_query.edit_message_text(err_msg)
            elif update.message:
                await update.message.reply_text(err_msg)