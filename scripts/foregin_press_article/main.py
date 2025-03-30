import os
import datetime
import pandas as pd
import requests
from scraper_ars_technica import scrape_arstechnica_gadgets
from scraper_nyt import nyt_url_scraper, nyt_article_scraper
from scraper_techcrunch import techcrunch_url_scraper, techcrunch_article_scraper
from scraper_zdnet import scrape_articles_from_page
from scraper_itworld import itworld_scraper, itworld_article_scraper  # IT World 추가

LAST_RUN_FILE = "last_run.txt"
FLASK_SERVER_URL = "http://localhost:8080/upload"


def get_last_run_date():
    if os.path.exists(LAST_RUN_FILE):
        with open(LAST_RUN_FILE, "r") as f:
            return datetime.datetime.strptime(f.read().strip(), "%Y-%m-%d")
    return datetime.datetime(2000, 1, 1)


def update_last_run_date():
    with open(LAST_RUN_FILE, "w") as f:
        f.write(datetime.datetime.now().strftime("%Y-%m-%d"))


def filter_articles_by_date(articles, last_run_date):
    filtered_articles = []
    for article in articles:
        try:
            article_date = datetime.datetime.strptime(article["date"], "%Y-%m-%d")
            if article_date > last_run_date:
                filtered_articles.append(article)
        except ValueError:
            print(f"⚠️ 날짜 형식 오류: {article['date']} (URL: {article['url']})")
    return filtered_articles


def send_to_flask_server(articles, is_foreign=False):
    if not articles:
        print("📭 전송할 새로운 기사가 없습니다.")
        return
    url = "http://localhost:8080/upload_foreign" if is_foreign else "http://localhost:8080/upload"
    try:
        response = requests.post(url, json=articles)
        if response.status_code == 200:
            print(f"✅ {len(articles)}개의 기사가 Flask 서버로 성공적으로 전송되었습니다.")
        else:
            print(f"❌ 서버 응답 실패: {response.status_code} - {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"❌ 서버 요청 중 오류 발생: {e}")


def main():
    last_run_date = get_last_run_date()
    print(f"📅 마지막 실행 날짜: {last_run_date.strftime('%Y-%m-%d')}")

    print("\n🔍 Ars Technica 스크래핑 중...")
    arstechnica_articles = scrape_arstechnica_gadgets(num_pages=5)
    arstechnica_articles = filter_articles_by_date(arstechnica_articles, last_run_date)
    send_to_flask_server(arstechnica_articles)

    print("\n🔍 New York Times 스크래핑 중...")
    nyt_urls = nyt_url_scraper()
    nyt_articles = nyt_article_scraper(nyt_urls)
    nyt_articles = filter_articles_by_date(nyt_articles, last_run_date)
    send_to_flask_server(nyt_articles)

    print("\n🔍 TechCrunch 스크래핑 중...")
    techcrunch_urls = techcrunch_url_scraper()
    techcrunch_articles = techcrunch_article_scraper(techcrunch_urls)
    techcrunch_articles = filter_articles_by_date(techcrunch_articles, last_run_date)
    send_to_flask_server(techcrunch_articles)

    print("\n🔍 ZDNet 스크래핑 중...")
    zdnet_articles = []
    for page in range(1, 6):
        zdnet_articles.extend(scrape_articles_from_page(page))
    zdnet_articles = filter_articles_by_date(zdnet_articles, last_run_date)
    send_to_flask_server(zdnet_articles)

    print("\n🔍 IT World 스크래핑 중...")
    itworld_articles = []
    TOPIC_URLS = [
        "https://www.itworld.co.kr/cloud-computing/",
        "https://www.itworld.co.kr/generative-ai/",
        "https://www.itworld.co.kr/artificial-intelligence/"
    ]
    for topic_url in TOPIC_URLS:
        urls = itworld_scraper(topic_url)
        articles = itworld_article_scraper(urls)
        itworld_articles.extend(articles)

    itworld_articles = filter_articles_by_date(itworld_articles, last_run_date)
    send_to_flask_server(itworld_articles)

    update_last_run_date()
    print("\n✅ 모든 크롤링 및 데이터 전송이 완료되었습니다!")


if __name__ == "__main__":
    main()
