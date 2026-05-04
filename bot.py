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
from collections import deque

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
# ❌❌❌ ملغي: مفيش عدد محدد - يخلص القسم كله
MIN_DISCOUNT = 40          # خصم 40%+
MIN_RATING = 3.0           # 3 نجوم+

# ✅ الأقسام مرتبة حسب البيانات الفعلية لسوق السعودية 2026
# الأرقام: 1-12 Best Sellers | 13-18 Deals | 19-39 Apple | 40-49 Samsung
# 50-69 Perfumes | 70-89 Beauty | 90-109 Home | 110-129 Fashion
# 130-149 Automotive | 150-169 Baby | 170-189 Sports | 190-209 Kitchen
# 210-229 Smart Home | 230-249 Grocery | 250-269 Laptops | 270-289 Power
# 290-309 General Electronics | 310-329 Toys | 330-349 Jewelry
# 350-369 Watches | 370-389 Sunglasses | 390-409 Shoes
# 410-429 Bags | 430-449 Books | 450-469 Office

CATEGORIES_DEF = [
    # ⭐⭐⭐ BEST SELLERS SAUDI - أولوية قصوى (الأقسام 1-12)
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
    
    # 🔥🔥🔥 DEALS الرسمية - ثاني أولوية (الأقسام 13-18)
    ("https://www.amazon.sa/gp/goldbox", "🔥 Goldbox - الصفقات اليومية", 'deals'),
    ("https://www.amazon.sa/gp/prime/pipeline/lightning_deals", "⚡ Lightning Deals - عروض فلاش", 'lightning'),
    ("https://www.amazon.sa/gp/todays-deals", "📅 Today's Deals - عروض اليوم", 'today'),
    ("https://www.amazon.sa/gp/warehouse-deals", "🏭 Warehouse - مستعمل ممتاز", 'warehouse'),
    ("https://www.amazon.sa/gp/coupons", "🎟️ Coupons - كوبونات", 'coupons'),
    ("https://www.amazon.sa/outlet", "🎁 Outlet - مخلفات بأسعار مخفضة", 'outlet'),
    
    # 🍎🍎🍎 APPLE - ربحية خرافية للأفلييت في السعودية (الأقسام 19-39)
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
    
    # 📱📱📱 SAMSUNG - منافس Apple في السعودية (الأقسام 40-49)
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
    
    # 🌸🌸🌸 PERFUMES - السعوديون الأكثر إنفاقاً على العطور عالمياً (الأقسام 50-69)
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
    
    # 💄💄💄 BEAUTY & SKINCARE - الأكثر مبيعاً في السعودية (الأقسام 70-89)
    ("https://www.amazon.sa/s?k=la+mer&rh=p_8%3A30-99", "💆 La Mer", 'search'),
    ("https://www.amazon.sa/s?k=sk+ii&rh=p_8%3A30-99", "💆 SK-II", 'search'),
    ("https://www.amazon.sa/s?k=estee+lauder+advanced+night+repair&rh=p_8%3A30-99", "💆 Estée Lauder ANR", 'search'),
    ("https://www.amazon.sa/s?k=lancome+genifique&rh=p_8%3A30-99", "💆 Lancôme Génifique", 'search'),
    ("https://www.amazon.sa/s?k=clarins+double+serum&rh=p_8%3A30-99", "💆 Clarins Double Serum", 'search'),
    ("https://www.amazon.sa/s?k=johnson+vita+rich&rh=p_8%3A30-99", "💆 Johnson Vita-Rich - #1", 'search'),
    ("https://www.amazon.sa/s?k=herbal+essences+argan&rh=p_8%3A30-99", "💆 Herbal Essences Argan - #2", 'search'),
    ("https://www.amazon.sa/s?k=cosrx+pimple+patch&rh=p_8%3A30-99", "💆 COSRX Pimple Patch", 'search'),
    ("https://www.amazon.sa/s?k=mighty+patch&rh=p_8%3A30-99", "💆 Mighty Patch", 'search'),
    ("https://www.amazon.sa/s?k=the+ordinary&rh=p_8%3A30-99", "💆 The Ordinary", 'search'),
    ("https://www.amazon.sa/s?k=cerave&rh=p_8%3A30-99", "💆 CeraVe", 'search'),
    ("https://www.amazon.sa/s?k=neutrogena&rh=p_8%3A30-99", "💆 Neutrogena", 'search'),
    ("https://www.amazon.sa/s?k=olay&rh=p_8%3A30-99", "💆 Olay", 'search'),
    ("https://www.amazon.sa/s?k=charlotte+tilbury&rh=p_8%3A30-99", "💄 Charlotte Tilbury", 'search'),
    ("https://www.amazon.sa/s?k=nars&rh=p_8%3A30-99", "💄 NARS", 'search'),
    ("https://www.amazon.sa/s?k=huda+beauty&rh=p_8%3A30-99", "💄 Huda Beauty", 'search'),
    ("https://www.amazon.sa/s?k=fenty+beauty&rh=p_8%3A30-99", "💄 Fenty Beauty", 'search'),
    ("https://www.amazon.sa/s?k=revolution+beauty&rh=p_8%3A30-99", "💄 Revolution Beauty - #1", 'search'),
    ("https://www.amazon.sa/s?k=dabur+amla&rh=p_8%3A30-99", "💆 Dabur Amla - #1 Hair", 'search'),
    ("https://www.amazon.sa/s?k=johnson+body+wash&rh=p_8%3A30-99", "🧴 Johnson Body Wash - #1 Bath", 'search'),
    
    # 🏠🏠🏠 HOME & KITCHEN - الأكثر مبيعاً في السعودية (الأقسام 90-109)
    ("https://www.amazon.sa/s?k=dyson+v15&rh=p_8%3A30-99", "🏠 Dyson V15", 'search'),
    ("https://www.amazon.sa/s?k=dyson+gen5&rh=p_8%3A30-99", "🏠 Dyson Gen5", 'search'),
    ("https://www.amazon.sa/s?k=dyson+airwrap&rh=p_8%3A30-99", "🏠 Dyson Airwrap", 'search'),
    ("https://www.amazon.sa/s?k=dyson+supersonic&rh=p_8%3A30-99", "🏠 Dyson Supersonic", 'search'),
    ("https://www.amazon.sa/s?k=levoit+air+purifier&rh=p_8%3A30-99", "🏠 Levoit Air Purifier - #1", 'search'),
    ("https://www.amazon.sa/s?k=nespresso+vertuo&rh=p_8%3A30-99", "☕ Nespresso Vertuo", 'search'),
    ("https://www.amazon.sa/s?k=nespresso+original&rh=p_8%3A30-99", "☕ Nespresso Original", 'search'),
    ("https://www.amazon.sa/s?k=breville+barista&rh=p_8%3A30-99", "☕ Breville Barista", 'search'),
    ("https://www.amazon.sa/s?k=kitchenaid+stand+mixer&rh=p_8%3A30-99", "🍳 KitchenAid Stand Mixer", 'search'),
    ("https://www.amazon.sa/s?k=philips+air+fryer+premium&rh=p_8%3A30-99", "🍳 Philips Air Fryer Premium", 'search'),
    ("https://www.amazon.sa/s?k=lg+instaview&rh=p_8%3A30-99", "❄️ LG InstaView", 'search'),
    ("https://www.amazon.sa/s?k=samsung+bespoke&rh=p_8%3A30-99", "❄️ Samsung Bespoke", 'search'),
    ("https://www.amazon.sa/s?k=stanley+tumbler&rh=p_8%3A30-99", "🏠 Stanley Tumbler - ترندي", 'search'),
    ("https://www.amazon.sa/s?k=owala&rh=p_8%3A30-99", "🏠 Owala", 'search'),
    ("https://www.amazon.sa/s?k=vileda&rh=p_8%3A30-99", "🏠 Vileda - #1 Home", 'search'),
    ("https://www.amazon.sa/s?k=ultrean&rh=p_8%3A30-99", "🏠 Ultrean", 'search'),
    ("https://www.amazon.sa/s?k=smeg&rh=p_8%3A30-99", "🏠 Smeg", 'search'),
    ("https://www.amazon.sa/s?k=downy+fabric+softener&rh=p_8%3A30-99", "🧴 Downy Fabric Softener", 'search'),
    ("https://www.amazon.sa/s?k=comfort+fabric+softener&rh=p_8%3A30-99", "🧴 Comfort Fabric Softener", 'search'),
    ("https://www.amazon.sa/s?k=fairy+dishwashing&rh=p_8%3A30-99", "🧴 Fairy Dishwashing - #1", 'search'),
    
    # 🧳🧳🧳 FASHION & LUGGAGE - الأكثر مبيعاً في السعودية (الأقسام 110-129)
    ("https://www.amazon.sa/s?k=sky+touch+luggage+organizer&rh=p_8%3A30-99", "🧳 SKY-TOUCH Luggage Organizer - #1", 'search'),
    ("https://www.amazon.sa/s?k=joto+water+shoes&rh=p_8%3A30-99", "👟 JOTO Water Shoes - #2", 'search'),
    ("https://www.amazon.sa/s?k=cotton+crew+socks&rh=p_8%3A30-99", "🧦 Cotton Crew Socks", 'search'),
    ("https://www.amazon.sa/s?k=luggage+scale&rh=p_8%3A30-99", "🧳 Luggage Scale", 'search'),
    ("https://www.amazon.sa/s?k=nike+air+jordan&rh=p_8%3A30-99", "👟 Nike Air Jordan", 'search'),
    ("https://www.amazon.sa/s?k=nike+dunk&rh=p_8%3A30-99", "👟 Nike Dunk", 'search'),
    ("https://www.amazon.sa/s?k=adidas+ultraboost&rh=p_8%3A30-99", "👟 Adidas Ultraboost", 'search'),
    ("https://www.amazon.sa/s?k=new+balance+990&rh=p_8%3A30-99", "👟 New Balance 990", 'search'),
    ("https://www.amazon.sa/s?k=asics+gel+kayano&rh=p_8%3A30-99", "👟 ASICS Gel Kayano", 'search'),
    ("https://www.amazon.sa/s?k=hoka&rh=p_8%3A30-99", "👟 HOKA", 'search'),
    ("https://www.amazon.sa/s?k=on+running&rh=p_8%3A30-99", "👟 On Running", 'search'),
    ("https://www.amazon.sa/s?k=salomon&rh=p_8%3A30-99", "👟 Salomon", 'search'),
    ("https://www.amazon.sa/s?k=ray+ban+aviator&rh=p_8%3A30-99", "🕶️ Ray-Ban Aviator", 'search'),
    ("https://www.amazon.sa/s?k=ray+ban+wayfarer&rh=p_8%3A30-99", "🕶️ Ray-Ban Wayfarer", 'search'),
    ("https://www.amazon.sa/s?k=oakley+holbrook&rh=p_8%3A30-99", "🕶️ Oakley Holbrook", 'search'),
    ("https://www.amazon.sa/s?k=prada+sunglasses&rh=p_8%3A30-99", "🕶️ Prada", 'search'),
    ("https://www.amazon.sa/s?k=gucci+sunglasses&rh=p_8%3A30-99", "🕶️ Gucci", 'search'),
    ("https://www.amazon.sa/s?k=versace+sunglasses&rh=p_8%3A30-99", "🕶️ Versace", 'search'),
    ("https://www.amazon.sa/s?k=burberry+sunglasses&rh=p_8%3A30-99", "🕶️ Burberry", 'search'),
    ("https://www.amazon.sa/s?k=tumi+luggage&rh=p_8%3A30-99", "🧳 TUMI - بريميوم", 'search'),
    
    # 🚗🚗🚗 AUTOMOTIVE - الأكثر مبيعاً في السعودية (الأقسام 130-149)
    ("https://www.amazon.sa/s?k=showtop+microfiber&rh=p_8%3A30-99", "🚗 ShowTop Microfiber - #1", 'search'),
    ("https://www.amazon.sa/s?k=shell+helix+ultra&rh=p_8%3A30-99", "🚗 Shell Helix Ultra - #2", 'search'),
    ("https://www.amazon.sa/s?k=car+windshield+sun+shade&rh=p_8%3A30-99", "🚗 Car Sun Shade", 'search'),
    ("https://www.amazon.sa/s?k=car+seat+gap+storage&rh=p_8%3A30-99", "🚗 Car Seat Gap Storage", 'search'),
    ("https://www.amazon.sa/s?k=car+organizer&rh=p_8%3A30-99", "🚗 Car Organizer", 'search'),
    ("https://www.amazon.sa/s?k=michelin+pilot+sport&rh=p_8%3A30-99", "🚗 Michelin Pilot Sport", 'search'),
    ("https://www.amazon.sa/s?k=continental+premiumcontact&rh=p_8%3A30-99", "🚗 Continental PremiumContact", 'search'),
    ("https://www.amazon.sa/s?k=garmin+dash+cam&rh=p_8%3A30-99", "🚗 Garmin Dash Cam", 'search'),
    ("https://www.amazon.sa/s?k=chemical+guys&rh=p_8%3A30-99", "🚗 Chemical Guys", 'search'),
    ("https://www.amazon.sa/s?k=adam%27s+polishes&rh=p_8%3A30-99", "🚗 Adam's Polishes", 'search'),
    ("https://www.amazon.sa/s?k=car+vacuum&rh=p_8%3A30-99", "🚗 Car Vacuum", 'search'),
    ("https://www.amazon.sa/s?k=car+air+freshener&rh=p_8%3A30-99", "🚗 Car Air Freshener", 'search'),
    ("https://www.amazon.sa/s?k=tire+inflator&rh=p_8%3A30-99", "🚗 Tire Inflator", 'search'),
    ("https://www.amazon.sa/s?k=jump+starter&rh=p_8%3A30-99", "🚗 Jump Starter", 'search'),
    ("https://www.amazon.sa/s?k=dash+cam+4k&rh=p_8%3A30-99", "🚗 Dash Cam 4K", 'search'),
    ("https://www.amazon.sa/s?k=car+phone+mount&rh=p_8%3A30-99", "🚗 Car Phone Mount", 'search'),
    ("https://www.amazon.sa/s?k=car+charger+fast&rh=p_8%3A30-99", "🚗 Car Charger Fast", 'search'),
    ("https://www.amazon.sa/s?k=seat+cover+leather&rh=p_8%3A30-99", "🚗 Seat Cover Leather", 'search'),
    ("https://www.amazon.sa/s?k=steering+wheel+cover&rh=p_8%3A30-99", "🚗 Steering Wheel Cover", 'search'),
    ("https://www.amazon.sa/s?k=car+mat+premium&rh=p_8%3A30-99", "🚗 Car Mat Premium", 'search'),
    
    # 👶👶👶 BABY - الأكثر مبيعاً في السعودية (الأقسام 150-169)
    ("https://www.amazon.sa/s?k=pampers&rh=p_8%3A30-99", "👶 Pampers - #1", 'search'),
    ("https://www.amazon.sa/s?k=waterwipes&rh=p_8%3A30-99", "👶 WaterWipes - #2", 'search'),
    ("https://www.amazon.sa/s?k=bugaboo&rh=p_8%3A30-99", "👶 Bugaboo - بريميوم", 'search'),
    ("https://www.amazon.sa/s?k=stokke&rh=p_8%3A30-99", "👶 Stokke - نرويجي", 'search'),
    ("https://www.amazon.sa/s?k=cybex+priam&rh=p_8%3A30-99", "👶 Cybex Priam", 'search'),
    ("https://www.amazon.sa/s?k=nuna&rh=p_8%3A30-99", "👶 Nuna", 'search'),
    ("https://www.amazon.sa/s?k=philips+avent+premium&rh=p_8%3A30-99", "👶 Philips Avent Premium", 'search'),
    ("https://www.amazon.sa/s?k=medela&rh=p_8%3A30-99", "👶 Medela", 'search'),
    ("https://www.amazon.sa/s?k=willow+pump&rh=p_8%3A30-99", "👶 Willow Pump", 'search'),
    ("https://www.amazon.sa/s?k=elvie&rh=p_8%3A30-99", "👶 Elvie", 'search'),
    ("https://www.amazon.sa/s?k=owlet&rh=p_8%3A30-99", "👶 Owlet - مونيتور ذكي", 'search'),
    ("https://www.amazon.sa/s?k=fisher+price&rh=p_8%3A30-99", "👶 Fisher-Price", 'search'),
    ("https://www.amazon.sa/s?k=melissa+doug&rh=p_8%3A30-99", "👶 Melissa & Doug", 'search'),
    ("https://www.amazon.sa/s?k=lego+duplo&rh=p_8%3A30-99", "🧱 LEGO DUPLO", 'search'),
    ("https://www.amazon.sa/s?k=vtech&rh=p_8%3A30-99", "👶 VTech", 'search'),
    ("https://www.amazon.sa/s?k=skip+hop&rh=p_8%3A30-99", "👶 Skip Hop", 'search'),
    ("https://www.amazon.sa/s?k=ergobaby&rh=p_8%3A30-99", "👶 Ergobaby", 'search'),
    ("https://www.amazon.sa/s?k=baby+bjorn&rh=p_8%3A30-99", "👶 BabyBjörn", 'search'),
    ("https://www.amazon.sa/s?k=doona&rh=p_8%3A30-99", "👶 Doona - ترندي", 'search'),
    ("https://www.amazon.sa/s?k=uppababy&rh=p_8%3A30-99", "👶 UPPAbaby - أمريكي", 'search'),
    
    # 🏋️🏋️🏋️ SPORTS & FITNESS - السعوديون يهتمون باللياقة (الأقسام 170-189)
    ("https://www.amazon.sa/s?k=bowflex&rh=p_8%3A30-99", "🏋️ Bowflex", 'search'),
    ("https://www.amazon.sa/s?k=nordictrack&rh=p_8%3A30-99", "🏋️ NordicTrack", 'search'),
    ("https://www.amazon.sa/s?k=peloton&rh=p_8%3A30-99", "🏋️ Peloton", 'search'),
    ("https://www.amazon.sa/s?k=concept2&rh=p_8%3A30-99", "🏋️ Concept2", 'search'),
    ("https://www.amazon.sa/s?k=theragun&rh=p_8%3A30-99", "🏋️ Theragun", 'search'),
    ("https://www.amazon.sa/s?k=hyperice&rh=p_8%3A30-99", "🏋️ Hyperice", 'search'),
    ("https://www.amazon.sa/s?k=whoop&rh=p_8%3A30-99", "🏋️ WHOOP", 'search'),
    ("https://www.amazon.sa/s?k=oura+ring&rh=p_8%3A30-99", "🏋️ Oura Ring", 'search'),
    ("https://www.amazon.sa/s?k=optimum+nutrition&rh=p_8%3A30-99", "💪 Optimum Nutrition", 'search'),
    ("https://www.amazon.sa/s?k=dymatize+iso+100&rh=p_8%3A30-99", "💪 Dymatize ISO100", 'search'),
    ("https://www.amazon.sa/s?k=cellucor+c4&rh=p_8%3A30-99", "💪 Cellucor C4", 'search'),
    ("https://www.amazon.sa/s?k=bicycle&rh=p_8%3A30-99", "🚲 Bicycle", 'search'),
    ("https://www.amazon.sa/s?k=camping&rh=p_8%3A30-99", "⛺ Camping", 'search'),
    ("https://www.amazon.sa/s?k=yoga+mat+premium&rh=p_8%3A30-99", "🧘 Yoga Mat Premium", 'search'),
    ("https://www.amazon.sa/s?k=resistance+bands+set&rh=p_8%3A30-99", "🏋️ Resistance Bands", 'search'),
    ("https://www.amazon.sa/s?k=kettlebell+set&rh=p_8%3A30-99", "🏋️ Kettlebell Set", 'search'),
    ("https://www.amazon.sa/s?k=dumbbells+adjustable&rh=p_8%3A30-99", "🏋️ Dumbbells Adjustable", 'search'),
    ("https://www.amazon.sa/s?k=treadmill+folding&rh=p_8%3A30-99", "🏃 Treadmill Folding", 'search'),
    ("https://www.amazon.sa/s?k=elliptical+machine&rh=p_8%3A30-99", "🏃 Elliptical Machine", 'search'),
    ("https://www.amazon.sa/s?k=rowing+machine&rh=p_8%3A30-99", "🏃 Rowing Machine", 'search'),
    
    # 🍳🍳🍳 KITCHEN APPLIANCES - بديل Gaming (الأقسام 190-209)
    ("https://www.amazon.sa/s?k=air+fryer+ninja&rh=p_8%3A30-99", "🍳 Ninja Air Fryer - #1", 'search'),
    ("https://www.amazon.sa/s?k=instant+pot&rh=p_8%3A30-99", "🍳 Instant Pot - ترندي", 'search'),
    ("https://www.amazon.sa/s?k=crock+pot&rh=p_8%3A30-99", "🍳 Crock-Pot", 'search'),
    ("https://www.amazon.sa/s?k=food+processor+magimix&rh=p_8%3A30-99", "🍳 Magimix Food Processor", 'search'),
    ("https://www.amazon.sa/s?k=blender+vitamix&rh=p_8%3A30-99", "🍳 Vitamix Blender", 'search'),
    ("https://www.amazon.sa/s?k=blender+ninja&rh=p_8%3A30-99", "🍳 Ninja Blender", 'search'),
    ("https://www.amazon.sa/s?k=stand+mixer+artisan&rh=p_8%3A30-99", "🍳 KitchenAid Artisan", 'search'),
    ("https://www.amazon.sa/s?k=espresso+machine+breville&rh=p_8%3A30-99", "☕ Breville Espresso", 'search'),
    ("https://www.amazon.sa/s?k=espresso+machine+delonghi&rh=p_8%3A30-99", "☕ DeLonghi Espresso", 'search'),
    ("https://www.amazon.sa/s?k=coffee+maker+moccamaster&rh=p_8%3A30-99", "☕ Moccamaster - التوب", 'search'),
    ("https://www.amazon.sa/s?k=sous+vide+anova&rh=p_8%3A30-99", "🍳 Anova Sous Vide", 'search'),
    ("https://www.amazon.sa/s?k=waffle+maker&rh=p_8%3A30-99", "🍳 Waffle Maker", 'search'),
    ("https://www.amazon.sa/s?k=rice+cooker+zojirushi&rh=p_8%3A30-99", "🍳 Zojirushi Rice Cooker", 'search'),
    ("https://www.amazon.sa/s?k=toaster+oven+breville&rh=p_8%3A30-99", "🍳 Breville Toaster Oven", 'search'),
    ("https://www.amazon.sa/s?k=microwave+panasonic&rh=p_8%3A30-99", "📡 Panasonic Microwave", 'search'),
    ("https://www.amazon.sa/s?k=juicer+hurom&rh=p_8%3A30-99", "🍹 Hurom Juicer", 'search'),
    ("https://www.amazon.sa/s?k=juicer+breville&rh=p_8%3A30-99", "🍹 Breville Juicer", 'search'),
    ("https://www.amazon.sa/s?k=meat+grinder&rh=p_8%3A30-99", "🍳 Meat Grinder", 'search'),
    ("https://www.amazon.sa/s?k=pasta+maker&rh=p_8%3A30-99", "🍳 Pasta Maker", 'search'),
    ("https://www.amazon.sa/s?k=ice+cream+maker&rh=p_8%3A30-99", "🍦 Ice Cream Maker", 'search'),
    
    # 🏠🏠🏠 SMART HOME - بديل TVs (الأقسام 210-229)
    ("https://www.amazon.sa/s?k=philips+hue&rh=p_8%3A30-99", "💡 Philips Hue", 'search'),
    ("https://www.amazon.sa/s?k=ring+doorbell&rh=p_8%3A30-99", "🏠 Ring Doorbell", 'search'),
    ("https://www.amazon.sa/s?k=arlo+pro&rh=p_8%3A30-99", "🏠 Arlo Pro", 'search'),
    ("https://www.amazon.sa/s?k=nest+thermostat&rh=p_8%3A30-99", "🏠 Nest Thermostat", 'search'),
    ("https://www.amazon.sa/s?k=roborock&rh=p_8%3A30-99", "🏠 Roborock", 'search'),
    ("https://www.amazon.sa/s?k=ecovacs&rh=p_8%3A30-99", "🏠 Ecovacs", 'search'),
    ("https://www.amazon.sa/s?k=irobot+roomba&rh=p_8%3A30-99", "🏠 iRobot Roomba", 'search'),
    ("https://www.amazon.sa/s?k=wyze&rh=p_8%3A30-99", "🏠 Wyze", 'search'),
    ("https://www.amazon.sa/s?k=eufy+security&rh=p_8%3A30-99", "🏠 eufy Security", 'search'),
    ("https://www.amazon.sa/s?k=aqara&rh=p_8%3A30-99", "🏠 Aqara - سمارت هوم", 'search'),
    ("https://www.amazon.sa/s?k=zigbee+hub&rh=p_8%3A30-99", "🏠 Zigbee Hub", 'search'),
    ("https://www.amazon.sa/s?k=smart+lock+yale&rh=p_8%3A30-99", "🏠 Yale Smart Lock", 'search'),
    ("https://www.amazon.sa/s?k=smart+lock+august&rh=p_8%3A30-99", "🏠 August Smart Lock", 'search'),
    ("https://www.amazon.sa/s?k=video+doorbell+ezviz&rh=p_8%3A30-99", "🏠 EZVIZ Doorbell", 'search'),
    ("https://www.amazon.sa/s?k=security+camera+reolink&rh=p_8%3A30-99", "🏠 Reolink Camera", 'search'),
    ("https://www.amazon.sa/s?k=smart+plug+kasa&rh=p_8%3A30-99", "🏠 Kasa Smart Plug", 'search'),
    ("https://www.amazon.sa/s?k=smart+switch+leviton&rh=p_8%3A30-99", "🏠 Leviton Smart Switch", 'search'),
    ("https://www.amazon.sa/s?k=air+purifier+levoit&rh=p_8%3A30-99", "🏠 Levoit Air Purifier", 'search'),
    ("https://www.amazon.sa/s?k=humidifier+dyson&rh=p_8%3A30-99", "🏠 Dyson Humidifier", 'search'),
    ("https://www.amazon.sa/s?k=dehumidifier&rh=p_8%3A30-99", "🏠 Dehumidifier", 'search'),
    
    # 🍚🍚🍚 GROCERY - السعوديون يشترون بالجملة (الأقسام 230-249)
    ("https://www.amazon.sa/s?k=nestle+pure+life+water&rh=p_8%3A30-99", "🍚 Nestlé Pure Life Water - #1", 'search'),
    ("https://www.amazon.sa/s?k=nadec+milk&rh=p_8%3A30-99", "🍚 Nadec Milk - #2", 'search'),
    ("https://www.amazon.sa/s?k=berain+water&rh=p_8%3A30-99", "🍚 Berain Water", 'search'),
    ("https://www.amazon.sa/s?k=abu+kass+rice&rh=p_8%3A30-99", "🍚 Abu Kass Rice", 'search'),
    ("https://www.amazon.sa/s?k=basmati+rice&rh=p_8%3A30-99", "🍚 Basmati Rice", 'search'),
    ("https://www.amazon.sa/s?k=maharaja+rice&rh=p_8%3A30-99", "🍚 Maharaja Rice", 'search'),
    ("https://www.amazon.sa/s?k=india+gate+rice&rh=p_8%3A30-99", "🍚 India Gate Rice", 'search'),
    ("https://www.amazon.sa/s?k=daawat+rice&rh=p_8%3A30-99", "🍚 Daawat Rice", 'search'),
    ("https://www.amazon.sa/s?k=almarai+milk&rh=p_8%3A30-99", "🍚 Almarai Milk", 'search'),
    ("https://www.amazon.sa/s?k=almarai+yogurt&rh=p_8%3A30-99", "🍚 Almarai Yogurt", 'search'),
    ("https://www.amazon.sa/s?k=nadec+juice&rh=p_8%3A30-99", "🍚 Nadec Juice", 'search'),
    ("https://www.amazon.sa/s?k=vimto&rh=p_8%3A30-99", "🍚 Vimto - رمضان", 'search'),
    ("https://www.amazon.sa/s?k=tang+orange&rh=p_8%3A30-99", "🍚 Tang Orange", 'search'),
    ("https://www.amazon.sa/s?k=nescafe+gold&rh=p_8%3A30-99", "☕ Nescafé Gold", 'search'),
    ("https://www.amazon.sa/s?k=starbucks+coffee+beans&rh=p_8%3A30-99", "☕ Starbucks Coffee", 'search'),
    ("https://www.amazon.sa/s?k=lavazza+coffee&rh=p_8%3A30-99", "☕ Lavazza Coffee", 'search'),
    ("https://www.amazon.sa/s?k=illy+coffee&rh=p_8%3A30-99", "☕ illy Coffee", 'search'),
    ("https://www.amazon.sa/s?k=dates+ajwa&rh=p_8%3A30-99", "🍚 Ajwa Dates - سعودي", 'search'),
    ("https://www.amazon.sa/s?k=dates+sukkari&rh=p_8%3A30-99", "🍚 Sukkari Dates", 'search'),
    ("https://www.amazon.sa/s?k=dates+medjool&rh=p_8%3A30-99", "🍚 Medjool Dates", 'search'),
    
    # 💻💻💻 LAPTOPS - السوق السعودي يفضل Dell, HP, Lenovo (الأقسام 250-269)
    ("https://www.amazon.sa/s?k=dell+xps+13&rh=p_8%3A30-99", "💻 Dell XPS 13", 'search'),
    ("https://www.amazon.sa/s?k=dell+xps+15&rh=p_8%3A30-99", "💻 Dell XPS 15", 'search'),
    ("https://www.amazon.sa/s?k=hp+spectre&rh=p_8%3A30-99", "💻 HP Spectre", 'search'),
    ("https://www.amazon.sa/s?k=hp+envy&rh=p_8%3A30-99", "💻 HP Envy", 'search'),
    ("https://www.amazon.sa/s?k=lenovo+thinkpad&rh=p_8%3A30-99", "💻 Lenovo ThinkPad", 'search'),
    ("https://www.amazon.sa/s?k=lenovo+yoga&rh=p_8%3A30-99", "💻 Lenovo Yoga", 'search'),
    ("https://www.amazon.sa/s?k=asus+zenbook&rh=p_8%3A30-99", "💻 ASUS ZenBook", 'search'),
    ("https://www.amazon.sa/s?k=asus+rog+zephyrus&rh=p_8%3A30-99", "💻 ASUS ROG Zephyrus", 'search'),
    ("https://www.amazon.sa/s?k=razer+blade&rh=p_8%3A30-99", "💻 Razer Blade", 'search'),
    ("https://www.amazon.sa/s?k=msi+gaming+laptop&rh=p_8%3A30-99", "💻 MSI Gaming", 'search'),
    ("https://www.amazon.sa/s?k=surface+laptop&rh=p_8%3A30-99", "💻 Surface Laptop", 'search'),
    ("https://www.amazon.sa/s?k=surface+pro&rh=p_8%3A30-99", "💻 Surface Pro", 'search'),
    ("https://www.amazon.sa/s?k=alienware&rh=p_8%3A30-99", "💻 Alienware", 'search'),
    ("https://www.amazon.sa/s?k=acer+predator&rh=p_8%3A30-99", "💻 Acer Predator", 'search'),
    ("https://www.amazon.sa/s?k=lg+gram&rh=p_8%3A30-99", "💻 LG Gram", 'search'),
    ("https://www.amazon.sa/s?k=huawei+matebook&rh=p_8%3A30-99", "💻 Huawei MateBook", 'search'),
    ("https://www.amazon.sa/s?k=honor+magicbook&rh=p_8%3A30-99", "💻 Honor MagicBook", 'search'),
    ("https://www.amazon.sa/s?k=realme+book&rh=p_8%3A30-99", "💻 realme Book", 'search'),
    ("https://www.amazon.sa/s?k=chuwi&rh=p_8%3A30-99", "💻 CHUWI - قيمة", 'search'),
    ("https://www.amazon.sa/s?k=teclast&rh=p_8%3A30-99", "💻 Teclast - قيمة", 'search'),
    
    # 🔋🔋🔋 POWER & CHARGING - إكسسوارات ربحية (الأقسام 270-289)
    ("https://www.amazon.sa/s?k=anker+prime&rh=p_8%3A30-99", "🔋 Anker Prime", 'search'),
    ("https://www.amazon.sa/s?k=anker+737&rh=p_8%3A30-99", "🔋 Anker 737", 'search'),
    ("https://www.amazon.sa/s?k=ugreen+nexode&rh=p_8%3A30-99", "🔋 UGREEN Nexode", 'search'),
    ("https://www.amazon.sa/s?k=baseus+blade&rh=p_8%3A30-99", "🔋 Baseus Blade", 'search'),
    ("https://www.amazon.sa/s?k=belkin+magsafe&rh=p_8%3A30-99", "🔌 Belkin MagSafe", 'search'),
    ("https://www.amazon.sa/s?k=mophie&rh=p_8%3A30-99", "🔌 Mophie", 'search'),
    ("https://www.amazon.sa/s?k=native+union&rh=p_8%3A30-99", "🔌 Native Union", 'search'),
    ("https://www.amazon.sa/s?k=romoss+sense&rh=p_8%3A30-99", "🔋 ROMOSS", 'search'),
    ("https://www.amazon.sa/s?k=xiaomi+power+bank&rh=p_8%3A30-99", "🔋 Xiaomi Power Bank", 'search'),
    ("https://www.amazon.sa/s?k=samsung+wireless+charger&rh=p_8%3A30-99", "🔌 Samsung Wireless Charger", 'search'),
    ("https://www.amazon.sa/s?k=apple+charger+20w&rh=p_8%3A30-99", "🔌 Apple Charger 20W", 'search'),
    ("https://www.amazon.sa/s?k=apple+charger+30w&rh=p_8%3A30-99", "🔌 Apple Charger 30W", 'search'),
    ("https://www.amazon.sa/s?k=usb+c+cable+anker&rh=p_8%3A30-99", "🔌 Anker USB-C Cable", 'search'),
    ("https://www.amazon.sa/s?k=usb+c+cable+belkin&rh=p_8%3A30-99", "🔌 Belkin USB-C Cable", 'search'),
    ("https://www.amazon.sa/s?k=charging+station+anker&rh=p_8%3A30-99", "🔌 Anker Charging Station", 'search'),
    ("https://www.amazon.sa/s?k=charging+station+ugreen&rh=p_8%3A30-99", "🔌 UGREEN Charging Station", 'search'),
    ("https://www.amazon.sa/s?k=car+charger+fast&rh=p_8%3A30-99", "🔌 Car Charger Fast", 'search'),
    ("https://www.amazon.sa/s?k=wireless+charger+stand&rh=p_8%3A30-99", "🔌 Wireless Charger Stand", 'search'),
    ("https://www.amazon.sa/s?k=power+strip+smart&rh=p_8%3A30-99", "🔌 Smart Power Strip", 'search'),
    ("https://www.amazon.sa/s?k=ups+apc&rh=p_8%3A30-99", "🔌 APC UPS", 'search'),
    
    # 📱📱📱 GENERAL ELECTRONICS - باقي الإلكترونيات (الأقسام 290-309)
    ("https://www.amazon.sa/s?k=laptop&rh=p_8%3A30-99", "💻 Laptop - عام", 'search'),
    ("https://www.amazon.sa/s?k=headphones&rh=p_8%3A30-99", "🎧 Headphones - عام", 'search'),
    ("https://www.amazon.sa/s?k=keyboard&rh=p_8%3A30-99", "⌨️ Keyboard - عام", 'search'),
    ("https://www.amazon.sa/s?k=mouse&rh=p_8%3A30-99", "🖱️ Mouse - عام", 'search'),
    ("https://www.amazon.sa/s?k=router&rh=p_8%3A30-99", "📡 Router - عام", 'search'),
    ("https://www.amazon.sa/s?k=power+bank&rh=p_8%3A30-99", "🔋 Power Bank - عام", 'search'),
    ("https://www.amazon.sa/s?k=charger&rh=p_8%3A30-99", "🔌 Charger - عام", 'search'),
    ("https://www.amazon.sa/s?k=hard+drive&rh=p_8%3A30-99", "💾 Hard Drive - عام", 'search'),
    ("https://www.amazon.sa/s?k=ssd&rh=p_8%3A30-99", "💾 SSD - عام", 'search'),
    ("https://www.amazon.sa/s?k=usb&rh=p_8%3A30-99", "💾 USB - عام", 'search'),
    ("https://www.amazon.sa/s?k=memory+card&rh=p_8%3A30-99", "💾 Memory Card - عام", 'search'),
    ("https://www.amazon.sa/s?k=tv&rh=p_8%3A30-99", "📺 TV - عام", 'search'),
    ("https://www.amazon.sa/s?k=monitor&rh=p_8%3A30-99", "🖥️ Monitor - عام", 'search'),
    ("https://www.amazon.sa/s?k=camera&rh=p_8%3A30-99", "📷 Camera - عام", 'search'),
    ("https://www.amazon.sa/s?k=watch&rh=p_8%3A30-99", "⌚ Watch - عام", 'search'),
    ("https://www.amazon.sa/s?k=perfume&rh=p_8%3A30-99", "🌸 Perfume - عام", 'search'),
    ("https://www.amazon.sa/s?k=makeup&rh=p_8%3A30-99", "💄 Makeup - عام", 'search'),
    ("https://www.amazon.sa/s?k=skincare&rh=p_8%3A30-99", "💆 Skincare - عام", 'search'),
    ("https://www.amazon.sa/s?k=bag&rh=p_8%3A30-99", "🎒 Bag - عام", 'search'),
    ("https://www.amazon.sa/s?k=wallet&rh=p_8%3A30-99", "👛 Wallet - عام", 'search'),
    
    # 🧱🧱🧱 TOYS - الأكثر مبيعاً (الأقسام 310-329)
    ("https://www.amazon.sa/s?k=lego+technic&rh=p_8%3A30-99", "🧱 LEGO Technic", 'search'),
    ("https://www.amazon.sa/s?k=lego+star+wars&rh=p_8%3A30-99", "🧱 LEGO Star Wars", 'search'),
    ("https://www.amazon.sa/s?k=lego+icons&rh=p_8%3A30-99", "🧱 LEGO Icons", 'search'),
    ("https://www.amazon.sa/s?k=lego+harry+potter&rh=p_8%3A30-99", "🧱 LEGO Harry Potter", 'search'),
    ("https://www.amazon.sa/s?k=lego+marvel&rh=p_8%3A30-99", "🧱 LEGO Marvel", 'search'),
    ("https://www.amazon.sa/s?k=lego+disney&rh=p_8%3A30-99", "🧱 LEGO Disney", 'search'),
    ("https://www.amazon.sa/s?k=barbie+dreamhouse&rh=p_8%3A30-99", "👸 Barbie DreamHouse", 'search'),
    ("https://www.amazon.sa/s?k=barbie+extra&rh=p_8%3A30-99", "👸 Barbie Extra", 'search'),
    ("https://www.amazon.sa/s?k=hot+wheels+track&rh=p_8%3A30-99", "🚗 Hot Wheels Track", 'search'),
    ("https://www.amazon.sa/s?k=hot+wheels+premium&rh=p_8%3A30-99", "🚗 Hot Wheels Premium", 'search'),
    ("https://www.amazon.sa/s?k=nerf+gun&rh=p_8%3A30-99", "🔫 Nerf Gun", 'search'),
    ("https://www.amazon.sa/s?k=nerf+rival&rh=p_8%3A30-99", "🔫 Nerf Rival", 'search'),
    ("https://www.amazon.sa/s?k=playmobil&rh=p_8%3A30-99", "🏰 Playmobil", 'search'),
    ("https://www.amazon.sa/s?k=playdoh&rh=p_8%3A30-99", "🎨 Play-Doh", 'search'),
    ("https://www.amazon.sa/s?k=hasbro+games&rh=p_8%3A30-99", "🎲 Hasbro Games", 'search'),
    ("https://www.amazon.sa/s?k=monopoly&rh=p_8%3A30-99", "🎲 Monopoly", 'search'),
    ("https://www.amazon.sa/s?k=scrabble&rh=p_8%3A30-99", "🎲 Scrabble", 'search'),
    ("https://www.amazon.sa/s?k=jenga&rh=p_8%3A30-99", "🎲 Jenga", 'search'),
    ("https://www.amazon.sa/s?k=uno&rh=p_8%3A30-99", "🎲 UNO", 'search'),
    ("https://www.amazon.sa/s?k=rubik%27s+cube&rh=p_8%3A30-99", "🎲 Rubik's Cube", 'search'),
    
    # 💎💎💎 JEWELRY - بديل Storage (الأقسام 330-349)
    ("https://www.amazon.sa/s?k=swarovski&rh=p_8%3A30-99", "💎 Swarovski", 'search'),
    ("https://www.amazon.sa/s?k=pandora&rh=p_8%3A30-99", "💎 Pandora", 'search'),
    ("https://www.amazon.sa/s?k=tiffany&rh=p_8%3A30-99", "💎 Tiffany", 'search'),
    ("https://www.amazon.sa/s?k=cartier&rh=p_8%3A30-99", "💎 Cartier", 'search'),
    ("https://www.amazon.sa/s?k=bulgari&rh=p_8%3A30-99", "💎 Bvlgari", 'search'),
    ("https://www.amazon.sa/s?k=chopard&rh=p_8%3A30-99", "💎 Chopard", 'search'),
    ("https://www.amazon.sa/s?k=apm+monaco&rh=p_8%3A30-99", "💎 APM Monaco", 'search'),
    ("https://www.amazon.sa/s?k=maison+margiela&rh=p_8%3A30-99", "💎 Maison Margiela", 'search'),
    ("https://www.amazon.sa/s?k=mejuri&rh=p_8%3A30-99", "💎 Mejuri", 'search'),
    ("https://www.amazon.sa/s?k=missoma&rh=p_8%3A30-99", "💎 Missoma", 'search'),
    ("https://www.amazon.sa/s?k=anita+ko&rh=p_8%3A30-99", "💎 Anita Ko", 'search'),
    ("https://www.amazon.sa/s?k=alighieri&rh=p_8%3A30-99", "💎 Alighieri", 'search'),
    ("https://www.amazon.sa/s?k=monica+vinader&rh=p_8%3A30-99", "💎 Monica Vinader", 'search'),
    ("https://www.amazon.sa/s?k=astley+clarke&rh=p_8%3A30-99", "💎 Astley Clarke", 'search'),
    ("https://www.amazon.sa/s?k=edge+of+ember&rh=p_8%3A30-99", "💎 Edge of Ember", 'search'),
    ("https://www.amazon.sa/s?k=ti+sento&rh=p_8%3A30-99", "💎 Ti Sento", 'search'),
    ("https://www.amazon.sa/s?k=thomas+sabo&rh=p_8%3A30-99", "💎 Thomas Sabo", 'search'),
    ("https://www.amazon.sa/s?k=links+of+london&rh=p_8%3A30-99", "💎 Links of London", 'search'),
    ("https://www.amazon.sa/s?k=chlo%C3%A9+jewelry&rh=p_8%3A30-99", "💎 Chloé Jewelry", 'search'),
    ("https://www.amazon.sa/s?k=kate+spade+jewelry&rh=p_8%3A30-99", "💎 Kate Spade Jewelry", 'search'),
    
    # ⌚⌚⌚ WATCHES - بديل E-Readers (الأقسام 350-369)
    ("https://www.amazon.sa/s?k=apple+watch+ultra&rh=p_8%3A30-99", "⌚ Apple Watch Ultra", 'search'),
    ("https://www.amazon.sa/s?k=garmin+fenix+7&rh=p_8%3A30-99", "⌚ Garmin Fenix 7", 'search'),
    ("https://www.amazon.sa/s?k=garmin+epix&rh=p_8%3A30-99", "⌚ Garmin Epix", 'search'),
    ("https://www.amazon.sa/s?k=garmin+forerunner&rh=p_8%3A30-99", "⌚ Garmin Forerunner", 'search'),
    ("https://www.amazon.sa/s?k=suunto&rh=p_8%3A30-99", "⌚ Suunto", 'search'),
    ("https://www.amazon.sa/s?k=polar+vantage&rh=p_8%3A30-99", "⌚ Polar Vantage", 'search'),
    ("https://www.amazon.sa/s?k=fitbit+sense&rh=p_8%3A30-99", "⌚ Fitbit Sense", 'search'),
    ("https://www.amazon.sa/s?k=huawei+watch+gt+4&rh=p_8%3A30-99", "⌚ Huawei Watch GT 4", 'search'),
    ("https://www.amazon.sa/s?k=fossil+gen+6&rh=p_8%3A30-99", "⌚ Fossil Gen 6", 'search'),
    ("https://www.amazon.sa/s?k=tissot&rh=p_8%3A30-99", "⌚ Tissot", 'search'),
    ("https://www.amazon.sa/s?k=casio+g+shock&rh=p_8%3A30-99", "⌚ Casio G-Shock", 'search'),
    ("https://www.amazon.sa/s?k=casio+edifice&rh=p_8%3A30-99", "⌚ Casio Edifice", 'search'),
    ("https://www.amazon.sa/s?k=seiko&rh=p_8%3A30-99", "⌚ Seiko", 'search'),
    ("https://www.amazon.sa/s?k=citizen+eco+drive&rh=p_8%3A30-99", "⌚ Citizen Eco-Drive", 'search'),
    ("https://www.amazon.sa/s?k=orient+watch&rh=p_8%3A30-99", "⌚ Orient", 'search'),
    ("https://www.amazon.sa/s?k=hamilton+watch&rh=p_8%3A30-99", "⌚ Hamilton", 'search'),
    ("https://www.amazon.sa/s?k=movado&rh=p_8%3A30-99", "⌚ Movado", 'search'),
    ("https://www.amazon.sa/s?k=tag+heuer&rh=p_8%3A30-99", "⌚ TAG Heuer", 'search'),
    ("https://www.amazon.sa/s?k=omega&rh=p_8%3A30-99", "⌚ Omega", 'search'),
    ("https://www.amazon.sa/s?k=rolex&rh=p_8%3A30-99", "⌚ Rolex", 'search'),
    
    # 🕶️🕶️🕶️ SUNGLASSES (الأقسام 370-389)
    ("https://www.amazon.sa/s?k=ray+ban+aviator&rh=p_8%3A30-99", "🕶️ Ray-Ban Aviator", 'search'),
    ("https://www.amazon.sa/s?k=ray+ban+wayfarer&rh=p_8%3A30-99", "🕶️ Ray-Ban Wayfarer", 'search'),
    ("https://www.amazon.sa/s?k=oakley+holbrook&rh=p_8%3A30-99", "🕶️ Oakley Holbrook", 'search'),
    ("https://www.amazon.sa/s?k=prada+sunglasses&rh=p_8%3A30-99", "🕶️ Prada", 'search'),
    ("https://www.amazon.sa/s?k=gucci+sunglasses&rh=p_8%3A30-99", "🕶️ Gucci", 'search'),
    ("https://www.amazon.sa/s?k=versace+sunglasses&rh=p_8%3A30-99", "🕶️ Versace", 'search'),
    ("https://www.amazon.sa/s?k=burberry+sunglasses&rh=p_8%3A30-99", "🕶️ Burberry", 'search'),
    ("https://www.amazon.sa/s?k=persol&rh=p_8%3A30-99", "🕶️ Persol", 'search'),
    ("https://www.amazon.sa/s?k=maui+jim&rh=p_8%3A30-99", "🕶️ Maui Jim", 'search'),
    ("https://www.amazon.sa/s?k=coach+sunglasses&rh=p_8%3A30-99", "🕶️ Coach", 'search'),
    ("https://www.amazon.sa/s?k=michael+kors+sunglasses&rh=p_8%3A30-99", "🕶️ Michael Kors", 'search'),
    ("https://www.amazon.sa/s?k=tom+ford+sunglasses&rh=p_8%3A30-99", "🕶️ Tom Ford", 'search'),
    ("https://www.amazon.sa/s?k=dior+sunglasses&rh=p_8%3A30-99", "🕶️ Dior", 'search'),
    ("https://www.amazon.sa/s?k=fendi+sunglasses&rh=p_8%3A30-99", "🕶️ Fendi", 'search'),
    ("https://www.amazon.sa/s?k=armani+sunglasses&rh=p_8%3A30-99", "🕶️ Armani", 'search'),
    ("https://www.amazon.sa/s?k=balenciaga+sunglasses&rh=p_8%3A30-99", "🕶️ Balenciaga", 'search'),
    ("https://www.amazon.sa/s?k=celine+sunglasses&rh=p_8%3A30-99", "🕶️ Celine", 'search'),
    ("https://www.amazon.sa/s?k=loewe+sunglasses&rh=p_8%3A30-99", "🕶️ Loewe", 'search'),
    ("https://www.amazon.sa/s?k=jacques+marie+mage&rh=p_8%3A30-99", "🕶️ Jacques Marie Mage", 'search'),
    ("https://www.amazon.sa/s?k=linda+farrow&rh=p_8%3A30-99", "🕶️ Linda Farrow", 'search'),
    
    # 👟👟👟 SHOES - بديل Audio (الأقسام 390-409)
    ("https://www.amazon.sa/s?k=nike+air+jordan&rh=p_8%3A30-99", "👟 Nike Air Jordan", 'search'),
    ("https://www.amazon.sa/s?k=nike+dunk&rh=p_8%3A30-99", "👟 Nike Dunk", 'search'),
    ("https://www.amazon.sa/s?k=nike+air+force&rh=p_8%3A30-99", "👟 Nike Air Force", 'search'),
    ("https://www.amazon.sa/s?k=nike+air+max&rh=p_8%3A30-99", "👟 Nike Air Max", 'search'),
    ("https://www.amazon.sa/s?k=adidas+ultraboost&rh=p_8%3A30-99", "👟 Adidas Ultraboost", 'search'),
    ("https://www.amazon.sa/s?k=adidas+yeezy&rh=p_8%3A30-99", "👟 Adidas Yeezy", 'search'),
    ("https://www.amazon.sa/s?k=adidas+samba&rh=p_8%3A30-99", "👟 Adidas Samba", 'search'),
    ("https://www.amazon.sa/s?k=new+balance+990&rh=p_8%3A30-99", "👟 New Balance 990", 'search'),
    ("https://www.amazon.sa/s?k=new+balance+550&rh=p_8%3A30-99", "👟 New Balance 550", 'search'),
    ("https://www.amazon.sa/s?k=asics+gel+kayano&rh=p_8%3A30-99", "👟 ASICS Gel Kayano", 'search'),
    ("https://www.amazon.sa/s?k=asics+gel+lyte&rh=p_8%3A30-99", "👟 ASICS Gel Lyte", 'search'),
    ("https://www.amazon.sa/s?k=hoka&rh=p_8%3A30-99", "👟 HOKA", 'search'),
    ("https://www.amazon.sa/s?k=on+running&rh=p_8%3A30-99", "👟 On Running", 'search'),
    ("https://www.amazon.sa/s?k=salomon&rh=p_8%3A30-99", "👟 Salomon", 'search'),
    ("https://www.amazon.sa/s?k=merrell&rh=p_8%3A30-99", "👟 Merrell", 'search'),
    ("https://www.amazon.sa/s?k=keen&rh=p_8%3A30-99", "👟 Keen", 'search'),
    ("https://www.amazon.sa/s?k=teva&rh=p_8%3A30-99", "👟 Teva", 'search'),
    ("https://www.amazon.sa/s?k=birkenstock&rh=p_8%3A30-99", "👟 Birkenstock", 'search'),
    ("https://www.amazon.sa/s?k=crocs&rh=p_8%3A30-99", "👟 Crocs", 'search'),
    ("https://www.amazon.sa/s?k=ugg&rh=p_8%3A30-99", "👟 UGG", 'search'),
    
    # 🎒🎒🎒 BAGS - بديل Cameras (الأقسام 410-429)
    ("https://www.amazon.sa/s?k=tumi&rh=p_8%3A30-99", "🎒 TUMI", 'search'),
    ("https://www.amazon.sa/s?k=samsonite+black+label&rh=p_8%3A30-99", "🎒 Samsonite Black Label", 'search'),
    ("https://www.amazon.sa/s?k=rimowa&rh=p_8%3A30-99", "🎒 Rimowa", 'search'),
    ("https://www.amazon.sa/s?k=away+luggage&rh=p_8%3A30-99", "🎒 Away", 'search'),
    ("https://www.amazon.sa/s?k=bellroy&rh=p_8%3A30-99", "🎒 Bellroy", 'search'),
    ("https://www.amazon.sa/s?k=nomatic&rh=p_8%3A30-99", "🎒 Nomatic", 'search'),
    ("https://www.amazon.sa/s?k=peak+design&rh=p_8%3A30-99", "🎒 Peak Design", 'search'),
    ("https://www.amazon.sa/s?k=lowepro&rh=p_8%3A30-99", "🎒 Lowepro", 'search'),
    ("https://www.amazon.sa/s?k=herschel&rh=p_8%3A30-99", "🎒 Herschel", 'search'),
    ("https://www.amazon.sa/s?k=fjallraven&rh=p_8%3A30-99", "🎒 Fjällräven", 'search'),
    ("https://www.amazon.sa/s?k=patagonia+backpack&rh=p_8%3A30-99", "🎒 Patagonia", 'search'),
    ("https://www.amazon.sa/s?k=north+face+backpack&rh=p_8%3A30-99", "🎒 The North Face", 'search'),
    ("https://www.amazon.sa/s?k=osprey&rh=p_8%3A30-99", "🎒 Osprey", 'search'),
    ("https://www.amazon.sa/s?k=deuter&rh=p_8%3A30-99", "🎒 Deuter", 'search'),
    ("https://www.amazon.sa/s?k=gregory&rh=p_8%3A30-99", "🎒 Gregory", 'search'),
    ("https://www.amazon.sa/s?k=mystery+ranch&rh=p_8%3A30-99", "🎒 Mystery Ranch", 'search'),
    ("https://www.amazon.sa/s?k=goruck&rh=p_8%3A30-99", "🎒 GORUCK", 'search'),
    ("https://www.amazon.sa/s?k=tortuga&rh=p_8%3A30-99", "🎒 Tortuga", 'search'),
    ("https://www.amazon.sa/s?k=everki&rh=p_8%3A30-99", "🎒 Everki", 'search'),
    ("https://www.amazon.sa/s?k=incase&rh=p_8%3A30-99", "🎒 Incase", 'search'),
    
    # 📚📚📚 BOOKS - بديل Bath & Body (الأقسام 430-449)
    ("https://www.amazon.sa/s?k=kindle+paperwhite&rh=p_8%3A30-99", "📚 Kindle Paperwhite", 'search'),
    ("https://www.amazon.sa/s?k=kindle+scribe&rh=p_8%3A30-99", "📚 Kindle Scribe", 'search'),
    ("https://www.amazon.sa/s?k=kindle+colorsoft&rh=p_8%3A30-99", "📚 Kindle Colorsoft", 'search'),
    ("https://www.amazon.sa/s?k=echo+dot&rh=p_8%3A30-99", "🔊 Echo Dot", 'search'),
    ("https://www.amazon.sa/s?k=echo+spot&rh=p_8%3A30-99", "🔊 Echo Spot", 'search'),
    ("https://www.amazon.sa/s?k=echo+show&rh=p_8%3A30-99", "🔊 Echo Show", 'search'),
    ("https://www.amazon.sa/s?k=echo+pop&rh=p_8%3A30-99", "🔊 Echo Pop", 'search'),
    ("https://www.amazon.sa/s?k=fire+tv+stick&rh=p_8%3A30-99", "📺 Fire TV Stick", 'search'),
    ("https://www.amazon.sa/s?k=fire+tv+cube&rh=p_8%3A30-99", "📺 Fire TV Cube", 'search'),
    ("https://www.amazon.sa/s?k=fire+hd+tablet&rh=p_8%3A30-99", "📱 Fire HD Tablet", 'search'),
    ("https://www.amazon.sa/s?k=book+arabic+bestseller&rh=p_8%3A30-99", "📚 Arabic Bestsellers", 'search'),
    ("https://www.amazon.sa/s?k=quran+english&rh=p_8%3A30-99", "📚 Quran English", 'search'),
    ("https://www.amazon.sa/s?k=islamic+books&rh=p_8%3A30-99", "📚 Islamic Books", 'search'),
    ("https://www.amazon.sa/s?k=self+help+books&rh=p_8%3A30-99", "📚 Self Help Books", 'search'),
    ("https://www.amazon.sa/s?k=business+books&rh=p_8%3A30-99", "📚 Business Books", 'search'),
    ("https://www.amazon.sa/s?k=cookbook&rh=p_8%3A30-99", "📚 Cookbooks", 'search'),
    ("https://www.amazon.sa/s?k=children+books+arabic&rh=p_8%3A30-99", "📚 Children Books Arabic", 'search'),
    ("https://www.amazon.sa/s?k=coloring+book+adult&rh=p_8%3A30-99", "📚 Adult Coloring Books", 'search'),
    ("https://www.amazon.sa/s?k=journal+premium&rh=p_8%3A30-99", "📚 Premium Journals", 'search'),
    ("https://www.amazon.sa/s?k=planner+2026&rh=p_8%3A30-99", "📚 Planner 2026", 'search'),
    
    # 🖊️🖊️🖊️ OFFICE & STATIONERY - بديل Storage (الأقسام 450-469)
    ("https://www.amazon.sa/s?k=montblanc&rh=p_8%3A30-99", "🖊️ Montblanc", 'search'),
    ("https://www.amazon.sa/s?k=parker+duofold&rh=p_8%3A30-99", "🖊️ Parker Duofold", 'search'),
    ("https://www.amazon.sa/s?k=pelikan+m800&rh=p_8%3A30-99", "🖊️ Pelikan M800", 'search'),
    ("https://www.amazon.sa/s?k=lamy+2000&rh=p_8%3A30-99", "🖊️ Lamy 2000", 'search'),
    ("https://www.amazon.sa/s?k=visconti&rh=p_8%3A30-99", "🖊️ Visconti", 'search'),
    ("https://www.amazon.sa/s?k=sailor+pen&rh=p_8%3A30-99", "🖊️ Sailor", 'search'),
    ("https://www.amazon.sa/s?k=platinum+3776&rh=p_8%3A30-99", "🖊️ Platinum 3776", 'search'),
    ("https://www.amazon.sa/s?k=rhodia&rh=p_8%3A30-99", "📓 Rhodia", 'search'),
    ("https://www.amazon.sa/s?k=moleskine&rh=p_8%3A30-99", "📓 Moleskine", 'search'),
    ("https://www.amazon.sa/s?k=leuchtturm1917&rh=p_8%3A30-99", "📓 Leuchtturm1917", 'search'),
    ("https://www.amazon.sa/s?k=field+notes&rh=p_8%3A30-99", "📓 Field Notes", 'search'),
    ("https://www.amazon.sa/s?k=baron+fig&rh=p_8%3A30-99", "📓 Baron Fig", 'search'),
    ("https://www.amazon.sa/s?k=lamy+notebook&rh=p_8%3A30-99", "📓 Lamy Notebook", 'search'),
    ("https://www.amazon.sa/s?k=clairefontaine&rh=p_8%3A30-99", "📓 Clairefontaine", 'search'),
    ("https://www.amazon.sa/s?k=maruman&rh=p_8%3A30-99", "📓 Maruman", 'search'),
    ("https://www.amazon.sa/s?k=kokuyo&rh=p_8%3A30-99", "📓 Kokuyo", 'search'),
    ("https://www.amazon.sa/s?k=midori&rh=p_8%3A30-99", "📓 Midori", 'search'),
    ("https://www.amazon.sa/s?k=traveler%27s+notebook&rh=p_8%3A30-99", "📓 Traveler's Notebook", 'search'),
    ("https://www.amazon.sa/s?k=hobonichi&rh=p_8%3A30-99", "📓 Hobonichi", 'search'),
    ("https://www.amazon.sa/s?k=stabilo&rh=p_8%3A30-99", "🖊️ Stabilo", 'search'),
]

