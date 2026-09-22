import os
import re
import sys
import json
import html
import heapq
import time
import random
import logging
import threading
from collections import defaultdict
from datetime import datetime, timedelta
from urllib.parse import quote_plus, urljoin

import cloudscraper
import pandas as pd
from bs4 import BeautifulSoup
from flask import Flask
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== الإعدادات ====================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8769441239:AAG4sl2y2qPdvK4iPkZgyiduHNEkTpto0zM")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "432826122")

PORT = int(os.environ.get("PORT", 8080))
DB_PATH = os.getenv("DB_PATH", "bot_database.json")   # لازم يكون على تخزين دائم (Volume/Disk)

RESEND_COOLDOWN_DAYS = 7     # نفس العرض ما يتبعتش تاني قبل أسبوع
PAGE_RESCAN_HOURS = 24 * 7   # ✅ الصفحة اللي اتفحصت ما تتفحصش تاني إلا بعد أسبوع كامل
MAX_PAGES = 20               # أمازون بيوقف النتائج تقريباً بعد كده
MIN_DISCOUNT = 70            # أقل خصم
MIN_RATING = 0.0             # أقل تقييم (نجوم) عشان نضمن إن الناس بتشتريه وراضية عنه
MIN_REVIEWS = 0              # أقل عدد تقييمات

# ==================== الحالة المشتركة ====================
state_lock = threading.RLock()
excel_lock = threading.Lock()
sent_log = {}    # asin -> {"ts": iso, "count": n, "price": p}
title_log = {}   # عنوان منظف -> iso  (لمنع نفس المنتج بـ ASIN مختلف)
page_log = {}    # رابط الصفحة -> وقت آخر فحص (epoch)
dead_log = {}    # رابط القسم -> [رقم أول صفحة فاضية, وقت]
stats = defaultdict(int)


# ==================== Flask (Keep-Alive) ====================
app = Flask(__name__)


@app.route('/')
def home():
    return "Bot is running!", 200


@app.route('/health')
def health():
    return {
        "status": "ok",
        "products_sent": len(sent_log),
        "total_pages": rotator.total,
        "timestamp": datetime.now().isoformat(),
    }, 200


def run_flask():
    app.run(host='0.0.0.0', port=PORT)


def keep_alive_ping():
    while True:
        time.sleep(600)
        logger.info("💓 Keep-alive ping")


# ==================== الأقسام ====================
BASE = "https://www.amazon.sa/s?"
DISC = "rh=p_8%3A70-"
POP = "&s=exact-aware-popularity-rank"   # الأكثر مبيعاً/شعبية
REV = "&s=review-rank"                   # الأعلى تقييماً

# ملاحظة: مفيش كلمة "books/كتب" هنا، وفيه فلتر إضافي بيشيل أي كتاب يظهر في النتائج
DEPARTMENTS = [
    "electronics", "mobile-apps", "fashion", "beauty", "home", "computers", "videogames",
    "toys", "sports", "automotive", "baby-products", "office-products", "hi-tech",
    "perfumes", "watches",
]

