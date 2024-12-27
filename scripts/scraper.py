from concurrent.futures import ThreadPoolExecutor
import requests
from dotenv import load_dotenv
import os

# .env 파일 로드
load_dotenv()

# 네이버 API 키 가져오기
client_id = os.getenv('NAVER_CLIENT_ID')
client_secret = os.getenv('NAVER_CLIENT_SECRET')

# 네이버 뉴스 검색 API를 이용하여 카테고리에 해당하는 뉴스 URL을 가져오는 함수
def naver_search(query, display=10, start=1):
    url = "https://openapi.naver.com/v1/search/news.json"

    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret
    }

    params = {
        "query": query,
        "display": display,
        "start": start
    }

    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        data = response.json()
        naver_links = [item['link'] for item in data['items'] if 'n.news.naver.com' in item['link']]
        return naver_links
    else:
        print(f"Error Code: {response.status_code}")
        return []

# 단일 URL에 대해 HTML을 요청하고 결과를 반환하는 함수
def fetch_url(url):
    try:
        response = requests.get(url)
        if response.status_code == 200:
            return response.text, url
        else:
            print(f"Failed to fetch URL: {url}, Status Code: {response.status_code}")
            return None, url
    except Exception as e:
        print(f"Error fetching URL: {url}, Error: {e}")
        return None, url

# 카테고리별로 병렬 크롤링을 수행하고 결과를 반환하는 함수
def scrape_data_by_category(categories):
    all_raw_html_list = []
    all_url_list = []

    with ThreadPoolExecutor(max_workers=5) as executor:
        # 카테고리별 네이버 뉴스 검색
        category_urls = {category: naver_search(category) for category in categories}
        for category, urls in category_urls.items():
            print(f"크롤링 중인 카테고리: {category}, URL 수: {len(urls)}")

            # 병렬로 각 URL의 HTML 데이터 가져오기
            if urls:
                results = executor.map(fetch_url, urls)
                for raw_html, url in results:
                    if raw_html:
                        all_raw_html_list.append(raw_html)
                        all_url_list.append(url)

    return all_raw_html_list, all_url_list