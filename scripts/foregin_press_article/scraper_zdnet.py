import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from utils import format_date, save_to_csv

# 기본 User-Agent 설정
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/115.0.0.0 Safari/537.36"
    )
}

media_company = "ZDNET"


def convert_relative_date(relative_str):
    """
    상대 날짜 문자열(예: "2 days ago", "1 week ago")를 오늘 날짜 기준의 절대 날짜("YYYY-MM-DD")로 변환합니다.
    """
    relative_str = relative_str.strip().lower()
    today = datetime.today()

    try:
        if "day" in relative_str:
            num = int(relative_str.split()[0])
            target_date = today - timedelta(days=num)
        elif "week" in relative_str:
            num = int(relative_str.split()[0])
            target_date = today - timedelta(weeks=num)
        elif "month" in relative_str:
            num = int(relative_str.split()[0])
            target_date = today - timedelta(days=num * 30)  # 대략 30일 기준
        elif "year" in relative_str:
            num = int(relative_str.split()[0])
            target_date = today - timedelta(days=num * 365)
        else:
            target_date = today
    except Exception as e:
        print(f"날짜 변환 오류 ({relative_str}): {e}")
        target_date = today

    return target_date.strftime("%Y-%m-%d")


def scrape_articles_from_page(page):
    """
    지정한 페이지 번호에 따라 기사 목록 HTML을 요청한 후,
    각 기사 컨테이너에서 URL, 제목, 날짜, 설명을 추출합니다.
    """
    if page == 1:
        url = "https://www.zdnet.com/topic/developer/"
        headers = HEADERS.copy()
    else:
        url = f"https://www.zdnet.com/topic/developer/{page}/"
        headers = HEADERS.copy()
        headers["X-Requested-With"] = "XMLHttpRequest"  # AJAX 요청임을 알림

    print(f"페이지 {page} 요청: {url}")
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"페이지 {page} 요청 실패, 상태 코드: {response.status_code}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    containers = soup.find_all("div", class_="c-listingDefault_item g-outer-spacing-bottom-large")
    articles = []

    for container in containers:
        try:
            # URL 추출
            a_tag = container.find("a", class_="c-listingDefault_itemLink")
            if not a_tag:
                continue
            href = a_tag.get("href")
            if not href.startswith("http"):
                href = "https://www.zdnet.com" + href

            # 제목 추출
            title_tag = container.find("h3",
                                       class_="c-listingDefault_title g-text-small-bold g-outer-spacing-bottom-xsmall")
            if not title_tag:
                continue
            title = title_tag.get_text(strip=True)

            # 설명 추출
            content_tag = container.find("span",
                                         class_="c-listingDefault_description g-text-xsmall g-outer-spacing-bottom-small")
            if not content_tag:
                continue
            content = content_tag.get_text(strip=True)

            # 날짜 추출 및 변환
            date_tag = container.find("span", class_="c-listingDefault_pubDate")
            if not date_tag:
                continue
            relative_date = date_tag.get_text(strip=True)
            date_str = convert_relative_date(relative_date)
            formatted_date = format_date(date_str, input_format="%Y-%m-%d")

            articles.append({
                "media_company": media_company,
                "date": formatted_date,
                "title": title,
                "content": content,
                "url": href
            })
        except Exception as e:
            print(f"기사 파싱 중 오류: {e}")
            continue
    return articles


def start():
    # 원하는 페이지 범위 설정 (예: 1~5페이지)
    start_page = 1
    end_page = 5
    all_articles = []

    for page in range(start_page, end_page + 1):
        articles = scrape_articles_from_page(page)
        all_articles.extend(articles)

    if all_articles:
        csv_filepath = "../../data/raw/zdnet_article.csv"
        save_to_csv(all_articles, csv_filepath)
    else:
        print("수집된 기사가 없습니다.")


if __name__ == "__main__":
    start()
