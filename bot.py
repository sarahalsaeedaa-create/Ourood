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
MIN_DISCOUNT = 40        # خصم 40%+
MIN_RATING = 3.0         # 3 نجوم+

# ✅ الأقسام من الكود الجديد (مبسطة)
CATEGORIES_DEF = [
    ("https://www.amazon.sa/gp/bestsellers", "⭐ Best Sellers", 'best_sellers'),
    ("https://www.amazon.sa/gp/goldbox", "🔥 Goldbox", 'deals'),
    ("https://www.amazon.sa/gp/warehouse-deals", "🏭 Warehouse", 'warehouse'),
    ("https://www.amazon.sa/gp/coupons", "🎟️ Coupons", 'coupons'),
    ("https://www.amazon.sa/gp/prime/pipeline/lightning_deals", "⚡ Lightning", 'lightning'),
    ("https://www.amazon.sa/gp/todays-deals", "📅 Today Deals", 'today'),
    ("https://www.amazon.sa/outlet", "🎁 Outlet", 'outlet'),
    
    # إلكترونيات
    ("https://www.amazon.sa/s?k=iphone&rh=p_8%3A30-99", "🍎 iPhone", 'search'),
    ("https://www.amazon.sa/s?k=samsung+galaxy&rh=p_8%3A30-99", "📱 Galaxy", 'search'),
    ("https://www.amazon.sa/s?k=laptop&rh=p_8%3A30-99", "💻 Laptop", 'search'),
    ("https://www.amazon.sa/s?k=headphones&rh=p_8%3A30-99", "🎧 Headphones", 'search'),
    ("https://www.amazon.sa/s?k=playstation&rh=p_8%3A30-99", "🎮 PlayStation", 'search'),
    
    # موضة
    ("https://www.amazon.sa/s?k=nike+shoes&rh=p_8%3A30-99", "👟 Nike", 'search'),
    ("https://www.amazon.sa/s?k=watch&rh=p_8%3A30-99", "⌚ Watches", 'search'),
    ("https://www.amazon.sa/s?k=perfume&rh=p_8%3A30-99", "🌸 Perfumes", 'search'),
    
    # منزل
    ("https://www.amazon.sa/s?k=kitchen&rh=p_8%3A30-99", "🍳 Kitchen", 'search'),
    ("https://www.amazon.sa/s?k=home&rh=p_8%3A30-99", "🏠 Home", 'search'),
]

# ================== Health Server ==================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('content-type', 'text/plain')
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
    global sent_products, sent_hashes
    try:
        if os.path.exists('bot_database.json'):
            with open('bot_database.json', 'r') as f:
                data = json.load(f)
                sent_products = set(data.get('ids', []))
                sent_hashes = set(data.get('hashes', []))
            logger.info(f"📦 Loaded {len(sent_products)} products")
    except Exception as e:
        logger.error(f"DB Load Error: {e}")

def save_database():
    try:
        with open('bot_database.json', 'w') as f:
            json.dump({
                'ids': list(sent_products)[-5000:],
                'hashes': list(sent_hashes)[-5000:]
            }, f)
    except Exception as e:
        logger.error(f"DB Save Error: {e}")

# ================== أدوات ==================
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
    clean = re.sub(r'\s+', ' ', clean).strip()
    return hashlib.md5(clean[:30].encode()).hexdigest()[:16]

def is_similar_product(title):
    return create_title_hash(title) in sent_hashes

def get_product_id(title, link, price):
    asin = extract_asin(link)
    if asin:
        return f"ASIN_{asin}"
    key = f"{title}_{price}"
    return f"HASH_{hashlib.md5(key.encode()).hexdigest()[:12]}"

# ================== Scraper (من الكود الجديد) ==================
def create_session():
    session = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True},
        delay=10
    )
    session.headers.update({
        'User-Agent': ua.random,
        'Accept-Language': 'ar-SA,ar;q=0.9',
        'Referer': 'https://www.amazon.sa/',
    })
    return session

def fetch_page(session, url, retries=3):
    for i in range(retries):
        try:
            time.sleep(random.uniform(2, 4))
            r = session.get(url, timeout=30)
            if r.status_code == 200 and len(r.text) > 5000:
                return r.text
            logger.warning(f"Attempt {i+1} failed: Status {r.status_code}")
            time.sleep(3)
        except Exception as e:
            logger.error(f"Fetch error attempt {i+1}: {e}")
            time.sleep(3)
    return None

def parse_rating(text):
    if not text:
        return 0
    match = re.search(r'(\d+\.?\d*)', str(text))
    return float(match.group(1)) if match else 0

