import concurrent.futures
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
from selenium import webdriver
from bs4 import BeautifulSoup
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

def init_driver():
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument("--blink-settings=imagesEnabled=false")

    # webdriver-manager 사용
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    return driver

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

def click_more_articles(driver):
    """기사 더보기 버튼을 클릭하여 모든 기사 목록을 로딩"""
    while True:
        try:
            more_button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CLASS_NAME, "section_more"))
            )
            more_button.click()
            time.sleep(2)
        except:
            break


def scrape_category_articles(category_name, target_date):
    """특정 카테고리에서 지정 날짜의 기사 URL 목록만 수집"""
    all_urls = []
    date_str = target_date.strftime("%Y%m%d")
    print(f"{date_str} - {category_name} 카테고리 URL 수집 시작")

    try:
        base_url = CATEGORY_URLS.get(category_name)
        if base_url is None:
            return []

        url = f"{base_url}?date={date_str}"
        driver = init_driver()
        driver.get(url)
        time.sleep(3)

        # 기사 더보기 버튼 클릭 로직 추가
        click_more_articles(driver)

        # BeautifulSoup으로 HTML 파싱
        soup = BeautifulSoup(driver.page_source, "html.parser")
        latest_section = soup.find("div", class_="section_latest_article _CONTENT_LIST _PERSIST_META")

        if not latest_section:
            print(f"{date_str} - {category_name} 기사 목록을 찾을 수 없습니다.")
            return []

        article_sections = latest_section.find_all("div", class_="section_article _TEMPLATE")

        for section in article_sections:
            links = [a["href"] for a in section.find_all("a", class_="sa_text_title", href=True)]
            all_urls.extend(links)

        if all_urls:
            print(f"카테고리: {category_name} URL 수집 완료, {len(all_urls)}개 수집")
        else:
            print(f"{category_name} URL 수집 실패")

    except Exception as e:
        print(f"에러 발생: {e}")
    finally:
        driver.quit()

    return all_urls


def scrape_all_categories_in_parallel(target_date, max_workers):
    """모든 카테고리에 대해 병렬로 URL 목록 수집"""
    all_results = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_category = {
            executor.submit(scrape_category_articles, category_name, target_date): category_name
            for category_name in CATEGORY_URLS.keys()
        }

        for future in concurrent.futures.as_completed(future_to_category):
            category = future_to_category[future]
            try:
                result = future.result()
                all_results[category] = result

            except Exception as e:
                print(f"{category} URL 수집 중 에러: {e}")
    print("모든 카테고리 URL 수집 완료")
    return all_results