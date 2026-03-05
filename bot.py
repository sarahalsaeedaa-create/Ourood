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

# ========== دالة إنشاء Session محسنة ==========
def create_session():
    """إنشاء session مع headers واقعية"""
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
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
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

# ========== دالة جلب صفحة Deals ==========
def get_deals_page(session, url):
    """جلب صفحة deals مع retry"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # تأخير عشوائي بين 2-5 ثواني
            time.sleep(random.uniform(2, 5))
            
            response = session.get(url, timeout=30)
            
            if response.status_code == 200:
                return response.text
            elif response.status_code == 503:
                logger.warning(f"Attempt {attempt + 1}: Service Unavailable (503)")
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
    """
    البحث في Amazon.sa عن عروض Fashion و Beauty
    """
    deals = []
    session = create_session()
    
    # روابط الـ Deals الرسمية (أفضل من البحث العادي)
    deal_urls = [
        "https://www.amazon.sa/gp/goldbox",
        "https://www.amazon.sa/deals/fashion",
        "https://www.amazon.sa/deals/beauty",
        "https://www.amazon.sa/s?k=fashion&rh=p_8%3A30-99",
        "https://www.amazon.sa/s?k=beauty&rh=p_8%3A30-99",
        "https://www.amazon.sa/s?k=perfume&rh=p_8%3A30-99",
        "https://www.amazon.sa/s?k=makeup&rh=p_8%3A30-99",
        "https://www.amazon.sa/s?k=skincare&rh=p_8%3A30-99",
    ]
    
    for url in deal_urls:
        try:
            logger.info(f"Fetching: {url}")
            html = get_deals_page(session, url)
            
            if not html:
                continue
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # البحث عن المنتجات بطرق مختلفة
            items = []
            
            # طريقة 1: Deal cards
            items.extend(soup.find_all('div', {'data-testid': 'deal-card'}))
            
            # طريقة 2: Search results
            items.extend(soup.find_all('div', {'data-component-type': 's-search-result'}))
            
            # طريقة 3: Grid items
            items.extend(soup.find_all('div', class_='a-section'))
            
            logger.info(f"Found {len(items)} raw items in {url}")
            
            for item in items:
                try:
                    # ===== استخراج السعر الحالي =====
                    price = None
                    
                    # طريقة 1: a-price-whole
                    price_whole = item.find('span', class_='a-price-whole')
                    if price_whole:
                        price_text = price_whole.text.replace(',', '').replace('ريال', '').strip()
                        try:
                            price = float(price_text)
                        except:
                            pass
                    
                    # طريقة 2: a-offscreen
                    if not price:
                        price_off = item.find('span', class_='a-offscreen')
                        if price_off:
                            price_match = re.search(r'[\d,]+\.?\d*', price_off.text.replace(',', ''))
                            if price_match:
                                try:
                                    price = float(price_match.group())
                                except:
                                    pass
                    
                    # طريقة 3: Deal price
                    if not price:
                        deal_price = item.find('span', class_='a-price')
                        if deal_price:
                            price_text = deal_price.find('span', class_='a-offscreen')
                            if price_text:
                                price_match = re.search(r'[\d,]+\.?\d*', price_text.text.replace(',', ''))
                                if price_match:
                                    try:
                                        price = float(price_match.group())
                                    except:
                                        pass
                    
                    if not price or price <= 0:
                        continue
                    
                    # ===== استخراج السعر القديم والخصم =====
                    old_price = 0
                    discount_percent = 0
                    
                    # طريقة 1: a-text-price (السعر القديم)
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
                    
                    # طريقة 2: Badge الخصم
                    if discount_percent == 0:
                        badge = item.find('span', class_=re.compile('a-badge-text|s-coupon-highlight-color'))
                        if badge:
                            badge_text = badge.text
                            discount_match = re.search(r'(\d+)%', badge_text)
                            if discount_match:
                                discount_percent = int(discount_match.group(1))
                                # تقدير السعر القديم
                                if discount_percent > 0:
                                    old_price = price / (1 - discount_percent/100)
                    
                    # ===== استخراج العنوان =====
                    title = "Unknown Product"
                    title_selectors = [
                        'h2 a span',
                        'h2 span',
                        '.a-size-mini span',
                        '.a-size-base-plus',
                        '[data-testid="product-title"]',
                        'a[data-testid="deal-title"]'
                    ]
                    
                    for selector in title_selectors:
                        title_elem = item.select_one(selector)
                        if title_elem:
                            title = title_elem.text.strip()
                            if len(title) > 5:
                                break
                    
                    # ===== استخراج الرابط =====
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
                    
                    # ===== استخراج الصورة =====
                    image = ""
                    img_selectors = ['img.s-image', 'img[src]', '[data-testid="product-image"] img']
                    for selector in img_selectors:
                        img = item.select_one(selector)
                        if img:
                            image = img.get('src', '') or img.get('data-src', '')
                            if image and image.startswith('http'):
                                break
                    
                    # ===== استخراج التقييم =====
                    rating = ""
                    rating_elem = item.find('span', class_='a-icon-alt')
                    if rating_elem:
                        rating_match = re.search(r'([\d.]+)', rating_elem.text)
                        if rating_match:
                            rating = rating_match.group(1)
                    
                    deals.append({
                        'title': title,
                        'price': price,
                        'old_price': round(old_price, 2) if old_price > 0 else 0,
                        'discount': discount_percent,
                        'link': link,
                        'image': image,
                        'rating': rating,
                        'source': url.split('/')[-1] if '/' in url else url
                    })
                    
                except Exception as e:
                    continue
            
            # تأخير بين الصفحات
            time.sleep(random.uniform(3, 6))
            
        except Exception as e:
            logger.error(f"Error with {url}: {e}")
            continue
    
    logger.info(f"Total deals collected: {len(deals)}")
    return deals

# ========== التصفية ==========
def filter_glitch_deals(deals):
    """
    تصفية العروض:
    - السعر < 1 ريال (Glitch)
    - أو الخصم >= 50% (غيرتها من 60% عشان تجرب)
    """
    filtered = []
    
    for deal in deals:
        price = deal['price']
        discount = deal['discount']
        
        # شرط 1: سعر < 1 ريال
        is_glitch = price < 1.0 and price > 0
        
        # شرط 2: خصم >= 50% (غيرت من 60% عشان تجرب)
        is_good_deal = discount >= 50
        
        if is_glitch or is_good_deal:
            deal['deal_type'] = '🔥 GLITCH' if is_glitch else f'💰 {discount}% OFF'
            deal['savings'] = round(deal['old_price'] - price, 2) if deal['old_price'] > 0 else 0
            filtered.append(deal)
    
    # ترتيب: Glitch أولاً، بعدين حسب الخصم
    filtered.sort(key=lambda x: (0 if x['deal_type'] == '🔥 GLITCH' else 1, -x['discount']))
    
    # إزالة التكرارات (نفس الرابط)
    seen_links = set()
    unique_deals = []
    for deal in filtered:
        if deal['link'] and deal['link'] not in seen_links:
            seen_links.add(deal['link'])
            unique_deals.append(deal)
    
    logger.info(f"Filtered to {len(unique_deals)} unique deals")
    return unique_deals

# ========== إرسال Telegram ==========
async def send_deals_to_telegram(deals):
    if not deals:
        message = f"""
