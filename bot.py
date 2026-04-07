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
PORT = int(os.environ.get("PORT", 10000))

ua = UserAgent()
sent_products = set()
sent_hashes = set()
is_scanning = False
updater = None

# ============ إعدادات البحث المتقدمة ============
TARGET_DEALS_COUNT = 40
MIN_DISCOUNT = 50
MIN_RATING = 3.0
PAGES_PER_SESSION = 5  # عدد الصفحات في كل مرة

# الأقسام المختلفة للبحث فيها
CATEGORIES = {
    'electronics': 'https://www.amazon.sa/s?k=electronics&deals-widget=%257B%2522version%2522%253A1%252C%2522viewIndex%2522%253A0%252C%2522presetId%2522%253A%2522deals-collection-all-deals%2522%257D&s=price-asc-rank',
    'fashion': 'https://www.amazon.sa/s?k=fashion&deals-widget=%257B%2522version%2522%253A1%252C%2522viewIndex%2522%253A0%252C%2522presetId%2522%253A%2522deals-collection-all-deals%2522%257D&s=price-asc-rank',
    'home': 'https://www.amazon.sa/s?k=home&deals-widget=%257B%2522version%2522%253A1%252C%2522viewIndex%2522%253A0%252C%2522presetId%2522%253A%2522deals-collection-all-deals%2522%257D&s=price-asc-rank',
    'beauty': 'https://www.amazon.sa/s?k=beauty&deals-widget=%257B%2522version%2522%253A1%252C%2522viewIndex%2522%253A0%252C%2522presetId%2522%253A%2522deals-collection-all-deals%2522%257D&s=price-asc-rank',
    'sports': 'https://www.amazon.sa/s?k=sports&deals-widget=%257B%2522version%2522%253A1%252C%2522viewIndex%2522%253A0%252C%2522presetId%2522%253A%2522deals-collection-all-deals%2522%257D&s=price-asc-rank',
    'toys': 'https://www.amazon.sa/s?k=toys&deals-widget=%257B%2522version%2522%253A1%252C%2522viewIndex%2522%253A0%252C%2522presetId%2522%253A%2522deals-collection-all-deals%2522%257D&s=price-asc-rank',
    'kitchen': 'https://www.amazon.sa/s?f=kitchen&deals-widget=%257B%2522version%2522%253A1%252C%2522viewIndex%2522%253A0%252C%2522presetId%2522%253A%2522deals-collection-all-deals%2522%257D&s=price-asc-rank',
    'phones': 'https://www.amazon.sa/s?k=smartphones&deals-widget=%257B%2522version%2522%253A1%252C%2522viewIndex%2522%253A0%252C%2522presetId%2522%253A%2522deals-collection-all-deals%2522%257D&s=price-asc-rank',
    'laptops': 'https://www.amazon.sa/s?k=laptops&deals-widget=%257B%2522version%2522%253A1%252C%2522viewIndex%2522%253A0%252C%2522presetId%2522%253A%2522deals-collection-all-deals%2522%257D&s=price-asc-rank',
    'grocery': 'https://www.amazon.sa/s?k=grocery&deals-widget=%257B%2522version%2522%253A1%252C%2522viewIndex%2522%253A0%252C%2522presetId%2522%253A%2522deals-collection-all-deals%2522%257D&s=price-asc-rank',
    'automotive': 'https://www.amazon.sa/s?k=automotive&deals-widget=%257B%2522version%2522%253A1%252C%2522viewIndex%2522%253A0%252C%2522presetId%2522%253A%2522deals-collection-all-deals%2522%257D&s=price-asc-rank',
    'baby': 'https://www.amazon.sa/s?k=baby&deals-widget=%257B%2522version%2522%253A1%252C%2522viewIndex%2522%253A0%252C%2522presetId%2522%253A%2522deals-collection-all-deals%2522%257D&s=price-asc-rank',
    'tools': 'https://www.amazon.sa/s?k=tools&deals-widget=%257B%2522version%2522%253A1%252C%2522viewIndex%2522%253A0%252C%2522presetId%2522%253A%2522deals-collection-all-deals%2522%257D&s=price-asc-rank',
    'health': 'https://www.amazon.sa/s?k=health&deals-widget=%257B%2522version%2522%253A1%252C%2522viewIndex%2522%253A0%252C%2522presetId%2522%253A%2522deals-collection-all-deals%2522%257D&s=price-asc-rank',
    'books': 'https://www.amazon.sa/s?k=books&deals-widget=%257B%2522version%2522%253A1%252C%2522viewIndex%2522%253A0%252C%2522presetId%2522%253A%2522deals-collection-all-deals%2522%257D&s=price-asc-rank',
    'gaming': 'https://www.amazon.sa/s?k=gaming&deals-widget=%257B%2522version%2522%253A1%252C%2522viewIndex%2522%253A0%252C%2522presetId%2522%253A%2522deals-collection-all-deals%2522%257D&s=price-asc-rank',
    'watches': 'https://www.amazon.sa/s?k=watches&deals-widget=%257B%2522version%2522%253A1%252C%2522viewIndex%2522%253A0%252C%2522presetId%2522%253A%2522deals-collection-all-deals%2522%257D&s=price-asc-rank',
    'jewelry': 'https://www.amazon.sa/s?k=jewelry&deals-widget=%257B%2522version%2522%253A1%252C%2522viewIndex%2522%253A0%252C%2522presetId%2522%253A%2522deals-collection-all-deals%2522%257D&s=price-asc-rank',
    'furniture': 'https://www.amazon.sa/s?k=furniture&deals-widget=%257B%2522version%2522%253A1%252C%2522viewIndex%2522%253A0%252C%2522presetId%2522%253A%2522deals-collection-all-deals%2522%257D&s=price-asc-rank',
    'pet': 'https://www.amazon.sa/s?k=pet+supplies&deals-widget=%257B%2522version%2522%253A1%252C%2522viewIndex%2522%253A0%252C%2522presetId%2522%253A%2522deals-collection-all-deals%2522%257D&s=price-asc-rank',
}

