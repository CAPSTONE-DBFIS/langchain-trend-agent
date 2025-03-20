import requests
from bs4 import BeautifulSoup
from datetime import datetime
import time
import pandas as pd
import os

# 최신 User-Agent (2025년 기준)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nytimes.com/",
    "Connection": "keep-alive"
}

ERROR_MESSAGE = "We are having trouble retrieving the article content.Please enable JavaScript in your browser settings.Thank you for your patience while we verify access. If you are in Reader mode please exit and log into your Times account, or subscribe for all of The Times.Thank you for your patience while we verify access.Already a subscriber? Log in.Want all of The Times? Subscribe."

def nyt_url_scraper(page=2):
    """ 지정한 페이지에서 기사 URL을 수집 """
    base_url = "https://www.nytimes.com/section/technology"
    url = f"{base_url}?page={page}"
    links = []

    response = requests.get(url, headers=HEADERS)

    if response.status_code == 200:
        soup = BeautifulSoup(response.content, 'html.parser')

        # li 태그에서 기사 링크를 포함한 a 태그 찾기
        list_items = soup.find_all('li', class_='css-18yolpw')

        for item in list_items:
            a_tag = item.find('a', href=True)
            if a_tag:
                link = a_tag['href']
                if link.startswith('/'):  # 내부 링크 처리
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

            # 제목 가져오기
            title_tag = soup.find('h1', {'data-testid': 'headline'})
            title = title_tag.text.strip() if title_tag else "제목 없음"

            # 날짜 가져오기
            time_tag = soup.find('time', datetime=True)
            date = time_tag['datetime'][:10] if time_tag else "날짜 없음"
            formatted_date = datetime.strptime(date, "%Y-%m-%d").strftime("%Y.%m.%d")

            # 본문 가져오기
            content_tag = soup.find('section', {'name': 'articleBody'})
            content = content_tag.text.strip() if content_tag else "요약 없음"

            # 오류 메시지를 기사 본문에서 제거
            content = content.replace(ERROR_MESSAGE, "").strip()

            articles.append({
                "media_company": media_company,
                "date": formatted_date,
                "title": title,
                "content": content,
                "url": url,
            })
        else:
            print(f"기사 요청 실패: {url} (상태 코드 {response.status_code})")

    return articles


def save_to_csv(articles, filepath):
    if not articles:
        print("저장할 데이터가 없습니다. CSV 저장을 중단합니다.")
        return

    df = pd.DataFrame(articles)

    if 'title' not in df.columns or 'content' not in df.columns:
        print("데이터프레임에 title 또는 desc 컬럼이 존재하지 않습니다. CSV 저장을 중단합니다.")
        return

    filtered_df = df[(df['title'] != "제목 없음") & (df['content'] != "내용 없음")]

    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    filtered_df.to_csv(filepath, index=False, encoding='utf-8-sig')
    print(f"CSV 파일이 저장되었습니다: {filepath}")


if __name__ == "__main__":
    urls = nyt_url_scraper()
    articles = nyt_article_scraper(urls)
    save_to_csv(articles, '../../data/raw/nyt_article.csv')
