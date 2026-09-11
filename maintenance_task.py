#!/usr/bin/env python3
"""Tâche planifiée PythonAnywhere : maintenance stockage et optimisation base de données."""

import logging
from logging.handlers import RotatingFileHandler
import os
import shutil
import subprocess
import sys
import time

# Configuration du fuseau horaire
os.environ["TZ"] = "Europe/Paris"
if hasattr(time, "tzset"):
    time.tzset()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

LOG_FILE = "/tmp/maintenance_task.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        RotatingFileHandler(LOG_FILE, maxBytes=2 * 1024 * 1024, backupCount=2, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("MaintenanceTask")


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


class UnifiedMaintenance:
    """Gestionnaire d'optimisation stockage et d'entretien base de données."""

    def __init__(self, db_manager=None):
        self.maintenance_flag = "/tmp/last_full_maintenance"
        self.db_manager = db_manager

    def check_storage_usage(self) -> float:
        """Calcule l'espace disque consommé dans le répertoire utilisateur (Mo)."""
        home = os.path.expanduser("~")
        try:
            res = subprocess.run(["du", "-sk", home], capture_output=True, text=True)
            if res.returncode == 0:
                kb_used = int(res.stdout.split()[0])
                return round(kb_used / 1024.0, 2)
        except Exception:
            pass

        try:
            usage = shutil.disk_usage(home)
            mb_used = (usage.total - usage.free) / (1024 * 1024)
            return round(mb_used, 2)
        except Exception as exc:
            logger.error("Erreur mesure disque : %s", exc)
            return 0.0

    def cleanup_caches(self):
        """Purge approfondie des caches applicatifs et fichiers temporaires."""
        try:
            logger.info("🧹 Purge des caches en cours...")
            home = os.path.expanduser("~")

            commands = [
                f"{sys.executable} -m pip cache purge 2>/dev/null || true",
                f"find {home}/.cache -type f -mtime +3 -delete 2>/dev/null || true",
                f"find {home} -name '__pycache__' -type d -exec rm -rf {{}} + 2>/dev/null || true",
                f"find {home} -name '*.pyc' -delete 2>/dev/null || true",
                f"find {home}/.local -name '*.log' -mtime +7 -delete 2>/dev/null || true",
                "find /tmp -user $(whoami) -type f -mtime +1 -delete 2>/dev/null || true",
            ]

            before = self.check_storage_usage()
            for cmd in commands:
                try:
                    subprocess.run(cmd, shell=True, capture_output=True, timeout=30)
                except subprocess.TimeoutExpired:
                    logger.warning("Timeout sur commande : %s", cmd)

            after = self.check_storage_usage()
            logger.info("🧹 Caches nettoyés : %.1f Mo libérés.", max(0.0, before - after))
        except Exception as exc:
            logger.error("Erreur nettoyage caches : %s", exc)

    def quick_cleanup(self):
        """Routine de purge légère."""
        try:
            home = os.path.expanduser("~")
            commands = [
                "find /tmp -name '*.log' -mtime +3 -delete 2>/dev/null || true",
                "find /tmp -name '*.tmp' -delete 2>/dev/null || true",
                f"find {home} -name '*.pyc' -delete 2>/dev/null || true",
                f"find {home} -name '__pycache__' -type d -exec rm -rf {{}} + 2>/dev/null || true",
            ]
            for cmd in commands:
                subprocess.run(cmd, shell=True, capture_output=True)
            logger.info("🧹 Nettoyage rapide effectué.")
        except Exception as exc:
            logger.error("Erreur nettoyage rapide : %s", exc)

    def full_maintenance(self):
        """Maintenance complète (stockage + SQL)."""
        try:
            logger.info("🔧 Exécution maintenance complète...")
            self.cleanup_caches()

            if self.db_manager:
                from utils.maintenance import daily_maintenance
                daily_maintenance(self.db_manager)

            with open(self.maintenance_flag, "w", encoding="utf-8") as f:
                f.write(str(time.time()))

            logger.info("🔧 Maintenance complète finalisée.")
        except Exception as exc:
            logger.error("Erreur maintenance complète : %s", exc)

    def emergency_cleanup(self):
        """Nettoyage d'urgence lors d'une saturation de l'espace disque (>90%)."""
        try:
            logger.warning("🚨 Nettoyage d'urgence déclenché !")
            home = os.path.expanduser("~")

            emergency_commands = [
                f"rm -rf {home}/.cache/pip/* 2>/dev/null || true",
                "rm -rf /tmp/*.log.* 2>/dev/null || true",
                "find /tmp -name '*.tmp' -delete 2>/dev/null || true",
                f"find {home}/.cache -type f -mtime +0 -delete 2>/dev/null || true",
            ]
            for cmd in emergency_commands:
                subprocess.run(cmd, shell=True, capture_output=True)

            log_files = ["/tmp/bot.log", "/tmp/bot_output.log", LOG_FILE]
            for lp in log_files:
                _truncate_file(lp, keep_lines=100)

            if self.db_manager:
                from utils.maintenance import cleanup_database
                cleanup_database(self.db_manager)

            logger.warning("🚨 Nettoyage d'urgence terminé.")
        except Exception as exc:
            logger.error("Erreur nettoyage urgence : %s", exc)

    def should_do_full_maintenance(self) -> bool:
        """Vérifie si la maintenance de 48 heures est due."""
        if not os.path.exists(self.maintenance_flag):
            return True
        try:
            with open(self.maintenance_flag, "r", encoding="utf-8") as f:
                last_maint = float(f.read().strip())
            return (time.time() - last_maint) > (48 * 3600)
        except Exception:
            return True

    def run(self):
        """Cycle principal d'exécution."""
        logger.info("🔧 === Exécution tâche planifiée de maintenance ===")

        # Gestion de l'espace disque
        storage_mb = self.check_storage_usage()
        storage_percent = (storage_mb / 512.0) * 100.0
        logger.info("💾 Disque utilisé : %.1f Mo / 512 Mo (%.1f%%)", storage_mb, storage_percent)

        if storage_percent > 90.0:
            self.emergency_cleanup()
        elif storage_percent > 75.0 or self.should_do_full_maintenance():
            self.full_maintenance()
        else:
            self.quick_cleanup()

        # Rapport des répertoires
        home = os.path.expanduser("~")
        inspect_dirs = [
            os.path.join(home, ".cache"),
            os.path.join(home, ".local"),
            "/tmp",
            BASE_DIR,
        ]
        valid_dirs = [d for d in inspect_dirs if os.path.exists(d)]
        du_res = subprocess.run(["du", "-sh"] + valid_dirs, capture_output=True, text=True)
        details = du_res.stdout.strip() if du_res.returncode == 0 else "N/A"

        logger.info("📊 Volumes consommés :\n%s", details)
        logger.info("✅ Tâche de maintenance terminée avec succès.")


if __name__ == "__main__":
    db = None
    try:
        from config import Config
        from database import DatabaseManager

        cfg = Config()
        # pool_size=1 pour ne pas saturer le quota de connexions MySQL
        db = DatabaseManager(cfg, pool_size=1)
        task = UnifiedMaintenance(db)
        task.run()
    except Exception as fatal_exc:
        logger.critical("Échec critique maintenance : %s", fatal_exc, exc_info=True)
        sys.exit(1)
    finally:
        if db and hasattr(db, "close"):
            try:
                db.close()
            except Exception:
                pass