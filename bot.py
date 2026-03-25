import os
import re
import json
import logging
import cloudscraper
import time
import random
import hashlib
from bs4 import BeautifulSoup
from telegram import Bot
from fake_useragent import UserAgent

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ====== CONFIG ======
TELEGRAM_BOT_TOKEN = "8769441239:AAEgX3uBbtWc_hHcqs0lmQ50AqKJGOWV6Ok"
TELEGRAM_CHAT_ID = "432826122"
ua = UserAgent()
sent_products = set()
sent_hashes = set()

bot = Bot(token=TELEGRAM_BOT_TOKEN)

# ====== DATABASE ======
def load_database():
    global sent_products, sent_hashes
    if os.path.exists('bot_database.json'):
        try:
            with open('bot_database.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
                sent_products = set(data.get('ids', []))
                sent_hashes = set(data.get('hashes', []))
                logger.info(f"📦 Loaded DB: {len(sent_products)} products")
        except Exception as e:
            logger.error(f"Error loading DB: {e}")

def save_database():
    try:
        with open('bot_database.json', 'w', encoding='utf-8') as f:
            json.dump({'ids': list(sent_products), 'hashes': list(sent_hashes)}, f)
    except Exception as e:
        logger.error(f"Error saving DB: {e}")

# ====== HELPERS ======
def extract_asin(link):
    patterns = [r'/dp/([A-Z0-9]{10})', r'/gp/product/([A-Z0-9]{10})', r'product/([A-Z0-9]{10})']
    for p in patterns:
        match = re.search(p, link)
        if match:
            return match.group(1).upper()
    return None

def create_title_hash(title):
    clean = re.sub(r'[^\w\s]', '', title.lower())
    clean = re.sub(r'\s+', ' ', clean).strip()
    clean = re.sub(r'\d+', '', clean)
    for word in ['amazon', 'saudi', 'ريال', 'sar', 'new', 'جديد', 'shipped', 'شحن']:
        clean = clean.replace(word, '')
    return hashlib.md5(clean[:30].encode()).hexdigest()[:16]

def is_similar_product(title):
    new_hash = create_title_hash(title)
    if new_hash in sent_hashes:
        return True
    return False

def get_product_id(deal):
    asin = extract_asin(deal.get('link', ''))
    if asin:
        return f"ASIN_{asin}"
    key = f"{deal.get('title', '')}_{deal.get('price', 0)}"
    return f"HASH_{hashlib.md5(key.encode()).hexdigest()[:12]}"

# ====== SESSION ======
def create_session():
    session = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True},
        delay=10
    )
    session.headers.update({
        'User-Agent': ua.random,
        'Accept-Language': 'ar-SA,ar;q=0.9',
        'Referer': 'https://www.amazon.sa/',
    })
    return session

def fetch_page(session, url):
    for i in range(3):
        try:
            time.sleep(random.uniform(1, 2))
            r = session.get(url, timeout=25)
            if r.status_code == 200:
                return r.text
            time.sleep(2)
        except Exception as e:
            logger.warning(f"Attempt {i+1} failed: {e}")
    return None

