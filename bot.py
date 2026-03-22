import os
import re
import json
import time
import random
import hashlib
import threading
import cloudscraper
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from telegram import Update
from telegram.ext import Updater, MessageHandler, Filters, CallbackContext

TELEGRAM_BOT_TOKEN = "8769441239:AAEgX3uBbtWc_hHcqs0lmQ50AqKJGOWV6Ok"

ua = UserAgent()
sent_hashes = set()
updater = None

# 🔥 نظام البحث المتكرر التلقائي
auto_scan_threads = {}  # {chat_id: thread}
auto_scan_status = {}  # {chat_id: bool}
SCAN_INTERVAL = 300    # 5 دقائق بين كل بحث

def load_database():
    global sent_hashes
    if os.path.exists("database.json"):
        with open("database.json", "r") as f:
            sent_hashes = set(json.load(f).get("hashes", []))

def save_database():
    with open("database.json", "w") as f:
        json.dump({"hashes": list(sent_hashes)}, f)

def create_hash(text):
    text = re.sub(r"[^\w\s]", "", text.lower())
    text = re.sub(r"\d+", "", text)
    return hashlib.md5(text[:40].encode()).hexdigest()

def create_session():
    s = cloudscraper.create_scraper()
    s.headers.update({"User-Agent": ua.random})
    return s

def fetch_page(session, url):
    try:
        r = session.get(url, timeout=20)
        if r.status_code == 200:
            return r.text
    except:
        return None

# 🔥 كلمات البحث الموسعة
def build_urls():
    keywords = [
        # Glitch + Hidden
        "price error", "pricing error", "wrong price", "glitch deal", "mistake price",
        "error deal", "bug price", "hidden deal", "secret deal", "crazy deal",
        "insane deal", "unbelievable deal", "warehouse deal", "clearance sale",
        "liquidation sale", "last chance", "final sale", "super clearance",
        "flash sale", "lightning deal", "deal of the day", "gold box deal",
        "prime deal", "exclusive deal", "members only", "early access",
        "limited time offer", "while supplies last", "almost gone", "selling fast",
        "low stock alert", "back in stock", "new arrival", "just dropped",
        "steal deal", "dirt cheap", "penny deal", "dollar deal", "under 10",
        "under 20", "under 50", "free shipping", "bundle deal", "buy one get one",
        
        # Men Clothing
        "men t shirt", "plain t shirt", "graphic t shirt", "oversized t shirt",
        "streetwear t shirt", "long sleeve shirt", "polo shirt",
        "men hoodie", "zip hoodie", "pullover hoodie", "oversized hoodie",
        "men jacket", "winter jacket", "leather jacket", "denim jacket", "bomber jacket",
        "men jeans", "slim fit jeans", "regular fit jeans", "baggy jeans", "ripped jeans",
        "cargo pants", "joggers", "track pants", "shorts men", "chino shorts",
        
        # Women Clothing
        "women dress", "summer dress", "maxi dress", "mini dress", "evening dress",
        "party dress", "cocktail dress", "abaya", "abaya women", "open abaya",
        "closed abaya", "kimono abaya", "colored abaya", "embroidered abaya",
        "hijab", "scarf", "shawl", "pashmina", "turban", "inner cap",
        "women blouse", "satin blouse", "silk blouse", "chiffon blouse",
        
        # Kids
        "kids clothes", "baby clothes", "baby outfit", "baby set", "newborn clothes",
        "kids t shirt", "kids hoodie", "kids jeans", "kids dress", "kids shirt",
        "baby pajamas", "school uniform", "kids uniform", "boys clothes",
        
        # Shoes
        "nike shoes", "adidas shoes", "puma shoes", "reebok shoes", "new balance",
        "running shoes", "walking shoes", "training shoes", "gym shoes",
        "basketball shoes", "football shoes", "tennis shoes", "cricket shoes",
        
        # Makeup
        "makeup kit", "makeup set", "makeup box", "makeup bag",
        "lipstick matte", "liquid lipstick", "lip gloss", "lip liner",
        "foundation full coverage", "foundation matte", "foundation dewy",
        
        # Skincare
        "skincare set", "face cream", "face serum", "vitamin c serum",
        "hyaluronic acid serum", "retinol cream", "retinol serum", "aha bha",
        
        # Hair
        "shampoo", "conditioner", "hair mask", "hair oil", "argan oil",
        "castor oil", "coconut oil", "olive oil", "almond oil", "jojoba oil",
        
        # Perfume
        "perfume", "men perfume", "women perfume", "unisex perfume",
        "arabic perfume", "oud perfume", "musk perfume", "amber perfume",
        
        # Phones
        "iphone", "iphone 11", "iphone 12", "iphone 13", "iphone 14", "iphone 15",
        "iphone 16", "iphone pro", "iphone pro max", "iphone plus", "iphone mini",
        "samsung galaxy", "samsung s24", "samsung s23", "samsung s22", "samsung ultra",
        
        # Accessories
        "phone case", "iphone case", "samsung case", "clear case", "shockproof case",
        "armor case", "wallet case", "leather case", "silicone case", "magnetic case",
        
        # Audio
        "earbuds", "bluetooth earbuds", "wireless earbuds", "tws earbuds",
        "airpods", "airpods pro", "airpods max", "beats headphones",
        
        # Electronics
        "laptop", "gaming laptop", "cheap laptop", "business laptop",
        "student laptop", "chromebook", "macbook", "macbook air", "macbook pro",
        
        # Gaming
        "ps5", "playstation 5", "ps5 digital", "ps5 slim", "ps5 pro",
        "ps4", "playstation 4", "xbox series x", "xbox series s",
        "nintendo switch", "switch oled", "switch lite",
        
        # Food
        "chocolate", "dark chocolate", "milk chocolate", "white chocolate",
        "snacks", "chips", "crisps", "biscuits", "cookies",
        
        # Home
        "air fryer", "air fryer oven", "deep fryer", "pressure cooker",
        "rice cooker", "slow cooker", "multi cooker", "instant pot",
        
        # Fitness
        "fitness equipment", "home gym", "gym equipment", "exercise equipment",
        "dumbbells", "adjustable dumbbells", "dumbbell set", "hex dumbbells",
        
        # Cars
        "car accessories", "car interior", "car exterior", "car care",
        "car charger", "fast car charger", "wireless car charger",
        
        # Luxury
        "luxury watch", "designer watch", "swiss watch", "automatic watch",
        "smart watch", "apple watch", "samsung watch", "garmin watch",
        
        # Viral + Trends
        "best seller", "top rated", "most popular", "amazon best seller",
        "trending now", "viral product", "tiktok made me buy it",
        "amazon choice", "amazon recommended", "frequently bought together",
        "limited stock", "low stock", "only few left", "selling out fast",
    ]

    urls = []
    for kw in keywords:
        for page in range(1, 40):  # 40 صفحة لكل كلمة
            urls.append(f"https://www.amazon.sa/s?k={kw}&page={page}")
    
    urls.append("https://www.amazon.sa/gp/todays-deals")
    urls.append("https://www.amazon.sa/gp/goldbox")
    urls.append("https://www.amazon.sa/gp/bestsellers")
    
    return urls

