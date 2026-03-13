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
    
    # ✅ 300+ قسم شامل (تم التوسيع)
    categories = [
        # 🏆 Best Sellers الأساسية (25 قسم)
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
        
        # 💰 Goldbox & Deals الرسمية (20 قسم)
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
        ("https://www.amazon.sa/deals/computers", "💻 Computers Deals", False),
        ("https://www.amazon.sa/deals/mobile", "📱 Mobile Deals", False),
        ("https://www.amazon.sa/deals/pet", "🐾 Pet Deals", False),
        ("https://www.amazon.sa/deals/luggage", "🧳 Luggage Deals", False),
        
        # 🔥 عروض مخفية - Warehouse Deals (15 قسم)
        ("https://www.amazon.sa/gp/warehouse-deals", "🏭 Warehouse Deals", False),
        ("https://www.amazon.sa/gp/warehouse-deals/electronics", "🏭 Warehouse Electronics", False),
        ("https://www.amazon.sa/gp/warehouse-deals/fashion", "🏭 Warehouse Fashion", False),
        ("https://www.amazon.sa/gp/warehouse-deals/home", "🏭 Warehouse Home", False),
        ("https://www.amazon.sa/gp/warehouse-deals/kitchen", "🏭 Warehouse Kitchen", False),
        ("https://www.amazon.sa/gp/warehouse-deals/beauty", "🏭 Warehouse Beauty", False),
        ("https://www.amazon.sa/gp/warehouse-deals/sports", "🏭 Warehouse Sports", False),
        ("https://www.amazon.sa/gp/warehouse-deals/tools", "🏭 Warehouse Tools", False),
        ("https://www.amazon.sa/gp/warehouse-deals/toys", "🏭 Warehouse Toys", False),
        ("https://www.amazon.sa/gp/warehouse-deals/books", "🏭 Warehouse Books", False),
        ("https://www.amazon.sa/gp/warehouse-deals/automotive", "🏭 Warehouse Automotive", False),
        ("https://www.amazon.sa/gp/warehouse-deals/computers", "🏭 Warehouse Computers", False),
        ("https://www.amazon.sa/gp/warehouse-deals/mobile", "🏭 Warehouse Mobile", False),
        ("https://www.amazon.sa/gp/warehouse-deals/pet", "🏭 Warehouse Pet", False),
        ("https://www.amazon.sa/gp/warehouse-deals/office", "🏭 Warehouse Office", False),
        
        # 🎟️ عروض مخفية - Coupons (10 قسم)
        ("https://www.amazon.sa/gp/coupons", "🎟️ Coupons", False),
        ("https://www.amazon.sa/gp/coupons/electronics", "🎟️ Electronics Coupons", False),
        ("https://www.amazon.sa/gp/coupons/fashion", "🎟️ Fashion Coupons", False),
        ("https://www.amazon.sa/gp/coupons/home", "🎟️ Home Coupons", False),
        ("https://www.amazon.sa/gp/coupons/beauty", "🎟️ Beauty Coupons", False),
        ("https://www.amazon.sa/gp/coupons/grocery", "🎟️ Grocery Coupons", False),
        ("https://www.amazon.sa/gp/coupons/baby", "🎟️ Baby Coupons", False),
        ("https://www.amazon.sa/gp/coupons/pet", "🎟️ Pet Coupons", False),
        ("https://www.amazon.sa/gp/coupons/sports", "🎟️ Sports Coupons", False),
        ("https://www.amazon.sa/gp/coupons/automotive", "🎟️ Automotive Coupons", False),
        
        # 👑 Prime & Lightning (8 قسم)
        ("https://www.amazon.sa/gp/prime/pipeline/prime_exclusives", "👑 Prime Exclusives", False),
        ("https://www.amazon.sa/gp/prime/pipeline/lightning_deals", "⚡ Lightning Deals", False),
        ("https://www.amazon.sa/gp/prime/pipeline/member_deals", "👑 Prime Member Deals", False),
        ("https://www.amazon.sa/gp/prime/pipeline/early_access", "👑 Prime Early Access", False),
        ("https://www.amazon.sa/gp/prime/pipeline/exclusive_brands", "👑 Prime Brands", False),
        ("https://www.amazon.sa/deals/lightning/electronics", "⚡ Lightning Electronics", False),
        ("https://www.amazon.sa/deals/lightning/fashion", "⚡ Lightning Fashion", False),
        ("https://www.amazon.sa/deals/lightning/home", "⚡ Lightning Home", False),
        
        # 📅 Today's Deals (10 قسم)
        ("https://www.amazon.sa/gp/todays-deals", "📅 Today Deals", False),
        ("https://www.amazon.sa/gp/todays-deals/electronics", "📅 Today Electronics", False),
        ("https://www.amazon.sa/gp/todays-deals/fashion", "📅 Today Fashion", False),
        ("https://www.amazon.sa/gp/todays-deals/home", "📅 Today Home", False),
        ("https://www.amazon.sa/gp/todays-deals/beauty", "📅 Today Beauty", False),
        ("https://www.amazon.sa/gp/todays-deals/grocery", "📅 Today Grocery", False),
        ("https://www.amazon.sa/gp/todays-deals/sports", "📅 Today Sports", False),
        ("https://www.amazon.sa/gp/todays-deals/toys", "📅 Today Toys", False),
        ("https://www.amazon.sa/gp/todays-deals/baby", "📅 Today Baby", False),
        ("https://www.amazon.sa/gp/todays-deals/pet", "📅 Today Pet", False),
        
        # 🎁 Outlet (12 قسم)
        ("https://www.amazon.sa/outlet", "🎁 Outlet", False),
        ("https://www.amazon.sa/outlet/electronics", "🎁 Outlet Electronics", False),
        ("https://www.amazon.sa/outlet/home", "🎁 Outlet Home", False),
        ("https://www.amazon.sa/outlet/fashion", "🎁 Outlet Fashion", False),
        ("https://www.amazon.sa/outlet/beauty", "🎁 Outlet Beauty", False),
        ("https://www.amazon.sa/outlet/kitchen", "🎁 Outlet Kitchen", False),
        ("https://www.amazon.sa/outlet/sports", "🎁 Outlet Sports", False),
        ("https://www.amazon.sa/outlet/toys", "🎁 Outlet Toys", False),
        ("https://www.amazon.sa/outlet/baby", "🎁 Outlet Baby", False),
        ("https://www.amazon.sa/outlet/tools", "🎁 Outlet Tools", False),
        ("https://www.amazon.sa/outlet/automotive", "🎁 Outlet Automotive", False),
        ("https://www.amazon.sa/outlet/pet", "🎁 Outlet Pet", False),
        
        # 🌟 Super Saver & Promotions (8 قسم)
        ("https://www.amazon.sa/-/en/b?ie=UTF8&node=22162537031", "💰 Super Saver 20%", False),
        ("https://www.amazon.sa/-/en/b?ie=UTF8&node=29783174031", "💰 Super Saver 50%", False),
        ("https://www.amazon.sa/s?k=clearance&rh=p_8%3A50-99", "🔥 Clearance", False),
        ("https://www.amazon.sa/s?k=last+chance&rh=p_8%3A50-99", "🔥 Last Chance", False),
        ("https://www.amazon.sa/s?k=final+sale&rh=p_8%3A50-99", "🔥 Final Sale", False),
        ("https://www.amazon.sa/s?k=limited+time&rh=p_8%3A50-99", "⏰ Limited Time", False),
        ("https://www.amazon.sa/s?k=flash+sale&rh=p_8%3A50-99", "⚡ Flash Sale", False),
        ("https://www.amazon.sa/s?k=super+sale&rh=p_8%3A50-99", "💥 Super Sale", False),
        
        # 🍎 Apple كامل (10 قسم)
        ("https://www.amazon.sa/s?k=iphone&rh=p_8%3A30-99", "🍎 iPhone", False),
        ("https://www.amazon.sa/s?k=ipad&rh=p_8%3A30-99", "🍎 iPad", False),
        ("https://www.amazon.sa/s?k=macbook&rh=p_8%3A30-99", "🍎 MacBook", False),
        ("https://www.amazon.sa/s?k=airpods&rh=p_8%3A30-99", "🍎 AirPods", False),
        ("https://www.amazon.sa/s?k=apple+watch&rh=p_8%3A30-99", "🍎 Apple Watch", False),
        ("https://www.amazon.sa/s?k=apple+tv&rh=p_8%3A30-99", "🍎 Apple TV", False),
        ("https://www.amazon.sa/s?k=airtag&rh=p_8%3A30-99", "🍎 AirTag", False),
        ("https://www.amazon.sa/s?k=homepod&rh=p_8%3A30-99", "🍎 HomePod", False),
        ("https://www.amazon.sa/s?k=apple+accessories&rh=p_8%3A30-99", "🍎 Accessories", False),
        ("https://www.amazon.sa/s?k=magsafe&rh=p_8%3A30-99", "🍎 MagSafe", False),
        
        # 📱 Samsung كامل (10 قسم)
        ("https://www.amazon.sa/s?k=samsung+galaxy&rh=p_8%3A30-99", "📱 Galaxy Phone", False),
        ("https://www.amazon.sa/s?k=samsung+tablet&rh=p_8%3A30-99", "📱 Galaxy Tab", False),
        ("https://www.amazon.sa/s?k=samsung+watch&rh=p_8%3A30-99", "📱 Galaxy Watch", False),
        ("https://www.amazon.sa/s?k=samsung+buds&rh=p_8%3A30-99", "📱 Galaxy Buds", False),
        ("https://www.amazon.sa/s?k=samsung+tv&rh=p_8%3A30-99", "📱 Samsung TV", False),
        ("https://www.amazon.sa/s?k=samsung+monitor&rh=p_8%3A30-99", "📱 Samsung Monitor", False),
        ("https://www.amazon.sa/s?k=samsung+ssd&rh=p_8%3A30-99", "📱 Samsung SSD", False),
        ("https://www.amazon.sa/s?k=samsung+memory&rh=p_8%3A30-99", "📱 Samsung Memory", False),
        ("https://www.amazon.sa/s?k=samsung+appliances&rh=p_8%3A30-99", "📱 Samsung Appliances", False),
        ("https://www.amazon.sa/s?k=samsung+accessories&rh=p_8%3A30-99", "📱 Samsung Accessories", False),
        
        # 🎧 سماعات (12 قسم)
        ("https://www.amazon.sa/s?k=sony+headphones&rh=p_8%3A30-99", "🎧 Sony Headphones", False),
        ("https://www.amazon.sa/s?k=bose+headphones&rh=p_8%3A30-99", "🎧 Bose Headphones", False),
        ("https://www.amazon.sa/s?k=beats+headphones&rh=p_8%3A30-99", "🎧 Beats Headphones", False),
        ("https://www.amazon.sa/s?k=jbl+speaker&rh=p_8%3A30-99", "🎧 JBL Speaker", False),
        ("https://www.amazon.sa/s?k=harman+kardon&rh=p_8%3A30-99", "🎧 Harman Kardon", False),
        ("https://www.amazon.sa/s?k=marshall&rh=p_8%3A30-99", "🎧 Marshall", False),
        ("https://www.amazon.sa/s?k=skullcandy&rh=p_8%3A30-99", "🎧 Skullcandy", False),
        ("https://www.amazon.sa/s?k=sennheiser&rh=p_8%3A30-99", "🎧 Sennheiser", False),
        ("https://www.amazon.sa/s?k=audio+technica&rh=p_8%3A30-99", "🎧 Audio-Technica", False),
        ("https://www.amazon.sa/s?k=beyerdynamic&rh=p_8%3A30-99", "🎧 Beyerdynamic", False),
        ("https://www.amazon.sa/s?k=anker+soundcore&rh=p_8%3A30-99", "🎧 Anker Soundcore", False),
        ("https://www.amazon.sa/s?k=edifier&rh=p_8%3A30-99", "🎧 Edifier", False),
        
        # 💻 لابتوبات (12 قسم)
        ("https://www.amazon.sa/s?k=lenovo+laptop&rh=p_8%3A30-99", "💻 Lenovo Laptop", False),
        ("https://www.amazon.sa/s?k=hp+laptop&rh=p_8%3A30-99", "💻 HP Laptop", False),
        ("https://www.amazon.sa/s?k=dell+laptop&rh=p_8%3A30-99", "💻 Dell Laptop", False),
        ("https://www.amazon.sa/s?k=asus+laptop&rh=p_8%3A30-99", "💻 Asus Laptop", False),
        ("https://www.amazon.sa/s?k=acer+laptop&rh=p_8%3A30-99", "💻 Acer Laptop", False),
        ("https://www.amazon.sa/s?k=msi+laptop&rh=p_8%3A30-99", "💻 MSI Laptop", False),
        ("https://www.amazon.sa/s?k=razer+laptop&rh=p_8%3A30-99", "💻 Razer Laptop", False),
        ("https://www.amazon.sa/s?k=alienware&rh=p_8%3A30-99", "💻 Alienware", False),
        ("https://www.amazon.sa/s?k=lg+gram&rh=p_8%3A30-99", "💻 LG Gram", False),
        ("https://www.amazon.sa/s?k=huawei+laptop&rh=p_8%3A30-99", "💻 Huawei Laptop", False),
        ("https://www.amazon.sa/s?k=surface+pro&rh=p_8%3A30-99", "💻 Surface Pro", False),
        ("https://www.amazon.sa/s?k=thinkpad&rh=p_8%3A30-99", "💻 ThinkPad", False),
        
        # 🎮 Gaming (15 قسم)
        ("https://www.amazon.sa/s?k=playstation+5&rh=p_8%3A30-99", "🎮 PS5", False),
        ("https://www.amazon.sa/s?k=playstation+4&rh=p_8%3A30-99", "🎮 PS4", False),
        ("https://www.amazon.sa/s?k=xbox+series&rh=p_8%3A30-99", "🎮 Xbox Series", False),
        ("https://www.amazon.sa/s?k=nintendo+switch&rh=p_8%3A30-99", "🎮 Nintendo Switch", False),
        ("https://www.amazon.sa/s?k=gaming+mouse&rh=p_8%3A30-99", "🎮 Gaming Mouse", False),
        ("https://www.amazon.sa/s?k=gaming+keyboard&rh=p_8%3A30-99", "🎮 Gaming Keyboard", False),
        ("https://www.amazon.sa/s?k=gaming+headset&rh=p_8%3A30-99", "🎮 Gaming Headset", False),
        ("https://www.amazon.sa/s?k=gaming+chair&rh=p_8%3A30-99", "🎮 Gaming Chair", False),
        ("https://www.amazon.sa/s?k=rtx+graphics&rh=p_8%3A30-99", "🎮 RTX Graphics", False),
        ("https://www.amazon.sa/s?k=rx+graphics&rh=p_8%3A30-99", "🎮 RX Graphics", False),
        ("https://www.amazon.sa/s?k=gaming+monitor&rh=p_8%3A30-99", "🎮 Gaming Monitor", False),
        ("https://www.amazon.sa/s?k=gaming+laptop&rh=p_8%3A30-99", "🎮 Gaming Laptop", False),
        ("https://www.amazon.sa/s?k=steam+deck&rh=p_8%3A30-99", "🎮 Steam Deck", False),
        ("https://www.amazon.sa/s?k=roccat&rh=p_8%3A30-99", "🎮 Roccat", False),
        ("https://www.amazon.sa/s?k=steelseries&rh=p_8%3A30-99", "🎮 SteelSeries", False),
        
        # 📷 كاميرات (10 قسم)
        ("https://www.amazon.sa/s?k=canon+camera&rh=p_8%3A30-99", "📷 Canon Camera", False),
        ("https://www.amazon.sa/s?k=nikon+camera&rh=p_8%3A30-99", "📷 Nikon Camera", False),
        ("https://www.amazon.sa/s?k=sony+camera&rh=p_8%3A30-99", "📷 Sony Camera", False),
        ("https://www.amazon.sa/s?k=fujifilm&rh=p_8%3A30-99", "📷 Fujifilm", False),
        ("https://www.amazon.sa/s?k=gopro&rh=p_8%3A30-99", "📷 GoPro", False),
        ("https://www.amazon.sa/s?k=dji&rh=p_8%3A30-99", "📷 DJI Drone", False),
        ("https://www.amazon.sa/s?k=insta360&rh=p_8%3A30-99", "📷 Insta360", False),
        ("https://www.amazon.sa/s?k=panasonic+lumix&rh=p_8%3A30-99", "📷 Lumix", False),
        ("https://www.amazon.sa/s?k=olympus+camera&rh=p_8%3A30-99", "📷 Olympus", False),
        ("https://www.amazon.sa/s?k=leica&rh=p_8%3A30-99", "📷 Leica", False),
        
        # ⌚ ساعات ذكية وعادية (15 قسم)
        ("https://www.amazon.sa/s?k=apple+watch&rh=p_8%3A30-99", "⌚ Apple Watch", False),
        ("https://www.amazon.sa/s?k=samsung+watch&rh=p_8%3A30-99", "⌚ Galaxy Watch", False),
        ("https://www.amazon.sa/s?k=garmin&rh=p_8%3A30-99", "⌚ Garmin", False),
        ("https://www.amazon.sa/s?k=fitbit&rh=p_8%3A30-99", "⌚ Fitbit", False),
        ("https://www.amazon.sa/s?k=huawei+watch&rh=p_8%3A30-99", "⌚ Huawei Watch", False),
        ("https://www.amazon.sa/s?k=amazfit&rh=p_8%3A30-99", "⌚ Amazfit", False),
        ("https://www.amazon.sa/s?k=casio+g+shock&rh=p_8%3A30-99", "⌚ G-Shock", False),
        ("https://www.amazon.sa/s?k=casio+edifice&rh=p_8%3A30-99", "⌚ Edifice", False),
        ("https://www.amazon.sa/s?k=seiko&rh=p_8%3A30-99", "⌚ Seiko", False),
        ("https://www.amazon.sa/s?k=citizen&rh=p_8%3A30-99", "⌚ Citizen", False),
        ("https://www.amazon.sa/s?k=fossil+watch&rh=p_8%3A30-99", "⌚ Fossil", False),
        ("https://www.amazon.sa/s?k=daniel+wellington&rh=p_8%3A30-99", "⌚ DW", False),
        ("https://www.amazon.sa/s?k=movado&rh=p_8%3A30-99", "⌚ Movado", False),
        ("https://www.amazon.sa/s?k=tissot&rh=p_8%3A30-99", "⌚ Tissot", False),
        ("https://www.amazon.sa/s?k=omega&rh=p_8%3A30-99", "⌚ Omega", False),
        
        # 🌸 عطور فاخرة (15 قسم)
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
        ("https://www.amazon.sa/s?k=creed+perfume&rh=p_8%3A30-99", "🌸 Creed", False),
        ("https://www.amazon.sa/s?k=jo+malone&rh=p_8%3A30-99", "🌸 Jo Malone", False),
        ("https://www.amazon.sa/s?k=lancome+perfume&rh=p_8%3A30-99", "🌸 Lancome", False),
        ("https://www.amazon.sa/s?k= paco+rabanne&rh=p_8%3A30-99", "🌸 Paco Rabanne", False),
        ("https://www.amazon.sa/s?k=hugo+boss+perfume&rh=p_8%3A30-99", "🌸 Hugo Boss", False),
        
        # 👟 أحذية رياضية (15 قسم)
        ("https://www.amazon.sa/s?k=nike+shoes&rh=p_8%3A30-99", "👟 Nike Shoes", False),
        ("https://www.amazon.sa/s?k=adidas+shoes&rh=p_8%3A30-99", "👟 Adidas Shoes", False),
        ("https://www.amazon.sa/s?k=jordan&rh=p_8%3A30-99", "👟 Jordan", False),
        ("https://www.amazon.sa/s?k=yeezy&rh=p_8%3A30-99", "👟 Yeezy", False),
        ("https://www.amazon.sa/s?k=new+balance+shoes&rh=p_8%3A30-99", "👟 New Balance", False),
        ("https://www.amazon.sa/s?k=puma+shoes&rh=p_8%3A30-99", "👟 Puma Shoes", False),
        ("https://www.amazon.sa/s?k=reebok+shoes&rh=p_8%3A30-99", "👟 Reebok Shoes", False),
        ("https://www.amazon.sa/s?k=under+armour+shoes&rh=p_8%3A30-99", "👟 UA Shoes", False),
        ("https://www.amazon.sa/s?k=asics&rh=p_8%3A30-99", "👟 Asics", False),
        ("https://www.amazon.sa/s?k=vans&rh=p_8%3A30-99", "👟 Vans", False),
        ("https://www.amazon.sa/s?k=converse&rh=p_8%3A30-99", "👟 Converse", False),
        ("https://www.amazon.sa/s?k=crocs&rh=p_8%3A30-99", "👟 Crocs", False),
        ("https://www.amazon.sa/s?k=skechers&rh=p_8%3A30-99", "👟 Skechers", False),
        ("https://www.amazon.sa/s?k=fila&rh=p_8%3A30-99", "👟 Fila", False),
        ("https://www.amazon.sa/s?k=timberland&rh=p_8%3A30-99", "👟 Timberland", False),
        
        # 👔 ملابس رجالي فاخرة (12 قسم)
        ("https://www.amazon.sa/s?k=calvin+klein+men&rh=p_8%3A30-99", "👔 CK Men", False),
        ("https://www.amazon.sa/s?k=tommy+hilfiger+men&rh=p_8%3A30-99", "👔 Tommy Men", False),
        ("https://www.amazon.sa/s?k=ralph+lauren+men&rh=p_8%3A30-99", "👔 RL Men", False),
        ("https://www.amazon.sa/s?k=lacoste+men&rh=p_8%3A30-99", "👔 Lacoste Men", False),
        ("https://www.amazon.sa/s?k=hugo+boss&rh=p_8%3A30-99", "👔 Hugo Boss", False),
        ("https://www.amazon.sa/s?k=levis+jeans&rh=p_8%3A30-99", "👔 Levis Jeans", False),
        ("https://www.amazon.sa/s?k=wrangler+jeans&rh=p_8%3A30-99", "👔 Wrangler Jeans", False),
        ("https://www.amazon.sa/s?k=diesel&rh=p_8%3A30-99", "👔 Diesel", False),
        ("https://www.amazon.sa/s?k=g+star&rh=p_8%3A30-99", "👔 G-Star", False),
        ("https://www.amazon.sa/s?k=armani+men&rh=p_8%3A30-99", "👔 Armani Men", False),
        ("https://www.amazon.sa/s?k=guess+men&rh=p_8%3A30-99", "👔 Guess Men", False),
        ("https://www.amazon.sa/s?k=north+face&rh=p_8%3A30-99", "👔 North Face", False),
        
        # 👗 ملابس حريمي وشنط (12 قسم)
        ("https://www.amazon.sa/s?k=michael+kors+bag&rh=p_8%3A30-99", "👜 MK Bags", False),
        ("https://www.amazon.sa/s?k=kate+spade&rh=p_8%3A30-99", "👜 Kate Spade", False),
        ("https://www.amazon.sa/s?k=coach+bag&rh=p_8%3A30-99", "👜 Coach", False),
        ("https://www.amazon.sa/s?k=guess+bag&rh=p_8%3A30-99", "👜 Guess", False),
        ("https://www.amazon.sa/s?k=fossil+bag&rh=p_8%3A30-99", "👜 Fossil Bag", False),
        ("https://www.amazon.sa/s?k=vera+bradley&rh=p_8%3A30-99", "👜 Vera Bradley", False),
        ("https://www.amazon.sa/s?k=chanel+bag&rh=p_8%3A30-99", "👜 Chanel Bags", False),
        ("https://www.amazon.sa/s?k=gucci+bag&rh=p_8%3A30-99", "👜 Gucci Bags", False),
        ("https://www.amazon.sa/s?k=prada+bag&rh=p_8%3A30-99", "👜 Prada Bags", False),
        ("https://www.amazon.sa/s?k=burberry+bag&rh=p_8%3A30-99", "👜 Burberry Bags", False),
        ("https://www.amazon.sa/s?k=fendi&rh=p_8%3A30-99", "👜 Fendi", False),
        ("https://www.amazon.sa/s?k=balenciaga&rh=p_8%3A30-99", "👜 Balenciaga", False),
        
        # 💎 مجوهرات (10 قسم)
        ("https://www.amazon.sa/s?k=swarovski&rh=p_8%3A30-99", "💎 Swarovski", False),
        ("https://www.amazon.sa/s?k=pandora&rh=p_8%3A30-99", "💎 Pandora", False),
        ("https://www.amazon.sa/s?k=tiffany&rh=p_8%3A30-99", "💎 Tiffany", False),
        ("https://www.amazon.sa/s?k=cartier&rh=p_8%3A30-99", "💎 Cartier", False),
        ("https://www.amazon.sa/s?k=bulova&rh=p_8%3A30-99", "💎 Bulova", False),
        ("https://www.amazon.sa/s?k=anne+klein&rh=p_8%3A30-99", "💎 Anne Klein", False),
        ("https://www.amazon.sa/s?k=rolex&rh=p_8%3A30-99", "💎 Rolex", False),
        ("https://www.amazon.sa/s?k=omega+jewelry&rh=p_8%3A30-99", "💎 Omega Jewelry", False),
        ("https://www.amazon.sa/s?k=david+yurman&rh=p_8%3A30-99", "💎 David Yurman", False),
        ("https://www.amazon.sa/s?k=kendra+scott&rh=p_8%3A30-99", "💎 Kendra Scott", False),
        
        # 🕶️ نظارات (10 قسم)
        ("https://www.amazon.sa/s?k=ray+ban&rh=p_8%3A30-99", "🕶️ Ray Ban", False),
        ("https://www.amazon.sa/s?k=oakley&rh=p_8%3A30-99", "🕶️ Oakley", False),
        ("https://www.amazon.sa/s?k=persol&rh=p_8%3A30-99", "🕶️ Persol", False),
        ("https://www.amazon.sa/s?k=prada+sunglasses&rh=p_8%3A30-99", "🕶️ Prada", False),
        ("https://www.amazon.sa/s?k=gucci+sunglasses&rh=p_8%3A30-99", "🕶️ Gucci Sun", False),
        ("https://www.amazon.sa/s?k=burberry+sunglasses&rh=p_8%3A30-99", "🕶️ Burberry Sun", False),
        ("https://www.amazon.sa/s?k=maui+jim&rh=p_8%3A30-99", "🕶️ Maui Jim", False),
        ("https://www.amazon.sa/s?k=carrera&rh=p_8%3A30-99", "🕶️ Carrera", False),
        ("https://www.amazon.sa/s?k=polarized+sunglasses&rh=p_8%3A30-99", "🕶️ Polarized", False),
        ("https://www.amazon.sa/s?k=aviator+sunglasses&rh=p_8%3A30-99", "🕶️ Aviator", False),
        
        # 💄 مكياج (12 قسم)
        ("https://www.amazon.sa/s?k=mac+makeup&rh=p_8%3A30-99", "💄 MAC", False),
        ("https://www.amazon.sa/s?k=nyx+makeup&rh=p_8%3A30-99", "💄 NYX", False),
        ("https://www.amazon.sa/s?k=maybelline+makeup&rh=p_8%3A30-99", "💄 Maybelline", False),
        ("https://www.amazon.sa/s?k=loreal+makeup&rh=p_8%3A30-99", "💄 L'Oreal", False),
        ("https://www.amazon.sa/s?k=revlon&rh=p_8%3A30-99", "💄 Revlon", False),
        ("https://www.amazon.sa/s?k=covergirl&rh=p_8%3A30-99", "💄 Covergirl", False),
        ("https://www.amazon.sa/s?k=bobbi+brown&rh=p_8%3A30-99", "💄 Bobbi Brown", False),
        ("https://www.amazon.sa/s?k=anastasia&rh=p_8%3A30-99", "💄 Anastasia", False),
        ("https://www.amazon.sa/s?k=huda+beauty&rh=p_8%3A30-99", "💄 Huda Beauty", False),
        ("https://www.amazon.sa/s?k=fenty+beauty&rh=p_8%3A30-99", "💄 Fenty", False),
        ("https://www.amazon.sa/s?k=nars&rh=p_8%3A30-99", "💄 NARS", False),
        ("https://www.amazon.sa/s?k=clinique&rh=p_8%3A30-99", "💄 Clinique", False),
        
        # 🧴 عناية شخصية (12 قسم)
        ("https://www.amazon.sa/s?k=olay&rh=p_8%3A30-99", "💆 Olay", False),
        ("https://www.amazon.sa/s?k=neutrogena&rh=p_8%3A30-99", "💆 Neutrogena", False),
        ("https://www.amazon.sa/s?k=cerave&rh=p_8%3A30-99", "💆 CeraVe", False),
        ("https://www.amazon.sa/s?k=cetaphil&rh=p_8%3A30-99", "💆 Cetaphil", False),
        ("https://www.amazon.sa/s?k=la+roche+posay&rh=p_8%3A30-99", "💆 La Roche", False),
        ("https://www.amazon.sa/s?k=vichy&rh=p_8%3A30-99", "💆 Vichy", False),
        ("https://www.amazon.sa/s?k=eucerin&rh=p_8%3A30-99", "💆 Eucerin", False),
        ("https://www.amazon.sa/s?k=aveeno&rh=p_8%3A30-99", "💆 Aveeno", False),
        ("https://www.amazon.sa/s?k=bioderma&rh=p_8%3A30-99", "💆 Bioderma", False),
        ("https://www.amazon.sa/s?k=the+ordinary&rh=p_8%3A30-99", "💆 The Ordinary", False),
        ("https://www.amazon.sa/s?k=paulas+choice&rh=p_8%3A30-99", "💆 Paula's Choice", False),
        ("https://www.amazon.sa/s?k=drunk+elephant&rh=p_8%3A30-99", "💆 Drunk Elephant", False),
        
        # 👶 أطفال (15 قسم)
        ("https://www.amazon.sa/s?k=pampers&rh=p_8%3A30-99", "👶 Pampers", False),
        ("https://www.amazon.sa/s?k=huggies&rh=p_8%3A30-99", "👶 Huggies", False),
        ("https://www.amazon.sa/s?k=johnson+baby&rh=p_8%3A30-99", "👶 Johnson's", False),
        ("https://www.amazon.sa/s?k=mustela&rh=p_8%3A30-99", "👶 Mustela", False),
        ("https://www.amazon.sa/s?k=aveeno+baby&rh=p_8%3A30-99", "👶 Aveeno Baby", False),
        ("https://www.amazon.sa/s?k=lego&rh=p_8%3A30-99", "🧱 LEGO", False),
        ("https://www.amazon.sa/s?k=barbie&rh=p_8%3A30-99", "👸 Barbie", False),
        ("https://www.amazon.sa/s?k=hot+wheels&rh=p_8%3A30-99", "🚗 Hot Wheels", False),
        ("https://www.amazon.sa/s?k=fisher+price&rh=p_8%3A30-99", "🎠 Fisher Price", False),
        ("https://www.amazon.sa/s?k=little+tikes&rh=p_8%3A30-99", "🎪 Little Tikes", False),
        ("https://www.amazon.sa/s?k=playskool&rh=p_8%3A30-99", "🎨 Playskool", False),
        ("https://www.amazon.sa/s?k=vtech&rh=p_8%3A30-99", "🔤 VTech", False),
        ("https://www.amazon.sa/s?k=leapfrog&rh=p_8%3A30-99", "🐸 LeapFrog", False),
        ("https://www.amazon.sa/s?k=melissa+doug&rh=p_8%3A30-99", "🧸 Melissa & Doug", False),
        ("https://www.amazon.sa/s?k=nuby&rh=p_8%3A30-99", "👶 Nuby", False),
        
        # 🏋️ رياضة (20 قسم)
        ("https://www.amazon.sa/s?k=fitness+equipment&rh=p_8%3A30-99", "🏋️ Fitness", False),
        ("https://www.amazon.sa/s?k=yoga+mat&rh=p_8%3A30-99", "🧘 Yoga Mat", False),
        ("https://www.amazon.sa/s?k=dumbbells&rh=p_8%3A30-99", "🏋️ Dumbbells", False),
        ("https://www.amazon.sa/s?k=kettlebell&rh=p_8%3A30-99", "🏋️ Kettlebell", False),
        ("https://www.amazon.sa/s?k=resistance+bands&rh=p_8%3A30-99", "🏋️ Resistance", False),
        ("https://www.amazon.sa/s?k=treadmill&rh=p_8%3A30-99", "🏃 Treadmill", False),
        ("https://www.amazon.sa/s?k=exercise+bike&rh=p_8%3A30-99", "🚴 Exercise Bike", False),
        ("https://www.amazon.sa/s?k=elliptical&rh=p_8%3A30-99", "🏃 Elliptical", False),
        ("https://www.amazon.sa/s?k=protein+powder&rh=p_8%3A30-99", "💪 Protein", False),
        ("https://www.amazon.sa/s?k=bcaa&rh=p_8%3A30-99", "💪 BCAA", False),
        ("https://www.amazon.sa/s?k=creatine&rh=p_8%3A30-99", "💪 Creatine", False),
        ("https://www.amazon.sa/s?k=pre+workout&rh=p_8%3A30-99", "💪 Pre Workout", False),
        ("https://www.amazon.sa/s?k=optimum+nutrition&rh=p_8%3A30-99", "💪 ON", False),
        ("https://www.amazon.sa/s?k=muscletech&rh=p_8%3A30-99", "💪 MuscleTech", False),
        ("https://www.amazon.sa/s?k=dymatize&rh=p_8%3A30-99", "💪 Dymatize", False),
        ("https://www.amazon.sa/s?k=bpi+sports&rh=p_8%3A30-99", "💪 BPI", False),
        ("https://www.amazon.sa/s?k=nike+fitness&rh=p_8%3A30-99", "🏋️ Nike Fitness", False),
        ("https://www.amazon.sa/s?k=adidas+fitness&rh=p_8%3A30-99", "🏋️ Adidas Fitness", False),
        ("https://www.amazon.sa/s?k=under+armour+fitness&rh=p_8%3A30-99", "🏋️ UA Fitness", False),
        ("https://www.amazon.sa/s?k=reebok+fitness&rh=p_8%3A30-99", "🏋️ Reebok Fitness", False),
        
        # 🏠 منزل ومطبخ (20 قسم)
        ("https://www.amazon.sa/s?k=philips+air+fryer&rh=p_8%3A30-99", "🏠 Philips AirFryer", False),
        ("https://www.amazon.sa/s?k=ninja+blender&rh=p_8%3A30-99", "🥤 Ninja", False),
        ("https://www.amazon.sa/s?k=nespresso&rh=p_8%3A30-99", "☕ Nespresso", False),
        ("https://www.amazon.sa/s?k=delonghi&rh=p_8%3A30-99", "☕ DeLonghi", False),
        ("https://www.amazon.sa/s?k=breville&rh=p_8%3A30-99", "🏠 Breville", False),
        ("https://www.amazon.sa/s?k=kenwood&rh=p_8%3A30-99", "🏠 Kenwood", False),
        ("https://www.amazon.sa/s?k=kitchenaid&rh=p_8%3A30-99", "🏠 KitchenAid", False),
        ("https://www.amazon.sa/s?k=cuisinart&rh=p_8%3A30-99", "🏠 Cuisinart", False),
        ("https://www.amazon.sa/s?k=tupperware&rh=p_8%3A30-99", "🥣 Tupperware", False),
        ("https://www.amazon.sa/s?k=pyrex&rh=p_8%3A30-99", "🍽️ Pyrex", False),
        ("https://www.amazon.sa/s?k=corelle&rh=p_8%3A30-99", "🍽️ Corelle", False),
        ("https://www.amazon.sa/s?k=dyson+vacuum&rh=p_8%3A30-99", "🏠 Dyson", False),
        ("https://www.amazon.sa/s?k=irobot&rh=p_8%3A30-99", "🏠 iRobot", False),
        ("https://www.amazon.sa/s?k=ecovacs&rh=p_8%3A30-99", "🏠 Ecovacs", False),
        ("https://www.amazon.sa/s?k=braun+blender&rh=p_8%3A30-99", "🏠 Braun", False),
        ("https://www.amazon.sa/s?k=instant+pot&rh=p_8%3A30-99", "🏠 Instant Pot", False),
        ("https://www.amazon.sa/s?k=cosori&rh=p_8%3A30-99", "🏠 Cosori", False),
        ("https://www.amazon.sa/s?k=anker+home&rh=p_8%3A30-99", "🏠 Anker Home", False),
        ("https://www.amazon.sa/s?k=eufy+home&rh=p_8%3A30-99", "🏠 Eufy Home", False),
        ("https://www.amazon.sa/s?k=roborock&rh=p_8%3A30-99", "🏠 Roborock", False),
        
        # 🔧 أدوات (12 قسم)
        ("https://www.amazon.sa/s?k=bosch+tools&rh=p_8%3A30-99", "🔧 Bosch", False),
        ("https://www.amazon.sa/s?k=makita&rh=p_8%3A30-99", "🔧 Makita", False),
        ("https://www.amazon.sa/s?k=dewalt&rh=p_8%3A30-99", "🔧 DeWalt", False),
        ("https://www.amazon.sa/s?k=black+decker&rh=p_8%3A30-99", "🔧 Black & Decker", False),
        ("https://www.amazon.sa/s?k=stanley&rh=p_8%3A30-99", "🔧 Stanley", False),
        ("https://www.amazon.sa/s?k=craftsman&rh=p_8%3A30-99", "🔧 Craftsman", False),
        ("https://www.amazon.sa/s?k=ryobi&rh=p_8%3A30-99", "🔧 Ryobi", False),
        ("https://www.amazon.sa/s?k=worx&rh=p_8%3A30-99", "🔧 Worx", False),
        ("https://www.amazon.sa/s?k=milwaukee&rh=p_8%3A30-99", "🔧 Milwaukee", False),
        ("https://www.amazon.sa/s?k=hitachi+tools&rh=p_8%3A30-99", "🔧 Hitachi", False),
        ("https://www.amazon.sa/s?k=metabo&rh=p_8%3A30-99", "🔧 Metabo", False),
        ("https://www.amazon.sa/s?k=ingco&rh=p_8%3A30-99", "🔧 Ingco", False),
        
        # 🚗 سيارات (12 قسم)
        ("https://www.amazon.sa/s?k=michelin+tires&rh=p_8%3A30-99", "🚗 Michelin", False),
        ("https://www.amazon.sa/s?k=bridgestone+tires&rh=p_8%3A30-99", "🚗 Bridgestone", False),
        ("https://www.amazon.sa/s?k=goodyear+tires&rh=p_8%3A30-99", "🚗 Goodyear", False),
        ("https://www.amazon.sa/s?k=pirelli&rh=p_8%3A30-99", "🚗 Pirelli", False),
        ("https://www.amazon.sa/s?k=continental+tires&rh=p_8%3A30-99", "🚗 Continental", False),
        ("https://www.amazon.sa/s?k=bosch+car&rh=p_8%3A30-99", "🚗 Bosch Car", False),
        ("https://www.amazon.sa/s?k=shell+oil&rh=p_8%3A30-99", "🚗 Shell", False),
        ("https://www.amazon.sa/s?k=mobil+1&rh=p_8%3A30-99", "🚗 Mobil 1", False),
        ("https://www.amazon.sa/s?k=castrol&rh=p_8%3A30-99", "🚗 Castrol", False),
        ("https://www.amazon.sa/s?k=3m+car&rh=p_8%3A30-99", "🚗 3M Car", False),
        ("https://www.amazon.sa/s?k=turtle+wax&rh=p_8%3A30-99", "🚗 Turtle Wax", False),
        ("https://www.amazon.sa/s?k=meguiars&rh=p_8%3A30-99", "🚗 Meguiar's", False),
        
        # 📚 كتب وأجهزة قراءة (8 قسم)
        ("https://www.amazon.sa/s?k=kindle&rh=p_8%3A30-99", "📚 Kindle", False),
        ("https://www.amazon.sa/s?k=harry+potter+book&rh=p_8%3A30-99", "📚 Harry Potter", False),
        ("https://www.amazon.sa/s?k=kindle+paperwhite&rh=p_8%3A30-99", "📚 Kindle Paperwhite", False),
        ("https://www.amazon.sa/s?k=kindle+oasis&rh=p_8%3A30-99", "📚 Kindle Oasis", False),
        ("https://www.amazon.sa/s?k=book+set&rh=p_8%3A30-99", "📚 Book Sets", False),
        ("https://www.amazon.sa/s?k=educational+books&rh=p_8%3A30-99", "📚 Educational", False),
        ("https://www.amazon.sa/s?k=children+books&rh=p_8%3A30-99", "📚 Children Books", False),
        ("https://www.amazon.sa/s?k=arabic+books&rh=p_8%3A30-99", "📚 Arabic Books", False),
        
        # 🌙 سعودي خاص (15 قسم)
        ("https://www.amazon.sa/s?k=dates&rh=p_8%3A30-99", "🌴 Dates", False),
        ("https://www.amazon.sa/s?k=oud&rh=p_8%3A30-99", "🌿 Oud", False),
        ("https://www.amazon.sa/s?k=bakhoor&rh=p_8%3A30-99", "🌿 Bakhoor", False),
        ("https://www.amazon.sa/s?k=prayer+mat&rh=p_8%3A30-99", "🕌 Prayer Mat", False),
        ("https://www.amazon.sa/s?k=thobe&rh=p_8%3A30-99", "👘 Thobe", False),
        ("https://www.amazon.sa/s?k=abaya&rh=p_8%3A30-99", "🧕 Abaya", False),
        ("https://www.amazon.sa/s?k=ramadan&rh=p_8%3A30-99", "🌙 Ramadan", False),
        ("https://www.amazon.sa/s?k=eid&rh=p_8%3A30-99", "🎉 Eid", False),
        ("https://www.amazon.sa/s?k=hajj&rh=p_8%3A30-99", "🕋 Hajj", False),
        ("https://www.amazon.sa/s?k=umrah&rh=p_8%3A30-99", "🕋 Umrah", False),
        ("https://www.amazon.sa/s?k=islamic+gifts&rh=p_8%3A30-99", "🎁 Islamic Gifts", False),
        ("https://www.amazon.sa/s?k=quran&rh=p_8%3A30-99", "📖 Quran", False),
        ("https://www.amazon.sa/s?k=islamic+decor&rh=p_8%3A30-99", "🏠 Islamic Decor", False),
        ("https://www.amazon.sa/s?k=arabic+coffee&rh=p_8%3A30-99", "☕ Arabic Coffee", False),
        ("https://www.amazon.sa/s?k=saudi+souvenirs&rh=p_8%3A30-99", "🎁 Saudi Souvenirs", False),
        
        # 💎 فاخر (15 قسم)
        ("https://www.amazon.sa/s?k=louis+vuitton&rh=p_8%3A30-99", "👜 LV", False),
        ("https://www.amazon.sa/s?k=hermes&rh=p_8%3A30-99", "👜 Hermes", False),
        ("https://www.amazon.sa/s?k=coach&rh=p_8%3A30-99", "👜 Coach", False),
        ("https://www.amazon.sa/s?k=kate+spade&rh=p_8%3A30-99", "👜 Kate Spade", False),
        ("https://www.amazon.sa/s?k=burberry+bag&rh=p_8%3A30-99", "👜 Burberry", False),
        ("https://www.amazon.sa/s?k=longchamp&rh=p_8%3A30-99", "👜 Longchamp", False),
        ("https://www.amazon.sa/s?k=tumi&rh=p_8%3A30-99", "🧳 Tumi", False),
        ("https://www.amazon.sa/s?k=samsonite&rh=p_8%3A30-99", "🧳 Samsonite", False),
        ("https://www.amazon.sa/s?k=rimowa&rh=p_8%3A30-99", "🧳 Rimowa", False),
        ("https://www.amazon.sa/s?k=american+tourister&rh=p_8%3A30-99", "🧳 American Tourister", False),
        ("https://www.amazon.sa/s?k=travel+pro&rh=p_8%3A30-99", "🧳 TravelPro", False),
        ("https://www.amazon.sa/s?k=briggs+riley&rh=p_8%3A30-99", "🧳 Briggs & Riley", False),
        ("https://www.amazon.sa/s?k=delsey&rh=p_8%3A30-99", "🧳 Delsey", False),
        ("https://www.amazon.sa/s?k=victorinox+luggage&rh=p_8%3A30-99", "🧳 Victorinox", False),
        ("https://www.amazon.sa/s?k=hartmann&rh=p_8%3A30-99", "🧳 Hartmann", False),
        
        # 🍎 إلكترونيات إضافية (15 قسم)
        ("https://www.amazon.sa/s?k=xiaomi&rh=p_8%3A30-99", "📱 Xiaomi", False),
        ("https://www.amazon.sa/s?k=oneplus&rh=p_8%3A30-99", "📱 OnePlus", False),
        ("https://www.amazon.sa/s?k=oppo&rh=p_8%3A30-99", "📱 OPPO", False),
        ("https://www.amazon.sa/s?k=vivo&rh=p_8%3A30-99", "📱 Vivo", False),
        ("https://www.amazon.sa/s?k=realme&rh=p_8%3A30-99", "📱 Realme", False),
        ("https://www.amazon.sa/s?k=nothing+phone&rh=p_8%3A30-99", "📱 Nothing", False),
        ("https://www.amazon.sa/s?k=google+pixel&rh=p_8%3A30-99", "📱 Pixel", False),
        ("https://www.amazon.sa/s?k=motorola+phone&rh=p_8%3A30-99", "📱 Motorola", False),
        ("https://www.amazon.sa/s?k=nokia+smartphone&rh=p_8%3A30-99", "📱 Nokia", False),
        ("https://www.amazon.sa/s?k=sony+xperia&rh=p_8%3A30-99", "📱 Xperia", False),
        ("https://www.amazon.sa/s?k=asus+phone&rh=p_8%3A30-99", "📱 Asus Phone", False),
        ("https://www.amazon.sa/s?k=lg+phone&rh=p_8%3A30-99", "📱 LG Phone", False),
        ("https://www.amazon.sa/s?k=honor&rh=p_8%3A30-99", "📱 Honor", False),
        ("https://www.amazon.sa/s?k=tcl+phone&rh=p_8%3A30-99", "📱 TCL", False),
        ("https://www.amazon.sa/s?k=zte&rh=p_8%3A30-99", "📱 ZTE", False),
        
        # 🏠 أثاث وديكور (10 قسم)
        ("https://www.amazon.sa/s?k=ikea&rh=p_8%3A30-99", "🏠 IKEA", False),
        ("https://www.amazon.sa/s?k=home+decor&rh=p_8%3A30-99", "🏠 Home Decor", False),
        ("https://www.amazon.sa/s?k=furniture&rh=p_8%3A30-99", "🏠 Furniture", False),
        ("https://www.amazon.sa/s?k=bedroom+furniture&rh=p_8%3A30-99", "🏠 Bedroom", False),
        ("https://www.amazon.sa/s?k=living+room&rh=p_8%3A30-99", "🏠 Living Room", False),
        ("https://www.amazon.sa/s?k=kitchen+furniture&rh=p_8%3A30-99", "🏠 Kitchen Furniture", False),
        ("https://www.amazon.sa/s?k=office+furniture&rh=p_8%3A30-99", "🏠 Office Furniture", False),
        ("https://www.amazon.sa/s?k=outdoor+furniture&rh=p_8%3A30-99", "🏠 Outdoor", False),
        ("https://www.amazon.sa/s?k=lighting&rh=p_8%3A30-99", "💡 Lighting", False),
        ("https://www.amazon.sa/s?k=smart+home&rh=p_8%3A30-99", "🏠 Smart Home", False),
        
        # 💊 صحة وغذاء (10 قسم)
        ("https://www.amazon.sa/s?k=vitamins&rh=p_8%3A30-99", "💊 Vitamins", False),
        ("https://www.amazon.sa/s?k=supplements&rh=p_8%3A30-99", "💊 Supplements", False),
        ("https://www.amazon.sa/s?k=omega+3&rh=p_8%3A30-99", "💊 Omega 3", False),
        ("https://www.amazon.sa/s?k=multivitamin&rh=p_8%3A30-99", "💊 Multivitamin", False),
        ("https://www.amazon.sa/s?k=probiotic&rh=p_8%3A30-99", "💊 Probiotic", False),
        ("https://www.amazon.sa/s?k=collagen&rh=p_8%3A30-99", "💊 Collagen", False),
        ("https://www.amazon.sa/s?k=organic+food&rh=p_8%3A30-99", "🥗 Organic Food", False),
        ("https://www.amazon.sa/s?k=gluten+free&rh=p_8%3A30-99", "🥗 Gluten Free", False),
        ("https://www.amazon.sa/s?k=keto&rh=p_8%3A30-99", "🥗 Keto", False),
        ("https://www.amazon.sa/s?k=vegan&rh=p_8%3A30-99", "🥗 Vegan", False),
        
        # 🎵 موسيقى وأدوات (8 قسم)
        ("https://www.amazon.sa/s?k=guitar&rh=p_8%3A30-99", "🎸 Guitar", False),
        ("https://www.amazon.sa/s?k=keyboard+piano&rh=p_8%3A30-99", "🎹 Keyboard", False),
        ("https://www.amazon.sa/s?k=drums&rh=p_8%3A30-99", "🥁 Drums", False),
        ("https://www.amazon.sa/s?k=piano&rh=p_8%3A30-99", "🎹 Piano", False),
        ("https://www.amazon.sa/s?k=yamaha+music&rh=p_8%3A30-99", "🎵 Yamaha Music", False),
        ("https://www.amazon.sa/s?k=casio+music&rh=p_8%3A30-99", "🎵 Casio Music", False),
        ("https://www.amazon.sa/s?k=microphone&rh=p_8%3A30-99", "🎤 Microphone", False),
        ("https://www.amazon.sa/s?k=audio+interface&rh=p_8%3A30-99", "🎵 Audio Interface", False),
        
        # 🐾 حيوانات أليفة إضافي (8 قسم)
        ("https://www.amazon.sa/s?k=royal+canin&rh=p_8%3A30-99", "🐾 Royal Canin", False),
        ("https://www.amazon.sa/s?k=whiskas&rh=p_8%3A30-99", "🐾 Whiskas", False),
        ("https://www.amazon.sa/s?k=felix+cat&rh=p_8%3A30-99", "🐾 Felix", False),
        ("https://www.amazon.sa/s?k=sheba&rh=p_8%3A30-99", "🐾 Sheba", False),
        ("https://www.amazon.sa/s?k=dog+food&rh=p_8%3A30-99", "🐾 Dog Food", False),
        ("https://www.amazon.sa/s?k=pedigree&rh=p_8%3A30-99", "🐾 Pedigree", False),
        ("https://www.amazon.sa/s?k=dog+treats&rh=p_8%3A30-99", "🐾 Dog Treats", False),
        ("https://www.amazon.sa/s?k=pet+toys&rh=p_8%3A30-99", "🐾 Pet Toys", False),
        
        # 🧹 تنظيف وصيانة (8 قسم)
        ("https://www.amazon.sa/s?k=fairy&rh=p_8%3A30-99", "🧹 Fairy", False),
        ("https://www.amazon.sa/s?k=persil&rh=p_8%3A30-99", "🧹 Persil", False),
        ("https://www.amazon.sa/s?k=ariel&rh=p_8%3A30-99", "🧹 Ariel", False),
        ("https://www.amazon.sa/s?k=tide&rh=p_8%3A30-99", "🧹 Tide", False),
        ("https://www.amazon.sa/s?k=downy&rh=p_8%3A30-99", "🧹 Downy", False),
        ("https://www.amazon.sa/s?k=comfort&rh=p_8%3A30-99", "🧹 Comfort", False),
        ("https://www.amazon.sa/s?k=finish&rh=p_8%3A30-99", "🧹 Finish", False),
        ("https://www.amazon.sa/s?k=dettol&rh=p_8%3A30-99", "🧹 Dettol", False),
        
        # 📱 إكسسوارات تقنية (8 قسم)
        ("https://www.amazon.sa/s?k=anker&rh=p_8%3A30-99", "🔌 Anker", False),
        ("https://www.amazon.sa/s?k=belkin&rh=p_8%3A30-99", "🔌 Belkin", False),
        ("https://www.amazon.sa/s?k=ugreen&rh=p_8%3A30-99", "🔌 Ugreen", False),
        ("https://www.amazon.sa/s?k=baseus&rh=p_8%3A30-99", "🔌 Baseus", False),
        ("https://www.amazon.sa/s?k=spigen&rh=p_8%3A30-99", "📱 Spigen", False),
        ("https://www.amazon.sa/s?k=screen+protector&rh=p_8%3A30-99", "📱 Screen Protector", False),
        ("https://www.amazon.sa/s?k=phone+case&rh=p_8%3A30-99", "📱 Phone Case", False),
        ("https://www.amazon.sa/s?k=power+bank&rh=p_8%3A30-99", "🔌 Power Bank", False),
        
        # 🎁 هدايا وألعاب (8 قسم)
        ("https://www.amazon.sa/s?k=gift+cards&rh=p_8%3A30-99", "🎁 Gift Cards", False),
        ("https://www.amazon.sa/s?k=board+games&rh=p_8%3A30-99", "🎲 Board Games", False),
        ("https://www.amazon.sa/s?k=puzzle&rh=p_8%3A30-99", "🧩 Puzzle", False),
        ("https://www.amazon.sa/s?k=card+games&rh=p_8%3A30-99", "🃏 Card Games", False),
        ("https://www.amazon.sa/s?k=chess&rh=p_8%3A30-99", "♟️ Chess", False),
        ("https://www.amazon.sa/s?k=darts&rh=p_8%3A30-99", "🎯 Darts", False),
        ("https://www.amazon.sa/s?k=billiard&rh=p_8%3A30-99", "🎱 Billiard", False),
        ("https://www.amazon.sa/s?k=collectibles&rh=p_8%3A30-99", "🎁 Collectibles", False),
    ]
    
    total = len(categories)
    
    for idx, (url, cat_name, is_best_seller) in enumerate(categories, 1):
        try:
            if idx % 10 == 0:
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
           
