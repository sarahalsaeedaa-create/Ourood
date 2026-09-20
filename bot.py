import os
import re
import json
import logging
import requests
import cloudscraper
import time
import random
import hashlib
import threading
from datetime import datetime
from bs4 import BeautifulSoup
from flask import Flask
from collections import deque
import pandas as pd

from telegram import Bot, Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from fake_useragent import UserAgent

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8769441239:AAG4sl2y2qPdvK4iPkZgyiduHNEkTpto0zM")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "432826122")
PORT = int(os.environ.get("PORT", 8080))

RESEND_COOLDOWN_DAYS = 7  # منع إعادة إرسال "نفس المنتج" قبل أسبوع كامل

# ========== Flask App for Keep-Alive ==========
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running continuously!", 200

@app.route('/health')
def health():
    stats = page_rotator.get_stats() if page_rotator.all_pages else {}
    return {
        "status": "ok",
        "products_sent": len(sent_log),
        "timestamp": datetime.now().isoformat(),
        "total_pages": stats.get('total_pages', 0),
        "visited_in_loop": stats.get('visited_pages', 0),
        "loop_count": stats.get('rotation_count', 0)
    }, 200

def run_flask():
    app.run(host='0.0.0.0', port=PORT)

def keep_alive_ping():
    while True:
        try:
            time.sleep(600)
            logger.info("💓 Keep-alive ping")
        except Exception as e:
            logger.error(f"Keep-alive error: {e}")
            time.sleep(60)

ua = UserAgent()
sent_products = set()
sent_hashes = set()
sent_log = {}   # deal_id -> تاريخ آخر إرسال
hash_log = {}   # title_hash -> تاريخ آخر إرسال

MIN_DISCOUNT = 70  # حد الخصم الأدنى 70%

# ========== عدد الصفحات لكل قسم (موسّع) ==========
# ملاحظة: أمازون غالباً بيوقف النتائج بعد ~20 صفحة، والبوت بيتخطى الصفحات الفاضية تلقائياً
PAGES_CONFIG = {
    'huge_cat': 40,
    'now_cat': 30,
    'deal_cat': 30,
    'best_cat': 40,   # بحث مرتب بالأكثر مبيعاً + خصم 70%
    'bs_list': 2,     # صفحات قوائم الأكثر مبيعاً الرسمية من أمازون (غالباً صفحتين)
}

