# scripts/scraper.py
import requests

def scrape_data():
    url = "https://example.com"
    response = requests.get(url)
    return response.text