import os
import re
import json
import time
import random
import hashlib
import cloudscraper
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from telegram import Update
from telegram.ext import Updater, MessageHandler, Filters, CallbackContext

TELEGRAM_BOT_TOKEN = "8769441239:AAEgX3uBbtWc_hHcqs0lmQ50AqKJGOWV6Ok"

ua = UserAgent()
updater = None
stop_search = False

# 🔥 بنية البيانات الجديدة: {hash: {"first_seen": timestamp, "last_sent": timestamp}}
sent_products = {}  # أرشيف 3 أيام
recently_sent = set()  # منتجات اليومين اللي فاتوا (ممنوع التكرار)

ARCHIVE_DAYS = 3
BLOCK_DAYS = 2

def load_database():
    global sent_products, recently_sent
    if os.path.exists("database.json"):
        try:
            with open("database.json","r") as f:
                data = json.load(f)
                sent_products = data.get("archive", {})
                
                # تنظيف الأرشيف القديم (أكبر من 3 أيام)
                now = datetime.now()
                cutoff = now - timedelta(days=ARCHIVE_DAYS)
                
                cleaned_archive = {}
                for h, info in sent_products.items():
                    try:
                        last_sent = datetime.fromisoformat(info.get("last_sent", "2000-01-01"))
                        if last_sent > cutoff:
                            cleaned_archive[h] = info
                            
                            # بناء مجموعة اليومين الممنوعين
                            block_cutoff = now - timedelta(days=BLOCK_DAYS)
                            if last_sent > block_cutoff:
                                recently_sent.add(h)
                    except:
                        pass
                
                sent_products = cleaned_archive
                print(f"📦 Loaded {len(sent_products)} products (blocked: {len(recently_sent)})")
        except Exception as e:
            print(f"Error loading DB: {e}")

def save_database():
    try:
        with open("database.json","w") as f:
            json.dump({
                "archive": sent_products,
                "last_save": datetime.now().isoformat()
            }, f, default=str)
    except Exception as e:
        print(f"Error saving DB: {e}")

def create_hash(text):
    text = re.sub(r"[^\w\s]","",text.lower())
    text = re.sub(r"\s+"," ", text).strip()
    text = re.sub(r"\d+","",text)
    # نستخدم أول 50 حرف للتمييز
    return hashlib.md5(text[:50].encode()).hexdigest()[:16]

def is_blocked(title_hash):
    """هل المنتج ممنوع (تبعت في اليومين اللي فاتوا)"""
    if title_hash in recently_sent:
        return True
    
    # نتحقق من الأرشيف
    if title_hash in sent_products:
        try:
            last_sent = datetime.fromisoformat(sent_products[title_hash].get("last_sent"))
            block_until = last_sent + timedelta(days=BLOCK_DAYS)
            if datetime.now() < block_until:
                recently_sent.add(title_hash)
                return True
        except:
            pass
    
    return False

def mark_sent(title_hash):
    """تسجيل المنتج كمنتج متبعت"""
    now = datetime.now().isoformat()
    
    if title_hash in sent_products:
        sent_products[title_hash]["last_sent"] = now
        sent_products[title_hash]["count"] = sent_products[title_hash].get("count", 0) + 1
    else:
        sent_products[title_hash] = {
            "first_seen": now,
            "last_sent": now,
            "count": 1
        }
    
    recently_sent.add(title_hash)

