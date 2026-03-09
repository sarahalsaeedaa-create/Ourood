import os
import re
import json
import logging
import requests
import cloudscraper
from datetime import datetime
from bs4 import BeautifulSoup
from telegram import Bot, Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from fake_useragent import UserAgent
from difflib import SequenceMatcher
import time
import random
import hashlib
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8769441239:AAEgX3uBbtWc_hHcqs0lmQ50AqKJGOWV6Ok")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "432826122")
PORT = int(os.environ.get("PORT", 8080))

ua = UserAgent()
sent_products = set()
sent_hashes = set()
is_scanning = False
updater = None

def load_database():
    global sent_products, sent_hashes
    try:
        if os.path.exists('bot_database.json'):
            with open('bot_database.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
                sent_products = set(data.get('ids', []))
                sent_hashes = set(data.get('hashes', []))
                logger.info(f"📦 Loaded: {len(sent_products)}")
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

def extract_asin(link):
    if not link:
        return None
    patterns = [r'/dp/([A-Z0-9]{10})', r'/gp/product/([A-Z0-9]{10})', r'product/([A-Z0-9]{10})']
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
    for word in ['amazon', 'saudi', 'ريال', 'sar', 'new', 'جديد', 'shipped', 'شحن']:
        clean = clean.replace(word, '')
    return hashlib.md5(clean[:30].strip().encode()).hexdigest()[:16]

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
            time.sleep(random.uniform(1, 2))
            r = session.get(url, timeout=25)
            if r.status_code == 200:
                return r.text
            time.sleep(2)
        except Exception as e:
            logger.warning(f"Attempt {i+1} failed: {e}")
    return None

# ========== البحث ==========
def search_all_deals(chat_id, status_message_id):
    all_deals = []
    session = create_session()
    
    # ✅ 120+ قسم - عروض مخفية + مبيعات عالية + عمولات ممتازة
    categories = [
        # 🏆 Best Sellers الأعلى مبيعاً
        ("https://www.amazon.sa/gp/bestsellers/electronics", "📱 Electronics Best Seller", True),
        ("https://www.amazon.sa/gp/bestsellers/fashion", "👕 Fashion Best Seller", True),
        ("https://www.amazon.sa/gp/bestsellers/beauty", "💄 Beauty Best Seller", True),
        ("https://www.amazon.sa/gp/bestsellers/watches", "⌚ Watches Best Seller", True),
        ("https://www.amazon.sa/gp/bestsellers/shoes", "👟 Shoes Best Seller", True),
        ("https://www.amazon.sa/gp/bestsellers/kitchen", "🍳 Kitchen Best Seller", True),
        ("https://www.amazon.sa/gp/bestsellers/home", "🏠 Home Best Seller", True),
        ("https://www.amazon.sa/gp/bestsellers/computers", "💻 Computers Best Seller", True),
        ("https://www.amazon.sa/gp/bestsellers/mobile", "📱 Mobile Best Seller", True),
        ("https://www.amazon.sa/gp/bestsellers/perfumes", "🌸 Perfumes Best Seller", True),
        ("https://www.amazon.sa/gp/bestsellers/toys", "🎮 Toys Best Seller", True),
        ("https://www.amazon.sa/gp/bestsellers/sports", "⚽ Sports Best Seller", True),
        ("https://www.amazon.sa/gp/bestsellers/baby", "👶 Baby Best Seller", True),
        ("https://www.amazon.sa/gp/bestsellers/grocery", "🛒 Grocery Best Seller", True),
        ("https://www.amazon.sa/gp/bestsellers/automotive", "🚗 Automotive Best Seller", True),
        ("https://www.amazon.sa/gp/bestsellers/tools", "🔧 Tools Best Seller", True),
        ("https://www.amazon.sa/gp/bestsellers/books", "📚 Books Best Seller", True),
        ("https://www.amazon.sa/gp/bestsellers/jewelry", "💎 Jewelry Best Seller", True),
        ("https://www.amazon.sa/gp/bestsellers/luggage", "🧳 Luggage Best Seller", True),
        ("https://www.amazon.sa/gp/bestsellers/pet", "🐾 Pet Best Seller", True),
        ("https://www.amazon.sa/gp/bestsellers/office", "📎 Office Best Seller", True),
        ("https://www.amazon.sa/gp/bestsellers/personal-care", "🧴 Personal Care Best Seller", True),
        ("https://www.amazon.sa/gp/bestsellers/health", "💊 Health Best Seller", True),
        ("https://www.amazon.sa/gp/bestsellers/video-games", "🎮 Games Best Seller", True),
        ("https://www.amazon.sa/gp/bestsellers/camera", "📷 Camera Best Seller", True),
        
        # 💰 Goldbox & Deals الرسمية
        ("https://www.amazon.sa/gp/goldbox", "🔥 Goldbox", False),
        ("https://www.amazon.sa/deals/electronics", "📱 Electronics Deals", False),
        ("https://www.amazon.sa/deals/fashion", "👕 Fashion Deals", False),
        ("https://www.amazon.sa/deals/beauty", "💄 Beauty Deals", False),
        ("https://www.amazon.sa/deals/home", "🏠 Home Deals", False),
        ("https://www.amazon.sa/deals/kitchen", "🍳 Kitchen Deals", False),
        ("https://www.amazon.sa/deals/watches", "⌚ Watches Deals", False),
        ("https://www.amazon.sa/deals/perfumes", "🌸 Perfumes Deals", False),
        ("https://www.amazon.sa/deals/toys", "🎮 Toys Deals", False),
        ("https://www.amazon.sa/deals/sports", "⚽ Sports Deals", False),
        ("https://www.amazon.sa/deals/baby", "👶 Baby Deals", False),
        ("https://www.amazon.sa/deals/grocery", "🛒 Grocery Deals", False),
        ("https://www.amazon.sa/deals/automotive", "🚗 Automotive Deals", False),
        ("https://www.amazon.sa/deals/tools", "🔧 Tools Deals", False),
        ("https://www.amazon.sa/deals/office", "📎 Office Deals", False),
        ("https://www.amazon.sa/deals/books", "📚 Books Deals", False),
        
        # 🔥 عروض مخفية - Warehouse Deals
        ("https://www.amazon.sa/gp/warehouse-deals", "🏭 Warehouse Deals", False),
        ("https://www.amazon.sa/gp/warehouse-deals/electronics", "🏭 Warehouse Electronics", False),
        ("https://www.amazon.sa/gp/warehouse-deals/fashion", "🏭 Warehouse Fashion", False),
        ("https://www.amazon.sa/gp/warehouse-deals/home", "🏭 Warehouse Home", False),
        ("https://www.amazon.sa/gp/warehouse-deals/kitchen", "🏭 Warehouse Kitchen", False),
        
        # 🎯 عروض مخفية - Coupons
        ("https://www.amazon.sa/gp/coupons", "🎟️ Coupons", False),
        ("https://www.amazon.sa/gp/coupons/electronics", "🎟️ Electronics Coupons", False),
        ("https://www.amazon.sa/gp/coupons/fashion", "🎟️ Fashion Coupons", False),
        ("https://www.amazon.sa/gp/coupons/home", "🎟️ Home Coupons", False),
        ("https://www.amazon.sa/gp/coupons/beauty", "🎟️ Beauty Coupons", False),
        
        # 💎 عروض مخفية - Prime Exclusive
        ("https://www.amazon.sa/gp/prime/pipeline/prime_exclusives", "👑 Prime Exclusives", False),
        ("https://www.amazon.sa/gp/prime/pipeline/lightning_deals", "⚡ Lightning Deals", False),
        
        # 🏷️ عروض مخفية - Today's Deals
        ("https://www.amazon.sa/gp/todays-deals", "📅 Today Deals", False),
        ("https://www.amazon.sa/gp/todays-deals/electronics", "📅 Today Electronics", False),
        ("https://www.amazon.sa/gp/todays-deals/fashion", "📅 Today Fashion", False),
        
        # 🎁 عروض مخفية - Outlet
        ("https://www.amazon.sa/outlet", "🎁 Outlet", False),
        ("https://www.amazon.sa/outlet/electronics", "🎁 Outlet Electronics", False),
        ("https://www.amazon.sa/outlet/home", "🎁 Outlet Home", False),
        ("https://www.amazon.sa/outlet/fashion", "🎁 Outlet Fashion", False),
        
        # 🎯 براندات عالية العمولة - إلكترونيات
        ("https://www.amazon.sa/s?k=apple&rh=p_8%3A30-99", "🍎 Apple", False),
        ("https://www.amazon.sa/s?k=samsung&rh=p_8%3A30-99", "📱 Samsung", False),
        ("https://www.amazon.sa/s?k=sony&rh=p_8%3A30-99", "🎧 Sony", False),
        ("https://www.amazon.sa/s?k=bose&rh=p_8%3A30-99", "🎵 Bose", False),
        ("https://www.amazon.sa/s?k=anker&rh=p_8%3A30-99", "🔋 Anker", False),
        ("https://www.amazon.sa/s?k=jbl&rh=p_8%3A30-99", "🎶 JBL", False),
        ("https://www.amazon.sa/s?k=beats&rh=p_8%3A30-99", "🎧 Beats", False),
        ("https://www.amazon.sa/s?k=xiaomi&rh=p_8%3A30-99", "📱 Xiaomi", False),
        ("https://www.amazon.sa/s?k=huawei&rh=p_8%3A30-99", "📱 Huawei", False),
        ("https://www.amazon.sa/s?k=lenovo&rh=p_8%3A30-99", "💻 Lenovo", False),
        ("https://www.amazon.sa/s?k=hp&rh=p_8%3A30-99", "💻 HP", False),
        ("https://www.amazon.sa/s?k=dell&rh=p_8%3A30-99", "💻 Dell", False),
        ("https://www.amazon.sa/s?k=logitech&rh=p_8%3A30-99", "🖱️ Logitech", False),
        ("https://www.amazon.sa/s?k=canon&rh=p_8%3A30-99", "📷 Canon", False),
        ("https://www.amazon.sa/s?k=nikon&rh=p_8%3A30-99", "📷 Nikon", False),
        ("https://www.amazon.sa/s?k=playstation&rh=p_8%3A30-99", "🎮 PlayStation", False),
        ("https://www.amazon.sa/s?k=xbox&rh=p_8%3A30-99", "🎮 Xbox", False),
        ("https://www.amazon.sa/s?k=nintendo&rh=p_8%3A30-99", "🎮 Nintendo", False),
        
        # 🎯 براندات عالية العمولة - ساعات
        ("https://www.amazon.sa/s?k=casio+watch&rh=p_8%3A30-99", "⌚ Casio", False),
        ("https://www.amazon.sa/s?k=fossil&rh=p_8%3A30-99", "⌚ Fossil", False),
        ("https://www.amazon.sa/s?k=swatch&rh=p_8%3A30-99", "⌚ Swatch", False),
        ("https://www.amazon.sa/s?k=smart+watch&rh=p_8%3A30-99", "⌚ Smart Watch", False),
        ("https://www.amazon.sa/s?k=rolex&rh=p_8%3A30-99", "⌚ Rolex", False),
        ("https://www.amazon.sa/s?k=michael+kors&rh=p_8%3A30-99", "⌚ Michael Kors", False),
        ("https://www.amazon.sa/s?k=apple+watch&rh=p_8%3A30-99", "⌚ Apple Watch", False),
        ("https://www.amazon.sa/s?k=samsung+watch&rh=p_8%3A30-99", "⌚ Galaxy Watch", False),
        
        # 🎯 براندات عالية العمولة - عطور
        ("https://www.amazon.sa/s?k=chanel+perfume&rh=p_8%3A30-99", "🌸 Chanel", False),
        ("https://www.amazon.sa/s?k=dior+perfume&rh=p_8%3A30-99", "🌸 Dior", False),
        ("https://www.amazon.sa/s?k=gucci+perfume&rh=p_8%3A30-99", "🌸 Gucci", False),
        ("https://www.amazon.sa/s?k=versace+perfume&rh=p_8%3A30-99", "🌸 Versace", False),
        ("https://www.amazon.sa/s?k=armani+perfume&rh=p_8%3A30-99", "🌸 Armani", False),
        ("https://www.amazon.sa/s?k=prada+perfume&rh=p_8%3A30-99", "🌸 Prada", False),
        ("https://www.amazon.sa/s?k=burberry+perfume&rh=p_8%3A30-99", "🌸 Burberry", False),
        ("https://www.amazon.sa/s?k=calvin+klein+perfume&rh=p_8%3A30-99", "🌸 CK Perfume", False),
        ("https://www.amazon.sa/s?k=tom+ford+perfume&rh=p_8%3A30-99", "🌸 Tom Ford", False),
        ("https://www.amazon.sa/s?k=yves+saint+laurent+perfume&rh=p_8%3A30-99", "🌸 YSL", False),
        
        # 🎯 براندات عالية العمولة - أزياء
        ("https://www.amazon.sa/s?k=adidas&rh=p_8%3A30-99", "👟 Adidas", False),
        ("https://www.amazon.sa/s?k=nike&rh=p_8%3A30-99", "👟 Nike", False),
        ("https://www.amazon.sa/s?k=calvin+klein&rh=p_8%3A30-99", "👔 Calvin Klein", False),
        ("https://www.amazon.sa/s?k=lacoste&rh=p_8%3A30-99", "🐊 Lacoste", False),
        ("https://www.amazon.sa/s?k=tommy+hilfiger&rh=p_8%3A30-99", "👕 Tommy Hilfiger", False),
        ("https://www.amazon.sa/s?k=ralph+lauren&rh=p_8%3A30-99", "👔 Ralph Lauren", False),
        ("https://www.amazon.sa/s?k=puma&rh=p_8%3A30-99", "👟 Puma", False),
        ("https://www.amazon.sa/s?k=reebok&rh=p_8%3A30-99", "👟 Reebok", False),
        ("https://www.amazon.sa/s?k=under+armour&rh=p_8%3A30-99", "👟 Under Armour", False),
        ("https://www.amazon.sa/s?k=levis&rh=p_8%3A30-99", "👖 Levis", False),
        ("https://www.amazon.sa/s?k=wrangler&rh=p_8%3A30-99", "👖 Wrangler", False),
        ("https://www.amazon.sa/s?k=timberland&rh=p_8%3A30-99", "👢 Timberland", False),
        ("https://www.amazon.sa/s?k=skechers&rh=p_8%3A30-99", "👟 Skechers", False),
        ("https://www.amazon.sa/s?k=new+balance&rh=p_8%3A30-99", "👟 New Balance", False),
        
        # 🎯 براندات عالية العمولة - مكياج وعناية
        ("https://www.amazon.sa/s?k=loreal&rh=p_8%3A30-99", "💄 L'Oreal", False),
        ("https://www.amazon.sa/s?k=maybelline&rh=p_8%3A30-99", "💄 Maybelline", False),
        ("https://www.amazon.sa/s?k=mac+makeup&rh=p_8%3A30-99", "💄 MAC", False),
        ("https://www.amazon.sa/s?k=nyx&rh=p_8%3A30-99", "💄 NYX", False),
        ("https://www.amazon.sa/s?k=clinique&rh=p_8%3A30-99", "💄 Clinique", False),
        ("https://www.amazon.sa/s?k=estee+lauder&rh=p_8%3A30-99", "💄 Estee Lauder", False),
        ("https://www.amazon.sa/s?k=olay&rh=p_8%3A30-99", "💆 Olay", False),
        ("https://www.amazon.sa/s?k=nivea&rh=p_8%3A30-99", "💆 Nivea", False),
        ("https://www.amazon.sa/s?k=dove&rh=p_8%3A30-99", "🧼 Dove", False),
        ("https://www.amazon.sa/s?k=pantene&rh=p_8%3A30-99", "💇 Pantene", False),
        ("https://www.amazon.sa/s?k=kerastase&rh=p_8%3A30-99", "💇 Kerastase", False),
        ("https://www.amazon.sa/s?k=the+ordinary&rh=p_8%3A30-99", "💆 The Ordinary", False),
        
        # 🎯 منتجات الأطفال (مبيعات عالية)
        ("https://www.amazon.sa/s?k=pampers&rh=p_8%3A30-99", "👶 Pampers", False),
        ("https://www.amazon.sa/s?k=johnson+baby&rh=p_8%3A30-99", "👶 Johnson's", False),
        ("https://www.amazon.sa/s?k=lego&rh=p_8%3A30-99", "🧱 LEGO", False),
        ("https://www.amazon.sa/s?k=barbie&rh=p_8%3A30-99", "👸 Barbie", False),
        ("https://www.amazon.sa/s?k=hot+wheels&rh=p_8%3A30-99", "🚗 Hot Wheels", False),
        ("https://www.amazon.sa/s?k=fisher+price&rh=p_8%3A30-99", "🎠 Fisher Price", False),
        ("https://www.amazon.sa/s?k=ninjago&rh=p_8%3A30-99", "🥷 Ninjago", False),
        ("https://www.amazon.sa/s?k=play-doh&rh=p_8%3A30-99", "🎨 Play-Doh", False),
        
        # 🎯 رياضة ولياقة
        ("https://www.amazon.sa/s?k=fitness+equipment&rh=p_8%3A30-99", "🏋️ Fitness Equipment", False),
        ("https://www.amazon.sa/s?k=yoga+mat&rh=p_8%3A30-99", "🧘 Yoga Mat", False),
        ("https://www.amazon.sa/s?k=dumbbells&rh=p_8%3A30-99", "🏋️ Dumbbells", False),
        ("https://www.amazon.sa/s?k=running+shoes&rh=p_8%3A30-99", "👟 Running Shoes", False),
        ("https://www.amazon.sa/s?k=cycling&rh=p_8%3A30-99", "🚴 Cycling", False),
        ("https://www.amazon.sa/s?k=treadmill&rh=p_8%3A30-99", "🏃 Treadmill", False),
        ("https://www.amazon.sa/s?k=protein&rh=p_8%3A30-99", "💪 Protein", False),
        
        # 🎯 منزل ومطبخ
        ("https://www.amazon.sa/s?k=philips&rh=p_8%3A30-99", "🏠 Philips", False),
        ("https://www.amazon.sa/s?k=braun&rh=p_8%3A30-99", "🏠 Braun", False),
        ("https://www.amazon.sa/s?k=tupperware&rh=p_8%3A30-99", "🥣 Tupperware", False),
        ("https://www.amazon.sa/s?k=pyrex&rh=p_8%3A30-99", "🍽️ Pyrex", False),
        ("https://www.amazon.sa/s?k=ninja+blender&rh=p_8%3A30-99", "🥤 Ninja", False),
        ("https://www.amazon.sa/s?k=dyson&rh=p_8%3A30-99", "🏠 Dyson", False),
        ("https://www.amazon.sa/s?k=nespresso&rh=p_8%3A30-99", "☕ Nespresso", False),
        ("https://www.amazon.sa/s?k=delonghi&rh=p_8%3A30-99", "☕ DeLonghi", False),
        
        # 🎯 اكسسوارات ومجوهرات
        ("https://www.amazon.sa/s?k=handbag&rh=p_8%3A30-99", "👜 Handbag", False),
        ("https://www.amazon.sa/s?k=sunglasses&rh=p_8%3A30-99", "🕶️ Sunglasses", False),
        ("https://www.amazon.sa/s?k=backpack&rh=p_8%3A30-99", "🎒 Backpack", False),
        ("https://www.amazon.sa/s?k=airpods&rh=p_8%3A30-99", "🎧 AirPods", False),
        ("https://www.amazon.sa/s?k=ray+ban&rh=p_8%3A30-99", "🕶️ Ray Ban", False),
        ("https://www.amazon.sa/s?k=oakley&rh=p_8%3A30-99", "🕶️ Oakley", False),
        ("https://www.amazon.sa/s?k=swarovski&rh=p_8%3A30-99", "💎 Swarovski", False),
        ("https://www.amazon.sa/s?k=pandora&rh=p_8%3A30-99", "💎 Pandora", False),
        ("https://www.amazon.sa/s?k=cartier&rh=p_8%3A30-99", "💎 Cartier", False),
        
        # 🎯 أدوات وتحسين المنزل
        ("https://www.amazon.sa/s?k=bosch+tools&rh=p_8%3A30-99", "🔧 Bosch", False),
        ("https://www.amazon.sa/s?k=makita&rh=p_8%3A30-99", "🔧 Makita", False),
        ("https://www.amazon.sa/s?k=dewalt&rh=p_8%3A30-99", "🔧 DeWalt", False),
        ("https://www.amazon.sa/s?k=black+decker&rh=p_8%3A30-99", "🔧 Black & Decker", False),
        ("https://www.amazon.sa/s?k=stanley&rh=p_8%3A30-99", "🔧 Stanley", False),
        
        # 🎯 أقسام خاصة بالسعودية
        ("https://www.amazon.sa/s?k=dates&rh=p_8%3A30-99", "🌴 Dates", False),
        ("https://www.amazon.sa/s?k=oud&rh=p_8%3A30-99", "🌿 Oud", False),
        ("https://www.amazon.sa/s?k=prayer+mat&rh=p_8%3A30-99", "🕌 Prayer Mat", False),
        ("https://www.amazon.sa/s?k=ramadan&rh=p_8%3A30-99", "🌙 Ramadan", False),
        ("https://www.amazon.sa/s?k=eid&rh=p_8%3A30-99", "🎉 Eid", False),
        
        # 🔥 عروض سرية - Hidden Deals
        ("https://www.amazon.sa/s?k=clearance&rh=p_8%3A50-99", "🔥 Clearance", False),
        ("https://www.amazon.sa/s?k=last+chance&rh=p_8%3A50-99", "🔥 Last Chance", False),
        ("https://www.amazon.sa/s?k=final+sale&rh=p_8%3A50-99", "🔥 Final Sale", False),
        ("https://www.amazon.sa/s?k=limited+time&rh=p_8%3A50-99", "⏰ Limited Time", False),
        ("https://www.amazon.sa/s?k=flash+sale&rh=p_8%3A50-99", "⚡ Flash Sale", False),
        
        # 💎 منتجات فاخرة - Luxury
        ("https://www.amazon.sa/s?k=louis+vuitton&rh=p_8%3A30-99", "👜 LV", False),
        ("https://www.amazon.sa/s?k=hermes&rh=p_8%3A30-99", "👜 Hermes", False),
        ("https://www.amazon.sa/s?k=coach&rh=p_8%3A30-99", "👜 Coach", False),
        ("https://www.amazon.sa/s?k=kate+spade&rh=p_8%3A30-99", "👜 Kate Spade", False),
        ("https://www.amazon.sa/s?k=tiffany&rh=p_8%3A30-99", "💍 Tiffany", False),
    ]
    
    total = len(categories)
    
    for idx, (url, cat_name, is_best_seller) in enumerate(categories, 1):
        try:
            if idx % 5 == 0:
                progress = f"⏳ جاري البحث... ({idx}/{total})\n📍 {cat_name}"
                try:
                    updater.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=status_message_id,
                        text=progress
                    )
                except:
                    pass
            
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
            items.extend(soup.find_all('div', class_='s-result-item'))
            items.extend(soup.find_all('div', class_='a-section'))
            
            logger.info(f"   Found {len(items)} items")
            
            for item in items:
                try:
                    deal = parse_item(item, cat_name, is_best_seller)
                    if deal:
                        all_deals.append(deal)
                except:
                    continue
            
            time.sleep(random.uniform(1, 2))
            
        except Exception as e:
            logger.error(f"Error in {cat_name}: {e}")
    
    logger.info(f"✅ Total: {len(all_deals)}")
    return all_deals

