import telebot
import requests
from bs4 import BeautifulSoup
import re
import time
import json
import random

TOKEN = "7956075348:AAEYTL28GKeMN7TXyVeGM69iUcfg5ZwOSIk"
bot = telebot.TeleBot(TOKEN)

GROQ_API_KEY = "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"

BRAND_NAMES = {
    "nespresso": "Nespresso", "nescafe": "Nescafé", "nescafé": "Nescafé",
    "dolce gusto": "Dolce Gusto", "delonghi": "DeLonghi", "philips": "Philips",
    "bosch": "Bosch", "samsung": "Samsung", "apple": "Apple", "iphone": "iPhone",
    "ipad": "iPad", "macbook": "MacBook", "airpods": "AirPods", "sony": "Sony",
    "lg": "LG", "dyson": "Dyson", "braun": "Braun", "panasonic": "Panasonic",
    "canon": "Canon", "nikon": "Nikon", "xiaomi": "Xiaomi", "huawei": "Huawei",
    "oppo": "OPPO", "realme": "Realme", "oneplus": "OnePlus", "nokia": "Nokia",
    "lenovo": "Lenovo", "dell": "Dell", "hp": "HP", "asus": "ASUS", "acer": "Acer",
    "msi": "MSI", "logitech": "Logitech", "razer": "Razer", "hyperx": "HyperX",
    "jbl": "JBL", "bose": "Bose", "beats": "Beats", "sennheiser": "Sennheiser",
    "anker": "Anker", "baseus": "Baseus", "ugreen": "UGREEN", "amazon": "Amazon",
    "google": "Google", "microsoft": "Microsoft", "adidas": "Adidas", "nike": "Nike",
    "puma": "Puma", "reebok": "Reebok", "under armour": "Under Armour",
    "new balance": "New Balance", "asics": "ASICS", "timberland": "Timberland",
    "skechers": "Skechers", "crocs": "Crocs", "levis": "Levi's", "wrangler": "Wrangler",
    "tommy hilfiger": "Tommy Hilfiger", "calvin klein": "Calvin Klein", "lacoste": "Lacoste",
    "polo": "Polo", "gucci": "Gucci", "prada": "Prada", "versace": "Versace",
    "dior": "Dior", "chanel": "Chanel", "louis vuitton": "Louis Vuitton",
    "hermes": "Hermès", "burberry": "Burberry", "coach": "Coach",
    "michael kors": "Michael Kors", "fossil": "Fossil", "casio": "Casio",
    "swatch": "Swatch", "rolex": "Rolex", "omega": "Omega", "tissot": "Tissot",
    "seiko": "Seiko", "citizen": "Citizen", "orient": "Orient", "dove": "Dove",
    "nivea": "Nivea", "loreal": "L'Oréal", "pantene": "Pantene",
    "head & shoulders": "Head & Shoulders", "gillette": "Gillette",
    "oral-b": "Oral-B", "colgate": "Colgate", "signal": "Signal",
    "ariel": "Ariel", "tide": "Tide", "persil": "Persil", "downy": "Downy",
    "comfort": "Comfort", "finish": "Finish", "fa": "FA", "rexona": "Rexona",
    "axe": "AXE", "old spice": "Old Spice", "dettol": "Dettol",
    "lifebuoy": "Lifebuoy", "purell": "Purell", "kleenex": "Kleenex",
    "tork": "Tork", "tempo": "Tempo", "whisper": "Whisper", "always": "Always",
    "tampax": "Tampax", "johnson": "Johnson's", "johnsons": "Johnson's",
    "pampers": "Pampers", "huggies": "Huggies", "molfix": "Molfix",
    "fine": "Fine", "marlboro": "Marlboro", "lm": "L&M", "kent": "Kent",
    "davidoff": "Davidoff", "nesquik": "Nesquik", "kitkat": "KitKat",
    "snickers": "Snickers", "mars": "Mars", "twix": "Twix", "bounty": "Bounty",
    "milky way": "Milky Way", "galaxy": "Galaxy", "cadbury": "Cadbury",
    "lindt": "Lindt", "ferrero": "Ferrero", "nutella": "Nutella",
    "kinder": "Kinder", "oreo": "Oreo", "belvita": "Belvita", "lu": "LU",
    "tuc": "TUC", "pringles": "Pringles", "lays": "Lay's", "doritos": "Doritos",
    "cheetos": "Cheetos", "pepsi": "Pepsi", "coca cola": "Coca-Cola",
    "cocacola": "Coca-Cola", "sprite": "Sprite", "fanta": "Fanta",
    "7up": "7UP", "mirinda": "Mirinda", "mountain dew": "Mountain Dew",
    "red bull": "Red Bull", "monster": "Monster", "power horse": "Power Horse",
    "nescafe dolce gusto": "Nescafé Dolce Gusto", "dolcegusto": "Dolce Gusto",
    "vichy": "Vichy", "dercos": "Dercos", "l'oreal": "L'Oréal",
    "l'oréal": "L'Oréal", "loreal paris": "L'Oréal Paris",
    "tresemme": "TRESemmé", "guess": "Guess", "night guess": "Night Guess",
    "swiss arabian": "Swiss Arabian", "kashkha": "Kashkha",
    "ultra doux": "Ultra Doux", "honey treasures": "Honey Treasures",
    "magic retouch": "Magic Retouch", "keratin smooth": "Keratin Smooth",
    "energy": "Energy",
}