# متغير لتتبع آخر صفحة تم البحث فيها لكل قسم
last_page_tracker = {cat: 0 for cat in CATEGORIES.keys()}

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
    global sent_products, sent_hashes, last_page_tracker
    try:
        if os.path.exists('bot_database.json'):
            with open('bot_database.json', 'r') as f:
                data = json.load(f)
                sent_products = set(data.get('ids', []))
                sent_hashes = set(data.get('hashes', []))
                # تحميل آخر صفحة لكل قسم
                saved_pages = data.get('last_pages', {})
                for cat in CATEGORIES.keys():
                    if cat in saved_pages:
                        last_page_tracker[cat] = saved_pages[cat]
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
    """تعديل الرابط ليشمل رقم الصفحة"""
    if page_num <= 1:
        return base_url
    # استبدال viewIndex أو إضافة page
    if 'page=' in base_url:
        return re.sub(r'page=\d+', f'page={page_num}', base_url)
    else:
        # إضافة معامل الصفحة
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
            time.sleep(random.uniform(0.5, 1.5))  # تأخير عشوائي
            r = session.get(url, timeout=25)
            if r.status_code == 200:
                return r.text
            elif r.status_code == 503:
                logger.warning(f"503 error, waiting... (attempt {attempt+1})")
                time.sleep(3)
            else:
                logger.warning(f"Status {r.status_code} for {url}")
        except Exception as e:
            logger.error(f"Fetch error (attempt {attempt+1}): {e}")
            time.sleep(2)
    return None

