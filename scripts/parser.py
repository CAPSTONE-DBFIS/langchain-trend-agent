# scripts/parser.py
from bs4 import BeautifulSoup

def parse_data(raw_html):
    soup = BeautifulSoup(raw_html, 'html.parser')
    # 원하는 데이터 추출 예시
    data = soup.find_all('div', class_='example')
    return [item.text for item in data]