def parse_item(item, category, is_best_seller=False):
    """✅ نفس طريقة الكود الجديد بالظبط"""
    try:
        # السعر
        price = None
        for sel in ['.a-price-whole', '.a-price .a-offscreen', '.a-price-range', '.a-price']:
            el = item.select_one(sel)
            if el:
                try:
                    txt = el.text.replace(',', '').replace('ريال', '').replace('٬', '').strip()
                    match = re.search(r'[\d,]+\.?\d*', txt)
                    if match:
                        price = float(match.group().replace(',', ''))
                        break
                except:
                    pass
        
        if not price or price <= 0:
            return None
        
        # السعر القديم والخصم
        old_price = 0
        discount = 0
        
        old_el = item.find('span', class_='a-text-price')
        if old_el:
            txt = old_el.get_text()
            match = re.search(r'[\d,]+\.?\d*', txt.replace(',', '').replace('٬', ''))
            if match:
                try:
                    old_price = float(match.group())
                    if old_price > price:
                        discount = int(((old_price - price) / old_price) * 100)
                except:
                    pass
        
        # لو مفيش خصم محسوب، ندور على نسبة مكتوبة
        if discount == 0:
            badge = item.find(string=re.compile(r'(\d+)%'))
            if badge:
                match = re.search(r'(\d+)', str(badge))
                if match:
                    discount = int(match.group())
                    old_price = price / (1 - discount/100)
        
        # ✅ شرط الخصم 40%+
        if discount < MIN_DISCOUNT:
            return None
        
        # العنوان
        title = "Unknown"
        for sel in ['h2 a span', 'h2 span', '.a-size-mini span', '.a-size-base-plus', '.a-size-medium']:
            el = item.select_one(sel)
            if el:
                title = el.text.strip()
                if len(title) > 5:
                    break
        
        # اللينك
        link = ""
        a = item.find('a', href=True)
        if a:
            href = a['href']
            if href.startswith('/'):
                link = f"https://www.amazon.sa{href}"
            elif 'amazon.sa' in href:
                link = href
            else:
                asin = extract_asin(href)
                if asin:
                    link = f"https://www.amazon.sa/dp/{asin}"
        
        # التقييم
        rating = 0
        rate_el = item.find('span', class_='a-icon-alt')
        if rate_el:
            rating = parse_rating(rate_el.text)
        
        # ✅ شرط التقييم 3+
        if rating < MIN_RATING:
            return None
        
        # المراجعات
        reviews = 0
        rev_el = item.find('span', class_='a-size-base')
        if rev_el:
            match = re.search(r'[\d,]+', rev_el.text)
            if match:
                try:
                    reviews = int(match.group().replace(',', ''))
                except:
                    pass
        
        # الصورة
        img = ""
        for sel in ['img.s-image', 'img[src]']:
            el = item.select_one(sel)
            if el:
                img = el.get('src', '') or el.get('data-src', '')
                if img.startswith('http'):
                    break
        
        return {
            'title': title[:120],
            'price': price,
            'old_price': round(old_price, 2) if old_price > 0 else round(price * 100 / (100 - discount), 2),
            'discount': discount,
            'rating': rating,
            'reviews': reviews,
            'link': link,
            'image': img,
            'category': category,
            'is_best_seller': is_best_seller,
            'id': get_product_id(title, link, price)
        }
        
    except Exception as e:
        logger.error(f"Parse error: {e}")
        return None

def search_all_deals():
    """✅ نفس طريقة الكود الجديد"""
    all_deals = []
    session = create_session()
    
    # خلط عشوائي للأقسام
    cats = list(CATEGORIES_DEF)
    random.shuffle(cats)
    
    logger.info(f"🚀 Searching {len(cats)} categories...")
    
    for base_url, cat_name, cat_type in cats:
        if len(all_deals) >= TARGET_DEALS_COUNT * 3:
            break
        
        logger.info(f"🔍 [{cat_name}]")
        
        html = fetch_page(session, base_url)
        if not html:
            continue
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # ✅ نفس selectors من الكود الجديد
        items = []
        if cat_type == 'best_sellers':
            items.extend(soup.find_all('li', class_='zg-item-immersion'))
            items.extend(soup.find_all('div', class_='p13n-sc-uncoverable-faceout'))
        
        items.extend(soup.find_all('div', {'data-component-type': 's-search-result'}))
        items.extend(soup.find_all('div', {'data-testid': 'deal-card'}))
        items.extend(soup.find_all('div', class_='s-result-item'))
        
        logger.info(f"   Found {len(items)} items")
        
        for item in items:
            try:
                deal = parse_item(item, cat_name, cat_type == 'best_sellers')
                if deal and deal['id'] not in sent_products:
                    if not is_similar_product(deal['title']):
                        all_deals.append(deal)
                        logger.info(f"✅ ADDED: {deal['title'][:40]} | {deal['discount']}%")
                        
                        if len(all_deals) >= TARGET_DEALS_COUNT * 3:
                            break
            except:
                continue
        
        time.sleep(random.uniform(2, 4))
    
    logger.info(f"🎯 Collected {len(all_deals)} deals")
    return all_deals

