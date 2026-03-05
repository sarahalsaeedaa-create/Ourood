import os
import re
import json
import logging
import requests
import cloudscraper
from datetime import datetime
from bs4 import BeautifulSoup
from telegram import Bot
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask
from fake_useragent import UserAgent
import time
import random
import asyncio
import hashlib

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== الإعدادات ==========
TELEGRAM_BOT_TOKEN = "8769441239:AAEgX3uBbtWc_hHcqs0lmQ50AqKJGOWV6Ok"
TELEGRAM_CHAT_ID = "432826122"

bot = Bot(token=TELEGRAM_BOT_TOKEN)
app = Flask(__name__)

ua = UserAgent()
sent_products = set()

def load_sent_products():
    global sent_products
    try:
        if os.path.exists('sent_products.json'):
            with open('sent_products.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
                sent_products = set(data.get('ids', []))
                logger.info(f"Loaded {len(sent_products)} products")
    except Exception as e:
        logger.error(f"Error loading: {e}")
        sent_products = set()

def save_sent_products():
    try:
        with open('sent_products.json', 'w', encoding='utf-8') as f:
            json.dump({'ids': list(sent_products)}, f)
    except Exception as e:
        logger.error(f"Error saving: {e}")

def extract_asin(link):
    """استخراج ASIN من أي رابط Amazon"""
    if not link:
        return None
    
    # أنماط ASIN
    patterns = [
        r'/dp/([A-Z0-9]{10})',
        r'/gp/product/([A-Z0-9]{10})',
        r'/product/([A-Z0-9]{10})',
        r'dp%2F([A-Z0-9]{10})',  # encoded
        r'/([A-Z0-9]{10})/',  # بعد slash
    ]
    
    for pattern in patterns:
        match = re.search(pattern, link, re.IGNORECASE)
        if match:
            asin = match.group(1).upper()
            # التحقق إنه ASIN صحيح (10 حروف/أرقام)
            if len(asin) == 10 and re.match(r'^[A-Z0-9]+$', asin):
                return asin
    
    return None

def normalize_title(title):
    """تنظيف العنوان للمقارنة"""
    # إزالة المسافات الزيادة والرموز
    title = re.sub(r'\s+', ' ', title.lower().strip())
    # إزالة الكلمات الشائعة المتغيرة
    stop_words = ['amazon', 'saudi', 'السعودية', 'prime', 'free shipping', 'شحن مجاني']
    for word in stop_words:
        title = title.replace(word, '')
    return title.strip()[:50]  # أول 50 حرف

def get_product_id(deal):
    """إنشاء ID فريد للمنتج"""
    # 1. جرب استخراج ASIN
    asin = extract_asin(deal.get('link', ''))
    if asin:
        return f"ASIN_{asin}"
    
    # 2. استخدم عنوان + سعر (normalized)
    title_key = normalize_title(deal.get('title', ''))
    price = str(deal.get('price', ''))
    
    # 3. إنشاء hash
    unique_string = f"{title_key}_{price}"
    hash_id = hashlib.md5(unique_string.encode()).hexdigest()[:12]
    
    return f"HASH_{hash_id}"

def create_session():
    session = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True, 'version': '120.0'},
        delay=10
    )
    headers = {
        'User-Agent': ua.random,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'ar-SA,ar;q=0.9,en;q=0.8',
        'Referer': 'https://www.amazon.sa/',
    }
    session.headers.update(headers)
    return session

def get_deals_page(session, url):
    for attempt in range(3):
        try:
            time.sleep(random.uniform(2, 5))
            response = session.get(url, timeout=30)
            if response.status_code == 200:
                return response.text
            time.sleep(5)
        except Exception as e:
            logger.error(f"Attempt {attempt + 1}: {e}")
            time.sleep(3)
    return None