# 🔥 كلمات ضخمة جداً - 100 كلمة
TOP_KEYWORDS = [
    # Glitch & Deals
    "price error","glitch deal","flash sale","lightning deal","clearance sale",
    "warehouse deal","mistake price","hidden deal","secret deal","crazy deal",
    "insane deal","unbelievable deal","super clearance","final sale","last chance",
    "limited time","while supplies last","almost gone","selling fast","low stock",
    
    # Electronics
    "iphone","iphone 15","iphone 16","samsung galaxy","samsung s24","samsung s23",
    "airpods","airpods pro","macbook","macbook air","macbook pro","ipad","ipad pro",
    "laptop","gaming laptop","tablet","samsung tablet","smart watch","apple watch",
    "ps5","playstation 5","nintendo switch","xbox series x","gaming chair",
    "graphics card","rtx","gpu","monitor","gaming monitor","keyboard mechanical",
    "mouse gaming","headphones","earbuds","speaker bluetooth","webcam",
    
    # Phones Accessories
    "phone case","iphone case","charger fast","wireless charger","power bank",
    "screen protector","usb cable","adapter","phone holder car","dash cam",
    
    # Fashion Men
    "men t shirt","men hoodie","men jacket","men jeans","cargo pants","joggers",
    "men suit","men watch","men sunglasses","men belt","men wallet","men shoes",
    "sneakers","running shoes","boots men","sandals men","slippers men",
    
    # Fashion Women
    "women dress","abaya","abaya women","women hijab","women blouse",
    "women jeans","leggings","women jacket","women coat","women shoes",
    "heels","handbag","women watch","women sunglasses","women jewelry",
    "makeup kit","lipstick","foundation","perfume women","perfume arabic",
    
    # Kids
    "kids clothes","baby clothes","kids shoes","school uniform","kids dress",
    "baby toys","lego","educational toys","stuffed animal","kids backpack",
    
    # Home
    "air fryer","vacuum cleaner","robot vacuum","coffee machine","blender",
    "pressure cooker","rice cooker","microwave","oven","refrigerator",
    "washing machine","dishwasher","water dispenser","fan","air conditioner",
    "bedding set","pillow","mattress","curtains","carpet","furniture",
    "kitchen tools","dinner set","storage box","laundry basket",
    
    # Beauty
    "skincare set","face serum","vitamin c","retinol","sunscreen","hair oil",
    "shampoo","hair dryer","hair straightener","nail polish","makeup brushes",
    
    # Sports
    "yoga mat","dumbbells","treadmill","exercise bike","resistance bands",
    "protein powder","whey protein","creatine","gym gloves","sports shoes",
    
    # Food
    "chocolate","dates","coffee","honey","nuts","olive oil","spices","tea",
    
    # Car
    "car accessories","car charger","tire inflator","car vacuum","car polish",
    
    # Luxury
    "luxury watch","gold jewelry","designer bag","sunglasses luxury","oud perfume"
]

def build_massive_urls():
    """بناء URLs ضخمة - 10 صفحات لكل كلمة"""
    urls = []
    
    # 🔥 10 صفحات لكل كلمة (1000 URL)
    for kw in TOP_KEYWORDS:
        for page in range(1, 11):  # 10 صفحات
            urls.append(f"https://www.amazon.sa/s?k={kw}&page={page}")
            # إضافة ترتيب حسب الخصم
            urls.append(f"https://www.amazon.sa/s?k={kw}&page={page}&s=discount-desc-rank")
    
    # 🔥 الصفحات الرئيسية المتجددة
    base_urls = [
        "https://www.amazon.sa/gp/todays-deals",
        "https://www.amazon.sa/gp/goldbox",
        "https://www.amazon.sa/gp/bestsellers",
        "https://www.amazon.sa/gp/new-releases",
        "https://www.amazon.sa/gp/movers-and-shakers",
        "https://www.amazon.sa/gp/most-wished-for",
        "https://www.amazon.sa/gp/most-gifted",
        "https://www.amazon.sa/deals",
        "https://www.amazon.sa/gp/warehouse-deals",
        "https://www.amazon.sa/outlet",
        "https://www.amazon.sa/gp/super-savings",
        "https://www.amazon.sa/gp/price-drop",
    ]
    urls.extend(base_urls)
    
    # 🔥 أقسام متعددة
    categories = [
        "electronics", "fashion", "home", "beauty", "sports", "toys",
        "books", "automotive", "grocery", "health", "kitchen", "office",
        "pet-supplies", "baby", "tools", "industrial"
    ]
    
    for cat in categories:
        urls.append(f"https://www.amazon.sa/gp/bestsellers/{cat}")
        urls.append(f"https://www.amazon.sa/gp/new-releases/{cat}")
        urls.append(f"https://www.amazon.sa/gp/movers-and-shakers/{cat}")
        urls.append(f"https://www.amazon.sa/deals/{cat}")
        urls.append(f"https://www.amazon.sa/s?i={cat}&s=discount-desc-rank")
        
        # صفحات إضافية لكل قسم
        for page in range(1, 4):
            urls.append(f"https://www.amazon.sa/s?i={cat}&page={page}")
    
    # 🔥 عروض خاصة
    special = [
        "https://www.amazon.sa/s?k=deal+of+the+day",
        "https://www.amazon.sa/s?k=lightning+deal",
        "https://www.amazon.sa/s?k=prime+deal",
        "https://www.amazon.sa/s?k=limited+time+offer",
        "https://www.amazon.sa/s?k=flash+sale",
        "https://www.amazon.sa/s?k=clearance",
        "https://www.amazon.sa/s?k=warehouse+deal",
        "https://www.amazon.sa/s?k=open+box",
        "https://www.amazon.sa/s?k=renewed",
    ]
    urls.extend(special)
    
    # 🔥 فلاتر سعر
    for price in [10, 20, 50, 100, 200, 500]:
        urls.append(f"https://www.amazon.sa/s?k=under+{price}&s=price-asc-rank")
        urls.append(f"https://www.amazon.sa/s?k=discount+{price}&s=discount-desc-rank")
    
    # 🔥 علامات تجارية شهيرة
    brands = ["nike","adidas","apple","samsung","sony","lg","bosch","philips","dyson"]
    for brand in brands:
        for page in range(1, 4):
            urls.append(f"https://www.amazon.sa/s?k={brand}&page={page}")
    
    return list(set(urls))  # إزالة التكرار

