import os
import logging
import httpx
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

NEWS_API_URL = "https://freenewsapi.ai/v1/search?host=www.pianetamilan.it&size=5"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Ciao! Sono il bot del Milan. Usa /notizie per le ultime.")

async def notizie(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("⏳ Recupero le ultime notizie...")
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(NEWS_API_URL)
            resp.raise_for_status()
            data = resp.json()

        articles = data.get("results", [])
        if not articles:
            await update.message.reply_text("⚠️ Nessuna notizia trovata al momento. Riprova più tardi.")
            return

        lines = ["⚽️ *Ultime notizie dal Milan:*\n"]
        for i, art in enumerate(articles, 1):
            title = art.get("title", "Titolo non disponibile")
            url = art.get("url", "#")
            pub = art.get("published_at", "")
            if pub:
                pub = pub[:16].replace("T", " ")  # "2026-08-25 21:53"
            lines.append(f"{i}. [{title}]({url})")
            if pub:
                lines.append(f"   🕐 {pub} UTC")

        await update.message.reply_text(
            "\n".join(lines),
            parse_mode="Markdown",
            disable_web_page_preview=True
        )

    except Exception as e:
        logger.error(f"Errore recupero notizie: {e}")
        await update.message.reply_text("❌ Errore nel recupero delle notizie. Riprova più tardi.")

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
