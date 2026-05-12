import os
import re
import json
import logging
import requests
import cloudscraper
from datetime import datetime
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from fake_useragent import UserAgent
import time
import random
import hashlib
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from collections import deque, defaultdict

# ================== إعدادات عامة ==================
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = "8769441239:AAEgX3uBbtWc_hHcqs0lmQ50AqKJGOWV6Ok"
PORT = int(os.environ.get("PORT", 10000))

ua = UserAgent()
sent_products = set()
sent_hashes = set()
is_scanning = False
updater = None

# ============ إعدادات البحث ============
MIN_DISCOUNT = 40
MIN_RATING = 3.0

# ✅ الترندينج: منتج يعتبر "ترند" لو عنده مراجعات كتير حتى لو خصمه أقل
TRENDING_MIN_REVIEWS = 500      # 500+ مراجعة = شعبي
TRENDING_MIN_RATING = 4.0       # 4 نجوم+ عشان نضمن الجودة
TRENDING_MIN_DISCOUNT = 10      # خصم 10%+ بس (مش لازم 40%)

CATEGORIES_DEF = [
    # ⭐⭐⭐ BEST SELLERS SAUDI
    ("https://www.amazon.sa/gp/bestsellers", "⭐ Best Sellers - السعودية الكل", 'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/beauty", "⭐ Best Sellers - Beauty & Personal Care", 'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/electronics", "⭐ Best Sellers - Electronics", 'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/home", "⭐ Best Sellers - Home & Kitchen", 'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/automotive", "⭐ Best Sellers - Automotive", 'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/grocery", "⭐ Best Sellers - Grocery", 'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/fashion", "⭐ Best Sellers - Fashion", 'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/sports", "⭐ Best Sellers - Sports", 'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/toys", "⭐ Best Sellers - Toys", 'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/baby", "⭐ Best Sellers - Baby", 'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/pet", "⭐ Best Sellers - Pet Supplies", 'best_sellers'),
    ("https://www.amazon.sa/gp/bestsellers/office", "⭐ Best Sellers - Office", 'best_sellers'),

    # 🔥🔥🔥 DEALS الرسمية
    ("https://www.amazon.sa/gp/goldbox", "🔥 Goldbox - الصفقات اليومية", 'deals'),
    ("https://www.amazon.sa/gp/prime/pipeline/lightning_deals", "⚡ Lightning Deals - عروض فلاش", 'lightning'),
    ("https://www.amazon.sa/gp/todays-deals", "📅 Today's Deals - عروض اليوم", 'today'),
    ("https://www.amazon.sa/gp/warehouse-deals", "🏭 Warehouse - مستعمل ممتاز", 'warehouse'),
    ("https://www.amazon.sa/gp/coupons", "🎟️ Coupons - كوبونات", 'coupons'),
    ("https://www.amazon.sa/outlet", "🎁 Outlet - مخلفات بأسعار مخفضة", 'outlet'),

    # 🍎 APPLE
    ("https://www.amazon.sa/s?k=iphone+15+pro+max&rh=p_8%3A30-99", "🍎 iPhone 15 Pro Max", 'search'),
    ("https://www.amazon.sa/s?k=iphone+15+pro&rh=p_8%3A30-99", "🍎 iPhone 15 Pro", 'search'),
    ("https://www.amazon.sa/s?k=iphone+15&rh=p_8%3A30-99", "🍎 iPhone 15", 'search'),
    ("https://www.amazon.sa/s?k=iphone+14+pro&rh=p_8%3A30-99", "🍎 iPhone 14 Pro", 'search'),
    ("https://www.amazon.sa/s?k=airpods+pro+2&rh=p_8%3A30-99", "🍎 AirPods Pro 2", 'search'),
    ("https://www.amazon.sa/s?k=airpods+max&rh=p_8%3A30-99", "🍎 AirPods Max", 'search'),
    ("https://www.amazon.sa/s?k=apple+watch+ultra+2&rh=p_8%3A30-99", "🍎 Apple Watch Ultra 2", 'search'),
    ("https://www.amazon.sa/s?k=apple+watch+series+9&rh=p_8%3A30-99", "🍎 Apple Watch Series 9", 'search'),
    ("https://www.amazon.sa/s?k=apple+watch+se&rh=p_8%3A30-99", "🍎 Apple Watch SE", 'search'),
    ("https://www.amazon.sa/s?k=ipad+pro+m4&rh=p_8%3A30-99", "🍎 iPad Pro M4", 'search'),
    ("https://www.amazon.sa/s?k=ipad+air+m2&rh=p_8%3A30-99", "🍎 iPad Air M2", 'search'),
    ("https://www.amazon.sa/s?k=ipad+mini&rh=p_8%3A30-99", "🍎 iPad Mini", 'search'),
    ("https://www.amazon.sa/s?k=macbook+pro+m3&rh=p_8%3A30-99", "🍎 MacBook Pro M3", 'search'),
    ("https://www.amazon.sa/s?k=macbook+air+m3&rh=p_8%3A30-99", "🍎 MacBook Air M3", 'search'),
    ("https://www.amazon.sa/s?k=macbook+air+m2&rh=p_8%3A30-99", "🍎 MacBook Air M2", 'search'),
    ("https://www.amazon.sa/s?k=mac+mini+m2&rh=p_8%3A30-99", "🍎 Mac Mini M2", 'search'),
    ("https://www.amazon.sa/s?k=apple+tv+4k&rh=p_8%3A30-99", "🍎 Apple TV 4K", 'search'),
    ("https://www.amazon.sa/s?k=homepod&rh=p_8%3A30-99", "🍎 HomePod", 'search'),
    ("https://www.amazon.sa/s?k=airtag&rh=p_8%3A30-99", "🍎 AirTag", 'search'),
    ("https://www.amazon.sa/s?k=magsafe&rh=p_8%3A30-99", "🍎 MagSafe", 'search'),
    ("https://www.amazon.sa/s?k=apple+pencil&rh=p_8%3A30-99", "🍎 Apple Pencil", 'search'),

    # 📱 SAMSUNG
    ("https://www.amazon.sa/s?k=samsung+galaxy+s24+ultra&rh=p_8%3A30-99", "📱 Galaxy S24 Ultra", 'search'),
    ("https://www.amazon.sa/s?k=samsung+galaxy+s24+plus&rh=p_8%3A30-99", "📱 Galaxy S24 Plus", 'search'),
    ("https://www.amazon.sa/s?k=samsung+galaxy+s24&rh=p_8%3A30-99", "📱 Galaxy S24", 'search'),
    ("https://www.amazon.sa/s?k=samsung+galaxy+z+fold+5&rh=p_8%3A30-99", "📱 Galaxy Z Fold 5", 'search'),
    ("https://www.amazon.sa/s?k=samsung+galaxy+z+flip+5&rh=p_8%3A30-99", "📱 Galaxy Z Flip 5", 'search'),
    ("https://www.amazon.sa/s?k=samsung+galaxy+tab+s9+ultra&rh=p_8%3A30-99", "📱 Galaxy Tab S9 Ultra", 'search'),
    ("https://www.amazon.sa/s?k=samsung+galaxy+tab+s9&rh=p_8%3A30-99", "📱 Galaxy Tab S9", 'search'),
    ("https://www.amazon.sa/s?k=samsung+galaxy+watch+6&rh=p_8%3A30-99", "📱 Galaxy Watch 6", 'search'),
    ("https://www.amazon.sa/s?k=samsung+galaxy+buds+2+pro&rh=p_8%3A30-99", "📱 Galaxy Buds 2 Pro", 'search'),
    ("https://www.amazon.sa/s?k=samsung+galaxy+buds+fe&rh=p_8%3A30-99", "📱 Galaxy Buds FE", 'search'),

    # 🌸 PERFUMES
    ("https://www.amazon.sa/s?k=tom+ford+oud+wood&rh=p_8%3A30-99", "🌸 Tom Ford Oud Wood", 'search'),
    ("https://www.amazon.sa/s?k=tom+ford+black+orchid&rh=p_8%3A30-99", "🌸 Tom Ford Black Orchid", 'search'),
    ("https://www.amazon.sa/s?k=creed+aventus&rh=p_8%3A30-99", "🌸 Creed Aventus", 'search'),
    ("https://www.amazon.sa/s?k=creed+silver+mountain&rh=p_8%3A30-99", "🌸 Creed Silver Mountain", 'search'),
    ("https://www.amazon.sa/s?k=le+labo+santal+33&rh=p_8%3A30-99", "🌸 Le Labo Santal 33", 'search'),
    ("https://www.amazon.sa/s?k=maison+francis+kurkdjian&rh=p_8%3A30-99", "🌸 MFK Baccarat", 'search'),
    ("https://www.amazon.sa/s?k=amouage&rh=p_8%3A30-99", "🌸 Amouage - عربي لاكشري", 'search'),
    ("https://www.amazon.sa/s?k=byredo&rh=p_8%3A30-99", "🌸 Byredo", 'search'),
    ("https://www.amazon.sa/s?k=diptyque&rh=p_8%3A30-99", "🌸 Diptyque", 'search'),
    ("https://www.amazon.sa/s?k=jo+malone&rh=p_8%3A30-99", "🌸 Jo Malone", 'search'),
    ("https://www.amazon.sa/s?k=chanel+bleu&rh=p_8%3A30-99", "🌸 Chanel Bleu", 'search'),
    ("https://www.amazon.sa/s?k=chanel+coco&rh=p_8%3A30-99", "🌸 Chanel Coco", 'search'),
    ("https://www.amazon.sa/s?k=dior+sauvage&rh=p_8%3A30-99", "🌸 Dior Sauvage", 'search'),
    ("https://www.amazon.sa/s?k=dior+jadore&rh=p_8%3A30-99", "🌸 Dior J'adore", 'search'),
    ("https://www.amazon.sa/s?k=gucci+oud&rh=p_8%3A30-99", "🌸 Gucci Oud", 'search'),
    ("https://www.amazon.sa/s?k=versace+eros&rh=p_8%3A30-99", "🌸 Versace Eros", 'search'),
    ("https://www.amazon.sa/s?k=armani+stronger+with+you&rh=p_8%3A30-99", "🌸 Armani Stronger With You", 'search'),
    ("https://www.amazon.sa/s?k=yves+saint+laurent+libre&rh=p_8%3A30-99", "🌸 YSL Libre", 'search'),
    ("https://www.amazon.sa/s?k=reef+perfume&rh=p_8%3A30-99", "🌸 Reef Perfume - سعودي", 'search'),

    # 💄 BEAUTY & SKINCARE
    ("https://www.amazon.sa/s?k=la+mer&rh=p_8%3A30-99", "💆 La Mer", 'search'),
    ("https://www.amazon.sa/s?k=sk+ii&rh=p_8%3A30-99", "💆 SK-II", 'search'),
    ("https://www.amazon.sa/s?k=estee+lauder+advanced+night+repair&rh=p_8%3A30-99", "💆 Estée Lauder ANR", 'search'),
    ("https://www.amazon.sa/s?k=lancome+genifique&rh=p_8%3A30-99", "💆 Lancôme Génifique", 'search'),
    ("https://www.amazon.sa/s?k=clarins+double+serum&rh=p_8%3A30-99", "💆 Clarins Double Serum", 'search'),
    ("https://www.amazon.sa/s?k=johnson+vita+rich&rh=p_8%3A30-99", "💆 Johnson Vita-Rich", 'search'),
    ("https://www.amazon.sa/s?k=herbal+essences+argan&rh=p_8%3A30-99", "💆 Herbal Essences Argan", 'search'),
    ("https://www.amazon.sa/s?k=cosrx+pimple+patch&rh=p_8%3A30-99", "💆 COSRX Pimple Patch", 'search'),
    ("https://www.amazon.sa/s?k=the+ordinary&rh=p_8%3A30-99", "💆 The Ordinary", 'search'),
    ("https://www.amazon.sa/s?k=cerave&rh=p_8%3A30-99", "💆 CeraVe", 'search'),
    ("https://www.amazon.sa/s?k=neutrogena&rh=p_8%3A30-99", "💆 Neutrogena", 'search'),
    ("https://www.amazon.sa/s?k=olay&rh=p_8%3A30-99", "💆 Olay", 'search'),
    ("https://www.amazon.sa/s?k=charlotte+tilbury&rh=p_8%3A30-99", "💄 Charlotte Tilbury", 'search'),
    ("https://www.amazon.sa/s?k=nars&rh=p_8%3A30-99", "💄 NARS", 'search'),
    ("https://www.amazon.sa/s?k=huda+beauty&rh=p_8%3A30-99", "💄 Huda Beauty", 'search'),
    ("https://www.amazon.sa/s?k=fenty+beauty&rh=p_8%3A30-99", "💄 Fenty Beauty", 'search'),
    ("https://www.amazon.sa/s?k=revolution+beauty&rh=p_8%3A30-99", "💄 Revolution Beauty", 'search'),
    ("https://www.amazon.sa/s?k=dabur+amla&rh=p_8%3A30-99", "💆 Dabur Amla", 'search'),
    ("https://www.amazon.sa/s?k=johnson+body+wash&rh=p_8%3A30-99", "🧴 Johnson Body Wash", 'search'),

    # 🏠 HOME & KITCHEN
    ("https://www.amazon.sa/s?k=dyson+v15&rh=p_8%3A30-99", "🏠 Dyson V15", 'search'),
    ("https://www.amazon.sa/s?k=dyson+gen5&rh=p_8%3A30-99", "🏠 Dyson Gen5", 'search'),
    ("https://www.amazon.sa/s?k=dyson+airwrap&rh=p_8%3A30-99", "🏠 Dyson Airwrap", 'search'),
    ("https://www.amazon.sa/s?k=dyson+supersonic&rh=p_8%3A30-99", "🏠 Dyson Supersonic", 'search'),
    ("https://www.amazon.sa/s?k=levoit+air+purifier&rh=p_8%3A30-99", "🏠 Levoit Air Purifier", 'search'),
    ("https://www.amazon.sa/s?k=nespresso+vertuo&rh=p_8%3A30-99", "☕ Nespresso Vertuo", 'search'),
    ("https://www.amazon.sa/s?k=nespresso+original&rh=p_8%3A30-99", "☕ Nespresso Original", 'search'),
    ("https://www.amazon.sa/s?k=breville+barista&rh=p_8%3A30-99", "☕ Breville Barista", 'search'),
    ("https://www.amazon.sa/s?k=kitchenaid+stand+mixer&rh=p_8%3A30-99", "🍳 KitchenAid Stand Mixer", 'search'),
    ("https://www.amazon.sa/s?k=philips+air+fryer+premium&rh=p_8%3A30-99", "🍳 Philips Air Fryer Premium", 'search'),
    ("https://www.amazon.sa/s?k=stanley+tumbler&rh=p_8%3A30-99", "🏠 Stanley Tumbler", 'search'),
    ("https://www.amazon.sa/s?k=vileda&rh=p_8%3A30-99", "🏠 Vileda", 'search'),
    ("https://www.amazon.sa/s?k=downy+fabric+softener&rh=p_8%3A30-99", "🧴 Downy Fabric Softener", 'search'),
    ("https://www.amazon.sa/s?k=fairy+dishwashing&rh=p_8%3A30-99", "🧴 Fairy Dishwashing", 'search'),

    # 🚗 AUTOMOTIVE
    ("https://www.amazon.sa/s?k=showtop+microfiber&rh=p_8%3A30-99", "🚗 ShowTop Microfiber", 'search'),
    ("https://www.amazon.sa/s?k=shell+helix+ultra&rh=p_8%3A30-99", "🚗 Shell Helix Ultra", 'search'),
    ("https://www.amazon.sa/s?k=car+windshield+sun+shade&rh=p_8%3A30-99", "🚗 Car Sun Shade", 'search'),
    ("https://www.amazon.sa/s?k=car+organizer&rh=p_8%3A30-99", "🚗 Car Organizer", 'search'),
    ("https://www.amazon.sa/s?k=garmin+dash+cam&rh=p_8%3A30-99", "🚗 Garmin Dash Cam", 'search'),
    ("https://www.amazon.sa/s?k=chemical+guys&rh=p_8%3A30-99", "🚗 Chemical Guys", 'search'),
    ("https://www.amazon.sa/s?k=jump+starter&rh=p_8%3A30-99", "🚗 Jump Starter", 'search'),
    ("https://www.amazon.sa/s?k=car+phone+mount&rh=p_8%3A30-99", "🚗 Car Phone Mount", 'search'),

    # 👶 BABY
    ("https://www.amazon.sa/s?k=pampers&rh=p_8%3A30-99", "👶 Pampers", 'search'),
    ("https://www.amazon.sa/s?k=waterwipes&rh=p_8%3A30-99", "👶 WaterWipes", 'search'),
    ("https://www.amazon.sa/s?k=bugaboo&rh=p_8%3A30-99", "👶 Bugaboo", 'search'),
    ("https://www.amazon.sa/s?k=philips+avent+premium&rh=p_8%3A30-99", "👶 Philips Avent Premium", 'search'),
    ("https://www.amazon.sa/s?k=medela&rh=p_8%3A30-99", "👶 Medela", 'search'),
    ("https://www.amazon.sa/s?k=fisher+price&rh=p_8%3A30-99", "👶 Fisher-Price", 'search'),
    ("https://www.amazon.sa/s?k=lego+duplo&rh=p_8%3A30-99", "🧱 LEGO DUPLO", 'search'),
    ("https://www.amazon.sa/s?k=doona&rh=p_8%3A30-99", "👶 Doona", 'search'),

    # 🏋️ SPORTS
    ("https://www.amazon.sa/s?k=theragun&rh=p_8%3A30-99", "🏋️ Theragun", 'search'),
    ("https://www.amazon.sa/s?k=oura+ring&rh=p_8%3A30-99", "🏋️ Oura Ring", 'search'),
    ("https://www.amazon.sa/s?k=optimum+nutrition&rh=p_8%3A30-99", "💪 Optimum Nutrition", 'search'),
    ("https://www.amazon.sa/s?k=yoga+mat+premium&rh=p_8%3A30-99", "🧘 Yoga Mat Premium", 'search'),
    ("https://www.amazon.sa/s?k=resistance+bands+set&rh=p_8%3A30-99", "🏋️ Resistance Bands", 'search'),
    ("https://www.amazon.sa/s?k=dumbbells+adjustable&rh=p_8%3A30-99", "🏋️ Dumbbells Adjustable", 'search'),
    ("https://www.amazon.sa/s?k=treadmill+folding&rh=p_8%3A30-99", "🏃 Treadmill Folding", 'search'),

    # 🍳 KITCHEN APPLIANCES
    ("https://www.amazon.sa/s?k=air+fryer+ninja&rh=p_8%3A30-99", "🍳 Ninja Air Fryer", 'search'),
    ("https://www.amazon.sa/s?k=instant+pot&rh=p_8%3A30-99", "🍳 Instant Pot", 'search'),
    ("https://www.amazon.sa/s?k=blender+vitamix&rh=p_8%3A30-99", "🍳 Vitamix Blender", 'search'),
    ("https://www.amazon.sa/s?k=espresso+machine+delonghi&rh=p_8%3A30-99", "☕ DeLonghi Espresso", 'search'),
    ("https://www.amazon.sa/s?k=rice+cooker+zojirushi&rh=p_8%3A30-99", "🍳 Zojirushi Rice Cooker", 'search'),

    # 🏠 SMART HOME
    ("https://www.amazon.sa/s?k=philips+hue&rh=p_8%3A30-99", "💡 Philips Hue", 'search'),
    ("https://www.amazon.sa/s?k=ring+doorbell&rh=p_8%3A30-99", "🏠 Ring Doorbell", 'search'),
    ("https://www.amazon.sa/s?k=roborock&rh=p_8%3A30-99", "🏠 Roborock", 'search'),
    ("https://www.amazon.sa/s?k=irobot+roomba&rh=p_8%3A30-99", "🏠 iRobot Roomba", 'search'),
    ("https://www.amazon.sa/s?k=eufy+security&rh=p_8%3A30-99", "🏠 eufy Security", 'search'),

    # 🍚 GROCERY
    ("https://www.amazon.sa/s?k=nestle+pure+life+water&rh=p_8%3A30-99", "🍚 Nestlé Pure Life Water", 'search'),
    ("https://www.amazon.sa/s?k=basmati+rice&rh=p_8%3A30-99", "🍚 Basmati Rice", 'search'),
    ("https://www.amazon.sa/s?k=almarai+milk&rh=p_8%3A30-99", "🍚 Almarai Milk", 'search'),
    ("https://www.amazon.sa/s?k=vimto&rh=p_8%3A30-99", "🍚 Vimto", 'search'),
    ("https://www.amazon.sa/s?k=nescafe+gold&rh=p_8%3A30-99", "☕ Nescafé Gold", 'search'),
    ("https://www.amazon.sa/s?k=dates+ajwa&rh=p_8%3A30-99", "🍚 Ajwa Dates", 'search'),

    # 💻 LAPTOPS
    ("https://www.amazon.sa/s?k=dell+xps+15&rh=p_8%3A30-99", "💻 Dell XPS 15", 'search'),
    ("https://www.amazon.sa/s?k=hp+spectre&rh=p_8%3A30-99", "💻 HP Spectre", 'search'),
    ("https://www.amazon.sa/s?k=lenovo+thinkpad&rh=p_8%3A30-99", "💻 Lenovo ThinkPad", 'search'),
    ("https://www.amazon.sa/s?k=asus+rog+zephyrus&rh=p_8%3A30-99", "💻 ASUS ROG Zephyrus", 'search'),
    ("https://www.amazon.sa/s?k=razer+blade&rh=p_8%3A30-99", "💻 Razer Blade", 'search'),

    # 🔋 POWER & CHARGING
    ("https://www.amazon.sa/s?k=anker+prime&rh=p_8%3A30-99", "🔋 Anker Prime", 'search'),
    ("https://www.amazon.sa/s?k=ugreen+nexode&rh=p_8%3A30-99", "🔋 UGREEN Nexode", 'search'),
    ("https://www.amazon.sa/s?k=baseus+blade&rh=p_8%3A30-99", "🔋 Baseus Blade", 'search'),
    ("https://www.amazon.sa/s?k=samsung+wireless+charger&rh=p_8%3A30-99", "🔌 Samsung Wireless Charger", 'search'),

    # 🧱 TOYS
    ("https://www.amazon.sa/s?k=lego+technic&rh=p_8%3A30-99", "🧱 LEGO Technic", 'search'),
    ("https://www.amazon.sa/s?k=lego+star+wars&rh=p_8%3A30-99", "🧱 LEGO Star Wars", 'search'),
    ("https://www.amazon.sa/s?k=barbie+dreamhouse&rh=p_8%3A30-99", "👸 Barbie DreamHouse", 'search'),
    ("https://www.amazon.sa/s?k=hot+wheels+track&rh=p_8%3A30-99", "🚗 Hot Wheels Track", 'search'),
    ("https://www.amazon.sa/s?k=nerf+gun&rh=p_8%3A30-99", "🔫 Nerf Gun", 'search'),

    # 💎 JEWELRY & WATCHES
    ("https://www.amazon.sa/s?k=swarovski&rh=p_8%3A30-99", "💎 Swarovski", 'search'),
    ("https://www.amazon.sa/s?k=pandora&rh=p_8%3A30-99", "💎 Pandora", 'search'),
    ("https://www.amazon.sa/s?k=casio+g+shock&rh=p_8%3A30-99", "⌚ Casio G-Shock", 'search'),
    ("https://www.amazon.sa/s?k=garmin+fenix+7&rh=p_8%3A30-99", "⌚ Garmin Fenix 7", 'search'),
    ("https://www.amazon.sa/s?k=tissot&rh=p_8%3A30-99", "⌚ Tissot", 'search'),

    # 👟 SHOES & BAGS
    ("https://www.amazon.sa/s?k=nike+air+jordan&rh=p_8%3A30-99", "👟 Nike Air Jordan", 'search'),
    ("https://www.amazon.sa/s?k=adidas+ultraboost&rh=p_8%3A30-99", "👟 Adidas Ultraboost", 'search'),
    ("https://www.amazon.sa/s?k=hoka&rh=p_8%3A30-99", "👟 HOKA", 'search'),
    ("https://www.amazon.sa/s?k=birkenstock&rh=p_8%3A30-99", "👟 Birkenstock", 'search'),
    ("https://www.amazon.sa/s?k=tumi&rh=p_8%3A30-99", "🎒 TUMI", 'search'),
    ("https://www.amazon.sa/s?k=rimowa&rh=p_8%3A30-99", "🎒 Rimowa", 'search'),

    # 📚 BOOKS & AMAZON DEVICES
    ("https://www.amazon.sa/s?k=kindle+paperwhite&rh=p_8%3A30-99", "📚 Kindle Paperwhite", 'search'),
    ("https://www.amazon.sa/s?k=echo+dot&rh=p_8%3A30-99", "🔊 Echo Dot", 'search'),
    ("https://www.amazon.sa/s?k=fire+tv+stick&rh=p_8%3A30-99", "📺 Fire TV Stick", 'search'),
]

# ================== Trending Tracker ==================
# يتتبع الـ trending خلال كل دورة بحث
trending_tracker = defaultdict(lambda: {
    'title': '',
    'price': 0,
    'old_price': 0,
    'discount': 0,
    'rating': 0,
    'reviews': 0,
    'link': '',
    'category': '',
    'score': 0   # trending score = reviews * rating * (1 + discount/100)
})

last_page_tracker = {cat[1]: 0 for cat in CATEGORIES_DEF}


# ================== Health Server ==================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'OK')

    def log_message(self, format, *args):
        pass

def run_health_server():
    health_port = 8080
    while True:
        try:
            server = HTTPServer(('0.0.0.0', health_port), HealthHandler)
            logger.info(f"🌐 Health server on {health_port}")
            server.serve_forever()
        except Exception as e:
            logger.error(f"Health error: {e}")
            time.sleep(3)


# ================== Database ==================
def load_database():
    global sent_products, sent_hashes, last_page_tracker
    try:
        if os.path.exists('bot_database.json'):
            with open('bot_database.json', 'r') as f:
                data = json.load(f)
                sent_products = set(data.get('ids', []))
                sent_hashes = set(data.get('hashes', []))
                saved_pages = data.get('last_pages', {})
                for cat in CATEGORIES_DEF:
                    if cat[1] in saved_pages:
                        last_page_tracker[cat[1]] = saved_pages[cat[1]]
            logger.info(f"📦 Loaded {len(sent_products)} products")
    except Exception as e:
        logger.error(f"DB Load Error: {e}")

def save_database():
    try:
        with open('bot_database.json', 'w') as f:
            json.dump({
                'ids': list(sent_products)[-5000:],
                'hashes': list(sent_hashes)[-5000:],
                'last_pages': last_page_tracker
            }, f)
    except Exception as e:
        logger.error(f"DB Save Error: {e}")


# ================== أدوات ==================
def extract_asin(link):
    if not link:
        return None
    patterns = [r'/dp/([A-Z0-9]{10})', r'/gp/product/([A-Z0-9]{10})']
    for p in patterns:
        match = re.search(p, link, re.I)
        if match:
            return match.group(1).upper()
    return None

def create_title_hash(title):
    clean = re.sub(r'[^\w\s]', '', title.lower())
    clean = re.sub(r'\s+', ' ', clean).strip()
    return hashlib.md5(clean[:30].encode()).hexdigest()[:16]

def is_similar_product(title):
    return create_title_hash(title) in sent_hashes

def get_product_id(title, link, price):
    asin = extract_asin(link)
    if asin:
        return f"ASIN_{asin}"
    key = f"{title}_{price}"
    return f"HASH_{hashlib.md5(key.encode()).hexdigest()[:12]}"

def get_page_url(base_url, page_num):
    if page_num <= 1:
        return base_url
    if 'page=' in base_url:
        return re.sub(r'page=\d+', f'page={page_num}', base_url)
    elif 's?' in base_url:
        return f"{base_url}&page={page_num}"
    else:
        return f"{base_url}?page={page_num}"

def calc_trending_score(reviews, rating, discount):
    """
    🔥 Trending Score:
    - مراجعات كتير = شعبي
    - تقييم عالي = موثوق
    - خصم = جذاب
    Score = reviews × rating × (1 + discount/100)
    """
    return reviews * rating * (1 + discount / 100)


# ================== Scraper ==================
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

def fetch_page(session, url, retries=2):
    for i in range(retries):
        try:
            time.sleep(random.uniform(1, 3))
            r = session.get(url, timeout=30)
            if r.status_code == 200 and len(r.text) > 5000:
                return r.text
            logger.warning(f"Attempt {i+1} failed: Status {r.status_code}")
            time.sleep(3)
        except Exception as e:
            logger.error(f"Fetch error: {e}")
            time.sleep(3)
    return None

def parse_rating(text):
    if not text:
        return 0
    match = re.search(r'(\d+\.?\d*)', str(text))
    return float(match.group(1)) if match else 0

def parse_item(item, category, is_best_seller=False):
    try:
        # السعر
        price = None
        for sel in ['.a-price-whole', '.a-price .a-offscreen', '.a-price-range', '.a-price']:
            el = item.select_one(sel)
            if el:
                try:
                    txt = el.text.replace(',', '').replace('ريال', '').replace('٬', '').strip()
                    match = re.search(r'[\d,]+\.?\d*', txt)
                    if match:
                        price = float(match.group().replace(',', ''))
                        break
                except:
                    pass

        if not price or price <= 0:
            return None

        # السعر القديم والخصم
        old_price = 0
        discount = 0

        old_el = item.find('span', class_='a-text-price')
        if old_el:
            txt = old_el.get_text()
            match = re.search(r'[\d,]+\.?\d*', txt.replace(',', '').replace('٬', ''))
            if match:
                try:
                    old_price = float(match.group())
                    if old_price > price:
                        discount = int(((old_price - price) / old_price) * 100)
                except:
                    pass

        if discount == 0:
            badge = item.find(string=re.compile(r'(\d+)%'))
            if badge:
                match = re.search(r'(\d+)', str(badge))
                if match:
                    discount = int(match.group())
                    old_price = price / (1 - discount / 100)

        # العنوان
        title = "Unknown"
        for sel in ['h2 a span', 'h2 span', '.a-size-mini span', '.a-size-base-plus', '.a-size-medium']:
            el = item.select_one(sel)
            if el:
                title = el.text.strip()
                if len(title) > 5:
                    break

        # اللينك
        link = ""
        a = item.find('a', href=True)
        if a:
            href = a['href']
            if href.startswith('/'):
                link = f"https://www.amazon.sa{href}"
            elif 'amazon.sa' in href:
                link = href
            else:
                asin = extract_asin(href)
                if asin:
                    link = f"https://www.amazon.sa/dp/{asin}"

        # التقييم
        rating = 0
        rate_el = item.find('span', class_='a-icon-alt')
        if rate_el:
            rating = parse_rating(rate_el.text)

        # المراجعات ✅ مهم للترندينج
        reviews = 0
        for rev_sel in ['span[data-component-type="s-client-side-analytics"]', '.a-size-base', '.a-size-small']:
            rev_el = item.find('span', class_='a-size-base')
            if rev_el:
                match = re.search(r'[\d,]+', rev_el.text)
                if match:
                    try:
                        reviews = int(match.group().replace(',', ''))
                        if reviews > 0:
                            break
                    except:
                        pass

        # ✅ Trending Score
        score = calc_trending_score(reviews, rating, discount)

        return {
            'title': title[:120],
            'price': price,
            'old_price': round(old_price, 2) if old_price > 0 else round(price * 100 / (100 - discount), 2) if discount > 0 else price,
            'discount': discount,
            'rating': rating,
            'reviews': reviews,
            'link': link,
            'category': category,
            'is_best_seller': is_best_seller,
            'score': score,
            'id': get_product_id(title, link, price)
        }

    except Exception as e:
        return None


# ================== Main Search ==================
def search_all_deals(chat_id=None, status_msg_id=None):
    global last_page_tracker, trending_tracker

    # ✅ نصفي الترندينج كل دورة
    trending_tracker = defaultdict(lambda: {
        'title': '', 'price': 0, 'old_price': 0, 'discount': 0,
        'rating': 0, 'reviews': 0, 'link': '', 'category': '', 'score': 0
    })

    all_deals = []
    session = create_session()

    cats = list(CATEGORIES_DEF)
    random.shuffle(cats)

    logger.info(f"🚀 Starting search in {len(cats)} categories...")

    page_counter = 0

    for base_url, cat_name, cat_type in cats:
        start_page = last_page_tracker.get(cat_name, 0) + 1

        for page_num in range(start_page, start_page + 20):
            page_counter += 1

            if cat_type in ['best_sellers', 'deals', 'warehouse', 'coupons', 'lightning', 'today', 'outlet']:
                url = f"{base_url}?page={page_num}" if '?' not in base_url else f"{base_url}&page={page_num}"
            else:
                url = get_page_url(base_url, page_num)

            logger.info(f"🔍 [{cat_name}] Page {page_num} | Deals: {len(all_deals)}")

            if chat_id and status_msg_id and page_counter % 10 == 0:
                try:
                    updater.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=status_msg_id,
                        text=(
                            f"🔍 *جاري البحث...*\n\n"
                            f"📄 صفحات: {page_counter}\n"
                            f"✅ عروض: {len(all_deals)}\n"
                            f"⏳ قسم: {cat_name}"
                        ),
                        parse_mode='Markdown'
                    )
                except:
                    pass

            html = fetch_page(session, url)
            if not html:
                continue

            soup = BeautifulSoup(html, 'html.parser')

            items = []
            if cat_type == 'best_sellers':
                items.extend(soup.find_all('li', class_='zg-item-immersion'))
                items.extend(soup.find_all('div', class_='p13n-sc-uncoverable-faceout'))

            items.extend(soup.find_all('div', {'data-component-type': 's-search-result'}))
            items.extend(soup.find_all('div', {'data-testid': 'deal-card'}))
            items.extend(soup.find_all('div', class_='s-result-item'))

            if len(items) == 0:
                logger.info(f"   ⛔ Empty page, next category")
                break

            for item in items:
                try:
                    deal = parse_item(item, cat_name, cat_type == 'best_sellers')
                    if not deal:
                        continue

                    # ✅ تسجيل الترندينج لكل منتج عنده مراجعات حتى بدون خصم كبير
                    if deal['reviews'] >= TRENDING_MIN_REVIEWS and deal['rating'] >= TRENDING_MIN_RATING:
                        pid = deal['id']
                        if deal['score'] > trending_tracker[pid]['score']:
                            trending_tracker[pid] = deal.copy()

                    # ✅ العروض العادية: خصم 40%+
                    if deal['discount'] >= MIN_DISCOUNT and deal['rating'] >= MIN_RATING:
                        if deal['id'] not in sent_products and not is_similar_product(deal['title']):
                            all_deals.append(deal)
                            logger.info(f"✅ DEAL: {deal['title'][:40]} | {deal['discount']}% | ⭐{deal['rating']}")

                except:
                    continue

            last_page_tracker[cat_name] = page_num
            time.sleep(random.uniform(1, 2))

        # ✅ بعت العروض من كل قسم على طول
        if all_deals:
            logger.info(f"📤 Sending {len(all_deals)} deals from {cat_name}")
            filter_and_send_deals(all_deals, chat_id)
            all_deals = []

    # ✅ في النهاية: ابعت تقرير الترندينج
    send_trending_report(chat_id)

    save_database()
    logger.info("🎯 Search complete!")


