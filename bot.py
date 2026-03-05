import os
from telegram import Bot
from scraper import get_deals

TOKEN = os.getenv("8769441239:AAEgX3uBbtWc_hHcqs0lmQ50AqKJGOWV6Ok")
CHAT_ID = os.getenv("432826122")

bot = Bot(token=TOKEN)

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
