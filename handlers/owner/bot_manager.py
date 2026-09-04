"""Gestion contrôle bot selon architecture modulaire"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

class BotManager:
    """Gestionnaire contrôle bot - Module Owner"""
    
    def __init__(self, db_manager, config):
        """Initialisation BotManager"""
        self.db_manager = db_manager
        self.config = config
        
        logger.info("BotManager initialisé - Architecture modulaire")

    async def bot_on(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Active le bot globalement"""
        query = update.callback_query
        await query.answer()
        
        try:
            # Mettre à jour le statut en base
            with self.db_manager.get_cursor() as cursor:
                cursor.execute("""
                    UPDATE bot_settings 
                    SET bot_active = TRUE, updated_at = NOW() 
                    WHERE id = 1
                """)
            
            logger.info(f"Bot activé par owner {update.effective_user.id}")
            
            await query.edit_message_text(
                "🟢 <b>Bot activé</b>\n\n"
                "✅ Le bot est maintenant actif pour tous les utilisateurs.\n"
                "📊 Toutes les fonctionnalités sont disponibles.\n\n"
                "Les utilisateurs peuvent créer des demandes et utiliser toutes les commandes.",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔴 Désactiver", callback_data="bot_off")],
                    [InlineKeyboardButton("🛠️ Maintenance", callback_data="bot_maintenance")],
                    [InlineKeyboardButton("🔙 Menu Owner", callback_data="start_menu")]
                ])
            )
            
        except Exception as e:
            logger.error(f"Erreur activation bot: {e}")
            await query.edit_message_text(
                "❌ Erreur lors de l'activation du bot.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Retour", callback_data="gerer_bot")
                ]])
            )

    async def bot_off(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Désactive le bot globalement"""
        query = update.callback_query
        await query.answer()
        
        try:
            # Mettre à jour le statut en base
            with self.db_manager.get_cursor() as cursor:
                cursor.execute("""
                    UPDATE bot_settings 
                    SET bot_active = FALSE, updated_at = NOW() 
                    WHERE id = 1
                """)
            
            logger.info(f"Bot désactivé par owner {update.effective_user.id}")
            
            await query.edit_message_text(
                "🔴 <b>Bot désactivé</b>\n\n"
                "⏸️ Le bot est maintenant inactif pour les utilisateurs normaux.\n"
                "🔒 Seuls les administrateurs et le propriétaire peuvent l'utiliser.\n\n"
                "Les utilisateurs recevront un message indiquant que le service est temporairement indisponible.",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🟢 Activer", callback_data="bot_on")],
                    [InlineKeyboardButton("🛠️ Maintenance", callback_data="bot_maintenance")],
                    [InlineKeyboardButton("🔙 Menu Owner", callback_data="start_menu")]
                ])
            )
            
        except Exception as e:
            logger.error(f"Erreur désactivation bot: {e}")
            await query.edit_message_text(
                "❌ Erreur lors de la désactivation du bot.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Retour", callback_data="gerer_bot")
                ]])
            )

    async def bot_maintenance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Active le mode maintenance"""
        query = update.callback_query
        await query.answer()
        
        try:
            # Mettre à jour le statut en base
            with self.db_manager.get_cursor() as cursor:
                cursor.execute("""
                    UPDATE bot_settings 
                    SET maintenance_mode = TRUE, updated_at = NOW() 
                    WHERE id = 1
                """)
            
            logger.info(f"Mode maintenance activé par owner {update.effective_user.id}")
            
            await query.edit_message_text(
                "🛠️ <b>Mode maintenance activé</b>\n\n"
                "⚙️ Le bot est en cours de maintenance.\n"
                "🔧 Seul le propriétaire peut l'utiliser actuellement.\n\n"
                "Les utilisateurs et administrateurs recevront un message de maintenance.",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🟢 Activer", callback_data="bot_on")],
                    [InlineKeyboardButton("🔴 Désactiver", callback_data="bot_off")],
                    [InlineKeyboardButton("🔙 Menu Owner", callback_data="start_menu")]
                ])
            )
            
        except Exception as e:
            logger.error(f"Erreur mode maintenance: {e}")
            await query.edit_message_text(
                "❌ Erreur lors de l'activation du mode maintenance.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Retour", callback_data="gerer_bot")
                ]])
            )

    async def get_bot_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Affiche le statut actuel du bot"""
        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute("""
                    SELECT bot_active, maintenance_mode, updated_at 
                    FROM bot_settings 
                    WHERE id = 1
                """)
                status = cursor.fetchone()

            if not status:
                # Créer un enregistrement par défaut si aucun n'existe
                with self.db_manager.get_cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO bot_settings (id, bot_active, maintenance_mode) 
                        VALUES (1, TRUE, FALSE)
                    """)
                status = {'bot_active': True, 'maintenance_mode': False, 'updated_at': None}

            # Déterminer le statut
            if status['maintenance_mode']:
                status_text = "🛠️ **Maintenance**"
                status_desc = "Le bot est en maintenance. Seul le propriétaire peut l'utiliser."
            elif status['bot_active']:
                status_text = "🟢 **Actif**"
                status_desc = "Le bot fonctionne normalement pour tous les utilisateurs."
            else:
                status_text = "🔴 **Inactif**"
                status_desc = "Le bot est désactivé. Seuls les admins et le propriétaire peuvent l'utiliser."

            last_update = ""
            if status['updated_at']:
                last_update = f"\n🕐 **Dernière modification :** {status['updated_at'].strftime('%d/%m/%Y à %H:%M')}"

            message = (
                f"📊 **Statut du Bot**\n\n"
                f"**État actuel :** {status_text}\n\n"
                f"{status_desc}{last_update}"
            )

            keyboard = [
                [InlineKeyboardButton("🟢 Activer", callback_data="bot_on"),
                 InlineKeyboardButton("🔴 Désactiver", callback_data="bot_off")],
                [InlineKeyboardButton("🛠️ Maintenance", callback_data="bot_maintenance")],
                [InlineKeyboardButton("🔙 Menu Owner", callback_data="start_menu")]
            ]

            if update.callback_query:
                query = update.callback_query
                await query.answer()
                await query.edit_message_text(
                    message,
                    parse_mode='Markdown',
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            else:
                await update.message.reply_text(
                    message,
                    parse_mode='Markdown',
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                
        except Exception as e:
            logger.error(f"Erreur statut bot: {e}")
            error_msg = "❌ Erreur lors de la récupération du statut"
            
            if update.callback_query:
                await update.callback_query.edit_message_text(error_msg)
            else:
                await update.message.reply_text(error_msg)