def protect_brands(text):
    for brand_key, brand_original in sorted(BRAND_NAMES.items(), key=lambda x: -len(x[0])):
        pattern = re.compile(re.escape(brand_key), re.IGNORECASE)
        text = pattern.sub(brand_original, text)
    return text


CATEGORY_KEYWORDS = {
    "electronics": ["phone", "iphone", "samsung", "laptop", "computer", "tablet", "ipad", "airpods", "headphones", "camera", "tv", "screen", "monitor", "keyboard", "mouse", "charger", "cable", "power bank", "battery", "smart watch", "watch", "speaker", "router", "modem", "electronic", "digital", "هاتف", "آيفون", "لابتوب", "كمبيوتر", "تابلت", "سماعات", "شاحن", "كيبل", "بطارية", "شاشة", "كاميرا", "تلفزيون", "راوتر", "ساعة ذكية", "إلكتروني"],
    "fashion": ["shirt", "t-shirt", "pants", "jeans", "jacket", "hoodie", "dress", "skirt", "socks", "shoes", "sneakers", "boots", "sandals", "slippers", "cap", "hat", "bag", "backpack", "wallet", "belt", "tie", "scarf", "gloves", "clothing", "apparel", "wear", "fashion", "قميص", "تيشيرت", "بنطلون", "جاكيت", "فستان", "تنورة", "حذاء", "شنطة", "حقيبة", "محفظة", "حزام", "كاب", "ملابس", "أزياء"],
    "beauty": ["perfume", "fragrance", "oud", "musk", "cream", "lotion", "shampoo", "conditioner", "soap", "makeup", "lipstick", "foundation", "mascara", "eyeliner", "brush", "cosmetic", "skincare", "haircare", "عطر", "عود", "مسك", "كريم", "شامبو", "بلسم", "صابون", "مكياج", "أحمر شفاه", "عناية", "جمال", "تجميل"],
    "home": ["refrigerator", "fridge", "washing machine", "vacuum cleaner", "air conditioner", "ac", "heater", "fan", "blender", "mixer", "oven", "microwave", "toaster", "kettle", "coffee maker", "iron", "hair dryer", "chair", "table", "desk", "bed", "sofa", "couch", "lamp", "light", "mirror", "carpet", "curtain", "furniture", "kitchen", "home", "house", "ثلاجة", "غسالة", "مكنسة", "مكيف", "دفاية", "مروحة", "خلاط", "فرن", "مايكرويف", "غلاية", "كرسي", "طاولة", "سرير", "كنبة", "لمبة", "سجادة", "أثاث", "مطبخ", "منزل"],
    "sports": ["treadmill", "dumbbell", "yoga mat", "bicycle", "ball", "gym", "fitness", "exercise", "workout", "sport", "running", "walking", "training", "sneakers", "shoes", "رياضة", "جيم", "لياقة", "تمارين", "سير", "دامبل", "يوغا", "دراجة", "كرة", "جري", "مشي", "تدريب"]
}


