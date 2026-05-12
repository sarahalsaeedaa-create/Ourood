import os
import re
import json
import logging
import cloudscraper
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from fake_useragent import UserAgent
import time
import random
import hashlib
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = "8769441239:AAEgX3uBbtWc_hHcqs0lmQ50AqKJGOWV6Ok"
PORT = int(os.environ.get("PORT", 10000))

ua = UserAgent()
sent_products = set()
sent_hashes   = set()
is_scanning   = False
updater       = None

MIN_DISCOUNT          = 40
MIN_RATING            = 3.0
TRENDING_MIN_REVIEWS  = 300
TRENDING_MIN_RATING   = 4.0

# ============================================================
# ✅ أقسام عامة واسعة = أكبر كم من العروض اليومية
# ============================================================
CATEGORIES_DEF = [

    # 🔥 DEALS الرسمية
    ("https://www.amazon.sa/gp/goldbox",                        "🔥 Goldbox",         'deals'),
    ("https://www.amazon.sa/gp/todays-deals",                   "📅 Today's Deals",   'deals'),
    ("https://www.amazon.sa/gp/prime/pipeline/lightning_deals", "⚡ Lightning Deals", 'deals'),
    ("https://www.amazon.sa/gp/warehouse-deals",                "🏭 Warehouse",       'deals'),
    ("https://www.amazon.sa/gp/coupons",                        "🎟️ Coupons",         'deals'),
    ("https://www.amazon.sa/outlet",                            "🎁 Outlet",          'deals'),

    # ⭐ BEST SELLERS
    ("https://www.amazon.sa/gp/bestsellers",             "⭐ Best Sellers الكل",       'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/electronics", "⭐ Best Sellers Electronics", 'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/beauty",      "⭐ Best Sellers Beauty",      'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/home",        "⭐ Best Sellers Home",        'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/automotive",  "⭐ Best Sellers Automotive",  'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/grocery",     "⭐ Best Sellers Grocery",     'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/fashion",     "⭐ Best Sellers Fashion",     'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/sports",      "⭐ Best Sellers Sports",      'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/toys",        "⭐ Best Sellers Toys",        'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/baby",        "⭐ Best Sellers Baby",        'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/pet",         "⭐ Best Sellers Pet",         'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/office",      "⭐ Best Sellers Office",      'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/luggage",     "⭐ Best Sellers Luggage",     'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/kitchen",     "⭐ Best Sellers Kitchen",     'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/computers",   "⭐ Best Sellers Computers",   'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/watches",     "⭐ Best Sellers Watches",     'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/shoes",       "⭐ Best Sellers Shoes",       'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/jewelry",     "⭐ Best Sellers Jewelry",     'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/health",      "⭐ Best Sellers Health",      'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/tools",       "⭐ Best Sellers Tools",       'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/garden",      "⭐ Best Sellers Garden",      'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/books",       "⭐ Best Sellers Books",       'best_sellers'),

    # 📱 ELECTRONICS
    ("https://www.amazon.sa/s?k=electronics&s=review-rank",       "📱 Electronics",      'search'),
    ("https://www.amazon.sa/s?k=smartphones&s=review-rank",       "📱 Smartphones",      'search'),
    ("https://www.amazon.sa/s?k=tablets&s=review-rank",           "📱 Tablets",          'search'),
    ("https://www.amazon.sa/s?k=laptops&s=review-rank",           "💻 Laptops",          'search'),
    ("https://www.amazon.sa/s?k=headphones&s=review-rank",        "🎧 Headphones",       'search'),
    ("https://www.amazon.sa/s?k=smartwatch&s=review-rank",        "⌚ Smartwatch",       'search'),
    ("https://www.amazon.sa/s?k=cameras&s=review-rank",           "📷 Cameras",          'search'),
    ("https://www.amazon.sa/s?k=tv+television&s=review-rank",     "📺 TV",               'search'),
    ("https://www.amazon.sa/s?k=monitor+screen&s=review-rank",    "🖥️ Monitor",          'search'),
    ("https://www.amazon.sa/s?k=router+wifi&s=review-rank",       "📡 Router WiFi",      'search'),
    ("https://www.amazon.sa/s?k=power+bank&s=review-rank",        "🔋 Power Bank",       'search'),
    ("https://www.amazon.sa/s?k=fast+charger&s=review-rank",      "🔌 Fast Charger",     'search'),
    ("https://www.amazon.sa/s?k=wireless+earbuds&s=review-rank",  "🎧 Earbuds",          'search'),
    ("https://www.amazon.sa/s?k=gaming+keyboard&s=review-rank",   "⌨️ Keyboard",         'search'),
    ("https://www.amazon.sa/s?k=gaming+mouse&s=review-rank",      "🖱️ Mouse",            'search'),
    ("https://www.amazon.sa/s?k=external+ssd&s=review-rank",      "💾 SSD",              'search'),
    ("https://www.amazon.sa/s?k=external+hard+drive&s=review-rank","💾 Hard Drive",      'search'),
    ("https://www.amazon.sa/s?k=usb+hub&s=review-rank",           "💾 USB Hub",          'search'),
    ("https://www.amazon.sa/s?k=home+projector&s=review-rank",    "📽️ Projector",        'search'),
    ("https://www.amazon.sa/s?k=printer&s=review-rank",           "🖨️ Printer",          'search'),

    # 🌸 PERFUMES & BEAUTY
    ("https://www.amazon.sa/s?k=perfume+men&s=review-rank",        "🌸 Perfume Men",      'search'),
    ("https://www.amazon.sa/s?k=perfume+women&s=review-rank",      "🌸 Perfume Women",    'search'),
    ("https://www.amazon.sa/s?k=oud+perfume&s=review-rank",        "🌸 Oud Perfume",      'search'),
    ("https://www.amazon.sa/s?k=arabic+perfume&s=review-rank",     "🌸 Arabic Perfume",   'search'),
    ("https://www.amazon.sa/s?k=face+serum&s=review-rank",         "💆 Face Serum",       'search'),
    ("https://www.amazon.sa/s?k=face+moisturizer&s=review-rank",   "💆 Moisturizer",      'search'),
    ("https://www.amazon.sa/s?k=sunscreen+spf&s=review-rank",      "💆 Sunscreen",        'search'),
    ("https://www.amazon.sa/s?k=face+wash+cleanser&s=review-rank", "💆 Face Wash",        'search'),
    ("https://www.amazon.sa/s?k=foundation+makeup&s=review-rank",  "💄 Foundation",       'search'),
    ("https://www.amazon.sa/s?k=mascara&s=review-rank",            "💄 Mascara",          'search'),
    ("https://www.amazon.sa/s?k=lipstick&s=review-rank",           "💄 Lipstick",         'search'),
    ("https://www.amazon.sa/s?k=hair+shampoo&s=review-rank",       "💆 Shampoo",          'search'),
    ("https://www.amazon.sa/s?k=hair+oil&s=review-rank",           "💆 Hair Oil",         'search'),
    ("https://www.amazon.sa/s?k=body+lotion&s=review-rank",        "🧴 Body Lotion",      'search'),
    ("https://www.amazon.sa/s?k=body+wash&s=review-rank",          "🧴 Body Wash",        'search'),
    ("https://www.amazon.sa/s?k=deodorant&s=review-rank",          "🧴 Deodorant",        'search'),
    ("https://www.amazon.sa/s?k=vitamin+c+serum&s=review-rank",    "💆 Vitamin C Serum",  'search'),
    ("https://www.amazon.sa/s?k=eye+cream&s=review-rank",          "💆 Eye Cream",        'search'),

    # 🏠 HOME & KITCHEN
    ("https://www.amazon.sa/s?k=vacuum+cleaner&s=review-rank",      "🏠 Vacuum Cleaner",   'search'),
    ("https://www.amazon.sa/s?k=robot+vacuum&s=review-rank",        "🏠 Robot Vacuum",     'search'),
    ("https://www.amazon.sa/s?k=air+fryer&s=review-rank",           "🍳 Air Fryer",        'search'),
    ("https://www.amazon.sa/s?k=coffee+machine&s=review-rank",      "☕ Coffee Machine",   'search'),
    ("https://www.amazon.sa/s?k=blender&s=review-rank",             "🍹 Blender",          'search'),
    ("https://www.amazon.sa/s?k=stand+mixer&s=review-rank",         "🍳 Stand Mixer",      'search'),
    ("https://www.amazon.sa/s?k=air+purifier&s=review-rank",        "🌬️ Air Purifier",     'search'),
    ("https://www.amazon.sa/s?k=humidifier&s=review-rank",          "🌬️ Humidifier",       'search'),
    ("https://www.amazon.sa/s?k=water+dispenser&s=review-rank",     "💧 Water Dispenser",  'search'),
    ("https://www.amazon.sa/s?k=steam+iron&s=review-rank",          "🏠 Steam Iron",       'search'),
    ("https://www.amazon.sa/s?k=nonstick+cookware&s=review-rank",   "🍳 Cookware Set",     'search'),
    ("https://www.amazon.sa/s?k=kitchen+knife+set&s=review-rank",   "🍳 Knife Set",        'search'),
    ("https://www.amazon.sa/s?k=storage+organizer&s=review-rank",   "🏠 Storage",          'search'),
    ("https://www.amazon.sa/s?k=blackout+curtains&s=review-rank",   "🏠 Curtains",         'search'),
    ("https://www.amazon.sa/s?k=bedding+set&s=review-rank",         "🛏️ Bedding Set",      'search'),
    ("https://www.amazon.sa/s?k=memory+foam+pillow&s=review-rank",  "🛏️ Pillow",           'search'),
    ("https://www.amazon.sa/s?k=mattress+topper&s=review-rank",     "🛏️ Mattress Topper",  'search'),
    ("https://www.amazon.sa/s?k=cleaning+products&s=review-rank",   "🧹 Cleaning",         'search'),
    ("https://www.amazon.sa/s?k=fabric+softener&s=review-rank",     "🧴 Fabric Softener",  'search'),
    ("https://www.amazon.sa/s?k=dishwasher+detergent&s=review-rank","🧴 Dishwasher",       'search'),

    # 🚗 AUTOMOTIVE
    ("https://www.amazon.sa/s?k=car+accessories&s=review-rank",     "🚗 Car Accessories",  'search'),
    ("https://www.amazon.sa/s?k=car+phone+holder&s=review-rank",    "🚗 Phone Holder",     'search'),
    ("https://www.amazon.sa/s?k=car+seat+cover&s=review-rank",      "🚗 Seat Cover",       'search'),
    ("https://www.amazon.sa/s?k=dash+cam&s=review-rank",            "🚗 Dash Cam",         'search'),
    ("https://www.amazon.sa/s?k=car+vacuum&s=review-rank",          "🚗 Car Vacuum",       'search'),
    ("https://www.amazon.sa/s?k=car+air+freshener&s=review-rank",   "🚗 Air Freshener",    'search'),
    ("https://www.amazon.sa/s?k=car+charger&s=review-rank",         "🚗 Car Charger",      'search'),
    ("https://www.amazon.sa/s?k=tire+inflator&s=review-rank",       "🚗 Tire Inflator",    'search'),
    ("https://www.amazon.sa/s?k=engine+oil&s=review-rank",          "🚗 Engine Oil",       'search'),
    ("https://www.amazon.sa/s?k=windshield+sun+shade&s=review-rank","🚗 Sun Shade",        'search'),

    # 👶 BABY
    ("https://www.amazon.sa/s?k=baby+diapers&s=review-rank",        "👶 Diapers",          'search'),
    ("https://www.amazon.sa/s?k=baby+wipes&s=review-rank",          "👶 Baby Wipes",       'search'),
    ("https://www.amazon.sa/s?k=baby+formula+milk&s=review-rank",   "👶 Baby Formula",     'search'),
    ("https://www.amazon.sa/s?k=baby+monitor&s=review-rank",        "👶 Baby Monitor",     'search'),
    ("https://www.amazon.sa/s?k=stroller&s=review-rank",            "👶 Stroller",         'search'),
    ("https://www.amazon.sa/s?k=baby+carrier&s=review-rank",        "👶 Baby Carrier",     'search'),
    ("https://www.amazon.sa/s?k=breast+pump&s=review-rank",         "👶 Breast Pump",      'search'),
    ("https://www.amazon.sa/s?k=baby+bottle&s=review-rank",         "👶 Baby Bottle",      'search'),
    ("https://www.amazon.sa/s?k=baby+toys&s=review-rank",           "👶 Baby Toys",        'search'),
    ("https://www.amazon.sa/s?k=baby+crib&s=review-rank",           "👶 Baby Crib",        'search'),

    # 🏋️ SPORTS
    ("https://www.amazon.sa/s?k=fitness+equipment&s=review-rank",   "🏋️ Fitness",          'search'),
    ("https://www.amazon.sa/s?k=yoga+mat&s=review-rank",            "🧘 Yoga Mat",         'search'),
    ("https://www.amazon.sa/s?k=dumbbells&s=review-rank",           "🏋️ Dumbbells",        'search'),
    ("https://www.amazon.sa/s?k=resistance+bands&s=review-rank",    "🏋️ Resistance Bands", 'search'),
    ("https://www.amazon.sa/s?k=treadmill&s=review-rank",           "🏃 Treadmill",        'search'),
    ("https://www.amazon.sa/s?k=protein+powder&s=review-rank",      "💪 Protein Powder",   'search'),
    ("https://www.amazon.sa/s?k=running+shoes&s=review-rank",       "👟 Running Shoes",    'search'),
    ("https://www.amazon.sa/s?k=gym+bag&s=review-rank",             "🎒 Gym Bag",          'search'),
    ("https://www.amazon.sa/s?k=bicycle&s=review-rank",             "🚲 Bicycle",          'search'),
    ("https://www.amazon.sa/s?k=massage+gun&s=review-rank",         "🏋️ Massage Gun",      'search'),

    # 🍚 GROCERY
    ("https://www.amazon.sa/s?k=mineral+water&s=review-rank",       "💧 Water",            'search'),
    ("https://www.amazon.sa/s?k=basmati+rice&s=review-rank",        "🍚 Rice",             'search'),
    ("https://www.amazon.sa/s?k=coffee+beans&s=review-rank",        "☕ Coffee",           'search'),
    ("https://www.amazon.sa/s?k=saudi+dates&s=review-rank",         "🍚 Dates",            'search'),
    ("https://www.amazon.sa/s?k=extra+virgin+olive+oil&s=review-rank","🫒 Olive Oil",       'search'),
    ("https://www.amazon.sa/s?k=vitamins+supplements&s=review-rank","💊 Vitamins",         'search'),
    ("https://www.amazon.sa/s?k=natural+honey&s=review-rank",       "🍯 Honey",            'search'),
    ("https://www.amazon.sa/s?k=nuts+almonds&s=review-rank",        "🥜 Nuts",             'search'),
    ("https://www.amazon.sa/s?k=arabic+tea&s=review-rank",          "🍵 Tea",              'search'),
    ("https://www.amazon.sa/s?k=protein+bars&s=review-rank",        "🍫 Protein Bars",     'search'),

    # 👗 FASHION
    ("https://www.amazon.sa/s?k=saudi+thobe&s=review-rank",         "👗 Thobe",            'search'),
    ("https://www.amazon.sa/s?k=abaya+women&s=review-rank",         "👗 Abaya",            'search'),
    ("https://www.amazon.sa/s?k=men+sneakers&s=review-rank",        "👟 Sneakers",         'search'),
    ("https://www.amazon.sa/s?k=women+heels&s=review-rank",         "👠 Heels",            'search'),
    ("https://www.amazon.sa/s?k=sunglasses&s=review-rank",          "🕶️ Sunglasses",       'search'),
    ("https://www.amazon.sa/s?k=men+leather+wallet&s=review-rank",  "👛 Wallet",           'search'),
    ("https://www.amazon.sa/s?k=women+handbag&s=review-rank",       "👜 Handbag",          'search'),
    ("https://www.amazon.sa/s?k=travel+suitcase&s=review-rank",     "🧳 Luggage",          'search'),
    ("https://www.amazon.sa/s?k=men+watch&s=review-rank",           "⌚ Watch Men",        'search'),
    ("https://www.amazon.sa/s?k=women+watch&s=review-rank",         "⌚ Watch Women",      'search'),
    ("https://www.amazon.sa/s?k=backpack&s=review-rank",            "🎒 Backpack",         'search'),
    ("https://www.amazon.sa/s?k=women+jewelry&s=review-rank",       "💍 Jewelry",          'search'),
    ("https://www.amazon.sa/s?k=men+belt&s=review-rank",            "👔 Belt",             'search'),
    ("https://www.amazon.sa/s?k=cotton+socks&s=review-rank",        "🧦 Socks",            'search'),

    # 🧸 TOYS
    ("https://www.amazon.sa/s?k=lego&s=review-rank",                "🧱 LEGO",             'search'),
    ("https://www.amazon.sa/s?k=board+games&s=review-rank",         "🎲 Board Games",      'search'),
    ("https://www.amazon.sa/s?k=remote+control+car&s=review-rank",  "🚗 RC Car",           'search'),
    ("https://www.amazon.sa/s?k=girls+dolls&s=review-rank",         "🪆 Dolls",            'search'),
    ("https://www.amazon.sa/s?k=boys+action+figures&s=review-rank", "🦸 Action Figures",   'search'),
    ("https://www.amazon.sa/s?k=educational+toys&s=review-rank",    "📚 Educational Toys", 'search'),
    ("https://www.amazon.sa/s?k=puzzle&s=review-rank",              "🧩 Puzzle",           'search'),
    ("https://www.amazon.sa/s?k=outdoor+kids+toys&s=review-rank",   "⛹️ Outdoor Toys",     'search'),

    # 🏠 SMART HOME
    ("https://www.amazon.sa/s?k=smart+home&s=review-rank",          "🏠 Smart Home",       'search'),
    ("https://www.amazon.sa/s?k=smart+led+bulb&s=review-rank",      "💡 Smart Bulb",       'search'),
    ("https://www.amazon.sa/s?k=wifi+security+camera&s=review-rank","📷 Security Camera",  'search'),
    ("https://www.amazon.sa/s?k=smart+doorbell&s=review-rank",      "🔔 Smart Doorbell",   'search'),
    ("https://www.amazon.sa/s?k=smart+plug&s=review-rank",          "🔌 Smart Plug",       'search'),
    ("https://www.amazon.sa/s?k=echo+alexa&s=review-rank",          "🔊 Echo / Alexa",     'search'),

    # 🛠️ TOOLS & GARDEN
    ("https://www.amazon.sa/s?k=power+drill+tools&s=review-rank",   "🔧 Power Tools",      'search'),
    ("https://www.amazon.sa/s?k=garden+tools&s=review-rank",        "🌱 Garden Tools",     'search'),
    ("https://www.amazon.sa/s?k=toolbox+set&s=review-rank",         "🔧 Toolbox",          'search'),
    ("https://www.amazon.sa/s?k=ladder&s=review-rank",              "🔧 Ladder",           'search'),

    # 💊 HEALTH
    ("https://www.amazon.sa/s?k=blood+pressure+monitor&s=review-rank","💊 BP Monitor",     'search'),
    ("https://www.amazon.sa/s?k=pulse+oximeter&s=review-rank",       "💊 Oximeter",        'search'),
    ("https://www.amazon.sa/s?k=digital+thermometer&s=review-rank",  "💊 Thermometer",     'search'),
    ("https://www.amazon.sa/s?k=smart+scale&s=review-rank",          "⚖️ Smart Scale",     'search'),
    ("https://www.amazon.sa/s?k=first+aid+kit&s=review-rank",        "🏥 First Aid",       'search'),

    # 📚 BOOKS & OFFICE
    ("https://www.amazon.sa/s?k=kindle+ereader&s=review-rank",       "📚 Kindle",          'search'),
    ("https://www.amazon.sa/s?k=notebook+journal&s=review-rank",     "📓 Notebook",        'search'),
    ("https://www.amazon.sa/s?k=ergonomic+office+chair&s=review-rank","🪑 Office Chair",   'search'),
    ("https://www.amazon.sa/s?k=desk+organizer&s=review-rank",       "🗂️ Desk Organizer",  'search'),
    ("https://www.amazon.sa/s?k=pens+stationery&s=review-rank",      "🖊️ Pens",            'search'),
]