def filter_and_send_deals(deals, chat_id):
    if not deals:
        return

    super_deals = [d for d in deals if d['discount'] >= 90]
    normal_deals = [d for d in deals if d['discount'] < 90]

    logger.info(f"🚨 Super: {len(super_deals)} | 🔥 Normal: {len(normal_deals)}")

    # 🚨 السوبر ديلز (90%+)
    if super_deals:
        msg = "🚨🚨🚨 *عروض خرافية 90%+* 🚨🚨🚨\n\n"
        for i, d in enumerate(super_deals, 1):
            savings = d['old_price'] - d['price'] if d['old_price'] > d['price'] else 0
            msg += f"*{i}. {d['title'][:50]}*\n"
            msg += f"💰 {d['price']:.0f} ريال ~~{d['old_price']:.0f}~~\n"
            msg += f"🔥🔥🔥 خصم: *{d['discount']}%* (توفر {savings:.0f} ريال)\n"
            msg += f"⭐ {d['rating']}/5 | 💬 {d['reviews']:,} مراجعة\n"
            msg += f"🏷️ {d['category']}\n"
            msg += f"🔗 [اشتري بسرعة]({d['link']})\n\n"

        try:
            updater.bot.send_message(chat_id=chat_id, text=msg, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Super send error: {e}")
        time.sleep(1)

    # 🔥 العروض العادية (40-89%)
    if normal_deals:
        msg = f"🔥 *عروض رهيبة 40%+* ({len(normal_deals)} منتج)\n\n"
        count = 0
        for i, d in enumerate(normal_deals, 1):
            if d['id'] in sent_products:
                continue
            savings = d['old_price'] - d['price'] if d['old_price'] > d['price'] else 0
            msg += f"*{i}. {d['title'][:50]}*\n"
            msg += f"💰 {d['price']:.0f} ريال ~~{d['old_price']:.0f}~~ (توفر {savings:.0f})\n"
            msg += f"📉 خصم: *{d['discount']}%* | ⭐ {d['rating']}/5"
            if d['reviews'] > 0:
                msg += f" | 💬 {d['reviews']:,}"
            msg += f"\n🏷️ {d['category']}\n"
            msg += f"🔗 [اشتري من هنا]({d['link']})\n\n"
            count += 1

            if count % 5 == 0 or i == len(normal_deals):
                try:
                    updater.bot.send_message(
                        chat_id=chat_id,
                        text=msg,
                        parse_mode='Markdown',
                        disable_web_page_preview=True
                    )
                    msg = ""
                except Exception as e:
                    logger.error(f"Send error: {e}")
                time.sleep(0.5)

            sent_products.add(d['id'])
            sent_hashes.add(create_title_hash(d['title']))

    for d in super_deals:
        sent_products.add(d['id'])
        sent_hashes.add(create_title_hash(d['title']))

    save_database()


# ================== 🔥 TRENDING REPORT ==================
def send_trending_report(chat_id):
    """
    📊 تقرير الترندينج:
    أكتر المنتجات شراءً في المجتمع السعودي
    مرتبين حسب Trending Score (مراجعات × تقييم × خصم)
    """
    if not trending_tracker:
        return

    # ✅ ترتيب حسب الـ score
    all_trending = list(trending_tracker.values())
    all_trending = [p for p in all_trending if p.get('title') and p['title'] != '' and p['link']]
    all_trending.sort(key=lambda x: x['score'], reverse=True)

    top_trending = all_trending[:20]  # أكتر 20 منتج ترند

    if not top_trending:
        logger.info("No trending products found")
        return

    logger.info(f"📊 Sending trending report with {len(top_trending)} products")

    # ✅ رسالة الترندينج
    msg = (
        "📊🔥 *أكتر المنتجات شراءً في السعودية* 🇸🇦\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "_مرتبة حسب: مراجعات الشراء × التقييم × الخصم_\n\n"
    )

    # تقسيم حسب الكاتيجوري
    by_category = defaultdict(list)
    for p in top_trending:
        cat = p.get('category', 'عام')
        # استخراج الإيموجي والاسم الأساسي من الكاتيجوري
        short_cat = cat.split(' - ')[0] if ' - ' in cat else cat
        by_category[short_cat].append(p)

    rank = 1
    for cat_name, products in list(by_category.items())[:8]:  # أكتر 8 أقسام
        if not products:
            continue
        top_in_cat = products[0]  # الأعلى في القسم
        savings = top_in_cat['old_price'] - top_in_cat['price'] if top_in_cat['old_price'] > top_in_cat['price'] else 0

        msg += f"*{rank}. {top_in_cat['title'][:55]}*\n"
        msg += f"   💰 {top_in_cat['price']:.0f} ريال"
        if top_in_cat['discount'] > 0:
            msg += f" | 📉 -{top_in_cat['discount']}%"
        if savings > 0:
            msg += f" (وفّر {savings:.0f})"
        msg += f"\n   ⭐ {top_in_cat['rating']}/5 | 💬 {top_in_cat['reviews']:,} مراجعة"
        msg += f"\n   🏷️ {cat_name}"
        msg += f"\n   🔗 [تسوق الآن]({top_in_cat['link']})\n\n"
        rank += 1

    msg += "━━━━━━━━━━━━━━━━━━━━\n"
    msg += f"📈 *اجمالي منتجات رصدها البوت: {len(all_trending):,}*"

    try:
        updater.bot.send_message(
            chat_id=chat_id,
            text=msg,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        logger.info("✅ Trending report sent!")
    except Exception as e:
        logger.error(f"Trending report send error: {e}")
        # لو الرسالة طويلة أوي، ابعتها على أجزاء
        try:
            lines = msg.split('\n\n')
            chunk = ""
            for line in lines:
                if len(chunk) + len(line) < 4000:
                    chunk += line + "\n\n"
                else:
                    updater.bot.send_message(chat_id=chat_id, text=chunk, parse_mode='Markdown', disable_web_page_preview=True)
                    chunk = line + "\n\n"
                    time.sleep(0.5)
            if chunk:
                updater.bot.send_message(chat_id=chat_id, text=chunk, parse_mode='Markdown', disable_web_page_preview=True)
        except Exception as e2:
            logger.error(f"Trending fallback error: {e2}")


# ================== أوامر ==================
def start_cmd(update: Update, context: CallbackContext):
    welcome = """👋 *أهلا بيك في بوت عروض أمازون السعودية!*

🔥 *مميزات البوت:*
• يدور في *120+ قسم* مختلف
• يخلص *كل قسم كامل* (كل الصفحات)
• خصومات *40%+* | تقييم *3 نجوم+*
• عروض *90%+* بشكل خاص 🚨
• *تقرير الترندينج* في نهاية كل بحث 📊
• مخصص *100% للسوق السعودي* 🇸🇦

اكتب *Hi* عشان تبدأ البحث!"""
    update.message.reply_text(welcome, parse_mode='Markdown')

def hi_cmd(update: Update, context: CallbackContext):
    global is_scanning

    if is_scanning:
        update.message.reply_text("⏳ البوت شغال في بحث تاني... استنى شوية!")
        return

    is_scanning = True
    chat_id = update.effective_chat.id

    status_msg = update.message.reply_text(
        "🔍 *بدأت البحث...*\n"
        "📄 بدور في كل الأقسام والصفحات\n"
        "⏳ *الوقت المتوقع: 10-15 دقيقة*\n\n"
        "📊 *في النهاية هبعتلك تقرير أكتر المنتجات شراءً*",
        parse_mode='Markdown'
    )

    try:
        search_all_deals(chat_id, status_msg.message_id)

        try:
            updater.bot.delete_message(chat_id, status_msg.message_id)
        except:
            pass

        updater.bot.send_message(
            chat_id=chat_id,
            text=(
                "✅ *خلصت البحث!*\n\n"
                "📦 كل الأقسام اتبحثت\n"
                "🔥 العروض اتبعتت لك\n"
                "📊 تقرير الترندينج اتبعت\n\n"
                "اكتب *Hi* عشان تبدأ بحث جديد!"
            ),
            parse_mode='Markdown'
        )

    except Exception as e:
        logger.error(f"Error: {e}")
        try:
            updater.bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_msg.message_id,
                text=f"❌ حصل خطأ: {str(e)[:100]}\n🔄 جرب تاني!"
            )
        except:
            update.message.reply_text(f"❌ خطأ: {str(e)[:100]}")
    finally:
        is_scanning = False

def status_cmd(update: Update, context: CallbackContext):
    total_cats = len(CATEGORIES_DEF)
    msg = f"""✅ *البوت شغال تمام!*

📦 منتجات متبعتة: *{len(sent_products)}*
📁 عدد الأقسام: *{total_cats}*
📉 الحد الأدنى للخصم: *{MIN_DISCOUNT}%*
⭐ الحد الأدنى للتقييم: *{MIN_RATING}*
📊 معيار الترندينج: *{TRENDING_MIN_REVIEWS}+ مراجعة*

🇸🇦 *مخصص للسوق السعودي*

اكتب *Hi* عشان تبدأ بحث جديد!"""
    update.message.reply_text(msg, parse_mode='Markdown')


# ================== تشغيل ==================
def start_bot():
    global updater

    load_database()

    updater = Updater(token=TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start_cmd))
    dp.add_handler(CommandHandler("status", status_cmd))
    dp.add_handler(MessageHandler(Filters.regex(r'(?i)^hi$') & Filters.text, hi_cmd))

    logger.info("🤖 Bot started!")
    logger.info(f"📁 Categories: {len(CATEGORIES_DEF)}")
    logger.info("🎯 Mode: Full scan + Trending Report")

    updater.start_polling(drop_pending_updates=True, timeout=30)
    updater.idle()


def main():
    threading.Thread(target=run_health_server, daemon=True).start()
    time.sleep(2)

    while True:
        try:
            start_bot()
        except Exception as e:
            logger.error(f"Crash: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