_KEYWORDS_RAW = """
laptop,gaming laptop,tablet,iphone,samsung galaxy,smartphone,phone case,screen protector,charger,power bank,
usb cable,earbuds,headphones,bluetooth speaker,smart watch,fitness tracker,camera,action camera,drone,tv,
monitor,keyboard,mouse,gaming chair,ssd,hard drive,flash drive,memory card,router,printer,ink cartridge,
webcam,microphone,projector,playstation,xbox,nintendo switch,game controller,vr headset,smart home,
security camera,led lights,vacuum cleaner,robot vacuum,air conditioner,fan,heater,refrigerator,
washing machine,microwave,blender,coffee machine,electric kettle,toaster,rice cooker,air fryer,iron,
water dispenser,air purifier,humidifier,dishwasher,cookware,frying pan,knife set,food storage,lunch box,
thermos,mug,dinnerware,cutlery,towels,bed sheets,pillow,mattress,blanket,curtains,carpet,sofa,desk,
office chair,bookshelf,storage box,organizer,mirror,wall art,candles,lamp,light bulb,tool set,drill,
screwdriver,garden,plant pot,bbq grill,men shirt,men t-shirt,jeans,jacket,hoodie,thobe,shoes,sneakers,
sandals,boots,abaya,dress,handbag,backpack,luggage,wallet,belt,sunglasses,men watch,women watch,jewelry,
necklace,ring,earrings,socks,underwear,pajamas,sportswear,scarf,hijab,kids clothes,baby clothes,
men perfume,women perfume,oud,bakhoor,makeup,lipstick,foundation,mascara,eyeshadow,nail polish,skincare,
face cream,serum,sunscreen,hair dryer,hair straightener,hair oil,conditioner,beard trimmer,shaver,
electric toothbrush,body lotion,deodorant,shower gel,protein powder,supplements,thermometer,
blood pressure monitor,dumbbells,yoga mat,treadmill,bicycle,football,gym bag,camping,tent,fishing,
swimwear,running shoes,lego,dolls,toy cars,board games,puzzle,stroller,car seat,baby bottle,baby toys,
school bag,stationery,notebook,pens,art supplies,car accessories,car cleaning,car charger,dash cam,
tires,engine oil,seat covers,cat food,dog food,cat litter,pet toys,aquarium,
عطور,ساعات,جوالات,سماعات,شنط,أحذية,ملابس رجالية,ملابس نسائية,ملابس أطفال,مكياج,عناية بالبشرة,
أجهزة منزلية,أدوات مطبخ,مفروشات,ألعاب أطفال,هدايا,دخون,بخور,عبايات,ثياب,شماغ,نظارات,حقائب,
ديكور,إضاءة,أثاث,مستلزمات حيوانات,أدوات رياضية,دراجات,كاميرات,طابعات,شاشات,لابتوب,تابلت
"""

# ==================== Amazon Now (yalla) ====================
# بحث الكلمات على Amazon Now مش شغال — بنفحص الأقسام نفسها بدل كده
NOW_BRAND = "sAuWWBROaG"
NOW_STOREFRONT = f"https://www.amazon.sa/-/en/fmc/storefront?almBrandId={NOW_BRAND}"

# أقسام yalla المعروفة على amazon.sa (بيتم اكتشاف باقي الأقسام تلقائياً من الواجهة)
NOW_FMC_CATEGORIES = [
    ("Fruits-Vegetables", "214989746031", "🥬 Amazon Now: خضروات وفواكه"),
    ("Fresh-Fruits-Vegetables", "16895312031", "🍎 Amazon Now: طازج"),
    ("Beverages-Coffee-Tea", "16895298031", "🥤 Amazon Now: مشروبات وقهوة"),
    ("Beauty", "12462992031", "💄 Amazon Now: تجميل وعطور"),
]


def _split(raw):
    items = [k.strip() for k in raw.replace("\n", "").split(",") if k.strip()]
    return list(dict.fromkeys(items))


def build_sources():
    """يرجّع قائمة (رابط, اسم القسم, النوع) — النوع: amazon أو now"""
    sources = []
    for sort in ("", POP, REV):
        sources.append((f"{BASE}{DISC}99{sort}", "🔥 كل العروض 70%+", 'amazon'))
        for d in DEPARTMENTS:
            sources.append((f"{BASE}i={d}&{DISC}{sort}", f"🛍️ {d}", 'amazon'))
    for kw in _split(_KEYWORDS_RAW):
        q = quote_plus(kw)
        for sort in ("", POP, REV):
            sources.append((f"{BASE}k={q}&{DISC}{sort}", f"🔎 {kw}", 'amazon'))

    # ✅ Amazon Now: السوبرماركت كامل + أقسام yalla الحقيقية + واجهة الاكتشاف
    for sort in ("", POP, REV):
        sources.append((f"{BASE}i=grocery&{DISC}99{sort}", "🛒 سوبرماركت (Grocery)", 'now'))
    for slug, node, label in NOW_FMC_CATEGORIES:
        for n in range(1, 6):   # أقسام yalla محدودة الصفحات غالباً
            url = (f"https://www.amazon.sa/-/en/fmc/category/yalla/{slug}"
                   f"?almBrandId={NOW_BRAND}&node={node}" + (f"&page={n}" if n > 1 else ""))
            sources.append((url, label, 'now'))
    sources.append((NOW_STOREFRONT, "🏪 Amazon Now: الواجهة", 'now'))

    seen, out = set(), []
    for u, n, t in sources:
        if u not in seen:
            seen.add(u)
            out.append((u, n, t))
    return out