def parse_item(item):
    try:
        # العنوان
        title_elem = item.select_one('h2 a span') or item.select_one('h2 span') or item.select_one('[data-cy="title-recipe-title"]')
        if not title_elem:
            return None
        
        title = title_elem.text.strip()
        if len(title) < 5:  # عنوان قصير جداً = غير صالح
            return None
        
        # السعر الحالي
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
        
        # السعر القديم (لحساب الخصم الحقيقي)
        old_price_elem = item.select_one('.a-text-price .a-offscreen') or item.select_one('.a-price.a-text-price .a-offscreen')
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
        
        # لو مفيش سعر قديم، ندور على نسبة خصم مكتوبة
        if discount == 0:
            discount_elem = item.select_one('.a-color-base') or item.select_one('[aria-label*="خصم"]')
            if discount_elem:
                discount_text = discount_elem.text
                discount_match = re.search(r'(\d+)\s*%', discount_text) or re.search(r'(\d+)', discount_text)
                if discount_match:
                    try:
                        discount = int(discount_match.group(1))
                    except:
                        discount = 0
        
        # اللينك
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
        
        # التقييم
        rating = 0
        rating_elem = item.select_one('.a-icon-alt') or item.select_one('[aria-label*="نجوم"]') or item.select_one('[aria-label*="out of"]')
        if rating_elem:
            rating_text = rating_elem.get('aria-label', '') or rating_elem.text
            rating_match = re.search(r'(\d+[.,]?\d*)\s*(?:out of|من|نجوم?)', rating_text, re.IGNORECASE)
            if rating_match:
                try:
                    rating = float(rating_match.group(1).replace(',', '.'))
                except:
                    rating = 0
        
        # عدد المراجعات
        reviews_count = 0
        reviews_elem = item.select_one('a[href*="reviews"] span') or item.select_one('.a-size-base.a-color-secondary')
        if reviews_elem:
            reviews_text = reviews_elem.text.replace(',', '').replace('(', '').replace(')', '').replace('مراجعة', '').replace('تقييم', '').strip()
            reviews_match = re.search(r'(\d+)', reviews_text)
            if reviews_match:
                try:
                    reviews_count = int(reviews_match.group(1))
                except:
                    reviews_count = 0
        
        # الصورة
        img_elem = item.select_one('img.s-image') or item.select_one('.s-image')
        image_url = ""
        if img_elem:
            image_url = img_elem.get('data-src') or img_elem.get('src', '')
            if image_url and '._' in image_url:
                image_url = re.sub(r'\._[^_]+_\.', '._SL1000_.', image_url)
        
        # الشحن المجاني
        free_shipping = bool(item.select_one('[aria-label*="شحن مجاني"]') or 
                           item.select_one('.a-color-success') or
                           item.select_one('i.a-icon-prime') or
                           'FREE' in item.get_text().upper())
        
        # Prime
        is_prime = bool(item.select_one('.a-icon-prime') or 
                     item.select_one('[aria-label*="Prime"]') or
                     'prime' in item.get_text().lower())
        
        # القسم (Category)
        category_elem = item.select_one('[data-component-type="s-search-result"]')
        category = "متنوع"
        
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
            'category': category,
            'id': hashlib.md5((title + str(asin)).encode()).hexdigest()
        }
        
    except Exception as e:
        logger.error(f"Parse error: {e}")
        return None

def search_category(session, category_name, base_url, start_page, num_pages):
    """البحث في قسم معين من صفحة محددة"""
    deals = []
    
    for page_offset in range(num_pages):
        current_page = start_page + page_offset
        url = get_page_url(base_url, current_page)
        
        logger.info(f"🔍 Searching {category_name} - Page {current_page}")
        
        html = fetch_page(session, url)
        if not html:
            continue
        
        soup = BeautifulSoup(html, 'html.parser')
        items = soup.find_all('div', {'data-component-type': 's-search-result'})
        
        if not items:
            logger.warning(f"No items found in {category_name} page {current_page}")
            continue
        
        for item in items:
            deal = parse_item(item)
            if deal and deal['discount'] >= MIN_DISCOUNT and deal['rating'] >= MIN_RATING:
                if deal['id'] not in sent_products and not is_similar_product(deal['title']):
                    deal['category'] = category_name  # إضافة اسم القسم
                    deals.append(deal)
        
        # تحديث آخر صفحة تم البحث فيها
        last_page_tracker[category_name] = current_page
        
        time.sleep(random.uniform(1, 2))  # تأخير بين الصفحات
    
    return deals

