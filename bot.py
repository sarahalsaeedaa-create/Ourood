import telebot
import requests
from bs4 import BeautifulSoup
import re
import random
import time
import json

TOKEN = "7956075348:AAEwHrxqtlHzew69Mu2UlxVd_1hEBq9mDeA"
bot = telebot.TeleBot(TOKEN)

# ===================================
# 🎯 جمل تسويقية سعودية عشوائية - موسعة جداً
# ===================================

OPENING_SENTENCES = [
    # 🔥 صيدات والحقو
    "والله صيدة صيدة 🎣🔥",
    "صيدة العمر هذي 💯",
    "صيدة ما تتعوض 🎯",
    "الحقو الحقو قبل يروح 🏃‍♂️💨",
    "الحقو يا جماعة الخير ⚡️",
    "صيدة ذهبية 🏆",
    "فرصة صيد نادرة 💎",
    "الحقو الفرصة ذي 👊",
    "صيدة السنة هذي 🌟",
    "ما راح تلقى زيها أبداً 🚨",
    "صيدة تاريخية 📉🔥",
    "الحقو قبل الكل 🏃‍♂️🏃‍♀️",
    "صيدة مجنونة 🤯",
    "الحقو الحقو يا شباب 💪",
    "صيدة العروض 💰",
    "فرصة صيد ما تتكرر ⏰",
    "الحقو يا ولد ⚠️",
    "صيدة فخمة 👑",
    "الحقو الكمية محدودة جداً 🔥",
    "صيدة صيدة صيدة 🎣🎣🎣",
    
    # ⏰ عروض بتروح بسرعة
    "ينتهي بأي لحظة ⏰⚡️",
    "الوقت ينفد بسرعة ⏳🔥",
    "لا تنام عليه 🚨🚨",
    "ينتهي اليوم 🌙",
    "العرض ينتهي بسرعة 💨",
    "فرصة لحظية ⚡️",
    "الحقو قبل ينتهي العرض ⏰",
    "ينتهي خلال ساعات ⏳",
    "الوقت ضيق جداً 🚨",
    "العرض محدود الوقت ⏰💥",
    "ينتهي بدون سابق إنذار ⚠️",
    "الحقو الحين 🏃‍♂️",
    "ما في وقت للتفكير 🤔❌",
    "قرر الحين أو ندم بكرة 😢",
    "العرض على وشك الانتهاء 🔥",
    "الكمية قليلة والوقت ينفد ⚡️",
    "الحقو الفرصة الأخيرة 🎯",
    "ينتهي قبل ما تلحق 🚨",
    "الوقت ما ينتظر أحد ⏳",
    "العرض يروح بسرعة البرق ⚡️",
    
    # 💥 إثارة وحماس
    "سعر خرافي صراحة 🔥🔥",
    "ما شاء الله تبارك الله السعر حلو 💥",
    "والله صفقة ما تتفوت 🎯",
    "عرض ناري وما يتكرر 🔥🔥🔥",
    "الحين أو لا 💪💪",
    "ببلاش تقريباً 😍🎉",
    "تخفيض مجنون 👌👌",
    "صفقة العمر هذي 💯🏆",
    "الكمية قليلة جداً ⚠️⚠️",
    "خذه فوراً 💨💨",
    "هاته الحين قبل يروح 🏃‍♂️💨",
    "ما راح تلقى مثله 👀👀",
    "سعر تاريخي 📉🔥",
    "فرصة لا تعوض أبداً 💎💎",
    "احجز قبل الكل 🏆🥇",
    "المنتج مطلوب جداً 🔥🔥",
    "سعر جنوني 🤯",
    "صفقة مجنونة 💥💥",
    "السعر كأنه غلطة 😂",
    "هذا سعر ولا حلم؟ 💭",
    
    # 🎯 حماس سعودي أصيل
    "يا أخي الحقو 🙏",
    "والله العظيم صفقة 👌",
    "ما راح تندم أبداً 💯",
    "ثقة في الله واشتري 🤲",
    "السعر يتكلم 🔊",
    "جودة وسعر منافس 💪",
    "تبي تنتظر زيادة السعر؟ 📈❌",
    "الحقو يا أهل الرياض 🏙️",
    "يا أهل جدة الحقو 🌊",
    "يا أهل مكة الحقو 🕋",
    "يا أهل الشرقية الحقو 🌅",
    "الحقو يا أهل السعودية 🇸🇦",
    "عرض للسعوديين الأوفياء 💚",
    "بسعر الجملة تقريباً 💰",
    "أرخص من السوق بكثير 📉",
    "توفير خرافي 💸",
    "وفر فلوسك 💵",
    "استغل الفرصة يا بطل 🦸‍♂️",
    "الحقو يا صياد 🎣",
    "صيدة الصيادين المحترفين 🏆",
    
    # 😱 فOMO (Fear Of Missing Out)
    "الكل يتكلم عنه 📢",
    "المنتج رقم 1 مبيعاً 🥇",
    "نفذ من المخزن مرتين 🔥",
    "الطلبات جاية من كل مكان 📦",
    "المنتج الأشهر الحين 🔝",
    "ترند السعودية 🇸🇦🔥",
    "الكل يبغاه 😍",
    "الكمية نفذت مرة وردت بصعوبة ⚠️",
    "المنتج اللي كله يدور عليه 👀",
    "الحقو قبل ينفذ نهائياً 🚫",
    "آخر فرصة للحصول عليه 🎯",
    "المنتج نادر في المخزون 📉",
    "نفذ سريع في المرات السابقة ⚡️",
    "الطلب مرتفع جداً 📈",
    "الحقو قبل ما ينتهي المخزون 🚨",
    
    # 💪 تحفيز وحماس
    "قرر الآن ولا تتردد ✅",
    "التردد خسارة 💸",
    "الفرصة ما تنتظر 🏃‍♂️",
    "الحقو ولا تفكر كثير 🤔❌",
    "اشتري الحين وارتح بالباقي 😌",
    "السعر ما راح ينزل أكثر 📉❌",
    "هذا أقل سعر ممكن 💯",
    "السعر الأخير 🔚",
    "ما في أرخص من كذا 👌",
    "العرض الأقوى 💪🔥",
    "صفقة القرن 🌍",
    "الحقو يا صاحبي 👊",
    "يا ولد الحقو 🏃‍♂️💨",
    "السعر يصرخ 📢🔥",
    "فرصة العمر لا تفوتها 🎯",
    "الحقو واستغل 🎣",
    "السعر يناديك 📞💰",
    "المنتج ينتظرك 🎁",
    "الحقو قبل الغيرك 🏃‍♂️🏃‍♂️",
    "السعر حقيقي ومو مزح 💯",
]

