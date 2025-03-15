import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select
from bs4 import BeautifulSoup
import time
import pandas as pd
import os
import re

# 블라인드 IT 검색 페이지
URL = "https://www.teamblind.com/kr/search/IT"

# 웹드라이버 실행 (Chrome)
options = webdriver.ChromeOptions()
options.add_argument("--headless")  # 브라우저 창을 열지 않음
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36")

driver = webdriver.Chrome(options=options)
driver.get(URL)
time.sleep(3)  # 페이지 로딩 대기


def scroll_and_collect_links(driver, max_scroll=2):
    links = []  # 수집한 게시물 링크 저장
    seen_links = set()  # 이미 수집한 링크를 추적하여 중복 방지
    scroll_count = 0

    # 처음 페이지 로딩 후 드롭다운 선택
    soup = BeautifulSoup(driver.page_source, "html.parser")
    wrap_category = driver.find_element(By.CLASS_NAME, "wrap-category")
    sort_element = wrap_category.find_element(By.CLASS_NAME, "sort")

    # sort 요소 내에서 select 요소 찾기
    select_element = sort_element.find_element(By.TAG_NAME, "select")
    select = Select(select_element)
    select.select_by_value("id")  # value="id"인 최신순 옵션 선택

    # 선택 후 페이지가 갱신될 수 있도록 잠시 대기
    time.sleep(2)

    while scroll_count < max_scroll:
        soup = BeautifulSoup(driver.page_source, "html.parser")

        # 현재 페이지의 HTML에서 게시물 링크 수집
        list_items = soup.find_all("div", class_=["tit"])

        # 게시물 링크 수집, 이미 수집된 링크는 추가하지 않음
        for item in list_items:
            a_tag = item.find("a", href=True)
            if a_tag:
                link = a_tag["href"]
                if not link.startswith("http"):
                    link = "https://www.teamblind.com" + link

                if link not in seen_links:
                    links.append(link)  # 새로운 링크만 추가
                    seen_links.add(link)  # 수집된 링크로 추가

        # 스크롤 내리기
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.END)
        time.sleep(2)  # 데이터 로딩 대기
        scroll_count += 1

    return links

def blind_post_scraper(post_urls):
    all_posts = []

    for post_url in post_urls:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        response = requests.get(post_url, headers=headers)
        soup = BeautifulSoup(response.text, "html.parser")

        title_tag = soup.find("div", class_="article-view-head").find("h2")
        title_text = title_tag.text.strip()
        title = title_text.strip() if title_tag else "제목 없음"

        date_tag = soup.find("span", class_="date")
        date = date_tag.text.strip()

        # 게시물 내용 추출
        content_tag = soup.find("p", class_="contents-txt")

        # content_tag가 None이 아닌 경우에만 get_text()를 호출
        if content_tag:
            content_text = content_tag.get_text()  # get_text()를 사용하여 텍스트 추출
            content_text = remove_html_tags(content_text)  # HTML 태그 제거
            content = content_text.strip() if content_text else "내용 없음"
        else:
            content = "내용 없음"
        comments=[]
        comment_elements = soup.find_all("p", class_="cmt-txt")
        if comment_elements:
            for comment in comment_elements:
                comments.append(comment.text.strip())
        else:
            comments.append("댓글 없음")

        all_posts.append({
            "url": post_url,
            "title": title,
            "date": date,
            "content": content,
            "comments": comments
        })
    return all_posts

def save_to_csv(posts, filepath):
    # 데이터프레임 생성
    df = pd.DataFrame(posts)

    # 디렉토리 생성 (존재하지 않을 경우)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    # CSV 파일 저장
    try:
        df.to_csv(filepath, index=False, encoding='utf-8-sig')  # utf-8로 저장
        print(f"CSV 파일이 저장되었습니다: {filepath}")
    except Exception as e:
        print(f"파일 저장 중 오류 발생: {e}")

def remove_html_tags(text):
    """HTML 태그를 제거하는 함수"""
    # <br>을 줄바꿈 문자로 바꾸고, 나머지 HTML 태그 제거
    text = re.sub(r'<br\s*/?>', '\n', text)  # <br>을 줄바꿈 문자로 변환
    text = re.sub(r'</?[^>]+>', '', text)  # 나머지 HTML 태그 제거
    return text

if __name__ == "__main__":
    # 크롤링 실행
    urls = scroll_and_collect_links(driver, max_scroll=2)
    # 결과 출력
    print(f"총 {len(urls)}개의 게시물 링크를 수집했습니다.")
    for url in urls:
        print(url)
    all_post = blind_post_scraper(urls)
    save_to_csv(all_post, '../../data/raw/blind_posts.csv')
    # 브라우저 종료
    driver.quit()





