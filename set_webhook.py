# set_webhook.py
import asyncio
import os
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
    # Détection et configuration du proxy HTTP obligatoire pour PythonAnywhere (compte gratuit)
    proxy_url = os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
    if not proxy_url and "pythonanywhere" in os.getenv("PYTHONANYWHERE_SITE", ""):
        proxy_url = "http://proxy.server:3128"

    request = HTTPXRequest(proxy=proxy_url) if proxy_url else None
    bot = Bot(token=BOT_TOKEN, request=request)

    kwargs = {
        "url": WEBHOOK_URL,
        "allowed_updates": Update.ALL_TYPES,
        "drop_pending_updates": True,
    }

    if TELEGRAM_WEBHOOK_SECRET:
        kwargs["secret_token"] = TELEGRAM_WEBHOOK_SECRET

    success = await bot.set_webhook(**kwargs)

    if success:
        print(f"✅ Webhook configuré avec succès sur : {WEBHOOK_URL}")
        info = await bot.get_webhook_info()
        print(f"📊 Mises à jour en attente : {info.pending_update_count}")
        print(f"🔗 URL active : {info.url}")
        print(f"🔒 Secret token configuré : {'Oui' if info.has_custom_certificate is not None and TELEGRAM_WEBHOOK_SECRET else 'Non'}")
        if info.last_error_message:
            print(f"⚠️ Dernier message d'erreur Telegram : {info.last_error_message}")
    else:
        print("❌ Erreur lors de la configuration du webhook.")


if __name__ == "__main__":
    asyncio.run(main())