import os
import time
from telegram import Bot
from scraper import get_deals

TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

bot = Bot(token=TOKEN)

while True:
    deals = get_deals()
    for d in deals:
        message = f"""
🔥 عرض جديد

{d['title']}

💰 السعر: {d['price']} ريال
📉 الخصم: {d['discount']}%

{d['link']}
"""
        bot.send_message(chat_id=CHAT_ID, text=message)
    time.sleep(600)  # كل 10 دقائق