def fetch_one(url):
    """تنفيذ طلب واحد"""
    try:
        session = cloudscraper.create_scraper()
        session.headers.update({
            "User-Agent": ua.random,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ar-SA,ar;q=0.9",
            "Referer": "https://www.amazon.sa/",
        })
        
        r = session.get(url, timeout=12)
        if r.status_code == 200:
            return r.text
    except:
        pass
    return None

def parse_items(html):
    """استخراج العروض"""
    if not html:
        return []
    
    soup = BeautifulSoup(html, "html.parser")
    items = soup.find_all("div", {"data-component-type": "s-search-result"})
    deals = []
    
    for item in items:
        try:
            # Title - محاولات متعددة
            title = None
            for sel in ["h2 a span", "h2 span", ".a-size-base-plus", ".a-size-medium", ".s-size-mini span"]:
                el = item.select_one(sel)
                if el and len(el.text.strip()) > 5:
                    title = el.text.strip()
                    break
            
            if not title:
                continue
            
            # Price
            price_el = item.select_one(".a-price .a-offscreen")
            if not price_el:
                continue
            
            price_text = price_el.text.replace(",", "").replace("ريال", "").strip()
            price_match = re.search(r"[\d,]+\.?\d*", price_text)
            if not price_match:
                continue
            price = float(price_match.group().replace(",", ""))
            
            if price <= 0:
                continue
            
            # Old Price
            old_el = item.select_one(".a-text-price .a-offscreen")
            old_price = 0
            if old_el:
                old_text = old_el.text.replace(",", "").replace("ريال", "").strip()
                old_match = re.search(r"[\d,]+\.?\d*", old_text)
                if old_match:
                    old_price = float(old_match.group().replace(",", ""))
            
            # Calculate discount
            discount = 0
            if old_price > price:
                discount = int(((old_price - price) / old_price) * 100)
            
            # Rating
            rating = 0
            r = item.select_one(".a-icon-alt")
            if r:
                r_match = re.search(r"(\d+\.?\d*)", r.text)
                if r_match:
                    rating = float(r_match.group())
            
            # Link
            a = item.find("a", href=True)
            if not a:
                continue
            
            link = a["href"]
            if link.startswith("/"):
                link = f"https://www.amazon.sa{link}"
            
            # Image
            img = ""
            img_el = item.select_one("img")
            if img_el:
                img = img_el.get("src") or img_el.get("data-src") or ""
            
            # ASIN للتأكد من عدم التكرار
            asin_match = re.search(r'/dp/([A-Z0-9]{10})', link)
            asin = asin_match.group(1) if asin_match else ""
            
            deals.append({
                "title": title,
                "price": price,
                "old": old_price,
                "discount": discount,
                "rating": rating,
                "link": link,
                "img": img,
                "asin": asin
            })
            
        except:
            continue
    
    return deals

def send_deal_now(chat_id, deal, tag):
    """إرسال عرض فوراً"""
    global updater
    
    # تقصير العنوان لو طويل
    title = deal['title']
    if len(title) > 100:
        title = title[:97] + "..."
    
    msg = f"""{tag} {deal['discount']}% OFF

{title}

💰 {deal['price']} SAR"""
    
    if deal['old'] > 0:
        msg += f" (was {deal['old']} SAR)"
    
    if deal['rating'] > 0:
        msg += f"\n⭐ {deal['rating']}/5"
    
    msg += f"\n\n{deal['link']}"
    
    try:
        if deal["img"] and deal["img"].startswith("http"):
            updater.bot.send_photo(chat_id, photo=deal["img"], caption=msg)
        else:
            updater.bot.send_message(chat_id, msg)
        return True
    except Exception as e:
        try:
            updater.bot.send_message(chat_id, msg)
            return True
        except:
            return False

def search_worker(args):
    """الـ Worker اللي بيشتغل في كل thread"""
    global stop_search, recently_sent
    
    url, chat_id = args
    
    if stop_search:
        return None
    
    html = fetch_one(url)
    if not html:
        return ("error", url, 0)
    
    deals = parse_items(html)
    sent_count = 0
    
    for d in deals:
        if stop_search:
            break
        
        # فلترة الخصم (60% أو أكتر)
        if d["discount"] < 60:
            continue
        
        # فلترة التقييم
        if 0 < d["rating"] < 3:
            continue
        
        # إنشاء hash فريد
        title_hash = create_hash(d["title"])
        asin_hash = d["asin"] if d["asin"] else ""
        
        # التحقق من التكرار (يومين)
        if is_blocked(title_hash):
            continue
        if asin_hash and is_blocked(asin_hash):
            continue
        
        # إرسال فوري
        tag = "💣 GLITCH" if d["discount"] >= 90 else "🔥 HOT"
        if send_deal_now(chat_id, d, tag):
            mark_sent(title_hash)
            if asin_hash:
                mark_sent(asin_hash)
            sent_count += 1
        
        time.sleep(0.3)  # تأخير بسيط بين الإرسال
    
    time.sleep(0.5)  # تأخير بين الطلبات
    return ("ok", url, sent_count)

