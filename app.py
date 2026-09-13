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
from email.utils import parsedate_to_datetime

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN non impostato!")

application = Application.builder().token(BOT_TOKEN).build()

# Feed RSS
RSS_SERIE_A = "https://www.gazzetta.it/dynamic-feed/rss/section/Calcio/Serie-A.xml"
RSS_CALCIOMERCATO = "https://www.gazzetta.it/dynamic-feed/rss/section/Calciomercato.xml"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; MilanNewsBot/1.0)"}
MAX_TITLE_LEN = 120
FILTER_KEYWORD = "Milan"

def clean_title(text: str) -> str:
    text = " ".join(text.split())
    if len(text) > MAX_TITLE_LEN:
        text = text[:MAX_TITLE_LEN].rsplit(" ", 1)[0] + "…"
    return text

def format_date(pub_date: str) -> str:
    try:
        dt = parsedate_to_datetime(pub_date)
        return dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return pub_date[:16] if pub_date else ""

async def fetch_news(rss_url: str, limit: int = 5):
    """Funzione generica per recuperare notizie da un feed RSS."""
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers=HEADERS) as client:
        resp = await client.get(rss_url)
        resp.raise_for_status()
        feed_content = resp.text

    feed = feedparser.parse(feed_content)
    articles = []

    for entry in feed.entries:
        title = entry.get("title", "")
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
    await update.message.reply_text(
        "Ciao! Sono il bot del Milan.\n"
        "Usa /notizie per le ultime notizie generali.\n"
        "Usa /mercato per le ultime notizie di calciomercato."
    )

async def notizie(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("⏳ Recupero le ultime notizie...")
    try:
        articles = await fetch_news(RSS_SERIE_A, limit=5)
        if not articles:
            await update.message.reply_text("⚠️ Nessuna notizia sul Milan trovata al momento. Riprova più tardi.")
            return
        await send_articles(update, articles, "Ultime notizie dal Milan (Serie A)")
    except Exception as e:
        logger.error(f"Errore recupero notizie: {e}")
        await update.message.reply_text("❌ Errore nel recupero delle notizie. Riprova più tardi.")

async def mercato(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("⏳ Recupero le ultime notizie di calciomercato...")
    try:
        articles = await fetch_news(RSS_CALCIOMERCATO, limit=5)
        if not articles:
            await update.message.reply_text("⚠️ Nessuna notizia di calciomercato sul Milan trovata al momento. Riprova più tardi.")
            return
        await send_articles(update, articles, "Ultime notizie di calciomercato (Milan)")
    except Exception as e:
        logger.error(f"Errore recupero notizie di mercato: {e}")
        await update.message.reply_text("❌ Errore nel recupero delle notizie. Riprova più tardi.")

async def send_articles(update: Update, articles: list, header: str) -> None:
    """Invia la lista di articoli formattata."""
    blocks = [f"<b>⚽️ {header}</b>"]
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

application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("notizie", notizie))
application.add_handler(CommandHandler("mercato", mercato))

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
