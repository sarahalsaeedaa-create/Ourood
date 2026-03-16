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

TELEGRAM_BOT_TOKEN = "8769441239:AAEgX3uBbtWc_hHcqs0lmQ50AqKJGOWV6Ok"

ua = UserAgent()
sent_hashes = set()
is_scanning = False
updater = None


# ---------------- DATABASE ----------------

def load_database():
    global sent_hashes

    if os.path.exists("database.json"):
        try:
            with open("database.json","r") as f:
                data = json.load(f)
                sent_hashes = set(data.get("hashes",[]))
        except:
            pass


def save_database():
    try:
        with open("database.json","w") as f:
            json.dump({"hashes":list(sent_hashes)},f)
    except:
        pass


# ---------------- HELPERS ----------------

def create_hash(text):

    clean = re.sub(r"[^\w\s]","",text.lower())
    clean = re.sub(r"\d+","",clean)
    clean = clean[:40]

    return hashlib.md5(clean.encode()).hexdigest()


def create_session():

    s = cloudscraper.create_scraper()

    s.headers.update({
        "User-Agent":ua.random,
        "Accept-Language":"en-US,en;q=0.9"
    })

    return s


def fetch_page(session,url):

    for _ in range(3):

        try:

            r = session.get(url,timeout=30)

            if r.status_code == 200:
                return r.text

        except:
            pass

        time.sleep(random.uniform(0.5,1.5))

    return None


# ---------------- BUILD SEARCH ----------------

def build_categories():

    keywords = [

    "iphone","ipad","macbook","airpods","apple watch",
    "samsung","galaxy","sony headphones","bose",
    "gaming monitor","mechanical keyboard","gaming mouse",
    "ps5","xbox","gaming chair","vr headset",
    "lego","barbie","toys","drone",
    "nike","adidas","puma","running shoes",
    "protein powder","creatine","mass gainer",
    "air fryer","coffee machine","blender",
    "vacuum cleaner","dyson","robot vacuum",
    "power tools","drill","tool set",
    "treadmill","exercise bike","dumbbells",
    "smart tv","4k tv","oled tv",
    "ssd","external ssd","hard drive",
    "router","wifi 6 router","mesh wifi"

    ]

    urls = []

    for kw in keywords:

        for page in range(1,16):

            urls.append(
                f"https://www.amazon.sa/s?k={kw}&page={page}"
            )

    urls.append("https://www.amazon.sa/gp/todays-deals")

    return urls


# ---------------- PARSE ----------------

def parse_items(html):

    soup = BeautifulSoup(html,"html.parser")

    items = soup.find_all("div",{"data-component-type":"s-search-result"})

    deals = []

    for item in items:

        try:

            title_el = item.select_one("h2 span")
            if not title_el:
                continue

            title = title_el.text.strip()

            price_el = item.select_one(".a-price .a-offscreen")
            if not price_el:
                continue

            price = float(re.findall(r"\d+\.?\d*",price_el.text)[0])

            old_el = item.select_one(".a-text-price .a-offscreen")
            if not old_el:
                continue

            old_price = float(re.findall(r"\d+\.?\d*",old_el.text)[0])

            if old_price <= price:
                continue

            discount = int(((old_price-price)/old_price)*100)

            rating = 0
            rating_el = item.select_one(".a-icon-alt")

            if rating_el:
                m = re.search(r"(\d+\.?\d*)",rating_el.text)
                if m:
                    rating = float(m.group(1))

            link = item.select_one("a")["href"]

            if link.startswith("/"):
                link = "https://www.amazon.sa"+link

            img = ""
            img_el = item.select_one("img")

            if img_el:
                img = img_el.get("src","")

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


# ---------------- SEARCH ----------------

def search_all():

    session = create_session()

    urls = build_categories()

    all_deals = []

    for url in urls:

        html = fetch_page(session,url)

        if not html:
            continue

        deals = parse_items(html)

        all_deals.extend(deals)

        time.sleep(random.uniform(0.4,1.0))

    return all_deals


# ---------------- FILTER ----------------

def filter_deals(deals):

    results = []

    for d in deals:

        if d["discount"] < 60:
            continue

        if d["rating"] < 3:
            continue

        h = create_hash(d["title"])

        if h in sent_hashes:
            continue

        sent_hashes.add(h)

        results.append(d)

    results.sort(key=lambda x:-x["discount"])

    return results


# ---------------- SEND ----------------

def send_deals(chat_id,deals):

    for d in deals:

        msg = f"""
🔥 {d['discount']}% OFF

{d['title']}

💰 {d['price']} SAR
🏷 {d['old']} SAR

⭐ {d['rating']} / 5

{d['link']}
"""

        try:

            if d["img"]:

                updater.bot.send_photo(
                    chat_id,
                    photo=d["img"],
                    caption=msg
                )

            else:

                updater.bot.send_message(
                    chat_id,
                    msg
                )

        except:

            updater.bot.send_message(
                chat_id,
                msg
            )

        time.sleep(1)


# ---------------- TELEGRAM ----------------

def hi_cmd(update:Update,context:CallbackContext):

    global is_scanning

    if is_scanning:
        update.message.reply_text("Bot already scanning...")
        return

    is_scanning = True

    chat_id = update.effective_chat.id

    update.message.reply_text("Searching 600+ Amazon pages...")

    deals = search_all()

    deals = filter_deals(deals)

    if not deals:

        update.message.reply_text("No deals found")

    else:

        send_deals(chat_id,deals)

    save_database()

    is_scanning = False


# ---------------- MAIN ----------------

def main():

    global updater

    load_database()

    updater = Updater(TELEGRAM_BOT_TOKEN,use_context=True)

    dp = updater.dispatcher

    dp.add_handler(
        MessageHandler(Filters.text & ~Filters.command,hi_cmd)
    )

    updater.start_polling()

    print("BOT STARTED")

    updater.idle()


if __name__ == "__main__":
    main()
