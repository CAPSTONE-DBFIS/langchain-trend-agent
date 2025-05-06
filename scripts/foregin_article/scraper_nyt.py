import requests
from bs4 import BeautifulSoup
import time
import os
from utils import format_date, save_to_csv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import logging

# 최신 User-Agent (2025년 기준)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nytimes.com/",
    "Connection": "keep-alive"
}

# NYT 에러 메시지 (정확히 일치하는 문자열)
ERROR_MESSAGE = "We are having trouble retrieving the article content.Please enable JavaScript in your browser settings.Thank you for your patience while we verify access. If you are in Reader mode please exit and log into your Times account, or subscribe for all of The Times.Thank you for your patience while we verify access.Already a subscriber? Log in.Want all of The Times? Subscribe."

def setup_driver():
    """셀레니움 웹드라이버 설정"""
    # web driver 호출 시에 로깅되던 것을 WARNING 시에만 뜨도록 조정
    logging.getLogger("WDM").setLevel(logging.WARNING)
    
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # 브라우저 창 없이 실행
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument(f"user-agent={HEADERS['User-Agent']}")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    
    # webdriver-manager 사용하여 ChromeDriver 자동 설치
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def nyt_url_scraper(page=1):
    """지정한 페이지에서 기사 URL을 수집합니다. 셀레니움 사용"""
    base_url = "https://www.nytimes.com/section/technology"
    url = f"{base_url}?page={page}"
    links = []

    # 셀레니움으로 페이지 로드
    driver = setup_driver()
    try:
        driver.get(url)
        
        # 페이지가 로드될 때까지 잠시 대기
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "ol[data-testid='asset-stream']"))
        )
        
        # 스크롤을 페이지 끝까지 내려서 모든 콘텐츠 로드
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)  # 모든 콘텐츠가 로드될 시간을 주기

        html_content = driver.page_source
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # li 요소 찾기
        list_items = soup.find_all('li', class_='css-18yolpw')

        for idx, item in enumerate(list_items):
            # a 태그 찾기
            a_tag = item.find('a', class_='css-8hzhxf', href=True)
            
            # a 태그가 없을 경우 대체 로직
            if a_tag is None:
                all_a_in_item = item.find_all('a', href=True)
                if all_a_in_item:
                    a_tag = all_a_in_item[0]
            
            if a_tag:
                link = a_tag['href']
                if link.startswith('/'):
                    link = "https://www.nytimes.com" + link
                links.append(link)
    except Exception as e:
        print(f"[예외] 페이지 스크래핑 중 오류 발생: {str(e)}")
    finally:
        driver.quit()

    print(f"NYT: 페이지 {page}에서 {len(links)}개 URL 수집 완료")
    return links

def extract_image_url(soup):
    """기사에서 이미지 URL 추출 시도"""
    try:
        # css-rq4mmj 클래스의 img 태그 직접 찾기 (가장 명확한 방법)
        img = soup.find('img', class_='css-rq4mmj')
        if img:
            # srcset이 있는 경우 가장 큰 이미지 URL 추출
            if img.has_attr('srcset'):
                srcset = img['srcset']
                # srcset 형식: "url1 600w,url2 1024w,url3 2048w,..."
                parts = srcset.split(',')
                largest_img = ""
                largest_size = 0

                for part in parts:
                    part = part.strip()
                    if not part:
                        continue
                    img_parts = part.split()
                    if len(img_parts) >= 2:
                        img_url = img_parts[0]
                        # 크기 표시에서 'w' 제거하고 정수로 변환
                        try:
                            size = int(img_parts[1].replace("w", ""))
                            if size > largest_size:
                                largest_size = size
                                largest_img = img_url
                        except ValueError:
                            continue

                if largest_img:
                    return largest_img
            
            # srcset이 없거나 추출 실패시 src 사용
            if img.has_attr('src'):
                return img['src']
        
        # 비디오 썸네일 이미지 추출 (간단한 방법)
        video_img = soup.find('img', alt='Video player loading')
        if video_img and video_img.has_attr('src'):
            return video_img['src']

        # css-79elbk 클래스와 data-testid 속성으로 컨테이너 찾기
        img_container = soup.find('div', {'class': 'css-79elbk', 'data-testid': 'imageContainer-children-Image'})
        if img_container:
            img = img_container.find('img')
            if img:
                if img.has_attr('srcset'):
                    srcset = img['srcset']
                    parts = srcset.split(',')
                    largest_img = ""
                    largest_size = 0

                    for part in parts:
                        part = part.strip()
                        if not part:
                            continue
                        img_parts = part.split()
                        if len(img_parts) >= 2:
                            img_url = img_parts[0]
                            try:
                                size = int(img_parts[1].replace("w", ""))
                                if size > largest_size:
                                    largest_size = size
                                    largest_img = img_url
                            except ValueError:
                                continue

                    if largest_img:
                        return largest_img
                
                if img.has_attr('src'):
                    return img['src']

        # 기존 방식도 유지 (하위 호환성)
        figure = soup.find('figure', {'itemprop': 'image'}) or soup.find('figure', class_='css-1pugwum')
        if figure:
            img = figure.find('img', src=True)
            if img:
                return img['src']

        # 다른 이미지 태그도 확인
        img = soup.find('img', {'data-testid': 'photoviewer-image'})
        if img and img.has_attr('src'):
            return img['src']
    except Exception as e:
        print(f"[예외] 이미지 URL 추출 오류: {str(e)}")

    return ""  # 이미지를 찾지 못한 경우 빈 문자열 반환

