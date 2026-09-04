#!/usr/bin/env python3
import sys
import subprocess
import psutil
import time
import os

def get_bot_status():
    """Récupère le statut du bot"""
    try:
        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
            cmdline = ' '.join(proc.info['cmdline'] or [])
            if ('main.py' in cmdline and
                'telegram_bot' in cmdline and
                'python' in proc.info['name']):
                runtime = time.time() - proc.info['create_time']
                return {
                    'running': True,
                    'pid': proc.info['pid'],
                    'runtime': runtime
                }
        return {'running': False}
    except Exception as e:
        return {'error': str(e)}

def start_bot():
    """Démarre le bot directement avec Python"""
    try:
        # Vérifier si le bot est déjà en cours
        if get_bot_status()['running']:
            print("⚠️ Bot déjà en cours d'exécution")
            return

        # Démarrer le bot directement
        bot_script = '/home/paraworld/telegram_bot/main.py'

        # Utiliser Popen pour démarrer en arrière-plan
        process = subprocess.Popen([
            'nohup',
            'python3.13',
            bot_script
        ],
        stdout=open('/tmp/bot_output.log', 'w'),
        stderr=subprocess.STDOUT,
        cwd='/home/paraworld/telegram_bot',
        preexec_fn=os.setsid  # Créer un nouveau groupe de processus
        )

        print(f"✅ Bot démarré avec PID: {process.pid}")

        # Attendre un peu pour vérifier que le démarrage s'est bien passé
        time.sleep(3)

        # Vérifier le statut
        status = get_bot_status()
        if status['running']:
            print("🎯 Bot opérationnel")
        else:
            print("⚠️ Le bot pourrait avoir des problèmes - Vérifiez les logs")

    except Exception as e:
        print(f"❌ Erreur démarrage: {e}")

def stop_bot():
    """Arrête le bot"""
    try:
        result = subprocess.run(['pkill', '-f', 'main.py'], capture_output=True)
        if result.returncode == 0:
            print("✅ Bot arrêté")
        else:
            print("⚠️ Aucun bot en cours ou déjà arrêté")
    except Exception as e:
        print(f"❌ Erreur arrêt: {e}")

def restart_bot():
    """Redémarre le bot"""
    print("🔄 Redémarrage du bot...")
    stop_bot()
    time.sleep(5)
    start_bot()

def show_status():
    """Affiche le statut détaillé"""
    status = get_bot_status()

    if status.get('running'):
        runtime = status['runtime']
        hours = int(runtime // 3600)
        minutes = int((runtime % 3600) // 60)

        print(f"✅ Bot actif")
        print(f"📊 PID: {status['pid']}")
        print(f"⏰ Runtime: {hours}h {minutes}m")
    elif status.get('error'):
        print(f"❌ Erreur: {status['error']}")
    else:
        print("❌ Bot non actif")

def main():
    if len(sys.argv) < 2:
        print("Usage: python3.13 manage_bot.py [start|stop|restart|status]")
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
        print("Commande invalide. Utilisez: start, stop, restart, ou status")

if __name__ == "__main__":
    main()
