import requests
import re
import time
import pandas as pd
import os
from bs4 import BeautifulSoup


def extract_date_from_url(url):
    """
    URL에서 날짜 정보를 추출하여 "YYYY-M-DD" 형식으로 반환합니다.
    URL의 형식은 https://techcrunch.com/YYYY/MM/DD/... 이어야 합니다.
    """
    parts = url.split("/")
    try:
        # parts[3]: 연도, parts[4]: 월, parts[5]: 일
        year = parts[3]
        month = int(parts[4])
        day = int(parts[5])
        return f"{year}-{month}-{day:02d}"
    except Exception as e:
        print(f"날짜 추출 오류 ({url}): {e}")
        return "날짜를 찾을 수 없음"


def techcrunch_url_scraper():
    """
    TechCrunch 최신 페이지(1~4페이지)에서 기사 URL을 수집합니다.
    URL은 "https://techcrunch.com/YYYY/" 형식의 링크만 필터링하며,
    중복을 제거한 후 리스트로 반환합니다.
    """
    base_url = "https://techcrunch.com/latest/"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/112.0.0.0 Safari/537.36"
        )
    }
    links = []

    # 1페이지부터 4페이지까지 순회
    for page in range(1, 3):
        if page == 1:
            url = base_url
        else:
            url = f"{base_url}page/{page}/"
        print(f"페이지 {page} 스크래핑 중: {url}")
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"페이지 {page} 요청 실패: {e}")
            continue

        soup = BeautifulSoup(response.content, 'html.parser')
        # 모든 <a> 태그에서 href 추출
        for a_tag in soup.find_all('a', href=True):
            link = a_tag['href']
            # "https://techcrunch.com/YYYY/" 형식의 링크만 수집
            if re.match(r"^https://techcrunch\.com/\d{4}/", link):
                links.append(link)
        time.sleep(2)  # 페이지별 요청 딜레이

    # 중복 제거 (순서를 유지)
    unique_links = []
    seen = set()
    for link in links:
        if link not in seen:
            unique_links.append(link)
            seen.add(link)

    return unique_links


def clean_html_text(soup):
    """
    본문에서 불필요한 태그 제거 및 텍스트 정리
    """
    for tag in soup(['script', 'style', 'aside', 'form']):  # 불필요한 태그 제거
        tag.decompose()

    paragraphs = soup.find_all("p")
    cleaned_text = []
    for p in paragraphs:
        for a_tag in p.find_all('a'):
            a_tag.unwrap()  # <a> 태그 제거하고 텍스트만 유지
        cleaned_text.append(p.get_text(separator=" ", strip=True))

    text = " ".join(cleaned_text)
    text = re.sub(r'\s+', ' ', text)  # 연속 공백을 단일 공백으로 축소
    return text[:5000]  # 5000자 이상이면 앞부분만 저장

def techcrunch_article_scraper(urls):
    """
    각 기사 URL에 접속하여 제목, 날짜, 본문을 추출합니다.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/112.0.0.0 Safari/537.36"
        )
    }
    articles = []

    for url in urls:
        print(f"기사 스크래핑 중: {url}")
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"기사 요청 실패: {url} (오류: {e})")
            continue

        soup = BeautifulSoup(response.content, 'html.parser')

        # 제목 추출
        title_tag = soup.select_one("h1.article-hero__title.wp-block-post-title")
        title = title_tag.get_text(strip=True) if title_tag else "제목을 찾을 수 없음"

        # 날짜 추출: URL에서 추출
        date = extract_date_from_url(url)

        # 본문(desc) 추출
        desc_div = soup.select_one(
            "div.entry-content.wp-block-post-content.is-layout-constrained.wp-block-post-content-is-layout-constrained")
        if desc_div:
            desc = clean_html_text(desc_div)  # 본문을 깨지지 않게 정리
        else:
            desc = "본문을 찾을 수 없음"

        articles.append({
            "url": url,
            "title": title,
            "date": date,
            "desc": desc
        })

    return articles

def save_to_csv(articles, filepath):
    """
    수집된 기사 데이터를 DataFrame으로 변환한 후,
    제목, 날짜, 본문에 문제가 있는 데이터는 필터링하여 CSV 파일로 저장합니다.
    CSV 파일은 encoding='utf-8-sig'로 저장하여 한글이 깨지지 않도록 합니다.
    """
    df = pd.DataFrame(articles)

    # 제목, 날짜, 본문이 정상적으로 수집된 기사만 필터링
    valid_df = df[
        (df['title'] != "제목을 찾을 수 없음") &
        (df['title'] != "N/A") &
        (df['date'] != "날짜를 찾을 수 없음") &
        (df['date'] != "날짜를 파싱할 수 없음") &
        (df['date'] != "N/A") &
        (df['desc'] != "본문을 찾을 수 없음") &
        (df['desc'] != "N/A")
        ]

    if valid_df.empty:
        print("유효한 기사 데이터가 없어 CSV 파일에 저장하지 않습니다.")
        return

    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    valid_df.to_csv(filepath, index=False, encoding='utf-8-sig')
    print(f"유효한 기사 데이터 {len(valid_df)}건이 CSV 파일로 저장되었습니다: {filepath}")


def save_to_csv(articles, filepath):
    df = pd.DataFrame(articles)

    # 유효한 기사만 필터링
    valid_df = df[
        (df['title'] != "제목을 찾을 수 없음") &
        (df['date'] != "날짜를 찾을 수 없음") &
        (df['desc'] != "본문을 찾을 수 없음")
        ]

    if valid_df.empty:
        print("유효한 기사 데이터가 없어 CSV 파일에 저장하지 않습니다.")
        return

    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    # CSV 저장 시 쉼표(,) 처리를 위한 quotechar 옵션 추가
    valid_df.to_csv(filepath, index=False, encoding='utf-8-sig', quotechar='"')

    print(f"유효한 기사 데이터 {len(valid_df)}건이 CSV 파일로 저장되었습니다: {filepath}")


def main():
    # 1단계: TechCrunch 최신 페이지에서 기사 URL 수집
    urls = techcrunch_url_scraper()
    print(f"총 {len(urls)}개의 기사 URL 수집됨.\n")

    # 2단계: 각 URL에서 기사 제목, 날짜, 본문 수집
    articles = techcrunch_article_scraper(urls)

    # 3단계: 유효한 기사 데이터만 CSV 파일로 저장
    csv_path = "../../data/raw/techcrunch_article.csv"
    save_to_csv(articles, csv_path)


if __name__ == "__main__":
    main()
