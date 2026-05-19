#!/usr/bin/env python3
import os
import re
import json
import logging
import time
import random
import hashlib
import signal
import atexit
from datetime import datetime
from collections import deque
from threading import Thread, Event, Lock

import cloudscraper
from fake_useragent import UserAgent
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN",
    "8769441239:AAEgX3uBbtWc_hHcqs0lmQ50AqKJGOWV6Ok"
)
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "432826122")
PORT = int(os.environ.get("PORT", 8080))

TARGET_DEALS_COUNT = 40
MIN_DISCOUNT = 50
MIN_RATING = 3.5

DATABASE_FILE = "bot_database.json"
ROTATION_FILE = "page_rotation.json"

ua = UserAgent()
sent_products = set()
sent_hashes = set()
is_scanning = False
updater = None
stop_event = Event()
state_lock = Lock()

class PageRotationManager:
    def __init__(self):
        self.visited_pages = set()
        self.page_queue = deque()
        self.all_pages = []
        self.rotation_count = 0
        self.current_batch = []

    def load_state(self):
        try:
            if os.path.exists(ROTATION_FILE):
                with open(ROTATION_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.visited_pages = set(data.get('visited', []))
                    self.rotation_count = data.get('rotation_count', 0)
                    logger.info(f"Loaded rotation state: {len(self.visited_pages)} visited, {self.rotation_count} rotations")
        except Exception as e:
            logger.error(f"Error loading rotation state: {e}")

    def save_state(self):
        try:
            with open(ROTATION_FILE, 'w', encoding='utf-8') as f:
                json.dump({
                    'visited': list(self.visited_pages),
                    'rotation_count': self.rotation_count,
                    'last_update': datetime.now().isoformat()
                }, f, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving rotation state: {e}")

    def generate_all_pages(self, categories):
        self.all_pages = []
        for base_url, cat_name, cat_type in categories:
            max_pages = PAGES_CONFIG.get(cat_type, 1)
            for page_num in range(1, max_pages + 1):
                page_url = self._build_page_url(base_url, page_num)
                page_id = f"{cat_name}_page{page_num}"
                self.all_pages.append({
                    'id': page_id,
                    'url': page_url,
                    'category': cat_name,
                    'type': cat_type,
                    'page_num': page_num,
                    'base_url': base_url
                })
        logger.info(f"Generated {len(self.all_pages)} total pages")
        self._refill_queue()
        self.save_state()
        return self.all_pages

    def _build_page_url(self, base_url, page_num):
        if page_num == 1:
            return base_url
        separator = '&' if '?' in base_url else '?'
        if 'gp/bestsellers' in base_url or 'gp/goldbox' in base_url:
            return f"{base_url}{separator}pg={page_num}"
        elif '/s?' in base_url or 'keywords=' in base_url:
            return f"{base_url}{separator}page={page_num}"
        else:
            return f"{base_url}{separator}page={page_num}"

    def _refill_queue(self):
        unvisited = [p for p in self.all_pages if p['id'] not in self.visited_pages]
        if not unvisited:
            unvisited = self.all_pages.copy()
            self.visited_pages.clear()
            self.rotation_count += 1
        random.shuffle(unvisited)
        self.page_queue = deque(unvisited)
        logger.info(f"Refilled queue with {len(unvisited)} pages")

    def get_next_batch(self, batch_size=50):
        if not self.page_queue:
            self._refill_queue()

        if self.all_pages and len(self.visited_pages) >= len(self.all_pages) * 0.9:
            logger.info("All pages visited, resetting rotation...")
            self.visited_pages.clear()
            self.rotation_count += 1
            self._refill_queue()

        available_pages = [p for p in self.page_queue if p['id'] not in self.visited_pages]
        random.shuffle(available_pages)
        batch = available_pages[:batch_size]

        for page in batch:
            try:
                self.page_queue.remove(page)
            except ValueError:
                pass
            self.visited_pages.add(page['id'])

        self.current_batch = batch
        self.save_state()
        logger.info(f"Selected batch: {len(batch)} pages (Total visited: {len(self.visited_pages)})")
        return batch

    def get_stats(self):
        total_pages = len(self.all_pages)
        return {
            'total_pages': total_pages,
            'visited_pages': len(self.visited_pages),
            'remaining_pages': total_pages - len(self.visited_pages) if total_pages else 0,
            'rotation_count': self.rotation_count,
            'progress_percent': (len(self.visited_pages) / total_pages * 100) if total_pages else 0
        }

page_rotator = PageRotationManager()

def load_database():
    global sent_products, sent_hashes
    try:
        if os.path.exists(DATABASE_FILE):
            with open(DATABASE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                sent_products = set(data.get('ids', []))
                sent_hashes = set(data.get('hashes', []))
                logger.info(f"Loaded DB: {len(sent_products)} ids, {len(sent_hashes)} hashes")
    except Exception as e:
        logger.error(f"Error loading DB: {e}")

def save_database():
    try:
        with state_lock:
            with open(DATABASE_FILE, 'w', encoding='utf-8') as f:
                json.dump({
                    'ids': list(sent_products),
                    'hashes': list(sent_hashes)
                }, f, ensure_ascii=False)
        logger.info("Saved DB")
    except Exception as e:
        logger.error(f"Error saving DB: {e}")

def extract_asin(link):
    if not link:
        return None
    patterns = [
        r'/dp/([A-Z0-9]{10})',
        r'/gp/product/([A-Z0-9]{10})',
        r'product/([A-Z0-9]{10})',
        r'/gp/aw/d/([A-Z0-9]{10})',
        r'asins?=([A-Z0-9]{10})',
        r'asin=([A-Z0-9]{10})'
    ]
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
    recent = list(sent_hashes)[-200:]
    for existing_hash in recent:
        if new_hash[:10] == existing_hash[:10]:
            return True
    return False

def get_product_id(deal):
    asin = extract_asin(deal.get('link', '') or '')
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
    try:
        ua_str = ua.random
    except Exception:
        ua_str = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/113.0 Safari/537.36'
    session = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True},
        delay=5
    )
    session.headers.update({
        'User-Agent': ua_str,
        'Accept-Language': 'ar-SA,ar;q=0.9,en-US;q=0.8,en;q=0.7',
        'Referer': 'https://www.amazon.sa/',
    })
    return session

def fetch_page(session, url, max_retries=3):
    backoff = 1.0
    for _ in range(max_retries):
        if stop_event.is_set():
            return None
        try:
            time.sleep(random.uniform(1, 2))
            r = session.get(url, timeout=25)
            if r.status_code == 200 and r.text:
                return r.text
            if r.status_code in (429, 503):
                logger.warning(f"Rate limited or unavailable ({r.status_code}) on {url}")
            time.sleep(backoff)
            backoff *= 2
        except Exception as e:
            logger.warning(f"Fetch failed for {url}: {e}")
            time.sleep(backoff)
            backoff *= 2
    return None

PAGES_CONFIG = {
    'best_sellers': 3,
    'deals': 2,
    'warehouse': 2,
    'coupons': 2,
    'search': 2,
    'outlet': 2,
    'prime': 2,
    'lightning': 1,
    'today': 2,
    'clearance': 3,
}

CATEGORIES_DEF = [
    ("https://www.amazon.sa/gp/bestsellers/electronics", "📱 Electronics Best Seller", 'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/fashion", "👕 Fashion Best Seller", 'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/beauty", "💄 Beauty Best Seller", 'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/watches", "⌚ Watches Best Seller", 'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/shoes", "👟 Shoes Best Seller", 'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/kitchen", "🍳 Kitchen Best Seller", 'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/home", "🏠 Home Best Seller", 'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/computers", "💻 Computers Best Seller", 'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/mobile", "📱 Mobile Best Seller", 'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/perfumes", "🌸 Perfumes Best Seller", 'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/toys", "🎮 Toys Best Seller", 'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/sports", "⚽ Sports Best Seller", 'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/baby", "👶 Baby Best Seller", 'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/grocery", "🛒 Grocery Best Seller", 'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/automotive", "🚗 Automotive Best Seller", 'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/tools", "🔧 Tools Best Seller", 'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/books", "📚 Books Best Seller", 'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/jewelry", "💎 Jewelry Best Seller", 'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/luggage", "🧳 Luggage Best Seller", 'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/pet", "🐾 Pet Best Seller", 'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/office", "📎 Office Best Seller", 'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/personal-care", "🧴 Personal Care Best Seller", 'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/health", "💊 Health Best Seller", 'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/video-games", "🎮 Games Best Seller", 'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/camera", "📷 Camera Best Seller", 'best_sellers'),

    ("https://www.amazon.sa/gp/goldbox", "🔥 Goldbox", 'deals'),
    ("https://www.amazon.sa/deals/electronics", "📱 Electronics Deals", 'deals'),
    ("https://www.amazon.sa/deals/fashion", "👕 Fashion Deals", 'deals'),
    ("https://www.amazon.sa/deals/beauty", "💄 Beauty Deals", 'deals'),
    ("https://www.amazon.sa/deals/home", "🏠 Home Deals", 'deals'),
    ("https://www.amazon.sa/deals/kitchen", "🍳 Kitchen Deals", 'deals'),
    ("https://www.amazon.sa/deals/watches", "⌚ Watches Deals", 'deals'),
    ("https://www.amazon.sa/deals/perfumes", "🌸 Perfumes Deals", 'deals'),
    ("https://www.amazon.sa/deals/toys", "🎮 Toys Deals", 'deals'),
    ("https://www.amazon.sa/deals/sports", "⚽ Sports Deals", 'deals'),
    ("https://www.amazon.sa/deals/baby", "👶 Baby Deals", 'deals'),
    ("https://www.amazon.sa/deals/grocery", "🛒 Grocery Deals", 'deals'),
    ("https://www.amazon.sa/deals/automotive", "🚗 Automotive Deals", 'deals'),
    ("https://www.amazon.sa/deals/tools", "🔧 Tools Deals", 'deals'),
    ("https://www.amazon.sa/deals/office", "📎 Office Deals", 'deals'),
    ("https://www.amazon.sa/deals/books", "📚 Books Deals", 'deals'),

    ("https://www.amazon.sa/gp/warehouse-deals", "🏭 Warehouse Deals", 'warehouse'),
    ("https://www.amazon.sa/gp/warehouse-deals/electronics", "🏭 Warehouse Electronics", 'warehouse'),
    ("https://www.amazon.sa/gp/warehouse-deals/fashion", "🏭 Warehouse Fashion", 'warehouse'),
    ("https://www.amazon.sa/gp/warehouse-deals/home", "🏭 Warehouse Home", 'warehouse'),
    ("https://www.amazon.sa/gp/warehouse-deals/kitchen", "🏭 Warehouse Kitchen", 'warehouse'),
    ("https://www.amazon.sa/gp/warehouse-deals/beauty", "🏭 Warehouse Beauty", 'warehouse'),
    ("https://www.amazon.sa/gp/warehouse-deals/sports", "🏭 Warehouse Sports", 'warehouse'),
    ("https://www.amazon.sa/gp/warehouse-deals/tools", "🏭 Warehouse Tools", 'warehouse'),

    ("https://www.amazon.sa/gp/coupons", "🎟️ Coupons", 'coupons'),
    ("https://www.amazon.sa/gp/coupons/electronics", "🎟️ Electronics Coupons", 'coupons'),
    ("https://www.amazon.sa/gp/coupons/fashion", "🎟️ Fashion Coupons", 'coupons'),
    ("https://www.amazon.sa/gp/coupons/home", "🎟️ Home Coupons", 'coupons'),
    ("https://www.amazon.sa/gp/coupons/beauty", "🎟️ Beauty Coupons", 'coupons'),
    ("https://www.amazon.sa/gp/coupons/grocery", "🎟️ Grocery Coupons", 'coupons'),
    ("https://www.amazon.sa/gp/coupons/baby", "🎟️ Baby Coupons", 'coupons'),

    ("https://www.amazon.sa/gp/prime/pipeline/prime_exclusives", "👑 Prime Exclusives", 'prime'),
    ("https://www.amazon.sa/gp/prime/pipeline/lightning_deals", "⚡ Lightning Deals", 'lightning'),

    ("https://www.amazon.sa/gp/todays-deals", "📅 Today Deals", 'today'),
    ("https://www.amazon.sa/gp/todays-deals/electronics", "📅 Today Electronics", 'today'),
    ("https://www.amazon.sa/gp/todays-deals/fashion", "📅 Today Fashion", 'today'),
    ("https://www.amazon.sa/gp/todays-deals/home", "📅 Today Home", 'today'),
    ("https://www.amazon.sa/gp/todays-deals/beauty", "📅 Today Beauty", 'today'),

    ("https://www.amazon.sa/outlet", "🎁 Outlet", 'outlet'),
    ("https://www.amazon.sa/outlet/electronics", "🎁 Outlet Electronics", 'outlet'),
    ("https://www.amazon.sa/outlet/home", "🎁 Outlet Home", 'outlet'),
    ("https://www.amazon.sa/outlet/fashion", "🎁 Outlet Fashion", 'outlet'),
    ("https://www.amazon.sa/outlet/beauty", "🎁 Outlet Beauty", 'outlet'),

    ("https://www.amazon.sa/s?k=clearance&rh=p_8%3A50-99", "🔥 Clearance", 'clearance'),
    ("https://www.amazon.sa/s?k=last+chance&rh=p_8%3A50-99", "🔥 Last Chance", 'clearance'),
    ("https://www.amazon.sa/s?k=final+sale&rh=p_8%3A50-99", "🔥 Final Sale", 'clearance'),
    ("https://www.amazon.sa/s?k=limited+time&rh=p_8%3A50-99", "⏰ Limited Time", 'clearance'),
    ("https://www.amazon.sa/s?k=flash+sale&rh=p_8%3A50-99", "⚡ Flash Sale", 'clearance'),
    ("https://www.amazon.sa/s?k=super+sale&rh=p_8%3A50-99", "💥 Super Sale", 'clearance'),
    ("https://www.amazon.sa/s?k=mega+deal&rh=p_8%3A50-99", "🎯 Mega Deal", 'clearance'),
    ("https://www.amazon.sa/s?k=big+sale&rh=p_8%3A50-99", "🎪 Big Sale", 'clearance'),

    ("https://www.amazon.sa/s?k=iphone&rh=p_8%3A30-99", "🍎 iPhone", 'search'),
    ("https://www.amazon.sa/s?k=ipad&rh=p_8%3A30-99", "🍎 iPad", 'search'),
    ("https://www.amazon.sa/s?k=macbook&rh=p_8%3A30-99", "🍎 MacBook", 'search'),
    ("https://www.amazon.sa/s?k=airpods&rh=p_8%3A30-99", "🍎 AirPods", 'search'),
    ("https://www.amazon.sa/s?k=apple+watch&rh=p_8%3A30-99", "🍎 Apple Watch", 'search'),
    ("https://www.amazon.sa/s?k=apple+tv&rh=p_8%3A30-99", "🍎 Apple TV", 'search'),
    ("https://www.amazon.sa/s?k=airtag&rh=p_8%3A30-99", "🍎 AirTag", 'search'),
    ("https://www.amazon.sa/s?k=homepod&rh=p_8%3A30-99", "🍎 HomePod", 'search'),

    ("https://www.amazon.sa/s?k=samsung+galaxy&rh=p_8%3A30-99", "📱 Galaxy Phone", 'search'),
    ("https://www.amazon.sa/s?k=samsung+tablet&rh=p_8%3A30-99", "📱 Galaxy Tab", 'search'),
    ("https://www.amazon.sa/s?k=samsung+watch&rh=p_8%3A30-99", "📱 Galaxy Watch", 'search'),
    ("https://www.amazon.sa/s?k=samsung+buds&rh=p_8%3A30-99", "📱 Galaxy Buds", 'search'),
    ("https://www.amazon.sa/s?k=samsung+tv&rh=p_8%3A30-99", "📱 Samsung TV", 'search'),
    ("https://www.amazon.sa/s?k=samsung+monitor&rh=p_8%3A30-99", "📱 Samsung Monitor", 'search'),

    ("https://www.amazon.sa/s?k=sony+headphones&rh=p_8%3A30-99", "🎧 Sony Headphones", 'search'),
    ("https://www.amazon.sa/s?k=bose+headphones&rh=p_8%3A30-99", "🎧 Bose Headphones", 'search'),
    ("https://www.amazon.sa/s?k=beats+headphones&rh=p_8%3A30-99", "🎧 Beats Headphones", 'search'),
    ("https://www.amazon.sa/s?k=jbl+speaker&rh=p_8%3A30-99", "🎧 JBL Speaker", 'search'),
    ("https://www.amazon.sa/s?k=harman+kardon&rh=p_8%3A30-99", "🎧 Harman Kardon", 'search'),
    ("https://www.amazon.sa/s?k=marshall&rh=p_8%3A30-99", "🎧 Marshall", 'search'),
    ("https://www.amazon.sa/s?k=skullcandy&rh=p_8%3A30-99", "🎧 Skullcandy", 'search'),
    ("https://www.amazon.sa/s?k=sennheiser&rh=p_8%3A30-99", "🎧 Sennheiser", 'search'),

    ("https://www.amazon.sa/s?k=lenovo+laptop&rh=p_8%3A30-99", "💻 Lenovo Laptop", 'search'),
    ("https://www.amazon.sa/s?k=hp+laptop&rh=p_8%3A30-99", "💻 HP Laptop", 'search'),
    ("https://www.amazon.sa/s?k=dell+laptop&rh=p_8%3A30-99", "💻 Dell Laptop", 'search'),
    ("https://www.amazon.sa/s?k=asus+laptop&rh=p_8%3A30-99", "💻 Asus Laptop", 'search'),
    ("https://www.amazon.sa/s?k=acer+laptop&rh=p_8%3A30-99", "💻 Acer Laptop", 'search'),
    ("https://www.amazon.sa/s?k=msi+laptop&rh=p_8%3A30-99", "💻 MSI Laptop", 'search'),
    ("https://www.amazon.sa/s?k=razer+laptop&rh=p_8%3A30-99", "💻 Razer Laptop", 'search'),
    ("https://www.amazon.sa/s?k=alienware&rh=p_8%3A30-99", "💻 Alienware", 'search'),

    ("https://www.amazon.sa/s?k=playstation+5&rh=p_8%3A30-99", "🎮 PS5", 'search'),
    ("https://www.amazon.sa/s?k=playstation+4&rh=p_8%3A30-99", "🎮 PS4", 'search'),
    ("https://www.amazon.sa/s?k=xbox+series&rh=p_8%3A30-99", "🎮 Xbox Series", 'search'),
    ("https://www.amazon.sa/s?k=nintendo+switch&rh=p_8%3A30-99", "🎮 Nintendo Switch", 'search'),
    ("https://www.amazon.sa/s?k=gaming+mouse&rh=p_8%3A30-99", "🎮 Gaming Mouse", 'search'),
    ("https://www.amazon.sa/s?k=gaming+keyboard&rh=p_8%3A30-99", "🎮 Gaming Keyboard", 'search'),
    ("https://www.amazon.sa/s?k=gaming+headset&rh=p_8%3A30-99", "🎮 Gaming Headset", 'search'),
    ("https://www.amazon.sa/s?k=gaming+chair&rh=p_8%3A30-99", "🎮 Gaming Chair", 'search'),
    ("https://www.amazon.sa/s?k=rtx+graphics&rh=p_8%3A30-99", "🎮 RTX Graphics", 'search'),
]

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
            except Exception:
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
            except Exception:
                pass

    if discount == 0:
        badge = item.find(string=re.compile(r'(\d+)%'))
        if badge:
            match = re.search(r'(\d+)', str(badge))
            if match:
                try:
                    discount = int(match.group())
                    old_price = price / (1 - discount / 100)
                except Exception:
                    pass

    title = None
    for sel in ['h2 a span', 'h2 span', '.a-size-mini span', '.a-size-base-plus', '.p13n-sc-truncated', '.a-size-medium']:
        el = item.select_one(sel)
        if el and el.text.strip():
            title = el.text.strip()
            if len(title) > 5:
                break

    if not title:
        return None

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
            except Exception:
                pass

    deal = {
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
    }
    deal['id'] = get_product_id(deal)
    return deal

def is_valid_deal(deal):
    if deal['discount'] < MIN_DISCOUNT:
        return False
    if deal['rating'] < MIN_RATING:
        return False
    if deal['price'] <= 0 or deal['price'] > 10000:
        return False
    return True

def search_all_deals(chat_id, status_message_id=None):
    all_deals = []
    session = create_session()

    if not page_rotator.all_pages:
        page_rotator.generate_all_pages(CATEGORIES_DEF)
        page_rotator.load_state()

    batch_size = 50
    max_attempts = 10

    for attempt in range(max_attempts):
        if stop_event.is_set():
            break
        if len(all_deals) >= TARGET_DEALS_COUNT * 3:
            break

        pages_to_search = page_rotator.get_next_batch(batch_size)
        if not pages_to_search:
            break

        total_pages = len(pages_to_search)
        processed = 0

        for page_info in pages_to_search:
            if stop_event.is_set():
                break

            try:
                processed += 1

                if processed % 5 == 0 and status_message_id and updater:
                    stats = page_rotator.get_stats()
                    progress = (
                        f"⏳ جاري البحث... ({processed}/{total_pages} صفحة)\n"
                        f"📍 {page_info['category']} - صفحة {page_info['page_num']}\n"
                        f"🔄 دورة: {stats['rotation_count']}\n"
                        f"✅ تم جمع: {len(all_deals)} صفقة"
                    )
                    try:
                        updater.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=status_message_id,
                            text=progress
                        )
                    except Exception:
                        pass

                logger.info(f"Searching [{page_info['category']}] Page {page_info['page_num']}")
                html = fetch_page(session, page_info['url'])
                if not html:
                    continue

                soup = BeautifulSoup(html, 'html.parser')
                items = []

                if 'best_sellers' in page_info['type']:
                    items.extend(soup.find_all('li', class_='zg-item-immersion'))
                    items.extend(soup.find_all('div', class_='p13n-sc-uncoverable-faceout'))

                items.extend(soup.find_all('div', {'data-component-type': 's-search-result'}))
                items.extend(soup.find_all('div', {'data-testid': 'deal-card'}))
                items.extend(soup.find_all('div', class_='s-result-item'))
                items.extend(soup.find_all('div', class_='a-section'))

                logger.info(f"Found {len(items)} items")

                for item in items:
                    if stop_event.is_set():
                        break
                    try:
                        deal = parse_item(item, page_info['category'], 'best_sellers' in page_info['type'])
                        if deal and is_valid_deal(deal):
                            all_deals.append(deal)
                    except Exception:
                        continue

                time.sleep(random.uniform(1.5, 3))

            except Exception as e:
                logger.error(f"Error in {page_info['category']}: {e}")

        logger.info(f"Attempt {attempt + 1}: Collected {len(all_deals)} valid deals")

    stats = page_rotator.get_stats()
    logger.info(f"Total collected: {len(all_deals)} deals | Progress: {stats['progress_percent']:.1f}%")
    return all_deals

