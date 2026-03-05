import requests
from bs4 import BeautifulSoup

def get_deals():
    URLS = [
        "https://www.amazon.sa/s?i=fashion",
        "https://www.amazon.sa/s?i=beauty"
    ]

    HEADERS = {
        "User-Agent": "Mozilla/5.0"
    }

    deals = []

    for url in URLS:
        for page in range(1, 6):  # 5 صفحات لكل قسم
            r = requests.get(f"{url}&page={page}", headers=HEADERS)
            soup = BeautifulSoup(r.text, "html.parser")
            products = soup.select(".s-result-item")

            for p in products:
                try:
                    title = p.select_one("h2 span").text
                    price_tag = p.select_one(".a-price-whole")
                    if not price_tag:
                        continue
                    price = float(price_tag.text.replace(",", ""))
                    link_tag = p.select_one("h2 a")
                    if not link_tag:
                        continue
                    link = "https://amazon.sa" + link_tag["href"]
                    discount_tag = p.select_one(".savingsPercentage")
                    discount = int(discount_tag.text.replace("%","")) if discount_tag else 0

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
