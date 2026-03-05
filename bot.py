import os
import re
import json
import logging
import requests
import cloudscraper
from datetime import datetime
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from telegram import Bot
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask
from fake_useragent import UserAgent

load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== الإعدادات ==========
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

bot = Bot(token=TELEGRAM_BOT_TOKEN)
app = Flask(__name__)

# إنشاء scraper يتجاوز CloudFlare
scraper = cloudscraper.create_scraper(
    browser={
        'browser': 'chrome',
        'platform': 'windows',
        'desktop': True
    }
)

ua = UserAgent()

# ========== دالة البحث في Amazon.sa ==========
def search_amazon_sa_deals():
    """
    البحث في Amazon.sa عن عروض Fashion و Beauty
    """
    deals = []
    
    # الكلمات المفتاحية للبحث
    search_terms = [
        "fashion women",
        "fashion men", 
        "beauty products",
        "makeup",
        "skin care"
    ]
    
    headers = {
        'Accept-Language': 'ar-SA,ar;q=0.9,en;q=0.8',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Referer': 'https://www.amazon.sa/',
    }
    
    for term in search_terms:
        try:
            url = f"https://www.amazon.sa/s?k={term.replace(' ', '+')}&s=price-asc-rank"
            
            headers['User-Agent'] = ua.random
            
            response = scraper.get(url, headers=headers, timeout=20)
            
            if response.status_code != 200:
                logger.warning(f"Status code: {response.status_code} for {term}")
                continue
            
            soup = BeautifulSoup(response.content, 'lxml')
            
            # البحث عن المنتجات
            items = soup.find_all('div', {'data-component-type': 's-search-result'})
            
            for item in items:
                try:
                    # استخراج السعر
                    price_whole = item.find('span', class_='a-price-whole')
                    price_fraction = item.find('span', class_='a-price-fraction')
                    
                    if not price_whole:
                        continue
                    
                    price_text = price_whole.text.replace(',', '').replace('ريال', '').strip()
                    if price_fraction:
                        price_text += '.' + price_fraction.text.strip()
                    
                    try:
                        price = float(price_text)
                    except:
                        continue
                    
                    # استخراج السعر الأصلي (لو موجود)
                    old_price_elem = item.find('span', class_='a-text-price')
                    old_price = 0
                    discount_percent = 0
                    
                    if old_price_elem:
                        old_price_text = old_price_elem.find('span', class_='a-offscreen')
                        if old_price_text:
                            try:
                                old_price_text = old_price_text.text.replace(',', '').replace('ريال', '').strip()
                                old_price = float(re.findall(r'[\d,]+\.?\d*', old_price_text)[0].replace(',', ''))
                                if old_price > price:
                                    discount_percent = int(((old_price - price) / old_price) * 100)
                            except:
                                pass
                    
                    # استخراج العنوان
                    title_tag = item.find('h2', class_='a-size-mini')
                    if not title_tag:
                        title_tag = item.find('span', class_='a-size-base-plus')
                    
                    title = title_tag.text.strip() if title_tag else 'Unknown Product'
                    
                    # استخراج الرابط
                    link_tag = item.find('a', class_='a-link-normal')
                    link = ''
                    if link_tag and link_tag.get('href'):
                        href = link_tag['href']
                        if href.startswith('/'):
                            link = f'https://www.amazon.sa{href}'
                        else:
                            link = f'https://www.amazon.sa/dp/{href.split("/dp/")[1].split("/")[0]}' if '/dp/' in href else href
                    
                    # استخراج الصورة
                    img_tag = item.find('img', class_='s-image')
                    image = img_tag.get('src', '') if img_tag else ''
                    
                    # استخراج التقييم
                    rating_elem = item.find('span', class_='a-icon-alt')
                    rating = ''
                    if rating_elem:
                        rating = rating_elem.text.split(' ')[0]
                    
                    deals.append({
                        'title': title,
                        'price': price,
                        'old_price': old_price,
                        'discount': discount_percent,
                        'link': link,
                        'image': image,
                        'rating': rating,
                        'category': term
                    })
                    
                except Exception as e:
                    continue
                    
            logger.info(f"Found {len(items)} items for {term}")
            
        except Exception as e:
            logger.error(f"Error searching {term}: {e}")
            continue
    
    return deals

