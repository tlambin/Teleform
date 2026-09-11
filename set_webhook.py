import asyncio
from telegram import Bot, Update
from config import Config

config = Config()
BOT_TOKEN = config.BOT_TOKEN

PYTHONANYWHERE_USERNAME = "paraworld"
WEBHOOK_URL = f"https://{PYTHONANYWHERE_USERNAME}.eu.pythonanywhere.com/{BOT_TOKEN}"


async def main():
    bot = Bot(token=BOT_TOKEN)

    # Réception de tous les types d'updates (messages, callbacks, paiements Stars)
    success = await bot.set_webhook(
        url=WEBHOOK_URL,
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )

    if success:
        print(f"✅ Webhook configuré avec succès sur : {WEBHOOK_URL}")
        info = await bot.get_webhook_info()
        print(f"📊 Mises à jour en attente : {info.pending_update_count}")
        print(f"🔗 URL active : {info.url}")
    else:
        print("❌ Erreur lors de la configuration du webhook.")


if __name__ == "__main__":
    asyncio.run(main())