def parse_item(item, category, is_best_seller):
    price = None
    for sel in ['.a-price-whole', '.a-price .a-offscreen', '.a-price-range', '.a-price']:
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
    for sel in ['h2 a span', 'h2 span', '.a-size-mini span', '.a-size-base-plus', '.p13n-sc-truncated', '.a-size-medium']:
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
    for sel in ['img.s-image', 'img[src]', '.s-image']:
        el = item.select_one(sel)
        if el:
            img = el.get('src', '') or el.get('data-src', '') or el.get('data-lazy-src', '')
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

def filter_premium_deals(deals):
    filtered = []
    seen_in_run = set()
    
    for deal in deals:
        disc = deal['discount']
        rating = deal['rating']
        is_bs = deal.get('is_best_seller', False)
        pid = deal['id']
        title = deal['title']
        
        # تخفيض الحد الأدنى للعروض المخفية
        min_discount = 50 if 'Warehouse' in deal['category'] or 'Outlet' in deal['category'] or 'Clearance' in deal['category'] else (60 if is_bs else 65)
        
        has_discount = disc >= min_discount
        has_rating = rating >= 3.0
        is_reasonable = 0.5 < deal['price'] < 8000
        
        if has_discount and has_rating and is_reasonable:
            if pid in sent_products or pid in seen_in_run:
                continue
            
            if is_similar_product(title):
                continue
            
            seen_in_run.add(pid)
            
            if deal['price'] < 1:
                deal['type'] = '🔥 GLITCH'
            elif 'Warehouse' in deal['category']:
                deal['type'] = '🏭 WAREHOUSE'
            elif 'Outlet' in deal['category']:
                deal['type'] = '🎁 OUTLET'
            elif 'Coupon' in deal['category']:
                deal['type'] = '🎟️ COUPON'
            elif 'Prime' in deal['category']:
                deal['type'] = '👑 PRIME'
            elif 'Lightning' in deal['category']:
                deal['type'] = '⚡ LIGHTNING'
            elif is_bs:
                deal['type'] = '⭐ BEST SELLER'
            else:
                deal['type'] = f'💰 {disc}%'
            
            deal['savings'] = round(deal['old_price'] - deal['price'], 2) if deal['old_price'] > 0 else 0
            filtered.append(deal)
    
    filtered.sort(key=lambda x: (
        0 if x['type'] == '🔥 GLITCH' else 1,
        0 if x['type'] == '🏭 WAREHOUSE' else 1,
        0 if x['type'] == '⚡ LIGHTNING' else 1,
        0 if x.get('is_best_seller') else 1,
        -x['discount']
    ))
    return filtered

