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

# ============ إعدادات البحث ============
TARGET_DEALS_COUNT = 20    # ✅ هدفنا 20 منتج بالظبط
MIN_DISCOUNT = 40          # خصم 40%+
MIN_RATING = 3.0           # 3 نجوم+

# ✅ كل الأقسام (200+ قسم)
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
    ("https://www.amazon.sa/s?k=xbox&rh=p_8%3A30-99", "🎮 Xbox", 'search'),
    ("https://www.amazon.sa/s?k=nintendo&rh=p_8%3A30-99", "🎮 Nintendo", 'search'),
    ("https://www.amazon.sa/s?k=ipad&rh=p_8%3A30-99", "🍎 iPad", 'search'),
    ("https://www.amazon.sa/s?k=macbook&rh=p_8%3A30-99", "🍎 MacBook", 'search'),
    ("https://www.amazon.sa/s?k=airpods&rh=p_8%3A30-99", "🍎 AirPods", 'search'),
    ("https://www.amazon.sa/s?k=apple+watch&rh=p_8%3A30-99", "🍎 Apple Watch", 'search'),
    ("https://www.amazon.sa/s?k=samsung+tablet&rh=p_8%3A30-99", "📱 Galaxy Tab", 'search'),
    ("https://www.amazon.sa/s?k=samsung+watch&rh=p_8%3A30-99", "📱 Galaxy Watch", 'search'),
    ("https://www.amazon.sa/s?k=samsung+buds&rh=p_8%3A30-99", "📱 Galaxy Buds", 'search'),
    ("https://www.amazon.sa/s?k=sony+headphones&rh=p_8%3A30-99", "🎧 Sony", 'search'),
    ("https://www.amazon.sa/s?k=bose&rh=p_8%3A30-99", "🎧 Bose", 'search'),
    ("https://www.amazon.sa/s?k=beats&rh=p_8%3A30-99", "🎧 Beats", 'search'),
    ("https://www.amazon.sa/s?k=jbl&rh=p_8%3A30-99", "🎧 JBL", 'search'),
    ("https://www.amazon.sa/s?k=lenovo+laptop&rh=p_8%3A30-99", "💻 Lenovo", 'search'),
    ("https://www.amazon.sa/s?k=hp+laptop&rh=p_8%3A30-99", "💻 HP", 'search'),
    ("https://www.amazon.sa/s?k=dell+laptop&rh=p_8%3A30-99", "💻 Dell", 'search'),
    ("https://www.amazon.sa/s?k=asus+laptop&rh=p_8%3A30-99", "💻 Asus", 'search'),
    ("https://www.amazon.sa/s?k=acer+laptop&rh=p_8%3A30-99", "💻 Acer", 'search'),
    ("https://www.amazon.sa/s?k=camera&rh=p_8%3A30-99", "📷 Camera", 'search'),
    ("https://www.amazon.sa/s?k=tv&rh=p_8%3A30-99", "📺 TV", 'search'),
    ("https://www.amazon.sa/s?k=monitor&rh=p_8%3A30-99", "🖥️ Monitor", 'search'),
    ("https://www.amazon.sa/s?k=keyboard&rh=p_8%3A30-99", "⌨️ Keyboard", 'search'),
    ("https://www.amazon.sa/s?k=mouse&rh=p_8%3A30-99", "🖱️ Mouse", 'search'),
    ("https://www.amazon.sa/s?k=router&rh=p_8%3A30-99", "📡 Router", 'search'),
    ("https://www.amazon.sa/s?k=power+bank&rh=p_8%3A30-99", "🔋 Power Bank", 'search'),
    ("https://www.amazon.sa/s?k=charger&rh=p_8%3A30-99", "🔌 Charger", 'search'),
    ("https://www.amazon.sa/s?k=cable&rh=p_8%3A30-99", "🔌 Cable", 'search'),
    ("https://www.amazon.sa/s?k=adapter&rh=p_8%3A30-99", "🔌 Adapter", 'search'),
    ("https://www.amazon.sa/s?k=hard+drive&rh=p_8%3A30-99", "💾 Hard Drive", 'search'),
    ("https://www.amazon.sa/s?k=ssd&rh=p_8%3A30-99", "💾 SSD", 'search'),
    ("https://www.amazon.sa/s?k=usb&rh=p_8%3A30-99", "💾 USB", 'search'),
    ("https://www.amazon.sa/s?k=memory+card&rh=p_8%3A30-99", "💾 Memory Card", 'search'),
    
    # موضة
    ("https://www.amazon.sa/s?k=nike+shoes&rh=p_8%3A30-99", "👟 Nike", 'search'),
    ("https://www.amazon.sa/s?k=adidas+shoes&rh=p_8%3A30-99", "👟 Adidas", 'search'),
    ("https://www.amazon.sa/s?k=puma+shoes&rh=p_8%3A30-99", "👟 Puma", 'search'),
    ("https://www.amazon.sa/s?k=reebok&rh=p_8%3A30-99", "👟 Reebok", 'search'),
    ("https://www.amazon.sa/s?k=under+armour&rh=p_8%3A30-99", "👟 UA", 'search'),
    ("https://www.amazon.sa/s?k=new+balance&rh=p_8%3A30-99", "👟 New Balance", 'search'),
    ("https://www.amazon.sa/s?k=asics&rh=p_8%3A30-99", "👟 Asics", 'search'),
    ("https://www.amazon.sa/s?k=vans&rh=p_8%3A30-99", "👟 Vans", 'search'),
    ("https://www.amazon.sa/s?k=converse&rh=p_8%3A30-99", "👟 Converse", 'search'),
    ("https://www.amazon.sa/s?k=crocs&rh=p_8%3A30-99", "👟 Crocs", 'search'),
    ("https://www.amazon.sa/s?k=watch&rh=p_8%3A30-99", "⌚ Watches", 'search'),
    ("https://www.amazon.sa/s?k=apple+watch&rh=p_8%3A30-99", "⌚ Apple Watch", 'search'),
    ("https://www.amazon.sa/s?k=samsung+watch&rh=p_8%3A30-99", "⌚ Galaxy Watch", 'search'),
    ("https://www.amazon.sa/s?k=garmin&rh=p_8%3A30-99", "⌚ Garmin", 'search'),
    ("https://www.amazon.sa/s?k=fitbit&rh=p_8%3A30-99", "⌚ Fitbit", 'search'),
    ("https://www.amazon.sa/s?k=perfume&rh=p_8%3A30-99", "🌸 Perfumes", 'search'),
    ("https://www.amazon.sa/s?k=chanel+perfume&rh=p_8%3A30-99", "🌸 Chanel", 'search'),
    ("https://www.amazon.sa/s?k=dior+perfume&rh=p_8%3A30-99", "🌸 Dior", 'search'),
    ("https://www.amazon.sa/s?k=gucci+perfume&rh=p_8%3A30-99", "🌸 Gucci", 'search'),
    ("https://www.amazon.sa/s?k=versace+perfume&rh=p_8%3A30-99", "🌸 Versace", 'search'),
    ("https://www.amazon.sa/s?k=armani+perfume&rh=p_8%3A30-99", "🌸 Armani", 'search'),
    ("https://www.amazon.sa/s?k=calvin+klein+perfume&rh=p_8%3A30-99", "🌸 CK", 'search'),
    ("https://www.amazon.sa/s?k=sunglasses&rh=p_8%3A30-99", "🕶️ Sunglasses", 'search'),
    ("https://www.amazon.sa/s?k=ray+ban&rh=p_8%3A30-99", "🕶️ Ray Ban", 'search'),
    ("https://www.amazon.sa/s?k=oakley&rh=p_8%3A30-99", "🕶️ Oakley", 'search'),
    ("https://www.amazon.sa/s?k=bag&rh=p_8%3A30-99", "👜 Bags", 'search'),
    ("https://www.amazon.sa/s?k=wallet&rh=p_8%3A30-99", "👛 Wallet", 'search'),
    ("https://www.amazon.sa/s?k=belt&rh=p_8%3A30-99", "🎽 Belt", 'search'),
    ("https://www.amazon.sa/s?k=hat&rh=p_8%3A30-99", "🧢 Hat", 'search'),
    ("https://www.amazon.sa/s?k=gloves&rh=p_8%3A30-99", "🧤 Gloves", 'search'),
    ("https://www.amazon.sa/s?k=scarf&rh=p_8%3A30-99", "🧣 Scarf", 'search'),
    ("https://www.amazon.sa/s?k=jewelry&rh=p_8%3A30-99", "💎 Jewelry", 'search'),
    ("https://www.amazon.sa/s?k=ring&rh=p_8%3A30-99", "💍 Ring", 'search'),
    ("https://www.amazon.sa/s?k=necklace&rh=p_8%3A30-99", "📿 Necklace", 'search'),
    ("https://www.amazon.sa/s?k=bracelet&rh=p_8%3A30-99", "📿 Bracelet", 'search'),
    ("https://www.amazon.sa/s?k=earrings&rh=p_8%3A30-99", "💎 Earrings", 'search'),
    
    # منزل
    ("https://www.amazon.sa/s?k=kitchen&rh=p_8%3A30-99", "🍳 Kitchen", 'search'),
    ("https://www.amazon.sa/s?k=coffee+maker&rh=p_8%3A30-99", "☕ Coffee Maker", 'search'),
    ("https://www.amazon.sa/s?k=nespresso&rh=p_8%3A30-99", "☕ Nespresso", 'search'),
    ("https://www.amazon.sa/s?k=blender&rh=p_8%3A30-99", "🥤 Blender", 'search'),
    ("https://www.amazon.sa/s?k=air+fryer&rh=p_8%3A30-99", "🍟 Air Fryer", 'search'),
    ("https://www.amazon.sa/s?k=microwave&rh=p_8%3A30-99", "📡 Microwave", 'search'),
    ("https://www.amazon.sa/s?k=oven&rh=p_8%3A30-99", "🔥 Oven", 'search'),
    ("https://www.amazon.sa/s?k=refrigerator&rh=p_8%3A30-99", "❄️ Fridge", 'search'),
    ("https://www.amazon.sa/s?k=washing+machine&rh=p_8%3A30-99", "🧺 Washer", 'search'),
    ("https://www.amazon.sa/s?k=vacuum&rh=p_8%3A30-99", "🏠 Vacuum", 'search'),
    ("https://www.amazon.sa/s?k=dyson&rh=p_8%3A30-99", "🏠 Dyson", 'search'),
    ("https://www.amazon.sa/s?k=home&rh=p_8%3A30-99", "🏠 Home", 'search'),
    ("https://www.amazon.sa/s?k=furniture&rh=p_8%3A30-99", "🪑 Furniture", 'search'),
    ("https://www.amazon.sa/s?k=bed&rh=p_8%3A30-99", "🛏️ Bed", 'search'),
    ("https://www.amazon.sa/s?k=mattress&rh=p_8%3A30-99", "🛏️ Mattress", 'search'),
    ("https://www.amazon.sa/s?k=pillow&rh=p_8%3A30-99", "🛏️ Pillow", 'search'),
    ("https://www.amazon.sa/s?k=blanket&rh=p_8%3A30-99", "🛏️ Blanket", 'search'),
    ("https://www.amazon.sa/s?k=curtain&rh=p_8%3A30-99", "🪟 Curtain", 'search'),
    ("https://www.amazon.sa/s?k=lamp&rh=p_8%3A30-99", "💡 Lamp", 'search'),
    ("https://www.amazon.sa/s?k=light&rh=p_8%3A30-99", "💡 Light", 'search'),
    
    # رياضة
    ("https://www.amazon.sa/s?k=fitness&rh=p_8%3A30-99", "🏋️ Fitness", 'search'),
    ("https://www.amazon.sa/s?k=dumbbells&rh=p_8%3A30-99", "🏋️ Dumbbells", 'search'),
    ("https://www.amazon.sa/s?k=treadmill&rh=p_8%3A30-99", "🏃 Treadmill", 'search'),
    ("https://www.amazon.sa/s?k=yoga&rh=p_8%3A30-99", "🧘 Yoga", 'search'),
    ("https://www.amazon.sa/s?k=protein&rh=p_8%3A30-99", "💪 Protein", 'search'),
    ("https://www.amazon.sa/s?k=bcaa&rh=p_8%3A30-99", "💪 BCAA", 'search'),
    ("https://www.amazon.sa/s?k=creatine&rh=p_8%3A30-99", "💪 Creatine", 'search'),
    ("https://www.amazon.sa/s?k=pre+workout&rh=p_8%3A30-99", "💪 Pre Workout", 'search'),
    ("https://www.amazon.sa/s?k=shaker&rh=p_8%3A30-99", "💪 Shaker", 'search'),
    ("https://www.amazon.sa/s?k=bicycle&rh=p_8%3A30-99", "🚲 Bicycle", 'search'),
    ("https://www.amazon.sa/s?k=camping&rh=p_8%3A30-99", "⛺ Camping", 'search'),
    ("https://www.amazon.sa/s?k=fishing&rh=p_8%3A30-99", "🎣 Fishing", 'search'),
    
    # أطفال
    ("https://www.amazon.sa/s?k=toys&rh=p_8%3A30-99", "🧸 Toys", 'search'),
    ("https://www.amazon.sa/s?k=lego&rh=p_8%3A30-99", "🧱 LEGO", 'search'),
    ("https://www.amazon.sa/s?k=barbie&rh=p_8%3A30-99", "👸 Barbie", 'search'),
    ("https://www.amazon.sa/s?k=hot+wheels&rh=p_8%3A30-99", "🚗 Hot Wheels", 'search'),
    ("https://www.amazon.sa/s?k=pampers&rh=p_8%3A30-99", "👶 Pampers", 'search'),
    ("https://www.amazon.sa/s?k=baby&rh=p_8%3A30-99", "👶 Baby", 'search'),
    ("https://www.amazon.sa/s?k=stroller&rh=p_8%3A30-99", "👶 Stroller", 'search'),
    ("https://www.amazon.sa/s?k=car+seat&rh=p_8%3A30-99", "👶 Car Seat", 'search'),
    
    # جمال
    ("https://www.amazon.sa/s?k=makeup&rh=p_8%3A30-99", "💄 Makeup", 'search'),
    ("https://www.amazon.sa/s?k=skincare&rh=p_8%3A30-99", "💆 Skincare", 'search'),
    ("https://www.amazon.sa/s?k=hair&rh=p_8%3A30-99", "💇 Hair", 'search'),
    ("https://www.amazon.sa/s?k=nails&rh=p_8%3A30-99", "💅 Nails", 'search'),
    ("https://www.amazon.sa/s?k=mac&rh=p_8%3A30-99", "💄 MAC", 'search'),
    ("https://www.amazon.sa/s?k=maybelline&rh=p_8%3A30-99", "💄 Maybelline", 'search'),
    ("https://www.amazon.sa/s?k=loreal&rh=p_8%3A30-99", "💄 L'Oreal", 'search'),
    ("https://www.amazon.sa/s?k=olay&rh=p_8%3A30-99", "💆 Olay", 'search'),
    ("https://www.amazon.sa/s?k=neutrogena&rh=p_8%3A30-99", "💆 Neutrogena", 'search'),
    ("https://www.amazon.sa/s?k=cerave&rh=p_8%3A30-99", "💆 CeraVe", 'search'),
    
    # سيارات
    ("https://www.amazon.sa/s?k=car&rh=p_8%3A30-99", "🚗 Car", 'search'),
    ("https://www.amazon.sa/s?k=tires&rh=p_8%3A30-99", "🚗 Tires", 'search'),
    ("https://www.amazon.sa/s?k=oil&rh=p_8%3A30-99", "🚗 Oil", 'search'),
    ("https://www.amazon.sa/s?k=tools&rh=p_8%3A30-99", "🔧 Tools", 'search'),
    ("https://www.amazon.sa/s?k=drill&rh=p_8%3A30-99", "🔧 Drill", 'search'),
]