trending_tracker  = {}
last_page_tracker = {cat[1]: 0 for cat in CATEGORIES_DEF}


# ================== Health Server ==================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'OK')
    def log_message(self, fmt, *args): pass

def run_health_server():
    while True:
        try:
            HTTPServer(('0.0.0.0', 8080), HealthHandler).serve_forever()
        except Exception as e:
            logger.error(f"Health: {e}")
            time.sleep(3)


# ================== Database ==================
def load_database():
    global sent_products, sent_hashes, last_page_tracker
    try:
        if os.path.exists('bot_database.json'):
            with open('bot_database.json') as f:
                data = json.load(f)
            sent_products = set(data.get('ids', []))
            sent_hashes   = set(data.get('hashes', []))
            for cat in CATEGORIES_DEF:
                if cat[1] in data.get('last_pages', {}):
                    last_page_tracker[cat[1]] = data['last_pages'][cat[1]]
            logger.info(f"📦 Loaded {len(sent_products)} products")
    except Exception as e:
        logger.error(f"DB Load: {e}")

def save_database():
    try:
        with open('bot_database.json', 'w') as f:
            json.dump({
                'ids':        list(sent_products)[-5000:],
                'hashes':     list(sent_hashes)[-5000:],
                'last_pages': last_page_tracker
            }, f)
    except Exception as e:
        logger.error(f"DB Save: {e}")


