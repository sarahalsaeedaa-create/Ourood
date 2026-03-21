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


# 🔥 كلمات ضخمة جداً
def build_urls():

    keywords = [

# 🔥 Glitch + Hidden
"price error","pricing error","wrong price","glitch deal","mistake price",
"error deal","bug price","hidden deal","secret deal","crazy deal",
"insane deal","unbelievable deal","warehouse deal","clearance sale",
"liquidation sale","last chance","final sale","super clearance",

# 👕 Men Clothing
"men t shirt","plain t shirt","graphic t shirt","oversized t shirt",
"streetwear t shirt","long sleeve shirt","polo shirt",
"men hoodie","zip hoodie","pullover hoodie",
"men jacket","winter jacket","leather jacket","denim jacket",
"men jeans","slim fit jeans","regular fit jeans","baggy jeans",
"cargo pants","joggers","track pants","shorts men",
"swim shorts","underwear men","boxers","briefs",
"pajamas men","tracksuit","gym wear men","sportswear men",

# 👗 Women Clothing
"women dress","summer dress","maxi dress","mini dress","evening dress",
"party dress","cocktail dress","abaya","abaya women",
"hijab","scarf","turban","women blouse",
"crop top","tank top","women t shirt",
"women jeans","leggings","yoga pants",
"skirts","long skirt","mini skirt",
"sleepwear women","nightwear women",

# 👶 Kids Clothing
"kids clothes","baby clothes","baby outfit","baby set",
"kids t shirt","kids hoodie","kids jeans","kids dress",
"baby pajamas","school uniform",

# 👟 Shoes
"nike shoes","adidas shoes","puma shoes","reebok shoes",
"running shoes","walking shoes","training shoes",
"basketball shoes","football shoes",
"boots","ankle boots","combat boots",
"heels","high heels","sandals","slippers",
"flip flops","crocs","kids shoes","baby shoes",

# 💄 Makeup
"makeup kit","lipstick matte","liquid lipstick",
"foundation full coverage","bb cream","cc cream",
"concealer makeup","face powder","setting spray",
"makeup brush set","beauty blender",
"eyeliner","mascara waterproof",
"eyeshadow palette","highlighter makeup","blush makeup",

# 🧴 Skincare
"skincare set","face cream","face serum","vitamin c serum",
"hyaluronic acid serum","retinol cream",
"cleanser face","face wash","moisturizer",
"sunscreen spf 50","night cream","anti aging cream",
"eye cream","face mask","peeling solution",

# 💇 Hair
"shampoo","conditioner","hair oil","argan oil",
"hair mask","keratin treatment","hair serum",
"hair dryer","hair straightener","hair curler",

# 🌸 Perfume
"perfume","men perfume","women perfume",
"arabic perfume","oud perfume","luxury perfume",
"body spray","deodorant","perfume gift set",

# 📱 Phones
"iphone","iphone 11","iphone 12","iphone 13","iphone 14","iphone 15",
"samsung galaxy","android phone","xiaomi phone",
"oppo phone","realme phone","huawei phone",

# 🔌 Accessories
"phone case","iphone case","clear case","shockproof case",
"charger","fast charger","usb c charger",
"wireless charger","power bank",
"car charger","phone holder car",
"screen protector","tempered glass",

# 🎧 Audio
"earbuds","bluetooth earbuds","wireless earbuds",
"airpods","noise cancelling headphones",
"gaming headset","speaker bluetooth",

# 💻 Electronics
"laptop","gaming laptop","cheap laptop",
"tablet","ipad","android tablet",
"smart tv","4k tv","android tv",
"monitor","gaming monitor",
"keyboard","gaming keyboard",
"mouse","gaming mouse",

# 🎮 Gaming
"ps5","playstation 5","xbox series x",
"nintendo switch","gaming chair",
"gaming desk","rgb keyboard",

# 🍫 Food
"chocolate","snacks","chips","biscuits",
"protein bar","coffee","tea",
"dates","saudi dates","nuts",
"honey","peanut butter",

# 👶 Kids
"baby toys","kids toys","lego","puzzle",
"remote control car",
"baby stroller","baby bottle",
"diapers","baby wipes",

# 🏠 Home
"air fryer","blender","coffee machine",
"vacuum cleaner","robot vacuum",
"microwave","kitchen tools",

# 🏋️ Fitness
"fitness equipment","dumbbells","yoga mat",
"treadmill","exercise bike",
"protein powder","creatine",

# 🚗 Cars
"car accessories","car charger","dash cam",
"car vacuum","car organizer",

# 💎 Luxury
"luxury watch","designer bag",
"gold jewelry","silver jewelry",

# 🔥 Viral + Trends
"best seller","top rated","most popular",
"trending now","viral product",
"amazon choice","limited stock",
"fast selling","hot product",
"top deals today","big discount",
"lowest price","price drop",
"must buy","recommended"

    ]


    urls = []

    for kw in keywords:
        for page in range(1, 40):  # 🔥 عدد صفحات كبير
            urls.append(f"https://www.amazon.sa/s?k={kw}&page={page}")

    urls.append("https://www.amazon.sa/gp/todays-deals")

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

        time.sleep(random.uniform(0.2,0.5))

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

    update.message.reply_text("🔎 بحث ضخم جداً جاري... انتظر 🔥")

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
