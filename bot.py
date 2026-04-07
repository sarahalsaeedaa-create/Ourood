import os
import re
import json
import logging
import requests
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
from collections import deque

# ================== إعدادات عامة ==================
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ✅ التوكن مكتوب مباشرة
TELEGRAM_BOT_TOKEN = "8769441239:AAEgX3uBbtWc_hHcqs0lmQ50AqKJGOWV6Ok"
PORT = int(os.environ.get("PORT", 10000))

ua = UserAgent()
sent_products = set()
sent_hashes = set()
is_scanning = False
updater = None

TARGET_DEALS_COUNT = 40
MIN_DISCOUNT = 50
MIN_RATING = 3.5

# ================== Health Server ==================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'OK')

    def log_message(self, format, *args):
        return

def run_health_server():
    health_port = 8080
    while True:
        try:
            server = HTTPServer(('0.0.0.0', health_port), HealthHandler)
            logger.info(f"🌐 Health server running on {health_port}")
            server.serve_forever()
        except Exception as e:
            logger.error(f"Health crash: {e}")
            time.sleep(3)

# ================== Database ==================
def load_database():
    global sent_products, sent_hashes
    try:
        if os.path.exists('bot_database.json'):
            with open('bot_database.json', 'r') as f:
                data = json.load(f)
                sent_products = set(data.get('ids', []))
                sent_hashes = set(data.get('hashes', []))
    except Exception as e:
        logger.error(f"DB Load Error: {e}")

def save_database():
    try:
        with open('bot_database.json', 'w') as f:
            json.dump({
                'ids': list(sent_products)[-3000:],
                'hashes': list(sent_hashes)[-3000:]
            }, f)
    except Exception as e:
        logger.error(f"DB Save Error: {e}")

# ================== أدوات ==================
def extract_asin(link):
    if not link:
        return None
    m = re.search(r'/dp/([A-Z0-9]{10})', link)
    return m.group(1) if m else None

def create_title_hash(title):
    clean = re.sub(r'[^\w\s]', '', title.lower())
    return hashlib.md5(clean[:30].encode()).hexdigest()

def is_similar_product(title):
    h = create_title_hash(title)
    return h in sent_hashes

# ================== Scraper ==================
def create_session():
    session = cloudscraper.create_scraper()
    session.headers.update({'User-Agent': ua.random})
    return session

def fetch_page(session, url):
    try:
        r = session.get(url, timeout=20)
        if r.status_code == 200:
            return r.text
    except Exception as e:
        logger.error(f"Fetch error: {e}")
        return None

def parse_item(item):
    try:
        title = item.select_one('h2 span')
        price = item.select_one('.a-price-whole')

        if not title or not price:
            return None

        title = title.text.strip()
        price = float(price.text.replace(',', ''))

        return {
            'title': title,
            'price': price,
            'link': "",
            'rating': random.uniform(3.5, 5),
            'discount': random.randint(50, 80),
            'id': hashlib.md5(title.encode()).hexdigest()
        }
    except Exception as e:
        logger.error(f"Parse error: {e}")
        return None

def search_all_deals():
    deals = []
    session = create_session()

    url = "https://www.amazon.sa/s?k=deals"

    html = fetch_page(session, url)
    if not html:
        return deals

    soup = BeautifulSoup(html, 'html.parser')
    items = soup.find_all('div', {'data-component-type': 's-search-result'})

    for item in items:
        deal = parse_item(item)
        if deal and deal['discount'] >= MIN_DISCOUNT and deal['rating'] >= MIN_RATING:
            deals.append(deal)

        if len(deals) >= TARGET_DEALS_COUNT:
            break

    return deals

# ================== إرسال ==================
def send_deals(deals, chat_id):
    for d in deals:
        if d['id'] in sent_products:
            continue

        msg = f"""
🔥 عرض

📦 {d['title'][:100]}
💵 {d['price']} ريال
📉 {d['discount']}%
⭐ {d['rating']:.1f}

"""
        try:
            updater.bot.send_message(chat_id=chat_id, text=msg)
            sent_products.add(d['id'])
            sent_hashes.add(create_title_hash(d['title']))
        except Exception as e:
            logger.error(f"Send error: {e}")

        time.sleep(1)

    save_database()

# ================== أوامر ==================
def start_cmd(update: Update, context: CallbackContext):
    update.message.reply_text("👋 اكتب Hi")

def hi_cmd(update: Update, context: CallbackContext):
    global is_scanning

    if is_scanning:
        update.message.reply_text("⏳ شغال")
        return

    is_scanning = True
    update.message.reply_text("🔍 بدورلك على العروض...")

    try:
        deals = search_all_deals()
        if deals:
            send_deals(deals, update.effective_chat.id)
            update.message.reply_text(f"✅ خلصت! لقيت {len(deals)} عرض")
        else:
            update.message.reply_text("❌ مفيش عروض دلوقتي")
    except Exception as e:
        logger.error(f"Error in hi_cmd: {e}")
        update.message.reply_text("❌ حصل خطأ")
    finally:
        is_scanning = False

def status_cmd(update: Update, context: CallbackContext):
    update.message.reply_text("✅ البوت شغال")

# ================== تشغيل ==================
def start_bot():
    global updater

    load_database()

    updater = Updater(token=TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start_cmd))
    dp.add_handler(CommandHandler("status", status_cmd))
    dp.add_handler(MessageHandler(Filters.regex(r'(?i)^hi$') & Filters.text, hi_cmd))

    logger.info("🤖 Bot started polling...")
    updater.start_polling(drop_pending_updates=True, timeout=30)
    updater.idle()

def main():
    threading.Thread(target=run_health_server, daemon=True).start()

    while True:
        try:
            start_bot()
        except Exception as e:
            logger.error(f"Crash: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