# ========== توسيع الأقسام الشاملة (أمازون السعودية + أمازون ناو) ==========
CATEGORIES_DEF = [
    # --- قسم أمازون ناو و السوبرماركت (Amazon Now & Fresh) ---
    ("https://www.amazon.sa/s?k=fresh&rh=p_8%3A70-", "⚡ Amazon Now Fresh", 'now_cat'),
    ("https://www.amazon.sa/s?k=amazon+now&rh=p_8%3A70-", "⚡ Amazon Now Deals", 'now_cat'),
    ("https://www.amazon.sa/s?k=supermarket&rh=p_8%3A70-", "🛒 Supermarket Deals", 'now_cat'),
    ("https://www.amazon.sa/s?k=groceries&rh=p_8%3A70-", "🛒 Groceries 70% Off", 'now_cat'),
    ("https://www.amazon.sa/s?k=fruits&rh=p_8%3A70-", "🍎 Fruits", 'now_cat'),
    ("https://www.amazon.sa/s?k=vegetables&rh=p_8%3A70-", "🥬 Vegetables", 'now_cat'),
    ("https://www.amazon.sa/s?k=meat&rh=p_8%3A70-", "🥩 Meat & Poultry", 'now_cat'),
    ("https://www.amazon.sa/s?k=dairy&rh=p_8%3A70-", "🥛 Dairy & Eggs", 'now_cat'),
    ("https://www.amazon.sa/s?k=bakery&rh=p_8%3A70-", "🍞 Bakery", 'now_cat'),
    ("https://www.amazon.sa/s?k=frozen&rh=p_8%3A70-", "🧊 Frozen Food", 'now_cat'),
    ("https://www.amazon.sa/s?k=drinks&rh=p_8%3A70-", "🥤 Drinks & Beverages", 'now_cat'),
    ("https://www.amazon.sa/s?k=snacks&rh=p_8%3A70-", "🍿 Snacks", 'now_cat'),
    ("https://www.amazon.sa/s?k=baby+food&rh=p_8%3A70-", "👶 Baby Food", 'now_cat'),
    ("https://www.amazon.sa/s?k=pet+food&rh=p_8%3A70-", "🐾 Pet Food", 'now_cat'),
    ("https://www.amazon.sa/s?k=cleaning&rh=p_8%3A70-", "🧼 Cleaning Products", 'now_cat'),
    ("https://www.amazon.sa/s?k=personal+care&rh=p_8%3A70-", "🧴 Personal Care", 'now_cat'),
    ("https://www.amazon.sa/s?k=breakfast&rh=p_8%3A70-", "🥣 Breakfast & Cereal", 'now_cat'),
    ("https://www.amazon.sa/s?k=rice+and+pasta&rh=p_8%3A70-", "🍚 Rice & Pasta", 'now_cat'),

    # --- عروض التصفية والمستودع والذهب ---
    ("https://www.amazon.sa/s?rh=p_8%3A70-99", "🔥 All Deals 70% Off", 'deal_cat'),
    ("https://www.amazon.sa/gp/goldbox", "🔥 Goldbox Today Deals", 'deal_cat'),
    ("https://www.amazon.sa/gp/warehouse-deals", "🏭 Warehouse Deals", 'deal_cat'),
    ("https://www.amazon.sa/outlet", "🎁 Outlet Store", 'deal_cat'),

    # --- الأقسام الكبرى على أمازون (تغطية شاملة) ---
    ("https://www.amazon.sa/s?i=electronics&rh=p_8%3A70-", "📱 الإلكترونيات", 'huge_cat'),
    ("https://www.amazon.sa/s?i=mobile-apps&rh=p_8%3A70-", "📲 الجوالات والإكسسوارات", 'huge_cat'),
    ("https://www.amazon.sa/s?i=fashion&rh=p_8%3A70-", "👕 الأزياء والموضة", 'huge_cat'),
    ("https://www.amazon.sa/s?i=beauty&rh=p_8%3A70-", "💄 العناية والجمال", 'huge_cat'),
    ("https://www.amazon.sa/s?i=home&rh=p_8%3A70-", "🏠 المنزل والمطبخ", 'huge_cat'),
    ("https://www.amazon.sa/s?i=computers&rh=p_8%3A70-", "💻 الكمبيوتر والملحقات", 'huge_cat'),
    ("https://www.amazon.sa/s?i=videogames&rh=p_8%3A70-", "🎮 الألعاب والألعاب الإلكترونية", 'huge_cat'),
    ("https://www.amazon.sa/s?i=toys&rh=p_8%3A70-", "🧸 الألعاب والترفيه", 'huge_cat'),
    ("https://www.amazon.sa/s?i=sports&rh=p_8%3A70-", "⚽ الرياضة واللياقة", 'huge_cat'),
    ("https://www.amazon.sa/s?i=automotive&rh=p_8%3A70-", "🚗 السيارات والإكسسوارات", 'huge_cat'),
    ("https://www.amazon.sa/s?i=baby-products&rh=p_8%3A70-", "🍼 مستلزمات الأطفال", 'huge_cat'),
    ("https://www.amazon.sa/s?i=office-products&rh=p_8%3A70-", "📎 المستلزمات المكتبية", 'huge_cat'),
    ("https://www.amazon.sa/s?i=hi-tech&rh=p_8%3A70-", "🎧 الصوتيات والصور", 'huge_cat'),
    ("https://www.amazon.sa/s?i=perfumes&rh=p_8%3A70-", "🌸 العطور 70% خصم", 'huge_cat'),
    ("https://www.amazon.sa/s?i=watches&rh=p_8%3A70-", "⌚ الساعات 70% خصم", 'huge_cat'),
]

# ========== إضافات: الأكثر مبيعاً + أقسام أمازون ناو الإضافية ==========
_POP = "&s=exact-aware-popularity-rank"   # ترتيب النتائج بالأكثر مبيعاً/شعبية

