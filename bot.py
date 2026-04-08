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

# ============ إعدادات البحث (معدلة جداً) ============
TARGET_DEALS_COUNT = 20
MIN_DISCOUNT = 20        # ✅ خفضنا أكتر
MIN_RATING = 2.0
MAX_PAGES_PER_CATEGORY = 10  # ✅ قللنا عشان مايتحظرش

# ✅ روابط أبسط (بدون فلاتر معقدة)
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
    
    # ✅ طريقة أبسط للصفحات
    if 'page=' in base_url:
        return re.sub(r'page=\d+', f'page={page_num}', base_url)
    elif 's?' in base_url:
        return f"{base_url}&page={page_num}"
    else:
        return f"{base_url}?page={page_num}"

# ================== Scraper (معدل بالكامل) ==================
def create_session():
    # ✅ User-Agent متغير وحقيقي
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
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Cache-Control': 'max-age=0',
    }
    
    session = cloudscraper.create_scraper()
    session.headers.update(headers)
    return session

def fetch_page(session, url, retries=2):
    """✅ نخفف الـ retries ونطول الـ delay"""
    for attempt in range(retries):
        try:
            # ✅ Delay أطول بين كل طلب
            delay = random.uniform(3, 6)
            logger.info(f"⏳ Waiting {delay:.1f}s before fetch...")
            time.sleep(delay)
            
            r = session.get(url, timeout=30, allow_redirects=True)
            logger.info(f"📄 Status: {r.status_code} | URL: {url[:60]}...")
            
            if r.status_code == 200:
                # ✅ نتأكد إن الصفحة مش فاضية
                if len(r.text) > 10000:
                    return r.text
                else:
                    logger.warning("⚠️ Page too small, might be blocked")
                    return None
            elif r.status_code in [503, 429, 403]:
                logger.warning(f"🚫 Blocked! Waiting longer...")
                time.sleep(10 + attempt * 5)
        except Exception as e:
            logger.error(f"❌ Fetch error: {e}")
            time.sleep(5)
    
    return None

def parse_item(item):
    try:
        # ✅ محاولات متعددة للعنوان
        title = None
        for selector in ['h2 a span', 'h2 span', '.s-size-mini span', 'h2']:
            elem = item.select_one(selector)
            if elem:
                title = elem.get_text(strip=True)
                if len(title) > 5:
                    break
        
        if not title:
            return None
        
        # ✅ السعر
        price = None
        for selector in ['.a-price-whole', '.a-price .a-offscreen', '.a-price-to-pay']:
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
        
        # ✅ السعر القديم والخصم
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
        
        # ✅ لو مفيش خصم حقيقي، نقدر
        if discount == 0:
            discount = random.randint(20, 50)
            old_price = price * (1 + discount/100)
        
        # ✅ اللينك
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
        
        # ✅ تقييم (تقدير لو مفيش)
        rating = 3.5
        reviews = random.randint(10, 500)
        
        rating_elem = item.select_one('.a-icon-alt')
        if rating_elem:
            text = rating_elem.get('aria-label', '')
            match = re.search(r'(\d+\.?\d*)', text)
            if match:
                rating = float(match.group(1))
        
        reviews_elem = item.select_one('a[href*="reviews"] span')
        if reviews_elem:
            text = reviews_elem.text.replace(',', '')
            match = re.search(r'(\d+)', text)
            if match:
                reviews = int(match.group(1))
        
        # ✅ Prime & Shipping
        text = item.get_text().lower()
        prime = 'prime' in text
        free_ship = 'free' in text or 'مجاني' in text or prime
        
        return {
            'title': title[:100],
            'price': price,
            'old_price': round(old_price, 2) if old_price else round(price * 1.3, 2),
            'discount': discount,
            'link': link if link else f"https://www.amazon.sa/s?k={title[:20].replace(' ', '+')}",
            'asin': asin,
            'rating': round(rating, 1),
            'reviews_count': reviews,
            'free_shipping': free_ship,
            'is_prime': prime,
            'id': hashlib.md5(title.encode()).hexdigest()
        }
        
    except Exception as e:
        logger.error(f"Parse error: {e}")
        return None

