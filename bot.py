import os
import re
import json
import logging
import cloudscraper
import time
import random
import hashlib
from bs4 import BeautifulSoup
from telegram import Bot
from fake_useragent import UserAgent

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ====== CONFIG ======
TELEGRAM_BOT_TOKEN = "8769441239:AAEgX3uBbtWc_hHcqs0lmQ50AqKJGOWV6Ok"
TELEGRAM_CHAT_ID = "432826122"
ua = UserAgent()
sent_products = set()
sent_hashes = set()

bot = Bot(token=TELEGRAM_BOT_TOKEN)

# ====== DATABASE ======
def load_database():
    global sent_products, sent_hashes
    if os.path.exists('bot_database.json'):
        try:
            with open('bot_database.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
                sent_products = set(data.get('ids', []))
                sent_hashes = set(data.get('hashes', []))
                logger.info(f"📦 Loaded DB: {len(sent_products)} products")
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

# ====== SESSION ======
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

# ====== PARSE ITEMS ======
def parse_item(item, category, is_best_seller):
    try:
        # Title
        title = "Unknown"
        for sel in ['h2 a span', 'h2 span', '.a-size-mini span', '.a-size-base-plus', '.p13n-sc-truncated', '.a-size-medium']:
            el = item.select_one(sel)
            if el:
                title = el.text.strip()
                if len(title) > 5:
                    break
        
        # Price
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
        
        # Link
        link = ""
        a = item.find('a', href=True)
        if a:
            href = a['href']
            if href.startswith('/'):
                link = f"https://www.amazon.sa{href}"
            else:
                link = href
        
        # Discount calculation
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
        
        # Build deal dict
        deal = {'title': title, 'price': price, 'old_price': old_price, 'discount': discount, 'link': link, 'category': category}
        return deal
    except Exception as e:
        logger.error(f"parse_item error: {e}")
        return None

# ====== SEND TO TELEGRAM ======
def send_to_telegram(deal):
    try:
        msg = f"📌 {deal['title']}\n💰 Price: {deal['price']} SAR"
        if deal['discount'] > 0:
            msg += f"\n💸 Discount: {deal['discount']}%\n~ {deal['old_price']} SAR"
        if deal.get('link'):
            msg += f"\n🔗 {deal['link']}"
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)
        logger.info(f"✅ Sent: {deal['title']}")
    except Exception as e:
        logger.error(f"Telegram send error: {e}")

# ====== SEARCH & PROCESS ======
def search_and_send():
    session = create_session()
    urls = [
        # مثال صغير للتجربة، يمكن توسعته مع بقية الأقسام
        ("https://www.amazon.sa/gp/bestsellers/electronics", "📱 Electronics Best Seller", True),
        ("https://www.amazon.sa/deals/electronics", "📱 Electronics Deals", False)
    ]
    for url, cat_name, is_best_seller in urls:
        html = fetch_page(session, url)
        if not html:
            continue
        soup = BeautifulSoup(html, 'html.parser')
        items = soup.find_all('div', {'data-component-type': 's-search-result'})
        for item in items:
            deal = parse_item(item, cat_name, is_best_seller)
            if deal:
                prod_id = get_product_id(deal)
                title_hash = create_title_hash(deal['title'])
                # إرسال كل المنتجات حتى لو مكررة
                send_to_telegram(deal)
                sent_products.add(prod_id)
                sent_hashes.add(title_hash)
        time.sleep(random.uniform(1,2))
    save_database()
    logger.info("✅ Finished sending all deals")

# ====== MAIN ======
if __name__ == "__main__":
    load_database()
    search_and_send()
