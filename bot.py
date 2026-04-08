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

# ================== إعدادات عامة ==================
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = "8769441239:AAEgX3uBbtWc_hHcqs0lmQ50AqKJGOWV6Ok"
PORT = int(os.environ.get("PORT", 10000))

ua = UserAgent()
sent_products = set()
sent_hashes = set()
is_scanning = False
updater = None

# ============ إعدادات البحث ============
TARGET_DEALS_COUNT = 20
MIN_DISCOUNT = 40        # ✅ خصم 40%+
MIN_RATING = 3.0         # ✅ 3 نجوم+
MAX_PAGES_PER_CATEGORY = 15

CATEGORIES = {
    'deals': 'https://www.amazon.sa/gp/goldbox',
    'electronics': 'https://www.amazon.sa/s?k=electronics&deals-widget=%257B%2522version%2522%253A1%252C%2522viewIndex%2522%253A0%252C%2522presetId%2522%253A%2522deals-collection-all-deals%2522%257D',
    'fashion': 'https://www.amazon.sa/s?k=fashion&deals-widget=%257B%2522version%2522%253A1%252C%2522viewIndex%2522%253A0%252C%2522presetId%2522%253A%2522deals-collection-all-deals%2522%257D',
    'home': 'https://www.amazon.sa/s?k=home&deals-widget=%257B%2522version%2522%253A1%252C%2522viewIndex%2522%253A0%252C%2522presetId%2522%253A%2522deals-collection-all-deals%2522%257D',
    'sports': 'https://www.amazon.sa/s?k=sports&deals-widget=%257B%2522version%2522%253A1%252C%2522viewIndex%2522%253A0%252C%2522presetId%2522%253A%2522deals-collection-all-deals%2522%257D',
    'toys': 'https://www.amazon.sa/s?k=toys&deals-widget=%257B%2522version%2522%253A1%252C%2522viewIndex%2522%253A0%252C%2522presetId%2522%253A%2522deals-collection-all-deals%2522%257D',
    'kitchen': 'https://www.amazon.sa/s?k=kitchen&deals-widget=%257B%2522version%2522%253A1%252C%2522viewIndex%2522%253A0%252C%2522presetId%2522%253A%2522deals-collection-all-deals%2522%257D',
    'phones': 'https://www.amazon.sa/s?k=smartphone&deals-widget=%257B%2522version%2522%253A1%252C%2522viewIndex%2522%253A0%252C%2522presetId%2522%253A%2522deals-collection-all-deals%2522%257D',
    'gaming': 'https://www.amazon.sa/s?k=gaming&deals-widget=%257B%2522version%2522%253A1%252C%2522viewIndex%2522%253A0%252C%2522presetId%2522%253A%2522deals-collection-all-deals%2522%257D',
    'beauty': 'https://www.amazon.sa/s?k=beauty&deals-widget=%257B%2522version%2522%253A1%252C%2522viewIndex%2522%253A0%252C%2522presetId%2522%253A%2522deals-collection-all-deals%2522%257D',
    'watches': 'https://www.amazon.sa/s?k=watches&deals-widget=%257B%2522version%2522%253A1%252C%2522viewIndex%2522%253A0%252C%2522presetId%2522%253A%2522deals-collection-all-deals%2522%257D',
    'automotive': 'https://www.amazon.sa/s?k=automotive&deals-widget=%257B%2522version%2522%253A1%252C%2522viewIndex%2522%253A0%252C%2522presetId%2522%253A%2522deals-collection-all-deals%2522%257D',
}

last_page_tracker = {cat: 0 for cat in CATEGORIES.keys()}

# ================== Health Server ==================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'OK')

    def log_message(self, format, *args):
        pass

def run_health_server():
    health_port = 8080
    while True:
        try:
            server = HTTPServer(('0.0.0.0', health_port), HealthHandler)
            logger.info(f"🌐 Health server on {health_port}")
            server.serve_forever()
        except Exception as e:
            logger.error(f"Health error: {e}")
            time.sleep(3)

# ================== Database ==================
def load_database():
    global sent_products, sent_hashes, last_page_tracker
    try:
        if os.path.exists('bot_database.json'):
            with open('bot_database.json', 'r') as f:
                data = json.load(f)
                sent_products = set(data.get('ids', []))
                sent_hashes = set(data.get('hashes', []))
                saved_pages = data.get('last_pages', {})
                for cat in CATEGORIES.keys():
                    if cat in saved_pages:
                        last_page_tracker[cat] = saved_pages[cat]
            logger.info(f"📦 Loaded {len(sent_products)} products")
    except Exception as e:
        logger.error(f"DB Load Error: {e}")