# ================== Helpers ==================
def extract_asin(link):
    if not link: return None
    for p in [r'/dp/([A-Z0-9]{10})', r'/gp/product/([A-Z0-9]{10})']:
        m = re.search(p, link, re.I)
        if m: return m.group(1).upper()
    return None

def title_hash(title):
    c = re.sub(r'[^\w\s]','', title.lower())
    c = re.sub(r'\s+',' ', c).strip()
    return hashlib.md5(c[:30].encode()).hexdigest()[:16]

def is_duplicate(title):
    return title_hash(title) in sent_hashes

def product_id(title, link, price):
    asin = extract_asin(link)
    return f"ASIN_{asin}" if asin else f"HASH_{hashlib.md5(f'{title}_{price}'.encode()).hexdigest()[:12]}"

def page_url(base, n):
    if n <= 1: return base
    if 'page=' in base: return re.sub(r'page=\d+', f'page={n}', base)
    sep = '&' if '?' in base else '?'
    return f"{base}{sep}page={n}"

def trending_score(reviews, rating, discount):
    return reviews * rating * (1 + discount / 100)


# ================== Scraper ==================
def make_session():
    s = cloudscraper.create_scraper(
        browser={'browser':'chrome','platform':'windows','desktop':True}, delay=10)
    s.headers.update({'User-Agent': ua.random,
                      'Accept-Language': 'ar-SA,ar;q=0.9',
                      'Referer': 'https://www.amazon.sa/'})
    return s

