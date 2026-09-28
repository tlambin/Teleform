"""Module d'analyse et d'affichage des statistiques d'utilisation du bot."""

import logging
from telegram import Update
from telegram.ext import ContextTypes
from utils.maintenance import check_storage_usage
from ui.admin import system as ui

logger = logging.getLogger(__name__)


class StatsManager:
    """Gestionnaire des métriques d'activité, des demandes et des utilisateurs avec support RBAC."""

    def __init__(self, db_manager, config):
        self.db_manager = db_manager
        self.config = config
        logger.info("StatsManager initialisé avec support RBAC")

    def _has_stats_perm(self, user_id: int) -> bool:
        """Vérifie si l'utilisateur a le droit de consulter les statistiques globales."""
        if self.config.is_owner(user_id):
            return True
        if self.config.is_admin(user_id):
            privs = self.db_manager.get_admin_privileges(user_id)
            return privs.get("can_view_stats", True)
        return False

    async def _safe_edit_or_send(self, query, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None):
        """Met à jour le message ou supprime la photo existante pour émettre du texte."""
        if query.message and query.message.photo:
            chat_id = query.message.chat_id
            try:
                await query.message.delete()
            except Exception:
                pass
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="HTML",
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
        else:
            try:
                await query.edit_message_text(
                    text=text,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                    disable_web_page_preview=True
                )
            except Exception:
                if query.message:
                    await query.message.reply_text(
                        text=text,
                        parse_mode="HTML",
                        reply_markup=reply_markup,
                        disable_web_page_preview=True
                    )

    async def show_general_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Affiche le panneau complet des statistiques pour la direction et managers habilités."""
        user = update.effective_user
        if not user or not self._has_stats_perm(user.id):
            if update.callback_query:
                await update.callback_query.answer("❌ Accès non autorisé aux statistiques.", show_alert=True)
            elif update.message:
                await update.message.reply_text("❌ Action non autorisée.")
            return

        if update.callback_query:
            await update.callback_query.answer()

        try:
            stats = self._get_full_statistics()
            message = ui.format_stats_message(stats)
            keyboard = ui.build_stats_keyboard(is_owner=self.config.is_owner(user.id))

            if update.callback_query:
                await self._safe_edit_or_send(update.callback_query, context, message, reply_markup=keyboard)
            elif update.message:
                await update.message.reply_text(
                    message, parse_mode="HTML", reply_markup=keyboard
                )

        except Exception as exc:
            logger.error("Erreur calcul statistiques complètes : %s", exc, exc_info=True)
            err_msg = "❌ Erreur technique lors du calcul des statistiques."
            if update.callback_query:
                await self._safe_edit_or_send(update.callback_query, context, err_msg)
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
                SELECT COUNT(*) AS total
                FROM users
                WHERE is_vip = TRUE AND (vip_until IS NULL OR vip_until > NOW())
                """
            )
            stats["total_vips"] = cursor.fetchone()["total"]

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

            # Métriques Rôles & Équipe
            cursor.execute("SELECT COUNT(*) AS total FROM staff")
            stats["total_staff"] = cursor.fetchone()["total"]

            cursor.execute("SELECT COUNT(*) AS total FROM admins")
            stats["total_admins"] = cursor.fetchone()["total"]

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

            # Cumul financier (actives + archives)
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
            prio_data = cursor.fetchone() or {}

            cursor.execute(
                """
                SELECT
                    COALESCE(SUM(montant), 0) AS montant_archives
                FROM archives
                WHERE prioritaire = 1
                """
            )
            arch_data = cursor.fetchone() or {}

            montant_actif = float(prio_data.get("total_montant") or 0.0)
            montant_arch = float(arch_data.get("montant_archives") or 0.0)

            stats["nb_prio"] = int(prio_data.get("nb_prio") or 0)
            stats["nb_std"] = int(prio_data.get("nb_std") or 0)
            stats["total_montant"] = round(montant_actif + montant_arch, 2)
            stats["avg_montant"] = float(prio_data.get("avg_montant") or 0.0)

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
        stats["db_stats"] = self.db_manager.get_database_size() or {}
        stats["storage_usage"] = float(check_storage_usage() or 0.0)
        return stats