def detect_product_category(product_name):
    name_lower = product_name.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if keyword in name_lower:
                return category
    return "general"


def detect_product_gender(product_name):
    name_lower = product_name.lower()
    women_indicators = ['women', 'woman', 'ladies', 'lady', 'female', 'feminine', 'نسائي', 'نساء', 'نسا', 'سيدات', 'سيدة', 'انثى', 'انثوي', 'dress', 'skirt', 'فستان', 'تنورة', 'بلايز', 'فساتين', 'makeup', 'lipstick', 'شامبو', 'بلسم', 'كريم', 'عطر نسائي', 'عطر للنساء']
    men_indicators = ['men', 'man', 'male', 'masculine', 'gents', 'gentlemen', 'رجالي', 'رجال', 'رجل', 'ذكر', 'ذكوري', 'رجولة', 'عطر رجالي', 'عطر للرجال']
    for indicator in women_indicators:
        if indicator in name_lower:
            return 'women'
    for indicator in men_indicators:
        if indicator in name_lower:
            return 'men'
    return 'neutral'


TRANSLATION_DICT = {
    "laptop": "لابتوب", "tablet": "تابلت", "keyboard": "كيبورد", "mouse": "ماوس",
    "charger": "شاحن", "cable": "كيبل", "power bank": "باور بانك", "battery": "بطارية",
    "screen": "شاشة", "monitor": "شاشة عرض", "camera": "كاميرا", "speaker": "سماعة",
    "watch": "ساعة", "smartwatch": "ساعة ذكية", "headphones": "سماعات رأس",
    "router": "راوتر", "modem": "مودم", "tv": "تلفزيون", "television": "تلفزيون",
    "shoes": "حذاء", "shoe": "حذاء", "sneakers": "حذاء رياضي", "boots": "بوت",
    "sandals": "صندل", "slippers": "شبشب", "t-shirt": "تيشيرت", "shirt": "قميص",
    "pants": "بنطلون", "jeans": "جينز", "jacket": "جاكيت", "hoodie": "هودي",
    "dress": "فستان", "skirt": "تنورة", "socks": "شرابات", "cap": "كاب",
    "hat": "قبعة", "bag": "شنطة", "backpack": "حقيبة ظهر", "wallet": "محفظة",
    "belt": "حزام", "scarf": "وشاح", "gloves": "قفازات",
    "perfume": "عطر", "fragrance": "عطر", "oud": "عود", "musk": "مسك",
    "cream": "كريم", "lotion": "لوشن", "shampoo": "شامبو", "conditioner": "بلسم", "soap": "صابون",
    "refrigerator": "ثلاجة", "fridge": "ثلاجة", "washing machine": "غسالة",
    "vacuum cleaner": "مكنسة كهربائية", "air conditioner": "مكيف", "ac": "مكيف",
    "heater": "دفاية", "fan": "مروحة", "blender": "خلاط", "mixer": "عجانة",
    "oven": "فرن", "microwave": "مايكرويف", "toaster": "محمصة", "kettle": "غلاية",
    "coffee maker": "ماكينة قهوة", "iron": "مكواة", "hair dryer": "سشوار",
    "chair": "كرسي", "table": "طاولة", "desk": "مكتب", "bed": "سرير",
    "sofa": "كنبة", "couch": "كنبة", "lamp": "لمبة", "light": "إضاءة",
    "mirror": "مرآة", "carpet": "سجادة", "curtain": "ستارة",
    "treadmill": "سير كهربائي", "dumbbell": "دامبل", "yoga mat": "حصيرة يوغا",
    "bicycle": "دراجة", "ball": "كرة", "toys": "ألعاب", "toy": "لعبة",
    "baby": "أطفال", "kids": "أطفال",
    "wireless": "لاسلكي", "bluetooth": "بلوتوث", "smart": "ذكي", "digital": "رقمي",
    "electric": "كهربائي", "automatic": "أوتوماتيك", "portable": "محمول",
    "professional": "احترافي", "original": "أصلي", "new": "جديد",
    "pro": "برو", "max": "ماكس", "plus": "بلس", "ultra": "ألترا", "mini": "ميني",
    "premium": "بريميوم", "deluxe": "ديلوكس", "unisex": "للجنسين", "adult": "للبالغين",
    "men": "رجالي", "women": "نسائي",
    "black": "أسود", "white": "أبيض", "blue": "أزرق", "red": "أحمر", "green": "أخضر",
    "capsule": "كبسولة", "capsules": "كبسولات", "machine": "ماكينة", "maker": "صانع",
    "espresso": "إسبريسو", "coffee": "قهوة", "cafe": "كافيه",
    "preparation": "تحضير", "prepare": "تحضير",
    "anti": "مضاد", "anti-hair loss": "مضاد تساقط", "hair loss": "تساقط الشعر",
    "stimulating": "منشط", "stimulator": "منشط", "fortifying": "يقوي",
    "serum": "سيروم", "repair": "ترميم", "damaged": "تالف", "split ends": "نهايات متقصفة",
    "protection": "حماية", "heat": "حرارة", "spray": "بخاخ", "fixative": "مثبت",
    "keratin": "كيراتين", "smooth": "سموث", "touch": "ريتاتش", "retouch": "ريتاتش",
    "night": "نايت", "eau de toilette": "أو دي تواليت", "edt": "أو دي تواليت",
    "eau de parfum": "أو دي بارفان", "edp": "أو دي بارفان", "perfume": "عطر",
    "for men": "للرجال", "for women": "للنساء", "unisex": "للجنسين",
    "swiss": "سويسرية", "arabian": "عربية", "oriental": "شرقية",
    "honey": "هوني", "treasures": "تريجرز",
}


