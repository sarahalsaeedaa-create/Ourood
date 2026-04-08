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
from urllib.parse import urljoin, quote

# ================== إعدادات عامة ==================
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = "8769441239:AAEgX3uBbtWc_hHcqs0lmQ50AqKJGOWV6Ok"

# ✅ مهم: استخدم PORT اللي Render بيديه
PORT = int(os.environ.get("PORT", 10000))

ua = UserAgent()
sent_products = set()
sent_hashes = set()
is_scanning = False
updater = None

# ============ إعدادات البحث ============
TARGET_DEALS_COUNT = 20
MIN_DISCOUNT = 50
MIN_RATING = 3.0
MAX_PAGES_PER_CATEGORY = 20

CATEGORIES = {
    'electronics': 'https://www.amazon.sa/s?k=electronics&deals-widget=%257B%2522version%2522%253A1%252C%2522viewIndex%2522%253A0%252C%2522presetId%2522%253A%2522deals-collection-all-deals%2522%257D&s=price-asc-rank',
    'fashion': 'https://www.amazon.sa/s?k=fashion&deals-widget=%257B%2522version%2522%253A1%252C%2522viewIndex%2522%253A0%252C%2522presetId%2522%253A%2522deals-collection-all-deals%2522%257D&s=price-asc-rank',
    'home': 'https://www.amazon.sa/s?k=home&deals-widget=%257B%2522version%2522%253A1%252C%2522viewIndex%2522%253A0%252C%2522presetId%2522%253A%2522deals-collection-all-deals%2522%257D&s=price-asc-rank',
    'beauty': 'https://www.amazon.sa/s?k=beauty&deals-widget=%257B%2522version%2522%253A1%252C%2522viewIndex%2522%253A0%252C%2522presetId%2522%253A%2522deals-collection-all-deals%2522%257D&s=price-asc-rank',
    'sports': 'https://www.amazon.sa/s?k=sports&deals-widget=%257B%2522version%2522%253A1%252C%2522viewIndex%2522%253A0%252C%2522presetId%2522%253A%2522deals-collection-all-deals%2522%257D&s=price-asc-rank',
    'toys': 'https://www.amazon.sa/s?k=toys&deals-widget=%257B%2522version%2522%253A1%252C%2522viewIndex%2522%253A0%252C%2522presetId%2522%253A%2522deals-collection-all-deals%2522%257D&s=price-asc-rank',
    'kitchen': 'https://www.amazon.sa/s?k=kitchen&deals-widget=%257B%2522version%2522%253A1%252C%2522viewIndex%2522%253A0%252C%2522presetId%2522%253A%2522deals-collection-all-deals%2522%257D&s=price-asc-rank',
    'phones': 'https://www.amazon.sa/s?k=smartphones&deals-widget=%257B%2522version%2522%253A1%252C%2522viewIndex%2522%253A0%252C%2522presetId%2522%253A%2522deals-collection-all-deals%2522%257D&s=price-asc-rank',
    'laptops': 'https://www.amazon.sa/s?k=laptops&deals-widget=%257B%2522version%2522%253A1%252C%2522viewIndex%2522%253A0%252C%2522presetId%2522%253A%2522deals-collection-all-deals%2522%257D&s=price-asc-rank',
    'gaming': 'https://www.amazon.sa/s?k=gaming&deals-widget=%257B%2522version%2522%253A1%252C%2522viewIndex%2522%253A0%252C%2522presetId%2522%253A%2522deals-collection-all-deals%2522%257D&s=price-asc-rank',
    'watches': 'https://www.amazon.sa/s?k=watches&deals-widget=%257B%2522version%2522%253A1%252C%2522viewIndex%2522%253A0%252C%2522presetId%2522%253A%2522deals-collection-all-deals%2522%257D&s=price-asc-rank',
}

last_page_tracker = {cat: 0 for cat in CATEGORIES.keys()}

# ================== Health Server (على PORT الرئيسي) ==================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'OK - Bot is running')

    def log_message(self, format, *args):
        # ✅ مهم: سجل الـ Health Check عشان تعرف إنه شغال
        logger.info(f"Health check: {format % args}")