def search_all_deals():
    """البحث في كل الأقسام مع دورة الصفحات"""
    global last_page_tracker
    
    all_deals = []
    session = create_session()
    
    # خلط الأقسام عشوياً عشان التنوع
    categories_list = list(CATEGORIES.items())
    random.shuffle(categories_list)
    
    logger.info(f"🚀 Starting search in {len(categories_list)} categories")
    logger.info(f"📄 Pages per session: {PAGES_PER_SESSION}")
    
    for category_name, base_url in categories_list:
        if len(all_deals) >= TARGET_DEALS_COUNT * 2:  # نجمع أكتر شوية للفلترة
            break
        
        # نبدأ من آخر صفحة + 1
        start_page = last_page_tracker.get(category_name, 0) + 1
        
        # لو وصلنا لصفحة كبيرة، نرجع للبداية
        if start_page > 20:
            start_page = 1
            last_page_tracker[category_name] = 0
        
        deals = search_category(session, category_name, base_url, start_page, PAGES_PER_SESSION)
        all_deals.extend(deals)
        
        logger.info(f"✅ {category_name}: {len(deals)} deals (Total: {len(all_deals)})")
        
        time.sleep(random.uniform(2, 3))  # تأخير بين الأقسام
    
    # ترتيب حسب الخصم (الأعلى أولاً) وأخذ الأفضل
    all_deals.sort(key=lambda x: (x['discount'], x['rating']), reverse=True)
    
    # إزالة التكرارات
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
    
    logger.info(f"🎯 Found {len(unique_deals)} unique deals")
    return unique_deals