# ===================================
# 🔄 قاموس ترجمة المنتجات للعربي
# ===================================

TRANSLATION_DICT = {
    "iphone": "آيفون",
    "samsung": "سامسونج",
    "xiaomi": "شاومي",
    "huawei": "هواوي",
    "airpods": "سماعات آيربودز",
    "earbuds": "سماعات أذن",
    "headphones": "سماعات رأس",
    "laptop": "لابتوب",
    "macbook": "ماك بوك",
    "tablet": "تابلت",
    "ipad": "آيباد",
    "watch": "ساعة ذكية",
    "smartwatch": "ساعة ذكية",
    "charger": "شاحن",
    "cable": "كيبل",
    "power bank": "باور بانك",
    "battery": "بطارية",
    "screen": "شاشة",
    "monitor": "شاشة عرض",
    "keyboard": "كيبورد",
    "mouse": "ماوس",
    "camera": "كاميرا",
    "speaker": "سماعة",
    "tv": "تلفزيون",
    "television": "تلفزيون",
    "router": "راوتر",
    "modem": "مودم",
    "shoes": "حذاء",
    "shoe": "حذاء",
    "sneakers": "حذاء رياضي",
    "boots": "بوت",
    "sandals": "صندل",
    "slippers": "شبشب",
    "t-shirt": "تيشيرت",
    "shirt": "قميص",
    "pants": "بنطلون",
    "jeans": "جينز",
    "jacket": "جاكيت",
    "hoodie": "هودي",
    "dress": "فستان",
    "skirt": "تنورة",
    "socks": "شرابات",
    "cap": "كاب",
    "hat": "قبعة",
    "bag": "شنطة",
    "backpack": "حقيبة ظهر",
    "wallet": "محفظة",
    "perfume": "عطر",
    "fragrance": "عطر",
    "oud": "عود",
    "musk": "مسك",
    "cream": "كريم",
    "lotion": "لوشن",
    "shampoo": "شامبو",
    "conditioner": "بلسم",
    "soap": "صابون",
    "refrigerator": "ثلاجة",
    "fridge": "ثلاجة",
    "washing machine": "غسالة",
    "vacuum cleaner": "مكنسة كهربائية",
    "air conditioner": "مكيف",
    "ac": "مكيف",
    "heater": "دفاية",
    "fan": "مروحة",
    "blender": "خلاط",
    "mixer": "عجانة",
    "oven": "فرن",
    "microwave": "مايكرويف",
    "toaster": "محمصة",
    "kettle": "غلاية",
    "coffee maker": "ماكينة قهوة",
    "iron": "مكواة",
    "hair dryer": "سشوار",
    "chair": "كرسي",
    "table": "طاولة",
    "desk": "مكتب",
    "bed": "سرير",
    "sofa": "كنبة",
    "couch": "كنبة",
    "lamp": "لمبة",
    "light": "إضاءة",
    "mirror": "مرآة",
    "carpet": "سجادة",
    "curtain": "ستارة",
    "treadmill": "سير كهربائي",
    "dumbbell": "دامبل",
    "yoga mat": "حصيرة يوغا",
    "bicycle": "دراجة",
    "ball": "كرة",
    "toys": "ألعاب",
    "toy": "لعبة",
    "baby": "أطفال",
    "kids": "أطفال",
    "stroller": "عربة أطفال",
    "car seat": "كرسي سيارة للأطفال",
    "car": "سيارة",
    "tire": "إطار",
    "oil": "زيت",
    "cleaner": "منظف",
    "wireless": "لاسلكي",
    "bluetooth": "بلوتوث",
    "smart": "ذكي",
    "digital": "رقمي",
    "electric": "كهربائي",
    "automatic": "أوتوماتيك",
    "portable": "محمول",
    "professional": "احترافي",
    "original": "أصلي",
    "new": "جديد",
    "pro": "برو",
    "max": "ماكس",
    "plus": "بلس",
    "ultra": "ألترا",
    "mini": "ميني",
    "premium": "بريميوم",
    "deluxe": "ديلوكس",
    "unisex": "للجنسين",
    "adult": "للبالغين",
    "men": "رجالي",
    "women": "نسائي",
    "black": "أسود",
    "white": "أبيض",
    "blue": "أزرق",
    "red": "أحمر",
    "green": "أخضر",
}


