import os
import re
import json
import time
import random
import hashlib
import cloudscraper
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from telegram import Update
from telegram.ext import Updater, MessageHandler, Filters, CallbackContext

TELEGRAM_BOT_TOKEN = "PUT_YOUR_TOKEN_HERE"

ua = UserAgent()
sent_hashes = set()
updater = None


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


def create_session():
    s = cloudscraper.create_scraper()
    s.headers.update({"User-Agent":ua.random})
    return s


def fetch_page(session,url):
    try:
        r = session.get(url,timeout=20)
        if r.status_code == 200:
            return r.text
    except:
        return None


# 🔥 النسخة المطورة
def build_urls():

    keywords = [
        "iphone","laptop","nike shoes","headphones","perfume",
        "watch","gaming chair","air fryer","protein powder",
        "baby toys","smart tv","tablet","camera","keyboard"
    ]

    # 🔥 توليد كلمات إضافية تلقائياً
    extra = []
    for kw in keywords:
        extra += [
            kw + " discount",
            kw + " sale",
            kw + " cheap",
            kw + " offer",
            kw + " amazon"
        ]

    keywords.extend(extra)

    urls = []

    # 🔥 زيادة الصفحات
    for kw in keywords:
        for page in range(1, 100):
            urls.append(f"https://www.amazon.sa/s?k={kw}&page={page}")

    # 🔥 مصادر إضافية
    urls.extend([
        "https://www.amazon.sa/gp/todays-deals",
        "https://www.amazon.sa/gp/goldbox",
        "https://www.amazon.sa/gp/bestsellers",
        "https://www.amazon.sa/gp/new-releases",
        "https://www.amazon.sa/gp/movers-and-shakers",
        "https://www.amazon.sa/gp/most-wished-for",
        "https://www.amazon.sa/gp/most-gifted",
        "https://www.amazon.sa/deals",
        "https://www.amazon.sa/outlet",
    ])

    # 🔥 صفحات الديلز
    for page in range(1,50):
        urls.append(f"https://www.amazon.sa/deals?ref=deals_hp&page={page}")

    return urls


def parse_items(html):

    soup = BeautifulSoup(html,"html.parser")
    items = soup.find_all("div",{"data-component-type":"s-search-result"})
    deals = []

    for item in items:
        try:
            title = item.select_one("h2 span").text.strip()

            price = float(re.findall(r"\d+\.?\d*",item.select_one(".a-price .a-offscreen").text)[0])

            old = item.select_one(".a-text-price .a-offscreen")
            if not old:
                continue

            old_price = float(re.findall(r"\d+\.?\d*",old.text)[0])

            if old_price <= price:
                continue

            discount = int(((old_price-price)/old_price)*100)

            rating = 0
            r = item.select_one(".a-icon-alt")
            if r:
                rating = float(re.findall(r"\d+\.?\d*",r.text)[0])

            link = item.select_one("a")["href"]
            if link.startswith("/"):
                link = "https://www.amazon.sa"+link

            img = item.select_one("img").get("src","")

            deals.append({
                "title":title,
                "price":price,
                "old":old_price,
                "discount":discount,
                "rating":rating,
                "link":link,
                "img":img
            })

        except:
            pass

    return deals


def search_all():

    session = create_session()
    urls = build_urls()
    all_deals = []

    for url in urls:

        html = fetch_page(session,url)

        if not html:
            continue

        deals = parse_items(html)
        all_deals.extend(deals)

        # 🔥 تهدئة لتجنب البلوك
        time.sleep(random.uniform(0.5,1.2))

    return all_deals


def filter_deals(deals):

    glitch = []
    normal = []

    for d in deals:

        if d["rating"] < 3:
            continue

        h = create_hash(d["title"])

        if h in sent_hashes:
            continue

        sent_hashes.add(h)

        if d["discount"] >= 90:
            glitch.append(d)
        elif d["discount"] >= 60:
            normal.append(d)

    glitch.sort(key=lambda x:-x["discount"])
    normal.sort(key=lambda x:-x["discount"])

    return glitch, normal


def send_group(chat_id,deals,title):

    if not deals:
        return

    updater.bot.send_message(chat_id,title)

    for d in deals:

        msg = f"""
🔥 {d['discount']}% OFF

{d['title']}

💰 {d['price']} SAR
🏷 {d['old']} SAR

⭐ {d['rating']}

{d['link']}
"""

        try:
            updater.bot.send_photo(chat_id,photo=d["img"],caption=msg)
        except:
            updater.bot.send_message(chat_id,msg)

        time.sleep(1)


def hi_cmd(update:Update,context:CallbackContext):

    chat_id = update.effective_chat.id

    update.message.reply_text("🔎 بحث ضخم جداً جاري... 🔥")

    deals = search_all()

    glitch, normal = filter_deals(deals)

    send_group(chat_id,glitch,"💣 GLITCH 90%+")
    send_group(chat_id,normal,"🔥 BEST DEALS 60%+")

    if not glitch and not normal:
        update.message.reply_text("❌ لا يوجد عروض حالياً")

    save_database()


def main():

    global updater

    load_database()

    updater = Updater(TELEGRAM_BOT_TOKEN,use_context=True)

    dp = updater.dispatcher

    dp.add_handler(MessageHandler(Filters.regex(r'(?i)^hi$'), hi_cmd))

    updater.start_polling()

    print("BOT STARTED")

    updater.idle()


if __name__ == "__main__":
    main()
