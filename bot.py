import os
import re
import json
import logging
import cloudscraper
import time
import random
import hashlib
import threading
from bs4 import BeautifulSoup
from telegram import Bot, Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from fake_useragent import UserAgent

# ====== CONFIG ======
TELEGRAM_BOT_TOKEN = "8769441239:AAEgX3uBbtWc_hHcqs0lmQ50AqKJGOWV6Ok"
TELEGRAM_CHAT_ID = "432826122"

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ====== DATABASE ======
sent_products = set()
sent_hashes = set()
ua = UserAgent()

def load_database():
    global sent_products, sent_hashes
    if os.path.exists('bot_database.json'):
        try:
            with open('bot_database.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
                sent_products = set(data.get('ids', []))
                sent_hashes = set(data.get('hashes', []))
        except Exception as e:
            logger.error(f"Error loading DB: {e}")

def save_database():
    try:
        with open('bot_database.json', 'w', encoding='utf-8') as f:
            json.dump({'ids': list(sent_products), 'hashes': list(sent_hashes)}, f)
    except Exception as e:
        logger.error(f"Error saving DB: {e}")

# ====== HELPERS ======
def extract_asin(link):
    patterns = [r'/dp/([A-Z0-9]{10})', r'/gp/product/([A-Z0-9]{10})', r'product/([A-Z0-9]{10})']
    for p in patterns:
        match = re.search(p, link)
        if match:
            return match.group(1).upper()
    return None

def create_title_hash(title):
    clean = re.sub(r'[^\w\s]', '', title.lower())
    clean = re.sub(r'\s+', ' ', clean).strip()
    clean = re.sub(r'\d+', '', clean)
    for word in ['amazon', 'saudi', 'ريال', 'sar', 'new', 'جديد', 'shipped', 'شحن']:
        clean = clean.replace(word, '')
    return hashlib.md5(clean[:30].encode()).hexdigest()[:16]

def is_similar_product(title):
    new_hash = create_title_hash(title)
    if new_hash in sent_hashes:
        return True
    return False

def get_product_id(deal):
    asin = extract_asin(deal.get('link', ''))
    if asin:
        return f"ASIN_{asin}"
    key = f"{deal.get('title', '')}_{deal.get('price', 0)}"
    return f"HASH_{hashlib.md5(key.encode()).hexdigest()[:12]}"

# ====== AMAZON SCRAPER ======
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

def fetch_page(session, url):
    for i in range(3):
        try:
            time.sleep(random.uniform(1, 2))
            r = session.get(url, timeout=25)
            if r.status_code == 200:
                return r.text
            time.sleep(2)
        except Exception as e:
            logger.warning(f"Attempt {i+1} failed: {e}")
    return None

def parse_item(item, category, is_best_seller):
    try:
        title = "Unknown"
        for sel in ['h2 a span', 'h2 span', '.a-size-mini span', '.a-size-base-plus', '.p13n-sc-truncated', '.a-size-medium']:
            el = item.select_one(sel)
            if el:
                title = el.text.strip()
                if len(title) > 5:
                    break
        
        price = None
        for sel in ['.a-price-whole', '.a-price .a-offscreen', '.a-price-range', '.a-price']:
            el = item.select_one(sel)
            if el:
                txt = el.text.replace(',', '').replace('ريال', '').strip()
                match = re.search(r'[\d,]+\.?\d*', txt)
                if match:
                    price = float(match.group().replace(',', ''))
                    break
        if not price or price <= 0:
            return None
        
        link = ""
        a = item.find('a', href=True)
        if a:
            href = a['href']
            if href.startswith('/'):
                link = f"https://www.amazon.sa{href}"
            else:
                link = href
        
        old_price = 0
        discount = 0
        old_el = item.find('span', class_='a-text-price')
        if old_el:
            txt = old_el.get_text()
            match = re.search(r'[\d,]+\.?\d*', txt.replace(',', ''))
            if match:
                old_price = float(match.group())
                if old_price > price:
                    discount = int(((old_price - price)/old_price)*100)
        
        return {
            'title': title,
            'price': price,
            'old_price': old_price,
            'discount': discount,
            'link': link,
            'category': category
        }
    except Exception as e:
        logger.error(f"parse_item error: {e}")
        return None

def get_amazon_deals(category_url, cat_name, limit=5):
    session = create_session()
    html = fetch_page(session, category_url)
    if not html:
        return []
    
    soup = BeautifulSoup(html, 'html.parser')
    items = soup.find_all('div', {'data-component-type': 's-search-result'})
    
    deals = []
    for item in items[:limit]:
        deal = parse_item(item, cat_name, False)
        if deal:
            deals.append(deal)
    
    return deals

# ====== TELEGRAM HANDLERS ======
def start(update: Update, context: CallbackContext):
    welcome_msg = """
👋 *أهلاً بيك في بوت عروض أمازون السعودية!*

الأوامر المتاحة:
🔹 /deals - جلب أحدث العروض
🔹 /electronics - عروض الإلكترونيات
🔹 /best - الأكثر مبيعاً
🔹 /help - المساعدة

أو ابعت *"hi"* أو *"مرحبا"* و هرد عليك! 😊
"""
    update.message.reply_text(welcome_msg, parse_mode='Markdown')

def help_command(update: Update, context: CallbackContext):
    help_msg = """
📋 *طريقة الاستخدام:*

• اكتب أي حاجة و هرد عليك
• /deals - عروض عامة
• /electronics - إلكترونيات
• /best - الأكثر مبيعاً

للدعم: @YourUsername
"""
    update.message.reply_text(help_msg, parse_mode='Markdown')

def handle_text(update: Update, context: CallbackContext):
    text = update.message.text.lower().strip()
    user = update.message.from_user.first_name
    
    # ردود على التحيات
    greetings = ['hi', 'hello', 'مرحبا', 'اهلا', 'أهلا', 'هلا', 'سلام', 'هاي']
    if any(g in text for g in greetings):
        reply = f"أهلاً بيك يا *{user}*! 👋\n\nجرب /deals عشان تشوف أحدث العروض 🛍️"
        update.message.reply_text(reply, parse_mode='Markdown')
        return
    
    # ردود على الشكر
    thanks = ['شكرا', 'شكراً', 'thanks', 'thank you', 'ميرسي']
    if any(t in text for t in thanks):
        update.message.reply_text("العفو! 😊 أي وقت تحتاج حاجة ابعتلي")
        return
    
    # ردود على الوداع
    bye = ['باي', 'مع السلامة', 'bye', 'goodbye', 'سلام']
    if any(b in text for b in bye):
        update.message.reply_text("مع السلامة! 👋 رجع بالسلامة")
        return
    
    # رد افتراضي
    update.message.reply_text(
        f"مش فاهم '{text}' 😅\n\nجرب: /deals أو /help",
        parse_mode='Markdown'
    )

def send_deal_message(update, deal, index=None):
    prefix = f"#{index}\n" if index else ""
    msg = f"{prefix}📌 *{deal['title']}*\n\n"
    msg += f"💰 *السعر:* {deal['price']} ريال"
    
    if deal['discount'] > 0:
        msg += f"\n💸 *خصم:* {deal['discount']}%\n"
        msg += f"~~{deal['old_price']}~~ ريال"
    
    if deal.get('link'):
        msg += f"\n\n🔗 [افتح المنتج]({deal['link']})"
    
    update.message.reply_text(msg, parse_mode='Markdown', disable_web_page_preview=False)

def deals_command(update: Update, context: CallbackContext):
    update.message.reply_text("🔍 بجيب العروض... استنى شوية ⏳")
    
    urls = [
        ("https://www.amazon.sa/deals", "🛍️ عروض عامة"),
        ("https://www.amazon.sa/deals/electronics", "📱 إلكترونيات")
    ]
    
    total_sent = 0
    for url, cat_name in urls:
        deals = get_amazon_deals(url, cat_name, limit=3)
        for i, deal in enumerate(deals, 1):
            send_deal_message(update, deal, i)
            total_sent += 1
            time.sleep(0.5)
    
    if total_sent == 0:
        update.message.reply_text("❌ مقدرتش أجيب عروض دلوقتي، جرب تاني بعدين")
    else:
        update.message.reply_text(f"✅ خلصت! جبتلك {total_sent} عروض")

def electronics_command(update: Update, context: CallbackContext):
    update.message.reply_text("📱 بجيب عروض الإلكترونيات...")
    
    deals = get_amazon_deals(
        "https://www.amazon.sa/deals/electronics",
        "📱 إلكترونيات",
        limit=5
    )
    
    if not deals:
        update.message.reply_text("❌ مفيش عروض دلوقتي")
        return
    
    for i, deal in enumerate(deals, 1):
        send_deal_message(update, deal, i)
        time.sleep(0.5)

def best_sellers_command(update: Update, context: CallbackContext):
    update.message.reply_text("🏆 بجيب الأكثر مبيعاً...")
    
    deals = get_amazon_deals(
        "https://www.amazon.sa/gp/bestsellers",
        "🏆 الأكثر مبيعاً",
        limit=5
    )
    
    if not deals:
        update.message.reply_text("❌ مقدرتش أجيب البيانات")
        return
    
    for i, deal in enumerate(deals, 1):
        send_deal_message(update, deal, i)
        time.sleep(0.5)

# ====== AUTO SEND (Background) ======
def auto_send_deals(context: CallbackContext):
    """بعت عروض تلقائي كل فترة للقناة المحددة"""
    logger.info("Running auto send...")
    
    urls = [
        ("https://www.amazon.sa/deals/electronics", "📱 Electronics", True),
    ]
    
    session = create_session()
    bot = context.bot
    
    for url, cat_name, is_best in urls:
        html = fetch_page(session, url)
        if not html:
            continue
        
        soup = BeautifulSoup(html, 'html.parser')
        items = soup.find_all('div', {'data-component-type': 's-search-result'})
        
        sent_count = 0
        for item in items[:3]:  # أول 3 بس
            deal = parse_item(item, cat_name, is_best)
            if not deal:
                continue
            
            prod_id = get_product_id(deal)
            title_hash = create_title_hash(deal['title'])
            
            # تخطي المنتجات المكررة
            if prod_id in sent_products or title_hash in sent_hashes:
                continue
            
            # إرسال للقناة
            msg = f"📌 *{deal['title']}*\n\n"
            msg += f"💰 {deal['price']} ريال"
            if deal['discount'] > 0:
                msg += f"\n💸 خصم {deal['discount']}%"
            msg += f"\n\n🔗 [الرابط]({deal['link']})"
            
            try:
                bot.send_message(
                    chat_id=TELEGRAM_CHAT_ID,
                    text=msg,
                    parse_mode='Markdown',
                    disable_web_page_preview=False
                )
                sent_products.add(prod_id)
                sent_hashes.add(title_hash)
                sent_count += 1
                time.sleep(1)
            except Exception as e:
                logger.error(f"Send error: {e}")
        
        logger.info(f"Auto sent {sent_count} deals")
    
    save_database()

# ====== MAIN ======
def main():
    load_database()
    
    updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    
    # Commands
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_command))
    dp.add_handler(CommandHandler("deals", deals_command))
    dp.add_handler(CommandHandler("electronics", electronics_command))
    dp.add_handler(CommandHandler("best", best_sellers_command))
    
    # Messages
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))
    
    # Job Queue للإرسال التلقائي (كل ساعة)
    jq = updater.job_queue
    jq.run_repeating(auto_send_deals, interval=3600, first=60)
    
    logger.info("🤖 Bot started!")
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
