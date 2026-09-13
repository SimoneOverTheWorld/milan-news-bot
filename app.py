import os
import logging
import httpx
from bs4 import BeautifulSoup
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

HOMEPAGE_URL = "https://www.pianetamilan.it/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; MilanNewsBot/1.0)"}

async def fetch_homepage_news(limit=5):
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers=HEADERS) as client:
        resp = await client.get(HOMEPAGE_URL)
        resp.raise_for_status()
        html = resp.text

    soup = BeautifulSoup(html, "html.parser")
    articles = []
    seen = set()

    # Strategia 1: tag <article>
    for art in soup.find_all("article"):
        a = art.find("a", href=True)
        if not a:
            continue
        title = a.get_text(strip=True)
        href = a["href"]
        if not title or len(title) < 20 or href in seen:
            continue
        seen.add(href)
        articles.append({"title": title, "url": href})
        if len(articles) >= limit:
            break

    # Strategia 2 (fallback): h2/h3 con link
    if len(articles) < limit:
        for h in soup.find_all(["h2", "h3"]):
            a = h.find("a", href=True)
            if not a:
                continue
            title = a.get_text(strip=True)
            href = a["href"]
            if not title or len(title) < 20 or href in seen:
                continue
            seen.add(href)
            articles.append({"title": title, "url": href})
            if len(articles) >= limit:
                break

    return articles

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Ciao! Sono il bot del Milan. Usa /notizie per le ultime.")

async def notizie(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("⏳ Recupero le ultime notizie...")
    try:
        articles = await fetch_homepage_news(limit=5)
        if not articles:
            await update.message.reply_text("⚠️ Nessuna notizia trovata. Riprova più tardi.")
            return

        lines = ["⚽️ *Ultime notizie dal Milan:*\n"]
        for i, art in enumerate(articles, 1):
            lines.append(f"{i}. [{art['title']}]({art['url']})")

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
