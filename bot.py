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
TARGET_DEALS_COUNT = 20    # ✅ هدفنا 20 منتج بالظبط
MIN_DISCOUNT = 40          # خصم 40%+
MIN_RATING = 3.0           # 3 نجوم+

# ✅ الأقسام مرتبة حسب البيانات الفعلية لسوق السعودية 2026
# المصادر: Amazon.sa Bestsellers Reports + Accio Market Analysis
CATEGORIES_DEF = [
    # ⭐⭐⭐ BEST SELLERS SAUDI - أولوية قصوى (بيانات فعلية من أمازون السعودية)
    ("https://www.amazon.sa/gp/bestsellers", "⭐ Best Sellers - السعودية", 'best_sellers'),
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
    
    # 🔥🔥🔥 DEALS الرسمية - ثاني أولوية
    ("https://www.amazon.sa/gp/goldbox", "🔥 Goldbox - الصفقات اليومية", 'deals'),
    ("https://www.amazon.sa/gp/prime/pipeline/lightning_deals", "⚡ Lightning Deals - عروض فلاش", 'lightning'),
    ("https://www.amazon.sa/gp/todays-deals", "📅 Today's Deals - عروض اليوم", 'today'),
    ("https://www.amazon.sa/gp/warehouse-deals", "🏭 Warehouse - مستعمل ممتاز", 'warehouse'),
    ("https://www.amazon.sa/gp/coupons", "🎟️ Coupons - كوبونات", 'coupons'),
    ("https://www.amazon.sa/outlet", "🎁 Outlet - مخلفات بأسعار مخفضة", 'outlet'),
    
    # 🍎🍎🍎 APPLE - ربحية خرافية للأفلييت في السعودية (الأكثر طلباً)
    ("https://www.amazon.sa/s?k=iphone+15+pro+max&rh=p_8%3A30-99", "🍎 iPhone 15 Pro Max - الأكثر مبيعاً", 'search'),
    ("https://www.amazon.sa/s?k=iphone+15+pro&rh=p_8%3A30-99", "🍎 iPhone 15 Pro", 'search'),
    ("https://www.amazon.sa/s?k=iphone+15&rh=p_8%3A30-99", "🍎 iPhone 15", 'search'),
    ("https://www.amazon.sa/s?k=iphone+14+pro&rh=p_8%3A30-99", "🍎 iPhone 14 Pro", 'search'),
    ("https://www.amazon.sa/s?k=airpods+pro+2&rh=p_8%3A30-99", "🍎 AirPods Pro 2 - ربحية عالية", 'search'),
    ("https://www.amazon.sa/s?k=airpods+max&rh=p_8%3A30-99", "🍎 AirPods Max - بريميوم", 'search'),
    ("https://www.amazon.sa/s?k=apple+watch+ultra+2&rh=p_8%3A30-99", "🍎 Apple Watch Ultra 2 - بريميوم", 'search'),
    ("https://www.amazon.sa/s?k=apple+watch+series+9&rh=p_8%3A30-99", "🍎 Apple Watch Series 9", 'search'),
    ("https://www.amazon.sa/s?k=apple+watch+se&rh=p_8%3A30-99", "🍎 Apple Watch SE - مبيعات ضخمة", 'search'),
    ("https://www.amazon.sa/s?k=ipad+pro+m4&rh=p_8%3A30-99", "🍎 iPad Pro M4 - بريميوم", 'search'),
    ("https://www.amazon.sa/s?k=ipad+air+m2&rh=p_8%3A30-99", "🍎 iPad Air M2", 'search'),
    ("https://www.amazon.sa/s?k=ipad+mini&rh=p_8%3A30-99", "🍎 iPad Mini", 'search'),
    ("https://www.amazon.sa/s?k=macbook+pro+m3&rh=p_8%3A30-99", "🍎 MacBook Pro M3 - بريميوم", 'search'),
    ("https://www.amazon.sa/s?k=macbook+air+m3&rh=p_8%3A30-99", "🍎 MacBook Air M3 - ربحية عالية", 'search'),
    ("https://www.amazon.sa/s?k=macbook+air+m2&rh=p_8%3A30-99", "🍎 MacBook Air M2", 'search'),
    ("https://www.amazon.sa/s?k=mac+mini+m2&rh=p_8%3A30-99", "🍎 Mac Mini M2", 'search'),
    ("https://www.amazon.sa/s?k=apple+tv+4k&rh=p_8%3A30-99", "🍎 Apple TV 4K", 'search'),
    ("https://www.amazon.sa/s?k=homepod&rh=p_8%3A30-99", "🍎 HomePod", 'search'),
    ("https://www.amazon.sa/s?k=airtag&rh=p_8%3A30-99", "🍎 AirTag - مبيعات ضخمة", 'search'),
    ("https://www.amazon.sa/s?k=magsafe&rh=p_8%3A30-99", "🍎 MagSafe - إكسسوارات ربحية", 'search'),
    ("https://www.amazon.sa/s?k=apple+pencil&rh=p_8%3A30-99", "🍎 Apple Pencil", 'search'),
    ("https://www.amazon.sa/s?k=magic+keyboard&rh=p_8%3A30-99", "🍎 Magic Keyboard", 'search'),
    
    # 📱📱📱 SAMSUNG - منافس Apple في السعودية (مبيعات ضخمة)
    ("https://www.amazon.sa/s?k=samsung+galaxy+s24+ultra&rh=p_8%3A30-99", "📱 Galaxy S24 Ultra - بريميوم", 'search'),
    ("https://www.amazon.sa/s?k=samsung+galaxy+s24+plus&rh=p_8%3A30-99", "📱 Galaxy S24 Plus", 'search'),
    ("https://www.amazon.sa/s?k=samsung+galaxy+s24&rh=p_8%3A30-99", "📱 Galaxy S24", 'search'),
    ("https://www.amazon.sa/s?k=samsung+galaxy+z+fold+5&rh=p_8%3A30-99", "📱 Galaxy Z Fold 5 - بريميوم", 'search'),
    ("https://www.amazon.sa/s?k=samsung+galaxy+z+flip+5&rh=p_8%3A30-99", "📱 Galaxy Z Flip 5", 'search'),
    ("https://www.amazon.sa/s?k=samsung+galaxy+tab+s9+ultra&rh=p_8%3A30-99", "📱 Galaxy Tab S9 Ultra", 'search'),
    ("https://www.amazon.sa/s?k=samsung+galaxy+tab+s9&rh=p_8%3A30-99", "📱 Galaxy Tab S9", 'search'),
    ("https://www.amazon.sa/s?k=samsung+galaxy+watch+6&rh=p_8%3A30-99", "📱 Galaxy Watch 6", 'search'),
    ("https://www.amazon.sa/s?k=samsung+galaxy+buds+2+pro&rh=p_8%3A30-99", "📱 Galaxy Buds 2 Pro", 'search'),
    ("https://www.amazon.sa/s?k=samsung+galaxy+buds+fe&rh=p_8%3A30-99", "📱 Galaxy Buds FE - مبيعات ضخمة", 'search'),
    
    # 🎮🎮🎮 GAMING - الأكثر مبيعاً في السعودية (PS5, Xbox, Steam Deck)
    ("https://www.amazon.sa/s?k=playstation+5&rh=p_8%3A30-99", "🎮 PlayStation 5 - الأكثر مبيعاً في السعودية", 'search'),
    ("https://www.amazon.sa/s?k=ps5+slim&rh=p_8%3A30-99", "🎮 PS5 Slim - جديد ورائج", 'search'),
    ("https://www.amazon.sa/s?k=ps5+pro&rh=p_8%3A30-99", "🎮 PS5 Pro - بريميوم", 'search'),
    ("https://www.amazon.sa/s?k=playstation+vr2&rh=p_8%3A30-99", "🎮 PS VR2 - بريميوم", 'search'),
    ("https://www.amazon.sa/s?k=dualsense+edge&rh=p_8%3A30-99", "🎮 DualSense Edge - بريميوم", 'search'),
    ("https://www.amazon.sa/s?k=dualsense+controller&rh=p_8%3A30-99", "🎮 DualSense Controller - مبيعات مستمرة", 'search'),
    ("https://www.amazon.sa/s?k=xbox+series+x&rh=p_8%3A30-99", "🎮 Xbox Series X", 'search'),
    ("https://www.amazon.sa/s?k=xbox+series+s&rh=p_8%3A30-99", "🎮 Xbox Series S - مبيعات ضخمة", 'search'),
    ("https://www.amazon.sa/s?k=nintendo+switch+oled&rh=p_8%3A30-99", "🎮 Nintendo Switch OLED", 'search'),
    ("https://www.amazon.sa/s?k=steam+deck&rh=p_8%3A30-99", "🎮 Steam Deck - بريميوم", 'search'),
    ("https://www.amazon.sa/s?k=asus+rog+ally&rh=p_8%3A30-99", "🎮 ASUS ROG Ally", 'search'),
    ("https://www.amazon.sa/s?k=rtx+4080&rh=p_8%3A30-99", "🎮 RTX 4080 - بريميوم", 'search'),
    ("https://www.amazon.sa/s?k=rtx+4070&rh=p_8%3A30-99", "🎮 RTX 4070", 'search'),
    ("https://www.amazon.sa/s?k=rtx+4090&rh=p_8%3A30-99", "🎮 RTX 4090 - التوب بريميوم", 'search'),
    ("https://www.amazon.sa/s?k=gaming+headset&rh=p_8%3A30-99", "🎮 Gaming Headsets - ربحية", 'search'),
    ("https://www.amazon.sa/s?k=gaming+keyboard&rh=p_8%3A30-99", "🎮 Gaming Keyboards - ربحية", 'search'),
    ("https://www.amazon.sa/s?k=gaming+mouse&rh=p_8%3A30-99", "🎮 Gaming Mouse - ربحية", 'search'),
    ("https://www.amazon.sa/s?k=gaming+monitor&rh=p_8%3A30-99", "🎮 Gaming Monitors - بريميوم", 'search'),
    
    # 💻💻💻 LAPTOPS - السوق السعودي يفضل Dell, HP, Lenovo للأعمال
    ("https://www.amazon.sa/s?k=dell+xps+13&rh=p_8%3A30-99", "💻 Dell XPS 13 - بريميوم", 'search'),
    ("https://www.amazon.sa/s?k=dell+xps+15&rh=p_8%3A30-99", "💻 Dell XPS 15 - بريميوم", 'search'),
    ("https://www.amazon.sa/s?k=hp+spectre&rh=p_8%3A30-99", "💻 HP Spectre - بريميوم", 'search'),
    ("https://www.amazon.sa/s?k=hp+envy&rh=p_8%3A30-99", "💻 HP Envy", 'search'),
    ("https://www.amazon.sa/s?k=lenovo+thinkpad&rh=p_8%3A30-99", "💻 Lenovo ThinkPad - بروفيشنال", 'search'),
    ("https://www.amazon.sa/s?k=lenovo+yoga&rh=p_8%3A30-99", "💻 Lenovo Yoga", 'search'),
    ("https://www.amazon.sa/s?k=asus+zenbook&rh=p_8%3A30-99", "💻 ASUS ZenBook - بريميوم", 'search'),
    ("https://www.amazon.sa/s?k=asus+rog+zephyrus&rh=p_8%3A30-99", "💻 ASUS ROG Zephyrus - جيمينج", 'search'),
    ("https://www.amazon.sa/s?k=razer+blade&rh=p_8%3A30-99", "💻 Razer Blade - التوب جيمينج", 'search'),
    ("https://www.amazon.sa/s?k=msi+gaming+laptop&rh=p_8%3A30-99", "💻 MSI Gaming - جيمينج", 'search'),
    ("https://www.amazon.sa/s?k=surface+laptop&rh=p_8%3A30-99", "💻 Surface Laptop - مايكروسوفت", 'search'),
    ("https://www.amazon.sa/s?k=surface+pro&rh=p_8%3A30-99", "💻 Surface Pro - مايكروسوفت", 'search'),
    
    # 📺📺📺 TVs - السعوديون يفضلون شاشات كبيرة (65"+)
    ("https://www.amazon.sa/s?k=samsung+neo+qled&rh=p_8%3A30-99", "📺 Samsung Neo QLED - بريميوم", 'search'),
    ("https://www.amazon.sa/s?k=lg+oled&rh=p_8%3A30-99", "📺 LG OLED - التوب", 'search'),
    ("https://www.amazon.sa/s?k=sony+bravia+xr&rh=p_8%3A30-99", "📺 Sony Bravia XR - بريميوم", 'search'),
    ("https://www.amazon.sa/s?k=tcl+mini+led&rh=p_8%3A30-99", "📺 TCL Mini LED - قيمة عالية", 'search'),
    ("https://www.amazon.sa/s?k=hisense+u8&rh=p_8%3A30-99", "📺 Hisense U8 - قيمة عالية", 'search'),
    ("https://www.amazon.sa/s?k=lg+ultragear&rh=p_8%3A30-99", "🖥️ LG UltraGear - جيمينج", 'search'),
    ("https://www.amazon.sa/s?k=samsung+odyssey&rh=p_8%3A30-99", "🖥️ Samsung Odyssey - جيمينج", 'search'),
    
    # 🎧🎧🎧 AUDIO - السعوديون يحبون السماعات البريميوم
    ("https://www.amazon.sa/s?k=sony+wh-1000xm5&rh=p_8%3A30-99", "🎧 Sony WH-1000XM5 - بريميوم", 'search'),
    ("https://www.amazon.sa/s?k=sony+wf-1000xm5&rh=p_8%3A30-99", "🎧 Sony WF-1000XM5 - بريميوم", 'search'),
    ("https://www.amazon.sa/s?k=bose+quietcomfort&rh=p_8%3A30-99", "🎧 Bose QuietComfort - بريميوم", 'search'),
    ("https://www.amazon.sa/s?k=bose+700&rh=p_8%3A30-99", "🎧 Bose 700 - بريميوم", 'search'),
    ("https://www.amazon.sa/s?k=sennheiser+momentum&rh=p_8%3A30-99", "🎧 Sennheiser Momentum - أوديوفيل", 'search'),
    ("https://www.amazon.sa/s?k=beats+studio+pro&rh=p_8%3A30-99", "🎧 Beats Studio Pro", 'search'),
    ("https://www.amazon.sa/s?k=jbl+tour+one&rh=p_8%3A30-99", "🎧 JBL Tour One", 'search'),
    ("https://www.amazon.sa/s?k=marshall+major&rh=p_8%3A30-99", "🎧 Marshall Major - ترندي", 'search'),
    ("https://www.amazon.sa/s?k=bang+olufsen&rh=p_8%3A30-99", "🎧 Bang & Olufsen - لاكشري", 'search'),
    ("https://www.amazon.sa/s?k=devialet&rh=p_8%3A30-99", "🎧 Devialet - لاكشري", 'search'),
    ("https://www.amazon.sa/s?k=sonos&rh=p_8%3A30-99", "🎧 Sonos - سماعات منزلية", 'search'),
    ("https://www.amazon.sa/s?k=anker+soundcore&rh=p_8%3A30-99", "🎧 Anker SoundCore - قيمة", 'search'),
    
    # 📷📷📷 CAMERAS - محتوى السعودية يدفع مبيعات الكاميرات
    ("https://www.amazon.sa/s?k=sony+a7iv&rh=p_8%3A30-99", "📷 Sony A7 IV - بروفيشنال", 'search'),
    ("https://www.amazon.sa/s?k=sony+a7rv&rh=p_8%3A30-99", "📷 Sony A7R V - التوب", 'search'),
    ("https://www.amazon.sa/s?k=canon+r6&rh=p_8%3A30-99", "📷 Canon R6 - بروفيشنال", 'search'),
    ("https://www.amazon.sa/s?k=canon+r5&rh=p_8%3A30-99", "📷 Canon R5 - التوب", 'search'),
    ("https://www.amazon.sa/s?k=fujifilm+xt5&rh=p_8%3A30-99", "📷 Fujifilm X-T5 - ترندي", 'search'),
    ("https://www.amazon.sa/s?k=fujifilm+x100v&rh=p_8%3A30-99", "📷 Fujifilm X100V - ترندي", 'search'),
    ("https://www.amazon.sa/s?k=nikon+z8&rh=p_8%3A30-99", "📷 Nikon Z8 - بروفيشنال", 'search'),
    ("https://www.amazon.sa/s?k=go+pro+hero+12&rh=p_8%3A30-99", "📷 GoPro Hero 12 - أكشن", 'search'),
    ("https://www.amazon.sa/s?k=dji+mini+4+pro&rh=p_8%3A30-99", "📷 DJI Mini 4 Pro - درون", 'search'),
    ("https://www.amazon.sa/s?k=dji+air+3&rh=p_8%3A30-99", "📷 DJI Air 3 - درون", 'search'),
    ("https://www.amazon.sa/s?k=dji+mavic+3+pro&rh=p_8%3A30-99", "📷 DJI Mavic 3 Pro - التوب", 'search'),
    ("https://www.amazon.sa/s?k=insta360&rh=p_8%3A30-99", "📷 Insta360 - 360°", 'search'),
    
    # 🏠🏠🏠 HOME & KITCHEN - الأكثر مبيعاً في السعودية (Vileda, Levoit)
    ("https://www.amazon.sa/s?k=dyson+v15&rh=p_8%3A30-99", "🏠 Dyson V15 - بريميوم", 'search'),
    ("https://www.amazon.sa/s?k=dyson+gen5&rh=p_8%3A30-99", "🏠 Dyson Gen5 - التوب", 'search'),
    ("https://www.amazon.sa/s?k=dyson+airwrap&rh=p_8%3A30-99", "🏠 Dyson Airwrap - بريميوم جداً", 'search'),
    ("https://www.amazon.sa/s?k=dyson+supersonic&rh=p_8%3A30-99", "🏠 Dyson Supersonic - بريميوم", 'search'),
    ("https://www.amazon.sa/s?k=levoit+air+purifier&rh=p_8%3A30-99", "🏠 Levoit Air Purifier - الأكثر مبيعاً", 'search'),
    ("https://www.amazon.sa/s?k=nespresso+vertuo&rh=p_8%3A30-99", "☕ Nespresso Vertuo - بريميوم", 'search'),
    ("https://www.amazon.sa/s?k=nespresso+original&rh=p_8%3A30-99", "☕ Nespresso Original", 'search'),
    ("https://www.amazon.sa/s?k=breville+barista&rh=p_8%3A30-99", "☕ Breville Barista Express - بريميوم", 'search'),
    ("https://www.amazon.sa/s?k=kitchenaid+stand+mixer&rh=p_8%3A30-99", "🍳 KitchenAid Stand Mixer - أيقونة", 'search'),
    ("https://www.amazon.sa/s?k=philips+air+fryer+premium&rh=p_8%3A30-99", "🍳 Philips Air Fryer Premium", 'search'),
    ("https://www.amazon.sa/s?k=lg+instaview&rh=p_8%3A30-99", "❄️ LG InstaView - ثلاجة بريميوم", 'search'),
    ("https://www.amazon.sa/s?k=samsung+bespoke&rh=p_8%3A30-99", "❄️ Samsung Bespoke - بريميوم", 'search'),
    ("https://www.amazon.sa/s?k=stanley+tumbler&rh=p_8%3A30-99", "🏠 Stanley Tumbler - ترندي في السعودية", 'search'),
    ("https://www.amazon.sa/s?k=owala&rh=p_8%3A30-99", "🏠 Owala - ترندي", 'search'),
    ("https://www.amazon.sa/s?k=vileda&rh=p_8%3A30-99", "🏠 Vileda - الأكثر مبيعاً في المنزل", 'search'),
    ("https://www.amazon.sa/s?k=ultrean&rh=p_8%3A30-99", "🏠 Ultrean - قيمة عالية", 'search'),
    ("https://www.amazon.sa/s?k=smeg&rh=p_8%3A30-99", "🏠 Smeg - لاكشري", 'search'),
    
    # 🌸🌸🌸 PERFUMES - السعوديون الأكثر إنفاقاً على العطور عالمياً
    ("https://www.amazon.sa/s?k=tom+ford+oud+wood&rh=p_8%3A30-99", "🌸 Tom Ford Oud Wood - لاكشري", 'search'),
    ("https://www.amazon.sa/s?k=tom+ford+black+orchid&rh=p_8%3A30-99", "🌸 Tom Ford Black Orchid", 'search'),
    ("https://www.amazon.sa/s?k=creed+aventus&rh=p_8%3A30-99", "🌸 Creed Aventus - التوب", 'search'),
    ("https://www.amazon.sa/s?k=creed+silver+mountain&rh=p_8%3A30-99", "🌸 Creed Silver Mountain", 'search'),
    ("https://www.amazon.sa/s?k=le+labo+santal+33&rh=p_8%3A30-99", "🌸 Le Labo Santal 33 - نيش", 'search'),
    ("https://www.amazon.sa/s?k=maison+francis+kurkdjian&rh=p_8%3A30-99", "🌸 MFK Baccarat - نيش", 'search'),
    ("https://www.amazon.sa/s?k=amouage&rh=p_8%3A30-99", "🌸 Amouage - عربي لاكشري", 'search'),
    ("https://www.amazon.sa/s?k=byredo&rh=p_8%3A30-99", "🌸 Byredo - نيش", 'search'),
    ("https://www.amazon.sa/s?k=diptyque&rh=p_8%3A30-99", "🌸 Diptyque - نيش", 'search'),
    ("https://www.amazon.sa/s?k=jo+malone&rh=p_8%3A30-99", "🌸 Jo Malone - بريميوم", 'search'),
    ("https://www.amazon.sa/s?k=chanel+bleu&rh=p_8%3A30-99", "🌸 Chanel Bleu - كلاسيك", 'search'),
    ("https://www.amazon.sa/s?k=chanel+coco&rh=p_8%3A30-99", "🌸 Chanel Coco", 'search'),
    ("https://www.amazon.sa/s?k=dior+sauvage&rh=p_8%3A30-99", "🌸 Dior Sauvage - بيستسلر", 'search'),
    ("https://www.amazon.sa/s?k=dior+jadore&rh=p_8%3A30-99", "🌸 Dior J'adore", 'search'),
    ("https://www.amazon.sa/s?k=gucci+oud&rh=p_8%3A30-99", "🌸 Gucci Oud", 'search'),
    ("https://www.amazon.sa/s?k=versace+eros&rh=p_8%3A30-99", "🌸 Versace Eros", 'search'),
    ("https://www.amazon.sa/s?k=armani+stronger+with+you&rh=p_8%3A30-99", "🌸 Armani Stronger With You", 'search'),
    ("https://www.amazon.sa/s?k=yves+saint+laurent+libre&rh=p_8%3A30-99", "🌸 YSL Libre", 'search'),
    ("https://www.amazon.sa/s?k=yves+saint+laurent+black+opium&rh=p_8%3A30-99", "🌸 YSL Black Opium", 'search'),
    ("https://www.amazon.sa/s?k=lancôme+la+vie+est+belle&rh=p_8%3A30-99", "🌸 Lancôme La Vie Est Belle", 'search'),
    ("https://www.amazon.sa/s?k=paco+rabanne+1+million&rh=p_8%3A30-99", "🌸 Paco Rabanne 1 Million", 'search'),
    ("https://www.amazon.sa/s?k=hugo+boss+bottled&rh=p_8%3A30-99", "🌸 Hugo Boss Bottled", 'search'),
    ("https://www.amazon.sa/s?k=reef+perfume&rh=p_8%3A30-99", "🌸 Reef Perfume - الأكثر مبيعاً في السعودية", 'search'),
    ("https://www.amazon.sa/s?k=afnan+9pm&rh=p_8%3A30-99", "🌸 Afnan 9PM - ترندي في السعودية", 'search'),
    ("https://www.amazon.sa/s?k=fragrance+world&rh=p_8%3A30-99", "🌸 Fragrance World - قيمة عالية", 'search'),
    ("https://www.amazon.sa/s?k=davidoff+cool+water&rh=p_8%3A30-99", "🌸 Davidoff Cool Water - كلاسيك", 'search'),
    ("https://www.amazon.sa/s?k=beesline+perfume&rh=p_8%3A30-99", "🌸 Beesline - عطور الحج والعمرة", 'search'),
    
    # 💄💄💄 BEAUTY & SKINCARE - الأكثر مبيعاً (Johnson & Johnson, COSRX)
    ("https://www.amazon.sa/s?k=la+mer&rh=p_8%3A30-99", "💆 La Mer - لاكشري", 'search'),
    ("https://www.amazon.sa/s?k=sk+ii&rh=p_8%3A30-99", "💆 SK-II - بريميوم", 'search'),
    ("https://www.amazon.sa/s?k=estee+lauder+advanced+night+repair&rh=p_8%3A30-99", "💆 Estée Lauder ANR - بيستسلر", 'search'),
    ("https://www.amazon.sa/s?k=lancome+genifique&rh=p_8%3A30-99", "💆 Lancôme Génifique", 'search'),
    ("https://www.amazon.sa/s?k=clarins+double+serum&rh=p_8%3A30-99", "💆 Clarins Double Serum", 'search'),
    ("https://www.amazon.sa/s?k=johnson+vita+rich&rh=p_8%3A30-99", "💆 Johnson Vita-Rich - الأكثر مبيعاً في السعودية", 'search'),
    ("https://www.amazon.sa/s?k=herbal+essences+argan&rh=p_8%3A30-99", "💆 Herbal Essences Argan - الأكثر مبيعاً", 'search'),
    ("https://www.amazon.sa/s?k=cosrx+pimple+patch&rh=p_8%3A30-99", "💆 COSRX Pimple Patch - ترندي", 'search'),
    ("https://www.amazon.sa/s?k=mighty+patch&rh=p_8%3A30-99", "💆 Mighty Patch - ترندي", 'search'),
    ("https://www.amazon.sa/s?k=niacinamide+serum&rh=p_8%3A30-99", "💆 Niacinamide Serum - ترندي", 'search'),
    ("https://www.amazon.sa/s?k=the+ordinary&rh=p_8%3A30-99", "💆 The Ordinary - مبيعات ضخمة", 'search'),
    ("https://www.amazon.sa/s?k=cerave&rh=p_8%3A30-99", "💆 CeraVe - بيستسلر", 'search'),
    ("https://www.amazon.sa/s?k=neutrogena&rh=p_8%3A30-99", "💆 Neutrogena", 'search'),
    ("https://www.amazon.sa/s?k=olay&rh=p_8%3A30-99", "💆 Olay", 'search'),
    ("https://www.amazon.sa/s?k=charlotte+tilbury&rh=p_8%3A30-99", "💄 Charlotte Tilbury - ميك أب بريميوم", 'search'),
    ("https://www.amazon.sa/s?k=nars&rh=p_8%3A30-99", "💄 NARS - ميك أب بريميوم", 'search'),
    ("https://www.amazon.sa/s?k=huda+beauty&rh=p_8%3A30-99", "💄 Huda Beauty - ترندي", 'search'),
    ("https://www.amazon.sa/s?k=fenty+beauty&rh=p_8%3A30-99", "💄 Fenty Beauty - ترندي", 'search'),
    ("https://www.amazon.sa/s?k=revolution+beauty&rh=p_8%3A30-99", "💄 Revolution Beauty - الأكثر مبيعاً", 'search'),
    ("https://www.amazon.sa/s?k=dabur+amla&rh=p_8%3A30-99", "💆 Dabur Amla - الأكثر مبيعاً في السعودية", 'search'),
    
    # 🚗🚗🚗 AUTOMOTIVE - الأكثر مبيعاً في السعودية (مناشف مايكروفايبر، زيوت)
    ("https://www.amazon.sa/s?k=showtop+microfiber&rh=p_8%3A30-99", "🚗 ShowTop Microfiber - الأكثر مبيعاً", 'search'),
    ("https://www.amazon.sa/s?k=shell+helix+ultra&rh=p_8%3A30-99", "🚗 Shell Helix Ultra - الأكثر مبيعاً", 'search'),
    ("https://www.amazon.sa/s?k=car+windshield+sun+shade&rh=p_8%3A30-99", "🚗 Car Sun Shade", 'search'),
    ("https://www.amazon.sa/s?k=car+seat+gap+storage&rh=p_8%3A30-99", "🚗 Car Seat Gap Storage - ترندي", 'search'),
    ("https://www.amazon.sa/s?k=car+organizer&rh=p_8%3A30-99", "🚗 Car Organizer", 'search'),
    ("https://www.amazon.sa/s?k=michelin+pilot+sport&rh=p_8%3A30-99", "🚗 Michelin Pilot Sport - بريميوم", 'search'),
    ("https://www.amazon.sa/s?k=continental+premiumcontact&rh=p_8%3A30-99", "🚗 Continental PremiumContact", 'search'),
    ("https://www.amazon.sa/s?k=garmin+dash+cam&rh=p_8%3A30-99", "🚗 Garmin Dash Cam", 'search'),
    ("https://www.amazon.sa/s?k=chemical+guys&rh=p_8%3A30-99", "🚗 Chemical Guys - عناية", 'search'),
    ("https://www.amazon.sa/s?k=adam%27s+polishes&rh=p_8%3A30-99", "🚗 Adam's Polishes - بريميوم", 'search'),
    ("https://www.amazon.sa/s?k=car+vacuum&rh=p_8%3A30-99", "🚗 Car Vacuum", 'search'),
    ("https://www.amazon.sa/s?k=car+air+freshener&rh=p_8%3A30-99", "🚗 Car Air Freshener", 'search'),
    
    # 🧴🧴🧴 BATH & BODY - الأكثر مبيعاً في السعودية (Johnson, Herbal Essences)
    ("https://www.amazon.sa/s?k=johnson+body+wash&rh=p_8%3A30-99", "🧴 Johnson Body Wash - #1 في السعودية", 'search'),
    ("https://www.amazon.sa/s?k=herbal+essences+shampoo&rh=p_8%3A30-99", "🧴 Herbal Essences Shampoo - #2 في السعودية", 'search'),
    ("https://www.amazon.sa/s?k=downy+fabric+softener&rh=p_8%3A30-99", "🧴 Downy Fabric Softener - مبيعات ضخمة", 'search'),
    ("https://www.amazon.sa/s?k=comfort+fabric+softener&rh=p_8%3A30-99", "🧴 Comfort Fabric Softener - مبيعات ضخمة", 'search'),
    ("https://www.amazon.sa/s?k=fairy+dishwashing&rh=p_8%3A30-99", "🧴 Fairy Dishwashing - الأكثر مبيعاً", 'search'),
    ("https://www.amazon.sa/s?k=clorox+bleach&rh=p_8%3A30-99", "🧴 Clorox Bleach", 'search'),
    ("https://www.amazon.sa/s?k=raid+insect+killer&rh=p_8%3A30-99", "🧴 Raid Insect Killer - الأكثر مبيعاً", 'search'),
    
    # 🍚🍚🍚 GROCERY - السعوديون يشترون بالجملة (مياه، حليب، أرز)
    ("https://www.amazon.sa/s?k=nestle+pure+life+water&rh=p_8%3A30-99", "🍚 Nestlé Pure Life Water - #1 في السعودية", 'search'),
    ("https://www.amazon.sa/s?k=nadec+milk&rh=p_8%3A30-99", "🍚 Nadec Milk - #2 في السعودية", 'search'),
    ("https://www.amazon.sa/s?k=berain+water&rh=p_8%3A30-99", "🍚 Berain Water", 'search'),
    ("https://www.amazon.sa/s?k=abu+kass+rice&rh=p_8%3A30-99", "🍚 Abu Kass Rice - الأكثر مبيعاً", 'search'),
    ("https://www.amazon.sa/s?k=basmati+rice&rh=p_8%3A30-99", "🍚 Basmati Rice", 'search'),
    
    # 🧳🧳🧳 FASHION & LUGGAGE - الأكثر مبيعاً (SKY-TOUCH, JOTO)
    ("https://www.amazon.sa/s?k=sky+touch+luggage+organizer&rh=p_8%3A30-99", "🧳 SKY-TOUCH Luggage Organizer - #1", 'search'),
    ("https://www.amazon.sa/s?k=joto+water+shoes&rh=p_8%3A30-99", "👟 JOTO Water Shoes - الأكثر مبيعاً", 'search'),
    ("https://www.amazon.sa/s?k=cotton+crew+socks&rh=p_8%3A30-99", "🧦 Cotton Crew Socks - مبيعات ضخمة", 'search'),
    ("https://www.amazon.sa/s?k=luggage+scale&rh=p_8%3A30-99", "🧳 Luggage Scale", 'search'),
    ("https://www.amazon.sa/s?k=nike+air+jordan&rh=p_8%3A30-99", "👟 Nike Air Jordan - ترندي", 'search'),
    ("https://www.amazon.sa/s?k=nike+dunk&rh=p_8%3A30-99", "👟 Nike Dunk - ترندي", 'search'),
    ("https://www.amazon.sa/s?k=adidas+ultraboost&rh=p_8%3A30-99", "👟 Adidas Ultraboost", 'search'),
    ("https://www.amazon.sa/s?k=new+balance+990&rh=p_8%3A30-99", "👟 New Balance 990 - ترندي", 'search'),
    ("https://www.amazon.sa/s?k=asics+gel+kayano&rh=p_8%3A30-99", "👟 ASICS Gel Kayano", 'search'),
    ("https://www.amazon.sa/s?k=hoka&rh=p_8%3A30-99", "👟 HOKA - ترندي", 'search'),
    ("https://www.amazon.sa/s?k=on+running&rh=p_8%3A30-99", "👟 On Running - سويسري", 'search'),
    ("https://www.amazon.sa/s?k=salomon&rh=p_8%3A30-99", "👟 Salomon - ترندي", 'search'),
    ("https://www.amazon.sa/s?k=ray+ban+aviator&rh=p_8%3A30-99", "🕶️ Ray-Ban Aviator - كلاسيك", 'search'),
    ("https://www.amazon.sa/s?k=ray+ban+wayfarer&rh=p_8%3A30-99", "🕶️ Ray-Ban Wayfarer", 'search'),
    ("https://www.amazon.sa/s?k=oakley+holbrook&rh=p_8%3A30-99", "🕶️ Oakley Holbrook", 'search'),
    ("https://www.amazon.sa/s?k=prada+sunglasses&rh=p_8%3A30-99", "🕶️ Prada - لاكشري", 'search'),
    ("https://www.amazon.sa/s?k=gucci+sunglasses&rh=p_8%3A30-99", "🕶️ Gucci - لاكشري", 'search'),
    
    # 🧱🧱🧱 TOYS - الأكثر مبيعاً (Lego, Barbie, Hot Wheels)
    ("https://www.amazon.sa/s?k=lego+technic&rh=p_8%3A30-99", "🧱 LEGO Technic - بريميوم", 'search'),
    ("https://www.amazon.sa/s?k=lego+star+wars&rh=p_8%3A30-99", "🧱 LEGO Star Wars - كلاسيك", 'search'),
    ("https://www.amazon.sa/s?k=lego+icons&rh=p_8%3A30-99", "🧱 LEGO Icons - بريميوم", 'search'),
    ("https://www.amazon.sa/s?k=barbie+dreamhouse&rh=p_8%3A30-99", "👸 Barbie DreamHouse - بريميوم", 'search'),
    ("https://www.amazon.sa/s?k=hot+wheels+track&rh=p_8%3A30-99", "🚗 Hot Wheels Track", 'search'),
    ("https://www.amazon.sa/s?k=fisher+price&rh=p_8%3A30-99", "👶 Fisher-Price", 'search'),
    ("https://www.amazon.sa/s?k=waterwipes&rh=p_8%3A30-99", "👶 WaterWipes - الأكثر مبيعاً", 'search'),
    ("https://www.amazon.sa/s?k=pampers&rh=p_8%3A30-99", "👶 Pampers - مبيعات ضخمة", 'search'),
    ("https://www.amazon.sa/s?k=bugaboo&rh=p_8%3A30-99", "👶 Bugaboo - عربة بريميوم", 'search'),
    ("https://www.amazon.sa/s?k=stokke&rh=p_8%3A30-99", "👶 Stokke - نرويجي بريميوم", 'search'),
    
    # 🏋️🏋️🏋️ SPORTS & FITNESS - السعوديون يهتمون باللياقة (Vision 2030)
    ("https://www.amazon.sa/s?k=bowflex&rh=p_8%3A30-99", "🏋️ Bowflex - بريميوم", 'search'),
    ("https://www.amazon.sa/s?k=nordictrack&rh=p_8%3A30-99", "🏋️ NordicTrack - بريميوم", 'search'),
    ("https://www.amazon.sa/s?k=peloton&rh=p_8%3A30-99", "🏋️ Peloton - التوب", 'search'),
    ("https://www.amazon.sa/s?k=concept2&rh=p_8%3A30-99", "🏋️ Concept2 - بروفيشنال", 'search'),
    ("https://www.amazon.sa/s?k=theragun&rh=p_8%3A30-99", "🏋️ Theragun - مساج بريميوم", 'search'),
    ("https://www.amazon.sa/s?k=hyperice&rh=p_8%3A30-99", "🏋️ Hyperice - ريكفري بريميوم", 'search'),
    ("https://www.amazon.sa/s?k=whoop&rh=p_8%3A30-99", "🏋️ WHOOP - تراكر بريميوم", 'search'),
    ("https://www.amazon.sa/s?k=oura+ring&rh=p_8%3A30-99", "🏋️ Oura Ring - ترندي", 'search'),
    ("https://www.amazon.sa/s?k=optimum+nutrition&rh=p_8%3A30-99", "💪 Optimum Nutrition - بروتين #1", 'search'),
    ("https://www.amazon.sa/s?k=dymatize+iso+100&rh=p_8%3A30-99", "💪 Dymatize ISO100", 'search'),
    ("https://www.amazon.sa/s?k=cellucor+c4&rh=p_8%3A30-99", "💪 Cellucor C4 - بري وركاوت", 'search'),
    ("https://www.amazon.sa/s?k=bicycle&rh=p_8%3A30-99", "🚲 Bicycle - رياضة", 'search'),
    ("https://www.amazon.sa/s?k=camping&rh=p_8%3A30-99", "⛺ Camping - ترندي", 'search'),
    
    # 💾💾💾 STORAGE & MEMORY - إكسسوارات إلكترونيات ربحية
    ("https://www.amazon.sa/s?k=samsung+990+pro&rh=p_8%3A30-99", "💾 Samsung 990 Pro - التوب", 'search'),
    ("https://www.amazon.sa/s?k=wd+black+sn850x&rh=p_8%3A30-99", "💾 WD Black SN850X - جيمينج", 'search'),
    ("https://www.amazon.sa/s?k=sandisk+extreme+pro&rh=p_8%3A30-99", "💾 SanDisk Extreme Pro", 'search'),
    ("https://www.amazon.sa/s?k=lexar+professional&rh=p_8%3A30-99", "💾 Lexar Professional", 'search'),
    ("https://www.amazon.sa/s?k=synology+nas&rh=p_8%3A30-99", "💾 Synology NAS - بروفيشنال", 'search'),
    
    # 🔋🔋🔋 POWER & CHARGING - إكسسوارات ربحية
    ("https://www.amazon.sa/s?k=anker+prime&rh=p_8%3A30-99", "🔋 Anker Prime - بريميوم", 'search'),
    ("https://www.amazon.sa/s?k=anker+737&rh=p_8%3A30-99", "🔋 Anker 737 - التوب", 'search'),
    ("https://www.amazon.sa/s?k=ugreen+nexode&rh=p_8%3A30-99", "🔋 UGREEN Nexode", 'search'),
    ("https://www.amazon.sa/s?k=baseus+blade&rh=p_8%3A30-99", "🔋 Baseus Blade", 'search'),
    ("https://www.amazon.sa/s?k=belkin+magsafe&rh=p_8%3A30-99", "🔌 Belkin MagSafe - بريميوم", 'search'),
    ("https://www.amazon.sa/s?k=mophie&rh=p_8%3A30-99", "🔌 Mophie - بريميوم", 'search'),
    
    # 🏠🏠🏠 SMART HOME - السعوديون يتجهون للمنزل الذكي
    ("https://www.amazon.sa/s?k=philips+hue&rh=p_8%3A30-99", "💡 Philips Hue - سمارت", 'search'),
    ("https://www.amazon.sa/s?k=ring+doorbell&rh=p_8%3A30-99", "🏠 Ring Doorbell - أمان", 'search'),
    ("https://www.amazon.sa/s?k=arlo+pro&rh=p_8%3A30-99", "🏠 Arlo Pro - كاميرا", 'search'),
    ("https://www.amazon.sa/s?k=nest+thermostat&rh=p_8%3A30-99", "🏠 Nest Thermostat - ذكي", 'search'),
    ("https://www.amazon.sa/s?k=roborock&rh=p_8%3A30-99", "🏠 Roborock - بريميوم", 'search'),
    ("https://www.amazon.sa/s?k=ecovacs&rh=p_8%3A30-99", "🏠 Ecovacs", 'search'),
    ("https://www.amazon.sa/s?k=irobot+roomba&rh=p_8%3A30-99", "🏠 iRobot Roomba - كلاسيك", 'search'),
    
    # 📚📚📚 E-READERS - Kindle الأكثر مبيعاً في السعودية
    ("https://www.amazon.sa/s?k=kindle+paperwhite&rh=p_8%3A30-99", "📚 Kindle Paperwhite - الأكثر مبيعاً", 'search'),
    ("https://www.amazon.sa/s?k=kindle+scribe&rh=p_8%3A30-99", "📚 Kindle Scribe - بريميوم", 'search'),
    ("https://www.amazon.sa/s?k=kindle+colorsoft&rh=p_8%3A30-99", "📚 Kindle Colorsoft - جديد", 'search'),
    ("https://www.amazon.sa/s?k=echo+dot&rh=p_8%3A30-99", "🔊 Echo Dot - الأكثر مبيعاً في السعودية", 'search'),
    ("https://www.amazon.sa/s?k=echo+spot&rh=p_8%3A30-99", "🔊 Echo Spot", 'search'),
    ("https://www.amazon.sa/s?k=echo+show&rh=p_8%3A30-99", "🔊 Echo Show", 'search'),
    ("https://www.amazon.sa/s?k=echo+pop&rh=p_8%3A30-99", "🔊 Echo Pop", 'search'),
    
    # 🎯🎯🎯 GENERAL ELECTRONICS - باقي الإلكترونيات
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
    ✅ يدور في كل الأقسام والصفحات لحد ما يلاقي 20 منتج
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
        # ✅ لو وصلنا للهدف، نوقف
        if len(all_deals) >= TARGET_DEALS_COUNT:
            logger.info(f"🎯 Target reached! Found {len(all_deals)} deals")
            break
        
        # ✅ نبدأ من آخر صفحة + 1
        start_page = last_page_tracker.get(cat_name, 0) + 1
        
        # ✅ ندور في صفحات متعددة من نفس القسم
        for page_num in range(start_page, start_page + 5):  # 5 صفحات من كل قسم
            if len(all_deals) >= TARGET_DEALS_COUNT:
                break
            
            page_counter += 1
            
            # ✅ بناء الرابط
            if cat_type in ['best_sellers', 'deals', 'warehouse', 'coupons', 'lightning', 'today', 'outlet']:
                # ✅ للأقسام الخاصة، نستخدم pagination مختلف
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
            
            for item in items:
                try:
                    deal = parse_item(item, cat_name, cat_type == 'best_sellers')
                    
                    # ✅ شروط الصفقة
                    if deal and deal['discount'] >= MIN_DISCOUNT and deal['rating'] >= MIN_RATING:
                        if deal['id'] not in sent_products and not is_similar_product(deal['title']):
                            all_deals.append(deal)
                            logger.info(f"✅ ADDED: {deal['title'][:40]} | {deal['discount']}% | {deal['rating']}★")
                            
                            # ✅ لو وصلنا للهدف، نوقف فوراً
                            if len(all_deals) >= TARGET_DEALS_COUNT:
                                last_page_tracker[cat_name] = page_num
                                save_database()
                                return all_deals
                            
                except:
                    continue
            
            # ✅ تحديث آخر صفحة
            last_page_tracker[cat_name] = page_num
            
            time.sleep(random.uniform(1, 2))
    
    save_database()
    logger.info(f"🎯 Search complete! Found {len(all_deals)} deals")
    return all_deals

def filter_and_send_deals(deals, chat_id):
    """
    ✅ يبعت العروض مرتبة: السوبر (90%+) الأول
    """
    if not deals:
        updater.bot.send_message(
            chat_id=chat_id,
            text="❌ مفيش عروض 40%+ لقيتها\n🔄 جرب تاني بعد شوية!",
            parse_mode='Markdown'
        )
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
• يدور في *200+ قسم* مختلف
• يبحث في *كل الصفحات* لحد ما يلاقي 20 منتج
• خصومات *40%+* | تقييم *3 نجوم+*
• عروض *90%+* بشكل خاص 🚨
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
        "🔍 *بدأت البحث عن 20 منتج...*\n"
        "📄 بدور في كل الأقسام والصفحات\n"
        "⏳ *الوقت المتوقع: 3-5 دقايق*",
        parse_mode='Markdown'
    )

    try:
        deals = search_all_deals(chat_id, status_msg.message_id)
        
        try:
            updater.bot.delete_message(chat_id, status_msg.message_id)
        except:
            pass
        
        filter_and_send_deals(deals, chat_id)
        
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
🎯 الهدف كل مرة: *20 منتج*
📉 الحد الأدنى للخصم: *{MIN_DISCOUNT}%*
⭐ الحد الأدنى للتقييم: *{MIN_RATING}*

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
    logger.info(f"🎯 Target: {TARGET_DEALS_COUNT} deals")
    
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
