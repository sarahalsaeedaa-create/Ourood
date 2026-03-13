import os
import re
import json
import logging
import requests
import cloudscraper
from datetime import datetime
from bs4 import BeautifulSoup
from telegram import Bot, Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from fake_useragent import UserAgent
from difflib import SequenceMatcher
import time
import random
import hashlib
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "YOUR_CHAT_ID")
PORT = int(os.environ.get("PORT", 8080))

ua = UserAgent()
sent_products = set()
sent_hashes = set()
is_scanning = False
updater = None
def load_database():
    global sent_products, sent_hashes
    try:
        if os.path.exists('bot_database.json'):
            with open('bot_database.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
                sent_products = set(data.get('ids', []))
                sent_hashes = set(data.get('hashes', []))
    except Exception as e:
        logger.error(e)


def save_database():
    with open('bot_database.json', 'w', encoding='utf-8') as f:
        json.dump({
            "ids": list(sent_products),
            "hashes": list(sent_hashes)
        }, f)
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
    categories = [

("https://www.amazon.sa/gp/bestsellers/electronics","Electronics",True),
("https://www.amazon.sa/gp/bestsellers/fashion","Fashion",True),
("https://www.amazon.sa/gp/bestsellers/beauty","Beauty",True),
("https://www.amazon.sa/gp/bestsellers/home","Home",True),
("https://www.amazon.sa/gp/bestsellers/kitchen","Kitchen",True),

("https://www.amazon.sa/gp/goldbox","Goldbox",False),
("https://www.amazon.sa/gp/todays-deals","Today Deals",False),

("https://www.amazon.sa/gp/warehouse-deals","Warehouse Deals",False),

("https://www.amazon.sa/outlet","Outlet",False),

("https://www.amazon.sa/gp/coupons","Coupons",False),

("https://www.amazon.sa/gp/prime/pipeline/lightning_deals","Lightning Deals",False),

("https://www.amazon.sa/s?k=flash+sale","Flash Sale",False),
("https://www.amazon.sa/s?k=clearance","Clearance",False),

("https://www.amazon.sa/s?k=mega+deal","Mega Deal",False),
("https://www.amazon.sa/s?k=big+sale","Big Sale",False),

("https://www.amazon.sa/s?k=iphone","iPhone",False),
("https://www.amazon.sa/s?k=ipad","iPad",False),
("https://www.amazon.sa/s?k=macbook","MacBook",False),

("https://www.amazon.sa/s?k=samsung+galaxy","Galaxy",False),

("https://www.amazon.sa/s?k=sony+headphones","Sony Headphones",False),

("https://www.amazon.sa/s?k=gaming+mouse","Gaming Mouse",False),

("https://www.amazon.sa/s?k=playstation+5","PS5",False),

("https://www.amazon.sa/s?k=nintendo+switch","Nintendo",False),

("https://www.amazon.sa/s?k=canon+camera","Canon",False),

("https://www.amazon.sa/s?k=gopro","GoPro",False),

("https://www.amazon.sa/s?k=apple+watch","Apple Watch",False),

("https://www.amazon.sa/s?k=garmin+watch","Garmin",False),

("https://www.amazon.sa/s?k=dior+perfume","Dior",False),

("https://www.amazon.sa/s?k=gucci+perfume","Gucci",False),

("https://www.amazon.sa/s?k=nike+shoes","Nike",False),

("https://www.amazon.sa/s?k=adidas+shoes","Adidas",False),

("https://www.amazon.sa/s?k=rayban","Rayban",False),

("https://www.amazon.sa/s?k=swarovski","Swarovski",False),

("https://www.amazon.sa/s?k=lego","Lego",False),

("https://www.amazon.sa/s?k=barbie","Barbie",False),

("https://www.amazon.sa/s?k=protein+powder","Protein",False),

("https://www.amazon.sa/s?k=creatine","Creatine",False),

("https://www.amazon.sa/s?k=dyson+vacuum","Dyson",False),

("https://www.amazon.sa/s?k=bosch+tools","Bosch",False),

("https://www.amazon.sa/s?k=michelin+tires","Michelin",False),

("https://www.amazon.sa/s?k=kindle","Kindle",False),

("https://www.amazon.sa/s?k=dates","Dates",False),

("https://www.amazon.sa/s?k=oud","Oud",False),

("https://www.amazon.sa/s?k=abaya","Abaya",False),

("https://www.amazon.sa/s?k=thobe","Thobe",False),

# الأماكن الجديدة المضافة

("https://www.amazon.sa/s?k=refurbished","Refurbished",False),
("https://www.amazon.sa/s?k=renewed+iphone","Renewed iPhone",False),
("https://www.amazon.sa/s?k=renewed+laptop","Renewed Laptop",False),

("https://www.amazon.sa/s?k=trending+products","Trending",False),

("https://www.amazon.sa/s?k=viral+products","Viral Products",False),

("https://www.amazon.sa/s?k=cool+gadgets","Cool Gadgets",False),

("https://www.amazon.sa/s?k=tech+gadgets","Tech Gadgets",False),

("https://www.amazon.sa/s?k=smart+home","Smart Home",False),

("https://www.amazon.sa/s?k=smart+camera","Smart Camera",False),

("https://www.amazon.sa/s?k=phone+accessories","Phone Accessories",False),

("https://www.amazon.sa/s?k=laptop+accessories","Laptop Accessories",False),

("https://www.amazon.sa/s?k=gaming+accessories","Gaming Accessories",False)

    ]
    def main():

    global updater

    load_database()

    updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)

    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start_cmd))
    dp.add_handler(CommandHandler("status", status_cmd))
    dp.add_handler(CommandHandler("clear", clear_cmd))

    dp.add_handler(MessageHandler(Filters.regex(r'(?i)^hi$'), hi_cmd))

    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, unknown))

    updater.start_polling()

    updater.idle()


if __name__ == "__main__":
    main()
