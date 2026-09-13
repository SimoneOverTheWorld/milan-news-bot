import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
import uvicorn

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN non impostato!")

application = Application.builder().token(BOT_TOKEN).build()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Ciao! Sono il bot del Milan. Usa /notizie per le ultime.")

async def notizie(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("⚽ Ultime notizie dal Milan:\n1. Il Milan vince il derby!\n2. Nuovo acquisto a centrocampo.\n3. Prossima partita domenica ore 20:45.")

application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("notizie", notizie))

async def telegram_webhook(request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return PlainTextResponse("OK")

async def healthcheck(request):
    return PlainTextResponse("OK")

routes = [
    Route("/telegram", telegram_webhook, methods=["POST"]),
    Route("/healthcheck", healthcheck, methods=["GET"]),
]

web_app = Starlette(routes=routes)

async def main():
    await application.initialize()
    config = uvicorn.Config(web_app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())