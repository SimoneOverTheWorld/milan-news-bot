import os
import logging
import html
import re
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
MAX_TITLE_LEN = 120

def clean_title(text: str) -> str:
    text = " ".join(text.split())
    if len(text) > MAX_TITLE_LEN:
        text = text[:MAX_TITLE_LEN].rsplit(" ", 1)[0] + "…"
    return text

def extract_date(art) -> str:
    """Cerca una data dentro la card dell'articolo."""
    # 1) Tag <time> (standard)
    t = art.find("time")
    if t:
        txt = t.get_text(strip=True)
        if txt:
            return " ".join(txt.split())
        dt = t.get("datetime")
        if dt:
            return dt[:16].replace("T", " ")
    # 2) Fallback: cerca pattern "13 settembre - 07:30" nel testo
    text = art.get_text(" ", strip=True)
    m = re.search(
        r"\d{1,2}\s+(gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre)(?:\s*-\s*\d{1,2}:\d{2})?",
        text, re.IGNORECASE
    )
    return m.group(0) if m else ""

def extract_author(art) -> str:
    """Cerca l'autore dentro la card dell'articolo."""
    # Prova classi comuni
    for cls in ["author", "byline", "autore", "entry-author", "post-author"]:
        el = art.find(class_=re.compile(cls, re.IGNORECASE))
        if el:
            txt = " ".join(el.get_text(" ", strip=True).split())
            if txt and len(txt) < 60:
                return txt
    return ""

async def fetch_homepage_news(limit=5):
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers=HEADERS) as client:
        resp = await client.get(HOMEPAGE_URL)
        resp.raise_for_status()
        html_text = resp.text

    soup = BeautifulSoup(html_text, "html.parser")
    articles = []
    seen = set()

    for art in soup.find_all("article"):
        a = art.find("a", href=True)
        if not a:
            continue

        # Titolo: prova h1/h2/h3 dentro l'articolo, fallback al testo del link
        title_el = art.find(["h1", "h2", "h3"])
        title = clean_title((title_el or a).get_text(strip=True))
        if not title or len(title) < 20:
            continue

        href = a["href"]
        if href.startswith("/"):
            href = HOMEPAGE_URL.rstrip("/") + href
        if not href.startswith("http") or href in seen:
            continue

        date_str = extract_date(art)
        author = extract_author(art)

        seen.add(href)
        articles.append({
            "title": title,
            "url": href,
            "date": date_str,
            "author": author,
        })
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

        blocks = ["<b>⚽️ Ultime notizie dal Milan</b>"]
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