# 1) نفس أقسام أمازون ناو الحالية لكن مرتبة بالأكثر مبيعاً
CATEGORIES_DEF += [
    (u + _POP, n + " ⭐Top", t)
    for (u, n, t) in list(CATEGORIES_DEF) if t == 'now_cat'
]

# 2) أقسام أمازون ناو / السوبرماركت إضافية (مرتبة بالأكثر مبيعاً)
_EXTRA_NOW = [
    ("grocery", "🛍️ Grocery"),
    ("water", "💧 Water"),
    ("coffee", "☕ Coffee"),
    ("tea", "🍵 Tea"),
    ("chocolate", "🍫 Chocolate & Sweets"),
    ("juice", "🧃 Juice"),
    ("cooking+oil", "🫒 Cooking Oil"),
    ("sugar+and+salt", "🧂 Sugar & Salt"),
    ("spices", "🌶️ Spices"),
    ("canned+food", "🥫 Canned Food"),
    ("nuts", "🥜 Nuts & Dried Fruits"),
    ("dates", "🌴 Dates"),
    ("diapers", "🍼 Diapers"),
    ("tissues", "🧻 Tissues & Paper"),
    ("laundry", "🧺 Laundry"),
    ("dishwashing", "🍽️ Dishwashing"),
    ("shampoo", "🧴 Shampoo & Hair Care"),
    ("vitamins", "💊 Vitamins & Supplements"),
    ("biscuits", "🍪 Biscuits & Cookies"),
    ("noodles", "🍜 Noodles & Instant Food"),
]
CATEGORIES_DEF += [
    (f"https://www.amazon.sa/s?k={kw}&rh=p_8%3A70-{_POP}", f"{label} (Now/Top)", 'now_cat')
    for kw, label in _EXTRA_NOW
]

# 3) كل الأقسام الكبرى + عروض عامة لكن مرتبة بالأكثر مبيعاً
CATEGORIES_DEF += [
    (u + _POP, "⭐ الأكثر مبيعاً - " + n, 'best_cat')
    for (u, n, t) in list(CATEGORIES_DEF) if t == 'huge_cat'
]
CATEGORIES_DEF.append(
    ("https://www.amazon.sa/s?rh=p_8%3A70-99" + _POP, "⭐ الأكثر مبيعاً - كل الأقسام 70%+", 'best_cat')
)

# 4) قوائم الأكثر مبيعاً الرسمية من أمازون (قد تحتاج تعديل الـ slugs حسب الموقع)
CATEGORIES_DEF += [
    ("https://www.amazon.sa/gp/bestsellers", "🏆 Best Sellers - الكل", 'bs_list'),
    ("https://www.amazon.sa/gp/bestsellers/electronics", "🏆 Best Sellers - إلكترونيات", 'bs_list'),
    ("https://www.amazon.sa/gp/bestsellers/beauty", "🏆 Best Sellers - جمال", 'bs_list'),
    ("https://www.amazon.sa/gp/bestsellers/grocery", "🏆 Best Sellers - بقالة", 'bs_list'),
    ("https://www.amazon.sa/gp/bestsellers/kitchen", "🏆 Best Sellers - مطبخ", 'bs_list'),
    ("https://www.amazon.sa/gp/bestsellers/videogames", "🏆 Best Sellers - ألعاب فيديو", 'bs_list'),
    ("https://www.amazon.sa/gp/bestsellers/toys", "🏆 Best Sellers - ألعاب", 'bs_list'),
    ("https://www.amazon.sa/gp/bestsellers/sports", "🏆 Best Sellers - رياضة", 'bs_list'),
    ("https://www.amazon.sa/gp/bestsellers/baby", "🏆 Best Sellers - أطفال", 'bs_list'),
    ("https://www.amazon.sa/gp/movers-and-shakers", "📈 Movers & Shakers", 'bs_list'),
    ("https://www.amazon.sa/gp/new-releases", "🆕 New Releases", 'bs_list'),
]

BEST_TYPES = ('best_cat', 'bs_list')

