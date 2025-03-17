import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime, timedelta
import time

# 모든 카테고리의 URL 목록
CATEGORY_URLS = {
    "모바일": "https://news.naver.com/breakingnews/section/105/731",
    "인터넷/SNS": "https://news.naver.com/breakingnews/section/105/226",
    "통신/뉴미디어": "https://news.naver.com/breakingnews/section/105/227",
    "IT 일반": "https://news.naver.com/breakingnews/section/105/230",
    "보안/해킹": "https://news.naver.com/breakingnews/section/105/732",
    "컴퓨터": "https://news.naver.com/breakingnews/section/105/283",
    "과학/일반": "https://news.naver.com/breakingnews/section/105/228",
}

# Selenium 설정
chrome_options = Options()
chrome_options.add_argument("--headless")  # 브라우저 창을 띄우지 않음
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--blink-settings=imagesEnabled=false")

service = Service(executable_path='../../lib/chromedriver-win64/chromedriver.exe')
driver = webdriver.Chrome(service=service, options=chrome_options)


def click_more_articles():
    """기사 더보기 버튼을 클릭하여 추가 기사 로딩"""
    while True:
        try:
            more_button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CLASS_NAME, "section_more"))
            )
            more_button.click()
            time.sleep(2)  # 기사 로딩 대기
        except:
            break  # 더 이상 "기사 더보기" 버튼이 없으면 종료


def scrape_articles_by_date(start_date, end_date):
    """모든 카테고리에서 시작 날짜부터 종료 날짜까지 크롤링"""
    all_data = []

    current_date = start_date
    while current_date <= end_date:
        date_str = current_date.strftime("%Y%m%d")  # "YYYYMMDD" 형식 변환
        print(f"{date_str} 날짜 크롤링 중...")

        for category_name, base_url in CATEGORY_URLS.items():
            url = f"{base_url}?date={date_str}"
            print(f"{category_name} 카테고리 크롤링 중...")

            driver.get(url)
            time.sleep(3)  # 초기 페이지 로드 대기

            # 기사 더보기 클릭
            click_more_articles()

            # 추가 기사들이 완전히 로드될 때까지 대기
            WebDriverWait(driver, 5).until(
                EC.presence_of_all_elements_located((By.CLASS_NAME, "section_article"))
            )
            time.sleep(3)  # 추가 기사들이 로드될 시간을 추가로 확보

            # **동적으로 로딩된 HTML을 가져와서 BeautifulSoup으로 파싱**
            soup = BeautifulSoup(driver.page_source, "html.parser")
            latest_section = soup.find("div", class_="section_latest_article _CONTENT_LIST _PERSIST_META")

            if not latest_section:
                print(f"{date_str} - {category_name} 기사 목록을 찾을 수 없습니다.")
                continue

            article_sections = latest_section.find_all("div", class_="section_article _TEMPLATE")

            if not article_sections:
                print(f"{date_str} - {category_name} 개별 기사 섹션을 찾을 수 없습니다.")
                continue

            print(f"{date_str} - {category_name} 기사 {len(article_sections) * 6}개 발견")

            for section in article_sections:
                links = [
                    a["href"]
                    for a in section.find_all("a", class_="sa_text_title", href=True)
                ]

                for article_url in links:
                    try:
                        driver.get(article_url)
                        time.sleep(2)  # 기사 페이지 로딩 대기
                        all_data.append({
                            "category": category_name,  # 카테고리 추가
                            "date": date_str,  # 기사 날짜 추가
                            "html": driver.page_source,
                            "url": article_url
                        })
                    except Exception as e:
                        print(f"{date_str} - {category_name} 기사 {article_url} 크롤링 실패. 오류: {e}")

        current_date += timedelta(days=1)  # 다음 날짜로 이동

    driver.quit()
    print("모든 날짜와 카테고리의 크롤링 완료")
    return all_data
