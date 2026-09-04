"""Module de maintenance quotidienne, nettoyage des fichiers temporaires et archivage SQL."""

import logging
import os
import subprocess
from typing import Dict

logger = logging.getLogger(__name__)


def cleanup_temp_files():
    """Purge les fichiers temporaires, tronque les logs et nettoie le cache bytecode."""
    try:
        # Tronquage des logs volumineux (conservation des 1000 dernières lignes)
        log_files = ["/tmp/bot.log", "/tmp/bot_console.log", "/tmp/maintenance_task.log"]
        for log_path in log_files:
            if os.path.exists(log_path):
                tmp_path = f"{log_path}.tmp"
                cmd = f"tail -n 1000 {log_path} > {tmp_path} && mv {tmp_path} {log_path}"
                subprocess.run(cmd, shell=True, capture_output=True)

        home_dir = os.path.expanduser("~")
        cleanup_commands = [
            f"find {home_dir} -name '*.pyc' -delete 2>/dev/null || true",
            f"find {home_dir} -name '__pycache__' -type d -exec rm -rf {{}} + 2>/dev/null || true",
            "find /tmp -name 'core.*' -delete 2>/dev/null || true",
            "find /tmp -name '*.tmp' -delete 2>/dev/null || true",
        ]

        for cmd in cleanup_commands:
            subprocess.run(cmd, shell=True, capture_output=True)

        logger.info("🧹 Nettoyage des fichiers temporaires terminé")

    except Exception as exc:
        logger.error("Erreur nettoyage fichiers temporaires: %s", exc)


def archive_old_requests(db_manager):
    """Bascule les demandes résolues ou abandonnées de plus de 7 jours dans la table archives."""
    try:
        with db_manager.get_cursor() as cursor:
            archive_query = """
                INSERT INTO archives (
                    original_id, user_id, prenom, nom, age, localisation,
                    photo_id, instagram, snapchat, details, prioritaire,
                    montant, statut, date_creation
                )
                SELECT id, user_id, prenom, nom, age, localisation,
                       photo_id, instagram, snapchat, details, prioritaire,
                       montant, statut, date_creation
                FROM demandes
                WHERE date_creation < DATE_SUB(NOW(), INTERVAL 7 DAY)
                AND statut IN ('✅ Réussie', '❌ Abandonnée')
            """
            cursor.execute(archive_query)
            archived_count = cursor.rowcount

            if archived_count > 0:
                delete_query = """
                    DELETE FROM demandes
                    WHERE date_creation < DATE_SUB(NOW(), INTERVAL 7 DAY)
                    AND statut IN ('✅ Réussie', '❌ Abandonnée')
                """
                cursor.execute(delete_query)
                logger.info("📦 %d demandes archivées et purgées de la table active", archived_count)
            else:
                logger.info("📦 Aucune demande à archiver")

    except Exception as exc:
        logger.error("Erreur archivage automatique: %s", exc, exc_info=True)


def check_storage_usage() -> float:
    """Retourne l'espace disque consommé dans le répertoire utilisateur en Mo."""
    try:
        home = os.path.expanduser("~")
        res = subprocess.run(["du", "-sb", home], capture_output=True, text=True)

        if res.returncode == 0:
            bytes_used = int(res.stdout.split()[0])
            mb_used = bytes_used / (1024 * 1024)

            # Alerte préventive si saturation proche de la limite PythonAnywhere (512 Mo)
            if mb_used > 400.0:
                logger.warning("⚠️ Espace disque critique: %.1f Mo / 512 Mo", mb_used)
                cleanup_temp_files()

            return round(mb_used, 2)

        logger.error("Erreur commande 'du': %s", res.stderr)
        return 0.0

    except Exception as exc:
        logger.error("Erreur calcul espace disque: %s", exc)
        return 0.0


def optimize_database(db_manager):
    """Exécute OPTIMIZE TABLE sur les tables existantes et vide le cache mémoire."""
    try:
        tables = ["demandes", "demandes_suivi", "archives", "users", "admins", "config"]
        with db_manager.get_cursor() as cursor:
            for tbl in tables:
                try:
                    cursor.execute(f"OPTIMIZE TABLE {tbl}")
                except Exception as tbl_exc:
                    logger.warning("Échec optimisation table %s: %s", tbl, tbl_exc)

        db_manager.clear_cache()
        logger.info("🔧 Optimisation MySQL et purge du cache applicatif terminées")

    except Exception as exc:
        logger.error("Erreur routine optimisation base de données: %s", exc)


