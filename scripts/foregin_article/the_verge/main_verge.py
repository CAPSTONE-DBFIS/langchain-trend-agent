import requests
from bs4 import BeautifulSoup
import os
import pandas as pd
import sys
import time
from pathlib import Path

# 절대 경로 설정을 위한 기본 디렉토리 경로 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
base_dir = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
sys.path.append(base_dir)

# 상대 경로 대신 절대 경로 임포트 사용
from scripts.foregin_article.the_verge.scraper_poster import poster_detail_scraper
from scripts.foregin_article.the_verge.scraper_news import news_detail_scraper
from scripts.foregin_article.utils import save_to_csv

BASE_URL = "https://www.theverge.com"


def verge_url_scraper(page: int = 1, section_url: str = f"{BASE_URL}/tech"):
    """
    지정한 섹션 페이지에서 포스터 및 일반 기사 URL을 반환합니다.
    - page=1: https://www.theverge.com/tech (또는 지정된 섹션)
    - page>1: https://www.theverge.com/tech/archives/{page} (또는 지정된 섹션)
    """
    if page < 1:
        raise ValueError("page must be >= 1")

    section_base = section_url.rstrip("/")
    if page == 1:
        url = section_base
    else:
        section_path = section_base.replace(BASE_URL, "")
        url = f"{BASE_URL}{section_path}/archives/{page}"

    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    # (1) 포스터 카드
    poster_cards = soup.select(
        "div.duet--content-cards--content-card.duet--content-cards--quick-post"
    )
    # (2) 일반 기사 카드
    article_cards = soup.select(
        "div.duet--content-cards--content-card._1ufh7nr1._1ufh7nr0._1lkmsmo0"
    )

    poster_urls = []
    article_urls = []

    for card in poster_cards:
        a_tag = card.find("a", href=True)
        if a_tag:
            href = a_tag["href"]
            full = href if href.startswith("http") else BASE_URL + href
            poster_urls.append(full)

    for card in article_cards:
        a_tag = card.find("a", href=True)
        if a_tag:
            href = a_tag["href"]
            full = href if href.startswith("http") else BASE_URL + href
            article_urls.append(full)
        else:
            span = card.select_one("span.coral-count")
            if span and span.has_attr("data-coral-url"):
                article_urls.append(span["data-coral-url"])

    return poster_urls, article_urls


def get_category_from_url(section_url):
    """URL에서 카테고리 추출"""
    if "ai-artificial-intelligence" in section_url:
        return "AI"
    elif "science" in section_url:
        return "SCIENCE"
    else:
        return "TECH"  # 기본 카테고리


def the_verge_start(page_count: int = 1):
    """
    The Verge 기사 스크래핑을 시작하는 함수.
    지정된 페이지 수를 고려하여 각 섹션에서 스크래핑을 시도합니다.

    Args:
        page_count (int): 고려할 페이지 수 (각 섹션별로 적용)

    Returns:
        list: 스크래핑된 기사 리스트
    """
    print(f"The Verge 기사 스크래핑 시작 (각 섹션당 최대 {page_count}페이지)")

    section_urls = [
        "https://www.theverge.com/tech",
        "https://www.theverge.com/ai-artificial-intelligence",
        "https://www.theverge.com/science"
    ]

    all_articles_data = []
    total_failed = 0
    seen_urls = set()  # 중복 검사용 URL 세트

    for section_index, section_url in enumerate(section_urls):
        print(f"The Verge: 섹션 {section_index + 1}/{len(section_urls)} 스크래핑 시작")
        category = get_category_from_url(section_url)

        for page in range(1, page_count + 1):
            print(f"The Verge: 섹션 {section_index + 1}, 페이지 {page}/{page_count} 스크래핑 중")
            poster_urls, article_urls = verge_url_scraper(page, section_url)

            # 포스터 기사 스크래핑
            for url in poster_urls:
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                try:
                    article_data = poster_detail_scraper(url, category)
                    if article_data and article_data.get("title") and article_data.get("content"):
                        article_data["media_company"] = "THE_VERGE"
                        all_articles_data.append(article_data)
                    else:
                        total_failed += 1
                except Exception as e:
                    print(f"Failed to scrape poster at {url}: {e}")
                    total_failed += 1

            # 일반 기사 스크래핑
            for url in article_urls:
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                try:
                    article_data = news_detail_scraper(url, category)
                    if article_data and article_data.get("title") and article_data.get("content"):
                        article_data["media_company"] = "THE_VERGE"
                        all_articles_data.append(article_data)
                    else:
                        total_failed += 1
                except Exception as e:
                    print(f"Failed to scrape article at {url}: {e}")
                    total_failed += 1

            if page < page_count:
                time.sleep(2)

        print(f"The Verge: 섹션 {section_index + 1} 스크래핑 완료, 총 수집 기사: {len(all_articles_data)}")

    print(f"The Verge: 총 {len(all_articles_data)}개 기사 스크래핑 성공, {total_failed}개 실패")

    if all_articles_data:
        csv_file_path = os.path.join(base_dir, "data", "raw", "the_verge_article.csv")
        save_to_csv(all_articles_data, csv_file_path)
        print(f"The Verge: CSV 파일 저장 완료 ({csv_file_path})")

    return all_articles_data


if __name__ == "__main__":
    the_verge_start(1)  # 기본값으로 1페이지 수집