def translate_to_arabic(text):
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
    words = full_title.split()
    if len(words) <= 10:
        short_title = full_title
    else:
        short_words = words[:12]
        short_title = " ".join(short_words)
    
    arabic_title = translate_to_arabic(short_title)
    
    if len(arabic_title) > 85:
        cut_point = arabic_title.rfind(' ', 50, 85)
        if cut_point == -1:
            cut_point = 80
        arabic_title = arabic_title[:cut_point] + "..."
    
    return arabic_title


# ===================================
# 🔧 دوال المساعدة
# ===================================

def expand_url(url):
    try:
        if any(short in url.lower() for short in ['amzn.to', 'bit.ly', 'tinyurl', 't.co']):
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
        r'/dp/([A-Z0-9]{10})',
        r'/gp/product/([A-Z0-9]{10})',
        r'/product/([A-Z0-9]{10})',
        r'([A-Z0-9]{10})/?$',
        r'([A-Z0-9]{10})(?:[/?]|\b)'
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


# ===================================
# 💰 تنظيف السعر - بدون نقاط ولا هللات
# ===================================

def clean_price(price_text):
    """
    ينظف السعر ويحط رقم صحيح + ريال سعودي
    مثال: 299.00 -> 299 ريال سعودي
    """
    try:
        # نستخرج الرقم (مع الفاصلة أو النقطة)
        nums = re.findall(r'[\d,]+(?:\.\d+)?', price_text)
        if nums:
            # ناخذ أول رقم ونحوله لـ float ثم int (نشيل العلامة العشرية)
            num_str = nums[0].replace(",", "")
            num_float = float(num_str)
            num_int = int(num_float)  # نشيل الهللات
            
            return f"{num_int} ريال سعودي"
    except:
        pass
    return price_text


