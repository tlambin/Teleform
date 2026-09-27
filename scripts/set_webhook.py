#!/usr/bin/env python3
"""Script de configuration et enregistrement du Webhook Telegram."""

import asyncio
import os
import sys

# Résolution des répertoires : ajout de la racine du projet au PYTHONPATH
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPTS_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from telegram import Bot, Update
from telegram.request import HTTPXRequest
from config import Config

config = Config()
BOT_TOKEN = config.BOT_TOKEN

PYTHONANYWHERE_USERNAME = "paraworld"
WEBHOOK_URL = f"https://{PYTHONANYWHERE_USERNAME}.eu.pythonanywhere.com/{BOT_TOKEN}"

# Secret token partagé avec webhook_app.py
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET")


async def main():
    # Détection et configuration robuste du proxy HTTP pour PythonAnywhere (Cluster EU inclus)
    proxy_url = os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
    if not proxy_url:
        is_pa = any(
            "pythonanywhere" in os.getenv(var, "").lower() 
            for var in ("PYTHONANYWHERE_SITE", "PYTHONANYWHERE_DOMAIN")
        )
        # Détection de secours si exécuté directement dans un terminal bash standard PythonAnywhere
        if is_pa or os.path.exists("/var/log/pythonanywhere.log") or "paraworld" in os.path.expanduser("~"):
            proxy_url = "http://proxy.server:3128"

    request = HTTPXRequest(
        proxy=proxy_url,
        connect_timeout=10.0,
        read_timeout=20.0
    ) if proxy_url else None

    bot = Bot(token=BOT_TOKEN, request=request)

    kwargs = {
        "url": WEBHOOK_URL,
        "allowed_updates": Update.ALL_TYPES,
        "drop_pending_updates": True,
        "max_connections": 40,
    }

    if TELEGRAM_WEBHOOK_SECRET:
        kwargs["secret_token"] = TELEGRAM_WEBHOOK_SECRET
    else:
        print("⚠️ Attention : Aucun TELEGRAM_WEBHOOK_SECRET trouvé dans le .env !")

    async with bot:
        success = await bot.set_webhook(**kwargs)

        if success:
            print(f"✅ Webhook configuré avec succès sur : {WEBHOOK_URL}")
            info = await bot.get_webhook_info()
            print(f"📊 Mises à jour en attente : {info.pending_update_count}")
            print(f"🔗 URL active : {info.url}")
            print(f"🔒 Secret token configuré : {'Oui' if TELEGRAM_WEBHOOK_SECRET else 'Non'}")
            if info.last_error_message:
                print(f"⚠️ Dernier message d'erreur Telegram : {info.last_error_message}")
        else:
            print("❌ Erreur lors de la configuration du webhook.")


if __name__ == "__main__":
    asyncio.run(main())