FROM python:3.11-slim

WORKDIR /app

# تثبيت dependencies
RUN apt-get update && apt-get install -y gcc libxml2-dev libxslt1-dev

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]