def filter_premium_deals(deals):
    filtered = []
    seen_ids_local = set()
    used_asins = set()
    random.shuffle(deals)

    for deal in deals:
        if len(filtered) >= TARGET_DEALS_COUNT:
            break

        pid = deal.get('id')
        if not pid:
            continue
        if pid in seen_ids_local or pid in sent_products:
            continue
        if is_similar_product(deal.get('title', '')):
            continue

        asin = extract_asin(deal.get('link', '') or '')
        if asin and asin in used_asins:
            continue

        filtered.append(deal)
        seen_ids_local.add(pid)
        if asin:
            used_asins.add(asin)

    filtered.sort(key=lambda d: (d.get('discount', 0), d.get('rating', 0)), reverse=True)
    return filtered[:TARGET_DEALS_COUNT]

def send_deals_to_telegram(chat_id, deals):
    if not updater:
        logger.warning("Updater not initialized")
        return

    bot = updater.bot
    for deal in deals:
        try:
            text = (
                f"{deal.get('title')}\n"
                f"السعر: {deal.get('price')} ريال\n"
                f"الخصم: {deal.get('discount')}%\n"
                f"التقييم: {deal.get('rating')}\n"
                f"{deal.get('link')}"
            )
            bot.send_message(chat_id=chat_id, text=text)
            with state_lock:
                sent_products.add(deal.get('id'))
                sent_hashes.add(create_title_hash(deal.get('title', '')))
            time.sleep(random.uniform(0.5, 1.5))
        except Exception as e:
            logger.warning(f"Failed to send deal: {e}")