def cleanup_database(db_manager):
    """Purger les archives de plus de 3 mois et les comptes inactifs sans historique."""
    try:
        with db_manager.get_cursor() as cursor:
            # Purge des archives obsolètes (plus de 90 jours)
            cursor.execute(
                """
                DELETE FROM archives
                WHERE date_archivage < DATE_SUB(NOW(), INTERVAL 3 MONTH)
                """
            )
            purged_archives = cursor.rowcount
            if purged_archives > 0:
                logger.info("🗑️ %d archives obsolètes supprimées définitivement", purged_archives)

            # Purge des utilisateurs inactifs sans demande associée
            cursor.execute(
                """
                DELETE u FROM users u
                LEFT JOIN demandes d ON u.user_id = d.user_id
                LEFT JOIN archives a ON u.user_id = a.user_id
                WHERE u.derniere_activite < DATE_SUB(NOW(), INTERVAL 6 MONTH)
                AND d.id IS NULL
                AND a.id IS NULL
                """
            )
            purged_users = cursor.rowcount
            if purged_users > 0:
                logger.info("👥 %d profils orphelins inactifs supprimés", purged_users)

    except Exception as exc:
        logger.error("Erreur nettoyage base de données: %s", exc, exc_info=True)


def get_system_stats(db_manager) -> Dict:
    """Retourne les métriques techniques agrégées du système."""
    stats = {}
    try:
        mb_used = check_storage_usage()
        stats["storage_mb"] = mb_used
        stats["storage_percent"] = (mb_used / 512.0) * 100.0

        tmp_dir = "/tmp"
        if os.path.exists(tmp_dir):
            stats["tmp_files"] = len([f for f in os.listdir(tmp_dir) if os.path.isfile(os.path.join(tmp_dir, f))])
        else:
            stats["tmp_files"] = 0

        # Mesure des logs
        log_paths = ["/tmp/bot.log", "/tmp/bot_console.log", "/tmp/maintenance_task.log"]
        total_logs_bytes = sum(os.path.getsize(p) for p in log_paths if os.path.exists(p))
        stats["logs_mb"] = round(total_logs_bytes / (1024 * 1024), 2)

        with db_manager.get_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS count FROM demandes")
            stats["demandes_count"] = cursor.fetchone()["count"]

            cursor.execute("SELECT COUNT(*) AS count FROM archives")
            stats["archives_count"] = cursor.fetchone()["count"]

            cursor.execute("SELECT COUNT(*) AS count FROM users")
            stats["users_count"] = cursor.fetchone()["count"]

        return stats

    except Exception as exc:
        logger.error("Erreur compilation statistiques système: %s", exc)
        return stats


def emergency_cleanup(db_manager=None):
    """Purge immédiate d'urgence en cas de saturation de l'espace disque."""
    try:
        logger.warning("🚨 Déclenchement du protocole de nettoyage d'urgence")

        subprocess.run("rm -rf /tmp/*.log.* 2>/dev/null || true", shell=True)
        subprocess.run("find /tmp -name '*.tmp' -delete 2>/dev/null || true", shell=True)

        # Réduction immédiate des journaux à 100 lignes
        log_files = ["/tmp/bot.log", "/tmp/bot_console.log", "/tmp/maintenance_task.log"]
        for lp in log_files:
            if os.path.exists(lp):
                subprocess.run(f"tail -n 100 {lp} > {lp}.tmp && mv {lp}.tmp {lp}", shell=True)

        if db_manager:
            cleanup_database(db_manager)

        logger.info("🚨 Nettoyage d'urgence finalisé")

    except Exception as exc:
        logger.error("Erreur nettoyage d'urgence: %s", exc)


def daily_maintenance(db_manager):
    """Point d'entrée de la routine de maintenance quotidienne globale."""
    logger.info("🔧 === Démarrage de la maintenance quotidienne ===")
    try:
        storage_mb = check_storage_usage()

        if storage_mb > 460.0:  # Dépassé 90% des 512 Mo
            emergency_cleanup(db_manager)
        else:
            cleanup_temp_files()
            archive_old_requests(db_manager)
            cleanup_database(db_manager)
            optimize_database(db_manager)

        stats = get_system_stats(db_manager)
        logger.info("📊 === Rapport de maintenance ===")
        logger.info("💾 Stockage: %.1f Mo (%.1f%%)", stats.get("storage_mb", 0.0), stats.get("storage_percent", 0.0))
        logger.info("📝 Demandes: %s | Archives: %s | Utilisateurs: %s", stats.get("demandes_count", 0), stats.get("archives_count", 0), stats.get("users_count", 0))
        logger.info("✅ === Maintenance terminée avec succès ===")

    except Exception as exc:
        logger.error("Erreur générale routine maintenance: %s", exc, exc_info=True)


if __name__ == "__main__":
    # Permet l'exécution directe en tâche cron planifiée
    logging.basicConfig(level=logging.INFO)
    try:
        from config import Config
        from database import DatabaseManager

        cfg = Config()
        db = DatabaseManager(cfg)
        daily_maintenance(db)
    except Exception as main_exc:
        logger.critical("Impossible de démarrer la maintenance autonome: %s", main_exc)