def fetch(session, url, retries=2):
    for _ in range(retries):
        try:
            time.sleep(random.uniform(1, 3))
            r = session.get(url, timeout=30)
            if r.status_code == 200 and len(r.text) > 5000:
                return r.text
            time.sleep(3)
        except Exception as e:
            logger.error(f"Fetch: {e}")
            time.sleep(3)
    return None

def parse_num(text):
    m = re.search(r'(\d+\.?\d*)', str(text))
    return float(m.group(1)) if m else 0

def parse_item(item, category, is_bs=False):
    try:
        price = None
        for sel in ['.a-price-whole','.a-price .a-offscreen','.a-price']:
            el = item.select_one(sel)
            if el:
                m = re.search(r'[\d]+\.?\d*',
                    el.text.replace(',','').replace('ريال','').replace('٬',''))
                if m:
                    price = float(m.group()); break
        if not price or price <= 0: return None

        old_price = 0; discount = 0
        old_el = item.find('span', class_='a-text-price')
        if old_el:
            m = re.search(r'[\d,]+\.?\d*',
                old_el.get_text().replace(',','').replace('٬',''))
            if m:
                try:
                    old_price = float(m.group())
                    if old_price > price:
                        discount = int(((old_price - price) / old_price) * 100)
                except: pass

        if discount == 0:
            badge = item.find(string=re.compile(r'\d+%'))
            if badge:
                m = re.search(r'(\d+)', str(badge))
                if m:
                    discount = int(m.group())
                    old_price = price / (1 - discount/100) if discount < 100 else price

        title = "Unknown"
        for sel in ['h2 a span','h2 span','.a-size-mini span',
                    '.a-size-base-plus','.a-size-medium']:
            el = item.select_one(sel)
            if el and len(el.text.strip()) > 5:
                title = el.text.strip(); break

        link = ""
        a = item.find('a', href=True)
        if a:
            h = a['href']
            if h.startswith('/'): link = f"https://www.amazon.sa{h}"
            elif 'amazon.sa' in h: link = h
            else:
                asin = extract_asin(h)
                if asin: link = f"https://www.amazon.sa/dp/{asin}"

        rating = 0
        re_el = item.find('span', class_='a-icon-alt')
        if re_el: rating = parse_num(re_el.text)

        reviews = 0
        rv_el = item.find('span', class_='a-size-base')
        if rv_el:
            m = re.search(r'[\d,]+', rv_el.text)
            if m:
                try: reviews = int(m.group().replace(',',''))
                except: pass

        return {
            'title':    title[:120],
            'price':    price,
            'old_price':round(old_price,2) if old_price > price else (round(price*100/(100-discount),2) if discount>0 else price),
            'discount': discount,
            'rating':   rating,
            'reviews':  reviews,
            'link':     link,
            'category': category,
            'score':    trending_score(reviews, rating, discount),
            'id':       product_id(title, link, price)
        }
    except:
        return None