def hi_cmd(update: Update, context: CallbackContext):
    global stop_search, updater, recently_sent
    stop_search = False
    
    chat_id = update.effective_chat.id
    updater = context.bot
    
    # إعادة تحميل الأرشيف عشان نتحقق من اليومين الممنوعين
    recently_sent = set()
    for h, info in sent_products.items():
        try:
            last_sent = datetime.fromisoformat(info.get("last_sent"))
            block_until = last_sent + timedelta(days=BLOCK_DAYS)
            if datetime.now() < block_until:
                recently_sent.add(h)
        except:
            pass
    
    urls = build_massive_urls()
    total = len(urls)
    
    update.message.reply_text(
        f"🚀 بدء البحث الضخم!\n"
        f"📊 {total} صفحة سيتم فحصها\n"
        f"🚫 {len(recently_sent)} منتج ممنوع (تبعت في اليومين اللي فاتوا)\n"
        f"⏳ العروض هتتبعت فوراً...\n\n"
        f"اكتب 'stop' لايقاف البحث"
    )
    
    processed = 0
    total_sent = 0
    start_time = time.time()
    
    # 🔥 8 threads للسرعة
    with ThreadPoolExecutor(max_workers=8) as executor:
        args_list = [(url, chat_id) for url in urls]
        futures = {executor.submit(search_worker, args): args for args in args_list}
        
        for future in as_completed(futures):
            if stop_search:
                try:
                    executor.shutdown(wait=False, cancel_futures=True)
                except:
                    pass
                break
            
            processed += 1
            
            try:
                result = future.result(timeout=20)
                if result:
                    status, url, count = result
                    if count > 0:
                        total_sent += count
            except:
                pass
            
            # تحديث كل 20 صفحة
            if processed % 20 == 0:
                elapsed = int(time.time() - start_time)
                try:
                    context.bot.send_message(
                        chat_id,
                        f"⏳ فحصت {processed}/{total} | ✅ بعتت {total_sent} | ⏱ {elapsed}s",
                        disable_notification=True
                    )
                except:
                    pass
    
    # حفظ الأرشيف
    save_database()
    
    elapsed = int(time.time() - start_time)
    summary = f"""
✅ {'توقف' if stop_search else 'انتهى'} البحث!

📊 النتائج:
• صفحات: {processed}/{total}
• عروض جديدة: {total_sent}
• ممنوع (يومين): {len(recently_sent)}
• أرشيف (3 أيام): {len(sent_products)}
⏱ الوقت: {elapsed} ثانية
"""
    update.message.reply_text(summary)

def stop_cmd(update: Update, context: CallbackContext):
    global stop_search
    stop_search = True
    update.message.reply_text("🛑 جاري إيقاف البحث...")

def stats_cmd(update: Update, context: CallbackContext):
    """إحصائيات الأرشيف"""
    now = datetime.now()
    
    # حساب الفئات
    today = now - timedelta(days=1)
    yesterday = now - timedelta(days=2)
    day2 = now - timedelta(days=3)
    
    today_count = 0
    yesterday_count = 0
    day2_count = 0
    older = 0
    
    for h, info in sent_products.items():
        try:
            last = datetime.fromisoformat(info.get("last_sent"))
            if last > today:
                today_count += 1
            elif last > yesterday:
                yesterday_count += 1
            elif last > day2:
                day2_count += 1
            else:
                older += 1
        except:
            pass
    
    msg = f"""
📊 إحصائيات الأرشيف (3 أيام):

📅 اليوم: {today_count}
📅 الأمس: {yesterday_count}
📅 قبل أمس: {day2_count}
🗑 قديم محذوف: {older}

🚫 محظور (يومين): {len(recently_sent)}
📦 إجمالي الأرشيف: {len(sent_products)}
"""
    update.message.reply_text(msg)

def main():
    load_database()
    
    updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    
    dp.add_handler(MessageHandler(Filters.regex(r'(?i)^hi$'), hi_cmd))
    dp.add_handler(MessageHandler(Filters.regex(r'(?i)^stop$'), stop_cmd))
    dp.add_handler(MessageHandler(Filters.regex(r'(?i)^stats$'), stats_cmd))
    
    updater.start_polling()
    print("🚀 BOT STARTED - 3 Days Archive Mode")
    updater.idle()

if __name__ == "__main__":
    main()
