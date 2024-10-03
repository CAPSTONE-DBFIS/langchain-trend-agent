# scripts/main.py
from scraper import scrape_data
from parser import parse_data

if __name__ == "__main__":
    raw_data = scrape_data()
    parsed_data = parse_data(raw_data)
    print(parsed_data)