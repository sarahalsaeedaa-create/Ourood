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
    
    # ✅ 200+ قسم شامل
    categories = [
        # 🏆 Best Sellers الأساسية
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
        ("https://www.amazon.sa/gp/warehouse-deals/beauty", "🏭 Warehouse Beauty", False),
        ("https://www.amazon.sa/gp/warehouse-deals/sports", "🏭 Warehouse Sports", False),
        ("https://www.amazon.sa/gp/warehouse-deals/tools", "🏭 Warehouse Tools", False),
        
        # 🎟️ عروض مخفية - Coupons
        ("https://www.amazon.sa/gp/coupons", "🎟️ Coupons", False),
        ("https://www.amazon.sa/gp/coupons/electronics", "🎟️ Electronics Coupons", False),
        ("https://www.amazon.sa/gp/coupons/fashion", "🎟️ Fashion Coupons", False),
        ("https://www.amazon.sa/gp/coupons/home", "🎟️ Home Coupons", False),
        ("https://www.amazon.sa/gp/coupons/beauty", "🎟️ Beauty Coupons", False),
        ("https://www.amazon.sa/gp/coupons/grocery", "🎟️ Grocery Coupons", False),
        ("https://www.amazon.sa/gp/coupons/baby", "🎟️ Baby Coupons", False),
        
        # 👑 Prime & Lightning
        ("https://www.amazon.sa/gp/prime/pipeline/prime_exclusives", "👑 Prime Exclusives", False),
        ("https://www.amazon.sa/gp/prime/pipeline/lightning_deals", "⚡ Lightning Deals", False),
        
        # 📅 Today's Deals
        ("https://www.amazon.sa/gp/todays-deals", "📅 Today Deals", False),
        ("https://www.amazon.sa/gp/todays-deals/electronics", "📅 Today Electronics", False),
        ("https://www.amazon.sa/gp/todays-deals/fashion", "📅 Today Fashion", False),
        ("https://www.amazon.sa/gp/todays-deals/home", "📅 Today Home", False),
        ("https://www.amazon.sa/gp/todays-deals/beauty", "📅 Today Beauty", False),
        
        # 🎁 Outlet
        ("https://www.amazon.sa/outlet", "🎁 Outlet", False),
        ("https://www.amazon.sa/outlet/electronics", "🎁 Outlet Electronics", False),
        ("https://www.amazon.sa/outlet/home", "🎁 Outlet Home", False),
        ("https://www.amazon.sa/outlet/fashion", "🎁 Outlet Fashion", False),
        ("https://www.amazon.sa/outlet/beauty", "🎁 Outlet Beauty", False),
        
        # 🔥 عروض سرية
        ("https://www.amazon.sa/s?k=clearance&rh=p_8%3A50-99", "🔥 Clearance", False),
        ("https://www.amazon.sa/s?k=last+chance&rh=p_8%3A50-99", "🔥 Last Chance", False),
        ("https://www.amazon.sa/s?k=final+sale&rh=p_8%3A50-99", "🔥 Final Sale", False),
        ("https://www.amazon.sa/s?k=limited+time&rh=p_8%3A50-99", "⏰ Limited Time", False),
        ("https://www.amazon.sa/s?k=flash+sale&rh=p_8%3A50-99", "⚡ Flash Sale", False),
        ("https://www.amazon.sa/s?k=super+sale&rh=p_8%3A50-99", "💥 Super Sale", False),
        ("https://www.amazon.sa/s?k=mega+deal&rh=p_8%3A50-99", "🎯 Mega Deal", False),
        ("https://www.amazon.sa/s?k=big+sale&rh=p_8%3A50-99", "🎪 Big Sale", False),
        
        # 🍎 Apple كامل
        ("https://www.amazon.sa/s?k=iphone&rh=p_8%3A30-99", "🍎 iPhone", False),
        ("https://www.amazon.sa/s?k=ipad&rh=p_8%3A30-99", "🍎 iPad", False),
        ("https://www.amazon.sa/s?k=macbook&rh=p_8%3A30-99", "🍎 MacBook", False),
        ("https://www.amazon.sa/s?k=airpods&rh=p_8%3A30-99", "🍎 AirPods", False),
        ("https://www.amazon.sa/s?k=apple+watch&rh=p_8%3A30-99", "🍎 Apple Watch", False),
        ("https://www.amazon.sa/s?k=apple+tv&rh=p_8%3A30-99", "🍎 Apple TV", False),
        ("https://www.amazon.sa/s?k=airtag&rh=p_8%3A30-99", "🍎 AirTag", False),
        ("https://www.amazon.sa/s?k=homepod&rh=p_8%3A30-99", "🍎 HomePod", False),
        
        # 📱 Samsung كامل
        ("https://www.amazon.sa/s?k=samsung+galaxy&rh=p_8%3A30-99", "📱 Galaxy Phone", False),
        ("https://www.amazon.sa/s?k=samsung+tablet&rh=p_8%3A30-99", "📱 Galaxy Tab", False),
        ("https://www.amazon.sa/s?k=samsung+watch&rh=p_8%3A30-99", "📱 Galaxy Watch", False),
        ("https://www.amazon.sa/s?k=samsung+buds&rh=p_8%3A30-99", "📱 Galaxy Buds", False),
        ("https://www.amazon.sa/s?k=samsung+tv&rh=p_8%3A30-99", "📱 Samsung TV", False),
        ("https://www.amazon.sa/s?k=samsung+monitor&rh=p_8%3A30-99", "📱 Samsung Monitor", False),
        
        # 🎧 سماعات
        ("https://www.amazon.sa/s?k=sony+headphones&rh=p_8%3A30-99", "🎧 Sony Headphones", False),
        ("https://www.amazon.sa/s?k=bose+headphones&rh=p_8%3A30-99", "🎧 Bose Headphones", False),
        ("https://www.amazon.sa/s?k=beats+headphones&rh=p_8%3A30-99", "🎧 Beats Headphones", False),
        ("https://www.amazon.sa/s?k=jbl+speaker&rh=p_8%3A30-99", "🎧 JBL Speaker", False),
        ("https://www.amazon.sa/s?k=harman+kardon&rh=p_8%3A30-99", "🎧 Harman Kardon", False),
        ("https://www.amazon.sa/s?k=marshall&rh=p_8%3A30-99", "🎧 Marshall", False),
        ("https://www.amazon.sa/s?k=skullcandy&rh=p_8%3A30-99", "🎧 Skullcandy", False),
        ("https://www.amazon.sa/s?k=sennheiser&rh=p_8%3A30-99", "🎧 Sennheiser", False),
        
        # 💻 لابتوبات
        ("https://www.amazon.sa/s?k=lenovo+laptop&rh=p_8%3A30-99", "💻 Lenovo Laptop", False),
        ("https://www.amazon.sa/s?k=hp+laptop&rh=p_8%3A30-99", "💻 HP Laptop", False),
        ("https://www.amazon.sa/s?k=dell+laptop&rh=p_8%3A30-99", "💻 Dell Laptop", False),
        ("https://www.amazon.sa/s?k=asus+laptop&rh=p_8%3A30-99", "💻 Asus Laptop", False),
        ("https://www.amazon.sa/s?k=acer+laptop&rh=p_8%3A30-99", "💻 Acer Laptop", False),
        ("https://www.amazon.sa/s?k=msi+laptop&rh=p_8%3A30-99", "💻 MSI Laptop", False),
        ("https://www.amazon.sa/s?k=razer+laptop&rh=p_8%3A30-99", "💻 Razer Laptop", False),
        ("https://www.amazon.sa/s?k=alienware&rh=p_8%3A30-99", "💻 Alienware", False),
        
        # 🎮 gaming
        ("https://www.amazon.sa/s?k=playstation+5&rh=p_8%3A30-99", "🎮 PS5", False),
        ("https://www.amazon.sa/s?k=playstation+4&rh=p_8%3A30-99", "🎮 PS4", False),
        ("https://www.amazon.sa/s?k=xbox+series&rh=p_8%3A30-99", "🎮 Xbox Series", False),
        ("https://www.amazon.sa/s?k=nintendo+switch&rh=p_8%3A30-99", "🎮 Nintendo Switch", False),
        ("https://www.amazon.sa/s?k=gaming+mouse&rh=p_8%3A30-99", "🎮 Gaming Mouse", False),
        ("https://www.amazon.sa/s?k=gaming+keyboard&rh=p_8%3A30-99", "🎮 Gaming Keyboard", False),
        ("https://www.amazon.sa/s?k=gaming+headset&rh=p_8%3A30-99", "🎮 Gaming Headset", False),
        ("https://www.amazon.sa/s?k=gaming+chair&rh=p_8%3A30-99", "🎮 Gaming Chair", False),
        ("https://www.amazon.sa/s?k=rtx+graphics&rh=p_8%3A30-99", "🎮 RTX Graphics", False),
        
        # 📷 كاميرات
        ("https://www.amazon.sa/s?k=canon+camera&rh=p_8%3A30-99", "📷 Canon Camera", False),
        ("https://www.amazon.sa/s?k=nikon+camera&rh=p_8%3A30-99", "📷 Nikon Camera", False),
        ("https://www.amazon.sa/s?k=sony+camera&rh=p_8%3A30-99", "📷 Sony Camera", False),
        ("https://www.amazon.sa/s?k=fujifilm&rh=p_8%3A30-99", "📷 Fujifilm", False),
        ("https://www.amazon.sa/s?k=gopro&rh=p_8%3A30-99", "📷 GoPro", False),
        ("https://www.amazon.sa/s?k=dji&rh=p_8%3A30-99", "📷 DJI Drone", False),
        
        # ⌚ ساعات
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
        
        # 🌸 عطور فاخرة
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
        
        # 👟 أحذية رياضية
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
        
        # 👔 ملابس رجالي
        ("https://www.amazon.sa/s?k=calvin+klein+men&rh=p_8%3A30-99", "👔 CK Men", False),
        ("https://www.amazon.sa/s?k=tommy+hilfiger+men&rh=p_8%3A30-99", "👔 Tommy Men", False),
        ("https://www.amazon.sa/s?k=ralph+lauren+men&rh=p_8%3A30-99", "👔 RL Men", False),
        ("https://www.amazon.sa/s?k=lacoste+men&rh=p_8%3A30-99", "👔 Lacoste Men", False),
        ("https://www.amazon.sa/s?k=hugo+boss&rh=p_8%3A30-99", "👔 Hugo Boss", False),
        ("https://www.amazon.sa/s?k=levis+jeans&rh=p_8%3A30-99", "👔 Levis Jeans", False),
        ("https://www.amazon.sa/s?k=wrangler+jeans&rh=p_8%3A30-99", "👔 Wrangler Jeans", False),
        ("https://www.amazon.sa/s?k=diesel&rh=p_8%3A30-99", "👔 Diesel", False),
        ("https://www.amazon.sa/s?k=g+star&rh=p_8%3A30-99", "👔 G-Star", False),
        
        # 👗 ملابس حريمي
        ("https://www.amazon.sa/s?k=michael+kors+bag&rh=p_8%3A30-99", "👜 MK Bags", False),
        ("https://www.amazon.sa/s?k=kate+spade&rh=p_8%3A30-99", "👜 Kate Spade", False),
        ("https://www.amazon.sa/s?k=coach+bag&rh=p_8%3A30-99", "👜 Coach", False),
        ("https://www.amazon.sa/s?k=guess+bag&rh=p_8%3A30-99", "👜 Guess", False),
        ("https://www.amazon.sa/s?k=fossil+bag&rh=p_8%3A30-99", "👜 Fossil Bag", False),
        ("https://www.amazon.sa/s?k=vera+bradley&rh=p_8%3A30-99", "👜 Vera Bradley", False),
        
        # 💎 مجوهرات
        ("https://www.amazon.sa/s?k=swarovski&rh=p_8%3A30-99", "💎 Swarovski", False),
        ("https://www.amazon.sa/s?k=pandora&rh=p_8%3A30-99", "💎 Pandora", False),
        ("https://www.amazon.sa/s?k=tiffany&rh=p_8%3A30-99", "💎 Tiffany", False),
        ("https://www.amazon.sa/s?k=cartier&rh=p_8%3A30-99", "💎 Cartier", False),
        ("https://www.amazon.sa/s?k=bulova&rh=p_8%3A30-99", "💎 Bulova", False),
        ("https://www.amazon.sa/s?k=anne+klein&rh=p_8%3A30-99", "💎 Anne Klein", False),
        
        # 🕶️ نظارات
        ("https://www.amazon.sa/s?k=ray+ban&rh=p_8%3A30-99", "🕶️ Ray Ban", False),
        ("https://www.amazon.sa/s?k=oakley&rh=p_8%3A30-99", "🕶️ Oakley", False),
        ("https://www.amazon.sa/s?k=persol&rh=p_8%3A30-99", "🕶️ Persol", False),
        ("https://www.amazon.sa/s?k=prada+sunglasses&rh=p_8%3A30-99", "🕶️ Prada", False),
        ("https://www.amazon.sa/s?k=gucci+sunglasses&rh=p_8%3A30-99", "🕶️ Gucci Sun", False),
        ("https://www.amazon.sa/s?k=burberry+sunglasses&rh=p_8%3A30-99", "🕶️ Burberry Sun", False),
        
        # 💄 مكياج
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
        
        # 🧴 عناية شخصية
        ("https://www.amazon.sa/s?k=olay&rh=p_8%3A30-99", "💆 Olay", False),
        ("https://www.amazon.sa/s?k=neutrogena&rh=p_8%3A30-99", "💆 Neutrogena", False),
        ("https://www.amazon.sa/s?k=cerave&rh=p_8%3A30-99", "💆 CeraVe", False),
        ("https://www.amazon.sa/s?k=cetaphil&rh=p_8%3A30-99", "💆 Cetaphil", False),
        ("https://www.amazon.sa/s?k=la+roche+posay&rh=p_8%3A30-99", "💆 La Roche", False),
        ("https://www.amazon.sa/s?k=vichy&rh=p_8%3A30-99", "💆 Vichy", False),
        ("https://www.amazon.sa/s?k=eucerin&rh=p_8%3A30-99", "💆 Eucerin", False),
        ("https://www.amazon.sa/s?k=aveeno&rh=p_8%3A30-99", "💆 Aveeno", False),
        ("https://www.amazon.sa/s?k=bioderma&rh=p_8%3A30-99", "💆 Bioderma", False),
        
        # 👶 أطفال
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
        
        # 🏋️ رياضة
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
        
        # 🏠 منزل
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
        
        # 🔧 أدوات
        ("https://www.amazon.sa/s?k=bosch+tools&rh=p_8%3A30-99", "🔧 Bosch", False),
        ("https://www.amazon.sa/s?k=makita&rh=p_8%3A30-99", "🔧 Makita", False),
        ("https://www.amazon.sa/s?k=dewalt&rh=p_8%3A30-99", "🔧 DeWalt", False),
        ("https://www.amazon.sa/s?k=black+decker&rh=p_8%3A30-99", "🔧 Black & Decker", False),
        ("https://www.amazon.sa/s?k=stanley&rh=p_8%3A30-99", "🔧 Stanley", False),
        ("https://www.amazon.sa/s?k=craftsman&rh=p_8%3A30-99", "🔧 Craftsman", False),
        ("https://www.amazon.sa/s?k=ryobi&rh=p_8%3A30-99", "🔧 Ryobi", False),
        ("https://www.amazon.sa/s?k=worx&rh=p_8%3A30-99", "🔧 Worx", False),
        
        # 🚗 سيارات
        ("https://www.amazon.sa/s?k=michelin+tires&rh=p_8%3A30-99", "🚗 Michelin", False),
        ("https://www.amazon.sa/s?k=bridgestone+tires&rh=p_8%3A30-99", "🚗 Bridgestone", False),
        ("https://www.amazon.sa/s?k=goodyear+tires&rh=p_8%3A30-99", "🚗 Goodyear", False),
        ("https://www.amazon.sa/s?k=pirelli&rh=p_8%3A30-99", "🚗 Pirelli", False),
        ("https://www.amazon.sa/s?k=continental+tires&rh=p_8%3A30-99", "🚗 Continental", False),
        ("https://www.amazon.sa/s?k=bosch+car&rh=p_8%3A30-99", "🚗 Bosch Car", False),
        ("https://www.amazon.sa/s?k=shell+oil&rh=p_8%3A30-99", "🚗 Shell", False),
        ("https://www.amazon.sa/s?k=mobil+1&rh=p_8%3A30-99", "🚗 Mobil 1", False),
        ("https://www.amazon.sa/s?k=castrol&rh=p_8%3A30-99", "🚗 Castrol", False),
        
        # 📚 كتب
        ("https://www.amazon.sa/s?k=kindle&rh=p_8%3A30-99", "📚 Kindle", False),
        ("https://www.amazon.sa/s?k=harry+potter+book&rh=p_8%3A30-99", "📚 Harry Potter", False),
        
        # 🌙 سعودي خاص
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
        
        # 💎 فاخر
        ("https://www.amazon.sa/s?k=louis+vuitton&rh=p_8%3A30-99", "👜 LV", False),
        ("https://www.amazon.sa/s?k=hermes&rh=p_8%3A30-99", "👜 Hermes", False),
        ("https://www.amazon.sa/s?k=coach&rh=p_8%3A30-99", "👜 Coach", False),
        ("https://www.amazon.sa/s?k=kate+spade&rh=p_8%3A30-99", "👜 Kate Spade", False),
        ("https://www.amazon.sa/s?k=burberry+bag&rh=p_8%3A30-99", "👜 Burberry", False),
        ("https://www.amazon.sa/s?k=longchamp&rh=p_8%3A30-99", "👜 Longchamp", False),
        ("https://www.amazon.sa/s?k=tumi&rh=p_8%3A30-99", "🧳 Tumi", False),
        ("https://www.amazon.sa/s?k=samsonite&rh=p_8%3A30-99", "🧳 Samsonite", False),
        ("https://www.amazon.sa/s?k=rimowa&rh=p_8%3A30-99", "🧳 Rimowa", False),

        # 🧠 Advanced Hidden Searches (جديدة وقوية)
        ("https://www.amazon.sa/s?k=discount&rh=p_n_pct-off-with-tax%3A50-99", "🔥 50-99% OFF", False),
        ("https://www.amazon.sa/s?k=deal&rh=p_n_pct-off-with-tax%3A60-99", "🔥 60-99% OFF", False),
        ("https://www.amazon.sa/s?k=offer&rh=p_n_pct-off-with-tax%3A70-99", "🔥 70-99% OFF", False),
        ("https://www.amazon.sa/s?k=sale&rh=p_n_pct-off-with-tax%3A80-99", "🔥 80-99% OFF", False),

        # ⚠️ Hidden Price Errors (Glitches)
        ("https://www.amazon.sa/s?k=*&rh=p_36%3A1-100", "💥 Ultra Cheap (1-100 SAR)", False),
        ("https://www.amazon.sa/s?k=*&rh=p_36%3A100-500", "💥 Cheap Deals (100-500 SAR)", False),

        # 🧾 Open Box / Used (كنز حقيقي)
        ("https://www.amazon.sa/s?k=used+like+new", "♻️ Used Like New", False),
        ("https://www.amazon.sa/s?k=open+box", "📦 Open Box", False),
        ("https://www.amazon.sa/s?k=renewed", "🔄 Renewed", False),

        # 🧪 Sorting Hacks (أهم إضافة)
        ("https://www.amazon.sa/s?k=*&s=price-asc-rank", "📉 Cheapest First", False),
        ("https://www.amazon.sa/s?k=*&s=review-rank", "⭐ Top Rated", False),
        ("https://www.amazon.sa/s?k=*&s=date-desc-rank", "🆕 Newest Deals", False),

        # 🏷️ Coupon stacking (مهم)
        ("https://www.amazon.sa/s?k=coupon+discount", "🎟️ Coupon Discount", False),
        ("https://www.amazon.sa/s?k=extra+off", "🎟️ Extra Off", False),

        # 🧨 Liquidation / Clearance مخفي
        ("https://www.amazon.sa/s?k=overstock", "📦 Overstock", False),
        ("https://www.amazon.sa/s?k=clearance+sale", "🔥 Clearance Sale", False),
        ("https://www.amazon.sa/s?k=warehouse+clearance", "🏭 Warehouse Clearance", False),

        # 🧠 Brand Hidden Deals (مش بتظهر بسهولة)
        ("https://www.amazon.sa/s?k=sony&rh=p_n_pct-off-with-tax%3A50-99", "🎧 Sony Hidden Deals", False),
        ("https://www.amazon.sa/s?k=samsung&rh=p_n_pct-off-with-tax%3A50-99", "📱 Samsung Hidden Deals", False),
        ("https://www.amazon.sa/s?k=apple&rh=p_n_pct-off-with-tax%3A30-99", "🍎 Apple Hidden Deals", False),

        # 🎯 Algorithm Exploit Searches
        ("https://www.amazon.sa/s?k=a&rh=p_n_pct-off-with-tax%3A70-99", "🎯 Single Letter Deals", False),
        ("https://www.amazon.sa/s?k=the&rh=p_n_pct-off-with-tax%3A70-99", "🎯 Random Deals", False),
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
        
        min_discount = 50 if 'Warehouse' in deal['category'] or 'Outlet' in deal['category'] or 'Clearance' in deal['category'] else (60 if is_bs else 65)
        
        has_discount = disc >= min_discount
        has_rating = rating >= 3.0
        is_reasonable = 0.5 < deal['price'] < 10000
        
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
• 200+ قسم شامل 📁
• عروض Warehouse المخفية 🏭
• Outlet & Clearance 🎁
• Lightning Deals ⚡
• Prime Exclusives 👑
• Best Sellers ⭐
• براندات فاخرة 💎

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
    
    status_msg = update.message.reply_text("🔍 *بدأت البحث في 200+ قسم...*\n⏱️ 5-7 دقائق", parse_mode='Markdown')
    
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
📁 الأقسام: 200+
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
            "categories": 200
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
