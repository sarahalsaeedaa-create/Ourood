import os
import re
import json
import logging
import requests
import cloudscraper
from datetime import datetime, timedelta
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
DAILY_TARGET = 100  # هدف 100 منتج يومياً

ua = UserAgent()
sent_products = set()
sent_hashes = set()
sent_asins_today = set()
daily_deals_count = 0
last_reset_date = None
is_scanning = False
updater = None

def load_database():
    global sent_products, sent_hashes, sent_asins_today, daily_deals_count, last_reset_date
    try:
        if os.path.exists('bot_database.json'):
            with open('bot_database.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
                sent_products = set(data.get('ids', []))
                sent_hashes = set(data.get('hashes', []))
                sent_asins_today = set(data.get('asins_today', []))
                daily_deals_count = data.get('daily_count', 0)
                last_reset_date = data.get('last_reset', str(datetime.now().date()))
                
                # Check if new day
                today = str(datetime.now().date())
                if last_reset_date != today:
                    logger.info(f"🌅 New day! Resetting daily counters. Last: {last_reset_date}, Today: {today}")
                    sent_asins_today.clear()
                    daily_deals_count = 0
                    last_reset_date = today
                    save_database()
    except Exception as e:
        logger.error(f"Error loading DB: {e}")

def save_database():
    try:
        with open('bot_database.json', 'w', encoding='utf-8') as f:
            json.dump({
                'ids': list(sent_products),
                'hashes': list(sent_hashes),
                'asins_today': list(sent_asins_today),
                'daily_count': daily_deals_count,
                'last_reset': last_reset_date
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
    for word in ['amazon', 'saudi', 'ريال', 'sar', 'new', 'جديد', 'shipped', 'شحن', '2024', '2025']:
        clean = clean.replace(word, '')
    return hashlib.md5(clean[:40].strip().encode()).hexdigest()[:20]

def is_similar_product(title):
    new_hash = create_title_hash(title)
    if new_hash in sent_hashes:
        return True
    # Check similarity with recent products
    for existing_hash in list(sent_hashes)[-500:]:
        if SequenceMatcher(None, new_hash[:15], existing_hash[:15]).ratio() > 0.85:
            return True
    return False

def get_product_id(deal):
    asin = extract_asin(deal.get('link', ''))
    if asin:
        return f"ASIN_{asin}"
    key = f"{deal.get('title', '')}_{deal.get('price', 0)}_{deal.get('category', '')}"
    return f"HASH_{hashlib.md5(key.encode()).hexdigest()[:16]}"

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
            time.sleep(random.uniform(0.5, 1.5))
            r = session.get(url, timeout=30)
            if r.status_code == 200:
                return r.text
            time.sleep(2)
        except Exception as e:
            logger.warning(f"Attempt {i+1} failed: {e}")
    return None

# ========== 300+ قسم شامل ==========
def get_all_categories():
    """جميع الأقسام المتاحة - يتم تدويرها يومياً"""
    
    # أقسام Best Sellers (أولوية عالية)
    best_sellers = [
        ("https://www.amazon.sa/gp/bestsellers/electronics", "📱 Electronics BS", True),
        ("https://www.amazon.sa/gp/bestsellers/fashion", "👕 Fashion BS", True),
        ("https://www.amazon.sa/gp/bestsellers/beauty", "💄 Beauty BS", True),
        ("https://www.amazon.sa/gp/bestsellers/watches", "⌚ Watches BS", True),
        ("https://www.amazon.sa/gp/bestsellers/shoes", "👟 Shoes BS", True),
        ("https://www.amazon.sa/gp/bestsellers/kitchen", "🍳 Kitchen BS", True),
        ("https://www.amazon.sa/gp/bestsellers/home", "🏠 Home BS", True),
        ("https://www.amazon.sa/gp/bestsellers/computers", "💻 Computers BS", True),
        ("https://www.amazon.sa/gp/bestsellers/mobile", "📱 Mobile BS", True),
        ("https://www.amazon.sa/gp/bestsellers/perfumes", "🌸 Perfumes BS", True),
        ("https://www.amazon.sa/gp/bestsellers/toys", "🎮 Toys BS", True),
        ("https://www.amazon.sa/gp/bestsellers/sports", "⚽ Sports BS", True),
        ("https://www.amazon.sa/gp/bestsellers/baby", "👶 Baby BS", True),
        ("https://www.amazon.sa/gp/bestsellers/automotive", "🚗 Automotive BS", True),
        ("https://www.amazon.sa/gp/bestsellers/tools", "🔧 Tools BS", True),
        ("https://www.amazon.sa/gp/bestsellers/jewelry", "💎 Jewelry BS", True),
        ("https://www.amazon.sa/gp/bestsellers/luggage", "🧳 Luggage BS", True),
        ("https://www.amazon.sa/gp/bestsellers/pet", "🐾 Pet BS", True),
        ("https://www.amazon.sa/gp/bestsellers/office", "📎 Office BS", True),
        ("https://www.amazon.sa/gp/bestsellers/health", "💊 Health BS", True),
        ("https://www.amazon.sa/gp/bestsellers/video-games", "🎮 Games BS", True),
        ("https://www.amazon.sa/gp/bestsellers/camera", "📷 Camera BS", True),
        ("https://www.amazon.sa/gp/bestsellers/personal-care", "🧴 Personal Care BS", True),
        ("https://www.amazon.sa/gp/bestsellers/grocery", "🛒 Grocery BS", True),
        ("https://www.amazon.sa/gp/bestsellers/books", "📚 Books BS", True),
    ]
    
    # عروض رسمية
    official_deals = [
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
        ("https://www.amazon.sa/deals/jewelry", "💎 Jewelry Deals", False),
        ("https://www.amazon.sa/deals/luggage", "🧳 Luggage Deals", False),
        ("https://www.amazon.sa/deals/pet", "🐾 Pet Deals", False),
        ("https://www.amazon.sa/deals/health", "💊 Health Deals", False),
    ]
    
    # Warehouse & Outlet
    warehouse = [
        ("https://www.amazon.sa/gp/warehouse-deals", "🏭 Warehouse", False),
        ("https://www.amazon.sa/gp/warehouse-deals/electronics", "🏭 W Electronics", False),
        ("https://www.amazon.sa/gp/warehouse-deals/fashion", "🏭 W Fashion", False),
        ("https://www.amazon.sa/gp/warehouse-deals/home", "🏭 W Home", False),
        ("https://www.amazon.sa/gp/warehouse-deals/kitchen", "🏭 W Kitchen", False),
        ("https://www.amazon.sa/gp/warehouse-deals/beauty", "🏭 W Beauty", False),
        ("https://www.amazon.sa/gp/warehouse-deals/sports", "🏭 W Sports", False),
        ("https://www.amazon.sa/gp/warehouse-deals/tools", "🏭 W Tools", False),
        ("https://www.amazon.sa/gp/warehouse-deals/toys", "🏭 W Toys", False),
        ("https://www.amazon.sa/gp/warehouse-deals/books", "🏭 W Books", False),
        ("https://www.amazon.sa/outlet", "🎁 Outlet", False),
        ("https://www.amazon.sa/outlet/electronics", "🎁 O Electronics", False),
        ("https://www.amazon.sa/outlet/home", "🎁 O Home", False),
        ("https://www.amazon.sa/outlet/fashion", "🎁 O Fashion", False),
        ("https://www.amazon.sa/outlet/beauty", "🎁 O Beauty", False),
    ]
    
    # Prime & Lightning
    prime_lightning = [
        ("https://www.amazon.sa/gp/prime/pipeline/prime_exclusives", "👑 Prime", False),
        ("https://www.amazon.sa/gp/prime/pipeline/lightning_deals", "⚡ Lightning", False),
        ("https://www.amazon.sa/gp/todays-deals", "📅 Today", False),
        ("https://www.amazon.sa/gp/todays-deals/electronics", "📅 T Electronics", False),
        ("https://www.amazon.sa/gp/todays-deals/fashion", "📅 T Fashion", False),
        ("https://www.amazon.sa/gp/todays-deals/home", "📅 T Home", False),
        ("https://www.amazon.sa/gp/todays-deals/beauty", "📅 T Beauty", False),
    ]
    
    # Coupons
    coupons = [
        ("https://www.amazon.sa/gp/coupons", "🎟️ Coupons", False),
        ("https://www.amazon.sa/gp/coupons/electronics", "🎟️ C Electronics", False),
        ("https://www.amazon.sa/gp/coupons/fashion", "🎟️ C Fashion", False),
        ("https://www.amazon.sa/gp/coupons/home", "🎟️ C Home", False),
        ("https://www.amazon.sa/gp/coupons/beauty", "🎟️ C Beauty", False),
        ("https://www.amazon.sa/gp/coupons/grocery", "🎟️ C Grocery", False),
        ("https://www.amazon.sa/gp/coupons/baby", "🎟️ C Baby", False),
    ]
    
    # عروض سرية
    hidden = [
        ("https://www.amazon.sa/s?k=clearance&rh=p_8%3A40-99", "🔥 Clearance", False),
        ("https://www.amazon.sa/s?k=last+chance&rh=p_8%3A40-99", "🔥 Last Chance", False),
        ("https://www.amazon.sa/s?k=final+sale&rh=p_8%3A40-99", "🔥 Final Sale", False),
        ("https://www.amazon.sa/s?k=limited+time&rh=p_8%3A40-99", "⏰ Limited", False),
        ("https://www.amazon.sa/s?k=flash+sale&rh=p_8%3A40-99", "⚡ Flash", False),
        ("https://www.amazon.sa/s?k=super+sale&rh=p_8%3A40-99", "💥 Super", False),
        ("https://www.amazon.sa/s?k=mega+deal&rh=p_8%3A40-99", "🎯 Mega", False),
        ("https://www.amazon.sa/s?k=big+sale&rh=p_8%3A40-99", "🎪 Big", False),
        ("https://www.amazon.sa/s?k=special+offer&rh=p_8%3A40-99", "🎁 Special", False),
        ("https://www.amazon.sa/s?k=hot+deal&rh=p_8%3A40-99", "🔥 Hot", False),
    ]
    
    # Apple
    apple = [
        ("https://www.amazon.sa/s?k=iphone+15&rh=p_8%3A30-99", "🍎 iPhone 15", False),
        ("https://www.amazon.sa/s?k=iphone+14&rh=p_8%3A30-99", "🍎 iPhone 14", False),
        ("https://www.amazon.sa/s?k=iphone+13&rh=p_8%3A30-99", "🍎 iPhone 13", False),
        ("https://www.amazon.sa/s?k=ipad+pro&rh=p_8%3A30-99", "🍎 iPad Pro", False),
        ("https://www.amazon.sa/s?k=ipad+air&rh=p_8%3A30-99", "🍎 iPad Air", False),
        ("https://www.amazon.sa/s?k=macbook+pro&rh=p_8%3A30-99", "🍎 MacBook Pro", False),
        ("https://www.amazon.sa/s?k=macbook+air&rh=p_8%3A30-99", "🍎 MacBook Air", False),
        ("https://www.amazon.sa/s?k=airpods+pro&rh=p_8%3A30-99", "🍎 AirPods Pro", False),
        ("https://www.amazon.sa/s?k=airpods+max&rh=p_8%3A30-99", "🍎 AirPods Max", False),
        ("https://www.amazon.sa/s?k=apple+watch+ultra&rh=p_8%3A30-99", "🍎 Watch Ultra", False),
        ("https://www.amazon.sa/s?k=apple+watch+series+9&rh=p_8%3A30-99", "🍎 Watch S9", False),
        ("https://www.amazon.sa/s?k=apple+tv+4k&rh=p_8%3A30-99", "🍎 TV 4K", False),
    ]
    
    # Samsung
    samsung = [
        ("https://www.amazon.sa/s?k=samsung+s24&rh=p_8%3A30-99", "📱 S24", False),
        ("https://www.amazon.sa/s?k=samsung+s23&rh=p_8%3A30-99", "📱 S23", False),
        ("https://www.amazon.sa/s?k=samsung+z+fold&rh=p_8%3A30-99", "📱 Z Fold", False),
        ("https://www.amazon.sa/s?k=samsung+z+flip&rh=p_8%3A30-99", "📱 Z Flip", False),
        ("https://www.amazon.sa/s?k=samsung+tab+s9&rh=p_8%3A30-99", "📱 Tab S9", False),
        ("https://www.amazon.sa/s?k=samsung+watch+6&rh=p_8%3A30-99", "📱 Watch 6", False),
        ("https://www.amazon.sa/s?k=samsung+buds&rh=p_8%3A30-99", "📱 Buds", False),
        ("https://www.amazon.sa/s?k=samsung+neo+qled&rh=p_8%3A30-99", "📱 Neo QLED", False),
    ]
    
    # سماعات
    headphones = [
        ("https://www.amazon.sa/s?k=sony+wh-1000xm5&rh=p_8%3A30-99", "🎧 Sony XM5", False),
        ("https://www.amazon.sa/s?k=sony+wh-1000xm4&rh=p_8%3A30-99", "🎧 Sony XM4", False),
        ("https://www.amazon.sa/s?k=bose+quietcomfort&rh=p_8%3A30-99", "🎧 Bose QC", False),
        ("https://www.amazon.sa/s?k=beats+studio&rh=p_8%3A30-99", "🎧 Beats Studio", False),
        ("https://www.amazon.sa/s?k=jbl+tour&rh=p_8%3A30-99", "🎧 JBL Tour", False),
        ("https://www.amazon.sa/s?k=harman+kardon+aura&rh=p_8%3A30-99", "🎧 HK Aura", False),
        ("https://www.amazon.sa/s?k=marshall+stanmore&rh=p_8%3A30-99", "🎧 Marshall", False),
        ("https://www.amazon.sa/s?k=sennheiser+momentum&rh=p_8%3A30-99", "🎧 Sennheiser", False),
    ]
    
    # لابتوبات
    laptops = [
        ("https://www.amazon.sa/s?k=lenovo+thinkpad&rh=p_8%3A30-99", "💻 ThinkPad", False),
        ("https://www.amazon.sa/s?k=lenovo+yoga&rh=p_8%3A30-99", "💻 Yoga", False),
        ("https://www.amazon.sa/s?k=lenovo+legion&rh=p_8%3A30-99", "💻 Legion", False),
        ("https://www.amazon.sa/s?k=hp+spectre&rh=p_8%3A30-99", "💻 Spectre", False),
        ("https://www.amazon.sa/s?k=hp+envy&rh=p_8%3A30-99", "💻 Envy", False),
        ("https://www.amazon.sa/s?k=hp+pavilion&rh=p_8%3A30-99", "💻 Pavilion", False),
        ("https://www.amazon.sa/s?k=dell+xps&rh=p_8%3A30-99", "💻 XPS", False),
        ("https://www.amazon.sa/s?k=dell+inspiron&rh=p_8%3A30-99", "💻 Inspiron", False),
        ("https://www.amazon.sa/s?k=dell+alienware&rh=p_8%3A30-99", "💻 Alienware", False),
        ("https://www.amazon.sa/s?k=asus+zenbook&rh=p_8%3A30-99", "💻 ZenBook", False),
        ("https://www.amazon.sa/s?k=asus+rog&rh=p_8%3A30-99", "💻 ROG", False),
        ("https://www.amazon.sa/s?k=asus+vivobook&rh=p_8%3A30-99", "💻 VivoBook", False),
        ("https://www.amazon.sa/s?k=acer+predator&rh=p_8%3A30-99", "💻 Predator", False),
        ("https://www.amazon.sa/s?k=acer+swift&rh=p_8%3A30-99", "💻 Swift", False),
        ("https://www.amazon.sa/s?k=msi+stealth&rh=p_8%3A30-99", "💻 MSI Stealth", False),
        ("https://www.amazon.sa/s?k=razer+blade&rh=p_8%3A30-99", "💻 Razer Blade", False),
        ("https://www.amazon.sa/s?k=microsoft+surface&rh=p_8%3A30-99", "💻 Surface", False),
    ]
    
    # Gaming
    gaming = [
        ("https://www.amazon.sa/s?k=playstation+5&rh=p_8%3A30-99", "🎮 PS5", False),
        ("https://www.amazon.sa/s?k=playstation+5+slim&rh=p_8%3A30-99", "🎮 PS5 Slim", False),
        ("https://www.amazon.sa/s?k=ps5+controller&rh=p_8%3A30-99", "🎮 PS5 Controller", False),
        ("https://www.amazon.sa/s?k=ps5+games&rh=p_8%3A30-99", "🎮 PS5 Games", False),
        ("https://www.amazon.sa/s?k=xbox+series+x&rh=p_8%3A30-99", "🎮 Xbox X", False),
        ("https://www.amazon.sa/s?k=xbox+series+s&rh=p_8%3A30-99", "🎮 Xbox S", False),
        ("https://www.amazon.sa/s?k=nintendo+switch+oled&rh=p_8%3A30-99", "🎮 Switch OLED", False),
        ("https://www.amazon.sa/s?k=steam+deck&rh=p_8%3A30-99", "🎮 Steam Deck", False),
        ("https://www.amazon.sa/s?k=rog+ally&rh=p_8%3A30-99", "🎮 ROG Ally", False),
        ("https://www.amazon.sa/s?k=logitech+g+pro&rh=p_8%3A30-99", "🎮 G Pro", False),
        ("https://www.amazon.sa/s?k=razer+deathadder&rh=p_8%3A30-99", "🎮 DeathAdder", False),
        ("https://www.amazon.sa/s?k=corsair+keyboard&rh=p_8%3A30-99", "🎮 Corsair KB", False),
        ("https://www.amazon.sa/s?k=rtx+4090&rh=p_8%3A30-99", "🎮 RTX 4090", False),
        ("https://www.amazon.sa/s?k=rtx+4080&rh=p_8%3A30-99", "🎮 RTX 4080", False),
        ("https://www.amazon.sa/s?k=rtx+4070&rh=p_8%3A30-99", "🎮 RTX 4070", False),
    ]
    
    # كاميرات
    cameras = [
        ("https://www.amazon.sa/s?k=canon+eos+r5&rh=p_8%3A30-99", "📷 EOS R5", False),
        ("https://www.amazon.sa/s?k=canon+eos+r6&rh=p_8%3A30-99", "📷 EOS R6", False),
        ("https://www.amazon.sa/s?k=sony+a7iv&rh=p_8%3A30-99", "📷 A7 IV", False),
        ("https://www.amazon.sa/s?k=sony+a7iii&rh=p_8%3A30-99", "📷 A7 III", False),
        ("https://www.amazon.sa/s?k=nikon+z6&rh=p_8%3A30-99", "📷 Z6", False),
        ("https://www.amazon.sa/s?k=fujifilm+xt5&rh=p_8%3A30-99", "📷 X-T5", False),
        ("https://www.amazon.sa/s?k=gopro+hero12&rh=p_8%3A30-99", "📷 Hero 12", False),
        ("https://www.amazon.sa/s?k=dji+mini+4&rh=p_8%3A30-99", "📷 Mini 4", False),
        ("https://www.amazon.sa/s?k=dji+air+3&rh=p_8%3A30-99", "📷 Air 3", False),
    ]
    
    # ساعات ذكية
    smartwatches = [
        ("https://www.amazon.sa/s?k=apple+watch+ultra+2&rh=p_8%3A30-99", "⌚ Ultra 2", False),
        ("https://www.amazon.sa/s?k=garmin+fenix&rh=p_8%3A30-99", "⌚ Fenix", False),
        ("https://www.amazon.sa/s?k=garmin+forerunner&rh=p_8%3A30-99", "⌚ Forerunner", False),
        ("https://www.amazon.sa/s?k=fitbit+sense&rh=p_8%3A30-99", "⌚ Sense", False),
        ("https://www.amazon.sa/s?k=fitbit+versa&rh=p_8%3A30-99", "⌚ Versa", False),
        ("https://www.amazon.sa/s?k=huawei+watch+gt&rh=p_8%3A30-99", "⌚ Watch GT", False),
        ("https://www.amazon.sa/s?k=amazfit+gtr&rh=p_8%3A30-99", "⌚ GTR", False),
        ("https://www.amazon.sa/s?k=xiaomi+watch&rh=p_8%3A30-99", "⌚ Xiaomi", False),
    ]
    
    # ساعات تقليدية
    traditional_watches = [
        ("https://www.amazon.sa/s?k=casio+g+shock&rh=p_8%3A30-99", "⌚ G-Shock", False),
        ("https://www.amazon.sa/s?k=casio+edifice&rh=p_8%3A30-99", "⌚ Edifice", False),
        ("https://www.amazon.sa/s?k=casio+protrek&rh=p_8%3A30-99", "⌚ ProTrek", False),
        ("https://www.amazon.sa/s?k=seiko+5&rh=p_8%3A30-99", "⌚ Seiko 5", False),
        ("https://www.amazon.sa/s?k=seiko+prospex&rh=p_8%3A30-99", "⌚ Prospex", False),
        ("https://www.amazon.sa/s?k=citizen+eco+drive&rh=p_8%3A30-99", "⌚ Eco-Drive", False),
        ("https://www.amazon.sa/s?k=orient&rh=p_8%3A30-99", "⌚ Orient", False),
        ("https://www.amazon.sa/s?k=fossil+watch&rh=p_8%3A30-99", "⌚ Fossil", False),
        ("https://www.amazon.sa/s?k=michael+kors+watch&rh=p_8%3A30-99", "⌚ MK Watch", False),
        ("https://www.amazon.sa/s?k=emporio+armani+watch&rh=p_8%3A30-99", "⌚ EA Watch", False),
    ]
    
    # عطور فاخرة
    luxury_perfumes = [
        ("https://www.amazon.sa/s?k=chanel+no+5&rh=p_8%3A30-99", "🌸 No.5", False),
        ("https://www.amazon.sa/s?k=chanel+bleu&rh=p_8%3A30-99", "🌸 Bleu", False),
        ("https://www.amazon.sa/s?k=dior+sauvage&rh=p_8%3A30-99", "🌸 Sauvage", False),
        ("https://www.amazon.sa/s?k=dior+jadore&rh=p_8%3A30-99", "🌸 J'adore", False),
        ("https://www.amazon.sa/s?k=gucci+bloom&rh=p_8%3A30-99", "🌸 Bloom", False),
        ("https://www.amazon.sa/s?k=gucci+guilty&rh=p_8%3A30-99", "🌸 Guilty", False),
        ("https://www.amazon.sa/s?k=versace+eros&rh=p_8%3A30-99", "🌸 Eros", False),
        ("https://www.amazon.sa/s?k=versace+dylan+blue&rh=p_8%3A30-99", "🌸 Dylan", False),
        ("https://www.amazon.sa/s?k=armani+code&rh=p_8%3A30-99", "🌸 Code", False),
        ("https://www.amazon.sa/s?k=armani+acqua&rh=p_8%3A30-99", "🌸 Acqua", False),
        ("https://www.amazon.sa/s?k=prada+luna+rossa&rh=p_8%3A30-99", "🌸 Luna", False),
        ("https://www.amazon.sa/s?k=burberry+her&rh=p_8%3A30-99", "🌸 Her", False),
        ("https://www.amazon.sa/s?k=ck+one&rh=p_8%3A30-99", "🌸 CK One", False),
        ("https://www.amazon.sa/s?k=tom+ford+black+orchid&rh=p_8%3A30-99", "🌸 Black Orchid", False),
        ("https://www.amazon.sa/s?k=ysl+libre&rh=p_8%3A30-99", "🌸 Libre", False),
        ("https://www.amazon.sa/s?k=creed+aventus&rh=p_8%3A30-99", "🌸 Aventus", False),
        ("https://www.amazon.sa/s?k=jo+malone&rh=p_8%3A30-99", "🌸 Jo Malone", False),
        ("https://www.amazon.sa/s?k=lancome+la+vie&rh=p_8%3A30-99", "🌸 La Vie", False),
    ]
    
    # أحذية رياضية
    sneakers = [
        ("https://www.amazon.sa/s?k=nike+air+force&rh=p_8%3A30-99", "👟 Air Force", False),
        ("https://www.amazon.sa/s?k=nike+air+max&rh=p_8%3A30-99", "👟 Air Max", False),
        ("https://www.amazon.sa/s?k=nike+dunk&rh=p_8%3A30-99", "👟 Dunk", False),
        ("https://www.amazon.sa/s?k=jordan+1&rh=p_8%3A30-99", "👟 Jordan 1", False),
        ("https://www.amazon.sa/s?k=jordan+4&rh=p_8%3A30-99", "👟 Jordan 4", False),
        ("https://www.amazon.sa/s?k=adidas+ultraboost&rh=p_8%3A30-99", "👟 Ultraboost", False),
        ("https://www.amazon.sa/s?k=adidas+nmd&rh=p_8%3A30-99", "👟 NMD", False),
        ("https://www.amazon.sa/s?k=adidas+samba&rh=p_8%3A30-99", "👟 Samba", False),
        ("https://www.amazon.sa/s?k=adidas+gazelle&rh=p_8%3A30-99", "👟 Gazelle", False),
        ("https://www.amazon.sa/s?k=yeezy+boost&rh=p_8%3A30-99", "👟 Yeezy", False),
        ("https://www.amazon.sa/s?k=new+balance+550&rh=p_8%3A30-99", "👟 NB 550", False),
        ("https://www.amazon.sa/s?k=new+balance+574&rh=p_8%3A30-99", "👟 NB 574", False),
        ("https://www.amazon.sa/s?k=puma+suede&rh=p_8%3A30-99", "👟 Suede", False),
        ("https://www.amazon.sa/s?k=puma+rs+x&rh=p_8%3A30-99", "👟 RS-X", False),
        ("https://www.amazon.sa/s?k=reebok+classic&rh=p_8%3A30-99", "👟 Classic", False),
        ("https://www.amazon.sa/s?k=under+armour+curry&rh=p_8%3A30-99", "👟 Curry", False),
        ("https://www.amazon.sa/s?k=asics+gel&rh=p_8%3A30-99", "👟 Gel", False),
        ("https://www.amazon.sa/s?k=vans+old+skool&rh=p_8%3A30-99", "👟 Old Skool", False),
        ("https://www.amazon.sa/s?k=converse+chuck&rh=p_8%3A30-99", "👟 Chuck", False),
        ("https://www.amazon.sa/s?k=crocs+classic&rh=p_8%3A30-99", "👟 Crocs", False),
    ]
    
    # ملابس رجالي
    men_clothing = [
        ("https://www.amazon.sa/s?k=calvin+klein+underwear&rh=p_8%3A30-99", "👔 CK Underwear", False),
        ("https://www.amazon.sa/s?k=calvin+klein+jeans&rh=p_8%3A30-99", "👔 CK Jeans", False),
        ("https://www.amazon.sa/s?k=tommy+hilfiger+shirt&rh=p_8%3A30-99", "👔 Tommy Shirt", False),
        ("https://www.amazon.sa/s?k=tommy+hilfiger+polo&rh=p_8%3A30-99", "👔 Tommy Polo", False),
        ("https://www.amazon.sa/s?k=ralph+lauren+polo&rh=p_8%3A30-99", "👔 RL Polo", False),
        ("https://www.amazon.sa/s?k=lacoste+polo&rh=p_8%3A30-99", "👔 Lacoste Polo", False),
        ("https://www.amazon.sa/s?k=hugo+boss+suit&rh=p_8%3A30-99", "👔 Boss Suit", False),
        ("https://www.amazon.sa/s?k=hugo+boss+shirt&rh=p_8%3A30-99", "👔 Boss Shirt", False),
        ("https://www.amazon.sa/s?k=levis+501&rh=p_8%3A30-99", "👔 Levi's 501", False),
        ("https://www.amazon.sa/s?k=levis+511&rh=p_8%3A30-99", "👔 Levi's 511", False),
        ("https://www.amazon.sa/s?k=wrangler+jeans&rh=p_8%3A30-99", "👔 Wrangler", False),
        ("https://www.amazon.sa/s?k=diesel+jeans&rh=p_8%3A30-99", "👔 Diesel", False),
        ("https://www.amazon.sa/s?k=g+star+raw&rh=p_8%3A30-99", "👔 G-Star", False),
        ("https://www.amazon.sa/s?k=timberland+boots&rh=p_8%3A30-99", "👔 Timberland", False),
        ("https://www.amazon.sa/s?k=timberland+shoes&rh=p_8%3A30-99", "👔 Timberland Shoes", False),
    ]
    
    # شنط وإكسسوارات
    bags = [
        ("https://www.amazon.sa/s?k=michael+kors+bag&rh=p_8%3A30-99", "👜 MK Bag", False),
        ("https://www.amazon.sa/s?k=michael+kors+backpack&rh=p_8%3A30-99", "👜 MK Backpack", False),
        ("https://www.amazon.sa/s?k=kate+spade+bag&rh=p_8%3A30-99", "👜 Kate Spade", False),
        ("https://www.amazon.sa/s?k=coach+bag&rh=p_8%3A30-99", "👜 Coach Bag", False),
        ("https://www.amazon.sa/s?k=coach+wallet&rh=p_8%3A30-99", "👜 Coach Wallet", False),
        ("https://www.amazon.sa/s?k=guess+bag&rh=p_8%3A30-99", "👜 Guess Bag", False),
        ("https://www.amazon.sa/s?k=fossil+bag&rh=p_8%3A30-99", "👜 Fossil Bag", False),
        ("https://www.amazon.sa/s?k=vera+bradley&rh=p_8%3A30-99", "👜 Vera Bradley", False),
        ("https://www.amazon.sa/s?k=longchamp+bag&rh=p_8%3A30-99", "👜 Longchamp", False),
        ("https://www.amazon.sa/s?k=tumi+backpack&rh=p_8%3A30-99", "🧳 Tumi", False),
        ("https://www.amazon.sa/s?k=samsonite+luggage&rh=p_8%3A30-99", "🧳 Samsonite", False),
        ("https://www.amazon.sa/s?k=rimowa&rh=p_8%3A30-99", "🧳 Rimowa", False),
        ("https://www.amazon.sa/s?k=north+face+backpack&rh=p_8%3A30-99", "🎒 North Face", False),
        ("https://www.amazon.sa/s?k=herschel+backpack&rh=p_8%3A30-99", "🎒 Herschel", False),
        ("https://www.amazon.sa/s?k=jan+sport&rh=p_8%3A30-99", "🎒 JanSport", False),
    ]
    
    # مجوهرات وإكسسوارات
    jewelry = [
        ("https://www.amazon.sa/s?k=swarovski+necklace&rh=p_8%3A30-99", "💎 Swarovski", False),
        ("https://www.amazon.sa/s?k=swarovski+earrings&rh=p_8%3A30-99", "💎 SW Earrings", False),
        ("https://www.amazon.sa/s?k=pandora+bracelet&rh=p_8%3A30-99", "💎 Pandora", False),
        ("https://www.amazon.sa/s?k=pandora+charms&rh=p_8%3A30-99", "💎 Charms", False),
        ("https://www.amazon.sa/s?k=tiffany+necklace&rh=p_8%3A30-99", "💎 Tiffany", False),
        ("https://www.amazon.sa/s?k=bulova+watch&rh=p_8%3A30-99", "💎 Bulova", False),
        ("https://www.amazon.sa/s?k=anne+klein+watch&rh=p_8%3A30-99", "💎 Anne Klein", False),
        ("https://www.amazon.sa/s?k=casio+watch&rh=p_8%3A30-99", "💎 Casio", False),
    ]
    
    # نظارات
    sunglasses = [
        ("https://www.amazon.sa/s?k=ray+ban+aviator&rh=p_8%3A30-99", "🕶️ Aviator", False),
        ("https://www.amazon.sa/s?k=ray+ban+wayfarer&rh=p_8%3A30-99", "🕶️ Wayfarer", False),
        ("https://www.amazon.sa/s?k=ray+ban+clubmaster&rh=p_8%3A30-99", "🕶️ Clubmaster", False),
        ("https://www.amazon.sa/s?k=oakley+holbrook&rh=p_8%3A30-99", "🕶️ Holbrook", False),
        ("https://www.amazon.sa/s?k=oakley+frogskins&rh=p_8%3A30-99", "🕶️ Frogskins", False),
        ("https://www.amazon.sa/s?k=persol+po0649&rh=p_8%3A30-99", "🕶️ Persol", False),
        ("https://www.amazon.sa/s?k=prada+sunglasses&rh=p_8%3A30-99", "🕶️ Prada", False),
        ("https://www.amazon.sa/s?k=gucci+sunglasses&rh=p_8%3A30-99", "🕶️ Gucci", False),
        ("https://www.amazon.sa/s?k=burberry+sunglasses&rh=p_8%3A30-99", "🕶️ Burberry", False),
        ("https://www.amazon.sa/s?k=maui+jim&rh=p_8%3A30-99", "🕶️ Maui Jim", False),
    ]
    
    # مكياج
    makeup = [
        ("https://www.amazon.sa/s?k=mac+lipstick&rh=p_8%3A30-99", "💄 MAC Lip", False),
        ("https://www.amazon.sa/s?k=mac+foundation&rh=p_8%3A30-99", "💄 MAC Base", False),
        ("https://www.amazon.sa/s?k=nyx+palette&rh=p_8%3A30-99", "💄 NYX", False),
        ("https://www.amazon.sa/s?k=maybelline+mascara&rh=p_8%3A30-99", "💄 Maybelline", False),
        ("https://www.amazon.sa/s?k=loreal+paris+makeup&rh=p_8%3A30-99", "💄 L'Oreal", False),
        ("https://www.amazon.sa/s?k=revlon+lipstick&rh=p_8%3A30-99", "💄 Revlon", False),
        ("https://www.amazon.sa/s?k=covergirl+foundation&rh=p_8%3A30-99", "💄 Covergirl", False),
        ("https://www.amazon.sa/s?k=bobbi+brown&rh=p_8%3A30-99", "💄 Bobbi Brown", False),
        ("https://www.amazon.sa/s?k=anastasia+beverly+hills&rh=p_8%3A30-99", "💄 ABH", False),
        ("https://www.amazon.sa/s?k=huda+beauty+palette&rh=p_8%3A30-99", "💄 Huda", False),
        ("https://www.amazon.sa/s?k=fenty+beauty&rh=p_8%3A30-99", "💄 Fenty", False),
        ("https://www.amazon.sa/s?k=rare+beauty&rh=p_8%3A30-99", "💄 Rare", False),
        ("https://www.amazon.sa/s?k=charlotte+tilbury&rh=p_8%3A30-99", "💄 CT", False),
        ("https://www.amazon.sa/s?k=nars+makeup&rh=p_8%3A30-99", "💄 NARS", False),
        ("https://www.amazon.sa/s?k=urban+decay&rh=p_8%3A30-99", "💄 Urban Decay", False),
    ]
    
    # عناية بالبشرة
    skincare = [
        ("https://www.amazon.sa/s?k=olay+regenerist&rh=p_8%3A30-99", "💆 Olay", False),
        ("https://www.amazon.sa/s?k=neutrogena+hydro+boost&rh=p_8%3A30-99", "💆 Neutrogena", False),
        ("https://www.amazon.sa/s?k=cerave+moisturizer&rh=p_8%3A30-99", "💆 CeraVe", False),
        ("https://www.amazon.sa/s?k=cetaphil+cleanser&rh=p_8%3A30-99", "💆 Cetaphil", False),
        ("https://www.amazon.sa/s?k=la+roche+posay+effaclar&rh=p_8%3A30-99", "💆 La Roche", False),
        ("https://www.amazon.sa/s?k=vichy+mineral+89&rh=p_8%3A30-99", "💆 Vichy", False),
        ("https://www.amazon.sa/s?k=eucerin+urea&rh=p_8%3A30-99", "💆 Eucerin", False),
        ("https://www.amazon.sa/s?k=aveeno+daily&rh=p_8%3A30-99", "💆 Aveeno", False),
        ("https://www.amazon.sa/s?k=bioderma+sensibio&rh=p_8%3A30-99", "💆 Bioderma", False),
        ("https://www.amazon.sa/s?k=the+ordinary&rh=p_8%3A30-99", "💆 The Ordinary", False),
        ("https://www.amazon.sa/s?k=paulas+choice&rh=p_8%3A30-99", "💆 Paula's", False),
        ("https://www.amazon.sa/s?k=drunk+elephant&rh=p_8%3A30-99", "💆 Drunk Elephant", False),
        ("https://www.amazon.sa/s?k=skinceuticals&rh=p_8%3A30-99", "💆 SkinCeuticals", False),
        ("https://www.amazon.sa/s?k=estee+lauder+advanced&rh=p_8%3A30-99", "💆 EL Advanced", False),
        ("https://www.amazon.sa/s?k=lancome+genifique&rh=p_8%3A30-99", "💆 Genifique", False),
        ("https://www.amazon.sa/s?k=clinique+moisture&rh=p_8%3A30-99", "💆 Clinique", False),
        ("https://www.amazon.sa/s?k=kiehls&rh=p_8%3A30-99", "💆 Kiehl's", False),
        ("https://www.amazon.sa/s?k=fresh+beauty&rh=p_8%3A30-99", "💆 Fresh", False),
        ("https://www.amazon.sa/s?k=tatcha&rh=p_8%3A30-99", "💆 Tatcha", False),
        ("https://www.amazon.sa/s?k=laneige&rh=p_8%3A30-99", "💆 Laneige", False),
    ]
    
    # شعر
    haircare = [
        ("https://www.amazon.sa/s?k=pantene+pro+v&rh=p_8%3A30-99", "💇 Pantene", False),
        ("https://www.amazon.sa/s?k=head+shoulders&rh=p_8%3A30-99", "💇 H&S", False),
        ("https://www.amazon.sa/s?k=dove+shampoo&rh=p_8%3A30-99", "💇 Dove", False),
        ("https://www.amazon.sa/s?k=kerastase&rh=p_8%3A30-99", "💇 Kerastase", False),
        ("https://www.amazon.sa/s?k=loreal+professional&rh=p_8%3A30-99", "💇 L'Oreal Pro", False),
        ("https://www.amazon.sa/s?k=redken&rh=p_8%3A30-99", "💇 Redken", False),
        ("https://www.amazon.sa/s?k=matrix&rh=p_8%3A30-99", "💇 Matrix", False),
        ("https://www.amazon.sa/s?k=wella&rh=p_8%3A30-99", "💇 Wella", False),
        ("https://www.amazon.sa/s?k=schwarzkopf&rh=p_8%3A30-99", "💇 Schwarzkopf", False),
        ("https://www.amazon.sa/s?k=garnier+hair&rh=p_8%3A30-99", "💇 Garnier", False),
        ("https://www.amazon.sa/s?k=herbal+essences&rh=p_8%3A30-99", "💇 Herbal", False),
        ("https://www.amazon.sa/s?k=ogx+shampoo&rh=p_8%3A30-99", "💇 OGX", False),
        ("https://www.amazon.sa/s?k=moroccanoil&rh=p_8%3A30-99", "💇 Moroccanoil", False),
        ("https://www.amazon.sa/s?k=olaplex&rh=p_8%3A30-99", "💇 Olaplex", False),
        ("https://www.amazon.sa/s?k=ghd+hair&rh=p_8%3A30-99", "💇 ghd", False),
        ("https://www.amazon.sa/s?k=dyson+hair&rh=p_8%3A30-99", "💇 Dyson Hair", False),
    ]
    
    # أطفال
    baby_kids = [
        ("https://www.amazon.sa/s?k=pampers+premium&rh=p_8%3A30-99", "👶 Pampers Premium", False),
        ("https://www.amazon.sa/s?k=pampers+baby+dry&rh=p_8%3A30-99", "👶 Baby Dry", False),
        ("https://www.amazon.sa/s?k=huggies+little&rh=p_8%3A30-99", "👶 Huggies", False),
        ("https://www.amazon.sa/s?k=johnson+baby+shampoo&rh=p_8%3A30-99", "👶 JJ Shampoo", False),
        ("https://www.amazon.sa/s?k=johnson+baby+lotion&rh=p_8%3A30-99", "👶 JJ Lotion", False),
        ("https://www.amazon.sa/s?k=mustela+baby&rh=p_8%3A30-99", "👶 Mustela", False),
        ("https://www.amazon.sa/s?k=aveeno+baby&rh=p_8%3A30-99", "👶 Aveeno Baby", False),
        ("https://www.amazon.sa/s?k=cetaphil+baby&rh=p_8%3A30-99", "👶 Cetaphil Baby", False),
        ("https://www.amazon.sa/s?k=sebamed+baby&rh=p_8%3A30-99", "👶 Sebamed", False),
        ("https://www.amazon.sa/s?k=bioderma+baby&rh=p_8%3A30-99", "👶 Bioderma Baby", False),
        ("https://www.amazon.sa/s?k=lego+star+wars&rh=p_8%3A30-99", "🧱 LEGO SW", False),
        ("https://www.amazon.sa/s?k=lego+technic&rh=p_8%3A30-99", "🧱 LEGO Tech", False),
        ("https://www.amazon.sa/s?k=lego+city&rh=p_8%3A30-99", "🧱 LEGO City", False),
        ("https://www.amazon.sa/s?k=lego+friends&rh=p_8%3A30-99", "🧱 LEGO Friends", False),
        ("https://www.amazon.sa/s?k=lego+marvel&rh=p_8%3A30-99", "🧱 LEGO Marvel", False),
        ("https://www.amazon.sa/s?k=lego+harry+potter&rh=p_8%3A30-99", "🧱 LEGO HP", False),
        ("https://www.amazon.sa/s?k=barbie+doll&rh=p_8%3A30-99", "👸 Barbie", False),
        ("https://www.amazon.sa/s?k=barbie+dreamhouse&rh=p_8%3A30-99", "👸 DreamHouse", False),
        ("https://www.amazon.sa/s?k=hot+wheels+track&rh=p_8%3A30-99", "🚗 HW Track", False),
        ("https://www.amazon.sa/s?k=hot+wheels+premium&rh=p_8%3A30-99", "🚗 HW Premium", False),
        ("https://www.amazon.sa/s?k=fisher+price+baby&rh=p_8%3A30-99", "🎠 FP Baby", False),
        ("https://www.amazon.sa/s?k=little+tikes+car&rh=p_8%3A30-99", "🎪 LT Car", False),
        ("https://www.amazon.sa/s?k=vtech+baby&rh=p_8%3A30-99", "🔤 VTech", False),
        ("https://www.amazon.sa/s?k=leapfrog+learning&rh=p_8%3A30-99", "🐸 LeapFrog", False),
        ("https://www.amazon.sa/s?k=playmobil&rh=p_8%3A30-99", "🎭 Playmobil", False),
        ("https://www.amazon.sa/s?k=hasbro+games&rh=p_8%3A30-99", "🎲 Hasbro", False),
        ("https://www.amazon.sa/s?k=mattel+games&rh=p_8%3A30-99", "🎲 Mattel", False),
    ]
    
    # رياضة
    fitness = [
        ("https://www.amazon.sa/s?k=nordictrack&rh=p_8%3A30-99", "🏋️ NordicTrack", False),
        ("https://www.amazon.sa/s?k=proform&rh=p_8%3A30-99", "🏋️ ProForm", False),
        ("https://www.amazon.sa/s?k=bowflex&rh=p_8%3A30-99", "🏋️ Bowflex", False),
        ("https://www.amazon.sa/s?k=peloton&rh=p_8%3A30-99", "🏋️ Peloton", False),
        ("https://www.amazon.sa/s?k=concept2&rh=p_8%3A30-99", "🏋️ Concept2", False),
        ("https://www.amazon.sa/s?k=trx+suspension&rh=p_8%3A30-99", "🏋️ TRX", False),
        ("https://www.amazon.sa/s?k=resistance+bands+set&rh=p_8%3A30-99", "🏋️ Bands", False),
        ("https://www.amazon.sa/s?k=kettlebell+set&rh=p_8%3A30-99", "🏋️ Kettlebells", False),
        ("https://www.amazon.sa/s?k=dumbbell+set&rh=p_8%3A30-99", "🏋️ Dumbbells", False),
        ("https://www.amazon.sa/s?k=barbell+set&rh=p_8%3A30-99", "🏋️ Barbells", False),
        ("https://www.amazon.sa/s?k=weight+plate&rh=p_8%3A30-99", "🏋️ Plates", False),
        ("https://www.amazon.sa/s?k=bench+press&rh=p_8%3A30-99", "🏋️ Bench", False),
        ("https://www.amazon.sa/s?k=power+rack&rh=p_8%3A30-99", "🏋️ Power Rack", False),
        ("https://www.amazon.sa/s?k=yoga+mat+lululemon&rh=p_8%3A30-99", "🧘 Lululemon", False),
        ("https://www.amazon.sa/s?k=manduka+yoga&rh=p_8%3A30-99", "🧘 Manduka", False),
        ("https://www.amazon.sa/s?k=gaiam+yoga&rh=p_8%3A30-99", "🧘 Gaiam", False),
        ("https://www.amazon.sa/s?k=foam+roller&rh=p_8%3A30-99", "🧘 Foam Roller", False),
        ("https://www.amazon.sa/s?k=massage+gun&rh=p_8%3A30-99", "🧘 Massage Gun", False),
        ("https://www.amazon.sa/s?k=theragun&rh=p_8%3A30-99", "🧘 Theragun", False),
        ("https://www.amazon.sa/s?k=hyperice&rh=p_8%3A30-99", "🧘 Hyperice", False),
        ("https://www.amazon.sa/s?k=optimum+nutrition+whey&rh=p_8%3A30-99", "💪 ON Whey", False),
        ("https://www.amazon.sa/s?k=optimum+nutrition+gold&rh=p_8%3A30-99", "💪 ON Gold", False),
        ("https://www.amazon.sa/s?k=muscletech+nitro&rh=p_8%3A30-99", "💪 Nitro", False),
        ("https://www.amazon.sa/s?k=muscletech+mass&rh=p_8%3A30-99", "💪 Mass Tech", False),
        ("https://www.amazon.sa/s?k=dymatize+iso&rh=p_8%3A30-99", "💪 ISO100", False),
        ("https://www.amazon.sa/s?k=bsn+syntha&rh=p_8%3A30-99", "💪 Syntha-6", False),
        ("https://www.amazon.sa/s?k=cellucor+c4&rh=p_8%3A30-99", "💪 C4", False),
        ("https://www.amazon.sa/s?k=bpi+sports+whey&rh=p_8%3A30-99", "💪 BPI Whey", False),
        ("https://www.amazon.sa/s?k=rule+one&rh=p_8%3A30-99", "💪 R1", False),
        ("https://www.amazon.sa/s?k=isopure&rh=p_8%3A30-99", "💪 Isopure", False),
        ("https://www.amazon.sa/s?k=quest+nutrition&rh=p_8%3A30-99", "💪 Quest", False),
    ]
    
    # منزل ومطبخ
    home_kitchen = [
        ("https://www.amazon.sa/s?k=philips+airfryer+xl&rh=p_8%3A30-99", "🏠 AirFryer XL", False),
        ("https://www.amazon.sa/s?k=philips+airfryer+xxl&rh=p_8%3A30-99", "🏠 AirFryer XXL", False),
        ("https://www.amazon.sa/s?k=ninja+foodi&rh=p_8%3A30-99", "🥤 Foodi", False),
        ("https://www.amazon.sa/s?k=ninja+blender+professional&rh=p_8%3A30-99", "🥤 Pro Blender", False),
        ("https://www.amazon.sa/s?k=ninja+multicooker&rh=p_8%3A30-99", "🥤 Multicooker", False),
        ("https://www.amazon.sa/s?k=nespresso+vertuo&rh=p_8%3A30-99", "☕ Vertuo", False),
        ("https://www.amazon.sa/s?k=nespresso+original&rh=p_8%3A30-99", "☕ Original", False),
        ("https://www.amazon.sa/s?k=delonghi+la+specialista&rh=p_8%3A30-99", "☕ Specialista", False),
        ("https://www.amazon.sa/s?k=delonghi+dedica&rh=p_8%3A30-99", "☕ Dedica", False),
        ("https://www.amazon.sa/s?k=delonghi+magnifica&rh=p_8%3A30-99", "☕ Magnifica", False),
        ("https://www.amazon.sa/s?k=breville+barista&rh=p_8%3A30-99", "🏠 Barista", False),
        ("https://www.amazon.sa/s?k=breville+smart+oven&rh=p_8%3A30-99", "🏠 Smart Oven", False),
        ("https://www.amazon.sa/s?k=kenwood+chef&rh=p_8%3A30-99", "🏠 Chef", False),
        ("https://www.amazon.sa/s?k=kenwood+kflex&rh=p_8%3A30-99", "🏠 kFlex", False),
        ("https://www.amazon.sa/s?k=kitchenaid+artisan&rh=p_8%3A30-99", "🏠 Artisan", False),
        ("https://www.amazon.sa/s?k=kitchenaid+stand+mixer&rh=p_8%3A30-99", "🏠 Stand Mixer", False),
        ("https://www.amazon.sa/s?k=cuisinart+food+processor&rh=p_8%3A30-99", "🏠 Processor", False),
        ("https://www.amazon.sa/s?k=cuisinart+air+fryer&rh=p_8%3A30-99", "🏠 Cuisinart AF", False),
        ("https://www.amazon.sa/s?k=instant+pot&rh=p_8%3A30-99", "🏠 Instant Pot", False),
        ("https://www.amazon.sa/s?k=cosori+air+fryer&rh=p_8%3A30-99", "🏠 Cosori", False),
        ("https://www.amazon.sa/s?k=tower+air+fryer&rh=p_8%3A30-99", "🏠 Tower", False),
        ("https://www.amazon.sa/s?k=tupperware+set&rh=p_8%3A30-99", "🥣 Tupperware Set", False),
        ("https://www.amazon.sa/s?k=pyrex+bowls&rh=p_8%3A30-99", "🍽️ Pyrex Bowls", False),
        ("https://www.amazon.sa/s?k=pyrex+baking&rh=p_8%3A30-99", "🍽️ Pyrex Baking", False),
        ("https://www.amazon.sa/s?k=corelle+dinnerware&rh=p_8%3A30-99", "🍽️ Corelle", False),
        ("https://www.amazon.sa/s?k=le+creuset&rh=p_8%3A30-99", "🍽️ Le Creuset", False),
        ("https://www.amazon.sa/s?k=staub&rh=p_8%3A30-99", "🍽️ Staub", False),
        ("https://www.amazon.sa/s?k=lodge+cast+iron&rh=p_8%3A30-99", "🍽️ Lodge", False),
        ("https://www.amazon.sa/s?k=all+clad&rh=p_8%3A30-99", "🍽️ All-Clad", False),
        ("https://www.amazon.sa/s?k=calphalon&rh=p_8%3A30-99", "🍽️ Calphalon", False),
        ("https://www.amazon.sa/s?k=t-fal&rh=p_8%3A30-99", "🍽️ T-fal", False),
        ("https://www.amazon.sa/s?k=dyson+v15&rh=p_8%3A30-99", "🏠 V15", False),
        ("https://www.amazon.sa/s?k=dyson+v12&rh=p_8%3A30-99", "🏠 V12", False),
        ("https://www.amazon.sa/s?k=dyson+outsize&rh=p_8%3A30-99", "🏠 Outsize", False),
        ("https://www.amazon.sa/s?k=irobot+roomba&rh=p_8%3A30-99", "🏠 Roomba", False),
        ("https://www.amazon.sa/s?k=irobot+braava&rh=p_8%3A30-99", "🏠 Braava", False),
        ("https://www.amazon.sa/s?k=ecovacs+deebot&rh=p_8%3A30-99", "🏠 Deebot", False),
        ("https://www.amazon.sa/s?k=roborock&rh=p_8%3A30-99", "🏠 Roborock", False),
        ("https://www.amazon.sa/s?k=shark+vacuum&rh=p_8%3A30-99", "🏠 Shark", False),
    ]
    
    # أدوات
    tools = [
        ("https://www.amazon.sa/s?k=bosch+professional&rh=p_8%3A30-99", "🔧 Bosch Pro", False),
        ("https://www.amazon.sa/s?k=bosch+impact&rh=p_8%3A30-99", "🔧 Bosch Impact", False),
        ("https://www.amazon.sa/s?k=makita+18v&rh=p_8%3A30-99", "🔧 Makita 18V", False),
        ("https://www.amazon.sa/s?k=makita+brushless&rh=p_8%3A30-99", "🔧 Makita BL", False),
        ("https://www.amazon.sa/s?k=dewalt+20v&rh=p_8%3A30-99", "🔧 DeWalt 20V", False),
        ("https://www.amazon.sa/s?k=dewalt+atomic&rh=p_8%3A30-99", "🔧 DeWalt Atomic", False),
        ("https://www.amazon.sa/s?k=dewalt+flexvolt&rh=p_8%3A30-99", "🔧 FlexVolt", False),
        ("https://www.amazon.sa/s?k=black+decker+20v&rh=p_8%3A30-99", "🔧 B&D 20V", False),
        ("https://www.amazon.sa/s?k=stanley+fatmax&rh=p_8%3A30-99", "🔧 FatMax", False),
        ("https://www.amazon.sa/s?k=craftsman+v20&rh=p_8%3A30-99", "🔧 Craftsman", False),
        ("https://www.amazon.sa/s?k=ryobi+18v&rh=p_8%3A30-99", "🔧 Ryobi", False),
        ("https://www.amazon.sa/s?k=milwaukee+m18&rh=p_8%3A30-99", "🔧 Milwaukee", False),
        ("https://www.amazon.sa/s?k=worx+20v&rh=p_8%3A30-99", "🔧 Worx", False),
        ("https://www.amazon.sa/s?k=hitachi+tools&rh=p_8%3A30-99", "🔧 Hitachi", False),
        ("https://www.amazon.sa/s?k=metabo&rh=p_8%3A30-99", "🔧 Metabo", False),
        ("https://www.amazon.sa/s?k=hilti&rh=p_8%3A30-99", "🔧 Hilti", False),
    ]
    
    # سيارات
    automotive = [
        ("https://www.amazon.sa/s?k=michelin+pilot&rh=p_8%3A30-99", "🚗 Pilot", False),
        ("https://www.amazon.sa/s?k=michelin+primacy&rh=p_8%3A30-99", "🚗 Primacy", False),
        ("https://www.amazon.sa/s?k=bridgestone+potenza&rh=p_8%3A30-99", "🚗 Potenza", False),
        ("https://www.amazon.sa/s?k=bridgestone+turanza&rh=p_8%3A30-99", "🚗 Turanza", False),
        ("https://www.amazon.sa/s?k=goodyear+eagle&rh=p_8%3A30-99", "🚗 Eagle", False),
        ("https://www.amazon.sa/s?k=goodyear+assurance&rh=p_8%3A30-99", "🚗 Assurance", False),
        ("https://www.amazon.sa/s?k=pirelli+p+zero&rh=p_8%3A30-99", "🚗 P Zero", False),
        ("https://www.amazon.sa/s?k=continental+premium&rh=p_8%3A30-99", "🚗 ContiPremium", False),
        ("https://www.amazon.sa/s?k=dunlop+sport&rh=p_8%3A30-99", "🚗 Dunlop", False),
        ("https://www.amazon.sa/s?k=yokohama+advan&rh=p_8%3A30-99", "🚗 Advan", False),
        ("https://www.amazon.sa/s?k=hankook+ventus&rh=p_8%3A30-99", "🚗 Ventus", False),
        ("https://www.amazon.sa/s?k=nexen+nfera&rh=p_8%3A30-99", "🚗 Nfera", False),
        ("https://www.amazon.sa/s?k=bosch+car+battery&rh=p_8%3A30-99", "🚗 Battery", False),
        ("https://www.amazon.sa/s?k=varta+battery&rh=p_8%3A30-99", "🚗 Varta", False),
        ("https://www.amazon.sa/s?k=shell+helix&rh=p_8%3A30-99", "🚗 Helix", False),
        ("https://www.amazon.sa/s?k=mobil+1+extended&rh=p_8%3A30-99", "🚗 Mobil 1 Ext", False),
        ("https://www.amazon.sa/s?k=castrol+edge&rh=p_8%3A30-99", "🚗 Edge", False),
        ("https://www.amazon.sa/s?k=liquimoly&rh=p_8%3A30-99", "🚗 Liqui Moly", False),
        ("https://www.amazon.sa/s?k=motul&rh=p_8%3A30-99", "🚗 Motul", False),
        ("https://www.amazon.sa/s?k=3m+car+care&rh=p_8%3A30-99", "🚗 3M Car", False),
        ("https://www.amazon.sa/s?k=meguiars&rh=p_8%3A30-99", "🚗 Meguiar's", False),
        ("https://www.amazon.sa/s?k=chemical+guys&rh=p_8%3A30-99", "🚗 Chemical Guys", False),
        ("https://www.amazon.sa/s?k=turtle+wax&rh=p_8%3A30-99", "🚗 Turtle Wax", False),
    ]
    
    # سعودي خاص
    saudi_special = [
        ("https://www.amazon.sa/s?k=ajwa+dates&rh=p_8%3A30-99", "🌴 Ajwa", False),
        ("https://www.amazon.sa/s?k=sukkari+dates&rh=p_8%3A30-99", "🌴 Sukkari", False),
        ("https://www.amazon.sa/s?k=khudri+dates&rh=p_8%3A30-99", "🌴 Khudri", False),
        ("https://www.amazon.sa/s?k=medjool+dates&rh=p_8%3A30-99", "🌴 Medjool", False),
        ("https://www.amazon.sa/s?k=date+maamoul&rh=p_8%3A30-99", "🌴 Maamoul", False),
        ("https://www.amazon.sa/s?k=oud+perfume&rh=p_8%3A30-99", "🌿 Oud Perfume", False),
        ("https://www.amazon.sa/s?k=oud+wood&rh=p_8%3A30-99", "🌿 Oud Wood", False),
        ("https://www.amazon.sa/s?k=bakhoor+oud&rh=p_8%3A30-99", "🌿 Bakhoor", False),
        ("https://www.amazon.sa/s?k=incense+burner&rh=p_8%3A30-99", "🌿 Mabkhara", False),
        ("https://www.amazon.sa/s?k=musk+tahara&rh=p_8%3A30-99", "🌿 Musk", False),
        ("https://www.amazon.sa/s?k=prayer+mat+premium&rh=p_8%3A30-99", "🕌 Premium Mat", False),
        ("https://www.amazon.sa/s?k=prayer+beads&rh=p_8%3A30-99", "🕌 Misbaha", False),
        ("https://www.amazon.sa/s?k=quran+stand&rh=p_8%3A30-99", "🕌 Stand", False),
        ("https://www.amazon.sa/s?k=islamic+gifts&rh=p_8%3A30-99", "🕌 Gifts", False),
        ("https://www.amazon.sa/s?k=thobe+white&rh=p_8%3A30-99", "👘 Thobe White", False),
        ("https://www.amazon.sa/s?k=thobe+bisht&rh=p_8%3A30-99", "👘 Bisht", False),
        ("https://www.amazon.sa/s?k=shmagh&rh=p_8%3A30-99", "👘 Shmagh", False),
        ("https://www.amazon.sa/s?k=ghutra&rh=p_8%3A30-99", "👘 Ghutra", False),
        ("https://www.amazon.sa/s?k=abaya+black&rh=p_8%3A30-99", "🧕 Abaya Black", False),
        ("https://www.amazon.sa/s?k=abaya+colored&rh=p_8%3A30-99", "🧕 Abaya Color", False),
        ("https://www.amazon.sa/s?k=shayla&rh=p_8%3A30-99", "🧕 Shayla", False),
        ("https://www.amazon.sa/s?k=niqab&rh=p_8%3A30-99", "🧕 Niqab", False),
        ("https://www.amazon.sa/s?k=ramadan+lantern&rh=p_8%3A30-99", "🌙 Fanous", False),
        ("https://www.amazon.sa/s?k=ramadan+decorations&rh=p_8%3A30-99", "🌙 Decor", False),
        ("https://www.amazon.sa/s?k=eid+gifts&rh=p_8%3A30-99", "🎉 Eid Gifts", False),
        ("https://www.amazon.sa/s?k=eid+clothes&rh=p_8%3A30-99", "🎉 Eid Clothes", False),
        ("https://www.amazon.sa/s?k=hajj+ihram&rh=p_8%3A30-99", "🕋 Ihram", False),
        ("https://www.amazon.sa/s?k=hajj+bag&rh=p_8%3A30-99", "🕋 Hajj Bag", False),
        ("https://www.amazon.sa/s?k=umrah+kit&rh=p_8%3A30-99", "🕋 Umrah Kit", False),
        ("https://www.amazon.sa/s?k=tasbih+electronic&rh=p_8%3A30-99", "🕋 E-Tasbih", False),
        ("https://www.amazon.sa/s?k=qibla+compass&rh=p_8%3A30-99", "🕋 Compass", False),
        ("https://www.amazon.sa/s?k=prayer+time+clock&rh=p_8%3A30-99", "🕋 Azan Clock", False),
    ]
    
    # فاخر
    luxury = [
        ("https://www.amazon.sa/s?k=louis+vuitton+bag&rh=p_8%3A30-99", "👜 LV Bag", False),
        ("https://www.amazon.sa/s?k=louis+vuitton+wallet&rh=p_8%3A30-99", "👜 LV Wallet", False),
        ("https://www.amazon.sa/s?k=hermes+birkin&rh=p_8%3A30-99", "👜 Birkin", False),
        ("https://www.amazon.sa/s?k=hermes+kelly&rh=p_8%3A30-99", "👜 Kelly", False),
        ("https://www.amazon.sa/s?k=hermes+scarf&rh=p_8%3A30-99", "👜 H Scarf", False),
        ("https://www.amazon.sa/s?k=coach+tabby&rh=p_8%3A30-99", "👜 Tabby", False),
        ("https://www.amazon.sa/s?k=coach+willis&rh=p_8%3A30-99", "👜 Willis", False),
        ("https://www.amazon.sa/s?k=kate+spade+spade&rh=p_8%3A30-99", "👜 KS Spade", False),
        ("https://www.amazon.sa/s?k=burberry+trench&rh=p_8%3A30-99", "👜 Trench", False),
        ("https://www.amazon.sa/s?k=burberry+check&rh=p_8%3A30-99", "👜 Check", False),
        ("https://www.amazon.sa/s?k=longchamp+le+pliage&rh=p_8%3A30-99", "👜 Le Pliage", False),
        ("https://www.amazon.sa/s?k=longchamp+roseau&rh=p_8%3A30-99", "👜 Roseau", False),
        ("https://www.amazon.sa/s?k=tumi+alpha&rh=p_8%3A30-99", "🧳 Alpha", False),
        ("https://www.amazon.sa/s?k=tumi+bravo&rh=p_8%3A30-99", "🧳 Bravo", False),
        ("https://www.amazon.sa/s?k=samsonite+proxis&rh=p_8%3A30-99", "🧳 Proxis", False),
        ("https://www.amazon.sa/s?k=samsonite+c-lite&rh=p_8%3A30-99", "🧳 C-Lite", False),
        ("https://www.amazon.sa/s?k=rimowa+essential&rh=p_8%3A30-99", "🧳 Essential", False),
        ("https://www.amazon.sa/s?k=rimowa+classic&rh=p_8%3A30-99", "🧳 Classic", False),
        ("https://www.amazon.sa/s?k=montblanc+pen&rh=p_8%3A30-99", "✒️ Montblanc", False),
        ("https://www.amazon.sa/s?k=montblanc+wallet&rh=p_8%3A30-99", "✒️ MB Wallet", False),
        ("https://www.amazon.sa/s?k=cross+pen&rh=p_8%3A30-99", "✒️ Cross", False),
        ("https://www.amazon.sa/s?k=parker+pen&rh=p_8%3A30-99", "✒️ Parker", False),
        ("https://www.amazon.sa/s?k=waterman+pen&rh=p_8%3A30-99", "✒️ Waterman", False),
    ]
    
    # تجمع كل الأقسام
    all_categories = (
        best_sellers + official_deals + warehouse + prime_lightning + 
        coupons + hidden + apple + samsung + headphones + laptops + 
        gaming + cameras + smartwatches + traditional_watches + 
        luxury_perfumes + sneakers + men_clothing + bags + jewelry + 
        sunglasses + makeup + skincare + haircare + baby_kids + 
        fitness + home_kitchen + tools + automotive + saudi_special + luxury
    )
    
    return all_categories

def search_all_deals(chat_id, status_message_id):
    global daily_deals_count, sent_asins_today
    
    all_deals = []
    session = create_session()
    
    # الحصول على الأقسام مع التدوير اليومي
    all_categories = get_all_categories()
    
    # ترتيب عشوائي يومي مختلف
    day_seed = int(datetime.now().strftime('%Y%m%d'))
    random.seed(day_seed)
    shuffled_categories = all_categories.copy()
    random.shuffle(shuffled_categories)
    
    # اختيار 150 قسم يومياً (تدوير)
    daily_categories = shuffled_categories[:150]
    
    total = len(daily_categories)
    logger.info(f"📅 Daily rotation: {total} categories selected")
    
    for idx, (url, cat_name, is_best_seller) in enumerate(daily_categories, 1):
        # توقف لو وصلنا 100 منتج
        if daily_deals_count >= DAILY_TARGET:
            logger.info(f"✅ Reached daily target: {DAILY_TARGET}")
            break
            
        try:
            if idx % 10 == 0:
                progress = f"⏳ جاري البحث... ({idx}/{total})\n📍 {cat_name}\n📦 اليوم: {daily_deals_count}/{DAILY_TARGET}"
                try:
                    updater.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=status_message_id,
                        text=progress
                    )
                except:
                    pass
            
            logger.info(f"🔍 [{cat_name}] - Daily: {daily_deals_count}")
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
            
            logger.info(f"   Found {len(items)} items")
            
            for item in items:
                # توقف لو وصلنا الهدف
                if daily_deals_count >= DAILY_TARGET:
                    break
                    
                try:
                    deal = parse_item(item, cat_name, is_best_seller)
                    if deal and is_unique_deal(deal):
                        all_deals.append(deal)
                        # تحديث العداد
                        asin = extract_asin(deal.get('link', ''))
                        if asin:
                            sent_asins_today.add(asin)
                        daily_deals_count += 1
                except:
                    continue
            
            time.sleep(random.uniform(0.5, 1.5))
            
        except Exception as e:
            logger.error(f"Error in {cat_name}: {e}")
    
    logger.info(f"✅ Total found: {len(all_deals)}, Daily count: {daily_deals_count}")
    save_database()
    return all_deals

def is_unique_deal(deal):
    """التحقق من أن المنتج فريد ولم يتم إرساله اليوم"""
    asin = extract_asin(deal.get('link', ''))
    if asin and asin in sent_asins_today:
        return False
    
    pid = deal['id']
    if pid in sent_products:
        return False
    
    # التحقق من عدم التشابه
    if is_similar_product(deal['title']):
        return False
    
    return True

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
        
        # تخفيض الحد للعروض المخفية
        min_discount = 40 if 'Warehouse' in deal['category'] or 'Outlet' in deal['category'] or 'Clearance' in deal['category'] else (50 if is_bs else 55)
        
        has_discount = disc >= min_discount
        has_rating = rating >= 2.5
        is_reasonable = 0.5 < deal['price'] < 15000
        
        if has_discount and has_rating and is_reasonable:
            if pid in seen_in_run:
                continue
            
            seen_in_run.add(pid)
            
            # تحديد نوع العرض
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
    
    # ترتيب ذكي
    filtered.sort(key=lambda x: (
        0 if x['type'] == '🔥 GLITCH' else 1,
        0 if x['type'] == '🏭 WAREHOUSE' else 1,
        0 if x['type'] == '⚡ LIGHTNING' else 1,
        0 if x['type'] == '👑 PRIME' else 1,
        0 if x.get('is_best_seller') else 1,
        -x['discount']
    ))
    
    # أخذ أول 100 فقط
    return filtered[:DAILY_TARGET]

def send_deals(deals, chat_id, status_message_id):
    global sent_products, sent_hashes, is_scanning
    
    try:
        try:
            updater.bot.delete_message(chat_id, status_message_id)
        except:
            pass
        
        if not deals:
            msg = "❌ *لا توجد عروض جديدة اليوم*\n\nجرب بكرة الصبح!"
            updater.bot.send_message(chat_id=chat_id, text=msg, parse_mode='Markdown')
            return
        
        # إحصائيات
        type_counts = {}
        for d in deals:
            t = d['type']
            type_counts[t] = type_counts.get(t, 0) + 1
        
        summary_lines = [f"🎯 *{len(deals)} صفقة يومية فريدة!*"]
        for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
            summary_lines.append(f"{t}: {c}")
        
        summary = "\n".join(summary_lines)
        updater.bot.send_message(chat_id=chat_id, text=summary, parse_mode='Markdown')
        
        # إرسال المنتجات
        for i, d in enumerate(deals, 1):
            savings = f"💵 توفير: {d['savings']:.2f} ريال\n" if d['savings'] > 0 else ""
            old = f"🏷️ قبل: {d['old_price']:.2f} ريال\n" if d['old_price'] > 0 else ""
            rev = f"📝 {d['reviews']:,} مراجعة\n" if d['reviews'] > 0 else ""
            
            msg = f"""
{d['type']} *#{i}/{len(deals)}*

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
        logger.info(f"✅ Sent {len(deals)} deals. Total history: {len(sent_products)}")
        
    finally:
        is_scanning = False

def start_cmd(update: Update, context: CallbackContext):
    today_count = len(sent_asins_today)
    remaining = DAILY_TARGET - today_count
    
    update.message.reply_text(f"""
👋 *أهلاً بيك في Amazon Deals Bot!*

🎯 *الهدف اليومي: 100 صفقة فريدة*
📦 *تم اليوم: {today_count}*
⏳ *المتبقي: {remaining}*

✨ مميزات البوت:
• 300+ قسم يتم تدويرها يومياً
• منتجات لا تتكرر أبداً
• عروض Warehouse المخفية 🏭
• Outlet & Clearance 🎁
• Lightning Deals ⚡
• Prime Exclusives 👑

🔥 خصومات من 40% لـ 99%!

اكتب *Hi* للحصول على عروض اليوم!
    """, parse_mode='Markdown')

def hi_cmd(update: Update, context: CallbackContext):
    global is_scanning
    
    chat_id = update.effective_chat.id
    
    # التحقق من الهدف اليومي
    if daily_deals_count >= DAILY_TARGET:
        update.message.reply_text(f"""
✅ *اكتمل هدف اليوم!*

📦 تم إرسال {DAILY_TARGET} صفقة فريدة
🔄 عد بكرة الصبح لعروض جديدة

⏰ {datetime.now().strftime('%H:%M')} توقيت السعودية
        """, parse_mode='Markdown')
        return
    
    if is_scanning:
        update.message.reply_text("⏳ أنا ببحث دلوقتي... استنى شوية!")
        return
    
    is_scanning = True
    
    status_msg = update.message.reply_text(
        f"🔍 *بدأت البحث اليومي...*\n📦 الهدف: {DAILY_TARGET}\n⏱️ 5-8 دقائق", 
        parse_mode='Markdown'
    )
    
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
    today = datetime.now().strftime('%Y-%m-%d')
    update.message.reply_text(f"""
📊 *حالة البوت:*

📅 اليوم: {today}
📦 تم اليوم: {len(sent_asins_today)}/{DAILY_TARGET}
📚 إجمالي المنتجات: {len(sent_products)}
🔍 البحوث الفريدة: {len(sent_hashes)}
📁 الأقسام المتاحة: 300+

✅ البوت يعمل بكفاءة!
    """, parse_mode='Markdown')

def clear_cmd(update: Update, context: CallbackContext):
    global sent_products, sent_hashes, sent_asins_today, daily_deals_count
    
    sent_products.clear()
    sent_hashes.clear()
    sent_asins_today.clear()
    daily_deals_count = 0
    save_database()
    
    update.message.reply_text("""
🗑️ *تم مسح كل البيانات!*

الآن البوت هيبدأ من جديد.
    """, parse_mode='Markdown')

def unknown(update: Update, context: CallbackContext):
    update.message.reply_text("""
🤔 *مش فاهم!*

الأوامر المتاحة:
• *Hi* - عروض اليوم
• /start - معلومات
• /status - الحالة
• /clear - مسح البيانات
    """, parse_mode='Markdown')

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        response = json.dumps({
            "status": "ok",
            "daily_target": DAILY_TARGET,
            "today_count": len(sent_asins_today),
            "total_products": len(sent_products),
            "categories": 300,
            "timestamp": datetime.now().isoformat()
        })
        self.wfile.write(response.encode())
    
    def log_message(self, format, *args):
        pass

def run_health_server():
    server = HTTPServer(('0.0.0.0', PORT), HealthHandler)
    logger.info(f"🌐 Health server on port {PORT}")
    server.serve_forever()

def main():
    global updater
    
    load_database()
    logger.info(f"🚀 Starting | Today: {len(sent_asins_today)}/{DAILY_TARGET} | Total: {len(sent_products)}")
    
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