def search_amazon_sa_deals():
    deals = []
    session = create_session()
    
    deal_urls = [
        "https://www.amazon.sa/gp/goldbox",
        "https://www.amazon.sa/deals/fashion",
        "https://www.amazon.sa/deals/beauty",
        "https://www.amazon.sa/s?k=adidas&rh=p_8%3A30-99",
        "https://www.amazon.sa/s?k=nike&rh=p_8%3A30-99",
        "https://www.amazon.sa/s?k=puma&rh=p_8%3A30-99",
        "https://www.amazon.sa/s?k=calvin+klein&rh=p_8%3A30-99",
        "https://www.amazon.sa/s?k=tommy+hilfiger&rh=p_8%3A30-99",
        "https://www.amazon.sa/s?k=lacoste&rh=p_8%3A30-99",
        "https://www.amazon.sa/s?k=reebok&rh=p_8%3A30-99",
        "https://www.amazon.sa/s?k=skechers&rh=p_8%3A30-99",
        "https://www.amazon.sa/s?k=new+balance&rh=p_8%3A30-99",
        "https://www.amazon.sa/s?k=under+armour&rh=p_8%3A30-99",
        "https://www.amazon.sa/gp/bestsellers/fashion",
        "https://www.amazon.sa/gp/bestsellers/beauty",
        "https://www.amazon.sa/gp/bestsellers/shoes",
        "https://www.amazon.sa/s?k=loreal&rh=p_8%3A30-99",
        "https://www.amazon.sa/s?k=maybelline&rh=p_8%3A30-99",
        "https://www.amazon.sa/s?k=casio&rh=p_8%3A30-99",
        "https://www.amazon.sa/s?k=fossil&rh=p_8%3A30-99",
        "https://www.amazon.sa/s?k=handbag&rh=p_8%3A30-99",
    ]
    
    for url in deal_urls:
        try:
            logger.info(f"Fetching: {url}")
            html = get_deals_page(session, url)
            if not html:
                continue
            
            soup = BeautifulSoup(html, 'html.parser')
            
            items = []
            items.extend(soup.find_all('div', {'data-testid': 'deal-card'}))
            items.extend(soup.find_all('div', {'data-component-type': 's-search-result'}))
            items.extend(soup.find_all('div', class_='a-section'))
            items.extend(soup.find_all('li', class_='zg-item-immersion'))
            
            logger.info(f"Found {len(items)} items")
            
            for item in items:
                try:
                    # استخراج السعر
                    price = None
                    price_whole = item.find('span', class_='a-price-whole')
                    if price_whole:
                        try:
                            price = float(price_whole.text.replace(',', '').replace('ريال', '').strip())
                        except:
                            pass
                    
                    if not price:
                        price_off = item.find('span', class_='a-offscreen')
                        if price_off:
                            match = re.search(r'[\d,]+\.?\d*', price_off.text.replace(',', ''))
                            if match:
                                try:
                                    price = float(match.group())
                                except:
                                    pass
                    
                    if not price or price <= 0:
                        continue
                    
                    # استخراج السعر القديم والخصم
                    old_price = 0
                    discount = 0
                    
                    old_elem = item.find('span', class_='a-text-price')
                    if old_elem:
                        old_text = old_elem.find('span', class_='a-offscreen')
                        if old_text:
                            match = re.search(r'[\d,]+\.?\d*', old_text.text.replace(',', ''))
                            if match:
                                try:
                                    old_price = float(match.group())
                                    if old_price > price:
                                        discount = int(((old_price - price) / old_price) * 100)
                                except:
                                    pass
                    
                    # Badge خصم
                    if discount == 0:
                        badge = item.find('span', class_=re.compile('a-badge-text'))
                        if badge:
                            match = re.search(r'(\d+)%', badge.text)
                            if match:
                                discount = int(match.group(1))
                                old_price = price / (1 - discount/100)
                    
                    # العنوان
                    title = "Unknown"
                    for sel in ['h2 a span', 'h2 span', '.a-size-mini span', '.a-size-base-plus', '.p13n-sc-truncated']:
                        elem = item.select_one(sel)
                        if elem:
                            title = elem.text.strip()
                            if len(title) > 3:
                                break
                    
                    # الرابط
                    link = ""
                    link_elem = item.find('a', href=True)
                    if link_elem:
                        href = link_elem['href']
                        if href.startswith('/'):
                            link = f'https://www.amazon.sa{href}'
                        elif 'amazon.sa' in href:
                            link = href
                        else:
                            # استخراج ASIN وعمل رابط نظيف
                            asin = extract_asin(href)
                            if asin:
                                link = f'https://www.amazon.sa/dp/{asin}'
                    
                    # الصورة
                    image = ""
                    for sel in ['img.s-image', 'img[src]']:
                        img = item.select_one(sel)
                        if img:
                            image = img.get('src', '') or img.get('data-src', '')
                            if image.startswith('http'):
                                break
                    
                    # التقييم
                    rating = ""
                    rate_elem = item.find('span', class_='a-icon-alt')
                    if rate_elem:
                        match = re.search(r'([\d.]+)', rate_elem.text)
                        if match:
                            rating = match.group(1)
                    
                    # الفئة
                    cat = "عام"
                    if 'adidas' in url.lower(): cat = "👟 Adidas"
                    elif 'nike' in url.lower(): cat = "👟 Nike"
                    elif 'puma' in url.lower(): cat = "👟 Puma"
                    elif 'shoes' in url.lower() or 'fashion' in url.lower(): cat = "👕 Fashion"
                    elif 'beauty' in url.lower(): cat = "💄 Beauty"
                    elif 'bestseller' in url.lower(): cat = "⭐ Best Seller"
                    
                    deal = {
                        'title': title,
                        'price': price,
                        'old_price': round(old_price, 2) if old_price > 0 else 0,
                        'discount': discount,
                        'link': link,
                        'image': image,
                        'rating': rating,
                        'category': cat,
                    }
                    
                    # ✅ إنشاء ID فريد
                    deal['id'] = get_product_id(deal)
                    deals.append(deal)
                    
                except Exception as e:
                    continue
            
            time.sleep(random.uniform(3, 6))
            
        except Exception as e:
            logger.error(f"Error: {e}")
            continue
    
    logger.info(f"Total collected: {len(deals)}")
    return deals

