"""Gestionnaire configuration selon architecture modulaire"""

import logging
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

class ConfigManager:
    """Gestionnaire configuration - Module admin"""
    
    def __init__(self, db_manager, config):
        """Initialisation ConfigManager"""
        self.db_manager = db_manager
        self.config = config
        
        # Configuration par défaut
        self.default_settings = {
            'bot_maintenance': False,
            'max_requests_per_user': 10,
            'allow_priority_requests': True,
            'auto_approve_requests': False,
            'notification_channel': None,
            'welcome_message': "👋 Bienvenue ! Utilisez /start pour commencer.",
            'max_request_age_days': 30
        }
        
        logger.info("ConfigManager initialisé - Module configuration")

    async def show_config_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Affiche le menu de configuration"""
        try:
            current_config = await self._get_current_config()
            
            message = self._format_config_message(current_config)
            keyboard = self._create_config_keyboard()
            
            if update.callback_query:
                await update.callback_query.edit_message_text(
                    message,
                    parse_mode='HTML',
                    reply_markup=keyboard
                )
            else:
                await update.message.reply_text(
                    message,
                    parse_mode='HTML',
                    reply_markup=keyboard
                )
                
        except Exception as e:
            logger.error(f"Erreur affichage menu configuration: {e}")
            await self._send_error_message(update, "❌ Erreur lors de la récupération de la configuration")

    async def toggle_maintenance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Active/désactive le mode maintenance"""
        try:
            query = update.callback_query
            await query.answer()
            
            current_status = await self._get_config_value('bot_maintenance', False)
            new_status = not current_status
            
            await self._set_config_value('bot_maintenance', new_status)
            
            status_text = "activé" if new_status else "désactivé"
            await query.edit_message_text(
                f"🛠️ <b>Mode maintenance {status_text}</b>\n\n"
                f"Le bot est maintenant {'en maintenance' if new_status else 'opérationnel'}.",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Retour configuration", callback_data="admin_config")
                ]])
            )
            
            logger.info(f"Mode maintenance {status_text} par admin {query.from_user.id}")
            
        except Exception as e:
            logger.error(f"Erreur toggle maintenance: {e}")
            await self._send_error_message(update, "❌ Erreur lors de la modification du mode maintenance")

    async def show_limits_config(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Affiche la configuration des limites"""
        try:
            query = update.callback_query
            await query.answer()
            
            max_requests = await self._get_config_value('max_requests_per_user', 10)
            max_age = await self._get_config_value('max_request_age_days', 30)
            
            message = (
                "⚙️ <b>Configuration Limites</b>\n\n"
                f"📊 <b>Max demandes par utilisateur :</b> {max_requests}\n"
                f"📅 <b>Âge max des demandes (jours) :</b> {max_age}\n\n"
                "Utilisez les boutons ci-dessous pour modifier :"
            )
            
            keyboard = [
                [
                    InlineKeyboardButton("📊 Modifier max demandes", callback_data="config_max_requests"),
                    InlineKeyboardButton("📅 Modifier âge max", callback_data="config_max_age")
                ],
                [InlineKeyboardButton("🔙 Retour configuration", callback_data="admin_config")]
            ]
            
            await query.edit_message_text(
                message,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        except Exception as e:
            logger.error(f"Erreur affichage limites: {e}")
            await self._send_error_message(update, "❌ Erreur lors de l'affichage des limites")

    async def toggle_priority_requests(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Active/désactive les demandes prioritaires"""
        try:
            query = update.callback_query
            await query.answer()
            
            current_status = await self._get_config_value('allow_priority_requests', True)
            new_status = not current_status
            
            await self._set_config_value('allow_priority_requests', new_status)
            
            status_text = "activées" if new_status else "désactivées"
            await query.edit_message_text(
                f"💎 <b>Demandes prioritaires {status_text}</b>\n\n"
                f"Les demandes prioritaires sont maintenant {'autorisées' if new_status else 'interdites'}.",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Retour configuration", callback_data="admin_config")
                ]])
            )
            
            logger.info(f"Demandes prioritaires {status_text} par admin {query.from_user.id}")
            
        except Exception as e:
            logger.error(f"Erreur toggle priority requests: {e}")
            await self._send_error_message(update, "❌ Erreur lors de la modification des demandes prioritaires")

    async def _get_current_config(self) -> dict:
        """Récupère la configuration actuelle"""
        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute("SELECT setting_key, setting_value FROM bot_settings")
                settings = cursor.fetchall()
                
                config = self.default_settings.copy()
                for setting in settings:
                    key = setting['setting_key']
                    value = setting['setting_value']
                    
                    # Conversion des types
                    if value == 'true':
                        config[key] = True
                    elif value == 'false':
                        config[key] = False
                    elif value.isdigit():
                        config[key] = int(value)
                    else:
                        config[key] = value
                
                return config
                
        except Exception as e:
            logger.error(f"Erreur récupération configuration: {e}")
            return self.default_settings.copy()

    async def _get_config_value(self, key: str, default=None):
        """Récupère une valeur de configuration spécifique"""
        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    "SELECT setting_value FROM bot_settings WHERE setting_key = %s",
                    (key,)
                )
                result = cursor.fetchone()
                
                if result:
                    value = result['setting_value']
                    # Conversion des types
                    if value == 'true':
                        return True
                    elif value == 'false':
                        return False
                    elif value.isdigit():
                        return int(value)
                    else:
                        return value
                else:
                    return default if default is not None else self.default_settings.get(key)
                    
        except Exception as e:
            logger.error(f"Erreur récupération config {key}: {e}")
            return default if default is not None else self.default_settings.get(key)

    async def _set_config_value(self, key: str, value):
        """Définit une valeur de configuration"""
        try:
            with self.db_manager.get_cursor() as cursor:
                # Conversion en string pour stockage
                if isinstance(value, bool):
                    str_value = 'true' if value else 'false'
                else:
                    str_value = str(value)
                
                cursor.execute("""
                    INSERT INTO bot_settings (setting_key, setting_value, updated_at)
                    VALUES (%s, %s, NOW())
                    ON DUPLICATE KEY UPDATE 
                    setting_value = VALUES(setting_value),
                    updated_at = NOW()
                """, (key, str_value))
                
                logger.info(f"Configuration mise à jour: {key} = {value}")
                return True
                
        except Exception as e:
            logger.error(f"Erreur mise à jour config {key}: {e}")
            return False

    def _format_config_message(self, config: dict) -> str:
        """Formate le message de configuration"""
        maintenance_status = "🔴 Activé" if config.get('bot_maintenance', False) else "🟢 Désactivé"
        priority_status = "✅ Autorisées" if config.get('allow_priority_requests', True) else "❌ Interdites"
        
        message = (
            "⚙️ <b>Configuration du Bot</b>\n\n"
            f"🛠️ <b>Mode maintenance :</b> {maintenance_status}\n"
            f"💎 <b>Demandes prioritaires :</b> {priority_status}\n"
            f"📊 <b>Max demandes/utilisateur :</b> {config.get('max_requests_per_user', 10)}\n"
            f"📅 <b>Âge max demandes :</b> {config.get('max_request_age_days', 30)} jours\n\n"
            "Utilisez les boutons ci-dessous pour modifier la configuration :"
        )
        
        return message

    def _create_config_keyboard(self):
        """Crée le clavier de configuration"""
        keyboard = [
            [
                InlineKeyboardButton("🛠️ Mode maintenance", callback_data="config_toggle_maintenance"),
                InlineKeyboardButton("💎 Demandes prioritaires", callback_data="config_toggle_priority")
            ],
            [
                InlineKeyboardButton("📊 Limites", callback_data="config_limits"),
                InlineKeyboardButton("📝 Messages", callback_data="config_messages")
            ],
            [
                InlineKeyboardButton("🔄 Actualiser", callback_data="admin_config"),
                InlineKeyboardButton("🏠 Menu admin", callback_data="admin_menu")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)

    async def _send_error_message(self, update: Update, message: str):
        """Envoie un message d'erreur"""
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Retour", callback_data="admin_menu")
        ]])
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                message,
                reply_markup=keyboard
            )
        else:
            await update.message.reply_text(
                message,
                reply_markup=keyboard
            )

    async def get_setting(self, key: str, default=None):
        """Méthode publique pour récupérer une configuration"""
        return await self._get_config_value(key, default)

    async def set_setting(self, key: str, value):
        """Méthode publique pour définir une configuration"""
        return await self._set_config_value(key, value)

    async def is_maintenance_mode(self) -> bool:
        """Vérifie si le bot est en mode maintenance"""
        return await self._get_config_value('bot_maintenance', False)

    async def is_priority_allowed(self) -> bool:
        """Vérifie si les demandes prioritaires sont autorisées"""
        return await self._get_config_value('allow_priority_requests', True)

    async def get_max_requests_per_user(self) -> int:
        """Récupère le nombre maximum de demandes par utilisateur"""
        return await self._get_config_value('max_requests_per_user', 10)
