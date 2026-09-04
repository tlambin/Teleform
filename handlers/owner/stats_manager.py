"""Module d'analyse et d'affichage des statistiques d'utilisation du bot."""

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from utils.maintenance import check_storage_usage

logger = logging.getLogger(__name__)


class StatsManager:
    """Gestionnaire des métriques d'activité, des demandes et des utilisateurs."""

    def __init__(self, db_manager, config):
        self.db_manager = db_manager
        self.config = config
        logger.info("StatsManager initialisé")

    async def show_general_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Affiche le panneau complet des statistiques à destination de l'Owner."""
        user = update.effective_user
        if not user or not self.config.is_owner(user.id):
            if update.callback_query:
                await update.callback_query.answer("❌ Accès propriétaire requis.", show_alert=True)
            elif update.message:
                await update.message.reply_text("❌ Action réservée au propriétaire.")
            return

        try:
            stats = self._get_full_statistics()
            message = self._format_stats_message(stats)
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Actualiser", callback_data="bot_stats")],
                [InlineKeyboardButton("🔙 Menu Owner", callback_data="gerer_bot")]
            ])

            if update.callback_query:
                await update.callback_query.edit_message_text(
                    message, parse_mode="HTML", reply_markup=keyboard
                )
            elif update.message:
                await update.message.reply_text(
                    message, parse_mode="HTML", reply_markup=keyboard
                )

        except Exception as exc:
            logger.error("Erreur calcul statistiques complètes: %s", exc, exc_info=True)
            err_msg = "❌ Erreur technique lors du calcul des statistiques."
            if update.callback_query:
                await update.callback_query.edit_message_text(err_msg)
            elif update.message:
                await update.message.reply_text(err_msg)

    def _get_full_statistics(self) -> dict:
        """Agrège l'ensemble des données chiffrées en base."""
        stats = {}
        with self.db_manager.get_cursor() as cursor:
            # Métriques Utilisateurs
            cursor.execute("SELECT COUNT(*) AS total FROM users")
            stats["total_users"] = cursor.fetchone()["total"]

            cursor.execute(
                """
                SELECT COUNT(DISTINCT user_id) AS actifs
                FROM users
                WHERE derniere_activite >= NOW() - INTERVAL 24 HOUR
                """
            )
            stats["active_24h"] = cursor.fetchone()["actifs"]

            cursor.execute(
                """
                SELECT COUNT(*) AS nouveaux
                FROM users
                WHERE date_inscription >= NOW() - INTERVAL 7 DAY
                """
            )
            stats["new_7d"] = cursor.fetchone()["nouveaux"]

            # Métriques Demandes
            cursor.execute("SELECT COUNT(*) AS total FROM demandes")
            stats["total_demandes"] = cursor.fetchone()["total"]

            cursor.execute("SELECT COUNT(*) AS total FROM archives")
            stats["total_archives"] = cursor.fetchone()["total"]

            cursor.execute(
                """
                SELECT COUNT(*) AS total
                FROM demandes
                WHERE DATE(date_creation) = CURDATE()
                """
            )
            stats["demandes_today"] = cursor.fetchone()["total"]

            cursor.execute(
                """
                SELECT
                    SUM(CASE WHEN prioritaire = 1 THEN 1 ELSE 0 END) AS nb_prio,
                    SUM(CASE WHEN prioritaire = 0 THEN 1 ELSE 0 END) AS nb_std,
                    COALESCE(SUM(montant), 0) AS total_montant,
                    COALESCE(AVG(NULLIF(montant, 0)), 0) AS avg_montant
                FROM demandes
                """
            )
            prio_data = cursor.fetchone()
            stats["nb_prio"] = prio_data["nb_prio"] or 0
            stats["nb_std"] = prio_data["nb_std"] or 0
            stats["total_montant"] = float(prio_data["total_montant"])
            stats["avg_montant"] = float(prio_data["avg_montant"])

            # Répartition par statut
            cursor.execute(
                """
                SELECT statut, COUNT(*) AS count
                FROM demandes
                GROUP BY statut
                ORDER BY count DESC
                """
            )
            stats["statuts"] = cursor.fetchall()

        # Métriques Stockage et Base
        stats["db_stats"] = self.db_manager.get_database_size()
        stats["storage_usage"] = check_storage_usage()
        return stats

    def _format_stats_message(self, stats: dict) -> str:
        """Met en forme l'affichage des métriques."""
        storage = stats.get("storage_usage", 0.0)
        db_size = stats.get("db_stats", {}).get("total_size_mb", 0.0)

        lines = [
            "📈 <b>Tableau de Bord & Statistiques</b>\n",
            "👥 <b>Communauté :</b>",
            f"• Inscrits totaux : <b>{stats.get('total_users', 0)}</b>",
            f"• Actifs (dernières 24h) : <b>{stats.get('active_24h', 0)}</b>",
            f"• Nouveaux (7 derniers jours) : <b>{stats.get('new_7d', 0)}</b>\n",
            "📋 <b>Volume de Demandes :</b>",
            f"• Actives : <b>{stats.get('total_demandes', 0)}</b>",
            f"• Reçues aujourd'hui : <b>{stats.get('demandes_today', 0)}</b>",
            f"• Archivées : <b>{stats.get('total_archives', 0)}</b>",
            f"• Répartition : 💎 <b>{stats.get('nb_prio', 0)}</b> prioritaires | 📝 <b>{stats.get('nb_std', 0)}</b> standard",
            f"• Montant cumulé : <b>{stats.get('total_montant', 0.0):.2f}€</b> (moyenne prio : {stats.get('avg_montant', 0.0):.2f}€)\n",
            "📊 <b>Statuts actuels :</b>"
        ]

        for s in stats.get("statuts", []):
            lines.append(f"• {s['statut']} : {s['count']}")

        lines.append(f"\n💾 <b>Ressources Système :</b>")
        lines.append(f"• Stockage local : <b>{storage:.1f} Mo / 512 Mo</b> ({(storage/512)*100:.1f}%)")
        lines.append(f"• Base de données : <b>{db_size} Mo</b>")

        return "\n".join(lines)