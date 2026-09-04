#!/usr/bin/env python3
# Configuration timezone Paris
import os
import time
os.environ["TZ"] = "Europe/Paris"
time.tzset()

"""
Tâche unifiée pour PythonAnywhere - Combine maintenance, keep-alive et nettoyage
"""
import sys
import os
import subprocess
import psutil
import logging
from logging.handlers import RotatingFileHandler
import time

# Ajouter le chemin vers votre bot
sys.path.append('/home/paraworld/telegram_bot')

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler(
            '/tmp/maintenance_task.log',
            maxBytes=2*1024*1024,
            backupCount=2
        ),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class UnifiedMaintenance:
    def __init__(self, db_manager=None):
        self.bot_script = '/home/paraworld/telegram_bot/main.py'
        self.maintenance_flag = '/tmp/last_full_maintenance'
        self.db_manager = db_manager

    def is_bot_running(self):
        """Vérifie si le bot est en cours d'exécution avec détection améliorée"""
        try:
            for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time', 'status']):
                cmdline = ' '.join(proc.info['cmdline'] or [])
                # Vérification plus spécifique pour éviter les faux positifs
                if ('main.py' in cmdline and
                    'telegram_bot' in cmdline and
                    'python' in proc.info['name'] and
                    proc.info['status'] == 'running'):
                    return True, proc.info['pid'], proc.info['create_time']
            return False, None, None
        except Exception as e:
            logger.error(f"Erreur vérification processus: {e}")
            return False, None, None

    def start_bot(self):
        """Démarre le bot en arrière-plan"""
        try:
            cmd = f"nohup python3.13 {self.bot_script} > /tmp/bot_output.log 2>&1 &"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

            if result.returncode == 0:
                logger.info("✅ Bot démarré avec succès")
                return True
            else:
                logger.error(f"❌ Erreur démarrage: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"Erreur démarrage bot: {e}")
            return False

    def check_storage_usage(self):
        """Vérifie l'usage du stockage"""
        try:
            result = subprocess.run(['du', '-sb', os.path.expanduser('~')],
                                  capture_output=True, text=True)

            if result.returncode == 0:
                bytes_used = int(result.stdout.split()[0])
                mb_used = bytes_used / (1024 * 1024)
                return mb_used
            return 0
        except Exception as e:
            logger.error(f"Erreur vérification stockage: {e}")
            return 0

    def cleanup_caches(self):
        """Nettoie les caches pour économiser l'espace - NOUVEAU"""
        try:
            logger.info("🧹 Début nettoyage des caches...")

            # Commandes de nettoyage des caches
            cleanup_commands = [
                # Cache pip (souvent le plus volumineux)
                "pip3.13 cache purge 2>/dev/null || true",

                # Cache général (fichiers anciens de plus de 3 jours)
                "find ~/.cache -type f -mtime +3 -delete 2>/dev/null || true",

                # Fichiers Python compilés
                "find ~ -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true",
                "find ~ -name '*.pyc' -delete 2>/dev/null || true",

                # Cache npm/node si présent
                "rm -rf ~/.npm/_cacache 2>/dev/null || true",

                # Logs anciens dans .local
                "find ~/.local -name '*.log' -mtime +7 -delete 2>/dev/null || true",

                # Fichiers temporaires système
                "find /tmp -user $(whoami) -type f -mtime +1 -delete 2>/dev/null || true"
            ]

            space_before = self.check_storage_usage()

            for cmd in cleanup_commands:
                try:
                    subprocess.run(cmd, shell=True, capture_output=True, timeout=30)
                except subprocess.TimeoutExpired:
                    logger.warning(f"Timeout pour: {cmd}")
                except Exception as e:
                    logger.warning(f"Erreur commande {cmd}: {e}")

            space_after = self.check_storage_usage()
            space_freed = space_before - space_after

            logger.info(f"🧹 Nettoyage caches terminé - {space_freed:.1f}MB libérés")

        except Exception as e:
            logger.error(f"Erreur nettoyage caches: {e}")

    def quick_cleanup(self):
        """Nettoyage rapide quotidien - AMÉLIORÉ"""
        try:
            logger.info("🧹 Nettoyage rapide quotidien...")

            # Nettoyer les logs anciens (garde les 3 derniers jours)
            cleanup_commands = [
                "find /tmp -name '*.log' -mtime +3 -delete 2>/dev/null || true",
                "find /tmp -name 'bot_*.log.*' -delete 2>/dev/null || true",
                "find /home/paraworld -name '*.pyc' -delete 2>/dev/null || true",
                "find /home/paraworld -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true"
            ]

            for cmd in cleanup_commands:
                subprocess.run(cmd, shell=True, capture_output=True)

            # Nettoyage léger des caches (fichiers récents seulement)
            light_cache_cleanup = [
                "find ~/.cache -type f -mtime +1 -size +10M -delete 2>/dev/null || true",
                "find /tmp -name '*.tmp' -mtime +0 -delete 2>/dev/null || true"
            ]

            for cmd in light_cache_cleanup:
                subprocess.run(cmd, shell=True, capture_output=True)

            logger.info("🧹 Nettoyage rapide effectué")

        except Exception as e:
            logger.error(f"Erreur nettoyage rapide: {e}")

    def full_maintenance(self):
        """Maintenance complète avec nettoyage approfondi - AMÉLIORÉ"""
        try:
            logger.info("🔧 Début maintenance complète...")

            # Nettoyage approfondi des caches
            self.cleanup_caches()

            # Maintenance de la base de données
            if self.db_manager:
                from utils.maintenance import daily_maintenance
                daily_maintenance(self.db_manager)

            # Marquer la date de dernière maintenance complète
            with open(self.maintenance_flag, 'w') as f:
                f.write(str(time.time()))

            logger.info("🔧 Maintenance complète effectuée")

        except Exception as e:
            logger.error(f"Erreur maintenance complète: {e}")

    def emergency_cleanup(self):
        """Nettoyage d'urgence si stockage critique - NOUVEAU"""
        try:
            logger.warning("🚨 Nettoyage d'urgence activé!")

            # Nettoyage agressif
            emergency_commands = [
                # Vider complètement le cache pip
                "rm -rf ~/.cache/pip/* 2>/dev/null || true",

                # Supprimer tous les fichiers temporaires
                "rm -rf /tmp/*.log.* 2>/dev/null || true",
                "find /tmp -name '*.tmp' -delete 2>/dev/null || true",

                # Nettoyer les caches anciens
                "find ~/.cache -type f -mtime +0 -delete 2>/dev/null || true",

                # Tronquer les logs à 100 lignes
                "tail -n 100 /tmp/bot.log > /tmp/bot.log.tmp && mv /tmp/bot.log.tmp /tmp/bot.log 2>/dev/null || true",
                "tail -n 100 /tmp/bot_console.log > /tmp/bot_console.log.tmp && mv /tmp/bot_console.log.tmp /tmp/bot_console.log 2>/dev/null || true",
                "tail -n 100 /tmp/maintenance_task.log > /tmp/maintenance_task.log.tmp && mv /tmp/maintenance_task.log.tmp /tmp/maintenance_task.log 2>/dev/null || true"
            ]

            for cmd in emergency_commands:
                subprocess.run(cmd, shell=True, capture_output=True)

            # Nettoyage de la base de données
            if self.db_manager:
                from utils.maintenance import cleanup_database
                cleanup_database(self.db_manager)

            logger.warning("🚨 Nettoyage d'urgence terminé")

        except Exception as e:
            logger.error(f"Erreur nettoyage d'urgence: {e}")

    def should_do_full_maintenance(self):
        """Détermine si une maintenance complète est nécessaire"""
        try:
            if not os.path.exists(self.maintenance_flag):
                return True

            with open(self.maintenance_flag, 'r') as f:
                last_maintenance = float(f.read().strip())

            # Maintenance complète toutes les 48 heures
            return time.time() - last_maintenance > 48 * 3600

        except Exception:
            return True

    def run(self):
        """Exécute la maintenance unifiée avec gestion intelligente du stockage"""
        logger.info("🔧 === Maintenance Task PythonAnywhere ===")

        # 1. Vérifier le statut du bot
        running, pid, start_time = self.is_bot_running()

        if running:
            runtime = time.time() - start_time
            hours = int(runtime // 3600)
            minutes = int((runtime % 3600) // 60)
            logger.info(f"✅ Bot actif (PID: {pid}, Runtime: {hours}h{minutes}m)")

            # Redémarrer le bot s'il tourne depuis plus de 12 heures
            if runtime > 12 * 3600:
                logger.info("🔄 Redémarrage préventif du bot (>12h)")
                subprocess.run(['pkill', '-f', 'main.py'], capture_output=True)
                time.sleep(3)
                self.start_bot()
        else:
            logger.warning("⚠️ Bot non actif - Redémarrage...")
            self.start_bot()

        # 2. Vérifier le stockage et décider du type de maintenance
        storage_mb = self.check_storage_usage()
        storage_percent = (storage_mb / 512) * 100

        logger.info(f"💾 Stockage: {storage_mb:.1f}MB ({storage_percent:.1f}%)")

        # 3. Maintenance selon l'usage du stockage
        if storage_percent > 90:  # Critique (>460MB)
            logger.warning("🚨 Stockage critique - Nettoyage d'urgence")
            self.emergency_cleanup()
        elif storage_percent > 75:  # Élevé (>384MB)
            logger.warning("⚠️ Stockage élevé - Maintenance complète forcée")
            self.full_maintenance()
        elif self.should_do_full_maintenance():
            logger.info("🔧 Maintenance complète programmée")
            self.full_maintenance()
        else:
            logger.info("🧹 Nettoyage rapide quotidien")
            self.quick_cleanup()

        # 4. Rapport final avec détails du stockage
        final_running, final_pid, _ = self.is_bot_running()
        final_storage = self.check_storage_usage()
        final_percent = (final_storage / 512) * 100

        # Détail des répertoires les plus volumineux
        try:
            result = subprocess.run(['du', '-sh', '~/.cache', '~/.local', '/tmp', '~/telegram_bot'],
                                  capture_output=True, text=True)
            storage_details = result.stdout if result.returncode == 0 else "N/A"
        except:
            storage_details = "N/A"

        logger.info(f"📊 === Rapport final ===")
        logger.info(f"Bot: {'✅ Actif' if final_running else '❌ Inactif'}")
        logger.info(f"Stockage: {final_storage:.1f}MB ({final_percent:.1f}%)")
        logger.info(f"Détails stockage:\n{storage_details}")
        logger.info(f"=== Maintenance terminée ===")

if __name__ == "__main__":
    try:
        from database import get_db_manager
        db_manager = get_db_manager()
        maintenance = UnifiedMaintenance(db_manager)
        maintenance.run()
    except Exception as e:
        logger.error(f"Erreur critique maintenance: {e}")
        raise