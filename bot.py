import os
import re
import json
import logging
import requests
import cloudscraper
from datetime import datetime
from bs4 import BeautifulSoup
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from flask import Flask
from fake_useragent import UserAgent
from difflib import SequenceMatcher
import time
import random
import asyncio
import hashlib
import threading

# ========== Logging ==========
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== الإعدادات ==========
TELEGRAM_BOT_TOKEN = "8769441239:AAEgX3uBbtWc_hHcqs0lmQ50AqKJGOWV6Ok"
TELEGRAM_CHAT_ID = "432826122"

# ========== المتغيرات العامة ==========
app = Flask(__name__)
ua = UserAgent()
sent_products = set()
sent_hashes = set()
is_scanning = False

# ========== قاعدة البيانات ==========
def load_database():
    global sent_products, sent_hashes
    try:
        if os.path.exists('bot_database.json'):
            with open('bot_database.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
                sent_products = set(data.get('ids', []))
                sent_hashes = set(data.get('hashes', []))
                logger.info(f"📦 Loaded: {len(sent_products)} products")
    except Exception as e:
        logger.error(f"Error loading DB: {e}")

def save_database():
    try:
        with open('bot_database.json', 'w', encoding='utf-8') as f:
            json.dump({
                'ids': list(sent_products),
                'hashes': list(sent_hashes)
            }, f)
    except Exception as e:
        logger.error(f"Error saving DB: {e}")

# ========== دوال المساعدة ==========
def extract_asin(link):
    if not link:
        return None
    patterns = [
        r'/dp/([A-Z0-9]{10})',
        r'/gp/product/([A-Z0-9]{10})',
        r'product/([A-Z0-9]{10})',
    ]
    for p in patterns:
        match = re.search(p, link, re.I)
        if match:
            asin = match.group(1).upper()
            if len(asin) == 10:
                return asin
    return None

def create_title_hash(title):
    clean = re.sub(r'[^\w\s]', '', title.lower())
    clean = re.sub(r'\s+', ' ', clean).strip()
    clean = re.sub(r'\d+', '', clean)
    stop_words = ['amazon', 'saudi', 'ريال', 'sar', 'new', 'جديد', 'shipped', 'شحن']
    for word in stop_words:
        clean = clean.replace(word, '')
    signature = clean[:30].strip()
    return hashlib.md5(signature.encode()).hexdigest()[:16]

def is_similar_product(title):
    new_hash = create_title_hash(title)
    if new_hash in sent_hashes:
        return True
    for existing_hash in list(sent_hashes)[-200:]:
        if new_hash[:10] == existing_hash[:10]:
            return True
    return False

def get_product_id(deal):
    asin = extract_asin(deal.get('link', ''))
    if asin:
        return f"ASIN_{asin}"
    key = f"{deal.get('title', '')}_{deal.get('price', 0)}"
    return f"HASH_{hashlib.md5(key.encode()).hexdigest()[:12]}"

def parse_rating(text):
    if not text:
        return 0
    match = re.search(r'(\d+\.?\d*)', str(text))
    return float(match.group(1)) if match else 0

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
            time.sleep(random.uniform(2, 4))
            r = session.get(url, timeout=25)
            if r.status_code == 200:
                return r.text
            time.sleep(3)
        except Exception as e:
            logger.warning(f"Attempt {i+1} failed: {e}")
    return None

# ========== البحث ==========
def search_all_deals():
    all_deals = []
    session = create_session()
    
    categories = [
        ("https://www.amazon.sa/gp/bestsellers/fashion", "👕 Fashion Best Seller", True),
        ("https://www.amazon.sa/gp/bestsellers/beauty", "💄 Beauty Best Seller", True),
        ("https://www.amazon.sa/gp/bestsellers/shoes", "👟 Shoes Best Seller", True),
        ("https://www.amazon.sa/gp/bestsellers/apparel", "👔 Apparel Best Seller", True),
        ("https://www.amazon.sa/s?k=adidas&rh=p_8%3A30-99", "👟 Adidas", False),
        ("https://www.amazon.sa/s?k=nike&rh=p_8%3A30-99", "👟 Nike", False),
        ("https://www.amazon.sa/s?k=puma&rh=p_8%3A30-99", "👟 Puma", False),
        ("https://www.amazon.sa/s?k=reebok&rh=p_8%3A30-99", "👟 Reebok", False),
        ("https://www.amazon.sa/s?k=skechers&rh=p_8%3A30-99", "👟 Skechers", False),
        ("https://www.amazon.sa/s?k=new+balance&rh=p_8%3A30-99", "👟 New Balance", False),
        ("https://www.amazon.sa/s?k=under+armour&rh=p_8%3A30-99", "👟 Under Armour", False),
        ("https://www.amazon.sa/s?k=calvin+klein&rh=p_8%3A30-99", "👔 Calvin Klein", False),
        ("https://www.amazon.sa/s?k=tommy+hilfiger&rh=p_8%3A30-99", "👔 Tommy Hilfiger", False),
        ("https://www.amazon.sa/s?k=lacoste&rh=p_8%3A30-99", "🐊 Lacoste", False),
        ("https://www.amazon.sa/s?k=guess&rh=p_8%3A30-99", "👜 Guess", False),
        ("https://www.amazon.sa/s?k=levis&rh=p_8%3A30-99", "👖 Levi's", False),
        ("https://www.amazon.sa/s?k=casio+watch&rh=p_8%3A30-99", "⌚ Casio", False),
        ("https://www.amazon.sa/s?k=fossil+watch&rh=p_8%3A30-99", "⌚ Fossil", False),
        ("https://www.amazon.sa/s?k=ray+ban&rh=p_8%3A30-99", "🕶️ Ray Ban", False),
        ("https://www.amazon.sa/s?k=loreal&rh=p_8%3A30-99", "💄 L'Oreal", False),
        ("https://www.amazon.sa/s?k=maybelline&rh=p_8%3A30-99", "💄 Maybelline", False),
        ("https://www.amazon.sa/s?k=nyx&rh=p_8%3A30-99", "💄 NYX", False),
        ("https://www.amazon.sa/s?k=mac+makeup&rh=p_8%3A30-99", "💄 MAC", False),
        ("https://www.amazon.sa/s?k=nivea&rh=p_8%3A30-99", "🧴 Nivea", False),
        ("https://www.amazon.sa/s?k=adidas+bag&rh=p_8%3A30-99", "🎒 Adidas Bag", False),
        ("https://www.amazon.sa/s?k=nike+bag&rh=p_8%3A30-99", "🎒 Nike Bag", False),
        ("https://www.amazon.sa/s?k=handbag&rh=p_8%3A30-99", "👜 Handbag", False),
        ("https://www.amazon.sa/gp/goldbox", "🔥 Goldbox", False),
        ("https://www.amazon.sa/deals/fashion", "👕 Fashion Deals", False),
        ("https://www.amazon.sa/deals/beauty", "💄 Beauty Deals", False),
    ]
    
    for url, cat_name, is_best_seller in categories:
        try:
            logger.info(f"🔍 [{cat_name}]")
            html = fetch_page(session, url)
            if not html:
                continue
            
            soup = BeautifulSoup(html, 'html.parser')
            
            items = []
            if is_best_seller:
                items.extend(soup.find_all('li', class_='zg-item-immersion'))
                items.extend(soup.find_all('div', class_='p13n-sc-uncoverable-faceout'))
            
            items.extend(soup.find_all('div', {'data-component-type': 's-search-result'}))
            items.extend(soup.find_all('div', {'data-testid': 'deal-card'}))
            items.extend(soup.find_all('div', class_='a-section'))
            
            logger.info(f"   Found {len(items)} items")
            
            for item in items:
                try:
                    deal = parse_item(item, cat_name, is_best_seller)
                    if deal:
                        all_deals.append(deal)
                except:
                    continue
            
            time.sleep(random.uniform(2, 5))
            
        except Exception as e:
            logger.error(f"Error in {cat_name}: {e}")
    
    logger.info(f"✅ Total: {len(all_deals)}")
    return all_deals

def parse_item(item, category, is_best_seller):
    price = None
    for sel in ['.a-price-whole', '.a-price .a-offscreen']:
        el = item.select_one(sel)
        if el:
            try:
                txt = el.text.replace(',', '').replace('ريال', '').strip()
                match = re.search(r'[\d,]+\.?\d*', txt)
                if match:
                    price = float(match.group().replace(',', ''))
                    break
            except:
                pass
    
    if not price or price <= 0:
        return None
    
    old_price = 0
    discount = 0
    
    old_el = item.find('span', class_='a-text-price')
    if old_el:
        txt = old_el.get_text()
        match = re.search(r'[\d,]+\.?\d*', txt.replace(',', ''))
        if match:
            try:
                old_price = float(match.group())
                if old_price > price:
                    discount = int(((old_price - price) / old_price) * 100)
            except:
                pass
    
    if discount == 0:
        badge = item.find(string=re.compile(r'(\d+)%'))
        if badge:
            match = re.search(r'(\d+)', str(badge))
            if match:
                discount = int(match.group())
                old_price = price / (1 - discount/100)
    
    title = "Unknown"
    for sel in ['h2 a span', 'h2 span', '.a-size-mini span', 
                '.a-size-base-plus', '.p13n-sc-truncated',
                '[data-testid="product-title"]']:
        el = item.select_one(sel)
        if el:
            title = el.text.strip()
            if len(title) > 5:
                break
    
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
    
    img = ""
    for sel in ['img.s-image', 'img[src]']:
        el = item.select_one(sel)
        if el:
            img = el.get('src', '') or el.get('data-src', '')
            if img.startswith('http'):
                break
    
    rating = 0
    reviews = 0
    
    rate_el = item.find('span', class_='a-icon-alt')
    if rate_el:
        rating = parse_rating(rate_el.text)
    
    rev_el = item.find('span', class_='a-size-base')
    if rev_el:
        match = re.search(r'[\d,]+', rev_el.text)
        if match:
            try:
                reviews = int(match.group().replace(',', ''))
            except:
                pass
    
    return {
        'title': title,
        'price': price,
        'old_price': round(old_price, 2),
        'discount': discount,
        'rating': rating,
        'reviews': reviews,
        'link': link,
        'image': img,
        'category': category,
        'is_best_seller': is_best_seller,
        'id': get_product_id({'title': title, 'link': link, 'price': price})
    }

# ========== الفلترة ==========
def filter_premium_deals(deals):
    filtered = []
    seen_in_run = set()
    
    for deal in deals:
        disc = deal['discount']
        rating = deal['rating']
        is_bs = deal.get('is_best_seller', False)
        pid = deal['id']
        title = deal['title']
        
        min_discount = 60 if is_bs else 65
        has_discount = disc >= min_discount
        has_rating = rating >= 3.5
        is_reasonable = 0.5 < deal['price'] < 5000
        
        if has_discount and has_rating and is_reasonable:
            if pid in sent_products or pid in seen_in_run:
                continue
            
            if is_similar_product(title):
                logger.info(f"🚫 Similar skipped: {title[:40]}")
                continue
            
            seen_in_run.add(pid)
            
            if deal['price'] < 1:
                deal['type'] = '🔥 GLITCH'
            elif is_bs:
                deal['type'] = '⭐ BEST SELLER'
            else:
                deal['type'] = f'💰 {disc}%'
            
            deal['savings'] = round(deal['old_price'] - deal['price'], 2) if deal['old_price'] > 0 else 0
            filtered.append(deal)
    
    filtered.sort(key=lambda x: (
        0 if x.get('is_best_seller') else 1,
        0 if x['type'] == '🔥 GLITCH' else 1,
        -x['discount']
    ))
    
    logger.info(f"🎯 Premium: {len(filtered)}")
    return filtered

# ========== الإرسال ==========
async def send_deals(deals, chat_id):
    global sent_products, sent_hashes, is_scanning
    
    if not deals:
        msg = """
❌ *لا توجد عروض جديدة*

المعايير:
• خصم ≥ 65% 📉
• تقييم ≥ 3.5 ⭐

جرب تاني بعدين!
        """
        await application.bot.send_message(chat_id=chat_id, text=msg, parse_mode='Markdown')
        is_scanning = False
        return
    
    bs = sum(1 for d in deals if d.get('is_best_seller'))
    glitch = sum(1 for d in deals if d['type'] == '🔥 GLITCH')
    
    summary = f"""
🎯 *{len(deals)} صفقات ممتازة!*

📊 التفاصيل:
• ⭐ Best Sellers: {bs}
• 🔥 Glitch: {glitch}
• 💰 خصومات 65%+: {len(deals)-bs-glitch}

⭐ التقييم: ≥ 3.5
📉 الخصم: ≥ 65%
    """
    await application.bot.send_message(chat_id=chat_id, text=summary, parse_mode='Markdown')
    
    for i, d in enumerate(deals, 1):
        savings = f"💵 توفير: {d['savings']:.2f} ريال\n" if d['savings'] > 0 else ""
        old = f"🏷️ قبل: {d['old_price']:.2f} ريال\n" if d['old_price'] > 0 else ""
        rev = f"📝 {d['reviews']:,} مراجعة\n" if d['reviews'] > 0 else ""
        
        msg = f"""
{d['type']} *#{i}*

📦 {d['title'][:120]}

💵 *{d['price']:.2f} ريال*
{old}{savings}📉 خصم: {d['discount']}%
⭐ تقييم: {d['rating']}/5
{rev}📍 {d['category']}

🔗 [Amazon]({d['link']})
        """
        
        try:
            if d['image'].startswith('http'):
                await application.bot.send_photo(chat_id=chat_id, photo=d['image'], 
                                               caption=msg, parse_mode='Markdown')
            else:
                await application.bot.send_message(chat_id=chat_id, text=msg, parse_mode='Markdown')
            
            sent_products.add(d['id'])
            sent_hashes.add(create_title_hash(d['title']))
            await asyncio.sleep(2)
            
        except Exception as e:
            logger.error(f"Error #{i}: {e}")
            try:
                await application.bot.send_message(chat_id=chat_id, text=msg, parse_mode='Markdown')
                sent_products.add(d['id'])
                sent_hashes.add(create_title_hash(d['title']))
                await asyncio.sleep(2)
            except:
                pass
    
    save_database()
    logger.info(f"✅ Done! Total: {len(sent_products)}")
    is_scanning = False

# ========== دوال التلجرام ==========
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("""
👋 *أهلاً بيك في Amazon Premium Bot!*

🎯 أنا ببحث عن:
• خصومات ≥ 65% 📉
• تقييم ≥ 3.5 ⭐  
• Best Sellers 🔥
• كل الماركات الكبيرة

اكتب *Hi* عشان أبدأ البحث!
    """, parse_mode='Markdown')

async def hi_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_scanning, application
    
    chat_id = update.effective_chat.id
    
    if is_scanning:
        await update.message.reply_text("⏳ أنا ببحث دلوقتي... استنى!")
        return
    
    is_scanning = True
    await update.message.reply_text("🔍 *بدأت البحث في كل الأقسام...*", parse_mode='Markdown')
    
    try:
        load_database()
        deals = search_all_deals()
        premium = filter_premium_deals(deals)
        await send_deals(premium, chat_id)
    except Exception as e:
        logger.error(f"Search error: {e}")
        await update.message.reply_text("❌ حصل خطأ! جرب تاني.")
        is_scanning = False

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"""
📊 *الحالة:*

📦 منتجات: {len(sent_products)}
🔍 بحوث: {len(sent_hashes)}
⏰ {datetime.now().strftime('%H:%M:%S')}

اكتب *Hi* للبحث!
    """, parse_mode='Markdown')