# ==================== تدوير الصفحات ====================
class PageRotator:
    """
    كل مرة بياخد الصفحات اللي ما اتفحصتش من أطول وقت (أو عمرها ما اتفحصت).
    الصفحة اللي اتفحصت في آخر أسبوع بتتخطى، فمفيش لفّ على نفس الصفحات.
    force=True بيلغي شرط الأسبوع ويرجع يفحص أقدم الصفحات (للرسائل اليدوية).
    """

    def __init__(self):
        self.pages = {'amazon': [], 'now': []}
        self.total = 0
        self._bases = set()

    def build(self, sources):
        for base_url, name, typ in sources:
            for n in range(1, MAX_PAGES + 1):
                url = base_url if n == 1 else f"{base_url}&page={n}"
                self._add(base_url, url, name, typ, n)
        self.total = sum(len(v) for v in self.pages.values())
        logger.info(f"📚 Total pages in rotation: {self.total}")

    def _add(self, base_url, url, name, typ, page_num):
        if url in self._bases:
            return False
        self._bases.add(url)
        self.pages[typ].append({
            'url': url, 'base_url': base_url, 'category': name,
            'type': typ, 'page_num': page_num,
        })
        self.total += 1
        return True

    def add_now_pages(self, base_url, name, max_pages=10):
        """إضافة قسم Amazon Now جديد اتاكتشف من الواجهة"""
        with state_lock:
            if base_url in {p['base_url'] for p in self.pages['now']}:
                return 0
            added = 0
            for n in range(1, max_pages + 1):
                url = base_url if n == 1 else f"{base_url}&page={n}"
                if self._add(base_url, url, name, 'now', n):
                    added += 1
            if added:
                logger.info(f"🆕 قسم Amazon Now جديد اتضاف: {name} ({added} صفحة)")
            return added

    def _eligible(self, p, now, force=False):
        if not force and now - page_log.get(p['url'], 0) < PAGE_RESCAN_HOURS * 3600:
            return False
        dead = dead_log.get(p['base_url'])
        if dead and p['page_num'] > dead[0] and now - dead[1] < PAGE_RESCAN_HOURS * 3600:
            return False
        return True

    def _pick(self, typ, k, now, force=False):
        if k <= 0:
            return []
        cands = (p for p in self.pages[typ] if self._eligible(p, now, force))
        picked = heapq.nsmallest(
            k, cands,
            key=lambda p: (page_log.get(p['url'], 0), p['page_num'], random.random())
        )
        for p in picked:
            page_log[p['url']] = now
        return picked

    def next_batch(self, n, force=False):
        now = time.time()
        with state_lock:
            batch = self._pick('amazon', n - n // 2, now, force) + \
                    self._pick('now', n // 2, now, force)
            missing = n - len(batch)
            for typ in ('amazon', 'now'):
                if missing > 0:
                    extra = self._pick(typ, missing, now, force)
                    batch += extra
                    missing -= len(extra)
        random.shuffle(batch)
        return batch

    def mark_exhausted(self, base_url, page_num):
        with state_lock:
            cur = dead_log.get(base_url)
            if cur is None or page_num < cur[0]:
                dead_log[base_url] = [page_num, time.time()]

    def unmark(self, url):
        with state_lock:
            page_log.pop(url, None)

    def scanned_last_24h(self):
        now = time.time()
        with state_lock:
            return sum(1 for t in page_log.values() if now - t < 86400)


rotator = PageRotator()


# ==================== قاعدة البيانات ====================
def load_database():
    global sent_log, title_log, page_log, dead_log
    try:
        if not os.path.exists(DB_PATH):
            return
        with open(DB_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        with state_lock:
            for k, v in data.get('sent_log', {}).items():
                if isinstance(v, str):   # تحويل الصيغة القديمة
                    k = k[5:] if k.startswith('ASIN_') else k
                    v = {"ts": v, "count": 1, "price": None}
                sent_log[k] = v
            title_log.update(data.get('title_log', {}))
            page_log.update(data.get('page_log', {}))
            dead_log.update(data.get('dead_log', {}))
        logger.info(f"DB loaded: {len(sent_log)} products")
    except Exception as e:
        logger.error(f"Error loading DB: {e}")


def save_database():
    try:
        with state_lock:
            # ✅ مهم جداً: نحتفظ بسجل الفحص لمدة أسبوع + يوم عشان شرط الأسبوع ما يتلغاش
            cutoff = time.time() - (PAGE_RESCAN_HOURS + 24) * 3600
            for u in [u for u, t in page_log.items() if t < cutoff]:
                del page_log[u]
            tcut = (datetime.now() - timedelta(days=RESEND_COOLDOWN_DAYS * 2)).isoformat()
            for k in [k for k, t in title_log.items() if t < tcut]:
                del title_log[k]
            data = {'sent_log': sent_log, 'title_log': title_log,
                    'page_log': page_log, 'dead_log': dead_log}
            tmp = DB_PATH + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp, DB_PATH)
    except Exception as e:
        logger.error(f"Error saving DB: {e}")


def export_to_excel(deals):
    if not deals:
        return
    try:
        with excel_lock:
            path = 'amazon_deals.xlsx'
            df_new = pd.DataFrame(deals)
            cols = ['title', 'price', 'old_price', 'discount', 'rating', 'reviews',
                    'category', 'type', 'link', 'asin']
            df_new = df_new[[c for c in cols if c in df_new.columns]]
            df_new['date_added'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            if os.path.exists(path):
                try:
                    df_new = pd.concat([pd.read_excel(path), df_new], ignore_index=True)
                except Exception:
                    pass
            df_new.to_excel(path, index=False)
    except Exception as e:
        logger.error(f"Error exporting to Excel: {e}")


# ==================== منع التكرار ====================
def title_key(title):
    t = re.sub(r'[^\w\s]', '', title.lower())
    return re.sub(r'\s+', ' ', t).strip()[:60]


def try_reserve(deal):
    """
    بيفحص ويحجز العرض في نفس اللحظة (تحت قفل) عشان ما يتبعتش مرتين.
    بيرجّع None لو العرض لسه في فترة الأسبوع، أو (الحالة, السجل القديم) لو مسموح.
    الحالة: 'new' أو 'reminder'
    """
    now = datetime.now()
    asin = deal['asin']
    tkey = title_key(deal['title'])
    cooldown = timedelta(days=RESEND_COOLDOWN_DAYS)

    with state_lock:
        rec = sent_log.get(asin)
        status = 'new'
        if rec:
            try:
                if now - datetime.fromisoformat(rec['ts']) < cooldown:
                    return None
            except Exception:
                pass
            status = 'reminder'

        ts = title_log.get(tkey)
        if ts:
            try:
                if now - datetime.fromisoformat(ts) < cooldown:
                    return None
            except Exception:
                pass

        prev = (dict(rec) if rec else None, ts)
        sent_log[asin] = {
            "ts": now.isoformat(),
            "count": (rec.get('count', 1) + 1) if rec else 1,
            "price": deal['price'],
        }
        title_log[tkey] = now.isoformat()
        return status, prev


def rollback(deal, prev):
    with state_lock:
        old_rec, old_ts = prev
        if old_rec is None:
            sent_log.pop(deal['asin'], None)
        else:
            sent_log[deal['asin']] = old_rec
        tkey = title_key(deal['title'])
        if old_ts is None:
            title_log.pop(tkey, None)
        else:
            title_log[tkey] = old_ts


# ==================== فلتر الكتب ====================
BOOK_TEXT_RE = re.compile(
    r'\b(paperback|hardcover|hardback|audiobook|audible|mass market|board book)\b'
    r'|غلاف\s*(?:ورقي|مقوى|عادي|صلب)'
    r'|(?<![\u0600-\u06FF])(?:كتاب|كتب|رواية|روايات)(?![\u0600-\u06FF])',
    re.I
)
BOOK_TITLE_RE = re.compile(r'\b(books?|novels?|textbooks?|ebooks?)\b', re.I)


def is_book(asin, title, text):
    # الكتب الورقية ASIN بتاعها رقم ISBN (بيبدأ برقم)، المنتجات العادية بتبدأ بـ B0
    if asin[0].isdigit():
        return True
    return bool(BOOK_TITLE_RE.search(title) or BOOK_TEXT_RE.search(text))


# ==================== تحليل المنتجات ====================
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫٬", "0123456789.,")


def to_num(text):
    text = (text or '').translate(_AR_DIGITS).replace(',', '')
    m = re.search(r'\d+(?:\.\d+)?', text)
    return float(m.group()) if m else None


def parse_count(text):
    t = (text or '').translate(_AR_DIGITS).lower().replace(',', '')
    m = re.search(r'(\d+(?:\.\d+)?)\s*(k|m|ك|ألف|الف|مليون)?', t)
    if not m:
        return None
    n = float(m.group(1))
    unit = m.group(2)
    if unit in ('k', 'ك', 'ألف', 'الف'):
        n *= 1000
    elif unit in ('m', 'مليون'):
        n *= 1000000
    return int(n)


def parse_rating_reviews(item):
    rating = reviews = None
    el = item.select_one('span.a-icon-alt')
    if el:
        rating = to_num(el.get_text())
    el = item.select_one('span.s-underline-text')
    if el:
        reviews = parse_count(el.get_text())
    if reviews is None:
        el = item.select_one('a[aria-label*="ratings"], a[aria-label*="تقييم"], '
                             'span[aria-label*="ratings"], span[aria-label*="تقييم"]')
        if el:
            reviews = parse_count(el.get('aria-label', ''))
    return rating, reviews


def parse_item(item, category, cat_type):
    asin = (item.get('data-asin') or '').strip().upper()
    if not re.fullmatch(r'[A-Z0-9]{10}', asin):
        return None

    title_el = item.select_one('h2')
    if not title_el:
        # ✅ صفحات Amazon Now (fmc) شكلها مختلف شوية
        title_el = item.select_one('[aria-label]') or item.select_one('img[alt]')
    if title_el:
        if title_el.name == 'img':
            title = (title_el.get('alt') or '').strip()
        elif title_el.has_attr('aria-label'):
            title = title_el.get('aria-label', '').strip()
        else:
            title = title_el.get_text(' ', strip=True)
    else:
        title = ''
    if len(title) < 5:
        return None

    # السعر الحالي
    price = None
    el = item.select_one('span.a-price:not(.a-text-price) span.a-offscreen') \
        or item.select_one('.a-price-whole')
    if el:
        price = to_num(el.get_text())
    if not price or price <= 0:
        return None

    # السعر القديم والخصم
    old_price, discount = 0, 0
    el = item.select_one('span.a-price.a-text-price span.a-offscreen') \
        or item.select_one('span.a-text-price')
    if el:
        val = to_num(el.get_text())
        if val and val > price:
            old_price = val
            discount = int((old_price - price) / old_price * 100)

    if discount == 0:
        for s in item.find_all(string=re.compile('%')):
            txt = str(s).translate(_AR_DIGITS)
            m = re.search(r'(?:-|−)\s*(\d{2})\s*%|(\d{2})\s*%\s*(?:off|خصم)|(?:خصم|off)\s*(\d{2})\s*%', txt, re.I)
            if m:
                d = int(next(g for g in m.groups() if g))
                if 0 < d < 100:
                    discount = d
                    old_price = round(price / (1 - d / 100), 2)
                    break

    if discount < MIN_DISCOUNT or old_price <= price:
        stats['skipped_low_discount'] += 1
        return None

    # الكتب: مرفوضة
    if is_book(asin, title, item.get_text(' ', strip=True)):
        stats['skipped_book'] += 1
        return None

    # الجودة: منتجات ناو الطازجة أغلبها ماعندهاش تقييمات —
    # الغياب بيتحسب 0 بدل الرفض (وده مطابق لحدود MIN_RATING=0 / MIN_REVIEWS=0)
    rating, reviews = parse_rating_reviews(item)
    rating = rating if rating is not None else 0.0
    reviews = reviews if reviews is not None else 0
    if rating < MIN_RATING or reviews < MIN_REVIEWS:
        stats['skipped_low_quality'] += 1
        return None

    return {
        'asin': asin,
        'title': title,
        'price': price,
        'old_price': round(old_price, 2),
        'discount': discount,
        'rating': rating,
        'reviews': reviews,
        'link': f"https://www.amazon.sa/dp/{asin}",
        'category': category,
        'type': cat_type,
    }


# ==================== الإرسال ====================
def build_message(deal, status, prev_rec):
    esc = html.escape
    if status == 'reminder':
        days = 7