# ================== Main Search ==================
def search_all_deals(chat_id=None, status_id=None):
    global last_page_tracker, trending_tracker
    trending_tracker = {}

    deals   = []
    session = make_session()
    cats    = list(CATEGORIES_DEF)
    random.shuffle(cats)
    page_n  = 0

    for base_url, cat_name, cat_type in cats:
        start = last_page_tracker.get(cat_name, 0) + 1

        for pg in range(start, start + 20):
            page_n += 1
            url = page_url(base_url, pg)

            if chat_id and status_id and page_n % 10 == 0:
                try:
                    updater.bot.edit_message_text(
                        chat_id=chat_id, message_id=status_id,
                        text=f"🔍 *جاري البحث...*\n\n📄 صفحات: {page_n}\n✅ عروض: {len(deals)}\n⏳ قسم: {cat_name}",
                        parse_mode='Markdown')
                except: pass

            html = fetch(session, url)
            if not html: continue

            soup  = BeautifulSoup(html, 'html.parser')
            items = []
            if cat_type == 'best_sellers':
                items += soup.find_all('li',  class_='zg-item-immersion')
                items += soup.find_all('div', class_='p13n-sc-uncoverable-faceout')
            items += soup.find_all('div', {'data-component-type':'s-search-result'})
            items += soup.find_all('div', {'data-testid':'deal-card'})
            items += soup.find_all('div', class_='s-result-item')

            if not items:
                logger.info(f"⛔ Empty [{cat_name}] p{pg}")
                break

            logger.info(f"🔍 [{cat_name}] p{pg} → {len(items)} items | deals so far: {len(deals)}")

            for item in items:
                try:
                    d = parse_item(item, cat_name, cat_type=='best_sellers')
                    if not d: continue

                    # ترندينج
                    if d['reviews'] >= TRENDING_MIN_REVIEWS and d['rating'] >= TRENDING_MIN_RATING:
                        pid = d['id']
                        if pid not in trending_tracker or d['score'] > trending_tracker[pid]['score']:
                            trending_tracker[pid] = d.copy()

                    # عروض 40%+
                    if d['discount'] >= MIN_DISCOUNT and d['rating'] >= MIN_RATING:
                        if d['id'] not in sent_products and not is_duplicate(d['title']):
                            deals.append(d)
                            logger.info(f"✅ {d['title'][:35]} | -{d['discount']}% | ⭐{d['rating']}")
                except: continue

            last_page_tracker[cat_name] = pg
            time.sleep(random.uniform(1, 2))

        if deals:
            send_deals(deals, chat_id)
            deals = []

    send_trending(chat_id)
    save_database()
    logger.info("🎯 Done!")


