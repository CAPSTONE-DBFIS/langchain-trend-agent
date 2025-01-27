# scripts/scraper.py
import os
import requests
from dotenv import load_dotenv
from datetime import datetime, timedelta

# .env 파일 로드
load_dotenv()

# 네이버 API 키 가져오기
client_id = os.getenv('NAVER_CLIENT_ID')
client_secret = os.getenv('NAVER_CLIENT_SECRET')

def naver_search(query, display=10, start=1, start_date=None, end_date=None):
    # 네이버 검색 API 요청 URL
    url = "https://openapi.naver.com/v1/search/news.json"

    # 요청 헤더 설정
    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret
    }

    # 요청 파라미터 설정
    params = {
        "query": query,
        "display": display,  # 한 번에 표시할 검색 결과 개수
        "start": start  # 검색 시작 위치
    }

    # 기간 설정 (YYYYMMDD 형식)
    if start_date:
        params["startDate"] = start_date
    if end_date:
        params["endDate"] = end_date

    # API 요청 보내기
    response = requests.get(url, headers=headers, params=params)

    # 상태 코드 200일 때만 데이터 반환
    if response.status_code == 200:
        # 응답 데이터에서 네이버 뉴스 링크만 추출
        data = response.json()
        naver_links = [item['link'] for item in data['items'] if 'n.news.naver.com' in item['link']]
        return naver_links
    else:
        print(f"Error Code: {response.status_code}")
        return None


def scrape_data_by_category(categories):
    all_raw_html_list = []
    all_url_list = []

    # 현재 날짜와 3개월 전 날짜 계산
    end_date = datetime.now()
    start_date = end_date - timedelta(days=90)

    # 날짜를 YYYYMMDD 형식으로 변환
    end_date_str = end_date.strftime('%Y%m%d')
    start_date_str = start_date.strftime('%Y%m%d')

    for category in categories:
        print(f"크롤링 중인 카테고리: {category}")
        urls = naver_search(category, start_date=start_date_str, end_date=end_date_str)

        if urls is None or len(urls) == 0:
            print(f"No URLs found for category: {category}")
            continue

        category_raw_html_list = []
        category_valid_urls = []

        for url in urls:
            response = requests.get(url)
            if response.status_code == 200:
                category_raw_html_list.append(response.text)
                category_valid_urls.append(url)
            else:
                print(f"Failed to retrieve data from {url}. Status code: {response.status_code}")

        all_raw_html_list.extend(category_raw_html_list)
        all_url_list.extend(category_valid_urls)

    return all_raw_html_list, all_url_list