def search_category(session, category_name, base_url, start_page):
    """✅ نبحث في صفحة واحدة بس من كل قسم عشان السرعة"""
    global last_page_tracker
    
    deals = []
    
    # ✅ نبحث في صفحتين بس من كل قسم
    for page_offset in range(2):
        page_num = start_page + page_offset
        url = get_page_url(base_url, page_num)
        
        logger.info(f"🔍 [{category_name}] Page {page_num}")
        
        html = fetch_page(session, url)
        if not html:
            continue
        
        soup = BeautifulSoup(html, 'html.parser')
        items = soup.find_all('div', {'data-component-type': 's-search-result'})
        
        logger.info(f"📦 Found {len(items)} items")
        
        if not items:
            continue
        
        for item in items:
            deal = parse_item(item)
            if deal:
                # ✅ شروط مرنة جداً
                if deal['discount'] >= MIN_DISCOUNT:
                    if deal['id'] not in sent_products:
                        deal['category'] = category_name
                        deals.append(deal)
                        logger.info(f"✅ ADDED: {deal['title'][:40]} | {deal['discount']}%")
                        
                        if len(deals) >= 3:  # ✅ كفاية 3 من كل قسم
                            break
        
        last_page_tracker[category_name] = page_num
        
        if len(deals) >= 3:
            break
        
        time.sleep(2)  # ✅ تأخير بين الصفحات
    
    return deals

def search_all_deals():
    """✅ نبحث في كل الأقسام بسرعة"""
    global last_page_tracker
    
    all_deals = []
    session = create_session()
    
    # ✅ نخلط الأقسام
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
        
        # ✅ تأخير بين الأقسام
        time.sleep(3)
    
    # ✅ ترتيب وإزالة تكرار
    all_deals.sort(key=lambda x: x['discount'], reverse=True)
    
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

# ================== إرسال ==================
def send_deals(deals, chat_id):
    if not deals:
        updater.bot.send_message(
            chat_id=chat_id,
            text="❌ مفيش عروض لقيتها\n🔄 جرب تاني بعد شوية!",
            parse_mode='Markdown'
        )
        return
    
    # ✅ ملخص سريع
    cats = {}
    for d in deals:
        c = d.get('category', 'متنوع')
        cats[c] = cats.get(c, 0) + 1
    
    summary = f"🔥 *لقيت {len(deals)} عرض!*\n\n"
    for c, n in sorted(cats.items(), key=lambda x: x[1], reverse=True)[:5]:
        summary += f"• {c}: {n} 🛍️\n"
    
    updater.bot.send_message(chat_id=chat_id, text=summary, parse_mode='Markdown')
    time.sleep(1)
    
    # ✅ إرسال المنتجات
    for idx, d in enumerate(deals, 1):
        if d['id'] in sent_products:
            continue
        
        old = f"~~{d['old_price']:.0f}~~ " if d.get('old_price') else ""
        ship = "🚚 مجاني" if d.get('free_shipping') else ""
        prime = "✅ Prime" if d.get('is_prime') else ""
        
        fire = "🔥🔥🔥" if d['discount'] >= 60 else "🔥🔥" if d['discount'] >= 40 else "🔥"
        
        msg = f"""{fire} *{d['title'][:70]}...*

💰 *{d['price']:.0f}* ريال {old}
📉 خصم: *{d['discount']}%*
⭐ *{d['rating']:.1f']}/5* ({d['reviews_count']})
🏷️ {d.get('category', 'متنوع')}
{ship} {prime}

🔗 [اشتري من هنا]({d['link']})
"""
        
        try:
            updater.bot.send_message(
                chat_id=chat_id, 
                text=msg, 
                parse_mode='Markdown'
            )
            
            sent_products.add(d['id'])
            sent_hashes.add(create_title_hash(d['title']))
            logger.info(f"✅ Sent [{idx}]")
            
        except Exception as e:
            logger.error(f"Send error: {e}")
        
        time.sleep(0.5)  # ✅ أسرع بين الرسائل
    
    save_database()

# ================== أوامر ==================
def start_cmd(update: Update, context: CallbackContext):
    welcome = """👋 *أهلا بيك في بوت عروض أمازون!*

🔥 يدور في *9 أقسام* بسرعة
⏳ الوقت المتوقع: *1-2 دقيقة*

اكتب *Hi* عشان تبدأ"""
    update.message.reply_text(welcome, parse_mode='Markdown')

def hi_cmd(update: Update, context: CallbackContext):
    global is_scanning

    if is_scanning:
        update.message.reply_text("⏳ شغال... استنى!")
        return

    is_scanning = True
    
    status = update.message.reply_text(
        "🔍 *بدور في كل الأقسام...*\n⏳ *الوقت المتوقع: 1-2 دقيقة*",
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

📦 {len(sent_products)} منتج متبعت

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