# ========== نظام تدوير الصفحات الشامل المستمر بلا نهاية ==========
class PageRotationManager:
    def __init__(self):
        self.visited_pages = set()
        self.page_queue_amazon = deque()
        self.page_queue_now = deque()
        self.all_pages = []
        self.rotation_count = 0
        self.dead_from = {}  # base_url -> أول رقم صفحة طلع فاضي (نتخطى اللي بعده)

    def generate_all_pages(self, categories):
        self.all_pages = []
        for base_url, cat_name, cat_type in categories:
            max_pages = PAGES_CONFIG.get(cat_type, 15)
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
        self._refill_queues()
        logger.info(f"📚 Full Scanning Engine Initialized: Generated {len(self.all_pages)} Pages across All Categories!")
        return self.all_pages

    def _build_page_url(self, base_url, page_num):
        if page_num == 1:
            return base_url
        if '/bestsellers' in base_url or '/movers-and-shakers' in base_url or '/new-releases' in base_url:
            separator = '&' if '?' in base_url else '?'
            return f"{base_url}{separator}pg={page_num}"
        separator = '&' if '?' in base_url else '?'
        return f"{base_url}{separator}page={page_num}"

    def _refill_queues(self):
        amazon_pages = [p for p in self.all_pages if not p['type'].startswith('now') and p['id'] not in self.visited_pages]
        now_pages = [p for p in self.all_pages if p['type'].startswith('now') and p['id'] not in self.visited_pages]

        random.shuffle(amazon_pages)
        random.shuffle(now_pages)

        self.page_queue_amazon = deque(amazon_pages)
        self.page_queue_now = deque(now_pages)

    def mark_exhausted(self, base_url, page_num):
        """تسجيل إن القسم ده خلصت صفحاته عند رقم معين"""
        cur = self.dead_from.get(base_url)
        if cur is None or page_num < cur:
            self.dead_from[base_url] = page_num

    def _pop_valid(self, queue):
        while queue:
            page = queue.popleft()
            self.visited_pages.add(page['id'])
            dead = self.dead_from.get(page['base_url'])
            if dead is not None and page['page_num'] > dead:
                continue  # صفحة بعد نهاية القسم، تخطى
            return page
        return None

    def get_balanced_batch(self, batch_size=10):
        """تجهيز دفعة صفحات؛ وفي حال انتهاء القائمة، يتم التحديث والتكرار فوراً"""
        batch = []
        half = batch_size // 2

        # إذا خلصت الصفحات، أعد فتح الدورة فوراً للتحديث المستمر!
        if not self.page_queue_amazon and not self.page_queue_now:
            self.restart_full_cycle()

        for _ in range(half):
            page = self._pop_valid(self.page_queue_amazon)
            if page:
                batch.append(page)

        for _ in range(half):
            page = self._pop_valid(self.page_queue_now)
            if page:
                batch.append(page)

        return batch

    def restart_full_cycle(self):
        """إعادة الدورة فوراً للبحث عن العروض الجديدة والمحدثة من أمازون"""
        self.visited_pages.clear()
        self.dead_from.clear()
        self.rotation_count += 1
        self._refill_queues()
        logger.info(f"🔄 Completed Full Scan Cycle #{self.rotation_count}! Re-shuffling and restarting endless scan...")

    def get_stats(self):
        visited = len(self.visited_pages)
        total = len(self.all_pages)
        return {
            'total_pages': total,
            'visited_pages': visited,
            'remaining_pages': max(0, total - visited),
            'progress_percent': (visited / total * 100) if total else 0,
            'rotation_count': self.rotation_count
        }

page_rotator = PageRotationManager()

