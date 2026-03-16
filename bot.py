import os
import re
import json
import time
import random
import hashlib
import logging
import threading

import cloudscraper
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

from telegram import Update
from telegram.ext import Updater, MessageHandler, Filters, CallbackContext

# ---------------- SETTINGS ----------------

TELEGRAM_BOT_TOKEN = "PUT_YOUR_BOT_TOKEN_HERE"

# ------------------------------------------

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

logger = logging.getLogger(__name__)

ua = UserAgent()

sent_hashes = set()
is_scanning = False
updater = None


# ---------- DATABASE ----------

def load_database():
    global sent_hashes
    if os.path.exists("bot_database.json"):
        try:
            with open("bot_database.json", "r") as f:
                data = json.load(f)
                sent_hashes = set(data.get("hashes", []))
        except:
            pass


def save_database():
    try:
        with open("bot_database.json", "w") as f:
            json.dump({"hashes": list(sent_hashes)}, f)
    except:
        pass


# ---------- HELPERS ----------

def create_hash(title):
    clean = re.sub(r"[^\w\s]", "", title.lower())
    clean = re.sub(r"\d+", "", clean)
    clean = clean[:40]
    return hashlib.md5(clean.encode()).hexdigest()


def create_session():
    session = cloudscraper.create_scraper()

    session.headers.update({
        "User-Agent": ua.random,
        "Accept-Language": "en-US,en;q=0.9"
    })

    return session


def fetch_page(session, url):

    for _ in range(3):
        try:
            r = session.get(url, timeout=25)
            if r.status_code == 200:
                return r.text
        except:
            pass

        time.sleep(random.uniform(0.5, 1.2))

    return None


# ---------- BUILD SEARCH SOURCES ----------

def build_categories():

    best = [
        "electronics","fashion","beauty","watches","shoes",
        "kitchen","home","computers","mobile","perfumes",
        "toys","sports","baby","grocery","automotive"
    ]

    keywords = [
        "iphone","ipad","macbook","airpods","apple watch",
        "samsung galaxy","sony headphones","bose headphones",
        "nike shoes","adidas shoes","puma shoes",
        "ps5","xbox series","nintendo switch",
        "lego","barbie","hot wheels",
        "protein powder","creatine","pre workout",
        "dyson vacuum","air fryer","nespresso",
        "bosch tools","dewalt tools",
        "treadmill","dumbbells","yoga mat"
    ]

    categories = []

    for cat in best:
        categories.append(
            (
                f"https://www.amazon.sa/gp/bestsellers/{cat}",
                f"BestSeller {cat}"
            )
        )

    for kw in keywords:
        for page in range(1, 6):
            categories.append(
                (
                    f"https://www.amazon.sa/s?k={kw}&page={page}&rh=p_8%3A30-99",
                    f"{kw} p{page}"
                )
            )

    categories.append(("https://www.amazon.sa/gp/todays-deals", "Today Deals"))
    categories.append(("https://www.amazon.sa/gp/coupons", "Coupons"))
    categories.append(("https://www.amazon.sa/outlet", "Outlet"))
    categories.append(("https://www.amazon.sa/gp/warehouse-deals", "Warehouse"))

    return categories


# ---------- PARSE ITEMS ----------

def parse_items(html, category):

    soup = BeautifulSoup(html, "html.parser")

    items = soup.find_all("div", {"data-component-type": "s-search-result"})

    deals = []

    for item in items:
        try:

            title_el = item.select_one("h2 span")
            if not title_el:
                continue

            title = title_el.text.strip()

            price_el = item.select_one(".a-price-whole")
            if not price_el:
                continue

            price = float(price_el.text.replace(",", ""))

            link = item.select_one("a")["href"]

            if link.startswith("/"):
                link = "https://www.amazon.sa" + link

            img = ""

            img_el = item.select_one("img")
            if img_el:
                img = img_el.get("src", "")

            deals.append({
                "title": title,
                "price": price,
                "link": link,
                "image": img,
                "category": category
            })

        except:
            pass

    return deals


# ---------- SEARCH ----------

def search_category(session, url, name):

    html = fetch_page(session, url)

    if not html:
        return []

    return parse_items(html, name)


def search_all():

    session = create_session()

    categories = build_categories()

    all_deals = []
    threads = []

    lock = threading.Lock()

    def worker(url, name):

        deals = search_category(session, url, name)

        with lock:
            all_deals.extend(deals)

    for url, name in categories:

        t = threading.Thread(target=worker, args=(url, name))
        t.start()

        threads.append(t)

    for t in threads:
        t.join()

    return all_deals


# ---------- FILTER ----------

def filter_deals(deals):

    results = []

    for d in deals:

        if d["price"] < 1:
            d["type"] = "🔥 GLITCH"

        elif d["price"] < 40:
            d["type"] = "💰 Cheap Deal"

        else:
            continue

        h = create_hash(d["title"])

        if h in sent_hashes:
            continue

        sent_hashes.add(h)

        results.append(d)

    return results


# ---------- SEND ----------

def send_deals(chat_id, deals):

    for d in deals:

        msg = f"""
{d['type']}

{d['title']}

💵 {d['price']} SAR

📦 {d['category']}

{d['link']}
"""

        try:

            if d["image"]:
                updater.bot.send_photo(
                    chat_id,
                    photo=d["image"],
                    caption=msg
                )

            else:

                updater.bot.send_message(
                    chat_id,
                    text=msg
                )

        except:

            updater.bot.send_message(
                chat_id,
                text=msg
            )

        time.sleep(1)


# ---------- TELEGRAM ----------

def hi_cmd(update: Update, context: CallbackContext):

    global is_scanning

    if is_scanning:
        update.message.reply_text("⏳ Already searching...")
        return

    is_scanning = True

    chat_id = update.effective_chat.id

    update.message.reply_text("🔎 Searching Amazon deals...")

    deals = search_all()

    deals = filter_deals(deals)

    if not deals:
        update.message.reply_text("❌ No good deals found")
    else:
        send_deals(chat_id, deals)

    save_database()

    is_scanning = False


# ---------- MAIN ----------

def main():

    global updater

    load_database()

    updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)

    dp = updater.dispatcher

    dp.add_handler(
        MessageHandler(Filters.text & ~Filters.command, hi_cmd)
    )

    updater.start_polling()

    print("BOT STARTED")

    updater.idle()


if __name__ == "__main__":
    main()