def parse_items(html):
    soup = BeautifulSoup(html, "html.parser")
    items = soup.find_all("div", {"data-component-type": "s-search-result"})
    deals = []

    for item in items:
        try:
            title = item.select_one("h2 span").text.strip()
            price = float(re.findall(r"\d+\.?\d*", item.select_one(".a-price .a-offscreen").text)[0])
            
            old = item.select_one(".a-text-price .a-offscreen")
            if not old:
                continue
            
            old_price = float(re.findall(r"\d+\.?\d*", old.text)[0])
            
            if old_price <= price:
                continue
            
            discount = int(((old_price - price) / old_price) * 100)
            
            rating = 0
            r = item.select_one(".a-icon-alt")
            if r:
                rating = float(re.findall(r"\d+\.?\d*", r.text)[0])
            
            link = item.select_one("a")["href"]
            if link.startswith("/"):
                link = "https://www.amazon.sa" + link
            
            img = item.select_one("img").get("src", "")
            
            deals.append({
                "title": title,
                "price": price,
                "old": old_price,
                "discount": discount,
                "rating": rating,
                "link": link,
                "img": img
            })
        except:
            pass
    
    return deals

def search_all():
    session = create_session()
    urls = build_urls()
    all_deals = []
    
    for url in urls:
        html = fetch_page(session, url)
        if not html:
            continue
        
        deals = parse_items(html)
        all_deals.extend(deals)
        time.sleep(random.uniform(0.2, 0.5))
    
    return all_deals

def filter_deals(deals):
    glitch = []
    normal = []
    new_hashes = []
    
    for d in deals:
        if d["rating"] < 3:
            continue
        
        h = create_hash(d["title"])
        
        if h in sent_hashes:
            continue
        
        new_hashes.append(h)
        
        if d["discount"] >= 90:
            glitch.append(d)
        elif d["discount"] >= 60:
            normal.append(d)
    
    # إضافة الهاشات الجديدة فقط بعد التأكد من إرسالها
    for h in new_hashes:
        sent_hashes.add(h)
    
    glitch.sort(key=lambda x: -x["discount"])
    normal.sort(key=lambda x: -x["discount"])
    
    return glitch, normal

def send_deal(chat_id, deal, updater_instance):
    msg = f"""
🔥 {deal['discount']}% OFF

{deal['title']}

💰 {deal['price']} SAR
🏷️ {deal['old']} SAR

⭐ {deal['rating']}

{deal['link']}
"""
    try:
        updater_instance.bot.send_photo(chat_id, photo=deal["img"], caption=msg)
    except:
        updater_instance.bot.send_message(chat_id, msg)

