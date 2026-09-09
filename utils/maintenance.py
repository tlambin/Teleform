"""Module de maintenance quotidienne, nettoyage des fichiers temporaires et archivage SQL."""

import logging
import os
import subprocess
from typing import Dict

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_LOG_FILE = os.path.join(BASE_DIR, "logs", "bot.log")


def _truncate_file(file_path: str, keep_lines: int = 1000):
    """Tronque un fichier en ne conservant que les dernières lignes (purement en Python)."""
    if not os.path.exists(file_path):
        return
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        if len(lines) > keep_lines:
            with open(file_path, "w", encoding="utf-8") as f:
                f.writelines(lines[-keep_lines:])
    except Exception as exc:
        logger.warning("Échec tronquage du fichier %s : %s", file_path, exc)


def cleanup_temp_files():
    """Purge les fichiers temporaires, tronque les logs et nettoie le cache bytecode."""
    try:
        log_files = [
            LOCAL_LOG_FILE,
            "/tmp/bot.log",
            "/tmp/bot_console.log",
            "/tmp/maintenance_task.log"
        ]
        for log_path in log_files:
            _truncate_file(log_path, keep_lines=1000)

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
        logger.error("Erreur nettoyage fichiers temporaires : %s", exc)


def archive_old_requests(db_manager):
    """Archive les demandes anciennes avec transaction atomique sécurisée et purge des suivis."""
    try:
        with db_manager.transaction() as cursor:
            cursor.execute(
                """
                SELECT id FROM demandes
                WHERE date_creation < DATE_SUB(NOW(), INTERVAL 7 DAY)
                AND statut IN ('✅ Réussie', '❌ Abandonnée')
                """
            )
            rows = cursor.fetchall()
            if not rows:
                logger.info("📦 Aucune demande à archiver")
                return

            ids = [r["id"] for r in rows]
            placeholders = ", ".join(["%s"] * len(ids))

            archive_query = f"""
                INSERT INTO archives (
                    original_id, user_id, prenom, nom, age, localisation,
                    photo_id, instagram, snapchat, details, prioritaire,
                    montant, statut, date_creation, date_archivage
                )
                SELECT id, user_id, prenom, nom, age, localisation,
                       photo_id, instagram, snapchat, details, prioritaire,
                       montant, statut, date_creation, NOW()
                FROM demandes
                WHERE id IN ({placeholders})
            """
            cursor.execute(archive_query, ids)
            archived_count = cursor.rowcount

            cursor.execute(f"DELETE FROM demandes_suivi WHERE demande_id IN ({placeholders})", ids)
            cursor.execute(f"DELETE FROM demandes WHERE id IN ({placeholders})", ids)

            logger.info("📦 %d demandes archivées et purgées avec succès", archived_count)

    except Exception as exc:
        logger.error("Erreur lors de l'archivage (rollback exécuté) : %s", exc, exc_info=True)


def check_storage_usage() -> float:
    """Retourne l'espace disque consommé dans le répertoire utilisateur en Mo."""
    try:
        home = os.path.expanduser("~")
        res = subprocess.run(["du", "-sb", home], capture_output=True, text=True)

        if res.returncode == 0:
            bytes_used = int(res.stdout.split()[0])
            mb_used = bytes_used / (1024 * 1024)

            if mb_used > 400.0:
                logger.warning("⚠️ Espace disque critique : %.1f Mo / 512 Mo", mb_used)
                cleanup_temp_files()

            return round(mb_used, 2)

        logger.error("Erreur commande 'du' : %s", res.stderr)
        return 0.0

    except Exception as exc:
        logger.error("Erreur calcul espace disque : %s", exc)
        return 0.0


def optimize_database(db_manager):
    """Exécute OPTIMIZE TABLE sur les tables existantes et vide le cache mémoire."""
    try:
        tables = [
            "demandes", "demandes_suivi", "archives",
            "users", "admins", "admin_preferences", "config"
        ]
        with db_manager.get_cursor() as cursor:
            for tbl in tables:
                try:
                    cursor.execute(f"OPTIMIZE TABLE {tbl}")
                except Exception as tbl_exc:
                    logger.warning("Échec optimisation table %s : %s", tbl, tbl_exc)

        db_manager.clear_cache()
        logger.info("🔧 Optimisation MySQL et purge du cache applicatif terminées")

    except Exception as exc:
        logger.error("Erreur routine optimisation base de données : %s", exc)


def cleanup_database(db_manager):
    """Purge les archives de plus de 3 mois et les comptes inactifs sans historique."""
    try:
        with db_manager.get_cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM archives
                WHERE date_archivage < DATE_SUB(NOW(), INTERVAL 3 MONTH)
                """
            )
            purged_archives = cursor.rowcount
            if purged_archives > 0:
                logger.info("🗑️ %d archives obsolètes supprimées définitivement", purged_archives)

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
        logger.error("Erreur nettoyage base de données : %s", exc, exc_info=True)


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

        log_paths = [LOCAL_LOG_FILE, "/tmp/bot.log", "/tmp/bot_console.log", "/tmp/maintenance_task.log"]
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
        logger.error("Erreur compilation statistiques système : %s", exc)
        return stats


def emergency_cleanup(db_manager=None):
    """Purge immédiate d'urgence en cas de saturation de l'espace disque."""
    try:
        logger.warning("🚨 Déclenchement du protocole de nettoyage d'urgence")

        subprocess.run("rm -rf /tmp/*.log.* 2>/dev/null || true", shell=True)
        subprocess.run("find /tmp -name '*.tmp' -delete 2>/dev/null || true", shell=True)

        log_files = [LOCAL_LOG_FILE, "/tmp/bot.log", "/tmp/bot_console.log", "/tmp/maintenance_task.log"]
        for lp in log_files:
            _truncate_file(lp, keep_lines=100)

        if db_manager:
            cleanup_database(db_manager)

        logger.info("🚨 Nettoyage d'urgence finalisé")

    except Exception as exc:
        logger.error("Erreur nettoyage d'urgence : %s", exc)


def daily_maintenance(db_manager):
    """Point d'entrée de la routine de maintenance quotidienne globale."""
    logger.info("🔧 === Démarrage de la maintenance quotidienne ===")
    try:
        storage_mb = check_storage_usage()

        if storage_mb > 460.0:
            emergency_cleanup(db_manager)
        else:
            cleanup_temp_files()
            archive_old_requests(db_manager)
            cleanup_database(db_manager)
            optimize_database(db_manager)

        stats = get_system_stats(db_manager)
        logger.info("📊 === Rapport de maintenance ===")
        logger.info("💾 Stockage : %.1f Mo (%.1f%%)", stats.get("storage_mb", 0.0), stats.get("storage_percent", 0.0))
        logger.info(
            "📝 Demandes : %s | Archives : %s | Utilisateurs : %s",
            stats.get("demandes_count", 0),
            stats.get("archives_count", 0),
            stats.get("users_count", 0)
        )
        logger.info("✅ === Maintenance terminée avec succès ===")

    except Exception as exc:
        logger.error("Erreur générale routine maintenance : %s", exc, exc_info=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        from config import Config
        from database import DatabaseManager

        cfg = Config()
        db = DatabaseManager(cfg)
        daily_maintenance(db)
    except Exception as main_exc:
        logger.critical("Impossible de démarrer la maintenance autonome : %s", main_exc)