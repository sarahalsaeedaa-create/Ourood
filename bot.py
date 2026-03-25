🚀 OPTIMIZED AMAZON DEALS BOT (FAST + SMART + LOW BAN RISK)


import os
import re
import json
import time
import random
import hashlib
import logging
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler


import cloudscraper
from bs4 import BeautifulSoup
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters


================= CONFIG =================


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PORT = int(os.environ.get("PORT", 8080))


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(name)


sent_ids = set()
is_scanning = False
updater = None


================= SESSION =================


def create_session():
scraper = cloudscraper.create_scraper(delay=5)
scraper.headers.update({
"User-Agent": "Mozilla/5.0",
"Accept-Language": "ar-SA,ar;q=0.9"
})
return scraper


================= FETCH =================


def fetch(session, url):
try:
time.sleep(random.uniform(1, 2))
r = session.get(url, timeout=20)
if r.status_code == 200:
return r.text
except Exception as e:
logger.warning(e)
return None


================= PARSE =================


def parse_items(html):
soup = BeautifulSoup(html, 'html.parser')
items = soup.select('[data-component-type="s-search-result"]')
deals = []


for item in items:
    try:
        title = item.select_one('h2 span')
        price = item.select_one('.a-price-whole')
        rating = item.select_one('.a-icon-alt')

        if not title or not price:
            continue

        title = title.text.strip()
        price = float(price.text.replace(',', ''))

        rating_val = 0
        if rating:
            rating_val = float(re.search(r"\d+\.?\d*", rating.text).group())

        if rating_val < 4:
            continue

        link = item.select_one('a')['href']
        link = "https://www.amazon.sa" + link

        pid = hashlib.md5(title.encode()).hexdigest()
        if pid in sent_ids:
            continue

        deals.append({
            "title": title,
            "price": price,
            "rating": rating_val,
            "link": link,
            "id": pid
        })

    except:
        continue

return deals



================= SEARCH =================


URLS = [
"https://www.amazon.sa/s?k=discount",
"https://www.amazon.sa/s?k=clearance",
"https://www.amazon.sa/s?k=flash+sale",
"https://www.amazon.sa/gp/movers-and-shakers",
"https://www.amazon.sa/gp/goldbox",
]


def search():
session = create_session()
results = []


for i in range(0, len(URLS), 2):  # batching
    batch = URLS[i:i+2]

    for url in batch:
        html = fetch(session, url)
        if html:
            results.extend(parse_items(html))

    time.sleep(3)  # anti-ban pause

return results



================= SEND =================


def send(chat_id, deals):
global sent_ids


if not deals:
    updater.bot.send_message(chat_id, "❌ لا يوجد عروض")
    return

for d in deals[:20]:  # limit
    msg = f"""



🔥 صفقة قوية


📦 {d['title'][:100]}
💰 {d['price']} ريال
⭐ {d['rating']}


🔗 {d['link']}
"""
updater.bot.send_message(chat_id, msg)
sent_ids.add(d['id'])
time.sleep(1)


================= COMMANDS =================


def start(update, context):
update.message.reply_text("اكتب Hi للبحث عن أفضل العروض 🔥")


def hi(update, context):
global is_scanning


if is_scanning:
    update.message.reply_text("⏳ جاري البحث...")
    return

is_scanning = True

deals = search()
send(update.effective_chat.id, deals)

is_scanning = False



================= HEALTH =================


class Handler(BaseHTTPRequestHandler):
def do_GET(self):
self.send_response(200)
self.end_headers()
self.wfile.write(b"OK")


================= MAIN =================


def main():
global updater


threading.Thread(target=lambda: HTTPServer(('0.0.0.0', PORT), Handler).serve_forever(), daemon=True).start()

updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
dp = updater.dispatcher

dp.add_handler(CommandHandler("start", start))
dp.add_handler(MessageHandler(Filters.regex("(?i)^hi$"), hi))

updater.start_polling()
updater.idle()



if name == "main":
main()