def send_group(chat_id, deals, title, updater_instance):
    if not deals:
        return 0
    
    updater_instance.bot.send_message(chat_id, f"{title} ({len(deals)} items)")
    
    count = 0
    for d in deals:
        send_deal(chat_id, d, updater_instance)
        count += 1
        time.sleep(1)
    
    return count

# 🔥 دالة البحث المتكرر التلقائي
def auto_scan_loop(chat_id, updater_instance):
    global auto_scan_status
    
    while auto_scan_status.get(chat_id, False):
        try:
            deals = search_all()
            glitch, normal = filter_deals(deals)
            
            total_sent = 0
            if glitch:
                total_sent += send_group(chat_id, glitch, "💣 GLITCH 90%+", updater_instance)
            if normal:
                total_sent += send_group(chat_id, normal, "🔥 BEST DEALS 60%+", updater_instance)
            
            if total_sent == 0:
                updater_instance.bot.send_message(chat_id, "⏳ تم البحث - لا يوجد عروض جديدة حالياً")
            else:
                updater_instance.bot.send_message(chat_id, f"✅ تم إرسال {total_sent} عرض جديد")
            
            save_database()
            
            # الانتظار 5 دقائق قبل البحث التالي
            for i in range(SCAN_INTERVAL):
                if not auto_scan_status.get(chat_id, False):
                    break
                time.sleep(1)
                
        except Exception as e:
            updater_instance.bot.send_message(chat_id, f"❌ خطأ في البحث: {str(e)}")
            time.sleep(60)  # انتظار دقيقة قبل إعادة المحاولة

def stop_auto_scan(chat_id):
    auto_scan_status[chat_id] = False
    if chat_id in auto_scan_threads:
        auto_scan_threads[chat_id].join(timeout=2)
        del auto_scan_threads[chat_id]

def start_auto_scan(chat_id, updater_instance):
    stop_auto_scan(chat_id)  # إيقاف أي بحث سابق
    auto_scan_status[chat_id] = True
    
    thread = threading.Thread(target=auto_scan_loop, args=(chat_id, updater_instance))
    thread.daemon = True
    thread.start()
    
    auto_scan_threads[chat_id] = thread

# 🔥 الأوامر الجديدة
def hi_cmd(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    
    update.message.reply_text("🔎 جاري بدء البحث المتكرر التلقائي...")
    update.message.reply_text(f"⏰ سيتم البحث كل 5 دقائق وإرسال العروض الجديدة تلقائياً")
    update.message.reply_text("🛑 لإيقاف البحث أرسل: stop")
    
    # بدء البحث المتكرر
    start_auto_scan(chat_id, updater)
    
    # البحث الأول فوراً
    threading.Thread(target=lambda: auto_scan_loop(chat_id, updater)).start()

def stop_cmd(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    stop_auto_scan(chat_id)
    update.message.reply_text("🛑 تم إيقاف البحث المتكرر التلقائي")

def status_cmd(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    status = "✅ يعمل" if auto_scan_status.get(chat_id, False) else "⛔ متوقف"
    update.message.reply_text(f"حالة البحث التلقائي: {status}")

def once_cmd(update: Update, context: CallbackContext):
    """بحث مرة واحدة فقط"""
    chat_id = update.effective_chat.id
    
    update.message.reply_text("🔎 جاري البحث لمرة واحدة... انتظر")
    
    try:
        deals = search_all()
        glitch, normal = filter_deals(deals)
        
        total_sent = 0
        if glitch:
            total_sent += send_group(chat_id, glitch, "💣 GLITCH 90%+", updater)
        if normal:
            total_sent += send_group(chat_id, normal, "🔥 BEST DEALS 60%+", updater)
        
        if total_sent == 0:
            update.message.reply_text("❌ لا يوجد عروض جديدة حالياً")
        else:
            update.message.reply_text(f"✅ تم إرسال {total_sent} عرض")
        
        save_database()
    except Exception as e:
        update.message.reply_text(f"❌ خطأ: {str(e)}")

def main():
    global updater
    
    load_database()
    
    updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    
    # الأوامر
    dp.add_handler(MessageHandler(Filters.regex(r'(?i)^hi$'), hi_cmd))
    dp.add_handler(MessageHandler(Filters.regex(r'(?i)^stop$'), stop_cmd))
    dp.add_handler(MessageHandler(Filters.regex(r'(?i)^status$'), status_cmd))
    dp.add_handler(MessageHandler(Filters.regex(r'(?i)^once$'), once_cmd))
    
    updater.start_polling()
    print("BOT STARTED - Auto Scan Mode Enabled")
    print("Commands: hi (start auto), stop (stop auto), status, once (single scan)")
    
    updater.idle()

if __name__ == "__main__":
    main()
'''

print(code)
print("\n" + "="*80)
print("✅ تم إنشاء الكود المعدل!")
print("="*80)
