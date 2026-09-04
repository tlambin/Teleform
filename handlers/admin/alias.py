# handlers/admin/alias.py
"""Système d'alias avec génération automatique et unicité selon [source 2]"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

logger = logging.getLogger(__name__)

class AliasManager:
    """Gestionnaire d'alias avec alias par défaut et unicité selon [source 2]"""

    def __init__(self, db_manager, config):
        self.db_manager = db_manager
        self.config = config

        # États conversation
        self.WAITING_ALIAS = "waiting_alias"

        # Alias par défaut
        self.DEFAULT_OWNER_ALIAS = "Propriétaire"
        self.DEFAULT_ADMIN_PREFIX = "Baiter"

    async def get_admin_alias(self, admin_user_id: int) -> str:
        """Récupère l'alias d'un admin avec génération automatique selon [source 2]"""
        try:
            if self.config.is_owner(admin_user_id):
                # Owner : alias depuis config
                return self.db_manager.get_config_value('owner_alias', self.DEFAULT_OWNER_ALIAS)
            else:
                # Admin : alias depuis table admins avec génération auto
                with self.db_manager.get_cursor() as cursor:
                    cursor.execute("SELECT alias FROM admins WHERE user_id = %s", (admin_user_id,))
                    result = cursor.fetchone()

                    if result and result['alias']:
                        return result['alias']
                    else:
                        # Générer alias par défaut selon ordre d'ajout
                        alias_auto = await self._generate_default_admin_alias(admin_user_id)
                        await self._save_admin_alias(admin_user_id, alias_auto)
                        return alias_auto

        except Exception as e:
            logger.error(f"Erreur récupération alias admin {admin_user_id}: {e}")
            return f"Admin_{admin_user_id}"

    async def _generate_default_admin_alias(self, admin_user_id: int) -> str:
        """Génère alias par défaut 'Baiter X' selon ordre d'ajout"""
        try:
            with self.db_manager.get_cursor() as cursor:
                # Récupérer ordre d'ajout de l'admin
                cursor.execute("""
                    SELECT ROW_NUMBER() OVER (ORDER BY date_creation ASC) as ordre
                    FROM admins
                    WHERE user_id = %s
                """, (admin_user_id,))
                result = cursor.fetchone()

                if result:
                    return f"{self.DEFAULT_ADMIN_PREFIX} {result['ordre']}"
                else:
                    # Fallback : compter le nombre d'admins + 1
                    cursor.execute("SELECT COUNT(*) as total FROM admins")
                    count_result = cursor.fetchone()
                    return f"{self.DEFAULT_ADMIN_PREFIX} {count_result['total'] if count_result else 1}"

        except Exception as e:
            logger.error(f"Erreur génération alias défaut pour {admin_user_id}: {e}")
            return f"{self.DEFAULT_ADMIN_PREFIX} 1"

    async def _save_admin_alias(self, admin_user_id: int, alias: str):
        """Sauvegarde l'alias d'un admin"""
        try:
            if self.config.is_owner(admin_user_id):
                # Owner : sauver dans config
                self.db_manager.set_config_value('owner_alias', alias)
            else:
                # Admin : sauver dans table admins
                with self.db_manager.get_cursor() as cursor:
                    cursor.execute("""
                        UPDATE admins SET alias = %s WHERE user_id = %s
                    """, (alias, admin_user_id))

        except Exception as e:
            logger.error(f"Erreur sauvegarde alias {admin_user_id}: {e}")

    async def _is_alias_unique(self, new_alias: str, current_user_id: int) -> bool:
        """Vérifie l'unicité de l'alias selon [source 2]"""
        try:
            # Vérifier owner_alias
            owner_alias = self.db_manager.get_config_value('owner_alias', self.DEFAULT_OWNER_ALIAS)
            if owner_alias.lower() == new_alias.lower() and not self.config.is_owner(current_user_id):
                return False

            # Vérifier alias des admins
            with self.db_manager.get_cursor() as cursor:
                cursor.execute("""
                    SELECT user_id FROM admins
                    WHERE LOWER(alias) = LOWER(%s) AND user_id != %s
                """, (new_alias, current_user_id))

                if cursor.fetchone():
                    return False

            return True

        except Exception as e:
            logger.error(f"Erreur vérification unicité alias '{new_alias}': {e}")
            return False

    async def modifier_alias(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Interface modification d'alias selon [source 2]"""
        query = update.callback_query
        user_id = query.from_user.id

        if not self.config.is_admin(user_id):
            await query.answer("❌ Accès non autorisé")
            return ConversationHandler.END

        try:
            # Récupérer alias actuel
            current_alias = await self.get_admin_alias(user_id)

            message = (
                f"✏️ <b>Modification d'Alias</b>\n\n"
                f"📝 <b>Alias actuel :</b> {current_alias}\n\n"
                f"📝 <b>Envoyez votre nouvel alias :</b>\n"
                f"• Maximum 30 caractères\n"
                f"• Lettres, chiffres, espaces autorisés\n"
                f"• Doit être unique\n\n"
                f"💡 <b>Exemples :</b> Admin Paul, Gestionnaire-1, Manager Pro\n\n"
                f"Ou annulez avec le bouton ci-dessous."
            )

            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Annuler", callback_data="cancel_alias")
            ]])

            await query.edit_message_text(
                message,
                parse_mode='HTML',
                reply_markup=keyboard
            )

            return self.WAITING_ALIAS

        except Exception as e:
            logger.error(f"Erreur interface modification alias {user_id}: {e}")
            await query.edit_message_text("❌ Erreur lors de l'affichage de l'interface")
            return ConversationHandler.END

    async def traiter_nouveau_alias(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Traite et valide le nouvel alias selon [source 2]"""
        user_id = update.effective_user.id
        new_alias = update.message.text.strip()

        if not self.config.is_admin(user_id):
            await update.message.reply_text("❌ Accès non autorisé")
            return ConversationHandler.END

        # Validation longueur
        if len(new_alias) > 30:
            await update.message.reply_text(
                "❌ L'alias ne peut pas dépasser 30 caractères.\n"
                "Veuillez en choisir un plus court."
            )
            return self.WAITING_ALIAS

        if len(new_alias) < 2:
            await update.message.reply_text(
                "❌ L'alias doit contenir au moins 2 caractères.\n"
                "Veuillez en choisir un plus long."
            )
            return self.WAITING_ALIAS

        # Validation caractères selon [source 2]
        if not new_alias.replace(' ', '').replace('-', '').replace('_', '').isalnum():
            await update.message.reply_text(
                "❌ L'alias ne doit contenir que des lettres, chiffres, espaces, tirets et underscores.\n"
                "Veuillez en choisir un autre."
            )
            return self.WAITING_ALIAS

        # Vérification unicité selon [source 2]
        if not await self._is_alias_unique(new_alias, user_id):
            await update.message.reply_text(
                "❌ Cet alias est déjà utilisé par un autre administrateur.\n"
                "Veuillez en choisir un autre unique."
            )
            return self.WAITING_ALIAS

        try:
            # Sauvegarder nouvel alias
            await self._save_admin_alias(user_id, new_alias)

            # Vider cache
            self.db_manager.clear_cache()

            message = (
                f"✅ <b>Alias mis à jour avec succès !</b>\n\n"
                f"📝 <b>Nouvel alias :</b> {new_alias}\n\n"
                f"Ce nom apparaîtra désormais dans toutes vos notifications."
            )

            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Retour Menu", callback_data="start_menu")
            ]])

            await update.message.reply_text(
                message,
                parse_mode='HTML',
                reply_markup=keyboard
            )

            logger.info(f"Alias mis à jour pour admin {user_id}: '{new_alias}'")
            return ConversationHandler.END

        except Exception as e:
            logger.error(f"Erreur sauvegarde nouvel alias {user_id}: {e}")
            await update.message.reply_text("❌ Erreur lors de la sauvegarde de l'alias")
            return ConversationHandler.END

    async def cancel_alias_change(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Annule la modification d'alias"""
        try:
            if update.callback_query:
                # Annulation via bouton
                query = update.callback_query

                message = "❌ <b>Modification annulée</b>\n\nVotre alias n'a pas été modifié."
                keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Retour Menu", callback_data="start_menu")
                ]])

                await query.edit_message_text(
                    message,
                    parse_mode='HTML',
                    reply_markup=keyboard
                )
            else:
                # Annulation via commande /cancel
                message = "❌ <b>Modification annulée</b>\n\nVotre alias n'a pas été modifié."
                keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Retour Menu", callback_data="start_menu")
                ]])

                await update.message.reply_text(
                    message,
                    parse_mode='HTML',
                    reply_markup=keyboard
                )

            return ConversationHandler.END

        except Exception as e:
            logger.error(f"Erreur annulation alias: {e}")
            return ConversationHandler.END

    async def send_status_notification(self, context, user_id, request_number, prenom, old_status, new_status, admin_alias):
        """Envoie notification changement statut avec alias admin"""
        try:
            # Émojis pour les statuts
            status_emojis = {
                "📨 Reçue": "📨",
                "⏳ En attente": "⏳",
                "🔄 En cours": "🔄",
                "✅ Réussie": "✅",
                "⚠️ Difficile": "⚠️",
                "❌ Abandonnée": "❌"
            }

            old_emoji = status_emojis.get(old_status, "📊")
            new_emoji = status_emojis.get(new_status, "📊")

            message = (
                f"📢 <b>Mise à jour de votre demande</b>\n\n"
                f"👤 <b>{prenom}</b>, votre demande <b>#{request_number}</b> "
                f"a été mise à jour :\n\n"
                f"{old_emoji} <s>{old_status}</s>\n"
                f"{new_emoji} <b>{new_status}</b>\n\n"
                f"👨‍💼 <b>Pris en charge par :</b> {admin_alias}\n\n"
            )

            # Messages personnalisés selon statut
            if new_status == "✅ Réussie":
                message += "🎉 Félicitations ! Votre demande a été traitée avec succès !"
            elif new_status == "🔄 En cours":
                message += "🔍 Votre demande est actuellement en cours de traitement."
            elif new_status == "⚠️ Difficile":
                message += "⚠️ Votre demande nécessite plus de temps pour être traitée."
            elif new_status == "❌ Abandonnée":
                message += "😔 Votre demande ne peut malheureusement pas être traitée."

            await context.bot.send_message(
                chat_id=user_id,
                text=message,
                parse_mode='HTML'
            )

            logger.info(f"Notification statut envoyée - Demande #{request_number} : {old_status} → {new_status} par {admin_alias}")

        except Exception as e:
            logger.error(f"Erreur envoi notification statut: {e}")

