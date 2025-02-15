import requests
from bs4 import BeautifulSoup
import pandas as pd
import os


TOPIC_URLS = [
    "https://www.itworld.co.kr/cloud-computing/",
    "https://www.itworld.co.kr/generative-ai/",
    "https://www.itworld.co.kr/artificial-intelligence/",
    "https://www.itworld.co.kr/computers-and-peripherals/",
    "https://www.itworld.co.kr/data-center/",
    "https://www.itworld.co.kr/emerging-technology/",
    "https://www.itworld.co.kr/augmented-reality/",
    "https://www.itworld.co.kr/apple/",
    "https://www.itworld.co.kr/vendors-and-providers/",
    "https://www.itworld.co.kr/software-development/",
    "https://www.itworld.co.kr/security/",
    "https://www.itworld.co.kr/collaboration-software/",
    "https://www.itworld.co.kr/productivity-software/",
    "https://www.itworld.co.kr/windows/",
    "https://www.itworld.co.kr/android/",
    "https://www.itworld.co.kr/networking/",
    "https://www.itworld.co.kr/mobile/",
    "https://www.itworld.co.kr/it-management/",
    "https://www.itworld.co.kr/it-leadership/",
    "https://www.itworld.co.kr/enterprise-applications/"
    ]

def itworld_scraper(topic_url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36"
    }
    links = []

    for page in range(1,4):
        url = f"{topic_url}/page/{page}/"
        response = requests.get(url, headers=headers)
        if response.status_code == 200 and page == 1:
            soup = BeautifulSoup(response.content, 'html.parser')
            list_items = soup.find_all('div', class_='content-listing-articles__row')
        elif response.status_code == 200 and page > 1:
            soup = BeautifulSoup(response.content, 'html.parser')
            list_items = soup.find_all('div', class_='content-listing-various__row')

        for item in list_items:
            a_tag = item.find('a', href=True)
            if a_tag:
                # 상대 경로를 절대 경로로 변환
                link = a_tag['href']
                if not link.startswith("http"):
                    link = "https://www.itworld.co.kr" + link
                links.append(link)
            else:
                print(f"페이지 {page} 요청 실패: 상태 코드 {response.status_code}")
    return links

def itworld_article_scraper(urls):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36"
    }

    articles = []

    for url in urls:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')

            title_tag = soup.find('h1', class_='article-hero__title')
            title = title_tag.text.strip() if title_tag else "제목 없음"

            div_tag = soup.find('div', class_ ='card')
            if div_tag:
                spans = div_tag.find_all('span')
                if len(spans) > 1:
                    time_tag = spans[1]
                    date = time_tag.text.strip()if time_tag else "날짜 없음"

            desc_tag = soup.find('h2', class_='content-subheadline')
            desc = desc_tag.text.strip() if desc_tag else "요약 없음"

            articles.append({
                "url": url,
                "title": title,
                "date": date,
                "desc": desc
            })
        else:
            print(f"기사 요청 실패: {url} (상태 코드 {response.status_code})")

    return articles

def save_to_csv(articles, filepath):
    # 데이터프레임 생성
    df = pd.DataFrame(articles)

    # 제목 없음 또는 요약 없음 데이터 필터링
    # filtered_df = df[(df['title'] != "제목 없음") & (df['desc'] != "요약 없음")]

    # 디렉토리 생성 (존재하지 않을 경우)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    # CSV 파일 저장
    df.to_csv(filepath, index=False, encoding='utf-8-sig')
    print(f"CSV 파일이 저장되었습니다: {filepath}")


if __name__ == "__main__":
    all_articles = []

    for topic_url in TOPIC_URLS:
        # URL에서 토픽명 추출
        topic_name = topic_url.split("/")[-2]
        print(f"크롤링 시작: {topic_name}")
        #1.기사 url 크롤링
        urls = itworld_scraper(topic_url)
        print(urls[0])
        #2. url의 기사 제목 날짜 요약 크롤링
        articles = itworld_article_scraper(urls)
        print(articles[0])
        #3.전체 리스트 추가
        all_articles.extend(articles)

    print(all_articles[:2])
    save_to_csv(all_articles, "../../data/raw/itworld_articles.csv")