def translate_to_arabic(text):
    text = protect_brands(text)
    text_lower = text.lower()
    words = text_lower.split()
    translated_words = []
    for word in words:
        clean_word = re.sub(r'[^\w\s]', '', word)
        if clean_word in TRANSLATION_DICT:
            translated_words.append(TRANSLATION_DICT[clean_word])
        else:
            translated_words.append(word)
    result = " ".join(translated_words)
    result = re.sub(r'\b(\w+)\s+\1\b', r'\1', result)
    return result


def smart_arabic_title(full_title):
    full_title = protect_brands(full_title)
    arabic_title = translate_to_arabic(full_title)
    words = arabic_title.split()
    unique_words = []
    for word in words:
        if not unique_words or word.lower() != unique_words[-1].lower():
            unique_words.append(word)
    result = " ".join(unique_words)
    result = protect_brands(result)
    if len(result) > 80:
        for sep in ['،', ',', '-', '|', '/']:
            if sep in result[:80]:
                idx = result.rfind(sep, 40, 80)
                if idx > 0:
                    result = result[:idx]
                    break
        else:
            idx = result.rfind(' ', 60, 80)
            if idx > 0:
                result = result[:idx]
            else:
                result = result[:80]
    return result.strip()


def get_category_emoji(category):
    emojis = {"electronics": "📱", "fashion": "👕", "beauty": "💄", "home": "🏠", "sports": "💪"}
    return emojis.get(category, "📦")


def expand_url(url):
    try:
        if any(short in url.lower() for short in ['amzn.to', 'bit.ly', 'tinyurl', 't.co', 'ty.gl']):
            headers = {"User-Agent": "Mozilla/5.0"}
            r = requests.get(url, headers=headers, allow_redirects=True, timeout=20)
            return r.url
        return url
    except:
        return url


def is_saudi_amazon(url):
    return "amazon.sa" in url.lower()