# ================== إرسال ==================
def send_deals(deals, chat_id):
    if not deals:
        return
    
    # إرسال ملخص أولاً
    summary = f"🔥 *لقيت {len(deals)} عرض قوي!*\n\n"
    summary += "📊 *الأقسام:*\n"
    
    categories_count = {}
    for d in deals:
        cat = d.get('category', 'متنوع')
        categories_count[cat] = categories_count.get(cat, 0) + 1
    
    for cat, count in sorted(categories_count.items(), key=lambda x: x[1], reverse=True)[:5]:
        summary += f"• {cat}: {count} منتجات\n"
    
    try:
        updater.bot.send_message(chat_id=chat_id, text=summary, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Summary send error: {e}")
    
    time.sleep(1)
    
    # إرسال كل منتج
    for idx, d in enumerate(deals, 1):
        if d['id'] in sent_products:
            continue
        
        old_price_text = f"~~{d['old_price']:.0f}~~ " if d['old_price'] else ""
        
        shipping_text = "🚚 مجاني" if d['free_shipping'] else ""
        prime_text = "✅ Prime" if d['is_prime'] else ""
        
        # اختيار إيموجي حسب الخصم
        if d['discount'] >= 70:
            fire_emoji = "🔥🔥🔥"
        elif d['discount'] >= 60:
            fire_emoji = "🔥🔥"
        else:
            fire_emoji = "🔥"
        
        msg = f"""{fire_emoji} *{d['title'][:70]}...*

💰 *{d['price']:.0f}* ريال {old_price_text}
📉 خصم: *{d['discount']}%*
⭐ تقييم: *{d['rating']:.1f}/5* ({d['reviews_count']})
🏷️ القسم: {d.get('category', 'متنوع')}
{shipping_text} {prime_text}

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
                updater.bot.send_message(
                    chat_id=chat_id,
                    text=msg,
                    parse_mode='Markdown'
                )
            
            sent_products.add(d['id'])
            sent_hashes.add(create_title_hash(d['title']))
            
            # تسجيل الإحصائيات
            logger.info(f"✅ [{idx}/{len(deals)}] Sent: {d['title'][:40]} | {d['discount']}% off")
            
        except Exception as e:
            logger.error(f"Send error for {d['title'][:30]}: {e}")
            try:
                updater.bot.send_message(chat_id=chat_id, text=msg, parse_mode='Markdown')
            except:
                pass
        
        time.sleep(1.5)  # تأخير أطول لتجنب الحظر
    
    save_database()

# ================== أوامر ==================
def start_cmd(update: Update, context: CallbackContext):
    welcome_msg = """👋 *أهلا بيك في بوت عروض أمازون السعودية المتقدم!*

🔥 *المميزات:*
• بحث في *20 قسم* مختلف
• دورة صفحات ذكية (كل مرة صفحات جديدة)
• خصومات *50%+* فقط
• تقييم *3+ نجوم*
• صور + لينكات مباشرة

📝 *طريقة الاستخدام:*
اكتب *Hi* - يبدأ البحث في كل الأقسام

⚡️ كل مرة هيجيبلك عروض من صفحات مختلفة!"""
    
    update.message.reply_text(welcome_msg, parse_mode='Markdown')

def hi_cmd(update: Update, context: CallbackContext):
    global is_scanning

    if is_scanning:
        update.message.reply_text("⏳ البوت شغال في بحث تاني... استنى شوية!")
        return

    is_scanning = True
    
    # إظهار حالة البحث
    status_msg = update.message.reply_text(
        "🔍 *بدورلك في كل الأقسام...*\n"
        "📄 كل مرة ببحث في صفحات مختلفة\n"
        "⏳ ممكن ياخد دقيقة...",
        parse_mode='Markdown'
    )

    try:
        deals = search_all_deals()
        
        if deals:
            # حذف رسالة الانتظار
            try:
                updater.bot.delete_message(
                    chat_id=update.effective_chat.id,
                    message_id=status_msg.message_id
                )
            except:
                pass
            
            send_deals(deals, update.effective_chat.id)
        else:
            update.message.reply_text(
                "❌ *مفيش عروض كافية دلوقتي*\n"
                "🔄 جرب تاني بعد شوية - الصفحات بتتغير كل مرة!",
                parse_mode='Markdown'
            )
            
    except Exception as e:
        logger.error(f"Error in hi_cmd: {e}")
        update.message.reply_text(
            "❌ *حصل خطأ في البحث*\n"
            "🔄 جرب تاني - لو استمر الخطأ، كلم المطور",
            parse_mode='Markdown'
        )
    finally:
        is_scanning = False

def status_cmd(update: Update, context: CallbackContext):
    total_sent = len(sent_products)
    categories_status = "\n".join([
        f"• {cat}: صفحة {page}" 
        for cat, page in sorted(last_page_tracker.items())[:10]
    ])
    
    status_msg = f"""✅ *البوت شغال تمام!*

📊 *الإحصائيات:*
• منتجات متبعتة: *{total_sent}*
• أقسام نشطة: *{len(CATEGORIES)}*
• صفحات/بحث: *{PAGES_PER_SESSION}*

🗂️ *آخر صفحات تم البحث فيها:*
{categories_status}

🔄 اكتب *Hi* عشان تبدأ بحث جديد!"""
    
    update.message.reply_text(status_msg, parse_mode='Markdown')

def reset_cmd(update: Update, context: CallbackContext):
    """أمر لإعادة تعيين الصفحات (للأدمن فقط)"""
    global last_page_tracker
    last_page_tracker = {cat: 0 for cat in CATEGORIES.keys()}
    save_database()
    update.message.reply_text("✅ تم إعادة تعيين الصفحات - البحث هيبدأ من الأول!")

# ================== تشغيل ==================
def start_bot():
    global updater

    load_database()

    updater = Updater(token=TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start_cmd))
    dp.add_handler(CommandHandler("status", status_cmd))
    dp.add_handler(CommandHandler("reset", reset_cmd))
    dp.add_handler(MessageHandler(Filters.regex(r'(?i)^hi$') & Filters.text, hi_cmd))

    logger.info("🤖 Bot started with advanced page rotation!")
    logger.info(f"📁 Categories: {len(CATEGORIES)}")
    logger.info(f"📄 Pages per search: {PAGES_PER_SESSION}")
    
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