# ========== التصفية ==========
def filter_glitch_deals(deals):
    """
    تصفية العروض:
    - السعر < 1 ريال (Glitch)
    - أو الخصم >= 60%
    """
    filtered = []
    
    for deal in deals:
        price = deal['price']
        discount = deal['discount']
        
        # الشرط: سعر < 1 ريال
        is_glitch = price < 1.0 and price > 0
        
        # أو خصم >= 60%
        is_good_deal = discount >= 60
        
        if is_glitch or is_good_deal:
            deal['deal_type'] = '🔥 GLITCH' if is_glitch else f'💰 {discount}% OFF'
            deal['savings'] = deal['old_price'] - price if deal['old_price'] > 0 else 0
            filtered.append(deal)
    
    # ترتيب حسب الأفضلية: Glitch أولاً، بعدين حسب الخصم
    filtered.sort(key=lambda x: (0 if x['deal_type'] == '🔥 GLITCH' else 1, -x['discount']))
    
    return filtered

# ========== إرسال Telegram ==========
async def send_deals_to_telegram(deals):
    if not deals:
        message = f"""
⏰ *بحث تلقائي - {datetime.now().strftime('%Y-%m-%d %H:%M')}*

🔍 لا توجد عروض تطابق المعايير:
• السعر < 1 ريال ⭐
• أو خصم ≥ 60% 💰

سيتم البحث مرة أخرى بعد 10 دقائق...
        """
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message,
            parse_mode='Markdown'
        )
        logger.info("No deals found")
        return
    
    # إرسال ملخص
    glitch_count = sum(1 for d in deals if d['deal_type'] == '🔥 GLITCH')
    discount_count = len(deals) - glitch_count
    
    summary = f"""
🚨 *تم العثور على {len(deals)} عروض رائعة!*
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}

📊 التفاصيل:
• 🔥 Glitch Deals (< 1 ريال): {glitch_count}
• 💰 خصومات ≥ 60%: {discount_count}

━━━━━━━━━━━━━━━
    """
    
    await bot.send_message(
        chat_id=TELEGRAM_CHAT_ID,
        text=summary,
        parse_mode='Markdown'
    )
    
    # إرسال كل عرض
    for i, deal in enumerate(deals[:15], 1):  # أقصى 15 عرض
        savings_text = f"💵 توفير: {deal['savings']:.2f} ريال\n" if deal['savings'] > 0 else ""
        rating_text = f"⭐ تقييم: {deal['rating']}/5\n" if deal['rating'] else ""
        
        message = f"""
{deal['deal_type']} *[#{i}]*

📦 *{deal['title'][:200]}*

💵 *السعر الآن: {deal['price']:.2f} ريال*
{"🏷️ السعر قبل: " + str(deal['old_price']) + " ريال\n" if deal['old_price'] > 0 else ""}{savings_text}🔥 نسبة الخصم: {deal['discount']}%
{rating_text}🏷️ القسم: {deal['category']}

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
            # Try without image
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
        logger.info(f"Total deals found: {len(deals)}")
        
        filtered = filter_glitch_deals(deals)
        logger.info(f"Filtered deals: {len(filtered)}")
        
        import asyncio
        asyncio.run(send_deals_to_telegram(filtered))
        
        logger.info(f"✅ تم إرسال {len(filtered)} عروض")
        
    except Exception as e:
        logger.error(f"Error in job: {e}")

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
    # جدولة البحث كل 10 دقائق
    scheduler = BackgroundScheduler()
    scheduler.add_job(job, 'interval', minutes=10, id='amazon_scan', replace_existing=True)
    scheduler.start()
    
    logger.info("🤖 البوت اشتغال...")
    logger.info(f"Telegram Chat ID: {TELEGRAM_CHAT_ID}")
    
    # تشغيل أول مرة بعد 5 ثواني
    import threading
    def start_job():
        import time
        time.sleep(5)
        job()
    
    threading.Thread(target=start_job).start()
    
    # تشغيل Flask
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
