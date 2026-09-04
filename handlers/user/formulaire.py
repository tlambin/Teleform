"""Formulaire de création de demandes selon [source 3]"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from utils.validators import Validators, ValidationError
from .navigation import NavigationManager
from functools import wraps

logger = logging.getLogger(__name__)

class FormulaireManager:
    """Gestionnaire formulaire - ÉTAPE 3.1 selon migration progressive"""

    def __init__(self, db_manager, config, account_manager):
        """Initialisation avec CompteManager injecté selon ÉTAPE 2"""
        self.db_manager = db_manager
        self.config = config
        self.account_manager = account_manager  # ✅ Référence vers CompteManager selon ÉTAPE 2

        # ✅ CONSTANTES CONVERSATION selon [source 3]
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

        # HISTORIQUE DES ÉTATS pour navigation retour
        self.state_history = {
            self.NOM: self.PRENOM,
            self.AGE: self.NOM,
            self.LOCALISATION: self.AGE,
            self.PHOTO: self.LOCALISATION,
            self.INSTAGRAM: self.PHOTO,
            self.SNAPCHAT: self.INSTAGRAM,
            self.DETAILS: self.SNAPCHAT,
            self.PRIORITAIRE: self.DETAILS,
            self.MONTANT: self.PRIORITAIRE
        }

        # CHAMPS AVEC OPTION SKIP
        self.skippable_fields = {
            self.NOM, self.INSTAGRAM, self.SNAPCHAT, self.DETAILS
        }

        # INITIALISATION NAVIGATIONMANAGER
        self.navigation = NavigationManager(self)
        logger.info("FormulaireManager initialisé - Migration ÉTAPE 3.1")

    def get_conversation_handler(self):
        """Retourne ConversationHandler complet selon [source 3]"""
        return ConversationHandler(
            entry_points=[
                CommandHandler('new', self.new_demande),
                CallbackQueryHandler(self.new_demande_from_callback, pattern="^new_demande$")
            ],
            states={
                self.PRENOM: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.prenom),
                    CallbackQueryHandler(self.navigation.handle_form_navigation, pattern="^form_(back|skip|cancel)($|_.*)")
                ],
                self.NOM: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.nom),
                    CommandHandler('skip', self.skip_nom),
                    CallbackQueryHandler(self.navigation.handle_form_navigation, pattern="^form_(back|skip|cancel)($|_.*)")
                ],
                self.AGE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.age),
                    CallbackQueryHandler(self.navigation.handle_form_navigation, pattern="^form_(back|skip|cancel)($|_.*)")
                ],
                self.LOCALISATION: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.localisation),
                    CallbackQueryHandler(self.navigation.handle_form_navigation, pattern="^form_(back|skip|cancel)($|_.*)")
                ],
                self.PHOTO: [
                    MessageHandler(filters.PHOTO, self.photo),
                    CallbackQueryHandler(self.navigation.handle_form_navigation, pattern="^form_(back|skip|cancel)($|_.*)")
                ],
                self.INSTAGRAM: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.instagram),
                    CommandHandler('skip', self.skip_instagram),
                    CallbackQueryHandler(self.navigation.handle_form_navigation, pattern="^form_(back|skip|cancel)($|_.*)")
                ],
                self.SNAPCHAT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.snapchat),
                    CommandHandler('skip', self.skip_snapchat),
                    CallbackQueryHandler(self.navigation.handle_form_navigation, pattern="^form_(back|skip|cancel)($|_.*)")
                ],
                self.DETAILS: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.details),
                    CommandHandler('skip', self.skip_details),
                    CallbackQueryHandler(self.navigation.handle_form_navigation, pattern="^form_(back|skip|cancel)($|_.*)")
                ],
                self.PRIORITAIRE: [
                    CallbackQueryHandler(self.handle_priority_choice, pattern="^(priorite_oui|priorite_non)$"),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_priority_choice),
                    CallbackQueryHandler(self.navigation.handle_form_navigation, pattern="^form_(back|skip|cancel)($|_.*)")
                ],
                self.MONTANT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.montant),
                    CallbackQueryHandler(self.navigation.handle_form_navigation, pattern="^form_(back|skip|cancel)($|_.*)")
                ]
            },
            fallbacks=[CommandHandler('cancel', self.cancel)],
            name="demande_creation"
        )

    def require_demandes_enabled(func):
        """Décorateur pour vérifier si les demandes sont activées"""
        @wraps(func)
        async def wrapper(update, context, *args, **kwargs):
            # Récupérer l'instance config depuis le context ou self
            config = context.bot_data.get('config')

            if not config or not config.are_demandes_enabled():
                await update.message.reply_text(
                    "🚫 **Création de demandes temporairement désactivée**\n\n"
                    "Les demandes sont actuellement suspendues par l'administration. "
                    "Veuillez réessayer plus tard.",
                    parse_mode='Markdown'
                )
                return

            return await func(update, context, *args, **kwargs)
        return wrapper

    async def new_demande(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Démarrage formulaire selon [source 3]"""
        # ✅ VÉRIFICATION VIA CompteManager selon ÉTAPE 2
        user_registered = await self.account_manager.ensure_user_registered(update)
        if not user_registered:
            await update.message.reply_text("❌ Erreur d'enregistrement utilisateur")
            return

        # ✅ WORKFLOW CRÉATION selon votre code existant
        if update.callback_query:
            await update.callback_query.answer()

        user_id = update.effective_user.id
        context.user_data.clear()
        context.user_data['user_id'] = user_id

        # INITIALISATION STRUCTURE DEMANDE
        context.user_data['demande'] = {}

        # Message de bienvenue workflow
        await update.message.reply_text(
            "📝 <b>Création d'une nouvelle demande</b>\n\n"
            "Nous allons créer votre demande étape par étape.\n\n"
            "Pour commencer, quel est son <b>prénom</b> ?",
            parse_mode='HTML'
        )

        return self.PRENOM

    async def new_demande_from_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Version callback pour bouton "Faire une demande" selon architecture modulaire"""
        query = update.callback_query
        await query.answer()

        # VÉRIFICATION VIA CompteManager selon ÉTAPE 2
        user_registered = await self.account_manager.ensure_user_registered(update)
        if not user_registered:
            await query.edit_message_text("❌ Erreur d'enregistrement utilisateur")
            return ConversationHandler.END

        user_id = query.from_user.id
        context.user_data.clear()
        context.user_data['user_id'] = user_id

        # INITIALISATION STRUCTURE DEMANDE
        context.user_data['demande'] = {}

        # Message de bienvenue workflow
        await query.edit_message_text(
            "📝 <b>Création d'une nouvelle demande</b>\n\n"
            "Nous allons créer votre demande étape par étape.\n\n"
            "Pour commencer, quel est son <b>prénom</b> ?",
            parse_mode='HTML'
        )

        return self.PRENOM

    async def prenom(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_input = Validators.clean_input(update.message.text)

        try:
            validated_prenom = Validators.validate_prenom(user_input)
            context.user_data['demande']['prenom'] = validated_prenom

            await update.message.reply_text(
                f"✅ Prénom enregistré : <b>{validated_prenom}</b>\n\n"
                "Maintenant, son nom de famille :",
                parse_mode='HTML',
                reply_markup=self.navigation.create_navigation_keyboard(self.NOM, include_skip=True)
            )
            return self.NOM

        except ValidationError as e:
            await update.message.reply_text(
                f"❌ {str(e)}\n\n"
                f"{Validators.get_validation_help('prenom')}\n\n"
                "Veuillez ressaisir le prénom :",
                parse_mode='HTML',
                reply_markup=self.navigation.create_navigation_keyboard(self.PRENOM)
            )
            return self.PRENOM

    async def nom(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_input = Validators.clean_input(update.message.text)

        try:
            validated_nom = Validators.validate_nom(user_input)
            context.user_data['demande']['nom'] = validated_nom

            nom_display = f" {validated_nom}" if validated_nom else ""
            await update.message.reply_text(
                f"✅ Nom enregistré : <b>{context.user_data['demande']['prenom']}{nom_display}</b>\n\n"
                "Maintenant, son âge (18-40 ans) :",
                parse_mode='HTML',
                reply_markup=self.navigation.create_navigation_keyboard(self.AGE)
            )
            return self.AGE

        except ValidationError as e:
            await update.message.reply_text(
                f"❌ {str(e)}\n\n"
                "Veuillez ressaisir le nom ou passez :",
                parse_mode='HTML',
                reply_markup=self.navigation.create_navigation_keyboard(self.NOM, include_skip=True)
            )
            return self.NOM

    async def skip_nom(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['demande']['nom'] = None
        await update.message.reply_text(
            "⏭️ Nom passé.\n\nSon âge (18-40 ans) :",
            reply_markup=self.navigation.create_navigation_keyboard(self.AGE)
        )
        return self.AGE

    async def age(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Traite la saisie de l'âge avec validation centralisée"""
        user_input = Validators.clean_input(update.message.text)

        try:
            # ✅ CORRECT - Validation centralisée
            validated_age = Validators.validate_age(user_input)
            context.user_data['demande']['age'] = validated_age

            await update.message.reply_text(
                f"✅ Âge enregistré : <b>{validated_age} ans</b>\n\n"
                "Sa localisation (ville, région ou pays) :",
                parse_mode='HTML',
                reply_markup=self.navigation.create_navigation_keyboard(self.LOCALISATION)
            )
            return self.LOCALISATION

        except ValidationError as e:
            await update.message.reply_text(
                f"❌ {str(e)}\n\n"
                f"{Validators.get_validation_help('age')}\n\n"
                "Veuillez ressaisir l'âge :",
                parse_mode='HTML',
                reply_markup=self.navigation.create_navigation_keyboard(self.AGE)
            )
            return self.AGE

    async def localisation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Traite la saisie de la localisation avec validation centralisée"""
        user_input = Validators.clean_input(update.message.text)

        try:
            # ✅ Validation centralisée spécialisée
            validated_localisation = Validators.validate_localisation(user_input)
            context.user_data['demande']['localisation'] = validated_localisation

            await update.message.reply_text(
                f"✅ Localisation enregistrée : <b>{validated_localisation}</b>\n\n"
                "📸 Envoyez maintenant une photo :",
                parse_mode='HTML',
                reply_markup=self.navigation.create_navigation_keyboard(self.PHOTO)
            )
            return self.PHOTO

        except ValidationError as e:
            await update.message.reply_text(
                f"❌ {str(e)}\n\n"
                f"{Validators.get_validation_help('localisation')}\n\n"
                "Veuillez ressaisir la localisation :",
                parse_mode='HTML',
                reply_markup=self.navigation.create_navigation_keyboard(self.LOCALISATION)
            )
            return self.LOCALISATION

    async def photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message.photo:
            await update.message.reply_text(
                "❌ Merci d'envoyer une photo pour continuer la demande.",
                reply_markup=self.navigation.create_navigation_keyboard(self.PHOTO)
            )
            return self.PHOTO
        try:
            photo_sizes = update.message.photo

            # Sélection optimale : 1280px max pour qualité/performance
            best_photo = None
            for photo in sorted(photo_sizes, key=lambda x: x.file_size or 0, reverse=True):
                if photo.width <= 1280 and photo.height <= 1280:
                    best_photo = photo
                    break

            # Fallback : si toutes les photos sont > 1280px, prendre la plus petite
            if not best_photo:
                best_photo = min(photo_sizes, key=lambda x: x.file_size or 0)

            # Stocker le file_id directement
            context.user_data['demande']['photo_id'] = best_photo.file_id

            await update.message.reply_text(
                "✅ Photo reçue !\n\n"
                "Son Instagram :",
                reply_markup=self.navigation.create_navigation_keyboard(self.INSTAGRAM, include_skip=True)
            )
            return self.INSTAGRAM

        except Exception as e:
            logger.error(f"Erreur photo: {e}")
            await update.message.reply_text(
                "❌ Erreur lors du traitement de la photo",
                reply_markup=self.navigation.create_navigation_keyboard(self.PHOTO)
            )
            return self.PHOTO

    async def instagram(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Traite la saisie Instagram avec validation centralisée"""
        user_input = Validators.clean_input(update.message.text)

        try:
            validated_instagram = Validators.validate_instagram(user_input)

            if validated_instagram is None:
                return await self.skip_instagram(update, context)

            context.user_data['demande']['instagram'] = validated_instagram

            await update.message.reply_text(
                f"✅ Instagram enregistré : <b>@{validated_instagram}</b>\n\n"
                "Son Snapchat :",
                parse_mode='HTML',
                reply_markup=self.navigation.create_navigation_keyboard(self.SNAPCHAT, include_skip=True)
            )
            return self.SNAPCHAT

        except ValidationError as e:
            await update.message.reply_text(
                f"❌ {str(e)}\n\n"
                f"{Validators.get_validation_help('instagram')}\n\n"
                "Veuillez ressaisir son Instagram ou passez :",
                parse_mode='HTML',
                reply_markup=self.navigation.create_navigation_keyboard(self.INSTAGRAM, include_skip=True)
            )
            return self.INSTAGRAM

    async def skip_instagram(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['demande']['instagram'] = None
        await update.message.reply_text(
            "⏭️ Instagram passé.\n\nSon Snapchat :",
            reply_markup=self.navigation.create_navigation_keyboard(self.SNAPCHAT, include_skip=True)
        )
        return self.SNAPCHAT

    async def snapchat(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Traite la saisie Snapchat avec validation centralisée"""
        user_input = Validators.clean_input(update.message.text)

        try:
            validated_snapchat = Validators.validate_snapchat(user_input)

            if validated_snapchat is None:
                # Skip détecté automatiquement par validator
                return await self.skip_snapchat(update, context)

            context.user_data['demande']['snapchat'] = validated_snapchat

            await update.message.reply_text(
                f"✅ Snapchat enregistré : <b>{validated_snapchat}</b>\n\n"
                "Des détails supplémentaires ? :",
                parse_mode='HTML',
                reply_markup=self.navigation.create_navigation_keyboard(self.DETAILS, include_skip=True)
            )
            return self.DETAILS

        except ValidationError as e:
            await update.message.reply_text(
                f"❌ {str(e)}\n\n"
                f"{Validators.get_validation_help('snapchat')}\n\n"
                "Veuillez ressaisir son Snapchat ou passez :",
                parse_mode='HTML',
                reply_markup=self.navigation.create_navigation_keyboard(self.SNAPCHAT, include_skip=True)
            )
            return self.SNAPCHAT

    async def skip_snapchat(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['demande']['snapchat'] = None
        await update.message.reply_text(
            "⏭️ Snapchat passé.\n\nDes détails supplémentaires :",
            reply_markup=self.navigation.create_navigation_keyboard(self.DETAILS, include_skip=True)
        )
        return self.DETAILS

    async def details(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Traite la saisie des détails avec validation centralisée"""
        user_input = Validators.clean_input(update.message.text)

        try:
            if user_input and not Validators.is_skip_command(user_input):
                # ✅ Validation centralisée spécialisée
                validated_details = Validators.validate_details(user_input)
                context.user_data['demande']['details'] = validated_details
                await update.message.reply_text(f"✅ Détails enregistrés : <b>{validated_details}</b>\n\n", parse_mode='HTML')
            else:
                context.user_data['demande']['details'] = None
                await update.message.reply_text("⏭️ Détails passés.\n\n")

            # Demander si c'est prioritaire
            keyboard = [
                [InlineKeyboardButton("⭐ Oui - Prioritaire", callback_data="priorite_oui")],
                [InlineKeyboardButton("📝 Non - Standard", callback_data="priorite_non")],
                [InlineKeyboardButton("⬅️ Retour", callback_data=f"form_back_{self.PRIORITAIRE}")],
                [InlineKeyboardButton("❌ Annuler", callback_data="form_cancel")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                "💎 <b>Demande prioritaire ?</b>\n\n"
                "Les demandes prioritaires nécessitent un montant et sont traitées en premier.",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            return self.PRIORITAIRE

        except ValidationError as e:
            await update.message.reply_text(
                f"❌ {str(e)}\n\n"
                "Veuillez ressaisir les détails ou passez :",
                parse_mode='HTML',
                reply_markup=self.navigation.create_navigation_keyboard(self.DETAILS, include_skip=True)
            )
            return self.DETAILS

    async def skip_details(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['demande']['details'] = None

        # Demander si c'est prioritaire
        keyboard = [
            [InlineKeyboardButton("⭐ Oui - Prioritaire", callback_data="priorite_oui")],
            [InlineKeyboardButton("📝 Non - Standard", callback_data="priorite_non")],
            [InlineKeyboardButton("⬅️ Retour", callback_data=f"form_back_{self.PRIORITAIRE}")],
            [InlineKeyboardButton("❌ Annuler", callback_data="form_cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "💎 <b>Demande prioritaire ?</b>\n\n"
            "Les demandes prioritaires nécessitent un montant et sont traitées en premier.",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        return self.PRIORITAIRE

    async def handle_priority_choice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Gère le choix prioritaire/standard"""
        query = update.callback_query
        await query.answer()
        data = query.data

        if data == "priorite_oui":
            await query.edit_message_text(
                "💰 <b>Demande prioritaire</b>\n\n"
                "Veuillez indiquer le montant (en euros) :",
                parse_mode='HTML',
                reply_markup=self.navigation.create_navigation_keyboard(self.MONTANT)
            )
            return self.MONTANT
        else:
            # Standard
            context.user_data['demande']['prioritaire'] = False
            context.user_data['demande']['montant'] = 0

            await self.save_demande(update, context)
            return ConversationHandler.END

    async def montant(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Traite la saisie du montant avec validation centralisée"""
        user_input = Validators.clean_input(update.message.text)

        try:
            validated_montant = Validators.validate_amount(user_input)
            context.user_data['demande']['montant'] = validated_montant
            context.user_data['demande']['prioritaire'] = True

            await update.message.reply_text(
                f"✅ Montant enregistré : <b>{validated_montant}€</b>\n\n"
                "Récapitulatif de votre demande :"
            )

            # Finaliser la demande
            await self.save_demande(update, context)
            return ConversationHandler.END

        except ValidationError as e:
            await update.message.reply_text(
                f"❌ {str(e)}\n\n"
                f"{Validators.get_validation_help('montant')}\n\n"
                "Veuillez ressaisir le montant :",
                parse_mode='HTML',
                reply_markup=self.navigation.create_navigation_keyboard(self.MONTANT)
            )
            return self.MONTANT

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Annulation formulaire selon [source 1]"""
        context.user_data.clear()
        await update.message.reply_text(
            "❌ Création de demande annulée.\n"
            "Tapez /start pour revenir au menu principal."
        )
        return ConversationHandler.END

    async def save_demande(self, update, context):
        """Finalise et sauvegarde la demande"""
        try:
            demande = context.user_data.get('demande', {})
            user_id = update.effective_user.id

            with self.db_manager.get_cursor() as cursor:
                # Calculer le prochain request_number pour cet utilisateur
                cursor.execute("""
                    SELECT COALESCE(MAX(request_number), 0) + 1 as next_numero
                    FROM demandes WHERE user_id = %s
                """, (user_id,))

                next_numero = cursor.fetchone()['next_numero']

                cursor.execute("""
                    INSERT INTO demandes (
                        user_id, prenom, nom, age, localisation, photo_id,
                        instagram, snapchat, details, prioritaire, montant, statut, request_number
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    user_id, demande['prenom'], demande.get('nom'),
                    demande['age'], demande['localisation'], demande.get('photo_id'),
                    demande.get('instagram'), demande.get('snapchat'), demande.get('details'),
                    demande.get('prioritaire', False), demande.get('montant', 0),
                    "📨 Reçue", next_numero
                ))

                demande_id = cursor.lastrowid

            # Vider les données temporaires
            context.user_data.pop('demande', None)

            logger.info(f"Demande créée - ID: {demande_id}, User: {user_id}, Numero: {next_numero}")

            # Message de confirmation
            type_demande = "💎 Prioritaire" if demande.get('prioritaire') else "📝 Standard"
            montant_text = f" - {demande.get('montant', 0):.2f}€" if demande.get('prioritaire') else ""

            message = (
                f"✅ <b>Demande n°{next_numero} créée avec succès !</b>\n\n"
                f"👤 <b>Nom :</b> {demande['prenom']}"
            )

            if demande.get('nom'):
                message += f" {demande['nom']}"

            message += (
                f"\n🎂 <b>Âge :</b> {demande['age']} ans\n"
                f"📍 <b>Localisation :</b> {demande['localisation']}\n"
                f"🎯 <b>Type :</b> {type_demande}{montant_text}\n\n"
                f"La demande sera traitée dans les meilleurs délais.\n"
                f"Tapez /demandes pour voir vos demandes."
            )
            if update.callback_query:
                await update.callback_query.edit_message_text(message, parse_mode='HTML')
            else:
                await update.message.reply_text(message, parse_mode='HTML')

        except Exception as e:
            logger.error(f"Erreur finalisation demande: {e}")
            error_msg = "❌ Erreur lors de la sauvegarde"
            if update.callback_query:
                await update.callback_query.edit_message_text(error_msg)
            else:
                await update.message.reply_text(error_msg)