def run_health_server():
    """شغل الـ Health Server على نفس PORT اللي Render بيديه"""
    while True:
        try:
            server = HTTPServer(('0.0.0.0', PORT), HealthHandler)
            logger.info(f"🌐 Health server running on port {PORT}")
            server.serve_forever()
        except Exception as e:
            logger.error(f"Health server error: {e}")
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
            logger.info(f"📦 Loaded {len(sent_products)} products from database")
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
    try:
        if 'viewIndex' in base_url:
            url = re.sub(r'viewIndex%22%3A\d+', f'viewIndex%22%3A{(page_num-1)*24}', base_url)
            return url
        else:
            separator = '&' if '?' in base_url else '?'
            return f"{base_url}{separator}page={page_num}"
    except:
        separator = '&' if '?' in base_url else '?'
        return f"{base_url}{separator}page={page_num}"

# ================== Scraper ==================
def create_session():
    session = cloudscraper.create_scraper()
    session.headers.update({
        'User-Agent': ua.random,
        'Accept-Language': 'ar-SA,ar;q=0.9,en;q=0.8',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
    })
    return session

def fetch_page(session, url, retries=3):
    for attempt in range(retries):
        try:
            time.sleep(random.uniform(0.5, 1.5))
            r = session.get(url, timeout=25)
            if r.status_code == 200:
                return r.text
            elif r.status_code in [503, 429]:
                logger.warning(f"Rate limited, waiting...")
                time.sleep(5 + attempt * 2)
        except Exception as e:
            logger.error(f"Fetch error: {e}")
            time.sleep(2)
    return None

def parse_item(item):
    try:
        title_elem = item.select_one('h2 a span') or item.select_one('h2 span')
        if not title_elem:
            return None
        
        title = title_elem.text.strip()
        if len(title) < 5:
            return None
        
        price_whole = item.select_one('.a-price-whole')
        price_fraction = item.select_one('.a-price-fraction')
        
        price = None
        if price_whole:
            price_text = price_whole.text.replace(',', '').replace('٬', '').replace('ريال', '').strip()
            if price_fraction:
                price_text += '.' + price_fraction.text
            try:
                price = float(price_text)
            except:
                price = None
        
        if not price or price <= 0:
            return None
        
        old_price_elem = item.select_one('.a-text-price .a-offscreen')
        old_price = None
        discount = 0
        
        if old_price_elem:
            old_text = old_price_elem.text.replace('ر.س', '').replace(',', '').replace('٬', '').strip()
            try:
                old_price = float(old_text)
                if old_price > price:
                    discount = int(((old_price - price) / old_price) * 100)
            except:
                old_price = None
        
        link_elem = item.select_one('h2 a') or item.select_one('a[href*="/dp/"]')
        relative_link = link_elem.get('href') if link_elem else None
        
        clean_link = ""
        asin = None
        if relative_link:
            if relative_link.startswith('/'):
                full_link = f"https://www.amazon.sa{relative_link}"
            elif relative_link.startswith('http'):
                full_link = relative_link
            else:
                full_link = f"https://www.amazon.sa/{relative_link}"
            
            asin = extract_asin(full_link)
            if asin:
                clean_link = f"https://www.amazon.sa/dp/{asin}"
            else:
                clean_link = full_link.split('?')[0] if '?' in full_link else full_link
        
        rating = 0
        rating_elem = item.select_one('.a-icon-alt') or item.select_one('[aria-label*="نجوم"]')
        if rating_elem:
            rating_text = rating_elem.get('aria-label', '') or rating_elem.text
            rating_match = re.search(r'(\d+[.,]?\d*)', rating_text.replace(',', '.'))
            if rating_match:
                try:
                    rating = float(rating_match.group(1))
                except:
                    rating = 0
        
        reviews_count = 0
        reviews_elem = item.select_one('a[href*="reviews"] span')
        if reviews_elem:
            reviews_text = reviews_elem.text.replace(',', '').replace('(', '').replace(')', '').strip()
            reviews_match = re.search(r'(\d+)', reviews_text)
            if reviews_match:
                try:
                    reviews_count = int(reviews_match.group(1))
                except:
                    reviews_count = 0
        
        img_elem = item.select_one('img.s-image')
        image_url = ""
        if img_elem:
            image_url = img_elem.get('data-src') or img_elem.get('src', '')
            if image_url and '._' in image_url:
                image_url = re.sub(r'\._[^_]+_\.', '._SL1000_.', image_url)
        
        free_shipping = bool(item.select_one('[aria-label*="شحن مجاني"]') or 'FREE' in item.get_text().upper())
        is_prime = bool(item.select_one('.a-icon-prime') or 'prime' in item.get_text().lower())
        
        return {
            'title': title,
            'price': price,
            'old_price': round(old_price, 2) if old_price else None,
            'discount': discount,
            'link': clean_link,
            'asin': asin,
            'rating': round(rating, 1),
            'reviews_count': reviews_count,
            'image_url': image_url,
            'free_shipping': free_shipping,
            'is_prime': is_prime,
            'id': hashlib.md5((title + str(asin)).encode()).hexdigest()
        }
        
    except Exception as e:
        logger.error(f"Parse error: {e}")
        return None

