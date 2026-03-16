import os
import re
import json
import logging
import requests
import cloudscraper
import random
import hashlib
import threading
import time

from datetime import datetime
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContextlogging.basicConfig(
format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
level=logging.INFO
)

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

ua = UserAgent()

sent_products = set()
sent_hashes = set()

is_scanning = False
updater = Nonedef load_database():

    global sent_products, sent_hashes

    try:

        if os.path.exists("bot_database.json"):

            with open("bot_database.json","r") as f:

                data = json.load(f)

                sent_products = set(data.get("ids",[]))
                sent_hashes = set(data.get("hashes",[]))

    except Exception as e:

        logger.error(e)def save_database():

    try:

        with open("bot_database.json","w") as f:

            json.dump({

                "ids": list(sent_products),
                "hashes": list(sent_hashes)

            },f)

    except Exception as e:

        logger.error(e)def extract_asin(link):

    if not link:
        return None

    patterns = [
        r'/dp/([A-Z0-9]{10})',
        r'/gp/product/([A-Z0-9]{10})'
    ]

    for p in patterns:

        m = re.search(p,link)

        if m:
            return m.group(1)

    return Nonedef create_title_hash(title):

    clean = re.sub(r'[^\w\s]','',title.lower())

    clean = re.sub(r'\d+','',clean)

    clean = clean[:30]

    return hashlib.md5(clean.encode()).hexdigest()def create_session():

    session = cloudscraper.create_scraper()

    session.headers.update({

        "User-Agent": ua.random,
        "Accept-Language": "en-US,en;q=0.9"

    })

    return sessiondef fetch_page(session,url):

    for _ in range(3):

        try:

            r = session.get(url,timeout=25)

            if r.status_code == 200:

                return r.text

        except:
            pass

        time.sleep(random.uniform(0.5,1.2))

    return Nonedef build_categories():

    best = [
        "electronics","fashion","beauty","watches","shoes","kitchen","home",
        "computers","mobile","perfumes","toys","sports","baby","grocery"
    ]

    brands = [
        "iphone","ipad","macbook","airpods","apple watch",
        "samsung galaxy","sony headphones","bose headphones",
        "nike shoes","adidas shoes","ps5","xbox series",
        "lego","barbie","creatine","protein powder",
        "dyson vacuum","air fryer","nespresso","bosch tools"
    ]

    categories = []

    for b in best:

        categories.append(

            (f"https://www.amazon.sa/gp/bestsellers/{b}",
            f"BestSeller {b}",
            True)

        )

    for brand in brands:

        for page in range(1,6):

            categories.append(

                (f"https://www.amazon.sa/s?k={brand}&page={page}&rh=p_8%3A30-99",
                f"{brand} p{page}",
                False)

            )

    categories.append(("https://www.amazon.sa/gp/todays-deals","Today",False))
    categories.append(("https://www.amazon.sa/gp/coupons","Coupons",False))
    categories.append(("https://www.amazon.sa/outlet","Outlet",False))
    categories.append(("https://www.amazon.sa/gp/warehouse-deals","Warehouse",False))

    return categoriesdef search_category(session,url,name):

    html = fetch_page(session,url)

    if not html:
        return []

    soup = BeautifulSoup(html,"html.parser")

    items = soup.find_all("div",{"data-component-type":"s-search-result"})

    deals = []

    for item in items:

        try:

            title = item.select_one("h2 span").text.strip()

            price_el = item.select_one(".a-price-whole")

            if not price_el:
                continue

            price = float(price_el.text.replace(",",""))

            link = item.select_one("a")["href"]

            if link.startswith("/"):
                link = "https://amazon.sa"+link

            img = item.select_one("img")["src"]

            deals.append({

                "title":title,
                "price":price,
                "link":link,
                "image":img,
                "category":name

            })

        except:
            pass

    return dealsdef search_all():

    session = create_session()

    categories = build_categories()

    all_deals = []

    threads = []

    def worker(url,name):

        deals = search_category(session,url,name)

        all_deals.extend(deals)

    for url,name,_ in categories:

        t = threading.Thread(target=worker,args=(url,name))

        t.start()

        threads.append(t)

    for t in threads:
        t.join()

    return all_dealsdef filter_deals(deals):

    result = []

    for d in deals:

        if d["price"] < 1:
            d["type"] = "🔥 GLITCH"

        elif d["price"] < 30:
            d["type"] = "💰 Cheap Deal"

        else:
            continue

        h = create_title_hash(d["title"])

        if h in sent_hashes:
            continue

        sent_hashes.add(h)

        result.append(d)

    return resultdef send_deals(chat_id,deals):

    for d in deals:

        msg = f"""

{d['type']}

{d['title']}

💵 {d['price']} SAR

{d['category']}

{d['link']}

"""

        try:

            updater.bot.send_photo(chat_id,photo=d["image"],caption=msg)

        except:

            updater.bot.send_message(chat_id,text=msg)

        time.sleep(1)def hi_cmd(update:Update,context:CallbackContext):

    global is_scanning

    if is_scanning:
        update.message.reply_text("Searching...")
        return

    is_scanning = True

    update.message.reply_text("🔍 Searching Amazon...")

    deals = search_all()

    deals = filter_deals(deals)

    send_deals(update.effective_chat.id,deals)

    save_database()

    is_scanning = Falsedef main():

    global updater

    load_database()

    updater = Updater(TELEGRAM_BOT_TOKEN,use_context=True)

    dp = updater.dispatcher

    dp.add_handler(MessageHandler(Filters.regex("(?i)^hi$"),hi_cmd))

    updater.start_polling()

    updater.idle()if __name__ == "__main__":
    main()