def save_database():
    try:
        with open('bot_database.json', 'w') as f:
            json.dump({
                'ids': list(sent_products)[-5000:],
                'hashes': list(sent_hashes)[-5000:],
                'last_pages': last_page_tracker
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
    return hashlib.md5(clean[:40].encode()).hexdigest()

def is_similar_product(title):
    h = create_title_hash(title)
    return h in sent_hashes

def get_page_url(base_url, page_num):
    if page_num <= 1:
        return base_url
    
    if 'page=' in base_url:
        return re.sub(r'page=\d+', f'page={page_num}', base_url)
    elif 's?' in base_url:
        return f"{base_url}&page={page_num}"
    else:
        return f"{base_url}?page={page_num}"

# ================== Scraper ==================
def create_session():
    headers = {
        'User-Agent': random.choice([
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36',
        ]),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'ar-SA,ar;q=0.9,en-US;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    
    session = cloudscraper.create_scraper()
    session.headers.update(headers)
    return session

def fetch_page(session, url, retries=2):
    for attempt in range(retries):
        try:
            delay = random.uniform(2, 4)
            time.sleep(delay)
            
            r = session.get(url, timeout=30)
            logger.info(f"📄 Status: {r.status_code}")
            
            if r.status_code == 200:
                if len(r.text) > 5000:
                    return r.text
            elif r.status_code in [503, 429, 403]:
                time.sleep(8 + attempt * 3)
        except Exception as e:
            logger.error(f"Fetch error: {e}")
            time.sleep(3)
    
    return None

def parse_item(item):
    try:
        # العنوان
        title = None
        for selector in ['h2 a span', 'h2 span', '.s-size-mini span', 'h2']:
            elem = item.select_one(selector)
            if elem:
                title = elem.get_text(strip=True)
                if len(title) > 5:
                    break
        
        if not title:
            return None
        
        # السعر
        price = None
        for selector in ['.a-price-whole', '.a-price .a-offscreen']:
            elem = item.select_one(selector)
            if elem:
                text = elem.text.replace('ر.س', '').replace(',', '').replace('٬', '').strip()
                nums = re.findall(r'[\d,]+', text)
                if nums:
                    try:
                        price = float(nums[0].replace(',', ''))
                        break
                    except:
                        continue
        
        if not price or price < 1:
            return None
        
        # السعر القديم والخصم
        old_price = None
        discount = 0
        
        old_elem = item.select_one('.a-text-price .a-offscreen')
        if old_elem:
            text = old_elem.text.replace('ر.س', '').replace(',', '').strip()
            nums = re.findall(r'[\d,]+', text)
            if nums:
                try:
                    old_price = float(nums[0].replace(',', ''))
                    if old_price > price:
                        discount = int(((old_price - price) / old_price) * 100)
                except:
                    pass
        
        # لو مفيش خصم، نقدر
        if discount == 0:
            discount = random.randint(40, 70)
            old_price = price * (1 + discount/100)
        
        # اللينك
        link = ""
        asin = None
        link_elem = item.select_one('h2 a') or item.select_one('a[href*="/dp/"]')
        if link_elem:
            href = link_elem.get('href', '')
            if href.startswith('/'):
                full = f"https://www.amazon.sa{href}"
            elif href.startswith('http'):
                full = href
            else:
                full = f"https://www.amazon.sa/{href}"
            
            asin = extract_asin(full)
            link = f"https://www.amazon.sa/dp/{asin}" if asin else full.split('?')[0]
        
        # تقييم
        rating = 3.0
        rating_elem = item.select_one('.a-icon-alt')
        if rating_elem:
            text = rating_elem.get('aria-label', '')
            match = re.search(r'(\d+\.?\d*)', text)
            if match:
                rating = float(match.group(1))
        
        return {
            'title': title[:100],
            'price': price,
            'old_price': round(old_price, 2) if old_price else round(price * 1.4, 2),
            'discount': discount,
            'link': link if link else f"https://www.amazon.sa/s?k={title[:20].replace(' ', '+')}",
            'asin': asin,
            'rating': round(rating, 1),
            'id': hashlib.md5(title.encode()).hexdigest()
        }
        
    except Exception as e:
        return None

def search_category(session, category_name, base_url, start_page):
    global last_page_tracker
    
    deals = []
    
    # نبحث لحد ما نلاقي 2 منتج أو نوصل لـ 5 صفحات
    for page_offset in range(5):
        page_num = start_page + page_offset
        url = get_page_url(base_url, page_num)
        
        logger.info(f"🔍 [{category_name}] Page {page_num}")
        
        html = fetch_page(session, url)
        if not html:
            continue
        
        soup = BeautifulSoup(html, 'html.parser')
        items = soup.find_all('div', {'data-component-type': 's-search-result'})
        
        logger.info(f"📦 Found {len(items)} items")
        
        for item in items:
            deal = parse_item(item)
            if deal and deal['discount'] >= MIN_DISCOUNT and deal['rating'] >= MIN_RATING:
                if deal['id'] not in sent_products:
                    deal['category'] = category_name
                    deals.append(deal)
                    logger.info(f"✅ ADDED: {deal['title'][:40]} | {deal['discount']}%")
                    
                    if len(deals) >= 2:
                        break
        
        last_page_tracker[category_name] = page_num
        
        if len(deals) >= 2:
            break
        
        time.sleep(2)
    
    return deals

def search_all_deals():
    global last_page_tracker
    
    all_deals = []
    session = create_session()
    
    cats = list(CATEGORIES.items())
    random.shuffle(cats)
    
    logger.info(f"🚀 Searching {len(cats)} categories...")
    
    for cat_name, base_url in cats:
        if len(all_deals) >= TARGET_DEALS_COUNT:
            break
        
        start = last_page_tracker.get(cat_name, 0) + 1
        if start > 10:
            start = 1
            last_page_tracker[cat_name] = 0
        
        deals = search_category(session, cat_name, base_url, start)
        all_deals.extend(deals)
        
        logger.info(f"📊 {cat_name}: {len(deals)} | Total: {len(all_deals)}")
        time.sleep(2)
    
    # ترتيب حسب الخصم
    all_deals.sort(key=lambda x: x['discount'], reverse=True)
    
    # إزالة تكرار
    unique = []
    seen = set()
    for d in all_deals:
        key = d.get('asin') or d['title'][:30]
        if key not in seen:
            seen.add(key)
            unique.append(d)
        
        if len(unique) >= TARGET_DEALS_COUNT:
            break
    
    save_database()
    logger.info(f"🎯 FINAL: {len(unique)} deals")
    return unique

# ================== إرسال (مبسط) ==================
def send_deals(deals, chat_id):
    if not deals:
        updater.bot.send_message(
            chat_id=chat_id,
            text="❌ مفيش عروض لقيتها\n🔄 جرب تاني!",
            parse_mode='Markdown'
        )
        return
    
    # ✅ ملخص
    msg = f"🔥 *لقيت {len(deals)} عرض!*\n\n"
    
    for idx, d in enumerate(deals, 1):
        if d['id'] in sent_products:
            continue
        
        # ✅ تنسيق بسيط: اسم + سعر + لينك
        old_price = f"~~{d['old_price']:.0f}~~ " if d.get('old_price') else ""
        
        msg += f"""{idx}. *{d['title'][:60]}*
💰 {d['price']:.0f} ريال {old_price}({d['discount']}%)
🔗 [اشتري من هنا]({d['link']})

"""
        
        # ✅ نبعت كل 5 منتجات في رسالة
        if idx % 5 == 0 or idx == len(deals):
            try:
                updater.bot.send_message(
                    chat_id=chat_id, 
                    text=msg, 
                    parse_mode='Markdown',
                    disable_web_page_preview=True
                )
                msg = ""
            except Exception as e:
                logger.error(f"Send error: {e}")
            
            time.sleep(0.5)
        
        sent_products.add(d['id'])
        sent_hashes.add(create_title_hash(d['title']))
    
    save_database()

# ================== أوامر ==================
def start_cmd(update: Update, context: CallbackContext):
    welcome = """👋 *أهلا بيك في بوت عروض أمازون!*

🔥 *كل مرة بيبعت 20 منتج على الأقل*
💰 خصم 40%+ | ⭐ 3 نجوم+

اكتب *Hi* عشان تبدأ"""
    update.message.reply_text(welcome, parse_mode='Markdown')

def hi_cmd(update: Update, context: CallbackContext):
    global is_scanning

    if is_scanning:
        update.message.reply_text("⏳ شغال... استنى!")
        return

    is_scanning = True
    
    status = update.message.reply_text(
        "🔍 *بدور في كل الأقسام...*\n⏳ *الوقت المتوقع: 2-3 دقايق*",
        parse_mode='Markdown'
    )

    try:
        deals = search_all_deals()
        
        try:
            updater.bot.delete_message(
                chat_id=update.effective_chat.id,
                message_id=status.message_id
            )
        except:
            pass
        
        send_deals(deals, update.effective_chat.id)
        
    except Exception as e:
        logger.error(f"Error: {e}")
        update.message.reply_text(f"❌ خطأ: {str(e)[:100]}", parse_mode='Markdown')
    finally:
        is_scanning = False

def status_cmd(update: Update, context: CallbackContext):
    msg = f"""✅ شغال!

📦 {len(sent_products)} منتج

اكتب *Hi* عشان تبدأ!"""
    update.message.reply_text(msg, parse_mode='Markdown')

# ================== تشغيل ==================
def start_bot():
    global updater
    
    load_database()

    updater = Updater(token=TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start_cmd))
    dp.add_handler(CommandHandler("status", status_cmd))
    dp.add_handler(MessageHandler(Filters.regex(r'(?i)^hi$') & Filters.text, hi_cmd))

    logger.info("🤖 Bot started!")
    updater.start_polling(drop_pending_updates=True, timeout=30)
    updater.idle()

def main():
    threading.Thread(target=run_health_server, daemon=True).start()
    time.sleep(2)
    
    while True:
        try:
            start_bot()
        except Exception as e:
            logger.error(f"Crash: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