def search_until_target(session, category_name, base_url, start_page):
    global last_page_tracker
    
    category_deals = []
    current_page = start_page
    
    while len(category_deals) < 3 and current_page < start_page + MAX_PAGES_PER_CATEGORY:
        url = get_page_url(base_url, current_page)
        logger.info(f"🔍 [{category_name}] Page {current_page} | Found: {len(category_deals)}")
        
        html = fetch_page(session, url)
        if not html:
            current_page += 1
            continue
        
        soup = BeautifulSoup(html, 'html.parser')
        items = soup.find_all('div', {'data-component-type': 's-search-result'})
        
        if not items:
            current_page += 1
            continue
        
        for item in items:
            deal = parse_item(item)
            if deal and deal['discount'] >= MIN_DISCOUNT and deal['rating'] >= MIN_RATING:
                if deal['id'] not in sent_products and not is_similar_product(deal['title']):
                    deal['category'] = category_name
                    category_deals.append(deal)
                    
                    if len(category_deals) >= 5:
                        break
        
        last_page_tracker[category_name] = current_page
        current_page += 1
        time.sleep(random.uniform(0.8, 1.5))
    
    return category_deals

def search_all_deals():
    global last_page_tracker
    
    all_deals = []
    session = create_session()
    
    categories_list = list(CATEGORIES.items())
    random.shuffle(categories_list)
    
    logger.info(f"🚀 Target: {TARGET_DEALS_COUNT} deals")
    
    for category_name, base_url in categories_list:
        if len(all_deals) >= TARGET_DEALS_COUNT:
            break
        
        start_page = last_page_tracker.get(category_name, 0) + 1
        
        if start_page > 50:
            start_page = 1
            last_page_tracker[category_name] = 0
        
        deals = search_until_target(session, category_name, base_url, start_page)
        all_deals.extend(deals)
        
        logger.info(f"✅ {category_name}: +{len(deals)} | Total: {len(all_deals)}")
        time.sleep(random.uniform(1, 2))
    
    all_deals.sort(key=lambda x: (x['discount'], x['rating']), reverse=True)
    
    unique_deals = []
    seen_asins = set()
    for deal in all_deals:
        if deal['asin'] and deal['asin'] not in seen_asins:
            seen_asins.add(deal['asin'])
            unique_deals.append(deal)
        elif not deal['asin']:
            unique_deals.append(deal)
        
        if len(unique_deals) >= TARGET_DEALS_COUNT:
            break
    
    save_database()
    logger.info(f"🎯 Final: {len(unique_deals)} deals")
    return unique_deals