# ===================================
# 🖼️ استخراج صورة عالية الجودة
# ===================================

def get_high_quality_image(soup):
    """
    يستخرج رابط الصورة بأعلى جودة متاحة من Amazon
    """
    image = None
    
    # محاولات متعددة للحصول على أعلى جودة
    # 1. البحث في landingImage (الصورة الرئيسية)
    img_elem = soup.select_one("#landingImage")
    if img_elem:
        # محاولة 1: data-old-hires (أعلى جودة)
        image = img_elem.get("data-old-hires")
        
        # محاولة 2: data-a-dynamic-image (JSON يحتوي على URLs متعددة)
        if not image:
            dynamic_data = img_elem.get("data-a-dynamic-image")
            if dynamic_data:
                try:
                    img_dict = json.loads(dynamic_data)
                    # نختار أكبر URL (عادة آخر واحد في القائمة)
                    if img_dict:
                        # نرتب حسب الحجم ونختار الأكبر
                        sorted_urls = sorted(img_dict.keys(), key=lambda x: img_dict[x][0] * img_dict[x][1], reverse=True)
                        image = sorted_urls[0] if sorted_urls else None
                except:
                    pass
        
        # محاولة 3: src attribute (الجودة العادية)
        if not image:
            image = img_elem.get("src")
    
    # 2. البحث في صور Gallery (أحياناً تكون أحسن)
    if not image:
        gallery_img = soup.select_one("#imgTagWrapperId img")
        if gallery_img:
            image = gallery_img.get("data-old-hires") or gallery_img.get("src")
    
    # 3. البحث في meta tags (OG image - عادة جودة عالية)
    if not image:
        og_img = soup.select_one('meta[property="og:image"]')
        if og_img:
            image = og_img.get("content")
    
    # 4. تنظيف الرابط لإزالة أي parameters تقلل الجودة
    if image:
        image = clean_image_url(image)
    
    return image


def clean_image_url(url):
    """
    ينظف رابط الصورة ويحوله لأعلى جودة ممكنة
    """
    if not url:
        return None
    
    # إزالة parameters الضغط والresize
    # Amazon يستخدم _SXxxx_SYxxx_ للتحكم في الحجم
    
    # نحول أي صورة لـ SL1500 (أعلى جودة قياسية في Amazon)
    # أو نستخدم SL1200 لو 1500 مش متاح
    
    patterns_to_remove = [
        r'_SX\d+_SY\d+_',  # أبعاد محددة
        r'_SX\d+_',        # عرض فقط
        r'_SY\d+_',        # ارتفاع فقط
        r'_CR\d+,\d+,\d+,\d+_',  # crop
        r'_AC_SL\d+_',      # anti-aliasing + dimensions
        r'_SCLZZZZZZZ_',    # zoom
        r'_FMwebp_',         # webp format
        r'_QL\d+_',          # quality level
    ]
    
    cleaned = url
    for pattern in patterns_to_remove:
        cleaned = re.sub(pattern, '_', cleaned)
    
    # نحول لـ SL1500 (أو SL1200) للحصول على أعلى جودة
    # نبحث عن .jpg أو .png في الرابط
    if '_SL' not in cleaned and 'amazon' in cleaned:
        # نضيف SL1500 قبل الامتداد
        cleaned = re.sub(r'(\.[a-zA-Z]+)(\?.*)?$', r'_SL1500\1', cleaned)
    
    # إزالة أي query parameters
    cleaned = cleaned.split('?')[0]
    
    return cleaned


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
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Cache-Control": "max-age=0",
                "Referer": "https://www.google.com/",
            }

            r = requests.get(url, headers=headers, timeout=30)
            
            if r.status_code != 200 or len(r.text) < 5000:
                continue
            
            soup = BeautifulSoup(r.text, "html.parser")
            
            title_elem = soup.select_one("#productTitle")
            if not title_elem:
                continue
            
            full_title = title_elem.text.strip()

            # السعر
            price = None
            price_selectors = [
                ".a-price.a-text-price.a-size-medium.apexPriceToPay .a-offscreen",
                ".a-price.a-text-price.apexPriceToPay .a-offscreen",
                ".a-price.aok-align-center .a-offscreen",
                ".a-price .a-offscreen",
                "[data-a-color='price'] .a-offscreen",
                ".a-price-whole"
            ]
            
            for selector in price_selectors:
                elem = soup.select_one(selector)
                if elem and elem.text:
                    price = elem.text.strip()
                    if any(c.isdigit() for c in price):
                        break

            # السعر القديم
            old_price = None
            old_selectors = [
                ".a-price.a-text-price[data-a-color='secondary'] .a-offscreen",
                ".a-price.a-text-price .a-offscreen",
                ".basisPrice .a-offscreen",
            ]
            
            for selector in old_selectors:
                elem = soup.select_one(selector)
                if elem and elem.text:
                    text = elem.text.strip()
                    if text != price and any(c.isdigit() for c in text):
                        old_price = text
                        break

            # ✅ الصورة عالية الجودة
            image = get_high_quality_image(soup)

            # الخصم
            discount_percent = None
            try:
                if old_price and price:
                    old_num = float(re.findall(r'[\d,.]+', old_price)[0].replace(",", ""))
                    new_num = float(re.findall(r'[\d,.]+', price)[0].replace(",", ""))
                    if old_num > new_num:
                        discount_percent = int(((old_num - new_num) / old_num) * 100)
            except:
                pass

            if price:
                arabic_title = smart_arabic_title(full_title)
                return arabic_title, price, old_price, image, discount_percent
                
        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            continue
    
    return None