# ====== PARSE ITEMS ======
def parse_item(item, category, is_best_seller):
    try:
        # Title
        title = "Unknown"
        for sel in ['h2 a span', 'h2 span', '.a-size-mini span', '.a-size-base-plus', '.p13n-sc-truncated', '.a-size-medium']:
            el = item.select_one(sel)
            if el:
                title = el.text.strip()
                if len(title) > 5:
                    break
        
        # Price
        price = None
        for sel in ['.a-price-whole', '.a-price .a-offscreen', '.a-price-range', '.a-price']:
            el = item.select_one(sel)
            if el:
                txt = el.text.replace(',', '').replace('ريال', '').strip()
                match = re.search(r'[\d,]+\.?\d*', txt)
                if match:
                    price = float(match.group().replace(',', ''))
                    break
        if not price or price <= 0:
            return None
        
        # Link
        link = ""
        a = item.find('a', href=True)
        if a:
            href = a['href']
            if href.startswith('/'):
                link = f"https://www.amazon.sa{href}"
            else:
                link = href
        
        # Discount calculation
        old_price = 0
        discount = 0
        old_el = item.find('span', class_='a-text-price')
        if old_el:
            txt = old_el.get_text()
            match = re.search(r'[\d,]+\.?\d*', txt.replace(',', ''))
            if match:
                old_price = float(match.group())
                if old_price > price:
                    discount = int(((old_price - price)/old_price)*100)
        
        # Build deal dict
        deal = {'title': title, 'price': price, 'old_price': old_price, 'discount': discount, 'link': link, 'category': category}
        return deal
    except Exception as e:
        logger.error(f"parse_item error: {e}")
        return None

# ====== SEND TO TELEGRAM ======
def send_to_telegram(deal):
    try:
        msg = f"📌 {deal['title']}\n💰 Price: {deal['price']} SAR"
        if deal['discount'] > 0:
            msg += f"\n💸 Discount: {deal['discount']}%\n~ {deal['old_price']} SAR"
        if deal.get('link'):
            msg += f"\n🔗 {deal['link']}"
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)
        logger.info(f"✅ Sent: {deal['title']}")
    except Exception as e:
        logger.error(f"Telegram send error: {e}")

