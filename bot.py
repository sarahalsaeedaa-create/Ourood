import os
import re
import json
import time
import random
import hashlib
import asyncio
import aiohttp
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

# 🔥 كلمات مختارة بعناية (مش كل الكلمات)
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
    
    # 🔥 1. أهم 5 صفحات لكل كلمة (مش 40)
    for kw in TOP_KEYWORDS:
        for page in range(1, 6):  # 5 بس مش 40
            urls.append(f"https://www.amazon.sa/s?k={kw}&page={page}")
    
    # 🔥 2. الصفحات الرئيسية المهمة
    urls.extend([
        "https://www.amazon.sa/gp/todays-deals",
        "https://www.amazon.sa/gp/goldbox",
        "https://www.amazon.sa/gp/bestsellers",
        "https://www.amazon.sa/gp/new-releases",
        "https://www.amazon.sa/deals",
        "https://www.amazon.sa/gp/warehouse-deals",
        "https://www.amazon.sa/outlet",
    ])
    
    # 🔥 3. أقسام العروض المباشرة
    categories = ["electronics","fashion","home","beauty","sports","toys"]
    for cat in categories:
        urls.append(f"https://www.amazon.sa/deals/{cat}")
        urls.append(f"https://www.amazon.sa/gp/bestsellers/{cat}")
    
    return urls

async def fetch_one(session, url, semaphore):
    async with semaphore:  # تحديد عدد الطلبات المتزامنة
        try:
            headers = {"User-Agent": ua.random}
            async with session.get(url, headers=headers, timeout=10) as r:
                if r.status == 200:
                    return await r.text()
        except:
            pass
        return None

def parse_fast(html):
    if not html:
        return []
    
    soup = BeautifulSoup(html, "html.parser")
    items = soup.find_all("div", {"data-component-type": "s-search-result"})
    deals = []
    
    for item in items:
        try:
            # Title
            title_el = item.select_one("h2 a span, h2 span, .a-size-base-plus")
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
            
            # Old Price (للحصول على الخصم)
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
            
        except Exception as e:
            continue
    
    return deals

async def search_fast(chat_id):
    global stop_search
    
    urls = build_fast_urls()
    total_urls = len(urls)
    
    # إرسال رسالة البداية
    updater.bot.send_message(chat_id, f"🔎 بدء البحث السريع في {total_urls} صفحة...")
    
    # Semaphore عشان نتحكم في عدد الطلبات المتزامنة (10 بس)
    semaphore = asyncio.Semaphore(10)
    
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_one(session, url, semaphore) for url in urls]
        
        # معالجة النتائج فوراً مش بعد ما يخلص الكل
        glitch_deals = []
        normal_deals = []
        processed = 0
        found = 0
        
        for i, task in enumerate(asyncio.as_completed(tasks)):
            if stop_search:
                break
            
            html = await task
            processed += 1
            
            if html:
                deals = parse_fast(html)
                
                for d in deals:
                    # فلترة التقييم
                    if d["rating"] < 3 and d["rating"] > 0:
                        continue
                    
                    # Check duplicate
                    h = create_hash(d["title"])
                    if h in sent_hashes:
                        continue
                    
                    sent_hashes.add(h)
                    found += 1
                    
                    # إرسال فوري حسب النوع
                    if d["discount"] >= 90:
                        glitch_deals.append(d)
                        await send_deal_async(chat_id, d, "💣 GLITCH")
                    elif d["discount"] >= 60:
                        normal_deals.append(d)
                        await send_deal_async(chat_id, d, "🔥 HOT")
                    
                    # كل 10 منتجات نعمل update
                    if found % 10 == 0:
                        updater.bot.send_message(
                            chat_id, 
                            f"⏳ تم فحص {processed}/{total_urls} | وجدت {found} عرض...",
                            disable_notification=True
                        )
            
            # تأخير بسيط عشان مايتعملش ban
            await asyncio.sleep(0.1)
    
    # ملخص نهائي
    summary = f"""
✅ انتهى البحث!

📊 الإحصائيات:
• صفحات مفحوصة: {processed}
• عروض جديدة: {found}
• Glitch (90%+): {len(glitch_deals)}
• Hot Deals (60%+): {len(normal_deals)}
"""
    updater.bot.send_message(chat_id, summary)
    save_database()

async def send_deal_async(chat_id, deal, tag):
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
        await asyncio.sleep(0.5)  # تأخير بسيط بين كل إرسال
    except Exception as e:
        try:
            updater.bot.send_message(chat_id, msg)
        except:
            pass

def hi_cmd(update: Update, context: CallbackContext):
    global stop_search
    stop_search = False
    
    chat_id = update.effective_chat.id
    update.message.reply_text("🚀 بدء البحث السريع المتزامن...")
    
    # تشغيل البحث في thread منفصل عشان مايعلقش البوت
    import threading
    def run_async():
        asyncio.run(search_fast(chat_id))
    
    thread = threading.Thread(target=run_async)
    thread.start()

def stop_cmd(update: Update, context: CallbackContext):
    global stop_search
    stop_search = True
    update.message.reply_text("🛑 جاري إيقاف البحث...")

def main():
    global updater
    
    load_database()
    
    updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    
    dp.add_handler(MessageHandler(Filters.regex(r'(?i)^hi$'), hi_cmd))
    dp.add_handler(MessageHandler(Filters.regex(r'(?i)^stop$'), stop_cmd))
    
    updater.start_polling()
    print("🚀 BOT STARTED - Fast Async Mode")
    updater.idle()

if __name__ == "__main__":
    main()
