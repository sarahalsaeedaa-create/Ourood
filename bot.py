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

# ========== قاعدة بيانات بسيطة (في الذاكرة) ==========
sent_products = set()  # هنا هنحفظ IDs المنتجات اللي بعتناها

def load_sent_products():
    """تحميل المنتجات اللي اتبعتت من ملف (لو موجود)"""
    global sent_products
    try:
        if os.path.exists('sent_products.json'):
            with open('sent_products.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
                sent_products = set(data.get('ids', []))
                logger.info(f"Loaded {len(sent_products)} previously sent products")
    except Exception as e:
        logger.error(f"Error loading sent products: {e}")
        sent_products = set()

def save_sent_products():
    """حفظ المنتجات اللي اتبعتت"""
    try:
        with open('sent_products.json', 'w', encoding='utf-8') as f:
            json.dump({'ids': list(sent_products)}, f)
    except Exception as e:
        logger.error(f"Error saving sent products: {e}")

def get_product_id(link):
    """استخراج ID المنتج من الرابط"""
    if not link:
        return None
    
    # استخراج ASIN من رابط Amazon
    patterns = [
        r'/dp/([A-Z0-9]{10})',
        r'/gp/product/([A-Z0-9]{10})',
        r'/product/([A-Z0-9]{10})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, link)
        if match:
            return match.group(1)
    
    # لو مفيش ASIN، استخدم hash من العنوان
    return None

# ========== دالة إنشاء Session ==========
def create_session():
    session = cloudscraper.create_scraper(
        browser={
            'browser': 'chrome',
            'platform': 'windows',
            'desktop': True,
            'version': '120.0'
        },
        delay=10
    )
    
    headers = {
        'User-Agent': ua.random,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'ar-SA,ar;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br',
        'Referer': 'https://www.amazon.sa/',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'same-origin',
        'Cache-Control': 'max-age=0',
    }
    
    session.headers.update(headers)
    return session

# ========== دالة جلب الصفحة ==========
def get_deals_page(session, url):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            time.sleep(random.uniform(2, 5))
            response = session.get(url, timeout=30)
            
            if response.status_code == 200:
                return response.text
            elif response.status_code == 503:
                logger.warning(f"Attempt {attempt + 1}: 503")
                time.sleep(5)
            else:
                logger.warning(f"Status {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Attempt {attempt + 1} failed: {e}")
            time.sleep(3)
    
    return None

# ========== دالة البحث في Amazon.sa ==========
def search_amazon_sa_deals():
    deals = []
    session = create_session()
    
    deal_urls = [
        "https://www.amazon.sa/gp/goldbox",
        "https://www.amazon.sa/deals/fashion",
        "https://www.amazon.sa/deals/beauty",
        "https://www.amazon.sa/s?k=adidas+fashion&rh=p_8%3A30-99",
        "https://www.amazon.sa/s?k=nike+fashion&rh=p_8%3A30-99",
        "https://www.amazon.sa/s?k=puma+fashion&rh=p_8%3A30-99",
        "https://www.amazon.sa/s?k=calvin+klein&rh=p_8%3A30-99",
        "https://www.amazon.sa/s?k=tommy+hilfiger&rh=p_8%3A30-99",
        "https://www.amazon.sa/s?k=lacoste&rh=p_8%3A30-99",
        "https://www.amazon.sa/s?k=guess&rh=p_8%3A30-99",
        "https://www.amazon.sa/s?k=adidas+shoes&rh=p_8%3A30-99",
        "https://www.amazon.sa/s?k=nike+shoes&rh=p_8%3A30-99",
        "https://www.amazon.sa/s?k=reebok+shoes&rh=p_8%3A30-99",
        "https://www.amazon.sa/s?k=skechers&rh=p_8%3A30-99",
        "https://www.amazon.sa/s?k=new+balance&rh=p_8%3A30-99",
        "https://www.amazon.sa/s?k=under+armour+shoes&rh=p_8%3A30-99",
        "https://www.amazon.sa/gp/bestsellers/fashion",
        "https://www.amazon.sa/gp/bestsellers/beauty",
        "https://www.amazon.sa/gp/bestsellers/shoes",
        "https://www.amazon.sa/s?k=loreal&rh=p_8%3A30-99",
        "https://www.amazon.sa/s?k=maybelline&rh=p_8%3A30-99",
        "https://www.amazon.sa/s?k=nyx&rh=p_8%3A30-99",
        "https://www.amazon.sa/s?k=mac+makeup&rh=p_8%3A30-99",
        "https://www.amazon.sa/s?k=casio+watch&rh=p_8%3A30-99",
        "https://www.amazon.sa/s?k=fossil+watch&rh=p_8%3A30-99",
        "https://www.amazon.sa/s?k=ray+ban&rh=p_8%3A30-99",
        "https://www.amazon.sa/s?k=adidas+bag&rh=p_8%3A30-99",
        "https://www.amazon.sa/s?k=nike+bag&rh=p_8%3A30-99",
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
            
            logger.info(f"Found {len(items)} items in {url}")
            
            for item in items:
                try:
                    price = None
                    
                    price_whole = item.find('span', class_='a-price-whole')
                    if price_whole:
                        price_text = price_whole.text.replace(',', '').replace('ريال', '').strip()
                        try:
                            price = float(price_text)
                        except:
                            pass
                    
                    if not price:
                        price_off = item.find('span', class_='a-offscreen')
                        if price_off:
                            price_match = re.search(r'[\d,]+\.?\d*', price_off.text.replace(',', ''))
                            if price_match:
                                try:
                                    price = float(price_match.group())
                                except:
                                    pass
                    
                    if not price or price <= 0:
                        continue
                    
                    old_price = 0
                    discount_percent = 0
                    
                    old_price_elem = item.find('span', class_='a-text-price')
                    if old_price_elem:
                        old_text = old_price_elem.find('span', class_='a-offscreen')
                        if old_text:
                            old_match = re.search(r'[\d,]+\.?\d*', old_text.text.replace(',', ''))
                            if old_match:
                                try:
                                    old_price = float(old_match.group())
                                    if old_price > price:
                                        discount_percent = int(((old_price - price) / old_price) * 100)
                                except:
                                    pass
                    
                    if discount_percent == 0:
                        badge = item.find('span', class_=re.compile('a-badge-text|s-coupon-highlight-color'))
                        if badge:
                            badge_text = badge.text
                            discount_match = re.search(r'(\d+)%', badge_text)
                            if discount_match:
                                discount_percent = int(discount_match.group(1))
                                if discount_percent > 0:
                                    old_price = price / (1 - discount_percent/100)
                    
                    title = "Unknown Product"
                    title_selectors = [
                        'h2 a span', 'h2 span', '.a-size-mini span',
                        '.a-size-base-plus', '[data-testid="product-title"]',
                        'a[data-testid="deal-title"]', '.p13n-sc-truncated'
                    ]
                    
                    for selector in title_selectors:
                        title_elem = item.select_one(selector)
                        if title_elem:
                            title = title_elem.text.strip()
                            if len(title) > 3:
                                break
                    
                    link = ""
                    link_elem = item.find('a', href=True)
                    if link_elem:
                        href = link_elem['href']
                        if href.startswith('/'):
                            link = f'https://www.amazon.sa{href}'
                        elif 'amazon.sa' in href:
                            link = href
                        else:
                            link = f'https://www.amazon.sa/dp/{href.split("/dp/")[1].split("/")[0]}' if '/dp/' in href else f'https://www.amazon.sa{href}'
                    
                    image = ""
                    img_selectors = ['img.s-image', 'img[src]', '[data-testid="product-image"] img']
                    for selector in img_selectors:
                        img = item.select_one(selector)
                        if img:
                            image = img.get('src', '') or img.get('data-src', '')
                            if image and image.startswith('http'):
                                break
                    
                    rating = ""
                    rating_elem = item.find('span', class_='a-icon-alt')
                    if rating_elem:
                        rating_match = re.search(r'([\d.]+)', rating_elem.text)
                        if rating_match:
                            rating = rating_match.group(1)
                    
                    category = "عام"
                    if 'adidas' in url.lower():
                        category = "👟 Adidas"
                    elif 'nike' in url.lower():
                        category = "👟 Nike"
                    elif 'shoes' in url.lower():
                        category = "👟 أحذية"
                    elif 'watch' in url.lower():
                        category = "⌚ ساعات"
                    elif 'bag' in url.lower() or 'handbag' in url:
                        category = "👜 شنط"
                    elif 'beauty' in url.lower() or 'makeup' in url:
                        category = "💄 Beauty"
                    elif 'fashion' in url.lower():
                        category = "👕 Fashion"
                    elif 'bestseller' in url.lower():
                        category = "⭐ Best Seller"
                    
                    # ✅ استخراج ID المنتج
                    product_id = get_product_id(link)
                    if not product_id:
                        # لو مفيش ID، استخدم hash من العنوان والسعر
                        product_id = f"{hash(title + str(price))}"
                    
                    deals.append({
                        'id': product_id,
                        'title': title,
                        'price': price,
                        'old_price': round(old_price, 2) if old_price > 0 else 0,
                        'discount': discount_percent,
                        'link': link,
                        'image': image,
                        'rating': rating,
                        'category': category,
                        'source': url
                    })
                    
                except Exception as e:
                    continue
            
            time.sleep(random.uniform(3, 6))
            
        except Exception as e:
            logger.error(f"Error with {url}: {e}")
            continue
    
    logger.info(f"Total raw deals: {len(deals)}")
    return deals

# ========== التصفية ==========
def filter_glitch_deals(deals):
    filtered = []
    new_deals_count = 0
    
    for deal in deals:
        price = deal['price']
        discount = deal['discount']
        product_id = deal['id']
        
        # شرط 1: سعر < 1 ريال
        is_glitch = price < 1.0 and price > 0
        
        # شرط 2: خصم >= 50%
        is_good_deal = discount >= 50
        
        if is_glitch or is_good_deal:
            # ✅ التحقق إن المنتج ماتبعتش قبل كده
            if product_id in sent_products:
                continue  # سكيب لو اتبعت قبل كده
            
            deal['deal_type'] = '🔥 GLITCH' if is_glitch else f'💰 {discount}% OFF'
            deal['savings'] = round(deal['old_price'] - price, 2) if deal['old_price'] > 0 else 0
            filtered.append(deal)
            new_deals_count += 1
    
    # ترتيب
    filtered.sort(key=lambda x: (0 if x['deal_type'] == '🔥 GLITCH' else 1, -x['discount']))
    
    logger.info(f"New unique deals to send: {new_deals_count}")
    return filtered

# ========== إرسال Telegram ==========
async def send_deals_to_telegram(deals):
    global sent_products
    
    if not deals:
        message = f"""
⏰ *بحث تلقائي - {datetime.now().strftime('%Y-%m-%d %H:%M')}*

🔍 لا توجد عروض جديدة تطابق المعايير
📦 إجمالي المنتجات المخزنة: {len(sent_products)}

سيتم البحث مرة أخرى بعد 10 دقائق...
        """
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message,
            parse_mode='Markdown'
        )
        logger.info(f"No new deals. Total stored: {len(sent_products)}")
        return
    
    glitch_count = sum(1 for d in deals if d['deal_type'] == '🔥 GLITCH')
    discount_count = len(deals) - glitch_count
    
    summary = f"""
🚨 *عروض جديدة!* {len(deals)} منتج
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}

📊 التفاصيل:
• 🔥 Glitch: {glitch_count}
• 💰 خصومات ≥ 50%: {discount_count}
• 📦 إجمالي مخزن: {len(sent_products) + len(deals)}

━━━━━━━━━━━━━━━
    """
    
    await bot.send_message(
        chat_id=TELEGRAM_CHAT_ID,
        text=summary,
        parse_mode='Markdown'
    )
    
    # إرسال العروض الجديدة
    for i, deal in enumerate(deals, 1):
        savings_text = f"💵 توفير: {deal['savings']:.2f} ريال\n" if deal['savings'] > 0 else ""
        rating_text = f"⭐ تقييم: {deal['rating']}/5\n" if deal['rating'] else ""
        old_price_text = f"🏷️ قبل: {deal['old_price']:.2f} ريال\n" if deal['old_price'] > 0 else ""
        
        message = f"""
{deal['deal_type']} *[جديد #{i}]*

📦 *{deal['title'][:150]}*

💵 *الآن: {deal['price']:.2f} ريال*
{old_price_text}{savings_text}🔥 خصم: {deal['discount']}%
{rating_text}📍 {deal['category']}

🔗 [افتح في Amazon]({deal['link']})
        """
        
        try:
            if deal['image'] and deal['image'].startswith('http'):
                await bot.send_photo(
                    chat_id=TELEGRAM_CHAT_ID,
                    photo=deal['image'],
                    caption=message,
                    parse_mode='Markdown'
                )
            else:
                await bot.send_message(
                    chat_id=TELEGRAM_CHAT_ID,
                    text=message,
                    parse_mode='Markdown'
                )
            
            # ✅ حفظ المنتج إنه اتبعت
            sent_products.add(deal['id'])
            
            await asyncio.sleep(2)
            
        except Exception as e:
            logger.error(f"Error sending deal {i}: {e}")
            try:
                await bot.send_message(
                    chat_id=TELEGRAM_CHAT_ID,
                    text=message,
                    parse_mode='Markdown'
                )
                sent_products.add(deal['id'])
                await asyncio.sleep(2)
            except:
                pass
    
    # ✅ حفظ القاعدة بعد الإرسال
    save_sent_products()
    logger.info(f"Saved {len(sent_products)} products to database")

# ========== المهمة الرئيسية ==========
def job():
    logger.info("="*50)
    logger.info("🔍 بدء البحث...")
    
    try:
        # تحميل المنتجات السابقة
        load_sent_products()
        
        deals = search_amazon_sa_deals()
        logger.info(f"Raw: {len(deals)}")
        
        if deals:
            sample = deals[:5]
            for d in sample:
                logger.info(f"Sample: {d['title'][:40]} | {d['price']}ريال | {d['discount']}% | {d['category']}")
        
        filtered = filter_glitch_deals(deals)
        
        asyncio.run(send_deals_to_telegram(filtered))
        
        logger.info(f"✅ Sent {len(filtered)} new deals")
        
    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        logger.error(traceback.format_exc())

# ========== Flask Routes ==========
@app.route('/')
def home():
    return f"""
    <h1>🛍️ Amazon SA Bot</h1>
    <p>✅ Running</p>
    <p>Stored: {len(sent_products)} products</p>
    <p>Last: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    <a href="/test"><button>🔍 Search</button></a>
    <a href="/clear"><button>🗑️ Clear DB</button></a>
    """

@app.route('/test')
def test():
    from threading import Thread
    Thread(target=job).start()
    return "🔍 Started!"

@app.route('/clear')
def clear_db():
    """مسح قاعدة البيانات (للاختبار)"""
    global sent_products
    sent_products.clear()
    save_sent_products()
    return f"🗑️ Cleared! Now: {len(sent_products)} products"

@app.route('/status')
def status():
    return {
        "status": "running",
        "stored_products": len(sent_products),
        "time": datetime.now().isoformat()
    }

# ========== التشغيل ==========
if __name__ == "__main__":
    # تحميل المنتجات السابقة عند البدء
    load_sent_products()
    
    scheduler = BackgroundScheduler()
    scheduler.add_job(job, 'interval', minutes=10, id='amazon_scan', replace_existing=True)
    scheduler.start()
    
    logger.info("🤖 Bot started")
    logger.info(f"Stored products: {len(sent_products)}")
    
    import threading
    def start_job():
        time.sleep(3)
        job()
    
    threading.Thread(target=start_job).start()
    
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