# متغير لتتبع الصفحات
last_page_tracker = {cat[1]: 0 for cat in CATEGORIES_DEF}

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
    global sent_products, sent_hashes, last_page_tracker
    try:
        if os.path.exists('bot_database.json'):
            with open('bot_database.json', 'r') as f:
                data = json.load(f)
                sent_products = set(data.get('ids', []))
                sent_hashes = set(data.get('hashes', []))
                saved_pages = data.get('last_pages', {})
                for cat in CATEGORIES_DEF:
                    if cat[1] in saved_pages:
                        last_page_tracker[cat[1]] = saved_pages[cat[1]]
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

def get_page_url(base_url, page_num):
    if page_num <= 1:
        return base_url
    
    if 'page=' in base_url:
        return re.sub(r'page=\d+', f'page={page_num}', base_url)
    elif 's?' in base_url:
        return f"{base_url}&page={page_num}"
    else:
        return f"{base_url}?page={page_num}"

# ================== Scraper ==================
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

def fetch_page(session, url, retries=2):
    for i in range(retries):
        try:
            time.sleep(random.uniform(1, 3))
            r = session.get(url, timeout=30)
            if r.status_code == 200 and len(r.text) > 5000:
                return r.text
            logger.warning(f"Attempt {i+1} failed: Status {r.status_code}")
            time.sleep(3)
        except Exception as e:
            logger.error(f"Fetch error: {e}")
            time.sleep(3)
    return None

