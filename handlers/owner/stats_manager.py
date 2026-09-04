"""Gestionnaire statistiques selon architecture modulaire"""

import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from utils.validators import convert_utc_to_paris

logger = logging.getLogger(__name__)

class StatsManager:
    """Gestionnaire statistiques - Module admin"""
    
    def __init__(self, db_manager, config):
        """Initialisation StatsManager"""
        self.db_manager = db_manager
        self.config = config
        
        logger.info("StatsManager initialisé - Module statistiques")

    async def show_general_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Affiche les statistiques générales du bot"""
        try:
            stats = await self._get_general_statistics()
            
            message = self._format_general_stats_message(stats)
            keyboard = self._create_stats_keyboard()
            
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
            logger.error(f"Erreur affichage statistiques générales: {e}")
            await self._send_error_message(update, "❌ Erreur lors de la récupération des statistiques")

    async def show_user_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Affiche les statistiques utilisateurs"""
        try:
            stats = await self._get_user_statistics()
            
            message = self._format_user_stats_message(stats)
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Retour statistiques", callback_data="admin_stats"),
                InlineKeyboardButton("🏠 Menu admin", callback_data="admin_menu")
            ]])
            
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
            logger.error(f"Erreur affichage statistiques utilisateurs: {e}")
            await self._send_error_message(update, "❌ Erreur lors de la récupération des statistiques utilisateurs")

    async def show_requests_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Affiche les statistiques des demandes"""
        try:
            stats = await self._get_requests_statistics()
            
            message = self._format_requests_stats_message(stats)
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Retour statistiques", callback_data="admin_stats"),
                InlineKeyboardButton("🏠 Menu admin", callback_data="admin_menu")
            ]])
            
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
            logger.error(f"Erreur affichage statistiques demandes: {e}")
            await self._send_error_message(update, "❌ Erreur lors de la récupération des statistiques demandes")

    async def _get_general_statistics(self) -> dict:
        """Récupère les statistiques générales"""
        try:
            with self.db_manager.get_cursor() as cursor:
                stats = {}
                
                # Nombre total d'utilisateurs
                cursor.execute("SELECT COUNT(*) as total FROM users")
                stats['total_users'] = cursor.fetchone()['total']
                
                # Nombre total de demandes
                cursor.execute("SELECT COUNT(*) as total FROM demandes")
                stats['total_requests'] = cursor.fetchone()['total']
                
                # Utilisateurs actifs (dernières 24h)
                cursor.execute("""
                    SELECT COUNT(DISTINCT user_id) as actifs 
                    FROM users 
                    WHERE last_activity >= NOW() - INTERVAL 24 HOUR
                """)
                stats['active_users_24h'] = cursor.fetchone()['actifs']
                
                # Demandes du jour
                cursor.execute("""
                    SELECT COUNT(*) as today 
                    FROM demandes 
                    WHERE DATE(date_creation) = CURDATE()
                """)
                stats['requests_today'] = cursor.fetchone()['today']
                
                # Demandes de la semaine
                cursor.execute("""
                    SELECT COUNT(*) as week 
                    FROM demandes 
                    WHERE date_creation >= NOW() - INTERVAL 7 DAY
                """)
                stats['requests_week'] = cursor.fetchone()['week']
                
                return stats
                
        except Exception as e:
            logger.error(f"Erreur récupération statistiques générales: {e}")
            return {}

    async def _get_user_statistics(self) -> dict:
        """Récupère les statistiques utilisateurs"""
        try:
            with self.db_manager.get_cursor() as cursor:
                stats = {}
                
                # Nouveaux utilisateurs dernières 24h
                cursor.execute("""
                    SELECT COUNT(*) as nouveaux 
                    FROM users 
                    WHERE date_inscription >= NOW() - INTERVAL 24 HOUR
                """)
                stats['new_users_24h'] = cursor.fetchone()['nouveaux']
                
                # Nouveaux utilisateurs dernière semaine
                cursor.execute("""
                    SELECT COUNT(*) as nouveaux 
                    FROM users 
                    WHERE date_inscription >= NOW() - INTERVAL 7 DAY
                """)
                stats['new_users_week'] = cursor.fetchone()['nouveaux']
                
                # Top 5 utilisateurs les plus actifs
                cursor.execute("""
                    SELECT u.first_name, u.username, COUNT(d.id) as nb_demandes
                    FROM users u
                    LEFT JOIN demandes d ON u.user_id = d.user_id
                    GROUP BY u.user_id
                    ORDER BY nb_demandes DESC
                    LIMIT 5
                """)
                stats['top_users'] = cursor.fetchall()
                
                return stats
                
        except Exception as e:
            logger.error(f"Erreur récupération statistiques utilisateurs: {e}")
            return {}

    async def _get_requests_statistics(self) -> dict:
        """Récupère les statistiques des demandes"""
        try:
            with self.db_manager.get_cursor() as cursor:
                stats = {}
                
                # Répartition par statut
                cursor.execute("""
                    SELECT statut, COUNT(*) as count 
                    FROM demandes 
                    GROUP BY statut 
                    ORDER BY count DESC
                """)
                stats['by_status'] = cursor.fetchall()
                
                # Demandes prioritaires vs standard
                cursor.execute("""
                    SELECT 
                        SUM(CASE WHEN prioritaire = 1 THEN 1 ELSE 0 END) as prioritaires,
                        SUM(CASE WHEN prioritaire = 0 THEN 1 ELSE 0 END) as standard
                    FROM demandes
                """)
                priority_stats = cursor.fetchone()
                stats['priority_breakdown'] = priority_stats
                
                # Montant moyen des demandes prioritaires
                cursor.execute("""
                    SELECT AVG(montant) as moyenne 
                    FROM demandes 
                    WHERE prioritaire = 1 AND montant > 0
                """)
                avg_amount = cursor.fetchone()['moyenne']
                stats['avg_priority_amount'] = round(avg_amount, 2) if avg_amount else 0
                
                # Évolution sur 7 derniers jours
                cursor.execute("""
                    SELECT 
                        DATE(date_creation) as jour,
                        COUNT(*) as nb_demandes
                    FROM demandes 
                    WHERE date_creation >= NOW() - INTERVAL 7 DAY
                    GROUP BY DATE(date_creation)
                    ORDER BY jour DESC
                """)
                stats['last_7_days'] = cursor.fetchall()
                
                return stats
                
        except Exception as e:
            logger.error(f"Erreur récupération statistiques demandes: {e}")
            return {}

    def _format_general_stats_message(self, stats: dict) -> str:
        """Formate le message des statistiques générales"""
        if not stats:
            return "❌ Impossible de récupérer les statistiques"
        
        message = (
            "📊 <b>Statistiques Générales</b>\n\n"
            f"👥 <b>Utilisateurs totaux :</b> {stats.get('total_users', 0)}\n"
            f"🟢 <b>Actifs (24h) :</b> {stats.get('active_users_24h', 0)}\n\n"
            f"📝 <b>Demandes totales :</b> {stats.get('total_requests', 0)}\n"
            f"📅 <b>Aujourd'hui :</b> {stats.get('requests_today', 0)}\n"
            f"📆 <b>Cette semaine :</b> {stats.get('requests_week', 0)}\n\n"
            f"🤖 <b>Bot opérationnel</b> ✅"
        )
        
        return message

    def _format_user_stats_message(self, stats: dict) -> str:
        """Formate le message des statistiques utilisateurs"""
        if not stats:
            return "❌ Impossible de récupérer les statistiques utilisateurs"
        
        message = (
            "👥 <b>Statistiques Utilisateurs</b>\n\n"
            f"🆕 <b>Nouveaux (24h) :</b> {stats.get('new_users_24h', 0)}\n"
            f"📅 <b>Nouveaux (7j) :</b> {stats.get('new_users_week', 0)}\n\n"
        )
        
        top_users = stats.get('top_users', [])
        if top_users:
            message += "<b>🏆 Top utilisateurs actifs :</b>\n"
            for i, user in enumerate(top_users[:5], 1):
                name = user['first_name'] or user['username'] or 'Utilisateur'
                message += f"{i}. {name} - {user['nb_demandes']} demande(s)\n"
        
        return message

    def _format_requests_stats_message(self, stats: dict) -> str:
        """Formate le message des statistiques demandes"""
        if not stats:
            return "❌ Impossible de récupérer les statistiques des demandes"
        
        message = "📝 <b>Statistiques Demandes</b>\n\n"
        
        # Répartition par statut
        by_status = stats.get('by_status', [])
        if by_status:
            message += "<b>📊 Par statut :</b>\n"
            for status in by_status:
                message += f"• {status['statut']} : {status['count']}\n"
            message += "\n"
        
        # Prioritaires vs standard
        priority = stats.get('priority_breakdown', {})
        if priority:
            total = (priority.get('prioritaires', 0) + priority.get('standard', 0))
            message += (
                f"<b>🎯 Types de demandes :</b>\n"
                f"💎 Prioritaires : {priority.get('prioritaires', 0)}\n"
                f"📝 Standard : {priority.get('standard', 0)}\n"
                f"💰 Montant moyen prioritaire : {stats.get('avg_priority_amount', 0)}€\n\n"
            )
        
        # Évolution 7 derniers jours
        last_days = stats.get('last_7_days', [])
        if last_days:
            message += "<b>📈 7 derniers jours :</b>\n"
            for day in last_days:
                date_obj = day['jour']
                if isinstance(date_obj, str):
                    date_display = date_obj
                else:
                    date_display = date_obj.strftime('%d/%m')
                message += f"• {date_display} : {day['nb_demandes']} demande(s)\n"
        
        return message

    def _create_stats_keyboard(self):
        """Crée le clavier des statistiques"""
        keyboard = [
            [
                InlineKeyboardButton("👥 Utilisateurs", callback_data="stats_users"),
                InlineKeyboardButton("📝 Demandes", callback_data="stats_requests")
            ],
            [
                InlineKeyboardButton("🔄 Actualiser", callback_data="admin_stats"),
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
