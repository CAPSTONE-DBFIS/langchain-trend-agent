import os
import csv
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

# 기본 User-Agent 설정
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/115.0.0.0 Safari/537.36"
    )
}


def convert_relative_date(relative_str):
    """
    상대 날짜 문자열(예: "2 days ago", "1 week ago")를 오늘 날짜 기준의 절대 날짜("YYYY-MM-DD")로 변환합니다.
    (월, 연도 등의 단위도 간단히 계산합니다.)
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
            target_date = today - timedelta(days=num * 30)  # 대략 30일
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
    지정한 페이지 번호(page)에 따라 기사 목록 HTML을 요청한 후,
    각 기사 컨테이너( <div class="c-listingDefault_item g-outer-spacing-bottom-large"> )에서
    URL, 제목, 날짜, 설명을 추출하여 리스트로 반환합니다.

    첫 페이지는 "https://www.zdnet.com/topic/developer/"로 요청하고,
    페이지 2 이상은 URL에 페이지 번호를 추가하고 AJAX 헤더를 포함합니다.
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

    html = response.text
    soup = BeautifulSoup(html, "html.parser")

    # 기사 컨테이너 선택자
    containers = soup.find_all("div", class_="c-listingDefault_item g-outer-spacing-bottom-large")
    articles = []

    for container in containers:
        try:
            # URL 추출: 첫 번째 <a class="c-listingDefault_itemLink"> 태그 사용
            a_tag = container.find("a", class_="c-listingDefault_itemLink")
            if not a_tag:
                continue
            href = a_tag.get("href")
            if not href.startswith("http"):
                href = "https://www.zdnet.com" + href

            # 제목 추출: <h3 class="c-listingDefault_title g-text-small-bold g-outer-spacing-bottom-xsmall">
            title_tag = container.find("h3",
                                       class_="c-listingDefault_title g-text-small-bold g-outer-spacing-bottom-xsmall")
            if not title_tag:
                continue
            title = title_tag.get_text(strip=True)

            # 설명 추출: <span class="c-listingDefault_description g-text-xsmall g-outer-spacing-bottom-small">
            desc_tag = container.find("span",
                                      class_="c-listingDefault_description g-text-xsmall g-outer-spacing-bottom-small")
            if not desc_tag:
                continue
            desc = desc_tag.get_text(strip=True)

            # 날짜 추출: <span class="c-listingDefault_pubDate">
            date_tag = container.find("span", class_="c-listingDefault_pubDate")
            if not date_tag:
                continue
            relative_date = date_tag.get_text(strip=True)
            date = convert_relative_date(relative_date)
            formatted_date = datetime.strptime(date, "%Y-%m-%d").strftime("%Y.%m.%d")

            articles.append({
                "url": href,
                "title": title,
                "date": formatted_date,
                "desc": desc
            })
        except Exception as e:
            print(f"기사 파싱 중 오류: {e}")
            continue
    return articles


def save_to_csv(articles, filepath):
    """
    수집한 기사 데이터를 지정한 CSV 파일 경로에 'utf-8-sig' 인코딩으로 저장합니다.
    """
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    fieldnames = ["url", "title", "date", "desc"]
    with open(filepath, "w", newline="", encoding="utf-8-sig") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for article in articles:
            writer.writerow(article)
    print(f"CSV 파일 저장 완료: {filepath}")


def main():
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
    main()
