import requests
from bs4 import BeautifulSoup
import time
import os
from utils import format_date, save_to_csv

# 최신 User-Agent (2025년 기준)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nytimes.com/",
    "Connection": "keep-alive"
}

ERROR_MESSAGE = ("We are having trouble retrieving the article content.Please enable JavaScript in your browser settings."
                 "Thank you for your patience while we verify access. If you are in Reader mode please exit and log into your Times account,"
                 " or subscribe for all of The Times.Thank you for your patience while we verify access.Already a subscriber? Log in."
                 "Want all of The Times? Subscribe.")

def nyt_url_scraper(page=2):
    """지정한 페이지에서 기사 URL을 수집합니다."""
    base_url = "https://www.nytimes.com/section/technology"
    url = f"{base_url}?page={page}"
    links = []

    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        soup = BeautifulSoup(response.content, 'html.parser')
        list_items = soup.find_all('li', class_='css-18yolpw')
        for item in list_items:
            a_tag = item.find('a', href=True)
            if a_tag:
                link = a_tag['href']
                if link.startswith('/'):
                    link = "https://www.nytimes.com" + link
                links.append(link)
    else:
        print(f"페이지 {page} 요청 실패: 상태 코드 {response.status_code}")

    return links

def nyt_article_scraper(urls):
    articles = []
    media_company = "New York Times"

    for url in urls:
        # ip 차단을 피하기 위한 딜레이
        time.sleep(1)
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')

            # 제목 추출
            title_tag = soup.find('h1', {'data-testid': 'headline'})
            title = title_tag.text.strip() if title_tag else "제목 없음"

            # 날짜 추출 및 포맷 변경 (YYYY-MM-DD)
            time_tag = soup.find('time', datetime=True)
            date_str = time_tag['datetime'][:10] if time_tag else "날짜 없음"
            formatted_date = format_date(date_str, input_format="%Y-%m-%d")

            # 본문 추출
            content_tag = soup.find('section', {'name': 'articleBody'})
            content = content_tag.text.strip() if content_tag else "본문 없음"
            # 오류 메시지 제거
            content = content.replace(ERROR_MESSAGE, "").strip()

            articles.append({
                "media_company": media_company,
                "date": formatted_date,
                "title": title,
                "content": content,
                "url": url
            })
        else:
            print(f"기사 요청 실패: {url} (상태 코드 {response.status_code})")
    return articles

if __name__ == "__main__":
    urls = nyt_url_scraper()
    articles = nyt_article_scraper(urls)
    save_to_csv(articles, '../../data/raw/nyt_article.csv')