def load_database():
    global sent_products, sent_hashes, sent_log, hash_log
    try:
        if os.path.exists('bot_database.json'):
            with open('bot_database.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
                sent_log = data.get('sent_log', {})
                hash_log = data.get('hash_log', {})
                sent_products = set(sent_log.keys())
                sent_hashes = set(hash_log.keys())
    except Exception as e:
        logger.error(f"Error loading DB: {e}")

def save_database():
    try:
        with open('bot_database.json', 'w', encoding='utf-8') as f:
            json.dump({
                'sent_log': sent_log,
                'hash_log': hash_log
            }, f)
    except Exception as e:
        logger.error(f"Error saving DB: {e}")

def export_to_excel(deals):
    try:
        excel_file = 'amazon_deals.xlsx'
        df_new = pd.DataFrame(deals)
        cols_to_keep = ['title', 'price', 'old_price', 'discount', 'category', 'type', 'is_best_seller', 'link', 'id']
        df_new = df_new[[c for c in cols_to_keep if c in df_new.columns]]
        df_new['date_added'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        if os.path.exists(excel_file):
            try:
                df_existing = pd.read_excel(excel_file)
                df_combined = pd.concat([df_existing, df_new], ignore_index=True)
                df_combined.drop_duplicates(subset=['id'], keep='last', inplace=True)
                df_combined.to_excel(excel_file, index=False)
            except Exception:
                df_new.to_excel(excel_file, index=False)
        else:
            df_new.to_excel(excel_file, index=False)
    except Exception as e:
        logger.error(f"Error exporting to Excel: {e}")

def extract_asin(link):
    if not link:
        return None
    patterns = [r'/dp/([A-Z0-9]{10})', r'/gp/product/([A-Z0-9]{10})', r'product/([A-Z0-9]{10})']
    for p in patterns:
        match = re.search(p, link, re.I)
        if match:
            return match.group(1).upper()
    return None

def create_title_hash(title):
    clean = re.sub(r'[^\w\s]', '', title.lower())
    clean = re.sub(r'\s+', ' ', clean).strip()
    clean = re.sub(r'\d+', '', clean)
    for word in ['amazon', 'saudi', 'ريال', 'sar', 'new', 'جديد', 'شحن']:
        clean = clean.replace(word, '')
    return hashlib.md5(clean[:30].strip().encode()).hexdigest()[:16]

def get_product_id(deal):
    asin = extract_asin(deal.get('link', ''))
    if asin:
        return f"ASIN_{asin}"
    key = f"{deal.get('title', '')}_{deal.get('price', 0)}"
    return f"HASH_{hashlib.md5(key.encode()).hexdigest()[:12]}"

def is_on_cooldown(deal_id, title):
    now = datetime.now()
    ts = sent_log.get(deal_id)
    if ts:
        try:
            if (now - datetime.fromisoformat(ts)).days < RESEND_COOLDOWN_DAYS:
                return True
        except Exception:
            pass
    h = create_title_hash(title)
    hts = hash_log.get(h)
    if hts:
        try:
            if (now - datetime.fromisoformat(hts)).days < RESEND_COOLDOWN_DAYS:
                return True
        except Exception:
            pass
    return False

def create_session():
    session = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True},
        delay=5
    )
    session.headers.update({
        'User-Agent': ua.random,
        'Accept-Language': 'ar-SA,ar;q=0.9,en-US;q=0.8,en;q=0.7',
        'Referer': 'https://www.amazon.sa/',
    })
    return session

def fetch_page(session, url):
    for i in range(2):
        try:
            time.sleep(random.uniform(0.5, 1.5))
            r = session.get(url, timeout=12)
            if r.status_code == 200:
                return r.text
        except Exception:
            pass
    return None

def is_valid_deal(deal):
    if deal['discount'] < MIN_DISCOUNT or deal['price'] <= 0 or deal['old_price'] <= deal['price']:
        return False
    return True