# ====== KEYWORDS & URLS ======
def get_keywords():
    return [
        # 🔥 Glitch + Hidden
        "price error","pricing error","wrong price","glitch deal","mistake price",
        "error deal","bug price","hidden deal","secret deal","crazy deal",
        "insane deal","unbelievable deal","warehouse deal","clearance sale",
        "liquidation sale","last chance","final sale","super clearance",
        "flash sale","lightning deal","deal of the day","gold box deal",
        "prime deal","exclusive deal","members only","early access",
        "limited time offer","while supplies last","almost gone","selling fast",
        "low stock alert","back in stock","new arrival","just dropped",
        "steal deal","dirt cheap","penny deal","dollar deal","under 10",
        "under 20","under 50","free shipping","bundle deal","buy one get one",
        "bogof","2 for 1","multi buy","bulk discount","wholesale price",

        # 👕 Men Clothing
        "men t shirt","plain t shirt","graphic t shirt","oversized t shirt",
        "streetwear t shirt","long sleeve shirt","polo shirt",
        "men hoodie","zip hoodie","pullover hoodie","oversized hoodie",
        "men jacket","winter jacket","leather jacket","denim jacket","bomber jacket",
        "men jeans","slim fit jeans","regular fit jeans","baggy jeans","ripped jeans",
        "cargo pants","joggers","track pants","shorts men","chino shorts",
        "swim shorts","underwear men","boxers","briefs","trunks",
        "pajamas men","tracksuit","gym wear men","sportswear men","compression wear",
        "men vest","tank top men","muscle shirt","henley shirt","flannel shirt",
        "men sweater","cardigan men","blazer men","suit men","formal wear men",
        "men socks","ankle socks","crew socks","no show socks","dress socks",
        "men belt","leather belt","casual belt","men wallet","card holder",
        "men sunglasses","men cap","baseball cap","snapback","bucket hat",
        "men scarf","men gloves","winter gloves","tie men","bow tie",
        "cufflinks","men watch","men bracelet","men ring","men necklace",

        # 👗 Women Clothing
        "women dress","summer dress","maxi dress","mini dress","evening dress",
        "party dress","cocktail dress","abaya","abaya women","open abaya",
        "closed abaya","kimono abaya","colored abaya","embroidered abaya",
        "hijab","scarf","shawl","pashmina","turban","inner cap",
        "women blouse","satin blouse","silk blouse","chiffon blouse",
        "crop top","tank top","women t shirt","women polo",
        "women jeans","mom jeans","boyfriend jeans","wide leg jeans",
        "leggings","yoga pants","flare pants","palazzo pants",
        "skirts","long skirt","mini skirt","midi skirt","pleated skirt",
        "sleepwear women","nightwear women","lingerie","bra","panties",
        "women bodysuit","women romper","women jumpsuit","women overall",
        "women cardigan","women sweater","women blazer","women coat",
        "trench coat women","wool coat women","fur coat women","puffer jacket women",
        "women vest","women shorts","women capri","women cargo pants",
        "maternity clothes","nursing clothes","plus size women","curve clothing",

        # 👶 Kids Clothing
        "kids clothes","baby clothes","baby outfit","baby set","newborn clothes",
        "kids t shirt","kids hoodie","kids jeans","kids dress","kids shirt",
        "baby pajamas","school uniform","kids uniform","boys clothes",
        "girls clothes","toddler clothes","infant clothes","kids jacket",
        "kids shoes","kids sandals","kids boots","kids socks",
        "baby onesie","baby bodysuit","baby romper","baby blanket",
        "kids swimwear","kids underwear","kids shorts","kids track pants",
        "kids costume","kids party dress","kids ethnic wear","kids traditional dress",

        # 👟 Shoes
        "nike shoes","adidas shoes","puma shoes","reebok shoes","new balance",
        "running shoes","walking shoes","training shoes","gym shoes",
        "basketball shoes","football shoes","tennis shoes","cricket shoes",
        "hiking shoes","trail running","boots","ankle boots","combat boots",
        "chelsea boots","desert boots","work boots","safety boots",
        "heels","high heels","stiletto","block heels","wedge heels",
        "platform shoes","sandals","flat sandals","wedge sandals",
        "slippers","house slippers","flip flops","beach sandals",
        "crocs","clogs","mules","loafers","oxford shoes",
        "brogues","derby shoes","monk strap","boat shoes",
        "kids shoes","baby shoes","school shoes","canvas shoes",
        "white sneakers","black sneakers","platform sneakers","slip on shoes",
        "velcro shoes","light up shoes","character shoes",

        # 💄 Makeup
        "makeup kit","makeup set","makeup box","makeup bag",
        "lipstick matte","liquid lipstick","lip gloss","lip liner",
        "lip balm","lip tint","lip stain","lip plumper",
        "foundation full coverage","foundation matte","foundation dewy",
        "bb cream","cc cream","dd cream","tinted moisturizer",
        "concealer makeup","color corrector","face powder","loose powder",
        "compact powder","setting spray","setting powder","primer makeup",
        "makeup brush set","beauty blender","makeup sponge","powder puff",
        "eyeliner","liquid eyeliner","gel eyeliner","pencil eyeliner",
        "mascara waterproof","mascara volumizing","mascara lengthening",
        "eyeshadow palette","neutral palette","smoky palette","glitter eyeshadow",
        "eyebrow pencil","eyebrow gel","eyebrow powder","brow kit",
        "highlighter makeup","blush makeup","bronzer","contour kit",
        "false eyelashes","eyelash glue","eyelash curler","lash serum",
        "nail polish","gel nail polish","nail dryer","nail art kit",
        "makeup remover","micellar water","cleansing balm","makeup wipes",

        # 🧴 Skincare
        "skincare set","face cream","face serum","vitamin c serum",
        "hyaluronic acid serum","retinol cream","retinol serum","aha bha",
        "niacinamide serum","salicylic acid","glycolic acid","lactic acid",
        "cleanser face","face wash","foaming cleanser","oil cleanser",
        "moisturizer","day cream","night cream","gel moisturizer",
        "sunscreen spf 50","sunscreen spf 30","sunblock","uv protection",
        "anti aging cream","wrinkle cream","firming cream","lifting serum",
        "eye cream","eye serum","eye gel","eye patch","dark circle cream",
        "face mask","sheet mask","clay mask","peel off mask","sleeping mask",
        "peeling solution","exfoliator","face scrub","toner","essence",
        "face oil","facial mist","face mist","thermal water",
        "acne treatment","pimple patch","spot treatment","blemish cream",
        "skin whitening","brightening cream","glow serum","radiance cream",
        "body lotion","body cream","body butter","hand cream","foot cream",
        "lip care","lip scrub","lip mask","under eye roller",

        # 💇 Hair
        "shampoo","conditioner","hair mask","hair oil","argan oil",
        "castor oil","coconut oil","olive oil","almond oil","jojoba oil",
        "hair serum","hair tonic","hair growth oil","hair vitamins",
        "keratin treatment","protein treatment","hair spa","hair cream",
        "leave in conditioner","dry shampoo","clarifying shampoo",
        "anti dandruff shampoo","color protect shampoo","sulfate free shampoo",
        "hair dryer","hair straightener","hair curler","curling wand",
        "hair brush","comb","detangling brush","paddle brush",
        "hair clips","hair ties","scrunchies","headband","hair band",
        "hair wax","hair gel","hair mousse","hair spray","hair color",
        "henna","hair dye","root touch up","hair bleach","developer",
        "hair extensions","clip in extensions","tape in extensions","wig",
        "hair accessories","hair pins","bobby pins","hair comb","tiara",

        # 🌸 Perfume
        "perfume","men perfume","women perfume","unisex perfume",
        "arabic perfume","oud perfume","musk perfume","amber perfume",
        "luxury perfume","designer perfume","niche perfume","indie perfume",
        "eau de parfum","eau de toilette","eau de cologne","parfum extrait",
        "body spray","body mist","deodorant","antiperspirant",
        "perfume gift set","perfume mini","travel size perfume","perfume sample",
        "attar","itra","bakhoor","oudh","mabthooth",
        "incense burner","mabkhara","perfume oil","roll on perfume",
        "fragrance","scent","cologne","aftershave","shaving lotion",

        # 📱 Phones
        "iphone","iphone 11","iphone 12","iphone 13","iphone 14","iphone 15",
        "iphone 16","iphone pro","iphone pro max","iphone plus","iphone mini",
        "samsung galaxy","samsung s24","samsung s23","samsung s22","samsung ultra",
        "samsung flip","samsung fold","samsung a series","samsung m series",
        "android phone","google pixel","oneplus","nothing phone",
        "xiaomi phone","redmi","poco","realme phone","oppo phone",
        "vivo phone","huawei phone","honor phone","nokia phone",
        "rugged phone","gaming phone","foldable phone","flip phone",
        "refurbished phone","renewed phone","open box phone",
        "feature phone","button phone","senior phone","kids phone",

        # 🔌 Accessories
        "phone case","iphone case","samsung case","clear case","shockproof case",
        "armor case","wallet case","leather case","silicone case","magnetic case",
        "charger","fast charger","usb c charger","quick charge","gan charger",
        "wireless charger","charging pad","charging stand","magsafe charger",
        "power bank","portable charger","solar charger","car charger",
        "phone holder car","dashboard mount","air vent mount","magnetic mount",
        "screen protector","tempered glass","privacy screen","anti glare",
        "camera protector","lens protector","back protector",
        "usb cable","charging cable","data cable","braided cable",
        "adapter","wall adapter","travel adapter","multi port charger",
        "otg cable","card reader","sim ejector","phone strap","phone ring",
        "pop socket","phone stand","selfie stick","tripod phone",
        "smart watch band","watch strap","airpods case","earbuds case",

        # 🎧 Audio
        "earbuds","bluetooth earbuds","wireless earbuds","tws earbuds",
        "airpods","airpods pro","airpods max","beats headphones",
        "noise cancelling headphones","anc headphones","over ear headphones",
        "on ear headphones","in ear headphones","sports headphones",
        "gaming headset","surround sound headset","rgb headset",
        "speaker bluetooth","portable speaker","waterproof speaker",
        "party speaker","soundbar","home theater","subwoofer",
        "microphone","condenser mic","dynamic mic","usb mic","wireless mic",
        "karaoke mic","studio headphones","monitor headphones","dj headphones",
        "audio interface","sound card","headphone amp","dac",
        "bluetooth receiver","bluetooth transmitter","fm transmitter",
        "earphone","wired earphone","gaming earphone","sleep earphone",

        # 💻 Electronics
        "laptop","gaming laptop","cheap laptop","business laptop",
        "student laptop","chromebook","macbook","macbook air","macbook pro",
        "ultrabook","2 in 1 laptop","convertible laptop","touchscreen laptop",
        "tablet","ipad","ipad air","ipad pro","samsung tablet",
        "android tablet","huawei tablet","lenovo tablet","kids tablet",
        "smart tv","4k tv","8k tv","oled tv","qled tv",
        "android tv","google tv","roku tv","fire tv","apple tv",
        "monitor","gaming monitor","curved monitor","ultrawide monitor",
        "4k monitor","144hz monitor","240hz monitor",
        "keyboard","gaming keyboard","mechanical keyboard","rgb keyboard",
        "wireless keyboard","compact keyboard","ergonomic keyboard",
        "mouse","gaming mouse","wireless mouse","ergonomic mouse",
        "mouse pad","gaming mouse pad","rgb mouse pad","extended mouse pad",
        "webcam","4k webcam","streaming webcam","document camera",
        "printer","laser printer","inkjet printer","label printer",
        "scanner","projector","mini projector","4k projector",
        "laptop stand","laptop cooling pad","usb hub","docking station",

        # 🎮 Gaming
        "ps5","playstation 5","ps5 digital","ps5 slim","ps5 pro",
        "ps4","playstation 4","xbox series x","xbox series s",
        "xbox one","nintendo switch","switch oled","switch lite",
        "gaming chair","ergonomic chair","racing chair","office chair",
        "gaming desk","gaming table","rgb desk","standing desk",
        "rgb keyboard","mechanical keyboard","gaming keypad",
        "gaming mouse","gaming headset","gaming monitor","gaming laptop",
        "graphics card","gpu","nvidia","amd","rtx","gtx",
        "cpu","processor","intel","amd ryzen","motherboard",
        "ram","ddr4","ddr5","ssd","nvme","hard drive",
        "power supply","pc case","cooling fan","liquid cooler",
        "controller","gamepad","joystick","racing wheel","fight stick",
        "vr headset","meta quest","ps vr","gaming glasses",
        "capture card","streaming equipment","green screen","ring light",

        # 🍫 Food
        "chocolate","dark chocolate","milk chocolate","white chocolate",
        "snacks","chips","crisps","biscuits","cookies",
        "protein bar","energy bar","granola bar","muesli bar",
        "coffee","instant coffee","ground coffee","coffee beans",
        "arabic coffee","turkish coffee","espresso","capsule coffee",
        "tea","green tea","black tea","herbal tea","chai",
        "dates","saudi dates","ajwa dates","sukkari dates","medjool dates",
        "nuts","almonds","cashews","walnuts","pistachios","mixed nuts",
        "honey","raw honey","manuka honey","sidr honey",
        "peanut butter","almond butter","nutella","jam","honey jar",
        "spices","saffron","cardamom","cinnamon","turmeric",
        "olive oil","coconut oil","ghee","butter","cheese",
        "protein powder","whey protein","mass gainer","bcaa",
        "pre workout","creatine","vitamins","supplements","omega 3",
        "baby food","organic food","gluten free","keto food","vegan food",

        # 👶 Kids
        "baby toys","kids toys","educational toys","stem toys",
        "lego","lego blocks","duplo","technic","star wars lego",
        "puzzle","jigsaw puzzle","3d puzzle","wooden puzzle",
        "remote control car","rc car","rc helicopter","rc drone",
        "doll","barbie","baby doll","stuffed animal","plush toy",
        "action figure","superhero toy","cars toy","train set",
        "building blocks","magnetic tiles","play dough","slime",
        "board games","card games","chess","monopoly","scrabble",
        "outdoor toys","swing","slide","trampoline","scooter",
        "baby stroller","pram","baby carrier","baby wrap","diaper bag",
        "baby bottle","sippy cup","baby spoon","baby plate","bib",
        "diapers","baby wipes","diaper pants","swim diapers",
        "baby monitor","baby thermometer","nasal aspirator","baby scale",
        "kids furniture","kids bed","kids table","kids chair",
        "kids backpack","school bag","lunch box","water bottle kids",

        # 🏠 Home
        "air fryer","air fryer oven","deep fryer","pressure cooker",
        "rice cooker","slow cooker","multi cooker","instant pot",
        "blender","juicer","smoothie maker","food processor",
        "coffee machine","espresso machine","capsule machine","french press",
        "vacuum cleaner","robot vacuum","cordless vacuum","stick vacuum",
        "microwave","oven","toaster oven","air fryer oven",
        "kitchen tools","knife set","cutting board","cooking utensils",
        "food storage","lunch box","food container","glass container",
        "water bottle","thermos","flask","cooler bag",
        "home decor","wall art","canvas print","wall clock",
        "curtains","blackout curtains","sheer curtains","curtain rods",
        "bedding","bed sheet","pillow case","duvet cover","comforter",
        "blanket","throw blanket","weighted blanket","electric blanket",
        "pillows","memory foam pillow","orthopedic pillow","pillow set",
        "mattress protector","mattress topper","bed skirt","bed frame",
        "sofa cover","sofa throw","cushion cover","floor mat",
        "bathroom accessories","shower curtain","bath mat","towel set",
        "storage box","organizer","closet organizer","shoe rack",
        "garment rack","laundry basket","ironing board","steam iron",

        # 🏋️ Fitness
        "fitness equipment","home gym","gym equipment","exercise equipment",
        "dumbbells","adjustable dumbbells","dumbbell set","hex dumbbells",
        "kettlebell","kettlebell set","medicine ball","slam ball",
        "yoga mat","exercise mat","gym mat","puzzle mat",
        "treadmill","running machine","elliptical","cross trainer",
        "exercise bike","spin bike","stationary bike","recumbent bike",
        "rowing machine","stair climber","stepper","vibration plate",
        "resistance bands","resistance tube","loop bands","pull up band",
        "jump rope","skipping rope","battle rope","pull up bar",
        "push up bar","ab roller","ab wheel","sit up bench",
        "weight bench","incline bench","flat bench","adjustable bench",
        "power rack","squat rack","smith machine","cable machine",
        "gym gloves","lifting belt","wrist wrap","knee sleeve",
        "foam roller","massage gun","massage ball","lacrosse ball",
        "yoga block","yoga strap","yoga wheel","pilates ring",
        "balance board","bosu ball","stability ball","gym ball",
        "protein powder","whey isolate","casein protein","plant protein",
        "creatine","pre workout","bcaa","eaa","glutamine",
        "fat burner","cla","l carnitine","testosterone booster",
        "multivitamin","fish oil","zma","magnesium","vitamin d",

        # 🚗 Cars
        "car accessories","car interior","car exterior","car care",
        "car charger","fast car charger","wireless car charger",
        "dash cam","car camera","reverse camera","360 camera",
        "car vacuum","handheld vacuum","wet dry vacuum",
        "car organizer","trunk organizer","seat organizer","back seat organizer",
        "car phone holder","car mount","magnetic car mount","cd slot mount",
        "car seat cover","steering wheel cover","floor mat","cargo liner",
        "car freshener","car perfume","air purifier car",
        "jump starter","car battery","battery charger","tire inflator",
        "car cover","sun shade","windshield cover","winter cover",
        "tool kit","emergency kit","first aid kit","tire repair kit",
        "car polish","wax","ceramic coating","paint protection",
        "window tint","headlight restoration","led bulb","hid kit",
        "roof rack","cargo box","bike rack","kayak rack",
        "seat cushion","lumbar support","neck pillow car","blind spot mirror",

        # 💎 Luxury
        "luxury watch","designer watch","swiss watch","automatic watch",
        "smart watch","apple watch","samsung watch","garmin watch",
        "designer bag","handbag","tote bag","crossbody bag","clutch",
        "backpack designer","luggage","suitcase","carry on","travel bag",
        "gold jewelry","silver jewelry","diamond jewelry","pearl jewelry",
        "ring","necklace","bracelet","earrings","pendant","anklet",
        "sunglasses luxury","designer sunglasses","polarized sunglasses",
        "wallet designer","card holder luxury","money clip","cufflinks gold",
        "tie luxury","scarf silk","belt designer","keychain luxury",
        "pen luxury","fountain pen","rollerball pen","ballpoint pen",

        # 🔥 Viral + Trends
        "best seller","top rated","most popular","amazon best seller",
        "trending now","viral product","tiktok made me buy it",
        "amazon choice","amazon recommended","frequently bought together",
        "limited stock","low stock","only few left","selling out fast",
        "fast selling","hot product","bestseller","top 100",
        "top deals today","big discount","huge savings","massive discount",
        "lowest price","price drop","price crash","slashed prices",
        "must buy","recommended","editor choice","staff pick",
        "as seen on tv","social media famous","instagram viral",
        "youtube review","unboxing","haul","favorites",
        "new release","just launched","coming soon","pre order",
        "clearance","final sale","end of season","winter sale","summer sale",
        "black friday","cyber monday","prime day","boxing day",
        "ramadan sale","eid sale","national day sale","founding day sale",
        "flash sale","24 hour deal","12 hour deal","6 hour deal",
        "deal alert","price alert","stock alert","restock alert"
    ]

