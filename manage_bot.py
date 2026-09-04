#!/usr/bin/env python3
"""Script d'administration et de supervision du processus Telegram Bot."""

import logging
import os
import signal
import subprocess
import sys
import time
from typing import Any, Dict
import psutil

# Détection dynamique de l'emplacement du projet
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MAIN_SCRIPT = os.path.join(BASE_DIR, "main.py")
LOG_FILE = "/tmp/bot_output.log"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("ManageBot")


def get_bot_status() -> Dict[str, Any]:
    """Détecte si le processus du bot est en cours d'exécution."""
    try:
        current_pid = os.getpid()
        for proc in psutil.process_iter(["pid", "name", "cmdline", "create_time"]):
            try:
                if proc.info["pid"] == current_pid:
                    continue

                cmdline_list = proc.info.get("cmdline") or []
                cmdline = " ".join(cmdline_list)

                # Identification précise du script main.py du projet
                if MAIN_SCRIPT in cmdline or ("main.py" in cmdline and BASE_DIR in cmdline):
                    runtime = time.time() - proc.info["create_time"]
                    return {
                        "running": True,
                        "pid": proc.info["pid"],
                        "runtime": runtime,
                    }
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        return {"running": False}
    except Exception as exc:
        return {"running": False, "error": str(exc)}


def start_bot():
    """Démarre le bot en arrière-plan avec redirection des flux."""
    status = get_bot_status()
    if status.get("running"):
        print(f"⚠️ Le bot tourne déjà avec le PID {status['pid']}.")
        return

    if not os.path.exists(MAIN_SCRIPT):
        print(f"❌ Fichier d'entrée introuvable : {MAIN_SCRIPT}")
        return

    try:
        with open(LOG_FILE, "a", encoding="utf-8") as out_file:
            process = subprocess.Popen(
                [sys.executable, MAIN_SCRIPT],
                stdout=out_file,
                stderr=subprocess.STDOUT,
                cwd=BASE_DIR,
                preexec_fn=os.setsid,  # Isole le processus dans sa propre session
            )

        print(f"🚀 Bot démarré avec le PID : {process.pid}")
        print(f"📝 Logs dirigés vers : {LOG_FILE}")

        time.sleep(3)
        verify = get_bot_status()
        if verify.get("running"):
            print("✅ Bot actif et opérationnel.")
        else:
            print("⚠️ Échec potentiel lors du démarrage. Consultez les logs :")
            print(f"   tail -n 20 {LOG_FILE}")

    except Exception as exc:
        print(f"❌ Erreur lors du lancement : {exc}")


def stop_bot():
    """Arrête proprement le processus du bot par SIGTERM puis SIGKILL si nécessaire."""
    status = get_bot_status()
    if not status.get("running"):
        print("⚠️ Aucun processus du bot n'est actuellement en cours.")
        return

    pid = status["pid"]
    print(f"🛑 Arrêt du bot (PID {pid})...")

    try:
        os.kill(pid, signal.SIGTERM)
        for _ in range(10):
            time.sleep(0.5)
            if not psutil.pid_exists(pid):
                print("✅ Bot arrêté avec succès.")
                return

        # Forçage si le processus ne répond pas au signal d'arrêt gracieux
        print("⚠️ Le processus ne répond pas, envoi de SIGKILL...")
        os.kill(pid, signal.SIGKILL)
        time.sleep(1)
        print("✅ Processus arrêté de force.")

    except ProcessLookupError:
        print("✅ Le bot était déjà arrêté.")
    except Exception as exc:
        print(f"❌ Impossible d'arrêter le processus {pid} : {exc}")


def restart_bot():
    """Effectue un arrêt complet puis un démarrage."""
    print("🔄 Redémarrage du bot en cours...")
    stop_bot()
    time.sleep(2)
    start_bot()


def show_status():
    """Affiche un récapitulatif textuel de l'état du bot."""
    status = get_bot_status()

    if status.get("running"):
        runtime = status["runtime"]
        hours = int(runtime // 3600)
        minutes = int((runtime % 3600) // 60)
        seconds = int(runtime % 60)

        print("🟢 Statut : EN COURS D'EXÉCUTION")
        print(f"📊 PID    : {status['pid']}")
        print(f"⏰ Uptime : {hours}h {minutes}m {seconds}s")
    elif status.get("error"):
        print(f"❌ Erreur lors de l'inspection des processus : {status['error']}")
    else:
        print("🔴 Statut : ARRÊTÉ")


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.executable} manage_bot.py [start|stop|restart|status]")
        return

    command = sys.argv[1].lower()
    if command == "start":
        start_bot()
    elif command == "stop":
        stop_bot()
    elif command == "restart":
        restart_bot()
    elif command == "status":
        show_status()
    else:
        print(f"❌ Commande '{command}' non reconnue.")
        print("Commandes valides : start, stop, restart, status")


if __name__ == "__main__":
    main()