def extract_asin(url):
    patterns = [
        r'/dp/([A-Z0-9]{10})', r'/gp/product/([A-Z0-9]{10})',
        r'/product/([A-Z0-9]{10})', r'([A-Z0-9]{10})/?$',
        r'([A-Z0-9]{10})(?:[/?]|\b)'
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


def clean_price(price_text):
    try:
        nums = re.findall(r'[\d,]+(?:.\d+)?', price_text)
        if nums:
            num_str = nums[0].replace(",", "")
            num_float = float(num_str)
            num_int = int(num_float)
            return f"{num_int} ريال"
    except:
        pass
    return price_text


def extract_number(price_text):
    try:
        nums = re.findall(r'[\d,]+(?:.\d+)?', price_text)
        if nums:
            return float(nums[0].replace(",", ""))
    except:
        pass
    return 0


def get_seller_info(soup):
    seller_name = None
    seller_rating = None
    seller_selectors = [
        "#merchant-info a",
        "[data-feature-name='merchant'] a",
        ".tabular-buybox-text[tabular-attribute-name='Merchant']",
        "#merchant-info",
    ]
    for selector in seller_selectors:
        elem = soup.select_one(selector)
        if elem:
            text = elem.get_text(strip=True)
            if text and "Amazon" not in text and len(text) > 2:
                seller_name = text
                break
    rating_elem = soup.select_one("[data-feature-name='merchant'] .a-icon-alt")
    if rating_elem:
        text = rating_elem.get_text(strip=True)
        match = re.search(r'(\d+)%', text)
        if match:
            seller_rating = int(match.group(1))
    return seller_name, seller_rating


def extract_coupon_info(text):
    if not text:
        return None, 0
    percent = 0
    percent_match = re.search(r'(\d+)%', text)
    if percent_match:
        percent = int(percent_match.group(1))
    code = None
    code_match = re.search(r'\b([A-Z]{3,}\d{2,}|\d{2,}[A-Z]{3,}|[A-Z]{4,})\b', text)
    if code_match:
        candidate = code_match.group(1)
        if len(candidate) >= 4 and len(candidate) <= 15 and re.search(r'[A-Z]', candidate):
            code = candidate
    if not code and percent > 0:
        code = f"خصم {percent}%"
    return code, percent


def get_all_coupons(soup, current_price_num):
    found_coupons = []
    selectors = [
        "#couponTextInput", "[data-feature-name='coupon']", ".couponText",
        "#couponContainer", "[id*='coupon']", ".promoPriceBlockMessage",
        "[data-a-expander-name='couponSecondaryView']", ".couponCheckbox",
        ".savingsPercentage", ".a-color-price",
    ]
    for selector in selectors:
        elems = soup.select(selector)
        for elem in elems:
            text = elem.get_text(strip=True)
            if text and len(text) > 3:
                code, percent = extract_coupon_info(text)
                if code and percent > 0:
                    final_price = int(current_price_num - (current_price_num * percent / 100))
                    found_coupons.append({
                        "code": code, "percent": percent, "final_price": final_price, "text": text
                    })
    page_text = soup.get_text()
    explicit_patterns = [
        r'(?:apply|clip|use|enter|استخدم|طبّق)\s+([A-Z0-9]{4,12})\s*(?:to save|للحصول|for)\s*(\d+)%',
        r'([A-Z]{3,}\d{2,})\s*[-–]\s*save\s*(\d+)%',
        r'([A-Z]{3,}\d{2,})\s*[-–]\s*(\d+)%\s*off',
        r'(?:promo\s*code|كود\s*الخصم|كوبون)[\s:]+([A-Z0-9]{4,12})',
    ]
    for pattern in explicit_patterns:
        matches = re.findall(pattern, page_text, re.IGNORECASE)
        for match in matches:
            if isinstance(match, tuple):
                code, percent = match[0], int(match[1]) if str(match[1]).isdigit() else 0
            else:
                code, percent = match, 0
            if code and len(code) >= 4 and percent > 0:
                final_price = int(current_price_num - (current_price_num * percent / 100))
                found_coupons.append({
                    "code": code.upper(), "percent": percent, "final_price": final_price,
                    "text": f"{code} خصم {percent}%"
                })
    seen = {}
    unique = []
    for c in found_coupons:
        key = c["code"].upper()
        if key not in seen:
            seen[key] = True
            unique.append(c)
    unique.sort(key=lambda x: x["percent"], reverse=True)
    return unique


def get_product(asin):
    url = f"https://www.amazon.sa/dp/{asin}"
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    ]
    for attempt, ua in enumerate(user_agents):
        try:
            if attempt > 0:
                time.sleep(2)
            headers = {
                "User-Agent": ua,
                "Accept-Language": "ar-SA,ar;q=0.9,en-US;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1", "Connection": "keep-alive", "Upgrade-Insecure-Requests": "1",
                "Cache-Control": "max-age=0", "Referer": "https://www.google.com/",
            }
            r = requests.get(url, headers=headers, timeout=30)
            if r.status_code != 200 or len(r.text) < 5000:
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            title_elem = soup.select_one("#productTitle")
            if not title_elem:
                continue
            full_title = title_elem.text.strip()
            price = None
            price_selectors = [
                ".a-price.a-text-price.a-size-medium.apexPriceToPay .a-offscreen",
                ".a-price.a-text-price.apexPriceToPay .a-offscreen",
                ".a-price.aok-align-center .a-offscreen", ".a-price .a-offscreen",
                "[data-a-color='price'] .a-offscreen", ".a-price-whole"
            ]
            for selector in price_selectors:
                elem = soup.select_one(selector)
                if elem and elem.text:
                    price = elem.text.strip()
                    if any(c.isdigit() for c in price):
                        break
            old_price = None
            old_selectors = [
                ".a-price.a-text-price[data-a-color='secondary'] .a-offscreen",
                ".a-price.a-text-price .a-offscreen", ".basisPrice .a-offscreen",
            ]
            for selector in old_selectors:
                elem = soup.select_one(selector)
                if elem and elem.text:
                    text = elem.text.strip()
                    if text != price and any(c.isdigit() for c in text):
                        old_price = text
                        break
            seller_name, seller_rating = get_seller_info(soup)
            current_price_num = extract_number(price) if price else 0
            all_coupons = get_all_coupons(soup, current_price_num)
            if price:
                arabic_title = smart_arabic_title(full_title)
                return {
                    "name": arabic_title, "price": price, "old_price": old_price,
                    "seller_name": seller_name, "seller_rating": seller_rating,
                    "all_coupons": all_coupons, "current_price_num": current_price_num,
                }
        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            continue
    return None