# متغير لتتبع الصفحات
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
        
        # لو مفيش خصم محسوب، ندور على نسبة مكتوبة
        if discount == 0:
            badge = item.find(string=re.compile(r'(\d+)%'))
            if badge:
                match = re.search(r'(\d+)', str(badge))
                if match:
                    discount = int(match.group())
                    old_price = price / (1 - discount/100)
        
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
        
        # المراجعات
        reviews = 0
        rev_el = item.find('span', class_='a-size-base')
        if rev_el:
            match = re.search(r'[\d,]+', rev_el.text)
            if match:
                try:
                    reviews = int(match.group().replace(',', ''))
                except:
                    pass
        
        return {
            'title': title[:120],
            'price': price,
            'old_price': round(old_price, 2) if old_price > 0 else round(price * 100 / (100 - discount), 2),
            'discount': discount,
            'rating': rating,
            'reviews': reviews,
            'link': link,
            'category': category,
            'is_best_seller': is_best_seller,
            'id': get_product_id(title, link, price)
        }
        
    except Exception as e:
        return None

def search_all_deals(chat_id=None, status_msg_id=None):
    """
    ✅ يخلص القسم كله (كل الصفحات) ويطلع كل العروض اللي فيه
    ❌ ملغي: مفيش عدد محدد 20 منتج
    """
    global last_page_tracker
    
    all_deals = []
    session = create_session()
    
    # ✅ خلط عشوائي للأقسام
    cats = list(CATEGORIES_DEF)
    random.shuffle(cats)
    
    logger.info(f"🚀 Starting search in {len(cats)} categories...")
    
    page_counter = 0
    
    for base_url, cat_name, cat_type in cats:
        # ✅ نبدأ من آخر صفحة + 1
        start_page = last_page_tracker.get(cat_name, 0) + 1
        
        # ✅ ندور في كل صفحات القسم (مفيش حد أقصى)
        for page_num in range(start_page, start_page + 20):  # 20 صفحة من كل قسم
            page_counter += 1
            
            # ✅ بناء الرابط
            if cat_type in ['best_sellers', 'deals', 'warehouse', 'coupons', 'lightning', 'today', 'outlet']:
                if '?' in base_url:
                    url = f"{base_url}&page={page_num}"
                else:
                    url = f"{base_url}?page={page_num}"
            else:
                url = get_page_url(base_url, page_num)
            
            logger.info(f"🔍 [{cat_name}] Page {page_num} | Total found: {len(all_deals)}")
            
            # ✅ تحديث رسالة الحالة كل 10 صفحات
            if chat_id and status_msg_id and page_counter % 10 == 0:
                try:
                    updater.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=status_msg_id,
                        text=f"🔍 *جاري البحث...*\n\n📄 صفحات تم البحث فيها: {page_counter}\n✅ منتجات تم العثور عليها: {len(all_deals)}\n⏳ جاري البحث في: {cat_name}",
                        parse_mode='Markdown'
                    )
                except:
                    pass
            
            html = fetch_page(session, url)
            if not html:
                continue
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # ✅ كل أنواع الـ selectors
            items = []
            if cat_type == 'best_sellers':
                items.extend(soup.find_all('li', class_='zg-item-immersion'))
                items.extend(soup.find_all('div', class_='p13n-sc-uncoverable-faceout'))
            
            items.extend(soup.find_all('div', {'data-component-type': 's-search-result'}))
            items.extend(soup.find_all('div', {'data-testid': 'deal-card'}))
            items.extend(soup.find_all('div', class_='s-result-item'))
            
            logger.info(f"   Found {len(items)} items")
            
            # ✅ لو الصفحة فاضية، نوقف القسم ده ونروح للقسم اللي بعده
            if len(items) == 0:
                logger.info(f"   ⛔ Empty page, moving to next category")
                break
            
            for item in items:
                try:
                    deal = parse_item(item, cat_name, cat_type == 'best_sellers')
                    
                    # ✅ شروط الصفقة
                    if deal and deal['discount'] >= MIN_DISCOUNT and deal['rating'] >= MIN_RATING:
                        if deal['id'] not in sent_products and not is_similar_product(deal['title']):
                            all_deals.append(deal)
                            logger.info(f"✅ ADDED: {deal['title'][:40]} | {deal['discount']}% | {deal['rating']}★")
                            
                except:
                    continue
            
            # ✅ تحديث آخر صفحة
            last_page_tracker[cat_name] = page_num
            
            time.sleep(random.uniform(1, 2))
        
        # ✅ بعد ما نخلص القسم، نبعت العروض اللي لقيناها
        if len(all_deals) > 0:
            logger.info(f"📤 Sending {len(all_deals)} deals from {cat_name}")
            filter_and_send_deals(all_deals, chat_id)
            all_deals = []  # نفضي الليست عشان القسم اللي جاي
    
    save_database()
    logger.info(f"🎯 Search complete! Total deals sent")
    return all_deals

