import requests
from bs4 import BeautifulSoup
import pandas as pd
import os


def nyt_url_scraper():
    # 뉴욕타임즈 기술 섹션 URL
    base_url = "https://www.nytimes.com/section/technology"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36"
    }
    links = []

    for page in range(1, 4):  # 페이지 범위 조정 (1부터 필요한 페이지까지)
        url = f"{base_url}?page={page}"
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            list_items = soup.find_all('li', class_='css-18yolpw')

            for item in list_items:
                a_tag = item.find('a', href=True)
                if a_tag:
                    # 상대 경로를 절대 경로로 변환
                    link = a_tag['href']
                    if not link.startswith("http"):
                        link = "https://www.nytimes.com" + link
                    links.append(link)
        else:
            print(f"페이지 {page} 요청 실패: 상태 코드 {response.status_code}")

    return links


def nyt_article_scraper(urls):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36"
    }

    articles = []

    for url in urls:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')

            # Title 추출
            title_tag = soup.find('h1', {'data-testid': 'headline'})
            title = title_tag.text.strip() if title_tag else "제목 없음"

            # Date 추출 (YYYY-MM-DD 형식 유지)
            time_tag = soup.find('time', datetime=True)
            date = time_tag['datetime'][:10] if time_tag else "날짜 없음"  # 날짜만 저장 (YYYY-MM-DD)

            # Description 추출
            desc_tag = soup.find('section', {'name': 'articleBody'})
            desc = desc_tag.text.strip() if desc_tag else "요약 없음"

            # 결과 저장
            articles.append({
                "url": url,
                "title": title,
                "date": date,  # YYYY-MM-DD 형식 유지
                "desc": desc
            })
        else:
            print(f"기사 요청 실패: {url} (상태 코드 {response.status_code})")

    return articles


def save_to_csv(articles, filepath):
    # 데이터프레임 생성
    df = pd.DataFrame(articles)

    # 제목 없음 또는 요약 없음 데이터 필터링
    filtered_df = df[(df['title'] != "제목 없음") & (df['desc'] != "요약 없음")]

    # 디렉토리 생성 (존재하지 않을 경우)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    # CSV 파일 저장
    filtered_df.to_csv(filepath, index=False, encoding='utf-8-sig')
    print(f"CSV 파일이 저장되었습니다: {filepath}")


if __name__ == "__main__":
    # 1단계: 기사 URL 크롤링
    urls = nyt_url_scraper()

    # 2단계: 각 URL의 기사 제목, 날짜, 요약 크롤링
    articles = nyt_article_scraper(urls)

    # 3단계: 결과를 CSV 파일로 저장 (제목 또는 요약이 없는 데이터 제외)
    save_to_csv(articles, '../../data/raw/nyt_article.csv')