def generate_post(product_data, original_url):
    name = product_data["name"]
    price = product_data["price"]
    old_price = product_data["old_price"]
    all_coupons = product_data["all_coupons"]
    current_price_num = product_data["current_price_num"]
    category = detect_product_category(name)
    gender = detect_product_gender(name)
    clean_current = clean_price(price)
    clean_old = clean_price(old_price) if old_price else None
    old_num = extract_number(old_price) if old_price else 0
    context_parts = []
    if clean_old and old_num > current_price_num:
        context_parts.append(f"السعر السابق {clean_old} والحالي {clean_current}")
    if all_coupons:
        best = all_coupons[0]
        context_parts.append(f"كود {best['code']} خصم {best['percent']}% يصير بـ {best['final_price']} ريال")
        if len(all_coupons) > 1:
            context_parts.append(f"وفيه كوبونات ثانية")
    context = " | ".join(context_parts)
    opening = generate_ai_sentence(name, category, gender, context)
    emoji = get_category_emoji(category)
    parts = []
    parts.append(opening)
    parts.append(f"{emoji} {name}")
    price_lines = []
    if clean_old and old_num > current_price_num:
        price_lines.append(f"❌ السعر السابق: {clean_old}")
    price_lines.append(f"✅ السعر الحالي: {clean_current}")
    parts.append("\n".join(price_lines))
    if all_coupons:
        best = all_coupons[0]
        if best["final_price"] > 0 and best["final_price"] != int(current_price_num):
            parts.append(f"🎟️ مع كود {best['code']} (خصم {best['percent']}%) يطلع بـ {best['final_price']} ريال 🔥")
        elif best["percent"] > 0:
            parts.append(f"🎟️ كود {best['code']} (خصم {best['percent']}%)")
        if len(all_coupons) > 1:
            extra_lines = ["💡 عروض إضافية تخفض زيادة:"]
            for c in all_coupons[1:3]:
                extra_lines.append(f"   • كود {c['code']} (خصم {c['percent']}%)")
            parts.append("\n".join(extra_lines))
    parts.append(f"رابط الشراء 👇🏻\n{original_url}")
    return "\n\n".join(parts)