def filter_and_send_deals(deals, chat_id):
    """
    ✅ يبعت العروض مرتبة: السوبر (90%+) الأول
    """
    if not deals:
        return
    
    # ✅ فصل العروض
    super_deals = [d for d in deals if d['discount'] >= 90]
    normal_deals = [d for d in deals if d['discount'] < 90]
    
    logger.info(f"🚨 Super deals (90%+): {len(super_deals)}")
    logger.info(f"🔥 Normal deals (40-89%): {len(normal_deals)}")
    
    # ✅ رسالة السوبر ديلز (90%+)
    if super_deals:
        msg = "🚨🚨🚨 *عروض خرافية 90%+* 🚨🚨🚨\n\n"
        
        for i, d in enumerate(super_deals, 1):
            savings = d['old_price'] - d['price'] if d['old_price'] > 0 else 0
            
            msg += f"*{i}. {d['title'][:50]}*\n"
            msg += f"💰 {d['price']:.0f} ريال ~~{d['old_price']:.0f}~~\n"
            msg += f"🔥🔥🔥 خصم: *{d['discount']}%* (توفر {savings:.0f} ريال)\n"
            msg += f"⭐ {d['rating']}/5 | 🏷️ {d['category']}\n"
            msg += f"🔗 [اشتري بسرعة]({d['link']})\n\n"
        
        try:
            updater.bot.send_message(chat_id=chat_id, text=msg, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Super send error: {e}")
        
        time.sleep(1)
    
    # ✅ رسالة العروض العادية (40-89%)
    if normal_deals:
        msg = f"🔥 *عروض رهيبة 40%+* ({len(normal_deals)} منتج)\n\n"
        
        for i, d in enumerate(normal_deals, 1):
            if d['id'] in sent_products:
                continue
            
            savings = d['old_price'] - d['price'] if d['old_price'] > 0 else 0
            
            msg += f"*{i}. {d['title'][:50]}*\n"
            msg += f"💰 {d['price']:.0f} ريال ~~{d['old_price']:.0f}~~ (توفر {savings:.0f})\n"
            msg += f"📉 خصم: *{d['discount']}%* | ⭐ {d['rating']}/5\n"
            msg += f"🏷️ {d['category']}\n"
            msg += f"🔗 [اشتري من هنا]({d['link']})\n\n"
            
            # ✅ نبعت كل 5 منتجات
            if i % 5 == 0 or i == len(normal_deals):
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
    
    # ✅ نضيف السوبر للـ sent
    for d in super_deals:
        sent_products.add(d['id'])
        sent_hashes.add(create_title_hash(d['title']))
    
    save_database()

# ================== أوامر ==================
def start_cmd(update: Update, context: CallbackContext):
    welcome = """👋 *أهلا بيك في بوت عروض أمازون السعودية!*

🔥 *مميزات البوت:*
• يدور في *470+ قسم* مختلف
• يخلص *كل قسم كامل* (كل الصفحات)
• خصومات *40%+* | تقييم *3 نجوم+*
• عروض *90%+* بشكل خاص 🚨
• مخصص *100% للسوق السعودي* 🇸🇦

✅ *الأقسام الأولى:*
1️⃣ Best Sellers السعودية
2️⃣ Deals الرسمية
3️⃣ Apple & Samsung
4️⃣ Perfumes & Beauty
5️⃣ Home & Kitchen
6️⃣ Fashion & Automotive
7️⃣ Baby & Sports
8️⃣ Kitchen Appliances
9️⃣ Smart Home & Grocery
🔟 Laptops & Power

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
        "⏳ *الوقت المتوقع: 10-15 دقيقة*",
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
            text="✅ *خلصت البحث!*\n\n📦 كل الأقسام اتبحثت\n🔥 العروض اتبعتت لك\n\nاكتب *Hi* عشان تبدأ بحث جديد!",
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
            update.message.reply_text(f"❌ خطأ: {str(e)[:100]}", parse_mode='Markdown')
    finally:
        is_scanning = False

def status_cmd(update: Update, context: CallbackContext):
    total_cats = len(CATEGORIES_DEF)
    msg = f"""✅ *البوت شغال تمام!*

📦 منتجات متبعتة: *{len(sent_products)}*
📁 عدد الأقسام: *{total_cats}*
📉 الحد الأدنى للخصم: *{MIN_DISCOUNT}%*
⭐ الحد الأدنى للتقييم: *{MIN_RATING}*

🇸🇦 *مخصص للسوق السعودي*

✅ *الأقسام الأولى:*
1️⃣ Best Sellers السعودية
2️⃣ Deals الرسمية
3️⃣ Apple & Samsung
4️⃣ Perfumes & Beauty
5️⃣ Home & Kitchen

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
    logger.info("🎯 Mode: Full category scan (no limit)")
    
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
