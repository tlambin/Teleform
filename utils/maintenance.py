"""Module de maintenance quotidienne, nettoyage des fichiers temporaires et archivage SQL.

Optimisé pour l'exécution asynchrone non-bloquante sous python-telegram-bot.
"""

import asyncio
import logging
import os
import shutil
import subprocess
from typing import Dict

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_LOG_FILE = os.path.join(BASE_DIR, "logs", "bot.log")


def _truncate_file_sync(file_path: str, keep_lines: int = 1000):
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


async def _truncate_file(file_path: str, keep_lines: int = 1000):
    """Version asynchrone non-bloquante du tronquage de fichier."""
    await asyncio.to_thread(_truncate_file_sync, file_path, keep_lines)


async def cleanup_temp_files():
    """Purge les fichiers temporaires, tronque les logs et nettoie le cache bytecode sans bloquer l'Event Loop."""
    try:
        log_files = [
            LOCAL_LOG_FILE,
            "/tmp/bot.log",
            "/tmp/bot_console.log",
            "/tmp/maintenance_task.log"
        ]
        for log_path in log_files:
            await _truncate_file(log_path, keep_lines=1000)

        home_dir = os.path.expanduser("~")
        cleanup_commands = [
            f"find {home_dir} -name '*.pyc' -delete 2>/dev/null || true",
            f"find {home_dir} -name '__pycache__' -type d -exec rm -rf {{}} + 2>/dev/null || true",
            "find /tmp -name 'core.*' -delete 2>/dev/null || true",
            "find /tmp -name '*.tmp' -delete 2>/dev/null || true",
        ]

        for cmd in cleanup_commands:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            await proc.communicate()

        logger.info("🧹 Nettoyage des fichiers temporaires terminé (async)")

    except Exception as exc:
        logger.error("Erreur nettoyage fichiers temporaires : %s", exc)


def _archive_old_requests_sync(db_manager):
    """Archive les demandes anciennes avec transaction atomique sécurisée et purge des suivis."""
    try:
        hours_setting = db_manager.get_auto_archive_hours() if hasattr(db_manager, "get_auto_archive_hours") else 72

        with db_manager.transaction() as cursor:
            cursor.execute(
                """
                SELECT id FROM demandes
                WHERE (
                    statut = '✅ Réussie' 
                    AND reussie_substatus = 'terminee' 
                    AND has_delivered_content = TRUE 
                    AND date_livraison <= DATE_SUB(NOW(), INTERVAL %s HOUR)
                ) OR (
                    statut = '❌ Abandonnée' 
                    AND date_modification <= DATE_SUB(NOW(), INTERVAL 7 DAY)
                )
                """,
                (hours_setting,)
            )
            rows = cursor.fetchall()
            if not rows:
                logger.info("📦 Aucune demande prête pour l'archivage automatique")
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


async def archive_old_requests(db_manager):
    """Version non-bloquante de l'archivage SQL."""
    await asyncio.to_thread(_archive_old_requests_sync, db_manager)


