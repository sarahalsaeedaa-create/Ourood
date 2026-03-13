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
    categories = generate_categories()
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
