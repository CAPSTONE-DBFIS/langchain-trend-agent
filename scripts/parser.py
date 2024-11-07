from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import requests

# 웹드라이버 재사용을 위한 전역 드라이버 변수
driver = None


def init_driver():
    global driver
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")

    # 크롬 드라이버 초기화
    service = Service(executable_path='../lib/chromedriver-win64/chromedriver.exe')
    driver = webdriver.Chrome(service=service, options=chrome_options)


def close_driver():
    global driver
    if driver:
        driver.quit()
        driver = None


def selenium_scrape(url):
    global driver
    if not driver:
        init_driver()  # 드라이버가 없으면 초기화

    # URL 접속
    driver.get(url)

    try:
        # 원본 URL
        base_url = driver.execute_script("return window.location.href;")
        # img 태그와 src 속성 추출
        img_element = driver.find_element(By.ID, "img1")
        img_url = img_element.get_attribute("src")
        # 댓글 개수 가져오기
        comment_element = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "u_cbox_count"))
        )
        comment_count = comment_element.text.strip() if comment_element.text else "No comment found"
    except: # 예외 처리
        base_url = url
        img_url = "No image"
        comment_count = "No comment found"

    return img_url, base_url, comment_count


def parse_data(raw_html, url):
    soup = BeautifulSoup(raw_html, 'html.parser')

    # 카테고리 추출
    category_tag = soup.find('em', class_='media_end_categorize_item')
    category = category_tag.get_text(strip=True) if category_tag else "No category found"

    # 언론사 이름 추출
    media_name = soup.find('img')['alt']

    # 기사 제목 추출
    title_tag = soup.find('h2', class_='media_end_head_headline')
    title = title_tag.get_text(strip=True) if title_tag else "No title found"

    # 게시일자 추출
    date_tag = soup.find('span', class_='media_end_head_info_datestamp_time')
    date = date_tag.get_text(strip=True) if date_tag else "No date found"

    # 기사 내용 추출
    content_tag = soup.find('div', id='newsct_article')
    content = content_tag.get_text(strip=True) if content_tag else "No content found"

    # 이미지 URL과 원본 URL 가져오기
    image, base_url, comment_count = selenium_scrape(url)

    # 결과 데이터
    article_data = {
        "category": category,
        "media_company": media_name,
        "title": title,
        "date": date,
        "content": content,
        "comment_count": comment_count,
        "image": image,
        "url": base_url
    }
    return article_data