# ================== Send Deals ==================
def send_deals(deals, chat_id):
    if not deals: return
    super_d  = [d for d in deals if d['discount'] >= 90]
    normal_d = [d for d in deals if d['discount'] <  90]

    if super_d:
        msg = "🚨🚨🚨 *عروض خرافية 90%+* 🚨🚨🚨\n\n"
        for i, d in enumerate(super_d, 1):
            sv = d['old_price'] - d['price'] if d['old_price'] > d['price'] else 0
            msg += f"*{i}. {d['title'][:50]}*\n"
            msg += f"💰 {d['price']:.0f} ر.س ~~{d['old_price']:.0f}~~ | 🔥 -{d['discount']}% (وفّر {sv:.0f})\n"
            msg += f"⭐ {d['rating']}/5 | 💬 {d['reviews']:,}\n"
            msg += f"🔗 [اشتري]({d['link']})\n\n"
        try: updater.bot.send_message(chat_id=chat_id, text=msg, parse_mode='Markdown')
        except Exception as e: logger.error(f"Super send: {e}")
        time.sleep(1)

    if normal_d:
        msg = f"🔥 *عروض 40%+* ({len(normal_d)} منتج)\n\n"
        cnt = 0
        for i, d in enumerate(normal_d, 1):
            if d['id'] in sent_products: continue
            sv = d['old_price'] - d['price'] if d['old_price'] > d['price'] else 0
            msg += f"*{d['title'][:50]}*\n"
            msg += f"💰 {d['price']:.0f} ر.س ~~{d['old_price']:.0f}~~ | 📉 *-{d['discount']}%*"
            if sv > 0: msg += f" (وفّر {sv:.0f})"
            msg += f"\n⭐ {d['rating']}/5"
            if d['reviews'] > 0: msg += f" | 💬 {d['reviews']:,}"
            msg += f"\n🏷️ {d['category']}\n🔗 [اشتري]({d['link']})\n\n"
            cnt += 1

            if cnt % 5 == 0 or i == len(normal_d):
                try:
                    updater.bot.send_message(chat_id=chat_id, text=msg,
                        parse_mode='Markdown', disable_web_page_preview=True)
                    msg = ""
                except Exception as e: logger.error(f"Send: {e}")
                time.sleep(0.5)

            sent_products.add(d['id'])
            sent_hashes.add(title_hash(d['title']))

    for d in super_d:
        sent_products.add(d['id'])
        sent_hashes.add(title_hash(d['title']))
    save_database()