def send_deals(deals, chat_id, status_message_id):
    global sent_products, sent_hashes, is_scanning
    
    try:
        try:
            updater.bot.delete_message(chat_id, status_message_id)
        except:
            pass
        
        if not deals:
            msg = "❌ *لا توجد عروض جديدة*\n\nجرب تاني بعدين!"
            updater.bot.send_message(chat_id=chat_id, text=msg, parse_mode='Markdown')
            return
        
        bs = sum(1 for d in deals if d.get('is_best_seller'))
        glitch = sum(1 for d in deals if d['type'] == '🔥 GLITCH')
        warehouse = sum(1 for d in deals if d['type'] == '🏭 WAREHOUSE')
        outlet = sum(1 for d in deals if d['type'] == '🎁 OUTLET')
        lightning = sum(1 for d in deals if d['type'] == '⚡ LIGHTNING')
        
        summary = f"""
🎯 *{len(deals)} صفقة ممتازة!*

🔥 Glitch: {glitch}
🏭 Warehouse: {warehouse}
🎁 Outlet: {outlet}
⚡ Lightning: {lightning}
⭐ Best Sellers: {bs}
💰 خصومات عادية: {len(deals)-bs-glitch-warehouse-outlet-lightning}
        """
        updater.bot.send_message(chat_id=chat_id, text=summary, parse_mode='Markdown')
        
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
                    updater.bot.send_photo(chat_id=chat_id, photo=d['image'], caption=msg, parse_mode='Markdown')
                else:
                    updater.bot.send_message(chat_id=chat_id, text=msg, parse_mode='Markdown')
                
                sent_products.add(d['id'])
                sent_hashes.add(create_title_hash(d['title']))
                time.sleep(1.5)
                
            except Exception as e:
                logger.error(f"Error #{i}: {e}")
                try:
                    updater.bot.send_message(chat_id=chat_id, text=msg, parse_mode='Markdown')
                    sent_products.add(d['id'])
                    time.sleep(1.5)
                except:
                    pass
        
        save_database()
        logger.info(f"✅ Done! Total: {len(sent_products)}")
        
    finally:
        is_scanning = False

