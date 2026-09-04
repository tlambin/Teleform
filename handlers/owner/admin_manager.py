"""Gestion des administrateurs selon architecture modulaire"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

class AdminManager:
    """Gestionnaire administrateurs - Module Owner"""

    def __init__(self, db_manager, config):
        """Initialisation AdminManager"""
        self.db_manager = db_manager
        self.config = config

        logger.info("AdminManager initialisé - Architecture modulaire")

    async def add_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Ajoute un nouvel admin (propriétaire uniquement)"""
        user_id = update.effective_user.id

        if not self.config.is_owner(user_id):
            await update.message.reply_text("❌ Seul le propriétaire peut gérer les admins.")
            return

        # Exiger 2 arguments
        if not context.args or len(context.args) < 2:
            await update.message.reply_text(
                "❓ <b>Usage :</b> <code>/addadmin [user_id] [alias]</code>\n\n"
                "<b>Exemple :</b> <code>/addadmin 123456789 name</code>\n\n"
                f"⚠️ <b>L'alias est obligatoire</b> et doit être unique.\n\n"
                f"{Validators.get_alias_rules()}",
                parse_mode='HTML'
            )
            return

        try:
            new_admin_id = Validators.validate_user_id(context.args[0])
            alias = Validators.clean_input(context.args[1])
        except ValidationError as e:
            await update.message.reply_text(f"❌ {str(e)}")
            return

        # Validation de l'alias
        is_valid, error_message = Validators.validate_alias(alias)
        if not is_valid:
            await update.message.reply_text(
                f"❌ <b>Alias invalide :</b> {error_message}\n\n"
                f"{Validators.get_alias_rules()}",
                parse_mode='HTML'
            )
            return

        # Vérifier qu'il n'est pas déjà admin
        if self.config.is_admin(new_admin_id):
            await update.message.reply_text(f"⚠️ L'utilisateur {new_admin_id} est déjà admin.")
            return

        try:
            with self.db_manager.get_cursor() as cursor:
                # Vérifier que l'utilisateur existe
                cursor.execute("SELECT first_name FROM users WHERE user_id = %s", (new_admin_id,))
                user_info = cursor.fetchone()

                if not user_info:
                    await update.message.reply_text(f"❌ L'utilisateur {new_admin_id} n'a jamais utilisé le bot.")
                    return

                # NOUVEAU : Vérifier l'unicité de l'alias
                cursor.execute("SELECT user_id FROM admins WHERE alias = %s", (alias,))
                if cursor.fetchone():
                    await update.message.reply_text(f"❌ L'alias '{alias}' est déjà utilisé par un autre admin.")
                    return

                # Ajouter l'admin
                cursor.execute("""
                    INSERT INTO admins (user_id, username, first_name, alias, added_by)
                    SELECT user_id, username, first_name, %s, %s
                    FROM users WHERE user_id = %s
                """, (alias, user_id, new_admin_id))

                # Mettre à jour la config en mémoire
                self.config.load_admins(self.db_manager)

                if self.config.is_admin(new_admin_id):
                    await update.message.reply_text(
                        f"✅ <b>Admin ajouté et vérifié !</b>\n\n"
                        f"👤 {user_info['first_name']} (ID: {new_admin_id})\n"
                        f"🏷️ <b>Alias :</b> {alias}\n"
                        f"🎯 Peut maintenant s'occuper des demandes",
                        parse_mode='HTML'
                    )
                else:
                    await update.message.reply_text(
                        f"⚠️ Admin ajouté en base mais cache non synchronisé\n"
                        f"Un redémarrage du bot peut être nécessaire.",
                        parse_mode='HTML'
                    )

        except Exception as e:
            logger.error(f"Erreur ajout admin: {e}")
            await update.message.reply_text("❌ Erreur lors de l'ajout de l'admin.")

    async def remove_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Supprime un admin (propriétaire uniquement)"""
        user_id = update.effective_user.id

        if not self.config.is_owner(user_id):
            await update.message.reply_text("❌ Seul le propriétaire peut gérer les admins.")
            return

        if len(context.args) != 1:
            await update.message.reply_text(
                "❓ <b>Usage :</b> <code>/removeadmin <user_id></code>\n\n"
                "Exemple : <code>/removeadmin 123456789</code>",
                parse_mode='HTML'
            )
            return

        try:
            admin_id = int(context.args[0])

            # Empêcher de supprimer le propriétaire
            if self.config.is_owner(admin_id):
                await update.message.reply_text("❌ Impossible de supprimer le propriétaire du bot.")
                return

            with self.db_manager.get_cursor() as cursor:
                # Vérifier que c'est un admin
                cursor.execute("""
                    SELECT u.first_name
                    FROM admins a
                    JOIN users u ON a.user_id = u.user_id
                    WHERE a.user_id = %s
                """, (admin_id,))
                admin_info = cursor.fetchone()

                if not admin_info:
                    await update.message.reply_text(f"❌ L'utilisateur {admin_id} n'est pas admin.")
                    return

                # Supprimer l'admin
                cursor.execute("DELETE FROM admins WHERE user_id = %s", (admin_id,))

                # Mettre à jour la config en mémoire
                self.config.load_admins(self.db_manager)

                if not self.config.is_admin(admin_id):
                    await update.message.reply_text(
                        f"✅ <b>Admin supprimé avec succès !</b>\n\n"
                        f"👤 {admin_info['first_name']} (ID: {admin_id})\n"
                        f"❌ N'a plus accès aux commandes admin",
                        parse_mode='HTML'
                    )
                else:
                    await update.message.reply_text(
                        f"⚠️ Admin supprimé de la base mais encore en cache\n"
                        f"Un redémarrage du bot peut être nécessaire.",
                        parse_mode='HTML'
                    )

        except ValueError:
            await update.message.reply_text("❌ L'ID utilisateur doit être un nombre.")
        except Exception as e:
            logger.error(f"Erreur suppression admin: {e}")
            await update.message.reply_text("❌ Erreur lors de la suppression de l'admin.")

    async def list_admins(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Liste tous les admins (propriétaire uniquement)"""
        user_id = update.effective_user.id

        if not self.config.is_owner(user_id):
            await update.message.reply_text("❌ Seul le propriétaire peut voir la liste des admins.")
            return

        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute("""
                    SELECT a.user_id, u.first_name, u.username, a.alias, a.date_added,
                           (SELECT first_name FROM users WHERE user_id = a.added_by) as added_by_name
                    FROM admins a
                    JOIN users u ON a.user_id = u.user_id
                    ORDER BY a.date_added
                """)

                admins = cursor.fetchall()

                if not admins:
                    await update.message.reply_text(
                        "📭 <b>Aucun admin configuré</b>\n\n"
                        f"👑 Seul le propriétaire (ID: <code>{self.config.OWNER_ID}</code>) a accès à ces commandes",
                        parse_mode='HTML'
                    )
                    return

                message = f"👥 <b>Liste des admins</b> ({len(admins)})\n\n"

                for admin in admins:
                    username = f"@{admin['username']}" if admin['username'] else "Pas de username"
                    date_added_paris = convert_utc_to_paris(admin['date_added'])
                    date_str = date_added_paris.strftime('%d/%m/%Y %H:%M')

                    message += f"👤 <b>{admin['first_name']}</b> - <b>{admin['alias']}</b>\n"
                    message += f"📱 {username}\n"
                    message += f"🆔 ID: <code>{admin['user_id']}</code>\n"
                    message += f"📅 Ajouté le: {date_str}\n"
                    message += f"👤 Par: {admin['added_by_name']}\n\n"

                message += f"👑 <b>Propriétaire :</b> ID <code>{self.config.OWNER_ID}</code> (accès permanent)"

                await update.message.reply_text(message, parse_mode='HTML')

        except Exception as e:
            logger.error(f"Erreur liste admins: {e}")
            await update.message.reply_text("❌ Erreur lors de la récupération des admins.")

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