def filter_deals(deals):
    """✅ فلترة واختيار أفضل 20 صفقة"""
    filtered = []
    seen_ids = set()
    
    # ترتيب عشوائي
    random.shuffle(deals)
    
    for deal in deals:
        if deal['id'] in seen_ids or deal['id'] in sent_products:
            continue
        
        seen_ids.add(deal['id'])
        
        # تحديد النوع
        if deal['discount'] >= 90:
            deal['type'] = '🔥 GLITCH'
        elif 'Warehouse' in deal['category']:
            deal['type'] = '🏭 WAREHOUSE'
        elif 'Outlet' in deal['category']:
            deal['type'] = '🎁 OUTLET'
        elif 'Lightning' in deal['category']:
            deal['type'] = '⚡ LIGHTNING'
        elif deal.get('is_best_seller'):
            deal['type'] = '⭐ BEST SELLER'
        else:
            deal['type'] = f'💰 {deal["discount"]}%'
        
        deal['savings'] = round(deal['old_price'] - deal['price'], 2)
        filtered.append(deal)
        
        if len(filtered) >= TARGET_DEALS_COUNT:
            break
    
    # ترتيب: Glitch أولاً، بعدين حسب الخصم
    filtered.sort(key=lambda x: (
        0 if x['type'] == '🔥 GLITCH' else 1,
        0 if x['type'] == '🏭 WAREHOUSE' else 1,
        0 if x['type'] == '⚡ LIGHTNING' else 1,
        -x['discount']
    ))
    
    return filtered

# ================== إرسال ==================
def send_deals(deals, chat_id):
    if not deals:
        updater.bot.send_message(
            chat_id=chat_id,
            text="❌ مفيش عروض 40%+ لقيتها\n🔄 جرب تاني!",
            parse_mode='Markdown'
        )
        return
    
    # فصل العروض
    super_deals = [d for d in deals if d['discount'] >= 90]
    normal_deals = [d for d in deals if d['discount'] < 90]
    
    # ✅ رسالة السوبر (90%+)
    if super_deals:
        msg = "🚨🚨🚨 *عروض خرافية 90%+* 🚨🚨🚨\n\n"
        for i, d in enumerate(super_deals, 1):
            msg += f"{i}. *{d['title'][:50]}*\n"
            msg += f"💰 {d['price']:.0f} ريال ~~{d['old_price']:.0f}~~\n"
            msg += f"🔥🔥🔥 خصم: *{d['discount']}%* 🔥🔥🔥\n"
            msg += f"🔗 [اشتري بسرعة]({d['link']})\n\n"
        
        try:
            updater.bot.send_message(chat_id=chat_id, text=msg, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Super send error: {e}")
        
        time.sleep(1)
    
    # ✅ رسالة العادية (40-89%)
    if normal_deals:
        msg = f"🔥 *عروض رهيبة 40%+* ({len(normal_deals)} منتج)\n\n"
        
        for i, d in enumerate(normal_deals, 1):
            savings = f" (توفر {d['savings']:.0f})" if d['savings'] > 0 else ""
            
            msg += f"{i}. *{d['title'][:50]}*\n"
            msg += f"💰 {d['price']:.0f} ريال{savings}\n"
            msg += f"📉 خصم: *{d['discount']}%*\n"
            msg += f"🔗 [اشتري من هنا]({d['link']})\n\n"
            
            # ✅ نبعت كل 5 منتجات
            if i % 5 == 0 or i == len(normal_deals):
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
    
    # نضيف السوبر للـ sent
    for d in super_deals:
        sent_products.add(d['id'])
        sent_hashes.add(create_title_hash(d['title']))
    
    save_database()

# ================== أوامر ==================
def start_cmd(update: Update, context: CallbackContext):
    welcome = """👋 *أهلا بيك في بوت عروض أمازون!*

🔥 *خصومات 40%+ فقط*
🚨 *عروض 90%+ بشكل خاص*

اكتب *Hi* عشان تبدأ"""
    update.message.reply_text(welcome, parse_mode='Markdown')

def hi_cmd(update: Update, context: CallbackContext):
    global is_scanning

    if is_scanning:
        update.message.reply_text("⏳ شغال... استنى!")
        return

    is_scanning = True
    
    status = update.message.reply_text(
        "🔍 *بدور في كل الأقسام...*\n⏳ *الوقت المتوقع: 3-5 دقايق*",
        parse_mode='Markdown'
    )

    try:
        deals = search_all_deals()
        filtered = filter_deals(deals)
        
        try:
            updater.bot.delete_message(
                chat_id=update.effective_chat.id,
                message_id=status.message_id
            )
        except:
            pass
        
        send_deals(filtered, update.effective_chat.id)
        
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
