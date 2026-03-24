import os
import re
import json
import logging
import cloudscraper
from datetime import datetime
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from fake_useragent import UserAgent
import time
import random
import hashlib
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from concurrent.futures import ThreadPoolExecutor

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# 🔥 حطي التوكن هنا
TELEGRAM_BOT_TOKEN = "8769441239:AAEgX3uBbtWc_hHcqs0lmQ50AqKJGOWV6Ok"

PORT = int(os.environ.get("PORT", 8080))

ua = UserAgent()
sent_products = set()
sent_hashes = set()
is_scanning = False
updater = None

# ================= DB =================

def load_database():
    global sent_products, sent_hashes
    if os.path.exists('bot_database.json'):
        with open('bot_database.json', 'r') as f:
            data = json.load(f)
            sent_products = set(data.get('ids', []))
            sent_hashes = set(data.get('hashes', []))

def save_database():
    with open('bot_database.json', 'w') as f:
        json.dump({
            'ids': list(sent_products),
            'hashes': list(sent_hashes)
        }, f)

# ================= Helpers =================

def create_session():
    session = cloudscraper.create_scraper()
    session.headers.update({
        'User-Agent': ua.random
    })
    return session

def fetch_page(session, url):
    try:
        time.sleep(random.uniform(0.3, 0.8))
        r = session.get(url, timeout=20)
        if r.status_code == 200:
            return r.text
    except:
        pass
    return None

def generate_pages(base_url, pages=5):
    urls = []
    for i in range(1, pages + 1):
        sep = "&" if "?" in base_url else "?"
        urls.append(f"{base_url}{sep}page={i}")
    return urls

def parse_item(item, category):
    try:
        title = item.select_one("h2 span").text.strip()
        price_el = item.select_one(".a-offscreen")
        price = float(re.sub(r"[^\d.]", "", price_el.text))

        link = "https://www.amazon.sa" + item.select_one("a")["href"]

        return {
            "title": title,
            "price": price,
            "category": category,
            "link": link,
            "id": hashlib.md5(title.encode()).hexdigest()
        }
    except:
        return None

# ================= Thread Worker =================

def process_category(args):
    url, name = args
    deals = []

    session = create_session()
    html = fetch_page(session, url)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    items = soup.find_all("div", {"data-component-type": "s-search-result"})

    for item in items:
        deal = parse_item(item, name)
        if deal:
            deals.append(deal)

    return deals

# ================= Search =================

def search_all_deals(chat_id, msg_id):
    categories = [
        ("https://www.amazon.sa/s?k=iphone", "📱 iPhone"),
        ("https://www.amazon.sa/s?k=laptop", "💻 Laptop"),
        ("https://www.amazon.sa/s?k=headphones", "🎧 Headphones"),
    ]

    expanded = []
    for url, name in categories:
        expanded.extend([(p, name) for p in generate_pages(url, 5)])

    results = []

    def worker(args):
        return process_category(args)

    with ThreadPoolExecutor(max_workers=10) as executor:
        for res in executor.map(worker, expanded):
            results.extend(res)

    return results

# ================= Telegram =================

def start_cmd(update: Update, context: CallbackContext):
    update.message.reply_text("👋 اكتب Hi لبدء البحث")

def hi_cmd(update: Update, context: CallbackContext):
    global is_scanning

    if is_scanning:
        update.message.reply_text("⏳ شغال...")
        return

    is_scanning = True
    msg = update.message.reply_text("🔍 جاري البحث...")

    deals = search_all_deals(update.effective_chat.id, msg.message_id)

    update.message.reply_text(f"✅ تم العثور على {len(deals)} منتج")

    is_scanning = False

# ================= Health =================

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_server():
    HTTPServer(("0.0.0.0", PORT), HealthHandler).serve_forever()

# ================= Main =================

def main():
    global updater

    threading.Thread(target=run_server, daemon=True).start()

    updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start_cmd))
    dp.add_handler(MessageHandler(Filters.regex(r'(?i)^hi$'), hi_cmd))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