def parse_rating(text):
    if not text:
        return 0
    match = re.search(r'(\d+\.?\d*)', str(text))
    return float(match.group(1)) if match else 0

def parse_item(item, category, is_best_seller=False):
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
        
        return {
            'title': title[:120],
            'price': price,
            'old_price': round(old_price, 2) if old_price > 0 else round(price * 100 / (100 - discount), 2),
            'discount': discount,
            'rating': rating,
            'reviews': reviews,
            'link': link,
            'category': category,
            'is_best_seller': is_best_seller,
            'id': get_product_id(title, link, price)
        }
        
    except Exception as e:
        return None

def search_all_deals(chat_id=None, status_msg_id=None):
    """
    ✅ يدور في كل الأقسام والصفحات لحد ما يلاقي 20 منتج
    """
    global last_page_tracker
    
    all_deals = []
    session = create_session()
    
    # ✅ خلط عشوائي للأقسام
    cats = list(CATEGORIES_DEF)
    random.shuffle(cats)
    
    logger.info(f"🚀 Starting search in {len(cats)} categories...")
    
    page_counter = 0
    
    for base_url, cat_name, cat_type in cats:
        # ✅ لو وصلنا للهدف، نوقف
        if len(all_deals) >= TARGET_DEALS_COUNT:
            logger.info(f"🎯 Target reached! Found {len(all_deals)} deals")
            break
        
        # ✅ نبدأ من آخر صفحة + 1
        start_page = last_page_tracker.get(cat_name, 0) + 1
        
        # ✅ ندور في صفحات متعددة من نفس القسم
        for page_num in range(start_page, start_page + 5):  # 5 صفحات من كل قسم
            if len(all_deals) >= TARGET_DEALS_COUNT:
                break
            
            page_counter += 1
            
            # ✅ بناء الرابط
            if cat_type in ['best_sellers', 'deals', 'warehouse', 'coupons', 'lightning', 'today', 'outlet']:
                # ✅ للأقسام الخاصة، نستخدم pagination مختلف
                if '?' in base_url:
                    url = f"{base_url}&page={page_num}"
                else:
                    url = f"{base_url}?page={page_num}"
            else:
                url = get_page_url(base_url, page_num)
            
            logger.info(f"🔍 [{cat_name}] Page {page_num} | Total found: {len(all_deals)}")
            
            # ✅ تحديث رسالة الحالة كل 10 صفحات
            if chat_id and status_msg_id and page_counter % 10 == 0:
                try:
                    updater.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=status_msg_id,
                        text=f"🔍 *جاري البحث...*\n\n📄 صفحات تم البحث فيها: {page_counter}\n✅ منتجات تم العثور عليها: {len(all_deals)}\n⏳ جاري البحث في: {cat_name}",
                        parse_mode='Markdown'
                    )
                except:
                    pass
            
            html = fetch_page(session, url)
            if not html:
                continue
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # ✅ كل أنواع الـ selectors
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
                    
                    # ✅ شروط الصفقة
                    if deal and deal['discount'] >= MIN_DISCOUNT and deal['rating'] >= MIN_RATING:
                        if deal['id'] not in sent_products and not is_similar_product(deal['title']):
                            all_deals.append(deal)
                            logger.info(f"✅ ADDED: {deal['title'][:40]} | {deal['discount']}% | {deal['rating']}★")
                            
                            # ✅ لو وصلنا للهدف، نوقف فوراً
                            if len(all_deals) >= TARGET_DEALS_COUNT:
                                last_page_tracker[cat_name] = page_num
                                save_database()
                                return all_deals
                            
                except:
                    continue
            
            # ✅ تحديث آخر صفحة
            last_page_tracker[cat_name] = page_num
            
            time.sleep(random.uniform(1, 2))
    
    save_database()
    logger.info(f"🎯 Search complete! Found {len(all_deals)} deals")
    return all_deals

