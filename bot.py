import os
import re
import json
import time
import random
import hashlib
import cloudscraper
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from telegram import Update
from telegram.ext import Updater, MessageHandler, Filters, CallbackContext

TELEGRAM_BOT_TOKEN = "8769441239:AAEgX3uBbtWc_hHcqs0lmQ50AqKJGOWV6Ok"

ua = UserAgent()
sent_hashes = set()
updater = None
stop_search = False

def load_database():
    global sent_hashes
    if os.path.exists("database.json"):
        with open("database.json","r") as f:
            sent_hashes = set(json.load(f).get("hashes",[]))

def save_database():
    with open("database.json","w") as f:
        json.dump({"hashes":list(sent_hashes)},f)

def create_hash(text):
    text = re.sub(r"[^\w\s]","",text.lower())
    text = re.sub(r"\d+","",text)
    return hashlib.md5(text[:40].encode()).hexdigest()

# 🔥 كلمات مختارة (50 كلمة فقط للسرعة)
TOP_KEYWORDS = [
    "price error","glitch deal","flash sale","lightning deal","clearance sale",
    "warehouse deal","best seller","top rated","amazon choice","limited time",
    "iphone","samsung galaxy","airpods","laptop","gaming laptop","ps5","nintendo switch",
    "nike shoes","adidas shoes","perfume","makeup kit","skincare set","hair oil",
    "air fryer","vacuum cleaner","coffee machine","blender","kitchen tools",
    "men t shirt","women dress","kids clothes","baby toys","lego",
    "watch","sunglasses","backpack","wallet","belt",
    "protein powder","whey protein","creatine","vitamins",
    "car accessories","dash cam","car charger","phone holder",
    "chocolate","dates","coffee","honey","nuts",
    "yoga mat","dumbbells","resistance bands","fitness equipment"
]

def build_fast_urls():
    urls = []
    
    # 🔥 3 صفحات بس لكل كلمة (150 URL)
    for kw in TOP_KEYWORDS:
        for page in range(1, 4):
            urls.append(f"https://www.amazon.sa/s?k={kw}&page={page}")
    
    # 🔥 الصفحات الرئيسية
    urls.extend([
        "https://www.amazon.sa/gp/todays-deals",
        "https://www.amazon.sa/gp/goldbox",
        "https://www.amazon.sa/gp/bestsellers",
        "https://www.amazon.sa/gp/new-releases",
        "https://www.amazon.sa/deals",
        "https://www.amazon.sa/gp/warehouse-deals",
        "https://www.amazon.sa/outlet",
        "https://www.amazon.sa/gp/most-wished-for",
        "https://www.amazon.sa/gp/most-gifted",
    ])
    
    # 🔥 أقسام العروض
    for cat in ["electronics","fashion","home","beauty","sports","toys"]:
        urls.append(f"https://www.amazon.sa/deals/{cat}")
        urls.append(f"https://www.amazon.sa/gp/bestsellers/{cat}")
    
    return urls

def fetch_one(url):
    """تنفيذ طلب واحد"""
    try:
        session = cloudscraper.create_scraper()
        session.headers.update({
            "User-Agent": ua.random,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "ar-SA,ar;q=0.9,en;q=0.8",
        })
        
        r = session.get(url, timeout=15)
        if r.status_code == 200:
            return r.text
    except Exception as e:
        pass
    return None

def parse_fast(html):
    """استخراج العروض من HTML"""
    if not html:
        return []
    
    soup = BeautifulSoup(html, "html.parser")
    items = soup.find_all("div", {"data-component-type": "s-search-result"})
    deals = []
    
    for item in items:
        try:
            # Title
            title_el = item.select_one("h2 a span, h2 span, .a-size-base-plus, .a-size-medium")
            if not title_el:
                continue
            title = title_el.text.strip()
            if len(title) < 5:
                continue
            
            # Current Price
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
            if not old_el:
                continue
            
            old_text = old_el.text.replace(",", "").replace("ريال", "").strip()
            old_match = re.search(r"[\d,]+\.?\d*", old_text)
            if not old_match:
                continue
            old_price = float(old_match.group().replace(",", ""))
            
            if old_price <= price:
                continue
            
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
                img = img_el.get("src", "") or img_el.get("data-src", "")
            
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
            continue
    
    return deals