async def clear_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global sent_products, sent_hashes
    sent_products.clear()
    sent_hashes.clear()
    save_database()
    await update.message.reply_text("🗑️ *تم المسح!*", parse_mode='Markdown')

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("""
🤔 اكتب:
• *Hi* - للبحث 👈
• /status - الحالة
• /start - المساعدة
    """, parse_mode='Markdown')

# ========== Flask ==========
@app.route('/')
def home():
    return f"""
    <h1>🛍️ Amazon Bot</h1>
    <p>✅ Running</p>
    <p>Products: {len(sent_products)}</p>
    <p>{datetime.now().strftime('%H:%M:%S')}</p>
    """

@app.route('/health')
def health():
    return {"status": "ok", "products": len(sent_products)}

# ========== التشغيل ==========
application = None  # سيتم تعريفه لاحقاً

def run_flask():
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, threaded=True)

def main():
    global application
    
    load_database()
    logger.info(f"🚀 Starting | Products: {len(sent_products)}")
    
    # إعداد Telegram Application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Handlers
    application.add_handler(CommandHandler("start", start_cmd))
    application.add_handler(CommandHandler("status", status_cmd))
    application.add_handler(CommandHandler("clear", clear_cmd))
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^hi$'), hi_cmd))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown))
    
    # تشغيل Flask في thread منفصل
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("🌐 Flask started")
    
    # تشغيل Telegram (blocking)
    logger.info("🤖 Telegram bot starting...")
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