def parse_item(item, category, is_best_seller, cat_type=''):
    price = None
    price_el = item.select_one('.a-price .a-offscreen') or item.select_one('.a-price-whole') or item.select_one('.a-price')
    if price_el:
        try:
            txt = price_el.text.replace(',', '').replace('ريال', '').replace('SAR', '').strip()
            match = re.search(r'[\d.]+', txt)
            if match:
                price = float(match.group())
        except Exception:
            pass

    if not price or price <= 0:
        return None

    old_price = 0
    discount = 0

    old_el = item.select_one('span.a-text-price span.a-offscreen') or item.select_one('span.a-text-price') or item.select_one('.a-possibility-price')
    if old_el:
        try:
            txt = old_el.text.replace(',', '').replace('ريال', '').replace('SAR', '').strip()
            match = re.search(r'[\d.]+', txt)
            if match:
                val = float(match.group())
                if val > price:
                    old_price = val
                    discount = int(((old_price - price) / old_price) * 100)
        except Exception:
            pass

    if discount == 0:
        badge = item.find(string=re.compile(r'خصم\s*(\d+)%|(\d+)%\s*off', re.I))
        if badge:
            try:
                match = re.search(r'(\d+)', str(badge))
                if match:
                    discount = int(match.group(1))
                    if 0 < discount < 100:
                        old_price = round(price / (1 - (discount / 100)), 2)
            except Exception:
                pass

    if discount < MIN_DISCOUNT or old_price <= price:
        return None

    title = ""
    for sel in ['h2 a span', 'h2 span', '.a-size-base-plus', '.a-size-medium', '.a-size-mini span',
                '._cDEzb_p13n-sc-css-line-clamp-3_g3dy1', '.p13n-sc-truncate-desktop-type2']:
        el = item.select_one(sel)
        if el and len(el.text.strip()) > 5:
            title = el.text.strip()
            break

    if not title:
        return None

    link = ""
    a = item.find('a', href=True)
    if a:
        href = a['href']
        link = f"https://www.amazon.sa{href}" if href.startswith('/') else href

    # كشف شارة "الأكثر مبيعاً" داخل نتائج البحث العادية
    try:
        badge_txt = ' '.join(b.get_text(' ', strip=True) for b in item.select('.a-badge-text, .a-badge-label, span.a-badge'))
        if re.search(r'best\s*seller|الأكثر\s*مبيع', badge_txt, re.I):
            is_best_seller = True
    except Exception:
        pass

    return {
        'title': title,
        'price': price,
        'old_price': round(old_price, 2),
        'discount': discount,
        'link': link,
        'category': category,
        'type': cat_type,
        'is_best_seller': is_best_seller,
        'id': get_product_id({'title': title, 'link': link, 'price': price})
    }

def send_deal(bot, deal, target_chat_id=None):
    global sent_products, sent_hashes

    chat_id = target_chat_id or TELEGRAM_CHAT_ID
    deal_id = deal['id']

    if is_on_cooldown(deal_id, deal['title']):
        return False

    deal_type = f"💰 {deal['discount']}%"
    if 'Warehouse' in deal['category']:
        deal_type = '🏭 WAREHOUSE'
    elif deal.get('type') == 'now_cat':
        deal_type = '⚡ AMAZON NOW'
    if deal['is_best_seller']:
        deal_type = '⭐ BEST SELLER' if deal_type.startswith('💰') else f"{deal_type} ⭐ BEST SELLER"

    savings = round(deal['old_price'] - deal['price'], 2)
    sav_txt = f"💵 توفير: {savings:.2f} ريال\n" if savings > 0 else ""
    old_txt = f"🏷️ قبل: {deal['old_price']:.2f} ريال\n" if deal['old_price'] > 0 else ""

    msg = f"""
{deal_type} *🔥 عرض جديد!*

📦 {deal['title'][:120]}

💵 *{deal['price']:.2f} ريال*
{old_txt}{sav_txt}📉 خصم: {deal['discount']}%
📍 {deal['category']}

🔗 [عرض المنتج على Amazon]({deal['link']})
    """
    try:
        try:
            bot.send_message(chat_id=chat_id, text=msg, parse_mode='Markdown')
        except Exception:
            # لو الماركداون فشل بسبب رموز في العنوان، ابعت نص عادي
            bot.send_message(chat_id=chat_id, text=msg)

        now_iso = datetime.now().isoformat()
        h = create_title_hash(deal['title'])
        sent_products.add(deal_id)
        sent_hashes.add(h)
        sent_log[deal_id] = now_iso
        hash_log[h] = now_iso
        save_database()
        export_to_excel([deal])
        logger.info(f"✅ Sent Deal: {deal['title'][:30]} - Discount: {deal['discount']}%")
        return True
    except Exception as e:
        logger.error(f"Error sending deal: {e}")
        return False

