import concurrent.futures
import time
from datetime import datetime
from bs4 import BeautifulSoup
from selenium import webdriver

def init_driver():
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument("--blink-settings=imagesEnabled=false")
    driver = webdriver.Chrome(options=options)
    return driver

def parse_data(url):
    """URL을 받아서 기사 내용을 파싱"""
    driver = init_driver()

    try:
        driver.get(url)
        time.sleep(2)

        # BeautifulSoup으로 페이지 HTML 파싱
        soup = BeautifulSoup(driver.page_source, 'html.parser')

        # 카테고리 추출
        category_tag = soup.find('em', class_='media_end_categorize_item')
        category = category_tag.get_text(strip=True) if category_tag else "No category found"

        # 언론사 이름 추출
        media_logo_tag = soup.find('a', class_="media_end_head_top_logo")
        media_name = media_logo_tag.img['title'] if media_logo_tag and media_logo_tag.img and 'title' in media_logo_tag.img.attrs else "No media found"

        # 기사 제목 추출
        title_tag = soup.find('h2', class_='media_end_head_headline')
        title = title_tag.get_text(strip=True) if title_tag else "No title found"

        # 게시일자 추출
        date_tag = soup.find('span', class_='media_end_head_info_datestamp_time')
        raw_date = date_tag.get_text(strip=True) if date_tag else None
        date = datetime.strptime(raw_date.split()[0].replace(".", "-").strip("-"), "%Y-%m-%d").strftime(
            "%Y-%m-%d") if raw_date else "No date found"

        # 기사 내용 추출
        content_tag = soup.find('div', id='newsct_article')
        content = content_tag.get_text(strip=True) if content_tag else "No content found"

        article_data = {
            "category": category,
            "media_company": media_name,
            "title": title,
            "date": date,
            "content": content,
            "url": url
        }

    finally:
        driver.quit()  # 사용 후 드라이버를 종료

    return article_data

def parse_articles_in_parallel(article_urls, max_workers):
    """병렬로 기사 내용을 파싱하는 함수"""
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(parse_data, article_urls))
    print("모든 URL 파싱 완료")
    return results