# ================== Trending Report ==================
def send_trending(chat_id):
    if not trending_tracker: return
    items = sorted(
        [v for v in trending_tracker.values() if v.get('title') and v.get('link')],
        key=lambda x: x['score'], reverse=True
    )[:25]
    if not items: return

    logger.info(f"📊 Trending report: {len(items)} products")
    msg = (
        "📊🔥 *الأكثر شراءً في السعودية الآن* 🇸🇦\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "_مرتبة: مراجعات × تقييم × خصم_\n\n"
    )

    for i, d in enumerate(items, 1):
        sv = d['old_price'] - d['price'] if d['old_price'] > d['price'] else 0
        msg += f"*{i}. {d['title'][:55]}*\n"
        msg += f"   💰 {d['price']:.0f} ر.س"
        if d['discount'] > 0: msg += f" | 📉 -{d['discount']}%"
        if sv > 0: msg += f" (وفّر {sv:.0f})"
        msg += f"\n   ⭐ {d['rating']}/5 | 💬 {d['reviews']:,} مراجعة"
        msg += f"\n   🏷️ {d['category']}\n   🔗 [تسوق]({d['link']})\n\n"

    msg += f"━━━━━━━━━━━━━━━━━━\n📈 رُصد {len(trending_tracker):,} منتج شعبي"

    def _send(text):
        try:
            updater.bot.send_message(chat_id=chat_id, text=text,
                parse_mode='Markdown', disable_web_page_preview=True)
        except Exception as e: logger.error(f"Trending: {e}")

    if len(msg) <= 4000:
        _send(msg)
    else:
        parts = msg.split('\n\n')
        chunk = ""
        for p in parts:
            if len(chunk) + len(p) + 2 < 4000: chunk += p + "\n\n"
            else:
                _send(chunk); chunk = p + "\n\n"; time.sleep(0.5)
        if chunk: _send(chunk)

    logger.info("✅ Trending sent!")


