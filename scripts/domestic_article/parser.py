import concurrent.futures
import requests
from datetime import datetime
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
import time

ua = UserAgent()  # fake-useragent 객체 생성

def fetch_html(url, retries=3, timeout=10):  # 타임아웃 기본값 10초로 변경
    """requests로 HTML 페이지를 가져오는 함수"""
    headers = {
        "User-Agent": ua.chrome,  # fake-useragent를 사용하여 무작위로 User-Agent 설정
    }

    session = requests.Session()  # 연결 풀링 활성화
    for attempt in range(1, retries + 1):
        try:
            response = session.get(url, headers=headers, timeout=timeout)
            if response.status_code == 200:
                return response.text
            else:
                print(f"오류: {response.status_code} - {url}")
        except requests.exceptions.RequestException as e: # 오류 처리
            print(f"{url}에서 {attempt}번째 시도 중 오류 발생: {e}")
            time.sleep(2 ** attempt)
    print(f"{url}에서 {retries}번 시도 후에도 데이터를 가져올 수 없습니다.")
    return None


def parse_data(url):
    """URL을 받아서 기사 HTML을 파싱"""
    html_content = fetch_html(url)

    if not html_content:
        return None

    soup = BeautifulSoup(html_content, 'html.parser')

    # 카테고리 추출
    category_tag = soup.find('em', class_='media_end_categorize_item')
    category = category_tag.get_text(strip=True) if category_tag else None

    # 언론사 이름 추출
    media_logo_tag = soup.find('a', class_="media_end_head_top_logo")
    media_name = media_logo_tag.img[
        'title'] if media_logo_tag and media_logo_tag.img and 'title' in media_logo_tag.img.attrs else None

    # 기사 제목 추출
    title_tag = soup.find('h2', class_='media_end_head_headline')
    title = title_tag.get_text(strip=True) if title_tag else None

    # 게시일자 추출
    date_tag = soup.find('span', class_='media_end_head_info_datestamp_time')
    raw_date = date_tag.get_text(strip=True) if date_tag else None

    try:
        if raw_date:
            date_part = raw_date.split()[0].replace(".", "-").strip("-")
            date = datetime.strptime(date_part, "%Y-%m-%d").strftime("%Y-%m-%d")
        else:
            date = None
    except (IndexError, ValueError) as e:
        print(f"날짜 파싱 오류: {url} - {e}")
        return None

    # 기사 내용 추출
    content_tag = soup.find('div', id='newsct_article')
    content = content_tag.get_text(strip=True) if content_tag else None

    # 대표 이미지 URL 추출
    og_image = soup.find('meta', property='og:image')
    image_url = og_image['content'] if og_image and og_image.get('content') else None

    # 필수 필드 검증
    required_fields = [category, media_name, title, date, content]
    if any(field is None for field in required_fields):
        print(f"필드값 누락 해당 기사는 저장하지 않음: {url}")
        return None

    return {
        "category": category,
        "media_company": media_name,
        "title": title,
        "date": date,
        "content": content,
        "url": url,
        "image_url": image_url
    }


def parse_articles_in_parallel(article_urls, max_workers):
    """병렬 HTML 파싱 함수"""
    print("HTML 파싱 시작")
    results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {executor.submit(parse_data, url): url for url in article_urls}

        for future in concurrent.futures.as_completed(future_to_url):
            url = future_to_url[future]
            try:
                result = future.result()
                if result:
                    results.append(result)
            except Exception as e:
                print(f"{url} 처리 중 예외 발생: {e}")

    print("모든 HTML 파싱 완료")
    return results