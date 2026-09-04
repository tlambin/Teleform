import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from utils.maintenance import daily_maintenance, check_storage_usage
from utils.interface_manager import InterfaceManager

logger = logging.getLogger(__name__)

class OwnerHandlers:
    def __init__(self, config, db_manager):
        self.config = config
        self.db_manager = db_manager
        self.interface = InterfaceManager(config, db_manager)
        self.WAITING_ADMIN_ID = "waiting_admin_id"
        self.WAITING_ADMIN_REMOVE = "waiting_admin_remove"
        self.WAITING_CONFIRMATION = "waiting_confirmation"

    async def run_maintenance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Lance une maintenance manuelle - Compatible CallbackQuery et Message"""
        user_id = update.effective_user.id

        if not self.config.is_owner(user_id):
            # ✅ Gestion hybride selon type d'update
            if update.callback_query:
                await update.callback_query.answer("❌ Accès non autorisé", show_alert=True)
            else:
                await update.message.reply_text("❌ Accès non autorisé")
            return

        try:
            # ✅ Message initial selon type d'update
            if update.callback_query:
                await update.callback_query.edit_message_text("🔧 Maintenance en cours...")
            else:
                await update.message.reply_text("🔧 Maintenance en cours...")

            # ✅ VOTRE LOGIQUE MAINTENANCE EXACTE (inchangée)
            storage_before = check_storage_usage()
            daily_maintenance(self.db_manager)
            storage_after = check_storage_usage()

            # Statistiques de la maintenance (votre code exact)
            with self.db_manager.get_cursor() as cursor:
                cursor.execute("SELECT COUNT(*) as count FROM demandes")
                demandes_count = cursor.fetchone()['count']

                cursor.execute("SELECT COUNT(*) as count FROM archives")
                archives_count = cursor.fetchone()['count']

            message = (
                "✅ <b>Maintenance terminée</b>\n\n"
                f"💾 <b>Stockage:</b>\n"
                f"• Avant: {storage_before:.1f} MB\n"
                f"• Après: {storage_after:.1f} MB\n"
                f"• Économisé: {storage_before - storage_after:.1f} MB\n\n"
                f"📊 <b>Base de données:</b>\n"
                f"• Demandes actives: {demandes_count}\n"
                f"• Archives: {archives_count}\n\n"
                f"🧹 Cache vidé et fichiers temporaires nettoyés"
            )

            # ✅ Résultat final selon type d'update
            if update.callback_query:
                # Pour bouton : ajouter bouton retour
                keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Retour", callback_data="gerer_bot")
                ]])
                await update.callback_query.edit_message_text(
                    message,
                    parse_mode='HTML',
                    reply_markup=keyboard
                )
            else:
                # Pour commande : message simple
                await update.message.reply_text(message, parse_mode='HTML')

        except Exception as e:
            logger.error(f"Erreur maintenance manuelle: {e}")

            # ✅ Gestion d'erreur selon type d'update
            if update.callback_query:
                await update.callback_query.answer("❌ Erreur lors de la maintenance", show_alert=True)
            else:
                await update.message.reply_text("❌ Erreur lors de la maintenance")

    async def toggle_bot_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Active/désactive l'acceptation de nouvelles demandes"""
        user_id = update.effective_user.id

        if not self.config.is_owner(user_id):
            await update.message.reply_text("❌ Accès non autorisé")
            return

        try:
            # ✅ UTILISER nouvelle architecture config unifiée
            current_status = self.db_manager.is_bot_active()
            new_status = not current_status

            # Mettre à jour via nouvelle méthode
            self.db_manager.set_bot_active(new_status)

            status_text = "✅ ACTIVÉES" if new_status else "❌ DÉSACTIVÉES"
            await update.message.reply_text(
                f"🔧 <b>Nouvelles demandes {status_text}</b>\n\n"
                f"Statut précédent : {'Activées' if current_status else 'Désactivées'}\n"
                f"Nouveau statut : {'Activées' if new_status else 'Désactivées'}",
                parse_mode='HTML'
            )

        except Exception as e:
            logger.error(f"Erreur toggle statut: {e}")
            await update.message.reply_text("❌ Erreur lors du changement de statut")

    async def bot_on(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Active les demandes"""
        query = update.callback_query
        user_id = query.from_user.id

        await query.answer()

        if not self.config.is_owner(user_id):
            await query.answer("❌ Accès propriétaire requis", show_alert=True)
            return

        try:
            self.db_manager.set_bot_active(True)
            await query.answer("✅ Demandes activées !", show_alert=True)

            message, keyboard = self.interface.get_gerer_bot_menu()
            await query.edit_message_text(message, parse_mode='HTML', reply_markup=keyboard)

        except Exception as e:
            logger.error(f"Erreur activation: {e}")
            await query.answer("❌ Erreur", show_alert=True)

    async def bot_off(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Interface désactivation avec confirmation"""
        query = update.callback_query
        user_id = query.from_user.id

        await query.answer()

        if not self.config.is_owner(user_id):
            await query.answer("❌ Accès propriétaire requis", show_alert=True)
            return

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("⚠️ CONFIRMER", callback_data="confirm_bot_off"),
                InlineKeyboardButton("❌ Annuler", callback_data="cancel_bot_off")
            ]
        ])

        await query.edit_message_text(
            "⚠️ <b>DÉSACTIVATION DES DEMANDES</b>\n\n"
            "Confirmer la désactivation ?",
            parse_mode='HTML',
            reply_markup=keyboard
        )

    async def confirmer_bot_off(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Confirme la désactivation"""
        query = update.callback_query
        await query.answer()

        try:
            self.db_manager.set_bot_active(False)
            await query.answer("🔴 Demandes désactivées !", show_alert=True)

            message, keyboard = self.interface.get_gerer_bot_menu()
            await query.edit_message_text(message, parse_mode='HTML', reply_markup=keyboard)

        except Exception as e:
            logger.error(f"Erreur désactivation: {e}")

    async def cancel_bot_off(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Annule la désactivation"""
        query = update.callback_query
        await query.answer()

        message, keyboard = self.interface.get_gerer_bot_menu()
        await query.edit_message_text(message, parse_mode='HTML', reply_markup=keyboard)

    async def toggle_demandes(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Activer/désactiver les demandes"""
        user_id = update.effective_user.id

        if user_id != self.config.OWNER_ID:
            await update.message.reply_text("❌ Accès refusé")
            return

        current_state = self.config.are_demandes_enabled()

        if current_state:
            self.config.disable_demandes()
            await update.message.reply_text(
                "🚫 **Demandes désactivées**\n\n"
                "Les utilisateurs ne peuvent plus créer de nouvelles demandes."
            )
        else:
            self.config.enable_demandes()
            await update.message.reply_text(
                "✅ **Demandes réactivées**\n\n"
                "Les utilisateurs peuvent à nouveau créer des demandes."
            )


    async def handle_owner_callbacks(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Gestionnaire callbacks owner"""
        query = update.callback_query
        user_id = query.from_user.id

        if not self.config.is_owner(user_id):
            await query.answer("❌ Accès propriétaire requis", show_alert=True)
            return

        if query.data == "bot_on":
            await self.bot_on(update, context)
        elif query.data == "bot_off":
            await self.bot_off(update, context)
        elif query.data == "confirm_bot_off":
            await self.confirmer_bot_off(update, context)
        elif query.data == "cancel_bot_off":
            await self.cancel_bot_off(update, context)
        elif query.data == "maintenance":
            await self.run_maintenance(update, context)
        elif query.data == "bot_stats":
            await self.show_statistics(update, context)
        else:
            await query.answer("❌ Action non reconnue")
            logger.warning(f"Callback owner non géré : {query.data}")

    async def admin_ajouter(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Interface ajout administrateur - Owner uniquement"""
        query = update.callback_query
        user_id = query.from_user.id

        await query.answer()

        # Vérification permissions propriétaire selon vos intérêts en contrôle d'accès
        if not self.config.is_owner(user_id):
            await query.answer("❌ Accès propriétaire requis", show_alert=True)
            return ConversationHandler.END

        try:
            # Comptage admins actuels selon le code fourni
            with self.db_manager.get_cursor() as cursor:
                cursor.execute("SELECT COUNT(*) as count FROM admins")
                admin_count = cursor.fetchone()['count']

            await query.edit_message_text(
                f"👤 <b>Ajout d'un Administrateur</b>\n\n"
                f"📊 Admins actuels : {admin_count}\n\n"
                f"Veuillez saisir :\n"
                f"• <b>ID Telegram</b> (exemple: 123456789)\n"
                f"• <b>Username</b> (exemple: johndoe)\n\n"
                f"⚠️ L'utilisateur doit avoir déjà interagi avec le bot.",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("❌ Annuler", callback_data="cancel_admin_add")
                ]])
            )

            return self.WAITING_ADMIN_ID

        except Exception as e:
            logger.error(f"Erreur ouverture ajout admin pour {user_id}: {e}")
            await query.edit_message_text(
                "❌ Erreur lors de l'ouverture de l'ajout d'administrateur",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Retour", callback_data="gerer_admins")
                ]])
            )
            return ConversationHandler.END

    async def traiter_admin_ajouter(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Traite la saisie pour ajouter un admin selon vos intérêts en administration système"""
        user_id = update.effective_user.id
        saisie = update.message.text.strip()

        # Double vérification propriétaire
        if not self.config.is_owner(user_id):
            await update.message.reply_text("❌ Accès propriétaire requis")
            return ConversationHandler.END

        try:
            # Validation entrée selon le code fourni
            if not saisie:
                await update.message.reply_text(
                    "❌ <b>Entrée invalide</b>\n\n"
                    "Veuillez saisir un ID Telegram ou username valide :",
                    parse_mode='HTML'
                )
                return self.WAITING_ADMIN_ID

            # Déterminer si c'est un ID ou username selon vos intérêts en contrôle d'accès
            if saisie.isdigit():
                # ID Telegram numérique
                target_user_id = int(saisie)
                search_by = "user_id"
            else:
                # Username (sans @)
                target_user_id = saisie.lower()
                search_by = "username"

            # Vérifier si déjà admin selon le code fourni adapté
            with self.db_manager.get_cursor() as cursor:
                if search_by == "user_id":
                    cursor.execute("SELECT user_id, alias FROM admins WHERE user_id = %s", (target_user_id,))
                else:
                    cursor.execute("SELECT user_id, alias FROM admins WHERE username = %s", (target_user_id,))

                existing_admin = cursor.fetchone()
                if existing_admin:
                    await update.message.reply_text(
                        f"❌ <b>Déjà administrateur</b>\n\n"
                        f"Cet utilisateur est déjà admin avec l'alias : <b>{existing_admin['alias']}</b>\n\n"
                        f"Veuillez saisir un autre utilisateur :",
                        parse_mode='HTML'
                    )
                    return self.WAITING_ADMIN_ID

            # Vérifier si utilisateur existe dans le système selon vos intérêts en administration système
            with self.db_manager.get_cursor() as cursor:
                if search_by == "user_id":
                    cursor.execute("SELECT user_id, username, first_name FROM users WHERE user_id = %s", (target_user_id,))
                else:
                    cursor.execute("SELECT user_id, username, first_name FROM users WHERE username = %s", (target_user_id,))

                user_data = cursor.fetchone()
                if not user_data:
                    await update.message.reply_text(
                        f"❌ <b>Utilisateur introuvable</b>\n\n"
                        f"L'utilisateur <code>{saisie}</code> n'a jamais interagi avec le bot.\n\n"
                        f"Il doit d'abord utiliser /start puis vous pourrez l'ajouter.\n\n"
                        f"Veuillez saisir un autre utilisateur :",
                        parse_mode='HTML'
                    )
                    return self.WAITING_ADMIN_ID

            # Génération alias automatique selon vos intérêts en personnalisation admin
            base_alias = user_data['first_name'] or user_data['username'] or f"Admin{user_data['user_id']}"
            alias = base_alias[:15]  # Limiter longueur

            # Vérification unicité alias
            with self.db_manager.get_cursor() as cursor:
                counter = 1
                original_alias = alias
                while True:
                    cursor.execute("SELECT user_id FROM admins WHERE alias = %s", (alias,))
                    if not cursor.fetchone():
                        break
                    alias = f"{original_alias}{counter}"
                    counter += 1

            # Ajout en base selon le code fourni amélioré
            with self.db_manager.get_cursor() as cursor:
                cursor.execute("""
                    INSERT INTO admins (user_id, alias, first_name, username, date_added, added_by)
                    VALUES (%s, %s, %s, %s, NOW(), %s)
                """, (
                    user_data['user_id'],
                    alias,
                    user_data['first_name'] or '',
                    user_data['username'] or '',
                    user_id
                ))

            # Recharger configuration selon vos intérêts en administration système
            self.config.load_admins(self.db_manager)

            # Message succès avec retour navigation selon vos intérêts en conception interface admin
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("👥 Gestion Admins", callback_data="gerer_admins")],
                [InlineKeyboardButton("🏠 Menu Principal", callback_data="start_menu")]
            ])

            await update.message.reply_text(
                f"✅ <b>Administrateur ajouté avec succès !</b>\n\n"
                f"👤 Utilisateur : {user_data['first_name'] or user_data['username']}\n"
                f"🆔 ID : <code>{user_data['user_id']}</code>\n"
                f"🏷️ Alias : <b>{alias}</b>\n\n"
                f"L'utilisateur peut maintenant utiliser les fonctions d'administration.",
                parse_mode='HTML',
                reply_markup=keyboard
            )

            logger.info(f"Admin ajouté par {user_id}: {user_data['user_id']} avec alias {alias}")
            return ConversationHandler.END

        except Exception as e:
            logger.error(f"Erreur ajout admin par {user_id}: {e}")
            await update.message.reply_text(
                "❌ Erreur lors de l'ajout de l'administrateur",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")
                ]])
            )
            return ConversationHandler.END

    async def cancel_admin_add(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Annulation ajout administrateur"""
        query = update.callback_query
        await query.answer()

        # Retour menu gestion admins selon vos intérêts en conception interface admin
        message, keyboard = self.interface.get_gerer_admins_menu()

        await query.edit_message_text(
            message,
            parse_mode='HTML',
            reply_markup=keyboard
        )

        return ConversationHandler.END

    # Constante pour ConversationHandler
    WAITING_ADMIN_ID = "waiting_admin_id"

    async def admin_supprimer(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Interface suppression administrateur avec liste - Owner uniquement"""
        query = update.callback_query
        user_id = query.from_user.id

        await query.answer()

        # Vérification permissions propriétaire selon vos intérêts en contrôle d'accès
        if not self.config.is_owner(user_id):
            await query.answer("❌ Accès propriétaire requis", show_alert=True)
            return ConversationHandler.END

        try:
            # Récupération liste admins selon les résultats fournis
            with self.db_manager.get_cursor() as cursor:
                cursor.execute("""
                    SELECT user_id, alias, first_name, username, date_added
                    FROM admins
                    WHERE user_id != %s
                    ORDER BY date_added DESC
                """, (user_id,))  # Exclure le propriétaire lui-même

                admins = cursor.fetchall()

            if not admins:
                await query.edit_message_text(
                    "👥 <b>Suppression d'Administrateur</b>\n\n"
                    "📭 Aucun administrateur à supprimer.\n"
                    "Vous êtes le seul administrateur du système.",
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 Retour", callback_data="gerer_admins")
                    ]])
                )
                return ConversationHandler.END

            # Construction du message avec liste d'admins selon vos intérêts en gestion des utilisateurs
            message = f"👥 <b>Suppression d'Administrateur</b>\n\n"
            message += f"📊 Administrateurs supprimables : {len(admins)}\n\n"
            message += "⚠️ <b>ATTENTION :</b> Cette action est irréversible !\n\n"

            for i, admin in enumerate(admins, 1):
                username_info = f"@{admin['username']}" if admin['username'] else admin['first_name']
                date_str = admin['date_added'].strftime('%d/%m/%Y')
                message += f"{i}. <b>{admin['alias']}</b> - {username_info}\n"
                message += f"   📅 Ajouté le {date_str} - ID: <code>{admin['user_id']}</code>\n\n"

            message += "Saisissez le <b>numéro</b> de l'admin à supprimer :"

            # Stocker la liste des admins pour la sélection
            context.user_data['admins_list'] = admins

            await query.edit_message_text(
                message,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("❌ Annuler", callback_data="cancel_admin_remove")
                ]])
            )

            return self.WAITING_ADMIN_REMOVE

        except Exception as e:
            logger.error(f"Erreur ouverture suppression admin pour {user_id}: {e}")
            await query.edit_message_text(
                "❌ Erreur lors de l'ouverture de la suppression d'administrateur",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Retour", callback_data="gerer_admins")
                ]])
            )
            return ConversationHandler.END

    async def traiter_admin_supprimer(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Traite la sélection d'admin à supprimer selon les bonnes pratiques"""
        user_id = update.effective_user.id
        choix = update.message.text.strip()

        # Double vérification propriétaire selon vos intérêts en contrôle d'accès
        if not self.config.is_owner(user_id):
            await update.message.reply_text("❌ Accès propriétaire requis")
            return ConversationHandler.END

        try:
            # Validation choix numérique
            if not choix.isdigit():
                await update.message.reply_text(
                    "❌ <b>Choix invalide</b>\n\n"
                    "Veuillez saisir un numéro valide de la liste :",
                    parse_mode='HTML'
                )
                return self.WAITING_ADMIN_REMOVE

            choix_num = int(choix)
            admins_list = context.user_data.get('admins_list', [])

            if choix_num < 1 or choix_num > len(admins_list):
                await update.message.reply_text(
                    f"❌ <b>Numéro invalide</b>\n\n"
                    f"Veuillez choisir entre 1 et {len(admins_list)} :",
                    parse_mode='HTML'
                )
                return self.WAITING_ADMIN_REMOVE

            # Récupérer l'admin sélectionné selon les résultats fournis
            admin_selected = admins_list[choix_num - 1]

            # Protection supplémentaire selon vos intérêts en contrôle d'accès
            if admin_selected['user_id'] == user_id:
                await update.message.reply_text(
                    "❌ <b>Auto-suppression interdite</b>\n\n"
                    "Vous ne pouvez pas vous supprimer vous-même.\n"
                    "Veuillez choisir un autre administrateur :",
                    parse_mode='HTML'
                )
                return self.WAITING_ADMIN_REMOVE

            # Stocker admin à supprimer pour confirmation
            context.user_data['admin_to_remove'] = admin_selected

            # Demande de confirmation selon les bonnes pratiques
            username_info = f"@{admin_selected['username']}" if admin_selected['username'] else admin_selected['first_name']

            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("⚠️ CONFIRMER SUPPRESSION", callback_data="confirm_admin_remove"),
                    InlineKeyboardButton("❌ Annuler", callback_data="cancel_admin_remove")
                ]
            ])

            await update.message.reply_text(
                f"⚠️ <b>CONFIRMATION SUPPRESSION</b>\n\n"
                f"Êtes-vous sûr de vouloir supprimer :\n\n"
                f"👤 <b>{admin_selected['alias']}</b>\n"
                f"📱 {username_info}\n"
                f"🆔 ID: <code>{admin_selected['user_id']}</code>\n\n"
                f"⚠️ <b>Cette action est IRRÉVERSIBLE !</b>",
                parse_mode='HTML',
                reply_markup=keyboard
            )

            return self.WAITING_CONFIRMATION

        except Exception as e:
            logger.error(f"Erreur traitement suppression admin par {user_id}: {e}")
            await update.message.reply_text(
                "❌ Erreur lors du traitement de la suppression",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")
                ]])
            )
            return ConversationHandler.END

    async def confirmer_admin_suppression(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Exécute la suppression après confirmation selon vos intérêts en administration système"""
        query = update.callback_query
        user_id = query.from_user.id

        await query.answer()

        # Triple vérification propriétaire
        if not self.config.is_owner(user_id):
            await query.answer("❌ Accès propriétaire requis", show_alert=True)
            return ConversationHandler.END

        try:
            admin_to_remove = context.user_data.get('admin_to_remove')
            if not admin_to_remove:
                await query.edit_message_text("❌ Erreur : administrateur non sélectionné")
                return ConversationHandler.END

            # Suppression de la base selon les résultats fournis
            with self.db_manager.get_cursor() as cursor:
                cursor.execute("DELETE FROM admins WHERE user_id = %s", (admin_to_remove['user_id'],))
                rows_affected = cursor.rowcount

            if rows_affected == 0:
                await query.edit_message_text(
                    "❌ <b>Échec de suppression</b>\n\n"
                    "L'administrateur n'a pas pu être supprimé.",
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 Gestion Admins", callback_data="gerer_admins")
                    ]])
                )
                return ConversationHandler.END

            # Recharger configuration selon vos intérêts en administration système
            self.config.load_admins(self.db_manager)

            # Message succès selon vos intérêts en gestion des utilisateurs
            username_info = f"@{admin_to_remove['username']}" if admin_to_remove['username'] else admin_to_remove['first_name']

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("👥 Gestion Admins", callback_data="gerer_admins")],
                [InlineKeyboardButton("🏠 Menu Principal", callback_data="start_menu")]
            ])

            await query.edit_message_text(
                f"✅ <b>Administrateur supprimé avec succès !</b>\n\n"
                f"👤 <b>{admin_to_remove['alias']}</b>\n"
                f"📱 {username_info}\n"
                f"🆔 ID: <code>{admin_to_remove['user_id']}</code>\n\n"
                f"L'utilisateur n'a plus accès aux fonctions d'administration.",
                parse_mode='HTML',
                reply_markup=keyboard
            )

            # Nettoyage données temporaires
            context.user_data.pop('admins_list', None)
            context.user_data.pop('admin_to_remove', None)

            logger.info(f"Admin supprimé par {user_id}: {admin_to_remove['user_id']} ({admin_to_remove['alias']})")
            return ConversationHandler.END

        except Exception as e:
            logger.error(f"Erreur confirmation suppression admin par {user_id}: {e}")
            await query.edit_message_text(
                "❌ Erreur lors de la suppression de l'administrateur",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")
                ]])
            )
            return ConversationHandler.END

    async def cancel_admin_remove(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Annulation suppression administrateur"""
        query = update.callback_query
        await query.answer()

        # Nettoyage données temporaires
        context.user_data.pop('admins_list', None)
        context.user_data.pop('admin_to_remove', None)

        # Retour menu gestion admins selon vos intérêts en gestion des utilisateurs
        message, keyboard = self.interface.get_gerer_admins_menu()

        await query.edit_message_text(
            message,
            parse_mode='HTML',
            reply_markup=keyboard
        )

        return ConversationHandler.END

    # Constantes pour ConversationHandler
    WAITING_ADMIN_REMOVE = "waiting_admin_remove"
    WAITING_CONFIRMATION = "waiting_confirmation"

    async def show_statistics(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Affiche les statistiques du bot"""
        try:
            with self.db_manager.get_cursor() as cursor:
                # Statistiques générales
                stats_queries = {
                    'total_demandes': "SELECT COUNT(*) as count FROM demandes",
                    'total_archives': "SELECT COUNT(*) as count FROM archives",
                    'total_users': "SELECT COUNT(*) as count FROM users",
                    'demandes_prioritaires': "SELECT COUNT(*) as count FROM demandes WHERE prioritaire = TRUE",
                    'montant_total': "SELECT SUM(montant) as total FROM demandes WHERE prioritaire = TRUE"
                }

                stats = {}
                for key, query in stats_queries.items():
                    cursor.execute(query)
                    result = cursor.fetchone()
                    stats[key] = result['count'] if 'count' in result else result['total'] or 0

                # Statistiques par statut
                cursor.execute("""
                    SELECT statut, COUNT(*) as count
                    FROM demandes
                    GROUP BY statut
                    ORDER BY count DESC
                """)
                statuts_stats = cursor.fetchall()

                # Récupérer la taille de la db
                db_stats = self.db_manager.get_database_size()

                # Vérifier l'usage du stockage
                storage_usage = check_storage_usage()

                message = (
                    "📈 <b>Statistiques du bot</b>\n\n"
                    f"👥 <b>Utilisateurs:</b> {stats['total_users']}\n"
                    f"📝 <b>Demandes actives:</b> {stats['total_demandes']}\n"
                    f"📦 <b>Archives:</b> {stats['total_archives']}\n"
                    f"💎 <b>Prioritaires:</b> {stats['demandes_prioritaires']}\n"
                    f"💰 <b>Montant total:</b> {stats['montant_total']:.2f}€\n\n"
                    "📊 <b>Répartition par statut:</b>\n"
                )

                for statut_stat in statuts_stats:
                    message += f"• {statut_stat['statut']}: {statut_stat['count']}\n"

                message += (
                    f"\n💾 <b>Stockage:</b> {storage_usage:.1f} MB / 512 MB\n"
                    f"📊 <b>Usage:</b> {(storage_usage/512)*100:.1f}%"
                )

                message += (
                    f"\n💾 <b>Base de données :</b> {db_stats['total_size_mb']} MB"
                )
                tables_info = db_stats.get('tables', [])
                if tables_info and isinstance(tables_info, list):
                    message += "\n📋 Détail par table :\n"
                    for table in tables_info:
                        if isinstance(table, dict) and 'TABLE_NAME' in table:
                            table_name = table.get('TABLE_NAME', 'Unknown')
                            size_mb = float(table.get('size_mb', 0))
                            row_count = table.get('row_count', 0)
                            message += f" • {table_name} : {size_mb} MB ({row_count} lignes)\n"
                else:
                    message += "\n📋 Aucune information de table disponible\n"

                # (Optionnel) Alerte si proche de la limite PythonAnywhere
                if db_stats['total_size_mb'] > 400:
                    message += f"\n⚠️ <b>Attention :</b> Proche de la limite 512 MB"
                elif db_stats['total_size_mb'] > 300:
                    message += f"\n🟡 <b>Info :</b> {(db_stats['total_size_mb']/512*100):.1f}% de la limite"

                keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Retour Paramètres", callback_data="parametres")
                ]])

                await update.callback_query.edit_message_text(
                    message,
                    parse_mode='HTML',
                    reply_markup=keyboard
                )

        except Exception as e:
            logger.error(f"Erreur statistiques: {e}")
            await update.callback_query.edit_message_text("❌ Erreur lors de la récupération des statistiques")