def nyt_article_scraper(urls):
    """기사 내용 스크래핑 - requests 사용"""
    articles = []
    media_company = "New York Times"
    category = "IT"  # 기본 카테고리 설정
    failed_count = 0
    
    print(f"NYT: 총 {len(urls)}개 URL 스크래핑 시작")

    for idx, url in enumerate(urls):
        # ip 차단을 피하기 위한 딜레이
        time.sleep(1)
        try:
            # requests로 페이지 요청
            response = requests.get(url, headers=HEADERS)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # 제목 추출
                title_tag = soup.find('h1', {'data-testid': 'headline'})
                if title_tag:
                    title = title_tag.text.strip()
                else:
                    # 대안: 다른 제목 태그 시도
                    alt_title_tags = soup.find_all('h1')
                    if alt_title_tags:
                        title = alt_title_tags[0].text.strip()
                    else:
                        title = "제목 없음"

                # 제목이 없으면 스킵
                if title == "제목 없음" or not title:
                    print(f"[예외] 제목이 없어 기사를 건너뜁니다: {url}")
                    failed_count += 1
                    continue

                # 날짜 추출 및 포맷 변경 (YYYY-MM-DD)
                time_tag = soup.find('time', datetime=True)
                if time_tag:
                    date_str = time_tag['datetime'][:10]
                    formatted_date = format_date(date_str, input_format="%Y-%m-%d")
                else:
                    formatted_date = "날짜 없음"

                # 본문 추출
                content_tag = soup.find('section', {'name': 'articleBody'})
                if content_tag:
                    # 전체 텍스트를 가져오고 에러 메시지 제거
                    content = content_tag.get_text(separator=" ", strip=True)
                    
                    # ERROR_MESSAGE가 정확히 포함되어 있는지 확인
                    if ERROR_MESSAGE in content:
                        # 에러 메시지를 빈 문자열로 대체
                        content = content.replace(ERROR_MESSAGE, "").strip()
                    
                    # 에러 메시지가 부분적으로 포함되었을 수 있으므로 추가 검사
                    if "We are having trouble retrieving the article content" in content and "Want all of The Times? Subscribe" in content:
                        # 에러 메시지 부분을 찾아서 제거
                        start_idx = content.find("We are having trouble retrieving the article content")
                        end_idx = content.find("Want all of The Times? Subscribe") + len("Want all of The Times? Subscribe")
                        
                        if start_idx >= 0 and end_idx > start_idx:
                            # 에러 메시지 부분 제거
                            content = content[:start_idx] + content[end_idx:].strip()
                else:
                    # 대안: p 태그 찾기
                    p_tags = soup.find_all('p')
                    if p_tags:
                        content = " ".join([p.text.strip() for p in p_tags])
                        
                        # 여기서도 에러 메시지 확인 및 제거
                        if ERROR_MESSAGE in content:
                            content = content.replace(ERROR_MESSAGE, "").strip()
                        
                        # 부분적으로 포함된 에러 메시지 처리
                        if "We are having trouble retrieving the article content" in content and "Want all of The Times? Subscribe" in content:
                            start_idx = content.find("We are having trouble retrieving the article content")
                            end_idx = content.find("Want all of The Times? Subscribe") + len("Want all of The Times? Subscribe")
                            
                            if start_idx >= 0 and end_idx > start_idx:
                                content = content[:start_idx] + content[end_idx:].strip()
                    else:
                        content = "본문 없음"

                # 본문이 없거나 길이가 너무 짧으면 스킵
                if content == "본문 없음" or not content or len(content.strip()) < 100:
                    print(f"[예외] 본문이 없거나 너무 짧아 기사를 건너뜁니다: {url}")
                    failed_count += 1
                    continue

                # 이미지 URL 추출
                image_url = extract_image_url(soup)

                articles.append({
                    "category": category,
                    "content": content,
                    "date": formatted_date,
                    "image_url": image_url,
                    "media_company": media_company,
                    "title": title,
                    "url": url
                })
            else:
                print(f"[예외] 기사 요청 실패: {url} (상태 코드 {response.status_code})")
                failed_count += 1
        except Exception as e:
            print(f"[예외] 기사 스크래핑 중 오류 발생: {url} - {str(e)}")
            failed_count += 1

    print(f"NYT: 총 {len(articles)}개 기사 스크래핑 성공, {failed_count}개 실패")
    return articles

def nyt_start(page_count=1):
    """
    NYT 기사 스크래핑을 시작하는 함수. 
    지정된 페이지 수만큼 스크래핑을 시도합니다.
    
    Args:
        page_count (int): 스크래핑할 페이지 수
    
    Returns:
        list: 스크래핑된 기사 리스트
    """
    all_urls = []
    all_articles = []
    
    print(f"NYT 기사 스크래핑 시작 (총 {page_count}페이지)")
    
    # 페이지별로 URL 수집
    for page in range(1, page_count + 1):
        urls = nyt_url_scraper(page)
        all_urls.extend(urls)
        # 페이지 간 요청 간격 (NYT 차단 방지)
        time.sleep(2)
    
    # 중복 URL 제거
    unique_urls = list(set(all_urls))
    print(f"NYT: 중복 제거 후 {len(unique_urls)}개 URL 확인")
    
    # 기사 내용 스크래핑
    articles = nyt_article_scraper(unique_urls)
    all_articles.extend(articles)
    
    # CSV 파일 저장
    if all_articles:
        csv_path = "../../data/raw/nyt_article.csv"
        save_to_csv(all_articles, csv_path)
        print(f"NYT: CSV 파일 저장 완료 ({csv_path})")
    
    return all_articles

if __name__ == "__main__":
    # 기존 코드를 start 함수 호출로 대체
    articles = nyt_start(page_count=1)
