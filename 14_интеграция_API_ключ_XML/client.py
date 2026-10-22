"""Занятие 14. Клиент на Python (requests): те же запросы, что делает client.html.

Запуск: API_KEY=... python client.py   (адрес API можно поменять переменной API_URL)
"""
import os

import requests

URL = os.getenv("API_URL", "http://127.0.0.1:8000")
HEADERS = {"X-API-Key": os.environ["API_KEY"]}  # ключ из переменной окружения, не из кода

r = requests.get(f"{URL}/titles/top", params={"year": 2019, "limit": 5}, headers=HEADERS)
r.raise_for_status()
print("Топ-5 за 2019 (JSON):")
for row in r.json():
    print(f"  {row['total']:>4}  {row['title']}")

r = requests.get(f"{URL}/titles/top", params={"year": 2019, "limit": 3, "format": "xml"}, headers=HEADERS)
r.raise_for_status()
print("\nТоп-3 за 2019 (XML):")
print(r.text)

r = requests.get(f"{URL}/search", params={"q": "novel"}, headers=HEADERS)
r.raise_for_status()
print(f"\nПоиск 'novel': найдено {len(r.json())}, первые 3:")
for row in r.json()[:3]:
    print(f"  {row['title_id']}: {row['title']}")

r = requests.get(f"{URL}/titles/top", params={"year": 2019})  # без ключа
print(f"\nБез ключа: HTTP {r.status_code} {r.json()}")
