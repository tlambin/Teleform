#!/usr/bin/env python3
"""Tâche planifiée PythonAnywhere : maintenance, keep-alive et surveillance disque."""

import logging
from logging.handlers import RotatingFileHandler
import os
import signal
import subprocess
import sys
import time
from typing import Optional, Tuple
import psutil

# Configuration du fuseau horaire
os.environ["TZ"] = "Europe/Paris"
if hasattr(time, "tzset"):
    time.tzset()

# Résolution dynamique des chemins
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

MAIN_SCRIPT = os.path.join(BASE_DIR, "main.py")
LOG_FILE = "/tmp/maintenance_task.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        RotatingFileHandler(LOG_FILE, maxBytes=2 * 1024 * 1024, backupCount=2),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("MaintenanceTask")


class UnifiedMaintenance:
    """Gestionnaire autonome de supervision du processus bot et d'optimisation stockage."""

    def __init__(self, db_manager=None):
        self.bot_script = MAIN_SCRIPT
        self.maintenance_flag = "/tmp/last_full_maintenance"
        self.db_manager = db_manager

    def is_bot_running(self) -> Tuple[bool, Optional[int], Optional[float]]:
        """Contrôle si le bot Telegram est en cours d'exécution."""
        try:
            current_pid = os.getpid()
            for proc in psutil.process_iter(["pid", "name", "cmdline", "create_time", "status"]):
                try:
                    if proc.info["pid"] == current_pid:
                        continue

                    # Évite les processus zombies
                    if proc.info.get("status") == psutil.STATUS_ZOMBIE:
                        continue

                    cmdline = " ".join(proc.info.get("cmdline") or [])
                    if self.bot_script in cmdline or ("main.py" in cmdline and BASE_DIR in cmdline):
                        return True, proc.info["pid"], proc.info["create_time"]
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue

            return False, None, None
        except Exception as exc:
            logger.error("Erreur inspection processus: %s", exc)
            return False, None, None

    def start_bot(self) -> bool:
        """Relance le bot en arrière-plan via sys.executable."""
        try:
            log_dest = "/tmp/bot_output.log"
            cmd = f"nohup {sys.executable} {self.bot_script} >> {log_dest} 2>&1 &"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

            if result.returncode == 0:
                logger.info("✅ Bot relancé avec succès.")
                return True

            logger.error("❌ Échec relance bot : %s", result.stderr)
            return False
        except Exception as exc:
            logger.error("Exception lors du démarrage du bot : %s", exc)
            return False

    def check_storage_usage(self) -> float:
        """Calcule l'espace disque consommé dans le répertoire utilisateur (Mo)."""
        try:
            home = os.path.expanduser("~")
            res = subprocess.run(["du", "-sb", home], capture_output=True, text=True)
            if res.returncode == 0:
                bytes_used = int(res.stdout.split()[0])
                return round(bytes_used / (1024 * 1024), 2)
            return 0.0
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
        """Routine quotidienne de purge légère."""
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
        """Maintenance complète (caches + SQL)."""
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
                if os.path.exists(lp):
                    subprocess.run(f"tail -n 100 {lp} > {lp}.tmp && mv {lp}.tmp {lp}", shell=True)

            if self.db_manager:
                from utils.maintenance import cleanup_database
                cleanup_database(self.db_manager)

            logger.warning("🚨 Nettoyage d'urgence terminé.")
        except Exception as exc:
            logger.error("Erreur nettoyage urgence : %s", exc)

    def should_do_full_maintenance(self) -> bool:
        """Détermine si la maintenance de 48 heures est due."""
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
        logger.info("🔧 === Exécution tâche planifiée PythonAnywhere ===")

        # 1. Vérification keep-alive du bot
        running, pid, start_time = self.is_bot_running()

        if running:
            runtime = time.time() - (start_time or time.time())
            hours = int(runtime // 3600)
            minutes = int((runtime % 3600) // 60)
            logger.info("✅ Bot actif (PID: %s, Uptime: %dh%02dm)", pid, hours, minutes)

            # Redémarrage préventif si le bot tourne en continu depuis plus de 24h
            if runtime > 24 * 3600:
                logger.info("🔄 Redémarrage préventif (> 24h d'activité)...")
                try:
                    os.kill(pid, signal.SIGTERM)
                    time.sleep(3)
                except Exception as k_err:
                    logger.warning("Échec arrêt gracieux : %s", k_err)
                self.start_bot()
        else:
            logger.warning("⚠️ Bot arrêté — Lancement immédiat...")
            self.start_bot()

        # 2. Gestion de l'espace disque
        storage_mb = self.check_storage_usage()
        storage_percent = (storage_mb / 512.0) * 100.0
        logger.info("💾 Disque utilisé : %.1f Mo / 512 Mo (%.1f%%)", storage_mb, storage_percent)

        if storage_percent > 90.0:
            self.emergency_cleanup()
        elif storage_percent > 75.0 or self.should_do_full_maintenance():
            self.full_maintenance()
        else:
            self.quick_cleanup()

        # 3. Rapport d'inspection des répertoires
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

        final_running, final_pid, _ = self.is_bot_running()
        logger.info("📊 === Bilan de tâche planifiée ===")
        logger.info("Statut bot : %s (PID %s)", "🟢 En ligne" if final_running else "🔴 Hors ligne", final_pid)
        logger.info("Volumes consommés :\n%s", details)
        logger.info("✅ Tâche planifiée terminée.")


if __name__ == "__main__":
    try:
        from config import Config
        from database import DatabaseManager

        cfg = Config()
        db = DatabaseManager(cfg)
        task = UnifiedMaintenance(db)
        task.run()
    except Exception as fatal_exc:
        logger.critical("Échec critique lors de l'exécution de la maintenance planifiée : %s", fatal_exc, exc_info=True)
        sys.exit(1)