def start_cmd(update: Update, context: CallbackContext):
    update.message.reply_text("""
👋 *أهلاً بيك في Amazon Deals Bot!*

🎯 أنا ببحث في:
• 120+ قسم شامل 📁
• عروض Warehouse المخفية 🏭
• Outlet & Clearance 🎁
• Lightning Deals ⚡
• Prime Exclusives 👑
• Best Sellers ⭐

🔥 خصومات من 50% لـ 99%!

اكتب *Hi* عشان تبدأ البحث!
    """, parse_mode='Markdown')

def hi_cmd(update: Update, context: CallbackContext):
    global is_scanning
    
    chat_id = update.effective_chat.id
    
    if is_scanning:
        update.message.reply_text("⏳ أنا ببحث دلوقتي... استنى شوية!")
        return
    
    is_scanning = True
    
    status_msg = update.message.reply_text("🔍 *بدأت البحث في 120+ قسم...*\n⏱️ 4-5 دقائق", parse_mode='Markdown')
    
    try:
        load_database()
        deals = search_all_deals(chat_id, status_msg.message_id)
        premium = filter_premium_deals(deals)
        send_deals(premium, chat_id, status_msg.message_id)
    except Exception as e:
        logger.error(f"Search error: {e}")
        is_scanning = False
        try:
            updater.bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_msg.message_id,
                text="❌ حصل خطأ! جرب تاني."
            )
        except:
            update.message.reply_text("❌ حصل خطأ! جرب تاني.")

