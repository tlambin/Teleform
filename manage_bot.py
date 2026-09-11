#!/usr/bin/env python3
"""Script d'administration et de supervision du bot en mode Webhook / uWSGI."""

import datetime
import json
import os
import subprocess
import sys
import urllib.request
from config import Config

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WSGI_FILE = "/var/www/paraworld_eu_pythonanywhere_com_wsgi.py"
ERROR_LOG = "/var/log/paraworld.eu.pythonanywhere.com.error.log"
SERVER_LOG = "/var/log/paraworld.eu.pythonanywhere.com.server.log"


def get_configured_opener():
    """Crée un opener urllib configuré avec le proxy de PythonAnywhere si nécessaire."""
    proxy_url = os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
    if not proxy_url and "pythonanywhere" in os.getenv("PYTHONANYWHERE_SITE", ""):
        proxy_url = "http://proxy.server:3128"

    if proxy_url:
        proxy_handler = urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
        return urllib.request.build_opener(proxy_handler)
    return urllib.request.build_opener()


def check_webhook_status():
    """Interroge l'API Telegram pour connaître la santé du Webhook."""
    try:
        config = Config()
        url = f"https://api.telegram.org/bot{config.BOT_TOKEN}/getWebhookInfo"
        opener = get_configured_opener()
        req = urllib.request.Request(url, headers={"User-Agent": "TeleformBotAdmin/1.0"})

        with opener.open(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))

        if not data.get("ok"):
            print("❌ Erreur API Telegram :", data)
            return

        res = data["result"]
        print("🌐 === Statut Webhook Telegram ===")
        print(f"URL enregistrée : {res.get('url') or 'Aucune (mode polling)'}")
        print(f"Certificat personnalisé : {res.get('has_custom_certificate', False)}")
        print(f"Mises à jour en attente : {res.get('pending_update_count', 0)}")

        last_err_date = res.get("last_error_date")
        if last_err_date:
            dt = datetime.datetime.fromtimestamp(last_err_date)
            print(f"⚠️ Dernière erreur ({dt}) : {res.get('last_error_message')}")
        else:
            print("✅ Aucune erreur récente signalée par Telegram.")

    except Exception as exc:
        print(f"❌ Impossible de joindre l'API Telegram : {exc}")


def reload_app():
    """Déclenche le redémarrage à chaud de l'application uWSGI."""
    if os.path.exists(WSGI_FILE):
        try:
            os.utime(WSGI_FILE, None)
            print("🔄 Application Web rechargée avec succès (signal WSGI envoyé).")
        except Exception as exc:
            print(f"❌ Erreur lors du rechargement WSGI : {exc}")
    else:
        print("⚠️ Fichier WSGI introuvable. Utilisez le bouton 'Reload' sur l'interface PythonAnywhere.")


def view_logs(log_type: str = "error", lines: int = 30):
    """Consulte les logs du serveur uWSGI."""
    path = ERROR_LOG if log_type == "error" else SERVER_LOG
    if not os.path.exists(path):
        print(f"⚠️ Fichier log introuvable : {path}")
        return

    cmd = ["tail", f"-n{lines}", path]
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        pass


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.executable} manage_bot.py [status|reload|logs-error|logs-server]")
        return

    action = sys.argv[1].lower()
    if action == "status":
        check_webhook_status()
    elif action == "reload":
        reload_app()
    elif action == "logs-error":
        view_logs("error", lines=35)
    elif action == "logs-server":
        view_logs("server", lines=35)
    else:
        print(f"❌ Commande '{action}' inconnue.")
        print("Commandes valides : status, reload, logs-error, logs-server")


if __name__ == "__main__":
    main()