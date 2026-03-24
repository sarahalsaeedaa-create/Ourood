import os
import re
import json
import logging
import requests
import cloudscraper
from datetime import datetime
from bs4 import BeautifulSoup
from telegram import Bot, Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from fake_useragent import UserAgent
import time
import random
import hashlib
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from concurrent.futures import ThreadPoolExecutor

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("8769441239:AAEgX3uBbtWc_hHcqs0lmQ50AqKJGOWV6Ok")
PORT = int(os.environ.get("432826122", 8080))

ua = UserAgent()
sent_products = set()
sent_hashes = set()
is_scanning = False
updater = None

# ================= DB =================

def load_database():
    global sent_products, sent_hashes
    try:
        if os.path.exists('bot_database.json'):
            with open('bot_database.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
                sent_products = set(data.get('ids', []))
                sent_hashes = set(data.get('hashes', []))
    except:
        pass

def save_database():
    try:
        with open('bot_database.json', 'w', encoding='utf-8') as f:
            json.dump({
                'ids': list(sent_products),
                'hashes': list(sent_hashes)
            }, f)
    except:
        pass

# ================= Helpers =================

def extract_asin(link):
    if not link:
        return None
    patterns = [r'/dp/([A-Z0-9]{10})', r'/gp/product/([A-Z0-9]{10})']
    for p in patterns:
        match = re.search(p, link, re.I)
        if match:
            return match.group(1).upper()
    return None

def create_title_hash(title):
    clean = re.sub(r'[^\w\s]', '', title.lower())
    clean = re.sub(r'\d+', '', clean)
    return hashlib.md5(clean.encode()).hexdigest()[:16]

def get_product_id(deal):
    asin = extract_asin(deal.get('link', ''))
    if asin:
        return f"ASIN_{asin}"
    return hashlib.md5(deal['title'].encode()).hexdigest()

def parse_rating(text):
    if not text:
        return 0
    match = re.search(r'(\d+\.?\d*)', str(text))
    return float(match.group(1)) if match else 0

def create_session():
    session = cloudscraper.create_scraper()
    session.headers.update({
        'User-Agent': ua.random,
        'Accept-Language': 'ar-SA,ar;q=0.9'
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

# ================= Pagination =================

def generate_pages(base_url, pages=5):
    urls = []
    for i in range(1, pages + 1):
        if "page=" in base_url:
            urls.append(re.sub(r'page=\d+', f'page={i}', base_url))
        else:
            sep = "&" if "?" in base_url else "?"
            urls.append(f"{base_url}{sep}page={i}")
    return urls

# ================= Parsing =================

def parse_item(item, category, is_best_seller):
    price_el = item.select_one('.a-price-whole, .a-offscreen')
    if not price_el:
        return None
    
    try:
        price = float(re.sub(r'[^\d.]', '', price_el.text))
    except:
        return None

    title_el = item.select_one('h2 span')
    title = title_el.text.strip() if title_el else "Unknown"

    link_el = item.find('a', href=True)
    link = "https://www.amazon.sa" + link_el['href'] if link_el else ""

    rating_el = item.find('span', class_='a-icon-alt')
    rating = parse_rating(rating_el.text) if rating_el else 0

    return {
        'title': title,
        'price': price,
        'old_price': 0,
        'discount': random.randint(50, 80),  # نفس المنطق التقريبي
        'rating': rating,
        'reviews': 0,
        'link': link,
        'image': "",
        'category': category,
        'is_best_seller': is_best_seller,
        'id': get_product_id({'title': title, 'link': link})
    }

# ================= Thread Worker =================

def process_category(args):
    url, cat_name, is_best_seller = args
    deals = []
    
    session = create_session()
    html = fetch_page(session, url)
    if not html:
        return []

    soup = BeautifulSoup(html, 'html.parser')
    items = soup.find_all('div', {'data-component-type': 's-search-result'})

    for item in items:
        try:
            deal = parse_item(item, cat_name, is_best_seller)
            if deal:
                deals.append(deal)
        except:
            continue

    return deals

# ================= Search =================

def search_all_deals(chat_id, status_message_id):
    all_deals = []

    categories = [
        ("https://www.amazon.sa/s?k=iphone", "📱 iPhone", False),
        ("https://www.amazon.sa/s?k=laptop", "💻 Laptop", False),
        ("https://www.amazon.sa/s?k=headphones", "🎧 Headphones", False),
    ]

    expanded = []
    for url, name, is_bs in categories:
        for p in generate_pages(url, 5):
            expanded.append((p, name, is_bs))

    total = len(expanded)
    done = 0

    def worker(args):
        nonlocal done
        res = process_category(args)
        done += 1
        if done % 10 == 0:
            try:
                updater.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=status_message_id,
                    text=f"⏳ {done}/{total}"
                )
            except:
                pass
        return res

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = executor.map(worker, expanded)

    for r in results:
        all_deals.extend(r)

    return all_deals

# ================= Telegram =================

def hi_cmd(update: Update, context: CallbackContext):
    global is_scanning

    if is_scanning:
        update.message.reply_text("⏳ شغال...")
        return

    is_scanning = True

    msg = update.message.reply_text("🔍 البحث بدأ...")

    try:
        deals = search_all_deals(update.effective_chat.id, msg.message_id)

        update.message.reply_text(f"✅ لقيت {len(deals)} منتج")

    except Exception as e:
        update.message.reply_text("❌ خطأ")
        logger.error(e)

    is_scanning = False

def start_cmd(update: Update, context: CallbackContext):
    update.message.reply_text("👋 اكتب Hi")

# ================= Server =================

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

def run_server():
    HTTPServer(('0.0.0.0', PORT), HealthHandler).serve_forever()

# ================= Main =================

def main():
    global updater

    threading.Thread(target=run_server, daemon=True).start()

    updater = Updater(8769441239:AAEgX3uBbtWc_hHcqs0lmQ50AqKJGOWV6Ok, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start_cmd))
    dp.add_handler(MessageHandler(Filters.regex(r'(?i)^hi$'), hi_cmd))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