def run_scan(chat_id, status_message_id=None):
    global is_scanning
    if is_scanning:
        logger.info("Scan already running")
        return

    is_scanning = True
    try:
        all_deals = search_all_deals(chat_id, status_message_id)
        if not all_deals:
            logger.info("No deals found")
            return
        final_deals = filter_premium_deals(all_deals)
        logger.info(f"Selected {len(final_deals)} deals to send")
        send_deals_to_telegram(chat_id, final_deals)
        save_database()
        page_rotator.save_state()
    finally:
        is_scanning = False

def start_command(update: Update, context: CallbackContext):
    update.message.reply_text("البوت يعمل. استخدم /scan_now للتشغيل و /status لمعرفة الحالة.")

def status_command(update: Update, context: CallbackContext):
    stats = page_rotator.get_stats()
    text = (
        f"Pages: {stats['total_pages']}\n"
        f"Visited: {stats['visited_pages']}\n"
        f"Remaining: {stats['remaining_pages']}\n"
        f"Rotation: {stats['rotation_count']}\n"
        f"Progress: {stats['progress_percent']:.1f}%\n"
        f"Scanning: {is_scanning}"
    )
    update.message.reply_text(text)

def scan_now_command(update: Update, context: CallbackContext):
    msg = update.message.reply_text("Starting scan... سأرسل النتائج بعد الانتهاء.")
    t = Thread(target=run_scan, args=(update.message.chat_id, msg.message_id), daemon=True)
    t.start()

def graceful_shutdown(signum, frame):
    logger.info(f"Signal {signum} received, shutting down...")
    stop_event.set()
    try:
        save_database()
        page_rotator.save_state()
    except Exception:
        pass
    if updater:
        try:
            updater.stop()
        except Exception:
            pass
    raise SystemExit(128 + signum)

def cleanup():
    try:
        save_database()
        page_rotator.save_state()
    except Exception:
        pass

def main():
    global updater

    load_database()
    page_rotator.generate_all_pages(CATEGORIES_DEF)
    page_rotator.load_state()

    atexit.register(cleanup)
    signal.signal(signal.SIGINT, graceful_shutdown)
    signal.signal(signal.SIGTERM, graceful_shutdown)

    updater = Updater(token=TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start_command))
    dp.add_handler(CommandHandler("status", status_command))
    dp.add_handler(CommandHandler("scan_now", scan_now_command))

    updater.start_polling()
    logger.info("Bot started successfully.")
    updater.idle()

if __name__ == "__main__":
    main()