# ================== Commands ==================
def start_cmd(update: Update, context: CallbackContext):
    update.message.reply_text(
        "👋 *بوت عروض أمازون السعودية* 🇸🇦\n\n"
        "🔍 *يدور في أقسام عامة واسعة:*\n"
        "• Deals + Best Sellers (كل الكاتيجوريز)\n"
        "• Electronics, Beauty, Perfumes, Home\n"
        "• Automotive, Baby, Sports, Grocery\n"
        "• Fashion, Toys, Smart Home, Health...\n\n"
        "📊 *في نهاية كل بحث:*\n"
        "أكتر 25 منتج شراءً في السعودية\n\n"
        "اكتب *Hi* للبدء!", parse_mode='Markdown')

def hi_cmd(update: Update, context: CallbackContext):
    global is_scanning
    if is_scanning:
        update.message.reply_text("⏳ البوت شغال... استنى!")
        return
    is_scanning = True
    chat_id    = update.effective_chat.id
    status_msg = update.message.reply_text(
        "🔍 *بدأت البحث...*\n📄 بدور في كل الأقسام العامة\n"
        "⏳ *الوقت المتوقع: 10-15 دقيقة*\n\n"
        "📊 *في النهاية: أكتر 25 منتج شراءً*",
        parse_mode='Markdown')
    try:
        search_all_deals(chat_id, status_msg.message_id)
        try: updater.bot.delete_message(chat_id, status_msg.message_id)
        except: pass
        updater.bot.send_message(
            chat_id=chat_id,
            text="✅ *خلصت البحث!*\n🔥 العروض اتبعتت\n📊 تقرير الترندينج اتبعت\n\nاكتب *Hi* لبحث جديد!",
            parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error: {e}")
        update.message.reply_text(f"❌ خطأ: {str(e)[:100]}")
    finally:
        is_scanning = False

def status_cmd(update: Update, context: CallbackContext):
    update.message.reply_text(
        f"✅ *البوت شغال*\n\n"
        f"📁 أقسام: *{len(CATEGORIES_DEF)}*\n"
        f"📦 منتجات: *{len(sent_products)}*\n"
        f"📉 حد الخصم: *{MIN_DISCOUNT}%+*\n"
        f"⭐ حد التقييم: *{MIN_RATING}+*\n"
        f"💬 حد الترندينج: *{TRENDING_MIN_REVIEWS}+ مراجعة*\n\n"
        f"اكتب *Hi* للبدء!", parse_mode='Markdown')


# ================== Run ==================
def start_bot():
    global updater
    load_database()
    updater = Updater(token=TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start",  start_cmd))
    dp.add_handler(CommandHandler("status", status_cmd))
    dp.add_handler(MessageHandler(Filters.regex(r'(?i)^hi$') & Filters.text, hi_cmd))
    logger.info(f"🤖 Bot started | {len(CATEGORIES_DEF)} categories")
    updater.start_polling(drop_pending_updates=True, timeout=30)
    updater.idle()

def main():
    threading.Thread(target=run_health_server, daemon=True).start()
    time.sleep(2)
    while True:
        try:    start_bot()
        except Exception as e:
            logger.error(f"Crash: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