# ================== إرسال ==================
def send_deals(deals, chat_id):
    if not deals:
        updater.bot.send_message(
            chat_id=chat_id,
            text="❌ مفيش عروض كافية دلوقتي",
            parse_mode='Markdown'
        )
        return
    
    categories = {}
    for d in deals:
        cat = d.get('category', 'متنوع')
        categories[cat] = categories.get(cat, 0) + 1
    
    summary = f"🔥 *لقيت {len(deals)} عرض!*\n\n"
    for cat, count in sorted(categories.items(), key=lambda x: x[1], reverse=True):
        summary += f"• {cat}: {count} 🛍️\n"
    
    try:
        updater.bot.send_message(chat_id=chat_id, text=summary, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Summary error: {e}")
    
    time.sleep(1)
    
    for idx, d in enumerate(deals, 1):
        if d['id'] in sent_products:
            continue
        
        old_price_text = f"~~{d['old_price']:.0f}~~ " if d['old_price'] else ""
        shipping = "🚚 مجاني" if d['free_shipping'] else ""
        prime = "✅ Prime" if d['is_prime'] else ""
        
        if d['discount'] >= 70:
            fire = "🔥🔥🔥"
        elif d['discount'] >= 60:
            fire = "🔥🔥"
        else:
            fire = "🔥"
        
        msg = f"""{fire} *{d['title'][:65]}...*

💰 *{d['price']:.0f}* ريال {old_price_text}
📉 خصم: *{d['discount']}%*
⭐ تقييم: *{d['rating']:.1f}/5* ({d['reviews_count']})
🏷️ {d.get('category', 'متنوع')}
{shipping} {prime}

🔗 [اشتري الآن]({d['link']})
"""
        
        try:
            if d['image_url']:
                updater.bot.send_photo(
                    chat_id=chat_id,
                    photo=d['image_url'],
                    caption=msg,
                    parse_mode='Markdown'
                )
            else:
                updater.bot.send_message(chat_id=chat_id, text=msg, parse_mode='Markdown')
            
            sent_products.add(d['id'])
            sent_hashes.add(create_title_hash(d['title']))
            logger.info(f"✅ [{idx}] {d['title'][:40]}")
            
        except Exception as e:
            logger.error(f"Send error: {e}")
            try:
                updater.bot.send_message(chat_id=chat_id, text=msg, parse_mode='Markdown')
            except:
                pass
        
        time.sleep(1.5)
    
    save_database()

# ================== أوامر ==================
def start_cmd(update: Update, context: CallbackContext):
    welcome = """👋 *أهلا بيك في بوت عروض أمازون!*

🔥 يدور في كل الأقسام لحد ما يلاقي 20 عرض
🔄 كل مرة صفحات جديدة

اكتب *Hi* عشان تبدأ"""
    update.message.reply_text(welcome, parse_mode='Markdown')

def hi_cmd(update: Update, context: CallbackContext):
    global is_scanning

    if is_scanning:
        update.message.reply_text("⏳ البوت شغال... استنى!")
        return

    is_scanning = True
    
    status_msg = update.message.reply_text(
        "🔍 بدور في كل الأقسام...\n⏳ ممكن ياخد دقيقة",
        parse_mode='Markdown'
    )

    try:
        deals = search_all_deals()
        
        try:
            updater.bot.delete_message(
                chat_id=update.effective_chat.id,
                message_id=status_msg.message_id
            )
        except:
            pass
        
        send_deals(deals, update.effective_chat.id)
        
    except Exception as e:
        logger.error(f"Error: {e}")
        update.message.reply_text("❌ حصل خطأ - جرب تاني!", parse_mode='Markdown')
    finally:
        is_scanning = False

def status_cmd(update: Update, context: CallbackContext):
    total = len(sent_products)
    msg = f"""✅ *البوت شغال!*

📦 منتجات: *{total}*
🔄 الصفحات بتتغير كل مرة

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
    # ✅ شغل Health Server في Thread منفصل
    health_thread = threading.Thread(target=run_health_server, daemon=True)
    health_thread.start()
    
    # ✅ تأكد إن الـ Health Server اشتغل
    time.sleep(2)
    
    while True:
        try:
            start_bot()
        except Exception as e:
            logger.error(f"Crash: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