def filter_glitch_deals(deals):
    filtered = []
    seen_in_this_scan = set()  # ✅ منع التكرار في نفس الـ scan
    
    for deal in deals:
        price = deal['price']
        discount = deal['discount']
        pid = deal['id']
        
        # شروط الفلترة
        is_glitch = price < 1.0 and price > 0
        is_good = discount >= 50
        
        if is_glitch or is_good:
            # ✅ فحص 1: متبعتش قبل كده (من الملف)
            if pid in sent_products:
                continue
            
            # ✅ فحص 2: متكررش في نفس الـ scan
            if pid in seen_in_this_scan:
                continue
            
            seen_in_this_scan.add(pid)
            
            deal['deal_type'] = '🔥 GLITCH' if is_glitch else f'💰 {discount}% OFF'
            deal['savings'] = round(deal['old_price'] - price, 2) if deal['old_price'] > 0 else 0
            filtered.append(deal)
    
    # ترتيب
    filtered.sort(key=lambda x: (0 if x['deal_type'] == '🔥 GLITCH' else 1, -x['discount']))
    
    logger.info(f"New unique: {len(filtered)} (filtered from duplicates)")
    return filtered

async def send_deals_to_telegram(deals):
    global sent_products
    
    if not deals:
        msg = f"""
⏰ *بحث تلقائي - {datetime.now().strftime('%Y-%m-%d %H:%M')}*

🔍 لا توجد عروض جديدة
📦 مخزن: {len(sent_products)} منتج

البحث بعد 10 دقائق...
        """
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg, parse_mode='Markdown')
        return
    
    glitch = sum(1 for d in deals if d['deal_type'] == '🔥 GLITCH')
    
    summary = f"""
🚨 *{len(deals)} عروض جديدة!*
⏰ {datetime.now().strftime('%H:%M')}

🔥 Glitch: {glitch}
💰 خصومات: {len(deals) - glitch}
📦 مخزن: {len(sent_products) + len(deals)}

━━━━━━━━━
    """
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=summary, parse_mode='Markdown')
    
    for i, deal in enumerate(deals, 1):
        savings = f"💵 توفير: {deal['savings']:.2f} ريال\n" if deal['savings'] > 0 else ""
        old = f"🏷️ قبل: {deal['old_price']:.2f} ريال\n" if deal['old_price'] > 0 else ""
        rate = f"⭐ {deal['rating']}/5\n" if deal['rating'] else ""
        
        msg = f"""
{deal['deal_type']} *#{i}*

📦 {deal['title'][:140]}

💵 *{deal['price']:.2f} ريال*
{old}{savings}🔥 خصم: {deal['discount']}%
{rate}📍 {deal['category']}

🔗 [Amazon]({deal['link']})
        """
        
        try:
            if deal['image'].startswith('http'):
                await bot.send_photo(chat_id=TELEGRAM_CHAT_ID, photo=deal['image'], caption=msg, parse_mode='Markdown')
            else:
                await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg, parse_mode='Markdown')
            
            # ✅ حفظ إنه اتبعت
            sent_products.add(deal['id'])
            await asyncio.sleep(2)
            
        except Exception as e:
            logger.error(f"Error {i}: {e}")
            try:
                await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg, parse_mode='Markdown')
                sent_products.add(deal['id'])
                await asyncio.sleep(2)
            except:
                pass
    
    save_sent_products()
    logger.info(f"Saved {len(sent_products)} products")

def job():
    logger.info("="*50)
    logger.info("🔍 Searching...")
    
    try:
        load_sent_products()
        deals = search_amazon_sa_deals()
        
        if deals:
            for d in deals[:3]:
                logger.info(f"Sample: {d['title'][:30]} | ID: {d['id'][:20]}...")
        
        filtered = filter_glitch_deals(deals)
        asyncio.run(send_deals_to_telegram(filtered))
        
        logger.info(f"Sent {len(filtered)} deals")
        
    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        logger.error(traceback.format_exc())

@app.route('/')
def home():
    return f"""
    <h1>🛍️ Amazon Bot</h1>
    <p>✅ Running</p>
    <p>Stored: {len(sent_products)}</p>
    <p>Last: {datetime.now().strftime('%H:%M:%S')}</p>
    <a href="/test"><button>🔍 Search</button></a>
    <a href="/clear"><button>🗑️ Clear</button></a>
    """

@app.route('/test')
def test():
    from threading import Thread
    Thread(target=job).start()
    return "🔍 Started!"

@app.route('/clear')
def clear():
    global sent_products
    sent_products.clear()
    save_sent_products()
    return f"🗑️ Cleared! {len(sent_products)}"

@app.route('/status')
def status():
    return {"stored": len(sent_products), "time": datetime.now().isoformat()}

if __name__ == "__main__":
    load_sent_products()
    
    from apscheduler.schedulers.background import BackgroundScheduler
    scheduler = BackgroundScheduler()
    scheduler.add_job(job, 'interval', minutes=10, id='scan', replace_existing=True)
    scheduler.start()
    
    logger.info(f"🤖 Bot started | Stored: {len(sent_products)}")
    
    import threading
    def start():
        time.sleep(3)
        job()
    threading.Thread(target=start).start()
    
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
