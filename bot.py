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

# 👕 ملابس رجالي
"men t shirt","plain t shirt","graphic t shirt","oversized t shirt",
"men hoodie","zip hoodie","sweatshirt","men jacket","winter jacket",
"leather jacket","denim jacket","men jeans","slim jeans","baggy jeans",
"cargo pants","joggers","shorts men","swim shorts","underwear men",
"boxers","briefs","pajamas men","tracksuit","gym wear men",

# 👗 ملابس حريمي
"women dress","evening dress","party dress","maxi dress","summer dress",
"abaya","abaya women","hijab","scarf","women blouse","crop top",
"women t shirt","women jeans","skinny jeans women","leggings",
"yoga pants","skirts","mini skirt","long skirt","nightwear women",

# 👶 ملابس أطفال
"kids clothes","baby clothes","baby set","baby outfit",
"kids t shirt","kids hoodie","kids jeans","kids dress",
"school uniform","baby pajamas",

# 👟 أحذية
"nike shoes","adidas shoes","puma shoes","reebok shoes",
"running shoes","walking shoes","training shoes",
"basketball shoes","football shoes","boots","ankle boots",
"heels","high heels","sandals","slippers","flip flops",
"crocs","kids shoes","baby shoes","school shoes",

# 💄 مكياج
"makeup kit","lipstick matte","liquid lipstick",
"foundation full coverage","concealer makeup",
"face powder","setting spray","makeup brush set",
"beauty blender","eyeliner","mascara waterproof",
"eyeshadow palette","highlighter makeup","blush makeup",

# 🧴 عناية بالبشرة
"skincare set","face cream","face serum vitamin c",
"hyaluronic acid serum","retinol cream",
"cleanser face","face wash","moisturizer",
"sunscreen spf 50","night cream","anti aging cream",
"eye cream","face mask","peeling solution",

# 💇‍♀️ عناية بالشعر
"shampoo","conditioner","hair oil","argan oil",
"hair mask","keratin treatment","hair serum",
"hair dryer","hair straightener","hair curler",
"hair brush","scalp massager",

# 🌸 عطور
"perfume","men perfume","women perfume",
"arabic perfume","oud perfume","luxury perfume",
"gift perfume set","body spray","deodorant",

# 📱 جوالات
"iphone","iphone 11","iphone 12","iphone 13","iphone 14","iphone 15",
"iphone pro max","renewed iphone","used iphone",
"samsung galaxy","galaxy s21","s22","s23","s24",
"android phone","xiaomi phone","redmi phone",
"oppo phone","realme phone","huawei phone",

# 🔌 اكسسوارات موبايل
"phone case","iphone case","clear case","shockproof case",
"charger","fast charger","usb c charger",
"wireless charger","magnetic charger",
"power bank","20000mah power bank",
"car charger","phone holder car",
"screen protector","tempered glass",
"camera protector","ring light phone",
"tripod phone","selfie stick",

# 🎧 صوتيات
"earbuds","bluetooth earbuds","wireless earbuds",
"airpods","noise cancelling headphones",
"gaming headset","speaker bluetooth",
"portable speaker","soundbar",

# 💻 إلكترونيات
"laptop","gaming laptop","cheap laptop",
"tablet","ipad","android tablet",
"smart tv","4k tv","android tv box",
"monitor","gaming monitor","keyboard",
"mechanical keyboard","gaming mouse",
"webcam","printer","router wifi",

# 🎮 جيمينج
"gaming mouse","gaming keyboard","gaming chair",
"ps5","playstation 5","xbox series x",
"nintendo switch","gaming headset",
"rgb keyboard","gaming desk",

# 🍫 طعام
"chocolate","dark chocolate","milk chocolate",
"snacks","chips","biscuits","cookies",
"protein bar","granola bar","energy bar",
"coffee","instant coffee","espresso",
"tea","green tea","matcha",
"dates","saudi dates","ajwa dates",
"nuts","almonds","cashew","pistachio",
"honey","natural honey","peanut butter",