def send_deal_now(chat_id, deal, tag):
    """إرسال عرض فوراً"""
    global updater
    
    msg = f"""
{tag} {deal['discount']}% OFF

{deal['title'][:100]}{'...' if len(deal['title']) > 100 else ''}

💰 {deal['price']} SAR (was {deal['old']} SAR)
⭐ {deal['rating'] if deal['rating'] else 'No rating'}

{deal['link']}
"""
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
    """الدالة اللي بتشتغل في كل thread"""
    global stop_search
    
    url, chat_id = args
    
    if stop_search:
        return None
    
    html = fetch_one(url)
    if not html:
        return ("error", url)
    
    deals = parse_fast(html)
    results = []
    
    for d in deals:
        if stop_search:
            break
        
        # فلترة
        if d["rating"] < 3 and d["rating"] > 0:
            continue
        
        h = create_hash(d["title"])
        if h in sent_hashes:
            continue
        
        sent_hashes.add(h)
        
        # إرسال فوري
        if d["discount"] >= 90:
            send_deal_now(chat_id, d, "💣 GLITCH")
            results.append("glitch")
        elif d["discount"] >= 60:
            send_deal_now(chat_id, d, "🔥 HOT")
            results.append("hot")
    
    time.sleep(0.5)  # تأخير بسيط
    return ("ok", len(results))

def hi_cmd(update: Update, context: CallbackContext):
    global stop_search, updater
    stop_search = False
    
    chat_id = update.effective_chat.id
    updater = context.bot
    
    urls = build_fast_urls()
    total = len(urls)
    
    update.message.reply_text(f"🚀 بدء البحث السريع في {total} صفحة...\n⏳ كل عرض هيتبعت فوراً لما نلاقيه\n\nاكتب 'stop' لايقاف البحث")
    
    glitch_count = 0
    hot_count = 0
    processed = 0
    
    # 🔥 ThreadPool - 5 طلبات في نفس الوقت
    with ThreadPoolExecutor(max_workers=5) as executor:
        # إعداد الـ args لكل URL
        args_list = [(url, chat_id) for url in urls]
        
        # تنفيذ متزامن
        futures = {executor.submit(search_worker, args): args for args in args_list}
        
        for future in as_completed(futures):
            if stop_search:
                executor.shutdown(wait=False)
                break
            
            processed += 1
            
            try:
                result = future.result(timeout=20)
                if result:
                    status, data = result
                    if status == "ok" and data > 0:
                        # تحديث العداد
                        pass
            except Exception as e:
                pass
            
            # تحديث كل 10 صفحات
            if processed % 10 == 0:
                try:
                    context.bot.send_message(
                        chat_id,
                        f"⏳ تم فحص {processed}/{total} صفحة...",
                        disable_notification=True
                    )
                except:
                    pass
    
    # ملخص نهائي
    summary = f"""
✅ {'توقف' if stop_search else 'انتهى'} البحث!

📊 الإحصائيات:
• صفحات مفحوصة: {processed}/{total}
• عروض Glitch (90%+): تم إرسالها فوراً
• عروض Hot (60%+): تم إرسالها فوراً

💡 النتائج اتبعتت فوراً لما اتلاقت!
"""
    update.message.reply_text(summary)
    save_database()

def stop_cmd(update: Update, context: CallbackContext):
    global stop_search
    stop_search = True
    update.message.reply_text("🛑 جاري إيقاف البحث...")

def main():
    load_database()
    
    updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    
    dp.add_handler(MessageHandler(Filters.regex(r'(?i)^hi$'), hi_cmd))
    dp.add_handler(MessageHandler(Filters.regex(r'(?i)^stop$'), stop_cmd))
    
    updater.start_polling()
    print("🚀 BOT STARTED - Multi-Threaded Mode")
    updater.idle()

if __name__ == "__main__":
    main()