def scan_batch_and_send(bot, target_chat_id=None, limit=10):
    session = create_session()
    pages = page_rotator.get_balanced_batch(batch_size=limit)
    found_count = 0

    if not pages:
        return 0

    for page_info in pages:
        html = fetch_page(session, page_info['url'])

        if not html:
            continue

        soup = BeautifulSoup(html, 'html.parser')
        items = soup.find_all('div', {'data-component-type': 's-search-result'})
        if not items:
            items = soup.find_all('div', class_='s-result-item')
        if not items:
            items = soup.find_all('li', class_='zg-item-immersion')
        if not items:
            items = soup.select('div#gridItemRoot')

        if not items:
            low = html.lower()
            # لو مش كابتشا، يبقى القسم خلصت صفحاته؛ نتخطى الصفحات اللي بعدها
            if 'captcha' not in low and 'robot check' not in low:
                page_rotator.mark_exhausted(page_info['base_url'], page_info['page_num'])
            continue

        is_bs = page_info['type'] in BEST_TYPES

        for item in items:
            deal = parse_item(item, page_info['category'], is_bs, page_info['type'])
            if deal and is_valid_deal(deal):
                if send_deal(bot, deal, target_chat_id=target_chat_id):
                    found_count += 1

        time.sleep(random.uniform(0.5, 1.5))
    return found_count

def auto_scan_and_send(bot):
    page_rotator.generate_all_pages(CATEGORIES_DEF)

    while True:
        try:
            scan_batch_and_send(bot, limit=10)
            time.sleep(3)  # سرعة دائرية متواصلة بدون توقف طويل
        except Exception as e:
            logger.error(f"Error in auto scan loop: {e}")
            time.sleep(5)

# ========== معالجة الأوامر والرسائل النصية ==========
def start_cmd(update: Update, context: CallbackContext):
    update.message.reply_text("🤖 أهلاً بك! البوت يعمل الآن في مسح شامل وغير محدود لملايين منتجات أمازون وأمازون ناو 24/7!\n\n💬 ابعتلي أي رسالة وهبحثلك فوراً في صفحات جديدة.")

def status_cmd(update: Update, context: CallbackContext):
    stats = page_rotator.get_stats()
    update.message.reply_text(
        f"📊 *حالة الفحص المستمر:*\n\n"
        f"📦 إجمالي العروض المبعوثة: {len(sent_log)}\n"
        f"📄 إجمالي الصفحات في الدورة الواحدة: {stats['total_pages']}\n"
        f"✅ صفحات تم فحصها في الدورة الحالية: {stats['visited_pages']}\n"
        f"🔄 عدد الدورات الكاملة التي أنجزها البوت: {stats['rotation_count']}\n"
        f"📈 نسبة إنجاز الدورة الحالية: {stats['progress_percent']:.1f}%",
        parse_mode='Markdown'
    )

def clear_cmd(update: Update, context: CallbackContext):
    sent_products.clear()
    sent_hashes.clear()
    sent_log.clear()
    hash_log.clear()
    page_rotator.visited_pages.clear()
    page_rotator.dead_from.clear()
    page_rotator._refill_queues()
    save_database()
    update.message.reply_text("🗑️ تم مسح سجل الإرسال وإعادة الفحص من البداية!")

def handle_text_messages(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    update.message.reply_text("🔎 جاري المسح اللحظي في صفحات أمازون وأمازون ناو... ⏳")
    found = scan_batch_and_send(context.bot, target_chat_id=chat_id, limit=8)

    if found == 0:
        update.message.reply_text("👍 البوت يمسح باستمرار، لم يتم العثور على عروض 70%+ جديدة في الدفعة الحالية. ابعتلي تاني في أي وقت!")

def main():
    load_database()

    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=keep_alive_ping, daemon=True).start()

    updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    threading.Thread(target=auto_scan_and_send, args=(updater.bot,), daemon=True).start()

    dp.add_handler(CommandHandler("start", start_cmd))
    dp.add_handler(CommandHandler("status", status_cmd))
    dp.add_handler(CommandHandler("clear", clear_cmd))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text_messages))

    logger.info("🤖 Continuous Amazon Crawler Bot Active!")
    updater.start_polling(drop_pending_updates=True)
    updater.idle()

if __name__ == "__main__":
    main()
