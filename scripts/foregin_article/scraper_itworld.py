# scraper_itworld.py
import requests
from bs4 import BeautifulSoup
import os
from utils import format_date, save_to_csv

TOPIC_URLS = [
    "https://www.itworld.co.kr/cloud-computing/",
    "https://www.itworld.co.kr/generative-ai/",
    "https://www.itworld.co.kr/artificial-intelligence/",
    "https://www.itworld.co.kr/computers-and-peripherals/",
    "https://www.itworld.co.kr/data-center/",
    "https://www.itworld.co.kr/emerging-technology/",
    "https://www.itworld.co.kr/augmented-reality/",
    "https://www.itworld.co.kr/apple/",
    "https://www.itworld.co.kr/vendors-and-providers/",
    "https://www.itworld.co.kr/software-development/",
    "https://www.itworld.co.kr/security/",
    "https://www.itworld.co.kr/collaboration-software/",
    "https://www.itworld.co.kr/productivity-software/",
    "https://www.itworld.co.kr/windows/",
    "https://www.itworld.co.kr/android/",
    "https://www.itworld.co.kr/networking/",
    "https://www.itworld.co.kr/mobile/",
    "https://www.itworld.co.kr/it-management/",
    "https://www.itworld.co.kr/it-leadership/",
    "https://www.itworld.co.kr/enterprise-applications/"
]


def itworld_scraper(topic_url):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/112.0.0.0 Safari/537.36"
        )
    }
    links = []
    for page in range(1, 2):
        url = f"{topic_url}/page/{page}/"
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            if page == 1:
                list_items = soup.find_all('div', class_='content-listing-articles__row')
            else:
                list_items = soup.find_all('div', class_='content-listing-various__row')
            for item in list_items:
                a_tag = item.find('a', href=True)
                if a_tag:
                    link = a_tag['href']
                    if not link.startswith("http"):
                        link = "https://www.itworld.co.kr" + link
                    links.append(link)
        else:
            print(f"페이지 {page} 요청 실패: 상태 코드 {response.status_code}")
    return links


def itworld_article_scraper(urls):
    media_company = "IT WORLD"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/112.0.0.0 Safari/537.36"
        )
    }
    articles = []
    for url in urls:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')

            # 제목 추출
            title_tag = soup.find('h1', class_='article-hero__title')
            title = title_tag.text.strip() if title_tag else "제목 없음"

            # 날짜 추출 (예: 'div' 내의 두 번째 'span'에서 날짜 정보 추출)
            date = "날짜 없음"
            div_tag = soup.find('div', class_='card')
            if div_tag:
                spans = div_tag.find_all('span')
                if len(spans) > 1:
                    raw_date = spans[1].text.strip() if spans[1] else "날짜 없음"
                    if raw_date != "날짜 없음":
                        date = format_date(raw_date)
                    else:
                        date = raw_date

            # 콘텐츠 추출
            content_tag = soup.find('div', id='remove_no_follow')
            content = content_tag.text.strip() if content_tag else "콘텐츠 내용이 없음"

            articles.append({
                "media_company": media_company,
                "date": date,
                "title": title,
                "content": content,
                "url": url
            })
        else:
            print(f"기사 요청 실패: {url} (상태 코드 {response.status_code})")
    return articles


def start_scraper_itworld():
    all_articles = []
    for topic_url in TOPIC_URLS:
        # 토픽명 추출 (예: 'cloud-computing')
        topic_name = topic_url.split("/")[-2]
        print(f"크롤링 시작: {topic_name}")
        urls = itworld_scraper(topic_url)
        if urls:
            articles = itworld_article_scraper(urls)
            if articles:
                all_articles.extend(articles)
        else:
            print(f"{topic_name}에서 URL을 찾지 못했습니다.")
    save_to_csv(all_articles, "../../data/raw/itworld_articles.csv")


if __name__ == "__main__":
    start_scraper_itworld()