def generate_ai_sentence(product_name, category, gender, context):
    gender_hint = ""
    if gender == "women":
        gender_hint = "المنتج نسائي، وجه الجملة للبنات"
    elif gender == "men":
        gender_hint = "المنتج رجالي، وجه الجملة للرجال"
    else:
        gender_hint = "المنتج للجنسين"
    styles = [
        "افتتح بأسلوب تهويلي صاروخي (مثل: 'انفجار سعر!'، 'صدمة!'، 'مستحيل!'، 'تخيلوا!')",
        "افتتح بأسلوب صياد لقى كنز (مثل: 'غنيمة العمر!'، 'صفقة تاريخية!'، 'هجمة!'، 'صطولة!')",
        "افتتح بأسلوب مفاجأة صادمة (مثل: 'صدمووو!'، 'تبي تصدق!'، 'عقلك راح ينفجر!'، 'لا يفوتك!')",
        "افتتح بأسلوب تحدي (مثل: 'جربوا تصدقوا!'، 'أقوى صفقة!'، 'ما راح تلقى مثلها!'، 'فرصة وحيدة!')",
        "افتتح بأسلوب فزعة (مثل: 'عاجل!'، 'هيّا!'، 'بسرعة!'، 'الحين الحين!'، 'قبل ما ينتهي!')",
    ]
    chosen_style = random.choice(styles)
    prompt = f"""أنت كاتب محتوى سعودي خليجي محترف في قناة تليجرام "صيدات وصفقات" للتسويق بالعمولة.
اكتب جملة افتتاحية قصيرة جداً (سطر واحد فقط، 4-10 كلمات كحد أقصى) باللهجة السعودية الخليجية.

🔹 قواعد مهمة:
- الجملة لازم تكون مختصرة جداً (تنفع تغريدة تويتر)
- استخدم إيموجي (2-3 إيموجي) في الجملة نفسها
- الجملة لازم تكون بأسلوب تهويلي حماسي صادم يشد العين فوراً
- أسلوب التهويل: صدمة، انفجار، غنيمة، صفقة خرافية، فرصة مجنونة، توفير جنوني
- بلهجة سعودية خليجية كريمة (مثل: "يستاهل"، "فرصة"، "صفقة"، "غنيمة"، "هجمة"، "صطولة")
- ❌ ممنوع: "ياجدعان", "ياجماعة", "يالله يا شباب", "حياكم", "يالا"
- ❌ ممنوع أي أمثلة جاهزة أو نمط ثابت
- ❌ ممنوع تكرار نفس الجملة أو نفس الأسلوب
- ❌ ممنوع استخدام كلمة "صيدة" أو "لازم تشوفها"
- كل مرة اكتب جملة مختلفة تماماً بناءً على المنتج والسياق
- الأسلوب المطلوب: {chosen_style}

🔹 {gender_hint}

🔹 المنتج: {product_name}
🔹 الفئة: {category}
🔹 المعلومات المتاحة: {context}

اكتب جملة واحدة فقط بدون أي مقدمة:"""
    try:
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        data = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": "أنت كاتب محتوى سعودي خليجي في قناة 'صيدات وصفقات'. تكتب جمل افتتاحية قصيرة بأسلوب تهويلي صادم. أسلوبك: صدمة، انفجار، غنيمة، صفقة خرافية. بلهجة سعودية خليجية. كل مرة تكتب جملة مختلفة تماماً. ممنوع الأمثلة الجاهزة. ممنوع التكرار. ممنوع استخدام كلمة 'صيدة' أو 'لازم تشوفها'."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.99, "max_tokens": 40
        }
        r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=data, timeout=20)
        if r.status_code == 200:
            result = r.json()
            sentence = result["choices"][0]["message"]["content"].strip()
            sentence = sentence.replace('"', '').replace("'", "").strip()
            sentence = re.sub(r'^[ـ\s]+', '', sentence)
            vulgar_calls = ["ياجدعان", "ياجماعه", "ياجماعة", "يالله يا", "حياكم", "يالا", "يالله"]
            for vulgar in vulgar_calls:
                if vulgar in sentence.lower().replace(" ", ""):
                    return generate_fallback_sentence(category)
            return sentence
    except Exception as e:
        print(f"Groq error: {e}")
    return generate_fallback_sentence(category)


