import os
import logging
import html
import json
import httpx
import feedparser
from pathlib import Path
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, ContextTypes
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from email.utils import parsedate_to_datetime

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
# IMPORTANTE: Aggiungi questa variabile d'ambiente su Render
CHAT_ID = os.environ.get("CHAT_ID")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN non impostato!")
if not CHAT_ID:
    raise ValueError("CHAT_ID non impostato! Aggiungilo come variabile d'ambiente su Render.")

application = Application.builder().token(BOT_TOKEN).build()
bot = application.bot

# Feed RSS
RSS_FEEDS = {
    "serie_a": "https://www.gazzetta.it/dynamic-feed/rss/section/Calcio/Serie-A.xml",
    "calciomercato": "https://www.gazzetta.it/dynamic-feed/rss/section/Calciomercato.xml",
}

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; MilanNewsBot/1.0)"}
MAX_TITLE_LEN = 120
FILTER_KEYWORD = "Milan"

# File per tenere traccia degli articoli già inviati
SEEN_FILE = Path("seen_articles.json")

def load_seen():
    if SEEN_FILE.exists():
        try:
            return json.loads(SEEN_FILE.read_text())
        except Exception:
            return {}
    return {}

def save_seen(seen):
    SEEN_FILE.write_text(json.dumps(seen, indent=2))

seen_articles = load_seen()

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

async def send_articles(bot: Bot, chat_id: str, articles: list, header: str) -> None:
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

    await bot.send_message(
        chat_id=chat_id,
        text="\n\n".join(blocks),
        parse_mode="HTML",
        disable_web_page_preview=True
    )

# --- Job per il controllo automatico delle notizie ---
async def check_for_new_news():
    logger.info("Controllo nuove notizie in corso...")
    new_articles_found = False

    for feed_name, feed_url in RSS_FEEDS.items():
        try:
            articles = await fetch_news(feed_url, limit=10)
        except Exception as e:
            logger.error(f"Errore nel recupero del feed {feed_name}: {e}")
            continue

        feed_seen = seen_articles.get(feed_url, [])
        new_articles = []

        for art in articles:
            if art["url"] not in feed_seen:
                new_articles.append(art)
                feed_seen.append(art["url"])

        if new_articles:
            new_articles_found = True
            header = "Nuove notizie dal Milan" if feed_name == "serie_a" else "Nuove notizie di calciomercato"
            await send_articles(bot, CHAT_ID, new_articles, header)
            logger.info(f"Inviate {len(new_articles)} nuove notizie da {feed_name}")

        seen_articles[feed_url] = feed_seen

    if new_articles_found:
        save_seen(seen_articles)
    else:
        logger.info("Nessuna nuova notizia trovata.")

# --- Comandi ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Ciao! Sono il bot del Milan.\n"
        "Usa /notizie per le ultime notizie generali.\n"
        "Usa /mercato per le ultime notizie di calciomercato.\n\n"
        "⏰ Invierò automaticamente le nuove notizie non appena vengono pubblicate!"
    )

async def notizie(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("⏳ Recupero le ultime notizie...")
    try:
        articles = await fetch_news(RSS_FEEDS["serie_a"], limit=5)
        if not articles:
            await update.message.reply_text("⚠️ Nessuna notizia sul Milan trovata al momento. Riprova più tardi.")
            return
        await send_articles(context.bot, update.effective_chat.id, articles, "Ultime notizie dal Milan (Serie A)")
    except Exception as e:
        logger.error(f"Errore recupero notizie: {e}")
        await update.message.reply_text("❌ Errore nel recupero delle notizie. Riprova più tardi.")

async def mercato(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("⏳ Recupero le ultime notizie di calciomercato...")
    try:
        articles = await fetch_news(RSS_FEEDS["calciomercato"], limit=5)
        if not articles:
            await update.message.reply_text("⚠️ Nessuna notizia di calciomercato sul Milan trovata al momento. Riprova più tardi.")
            return
        await send_articles(context.bot, update.effective_chat.id, articles, "Ultime notizie di calciomercato (Milan)")
    except Exception as e:
        logger.error(f"Errore recupero notizie di mercato: {e}")
        await update.message.reply_text("❌ Errore nel recupero delle notizie. Riprova più tardi.")

application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("notizie", notizie))
application.add_handler(CommandHandler("mercato", mercato))

# --- Webhook e Scheduler ---
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
    await application.start()

    # Avvia lo scheduler per il controllo automatico
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        check_for_new_news,
        'interval',
        minutes=10,  # Controlla ogni 10 minuti
        id='news_checker',
        replace_existing=True
    )
    scheduler.start()
    logger.info("Scheduler avviato: controllo nuove notizie ogni 10 minuti.")

    config = uvicorn.Config(web_app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
