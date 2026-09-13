import os
import logging
import html
import httpx
import feedparser
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

# Feed RSS della Gazzetta dello Sport - Serie A
RSS_URL = "https://www.gazzetta.it/dynamic-feed/rss/section/Calcio/Serie-A.xml"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; MilanNewsBot/1.0)"}
MAX_TITLE_LEN = 120
FILTER_KEYWORD = "Milan"

def clean_title(text: str) -> str:
    text = " ".join(text.split())
    if len(text) > MAX_TITLE_LEN:
        text = text[:MAX_TITLE_LEN].rsplit(" ", 1)[0] + "…"
    return text

def format_date(pub_date: str) -> str:
    """Formatta la data RSS in modo leggibile."""
    # Esempio: "Mon, 13 Oct 2025 10:59:09 +0200"
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(pub_date)
        return dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return pub_date[:16] if pub_date else ""

async def fetch_gazzetta_news(limit=5):
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers=HEADERS) as client:
        resp = await client.get(RSS_URL)
        resp.raise_for_status()
        feed_content = resp.text

    feed = feedparser.parse(feed_content)
    articles = []

    for entry in feed.entries:
        title = entry.get("title", "")
        # Filtra solo articoli che contengono "Milan" nel titolo
        if FILTER_KEYWORD.lower() not in title.lower():
            continue

        title = clean_title(title)
        link = entry.get("link", "#")
        pub = format_date(entry.get("published", ""))

        articles.append({
            "title": title,
            "url": link,
            "date": pub,
            "author": entry.get("author", ""),
        })

        if len(articles) >= limit:
            break

    return articles

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Ciao! Sono il bot del Milan. Usa /notizie per le ultime.")

async def notizie(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("⏳ Recupero le ultime notizie...")
    try:
        articles = await fetch_gazzetta_news(limit=5)
        if not articles:
            await update.message.reply_text("⚠️ Nessuna notizia sul Milan trovata al momento. Riprova più tardi.")
            return

        blocks = ["<b>⚽️ Ultime notizie dal Milan (Gazzetta)</b>"]
        for i, art in enumerate(articles, 1):
            title = html.escape(art["title"])
            url = html.escape(art["url"], quote=True)
            block = f'{i}. <a href="{url}">{title}</a>'

            refs = []
            if art["date"]:
                refs.append(f'📅 {html.escape(art["date"])}')
            if art["author"]:
                refs.append(f'✍️ {html.escape(art["author"])}')
            if refs:
                block += "\n" + "  ·  ".join(refs)

            blocks.append(block)

        await update.message.reply_text(
            "\n\n".join(blocks),
            parse_mode="HTML",
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