# 👶 أطفال
"baby toys","kids toys","educational toys",
"lego","lego sets","puzzle kids",
"remote control car","rc car",
"baby stroller","baby car seat",
"baby bottle","feeding bottle",
"baby milk","formula milk",
keywords = [

# 🔥 كلمات جليتش / عروض مخفية
"price error","pricing error","glitch deal","wrong price",
"mistake price","super discount","crazy deal","insane deal",
"unbelievable deal","hidden deal","secret deal",
"warehouse deal","refurbished","renewed","open box",
"like new","used like new","clearance sale","liquidation sale",

# 👕 ملابس (تفصيل قوي)
"oversized hoodie","streetwear hoodie","graphic hoodie",
"zip up hoodie","heavyweight hoodie","fleece hoodie",
"baggy jeans","ripped jeans","distressed jeans",
"cargo pants men","cargo pants women",
"tracksuit set","gym outfit","athleisure wear",
"compression shirt","thermal wear","winter clothes",
"summer clothes","beach wear","swimwear","bikini set",

# 👗 نسائي (ترند)
"bodycon dress","cocktail dress","prom dress",
"abaya luxury","abaya embroidered",
"hijab chiffon","hijab cotton","turban scarf",
"loungewear women","homewear set","sleepwear",
"lingerie set","sports bra","yoga outfit",

# 👟 أحذية متقدمة
"sneakers","chunky sneakers","running sneakers",
"retro sneakers","limited sneakers",
"gym shoes","training sneakers",
"hiking boots","combat boots",
"luxury shoes","designer shoes",

# 💄 مكياج احترافي
"full makeup kit professional","makeup palette",
"hd foundation","matte foundation","bb cream",
"cc cream","primer makeup","setting powder",
"contour kit","bronzer","glow highlighter",
"false lashes","lash extension","brow kit",

# 🧴 سكن كير قوي
"korean skincare","glass skin","skin whitening",
"acne treatment","pimple cream","dark spot remover",
"blackhead remover","face scrub","exfoliator",
"vitamin c serum","niacinamide serum",
"spf 100 sunscreen","organic skincare",

# 💇‍♀️ شعر (احترافي)
"hair growth oil","anti hair loss","hair vitamins",
"biotin shampoo","keratin shampoo",
"hair straightening brush","ionic hair dryer",
"professional hair tools","barber machine",

# 🌸 عطور فخمة
"arabic oud","bakhoor","incense burner",
"luxury fragrance","niche perfume",
"gift perfume box","mini perfume set",
"long lasting perfume","strong perfume",

# 📱 جوالات (تفصيل أعمق)
"cheap smartphone","budget phone","flagship phone",
"gaming phone","5g phone","dual sim phone",
"128gb phone","256gb phone","512gb phone",

# 🔌 اكسسوارات متقدمة
"fast charging cable","type c cable","lightning cable",
"magnetic cable","wireless powerbank",
"solar power bank","gaming phone cooler",
"mobile fan","cooling fan phone",
"camera lens phone","macro lens phone",

# 🎧 صوتيات احترافية
"studio headphones","dj headphones",
"noise cancelling earbuds","bass boosted headphones",
"gaming earbuds","rgb headset",
"waterproof speaker","party speaker",

# 💻 إلكترونيات متقدمة
"ultrabook laptop","business laptop","student laptop",
"cheap tablet","drawing tablet",
"smartwatch","fitness tracker",
"security camera","cctv camera","wifi camera",
"smart home","smart plug","smart bulb",

# 🎮 جيمينج احترافي
"gaming pc","rtx graphics card",
"gaming setup","gaming accessories",
"rgb mouse","rgb keyboard",
"gaming monitor 144hz","240hz monitor",
"gaming desk setup",

# 🍫 طعام (أقوى)
"keto snacks","diet snacks","low carb snacks",
"protein snacks","fitness snacks",
"organic food","healthy food",
"imported chocolate","luxury chocolate",
"gift chocolate box","energy snacks",

# 👶 أطفال متقدم
"montessori toys","learning toys",
"stem toys","brain toys",
"kids tablet","kids learning tablet",
"baby monitor","baby camera",
"baby care set","newborn essentials",

# 🏠 منزل (احترافي)
"smart vacuum","robot cleaner",
"air purifier","humidifier",
"electric kettle","smart coffee machine",
"kitchen gadgets","home gadgets",
"led lights","rgb lights room",

# 🏋️ رياضة متقدمة
"home gym equipment","fitness home gym",
"adjustable dumbbells","smart scale",
"fat burner","muscle gain",
"gym supplements","mass gainer",

# 🚗 سيارات
"car accessories","car gadgets",
"car vacuum","dash cam","car camera",
"car perfume","seat cover",
"car charger fast","car organizer",

# 💎 فخم
"luxury watch","designer bag",
"premium leather bag","gold jewelry",
"diamond jewelry","silver jewelry",

# 🔥 كلمات انفجار نتائج
"best seller","top rated","most popular",
"trending now","viral product",
"amazon choice","limited stock",
"fast selling","hot product",
"top deals today","big discount",
"lowest ever price","price drop",
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