⏰ *بحث تلقائي - {datetime.now().strftime('%Y-%m-%d %H:%M')}*

🔍 لا توجد عروض تطابق المعايير:
• السعر < 1 ريال ⭐
• أو خصم ≥ 50% 💰

💡 *نصيحة*: جرب تفتح Amazon.sa يدوياً وتشوف العروض

سيتم البحث مرة أخرى بعد 10 دقائق...
        """
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message,
            parse_mode='Markdown'
        )
        logger.info("No deals found")
        return
    
    glitch_count = sum(1 for d in deals if d['deal_type'] == '🔥 GLITCH')
    discount_count = len(deals) - glitch_count
    
    summary = f"""
🚨 *تم العثور على {len(deals)} عروض رائعة!*
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}

📊 التفاصيل:
• 🔥 Glitch Deals (< 1 ريال): {glitch_count}
• 💰 خصومات ≥ 50%: {discount_count}

━━━━━━━━━━━━━━━
    """
    
    await bot.send_message(
        chat_id=TELEGRAM_CHAT_ID,
        text=summary,
        parse_mode='Markdown'
    )
    
    for i, deal in enumerate(deals[:20], 1):  # زودت لـ 20 عرض
        savings_text = f"💵 توفير: {deal['savings']:.2f} ريال\n" if deal['savings'] > 0 else ""
        rating_text = f"⭐ تقييم: {deal['rating']}/5\n" if deal['rating'] else ""
        old_price_text = f"🏷️ السعر قبل: {deal['old_price']:.2f} ريال\n" if deal['old_price'] > 0 else ""
        
        message = f"""
{deal['deal_type']} *[#{i}]*

📦 *{deal['title'][:150]}*

💵 *السعر الآن: {deal['price']:.2f} ريال*
{old_price_text}{savings_text}🔥 نسبة الخصم: {deal['discount']}%
{rating_text}📍 المصدر: {deal['source']}

🔗 [افتح في Amazon.sa]({deal['link']})
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
        except Exception as e:
            logger.error(f"Error sending deal {i}: {e}")
            try:
                await bot.send_message(
                    chat_id=TELEGRAM_CHAT_ID,
                    text=message,
                    parse_mode='Markdown'
                )
            except:
                pass

# ========== المهمة الرئيسية ==========
def job():
    logger.info("="*50)
    logger.info("🔍 بدء البحث عن العروض في Amazon.sa...")
    
    try:
        deals = search_amazon_sa_deals()
        logger.info(f"Raw deals found: {len(deals)}")
        
        # طباعة عينة للـ debug
        if deals:
            sample = deals[:3]
            for d in sample:
                logger.info(f"Sample: {d['title'][:50]} - {d['price']} ريال - {d['discount']}% off")
        
        filtered = filter_glitch_deals(deals)
        
        import asyncio
        asyncio.run(send_deals_to_telegram(filtered))
        
        logger.info(f"✅ تم إرسال {len(filtered)} عروض")
        
    except Exception as e:
        logger.error(f"Error in job: {e}")
        import traceback
        logger.error(traceback.format_exc())

# ========== Flask Routes ==========
@app.route('/')
def home():
    return f"""
    <h1>🛍️ Amazon SA Glitch Deals Bot</h1>
    <p>Status: ✅ Running</p>
    <p>Last scan: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    <p>Next scan: Every 10 minutes</p>
    <hr>
    <a href="/test"><button>🔍 Search Now</button></a>
    <a href="/status"><button>📊 Status</button></a>
    """

@app.route('/test')
def test():
    from threading import Thread
    thread = Thread(target=job)
    thread.start()
    return "🔍 Scan started! Check Telegram."

@app.route('/status')
def status():
    return {"status": "running", "time": datetime.now().isoformat()}

# ========== التشغيل ==========
if __name__ == "__main__":
    scheduler = BackgroundScheduler()
    scheduler.add_job(job, 'interval', minutes=10, id='amazon_scan', replace_existing=True)
    scheduler.start()
    
    logger.info("🤖 البوت اشتغال...")
    logger.info(f"Chat ID: {TELEGRAM_CHAT_ID}")
    
    import threading
    def start_job():
        import time
        time.sleep(3)
        job()
    
    threading.Thread(target=start_job).start()
    
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