def filter_and_send_deals(deals, chat_id):
    """
    ✅ يبعت العروض مرتبة: السوبر (90%+) الأول
    """
    if not deals:
        updater.bot.send_message(
            chat_id=chat_id,
            text="❌ مفيش عروض 40%+ لقيتها\n🔄 جرب تاني بعد شوية!",
            parse_mode='Markdown'
        )
        return
    
    # ✅ فصل العروض
    super_deals = [d for d in deals if d['discount'] >= 90]
    normal_deals = [d for d in deals if d['discount'] < 90]
    
    logger.info(f"🚨 Super deals (90%+): {len(super_deals)}")
    logger.info(f"🔥 Normal deals (40-89%): {len(normal_deals)}")
    
    # ✅ رسالة السوبر ديلز (90%+)
    if super_deals:
        msg = "🚨🚨🚨 *عروض خرافية 90%+* 🚨🚨🚨\n\n"
        
        for i, d in enumerate(super_deals, 1):
            savings = d['old_price'] - d['price'] if d['old_price'] > 0 else 0
            
            msg += f"*{i}. {d['title'][:50]}*\n"
            msg += f"💰 {d['price']:.0f} ريال ~~{d['old_price']:.0f}~~\n"
            msg += f"🔥🔥🔥 خصم: *{d['discount']}%* (توفر {savings:.0f} ريال)\n"
            msg += f"⭐ {d['rating']}/5 | 🏷️ {d['category']}\n"
            msg += f"🔗 [اشتري بسرعة]({d['link']})\n\n"
        
        try:
            updater.bot.send_message(chat_id=chat_id, text=msg, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Super send error: {e}")
        
        time.sleep(1)
    
    # ✅ رسالة العروض العادية (40-89%)
    if normal_deals:
        msg = f"🔥 *عروض رهيبة 40%+* ({len(normal_deals)} منتج)\n\n"
        
        for i, d in enumerate(normal_deals, 1):
            if d['id'] in sent_products:
                continue
            
            savings = d['old_price'] - d['price'] if d['old_price'] > 0 else 0
            
            msg += f"*{i}. {d['title'][:50]}*\n"
            msg += f"💰 {d['price']:.0f} ريال ~~{d['old_price']:.0f}~~ (توفر {savings:.0f})\n"
            msg += f"📉 خصم: *{d['discount']}%* | ⭐ {d['rating']}/5\n"
            msg += f"🏷️ {d['category']}\n"
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
    
    # ✅ نضيف السوبر للـ sent
    for d in super_deals:
        sent_products.add(d['id'])
        sent_hashes.add(create_title_hash(d['title']))
    
    save_database()

# ================== أوامر ==================
def start_cmd(update: Update, context: CallbackContext):
    welcome = """👋 *أهلا بيك في بوت عروض أمازون!*

🔥 *مميزات البوت:*
• يدور في *200+ قسم* مختلف
• يبحث في *كل الصفحات* لحد ما يلاقي 20 منتج
• خصومات *40%+* | تقييم *3 نجوم+*
• عروض *90%+* بشكل خاص 🚨

اكتب *Hi* عشان تبدأ البحث!"""
    update.message.reply_text(welcome, parse_mode='Markdown')

def hi_cmd(update: Update, context: CallbackContext):
    global is_scanning

    if is_scanning:
        update.message.reply_text("⏳ البوت شغال في بحث تاني... استنى شوية!")
        return

    is_scanning = True
    
    chat_id = update.effective_chat.id
    
    status_msg = update.message.reply_text(
        "🔍 *بدأت البحث عن 20 منتج...*\n"
        "📄 بدور في كل الأقسام والصفحات\n"
        "⏳ *الوقت المتوقع: 3-5 دقايق*",
        parse_mode='Markdown'
    )

    try:
        deals = search_all_deals(chat_id, status_msg.message_id)
        
        try:
            updater.bot.delete_message(chat_id, status_msg.message_id)
        except:
            pass
        
        filter_and_send_deals(deals, chat_id)
        
    except Exception as e:
        logger.error(f"Error: {e}")
        try:
            updater.bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_msg.message_id,
                text=f"❌ حصل خطأ: {str(e)[:100]}\n🔄 جرب تاني!"
            )
        except:
            update.message.reply_text(f"❌ خطأ: {str(e)[:100]}", parse_mode='Markdown')
    finally:
        is_scanning = False

def status_cmd(update: Update, context: CallbackContext):
    total_cats = len(CATEGORIES_DEF)
    msg = f"""✅ *البوت شغال تمام!*

📦 منتجات متبعتة: *{len(sent_products)}*
📁 عدد الأقسام: *{total_cats}*
🎯 الهدف كل مرة: *20 منتج*
📉 الحد الأدنى للخصم: *{MIN_DISCOUNT}%*
⭐ الحد الأدنى للتقييم: *{MIN_RATING}*

اكتب *Hi* عشان تبدأ بحث جديد!"""
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
    logger.info(f"📁 Categories: {len(CATEGORIES_DEF)}")
    logger.info(f"🎯 Target: {TARGET_DEALS_COUNT} deals")
    
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