def status_cmd(update: Update, context: CallbackContext):
    update.message.reply_text(f"""
📊 *حالة البوت:*

📦 منتجات مخزنة: {len(sent_products)}
🔍 بحوث متنوعة: {len(sent_hashes)}
📁 الأقسام: 120+
⏰ التوقيت: {datetime.now().strftime('%H:%M:%S')}

✅ البوت شغال بكفاءة!
    """, parse_mode='Markdown')

def clear_cmd(update: Update, context: CallbackContext):
    global sent_products, sent_hashes
    sent_products.clear()
    sent_hashes.clear()
    save_database()
    update.message.reply_text("🗑️ *تم مسح كل البيانات!*\n\nالآن البوت هيبدأ من جديد.", parse_mode='Markdown')

def unknown(update: Update, context: CallbackContext):
    update.message.reply_text("🤔 *مش فاهم!*\n\nاكتب:\n• *Hi* للبحث عن عروض\n• /start للمساعدة\n• /status للحالة", parse_mode='Markdown')

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        response = json.dumps({
            "status": "ok",
            "products": len(sent_products),
            "timestamp": datetime.now().isoformat(),
            "categories": 120
        })
        self.wfile.write(response.encode())
    
    def log_message(self, format, *args):
        pass

def run_health_server():
    server = HTTPServer(('0.0.0.0', PORT), HealthHandler)
    logger.info(f"🌐 Health server running on port {PORT}")
    server.serve_forever()

def main():
    global updater
    
    load_database()
    logger.info(f"🚀 Starting | Products: {len(sent_products)}")
    
    health_thread = threading.Thread(target=run_health_server, daemon=True)
    health_thread.start()
    
    updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    
    dp.add_handler(CommandHandler("start", start_cmd))
    dp.add_handler(CommandHandler("status", status_cmd))
    dp.add_handler(CommandHandler("clear", clear_cmd))
    dp.add_handler(MessageHandler(Filters.regex(r'(?i)^hi$'), hi_cmd))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, unknown))
    
    logger.info("🤖 Bot starting...")
    updater.start_polling(drop_pending_updates=True)
    updater.idle()

if __name__ == "__main__":
    main()