def generate_fallback_sentence(category):
    fallbacks = [
        "💥 انفجار سعر مجنون! 🔥", "🎯 غنيمة العمر وصلت! ⚡️", "💰 صفقة تاريخية بانتظارك! 🚀",
        "🔥 صدمة سعر لا تُصدق! 💎", "⚡️ فرصة مجنونة قبل تفوت! 💸", "💎 كنز ببلاش تقريباً! 🏆",
        "🚀 هجمة أسعار لا تُفوت! 🔥", "💸 توفير جنوني شفتوه! ⚡️", "🔥 مستحيل تلقى مثلها! 💰",
        "⚡️ عاجل! صفقة صطورة! 🎯",
    ]
    return random.choice(fallbacks)


# الدالة المحدثة لاستقبال ومعالجة حتى 80 رابط بدون إرسال صور
@bot.message_handler(func=lambda m: True)
def handler(msg):
    text = msg.text.strip()
    urls = re.findall(r'https?://\S+', text)

    if not urls:
        bot.reply_to(msg, "❌ يرجى إرسال روابط المنتجات")
        return

    # تحديد سقف معالجة الروابط إلى 80 رابط فقط في الرسالة الواحدة
    valid_urls = urls[:80]
    total_urls = len(valid_urls)
    
    wait = bot.reply_to(msg, f"⏳ جاري تحليل وإرسال {total_urls} منتج بدون صور...")

    processed_count = 0
    for original_url in valid_urls:
        expanded = expand_url(original_url)

        if not is_saudi_amazon(expanded):
            continue

        asin = extract_asin(expanded)
        if not asin:
            continue

        product = get_product(asin)
        if not product:
            continue

        post = generate_post(product, original_url)

        try:
            # تم حذف إرسال الصور نهائياً، الإرسال نصي فقط لتفادي قيود تليجرام وبطء التحميل
            bot.send_message(msg.chat.id, post)
            processed_count += 1
            # تأخير بسيط جداً لحماية الحساب من حظر سبام تليجرام (Flood Control)
            time.sleep(1.5)
        except Exception as e:
            print(f"Error sending text: {e}")
            time.sleep(5)  # في حال وجود ضغط على السيرفر، انتظر قليلاً ثم تابع

    try:
        bot.edit_message_text(f"✅ تم الانتهاء! تم إرسال {processed_count} من أصل {total_urls} منتج بنجاح.", msg.chat.id, wait.message_id)
    except:
        pass


# حلقة تشغيل قوية تضمن بقاء البوت حياً ويعيد تشغيل نفسه تلقائياً دون توقف 24 ساعة
if __name__ == '__main__':
    print("🤖 البوت يعمل الآن ومحمي من التوقف 24 ساعة...")
    while True:
        try:
            bot.infinity_polling(timeout=10, long_polling_timeout=5)
        except Exception as e:
            print(f"🔄 حدث خطأ في الاتصال ({e}). سيتم إعادة تشغيل البوت تلقائياً خلال 5 ثوانٍ...")
            time.sleep(5)
