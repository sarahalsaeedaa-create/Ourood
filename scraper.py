import requests
from bs4 import BeautifulSoup

def get_deals():

    url = "https://www.amazon.sa/s?i=beauty"

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    r = requests.get(url, headers=headers)

    soup = BeautifulSoup(r.text, "html.parser")

    products = soup.select(".s-result-item")

    deals = []

    for p in products:

        try:

            title = p.select_one("h2 span").text

            price = p.select_one(".a-price-whole")

            if not price:
                continue

            price = float(price.text.replace(",", ""))

            link = "https://amazon.sa" + p.select_one("h2 a")["href"]

            discount = 0

            d = p.select_one(".savingsPercentage")

            if d:
                discount = int(d.text.replace("%",""))

            if discount >= 60 or price <= 1:

                deals.append({
                    "title": title,
                    "price": price,
                    "discount": discount,
                    "link": link
                })

        except:
            continue

    return deals