def build_urls():
    """بناء URLs ضخمة - 20 صفحة لكل كلمة"""
    urls = []
    keywords = get_keywords()
    
    # 🔥 20 صفحة لكل كلمة (ضخم جداً)
    for kw in keywords:
        for page in range(1, 21):  # 20 صفحة بدل 40
            urls.append(f"https://www.amazon.sa/s?k={kw}&page={page}")
    
    # 🔥 الصفحات الرئيسية
    urls.append("https://www.amazon.sa/gp/todays-deals")
    urls.append("https://www.amazon.sa/gp/goldbox")
    urls.append("https://www.amazon.sa/gp/bestsellers")
    urls.append("https://www.amazon.sa/gp/new-releases")
    urls.append("https://www.amazon.sa/gp/movers-and-shakers")
    urls.append("https://www.amazon.sa/gp/most-wished-for")
    urls.append("https://www.amazon.sa/gp/most-gifted")
    urls.append("https://www.amazon.sa/deals")
    urls.append("https://www.amazon.sa/gp/warehouse-deals")
    urls.append("https://www.amazon.sa/outlet")
    urls.append("https://www.amazon.sa/gp/super-savings")
    urls.append("https://www.amazon.sa/gp/price-drop")
    
    # 🔥 أقسام الأكثر مبيعاً حسب الفئة
    categories = [
        "electronics", "fashion", "home", "beauty", "sports", "toys",
        "books", "automotive", "grocery", "health", "kitchen", "office",
        "pet-supplies", "baby", "tools", "industrial", "software"
    ]
    for cat in categories:
        urls.append(f"https://www.amazon.sa/gp/bestsellers/{cat}")
        urls.append(f"https://www.amazon.sa/gp/new-releases/{cat}")
        urls.append(f"https://www.amazon.sa/gp/movers-and-shakers/{cat}")
        urls.append(f"https://www.amazon.sa/deals/{cat}")
    
    # 🔥 صفحات Lightning Deals
    urls.append("https://www.amazon.sa/deals?deals-widget=%257B%2522version%2522%253A1%252C%2522viewIndex%2522%253A0%252C%2522presetId%2522%253A%2522deals-collection-lightning-deals%2522%257D")
    
    # 🔥 صفحات Prime Deals
    urls.append("https://www.amazon.sa/deals?deals-widget=%257B%2522version%2522%253A1%252C%2522viewIndex%2522%253A0%252C%2522presetId%2522%253A%2522deals-collection-prime-exclusive%2522%257D")
    
    # 🔥 صفحات Warehouse
    urls.append("https://www.amazon.sa/gp/warehouse-deals")
    
    # 🔥 صفحات Coupons
    urls.append("https://www.amazon.sa/gp/coupons")
    
    # 🔥 صفحات Renewed
    urls.append("https://www.amazon.sa/gp/bestsellers/renewed")
    
    # 🔥 صفحات Outlet
    urls.append("https://www.amazon.sa/outlet")
    
    # 🔥 صفحات Fashion Deals
    urls.append("https://www.amazon.sa/deals/fashion")
    urls.append("https://www.amazon.sa/deals/beauty")
    urls.append("https://www.amazon.sa/deals/electronics")
    urls.append("https://www.amazon.sa/deals/home")
    urls.append("https://www.amazon.sa/deals/sports")
    urls.append("https://www.amazon.sa/deals/toys")
    urls.append("https://www.amazon.sa/deals/automotive")
    urls.append("https://www.amazon.sa/deals/grocery")
    
    # 🔥 صفحات Under 50, 100, 200
    urls.append("https://www.amazon.sa/s?k=under+50+riyals&s=price-asc-rank")
    urls.append("https://www.amazon.sa/s?k=under+100+riyals&s=price-asc-rank")
    urls.append("https://www.amazon.sa/s?k=under+200+riyals&s=price-asc-rank")
    
    # 🔥 صفحات Discount High to Low
    urls.append("https://www.amazon.sa/s?k=discount&s=discount-desc-rank")
    
    # 🔥 صفحات Price Drop
    urls.append("https://www.amazon.sa/gp/price-drop")
    
    # 🔥 صفحات Today's Deals مع فلاتر
    for i in range(0, 100, 20):
        urls.append(f"https://www.amazon.sa/gp/todays-deals?ie=UTF8&page={i//20 + 1}")
    
    # 🔥 صفحات International Best Sellers
    urls.append("https://www.amazon.sa/gp/bestsellers/imported")
    
    # 🔥 صفحات Super Saving
    urls.append("https://www.amazon.sa/gp/super-savings")
    
    return urls

# ====== SEARCH & PROCESS ======
def search_and_send():
    session = create_session()
    urls = build_urls()
    total_urls = len(urls)
    
    logger.info(f"🔥 Starting search in {total_urls} URLs")
    
    for idx, url in enumerate(urls, 1):
        html = fetch_page(session, url)
        if not html:
            continue
        
        soup = BeautifulSoup(html, 'html.parser')
        items = soup.find_all('div', {'data-component-type': 's-search-result'})
        
        for item in items:
            deal = parse_item(item, "Deal", False)
            if deal:
                prod_id = get_product_id(deal)
                title_hash = create_title_hash(deal['title'])
                
                # إرسال كل المنتجات حتى لو مكررة
                send_to_telegram(deal)
                sent_products.add(prod_id)
                sent_hashes.add(title_hash)
        
        # Log progress every 10 URLs
        if idx % 10 == 0:
            logger.info(f"⏳ Progress: {idx}/{total_urls} URLs processed")
        
        time.sleep(random.uniform(1, 2))
    
    save_database()
    logger.info("✅ Finished sending all deals")

# ====== MAIN ======
if __name__ == "__main__":
    load_database()
    search_and_send()