def _check_storage_usage_sync() -> float:
    """Calcul synchrone d'espace disque consommé."""
    home = os.path.expanduser("~")
    try:
        res = subprocess.run(["du", "-sk", home], capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            kb_used = int(res.stdout.split()[0])
            mb_used = kb_used / 1024.0
            return round(mb_used, 2)
    except Exception:
        pass

    try:
        usage = shutil.disk_usage(home)
        mb_used = (usage.total - usage.free) / (1024 * 1024)
        return round(mb_used, 2)
    except Exception as exc:
        logger.error("Erreur calcul espace disque synchrone : %s", exc)
        return 0.0


async def check_storage_usage() -> float:
    """Retourne l'espace disque consommé dans le répertoire utilisateur en Mo sans bloquer l'Event Loop."""
    home = os.path.expanduser("~")
    try:
        proc = await asyncio.create_subprocess_exec(
            "du", "-sk", home,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()

        if proc.returncode == 0 and stdout:
            kb_used = int(stdout.decode().split()[0])
            mb_used = kb_used / 1024.0

            if mb_used > 400.0:
                logger.warning("⚠️ Espace disque critique : %.1f Mo / 512 Mo", mb_used)
                await cleanup_temp_files()

            return round(mb_used, 2)
    except Exception:
        pass

    try:
        usage = await asyncio.to_thread(shutil.disk_usage, home)
        mb_used = (usage.total - usage.free) / (1024 * 1024)
        return round(mb_used, 2)
    except Exception as exc:
        logger.error("Erreur calcul espace disque (async) : %s", exc)
        return 0.0


def _optimize_database_sync(db_manager):
    """Exécute OPTIMIZE TABLE de façon synchrone."""
    try:
        tables = [
            "demandes", "demandes_suivi", "archives",
            "users", "admins", "staff", "admin_preferences", "config"
        ]
        with db_manager.get_cursor() as cursor:
            for tbl in tables:
                try:
                    cursor.execute(f"OPTIMIZE TABLE `{tbl}`")
                except Exception as tbl_exc:
                    logger.warning("Échec optimisation table %s : %s", tbl, tbl_exc)

        db_manager.clear_cache()
        logger.info("🔧 Optimisation MySQL et purge du cache applicatif terminées")

    except Exception as exc:
        logger.error("Erreur routine optimisation base de données : %s", exc)


async def optimize_database(db_manager):
    """Version non-bloquante d'optimisation des tables MySQL."""
    await asyncio.to_thread(_optimize_database_sync, db_manager)


def _cleanup_database_sync(db_manager):
    """Purge synchrone des archives obsolètes et utilisateurs orphelins."""
    try:
        with db_manager.transaction() as cursor:
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


async def cleanup_database(db_manager):
    """Version non-bloquante du nettoyage SQL."""
    await asyncio.to_thread(_cleanup_database_sync, db_manager)


def _get_system_stats_sync(db_manager, mb_used: float) -> Dict:
    """Compilation des métriques en thread dédié."""
    stats = {
        "storage_mb": mb_used,
        "storage_percent": (mb_used / 512.0) * 100.0,
    }
    try:
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
            row = cursor.fetchone()
            stats["demandes_count"] = row["count"] if row else 0

            cursor.execute("SELECT COUNT(*) AS count FROM archives")
            row = cursor.fetchone()
            stats["archives_count"] = row["count"] if row else 0

            cursor.execute("SELECT COUNT(*) AS count FROM users")
            row = cursor.fetchone()
            stats["users_count"] = row["count"] if row else 0

            cursor.execute("SELECT COUNT(*) AS count FROM staff")
            row = cursor.fetchone()
            stats["staff_count"] = row["count"] if row else 0

            cursor.execute("SELECT COUNT(*) AS count FROM admins")
            row = cursor.fetchone()
            stats["admins_count"] = row["count"] if row else 0

        return stats
    except Exception as exc:
        logger.error("Erreur compilation statistiques système : %s", exc)
        return stats


async def get_system_stats(db_manager) -> Dict:
    """Retourne les métriques techniques agrégées sans bloquer la boucle événementielle."""
    mb_used = await check_storage_usage()
    return await asyncio.to_thread(_get_system_stats_sync, db_manager, mb_used)


async def emergency_cleanup(db_manager=None):
    """Purge immédiate d'urgence en cas de saturation de l'espace disque."""
    try:
        logger.warning("🚨 Déclenchement du protocole de nettoyage d'urgence")

        p1 = await asyncio.create_subprocess_shell("rm -rf /tmp/*.log.* 2>/dev/null || true")
        await p1.communicate()

        p2 = await asyncio.create_subprocess_shell("find /tmp -name '*.tmp' -delete 2>/dev/null || true")
        await p2.communicate()

        log_files = [LOCAL_LOG_FILE, "/tmp/bot.log", "/tmp/bot_console.log", "/tmp/maintenance_task.log"]
        for lp in log_files:
            await _truncate_file(lp, keep_lines=100)

        if db_manager:
            await cleanup_database(db_manager)

        logger.info("🚨 Nettoyage d'urgence finalisé")

    except Exception as exc:
        logger.error("Erreur nettoyage d'urgence : %s", exc)


async def daily_maintenance(db_manager):
    """Point d'entrée principal de la routine de maintenance quotidienne non-bloquante."""
    logger.info("🔧 === Démarrage de la maintenance quotidienne (async) ===")
    try:
        storage_mb = await check_storage_usage()

        if storage_mb > 460.0:
            await emergency_cleanup(db_manager)
        else:
            await cleanup_temp_files()
            await archive_old_requests(db_manager)
            await cleanup_database(db_manager)
            await optimize_database(db_manager)

        stats = await get_system_stats(db_manager)
        logger.info("📊 === Rapport de maintenance ===")
        logger.info("💾 Stockage : %.1f Mo (%.1f%%)", stats.get("storage_mb", 0.0), stats.get("storage_percent", 0.0))
        logger.info(
            "📝 Demandes : %s | Archives : %s | Utilisateurs : %s | Staff : %s | Admins : %s",
            stats.get("demandes_count", 0),
            stats.get("archives_count", 0),
            stats.get("users_count", 0),
            stats.get("staff_count", 0),
            stats.get("admins_count", 0)
        )
        logger.info("✅ === Maintenance terminée avec succès ===")

    except Exception as exc:
        logger.error("Erreur générale routine maintenance : %s", exc, exc_info=True)


# ==================== UTILITAIRES DE SECOURS SYNCHRONES (CLI / CRON) ====================

def daily_maintenance_sync(db_manager):
    """Exécute la routine de maintenance de manière synchrone (pour les cronjobs hors boucle événementielle)."""
    asyncio.run(daily_maintenance(db_manager))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        from config import Config
        from database import DatabaseManager

        cfg = Config()
        db = DatabaseManager(cfg)
        daily_maintenance_sync(db)
    except Exception as main_exc:
        logger.critical("Impossible de démarrer la maintenance autonome : %s", main_exc)