# ===================================
# ✨ التوليد النهائي - عشوائي تماماً
# ===================================

def generate_post(product_name, price, old_price, discount_percent, original_url):
    # ✅ اختيار جملة عشوائية من القائمة الكبيرة
    opening = random.choice(OPENING_SENTENCES)
    
    # ننظف الأسعار - بدون نقاط ولا هللات
    clean_current = clean_price(price)
    clean_old = clean_price(old_price) if old_price else None
    
    lines = [opening]
    lines.append("")
    lines.append(f"🛒 {product_name}")
    lines.append("")
    
    if clean_old and discount_percent and discount_percent > 5:
        lines.append(f"❌ قبل: {clean_old}")
        lines.append(f"✅ الحين: {clean_current} (وفر {discount_percent}%)")
    else:
        lines.append(f"💰 السعر: {clean_current}")
    
    lines.append("")
    lines.append(f"🔗 {original_url}")
    
    return "\n".join(lines)


@bot.message_handler(func=lambda m: True)
def handler(msg):
    text = msg.text.strip()
    urls = re.findall(r'https?://\S+', text)

    if not urls:
        bot.reply_to(msg, "❌ أرسل رابط منتج")
        return

    for original_url in urls:
        expanded = expand_url(original_url)

        if not is_saudi_amazon(expanded):
            bot.reply_to(msg, "❌ الرابط لازم يكون من amazon.sa")
            continue

        asin = extract_asin(expanded)
        if not asin:
            bot.reply_to(msg, "❌ ما قدرت أستخرج رقم المنتج")
            continue

        wait = bot.reply_to(msg, "⏳ جاري التحليل...")

        product = get_product(asin)

        if not product:
            bot.edit_message_text("❌ ما قدرت أقرأ المنتج", msg.chat.id, wait.message_id)
            continue

        product_name, price, old_price, image, discount_percent = product
        post = generate_post(product_name, price, old_price, discount_percent, original_url)

        try:
            if image:
                bot.send_photo(msg.chat.id, image, caption=post)
            else:
                bot.send_message(msg.chat.id, post)

            bot.delete_message(msg.chat.id, wait.message_id)
        except Exception as e:
            print(f"Error sending: {e}")
            try:
                bot.send_message(msg.chat.id, post)
                bot.delete_message(msg.chat.id, wait.message_id)
            except:
                bot.edit_message_text("❌ خطأ في الإرسال", msg.chat.id, wait.message_id)


print("🤖 البوت يعمل...")
bot.infinity_polling()
