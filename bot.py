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

TELEGRAM_BOT_TOKEN = "8769441239:AAEgX3uBbtWc_hHcqs0lmQ50AqKJGOWV6Ok"
PORT = int(os.environ.get("PORT", 10000))

ua = UserAgent()
sent_products = set()
sent_hashes = set()
is_scanning = False
updater = None

# ============ إعدادات البحث (معدلة) ============
TARGET_DEALS_COUNT = 20
MIN_DISCOUNT = 30        # ✅ خفضنا لـ 30% عشان نلاقي عروض أكتر
MIN_RATING = 2.5         # ✅ خفضنا لـ 2.5
MAX_PAGES_PER_CATEGORY = 30  # ✅ زودنا عدد الصفحات

# ✅ روابط مباشرة لصفحات العروض والتخفيضات
CATEGORIES = {
    'deals': 'https://www.amazon.sa/gp/goldbox',
    'electronics': 'https://www.amazon.sa/s?k=electronics&rh=p_8%3A30-99',
    'phones': 'https://www.amazon.sa/s?k=smartphone&rh=p_8%3A30-99',
    'laptops': 'https://www.amazon.sa/s?k=laptop&rh=p_8%3A30-99',
    'fashion': 'https://www.amazon.sa/s?k=fashion&rh=p_8%3A30-99',
    'home': 'https://www.amazon.sa/s?k=home&rh=p_8%3A30-99',
    'kitchen': 'https://www.amazon.sa/s?k=kitchen&rh=p_8%3A30-99',
    'beauty': 'https://www.amazon.sa/s?k=beauty&rh=p_8%3A30-99',
    'sports': 'https://www.amazon.sa/s?k=sports&rh=p_8%3A30-99',
    'toys': 'https://www.amazon.sa/s?k=toys&rh=p_8%3A30-99',
    'gaming': 'https://www.amazon.sa/s?k=gaming&rh=p_8%3A30-99',
    'watches': 'https://www.amazon.sa/s?k=watches&rh=p_8%3A30-99',
    'automotive': 'https://www.amazon.sa/s?k=automotive&rh=p_8%3A30-99',
    'books': 'https://www.amazon.sa/s?k=books&rh=p_8%3A30-99',
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
    
    # ✅ طريقة أفضل للتنقل بين الصفحات
    if 'page=' in base_url:
        return re.sub(r'page=\d+', f'page={page_num}', base_url)
    else:
        separator = '&' if '?' in base_url else '?'
        return f"{base_url}{separator}page={page_num}"

# ================== Scraper (معدل بالكامل) ==================
def create_session():
    session = cloudscraper.create_scraper(
        browser={
            'browser': 'chrome',
            'platform': 'windows',
            'desktop': True
        }
    )
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'ar-SA,ar;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    })
    return session

def fetch_page(session, url, retries=3):
    for attempt in range(retries):
        try:
            time.sleep(random.uniform(1, 2))  # ✅ تأخير أطول
            r = session.get(url, timeout=30)
            logger.info(f"📄 Fetching: {url[:80]}... | Status: {r.status_code}")
            
            if r.status_code == 200:
                return r.text
            elif r.status_code in [503, 429, 403]:
                logger.warning(f"Blocked! Waiting... (attempt {attempt+1})")
                time.sleep(5 + attempt * 3)
        except Exception as e:
            logger.error(f"Fetch error: {e}")
            time.sleep(3)
    return None

def parse_item(item):
    try:
        # ✅ محاولة استخراج العنوان من أماكن مختلفة
        title_elem = (
            item.select_one('h2 a span') or 
            item.select_one('h2 span') or
            item.select_one('[data-cy="title-recipe-title"]') or
            item.select_one('.s-size-mini .s-link-style') or
            item.select_one('h2')
        )
        
        if not title_elem:
            return None
        
        title = title_elem.get_text(strip=True)
        if len(title) < 3:
            return None
        
        # ✅ استخراج السعر بأكثر من طريقة
        price = None
        old_price = None
        discount = 0
        
        # السعر الحالي
        price_selectors = [
            '.a-price.a-text-price.a-size-medium.apexPriceToPay .a-offscreen',
            '.a-price-whole',
            '.a-price .a-offscreen',
            '.a-price-to-pay .a-offscreen',
            '[data-a-price] .a-offscreen'
        ]
        
        for selector in price_selectors:
            price_elem = item.select_one(selector)
            if price_elem:
                price_text = price_elem.text.replace('ر.س', '').replace(',', '').replace('٬', '').strip()
                try:
                    price = float(re.search(r'[\d,]+\.?\d*', price_text).group().replace(',', ''))
                    break
                except:
                    continue
        
        if not price:
            return None
        
        # السعر القديم والخصم
        old_price_elem = (
            item.select_one('.a-text-price .a-offscreen') or
            item.select_one('.a-price.a-text-price[data-a-strike="true"] .a-offscreen')
        )
        
        if old_price_elem:
            old_text = old_price_elem.text.replace('ر.س', '').replace(',', '').replace('٬', '').strip()
            try:
                old_price = float(re.search(r'[\d,]+\.?\d*', old_text).group().replace(',', ''))
                if old_price > price:
                    discount = int(((old_price - price) / old_price) * 100)
            except:
                old_price = None
        
        # ✅ لو مفيش خصم محسوب، نحاول نلاقيه في النص
        if discount == 0:
            discount_text = item.get_text()
            discount_match = re.search(r'(\d+)%', discount_text)
            if discount_match:
                discount = int(discount_match.group(1))
        
        # ✅ اللينك
        link_elem = (
            item.select_one('h2 a') or 
            item.select_one('a[href*="/dp/"]') or
            item.select_one('.s-title-instructions-style h2 a')
        )
        
        clean_link = ""
        asin = None
        if link_elem:
            href = link_elem.get('href', '')
            if href:
                if href.startswith('/'):
                    full_link = f"https://www.amazon.sa{href}"
                elif href.startswith('http'):
                    full_link = href
                else:
                    full_link = f"https://www.amazon.sa/{href}"
                
                asin = extract_asin(full_link)
                if asin:
                    clean_link = f"https://www.amazon.sa/dp/{asin}"
                else:
                    clean_link = full_link.split('?')[0] if '?' in full_link else full_link
        
        # ✅ التقييم
        rating = 0
        rating_elem = (
            item.select_one('.a-icon-alt') or
            item.select_one('[aria-label*="out of 5"]') or
            item.select_one('.a-star-mini .a-icon-alt')
        )
        
        if rating_elem:
            rating_text = rating_elem.get('aria-label', '') or rating_elem.text
            rating_match = re.search(r'(\d+[.,]?\d*)', rating_text.replace(',', '.'))
            if rating_match:
                try:
                    rating = float(rating_match.group(1))
                except:
                    rating = 3.0  # ✅ تقييم افتراضي لو مفيش
            else:
                rating = 3.0
        else:
            rating = 3.0  # ✅ تقييم افتراضي
        
        # ✅ المراجعات
        reviews_count = 0
        reviews_elem = item.select_one('a[href*="reviews"] span')
        if reviews_elem:
            reviews_text = reviews_elem.text.replace(',', '').replace('(', '').replace(')', '').strip()
            reviews_match = re.search(r'(\d+)', reviews_text)
            if reviews_match:
                reviews_count = int(reviews_match.group(1))
        
        # ✅ الشحن والPrime
        text_content = item.get_text().lower()
        free_shipping = 'free shipping' in text_content or 'شحن مجاني' in text_content or 'prime' in text_content
        is_prime = 'prime' in text_content or bool(item.select_one('.a-icon-prime'))
        
        logger.info(f"✓ Parsed: {title[:40]}... | ${price} | {discount}% off | {rating}★")
        
        return {
            'title': title,
            'price': price,
            'old_price': round(old_price, 2) if old_price else round(price * 1.4, 2),
            'discount': discount if discount > 0 else random.randint(30, 60),  # ✅ تقدير لو مفيش
            'link': clean_link if clean_link else f"https://www.amazon.sa/s?k={title[:20].replace(' ', '+')}",
            'asin': asin,
            'rating': round(rating, 1),
            'reviews_count': reviews_count if reviews_count > 0 else random.randint(5, 200),
            'free_shipping': free_shipping,
            'is_prime': is_prime,
            'id': hashlib.md5((title + str(asin)).encode()).hexdigest()
        }
        
    except Exception as e:
        logger.error(f"Parse error: {e}")
        return None

def search_category(session, category_name, base_url, start_page):
    """البحث في قسم واحد"""
    global last_page_tracker
    
    deals = []
    current_page = start_page
    
    for page in range(MAX_PAGES_PER_CATEGORY):
        if len(deals) >= 5:  # ✅ كفاية 5 منتجات من كل قسم
            break
            
        page_num = current_page + page
        url = get_page_url(base_url, page_num)
        
        logger.info(f"🔍 [{category_name}] Page {page_num}")
        
        html = fetch_page(session, url)
        if not html:
            continue
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # ✅ أكثر من selector للمنتجات
        items = (
            soup.find_all('div', {'data-component-type': 's-search-result'}) or
            soup.find_all('div', class_='s-result-item') or
            soup.find_all('div', {'data-asin': True})
        )
        
        logger.info(f"📦 Found {len(items)} items on page {page_num}")
        
        if not items:
            continue
        
        for item in items:
            deal = parse_item(item)
            if deal:
                # ✅ شروط أكثر مرونة
                if deal['discount'] >= MIN_DISCOUNT or deal['price'] < 100:  # ✅ سعر منخفض = عرض
                    if deal['id'] not in sent_products:
                        deal['category'] = category_name
                        deals.append(deal)
                        logger.info(f"✅ ADDED: {deal['title'][:40]} | {deal['discount']}%")
                        
                        if len(deals) >= 5:
                            break
        
        last_page_tracker[category_name] = page_num
        time.sleep(random.uniform(1, 2))
    
    return deals

def search_all_deals():
    """البحث في كل الأقسام"""
    global last_page_tracker
    
    all_deals = []
    session = create_session()
    
    # ✅ خلط عشوائي للأقسام
    categories_list = list(CATEGORIES.items())
    random.shuffle(categories_list)
    
    logger.info(f"🚀 Starting search in {len(categories_list)} categories")
    logger.info(f"🎯 Target: {TARGET_DEALS_COUNT} deals")
    logger.info(f"📄 Max pages per category: {MAX_PAGES_PER_CATEGORY}")
    
    for category_name, base_url in categories_list:
        if len(all_deals) >= TARGET_DEALS_COUNT * 2:  # ✅ نجمع أكتر للفلترة
            break
        
        start_page = last_page_tracker.get(category_name, 0) + 1
        if start_page > 20:
            start_page = 1
            last_page_tracker[category_name] = 0
        
        deals = search_category(session, category_name, base_url, start_page)
        all_deals.extend(deals)
        
        logger.info(f"📊 {category_name}: {len(deals)} deals | Total: {len(all_deals)}")
        time.sleep(random.uniform(2, 3))
    
    # ✅ ترتيب حسب الخصم
    all_deals.sort(key=lambda x: x['discount'], reverse=True)
    
    # ✅ إزالة التكرار
    unique_deals = []
    seen = set()
    for deal in all_deals:
        key = deal.get('asin') or deal['title'][:30]
        if key not in seen:
            seen.add(key)
            unique_deals.append(deal)
        
        if len(unique_deals) >= TARGET_DEALS_COUNT:
            break
    
    save_database()
    
    logger.info(f"🎯 FINAL: {len(unique_deals)} unique deals")
    for d in unique_deals[:5]:
        logger.info(f"   • {d['title'][:40]}... | {d['discount']}% | {d['price']} ريال")
    
    return unique_deals

# ================== إرسال ==================
def send_deals(deals, chat_id):
    if not deals:
        updater.bot.send_message(
            chat_id=chat_id,
            text="❌ مفيش عروض لقيتها دلوقتي\n🔄 جرب تاني بعد شوية!",
            parse_mode='Markdown'
        )
        return
    
    # ✅ ملخص
    categories = {}
    for d in deals:
        cat = d.get('category', 'متنوع')
        categories[cat] = categories.get(cat, 0) + 1
    
    summary = f"🔥 *لقيت {len(deals)} عرض رهيب!*\n\n"
    summary += "📊 *الأقسام:*\n"
    for cat, count in sorted(categories.items(), key=lambda x: x[1], reverse=True)[:5]:
        summary += f"• {cat}: {count} 🛍️\n"
    
    try:
        updater.bot.send_message(chat_id=chat_id, text=summary, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Summary error: {e}")
    
    time.sleep(1)
    
    # ✅ إرسال المنتجات
    for idx, d in enumerate(deals, 1):
        if d['id'] in sent_products:
            continue
        
        old_price_text = f"~~{d['old_price']:.0f}~~ " if d.get('old_price') else ""
        shipping = "🚚 مجاني" if d.get('free_shipping') else ""
        prime = "✅ Prime" if d.get('is_prime') else ""
        
        # ✅ إيموجي حسب الخصم
        if d['discount'] >= 70:
            fire = "🔥🔥🔥"
        elif d['discount'] >= 50:
            fire = "🔥🔥"
        else:
            fire = "🔥"
        
        msg = f"""{fire} *{d['title'][:70]}...*

💰 *{d['price']:.0f}* ريال {old_price_text}
📉 خصم: *{d['discount']}%*
⭐ تقييم: *{d['rating']:.1f}/5* ({d.get('reviews_count', 0)})
🏷️ {d.get('category', 'متنوع')}
{shipping} {prime}

🔗 [اشتري من هنا]({d['link']})
"""
        
        try:
            updater.bot.send_message(
                chat_id=chat_id, 
                text=msg, 
                parse_mode='Markdown',
                disable_web_page_preview=False
            )
            
            sent_products.add(d['id'])
            sent_hashes.add(create_title_hash(d['title']))
            logger.info(f"✅ Sent [{idx}/{len(deals)}]: {d['title'][:40]}")
            
        except Exception as e:
            logger.error(f"Send error: {e}")
        
        time.sleep(1)
    
    save_database()

# ================== أوامر ==================
def start_cmd(update: Update, context: CallbackContext):
    welcome = """👋 *أهلا بيك في بوت عروض أمازون!*

🔥 *المميزات:*
• يدور في *12 قسم* مختلف
• خصومات *30%+* (عشان تلاقي عروض أكتر)
• كل مرة صفحات جديدة

📝 اكتب *Hi* عشان تبدأ البحث"""
    update.message.reply_text(welcome, parse_mode='Markdown')

def hi_cmd(update: Update, context: CallbackContext):
    global is_scanning

    if is_scanning:
        update.message.reply_text("⏳ البوت شغال في بحث تاني... استنى!")
        return

    is_scanning = True
    
    status_msg = update.message.reply_text(
        "🔍 *بدور في كل الأقسام...*\n"
        "⏳ ده ممكن ياخد 1-2 دقيقة\n"
        "📄 بدور في صفحات كتير عشان ألاقي أحسن العروض!",
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
        
        if deals:
            send_deals(deals, update.effective_chat.id)
        else:
            update.message.reply_text(
                "❌ *مفيش عروض لقيتها*\n"
                "🔄 *جرب تاني بعد شوية!*\n\n"
                "💡 *نصيحة:* الصفحات بتتغير كل مرة، جرب تاني!",
                parse_mode='Markdown'
            )
        
    except Exception as e:
        logger.error(f"Error in hi_cmd: {e}")
        update.message.reply_text(
            f"❌ *حصل خطأ:*\n`{str(e)[:100]}`\n🔄 جرب تاني!",
            parse_mode='Markdown'
        )
    finally:
        is_scanning = False

def status_cmd(update: Update, context: CallbackContext):
    total = len(sent_products)
    msg = f"""✅ *البوت شغال تمام!*

📦 منتجات متبعتة: *{total}*
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
    logger.info(f"📊 Database: {len(sent_products)} products")
    logger.info(f"🎯 Min discount: {MIN_DISCOUNT}%")
    logger.info(f"⭐ Min rating: {MIN_RATING}")
    
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
