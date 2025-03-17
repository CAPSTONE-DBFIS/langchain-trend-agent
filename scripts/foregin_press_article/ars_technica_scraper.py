import requests
from bs4 import BeautifulSoup
from dateutil import parser  # pip install python-dateutil
import csv
import os


def extract_article_details(url, headers):
    """
    주어진 기사 URL에서 title, date, 본문(desc)을 추출합니다.
    - title: 지정된 h1 태그의 텍스트
    - date: <time> 태그의 날짜 정보를 YYYY-MM-DD 형식으로 변환
    - desc: 본문으로, div class="post-content post-content-double" 내부의 텍스트
    """
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"[상세 페이지] {url} 를 가져오는데 실패했습니다. (상태 코드: {response.status_code})")
        return None

    soup = BeautifulSoup(response.content, 'html.parser')

    # 1. title 추출
    title_tag = soup.find(
        "h1",
        class_="dusk:text-gray-100 mb-3 px-[15px] font-serif text-3xl font-semibold leading-none text-gray-700 dark:text-gray-100 sm:px-5 md:px-0 md:text-4xl lg:text-5xl"
    )
    title = title_tag.get_text(strip=True) if title_tag else "제목 없음"

    # 2. date 추출 (예시: <time> 태그 사용)
    time_tag = soup.find("time")
    if time_tag:
        date_str = time_tag.get("datetime") if time_tag.has_attr("datetime") else time_tag.get_text(strip=True)
    else:
        date_str = "날짜 정보 없음"

    # 날짜 파싱 및 "YYYY-MM-DD" 형식으로 변환
    try:
        parsed_date = parser.parse(date_str)
        formatted_date = parsed_date.strftime("%Y.%m.%d")
    except Exception:
        formatted_date = date_str

    # 3. 본문(desc) 추출: div class="post-content post-content-double" 영역의 텍스트
    content_div = soup.find("div", class_="post-content post-content-double")
    if content_div:
        desc = content_div.get_text(separator="\n", strip=True)
    else:
        desc = "본문 없음"

    return {
        "url": url,
        "title": title,
        "date": formatted_date,
        "desc": desc
    }


def scrape_arstechnica_gadgets(num_pages=5):
    """
    https://arstechnica.com/gadgets/ 및 후속 페이지들을 순회하면서
    각 기사의 URL과 article id를 수집한 후, 해당 링크에서 상세 데이터를 추출합니다.
    """
    base_url = "https://arstechnica.com/gadgets/"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/98.0.4758.102 Safari/537.36"
        )
    }

    all_articles_data = []

    for page in range(1, num_pages + 1):
        # 첫 페이지는 기본 URL, 이후 페이지는 /page/{번호}/ 형식
        if page == 1:
            url = base_url
        else:
            url = f"{base_url}page/{page}/"

        print(f"\n[페이지 {page} 스크래핑] - URL: {url}")
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            print(f"페이지를 가져오는데 실패했습니다. (상태 코드: {response.status_code})")
            continue

        soup = BeautifulSoup(response.content, "html.parser")
        # id 속성이 있는 <article> 태그 찾기
        articles = soup.find_all("article", id=True)
        if not articles:
            print("id 속성이 있는 <article> 태그를 찾지 못했습니다.")
            continue

        for article in articles:
            article_id = article.get("id")
            # 각 article 내부에서 a 태그의 href(기사 링크) 추출
            a_tag = article.find("a", href=True)
            if not a_tag:
                print(f"[{article_id}] 링크를 찾지 못했습니다.")
                continue
            article_link = a_tag["href"]
            print(f"\n>> [기사 스크래핑] Article ID: {article_id}, URL: {article_link}")

            # 상세 페이지에서 title, date, 본문(desc) 추출
            details = extract_article_details(article_link, headers)
            if details:
                # 만약 title이나 desc가 올바른 형식이 아니라면(예: "제목 없음", "본문 없음") 해당 데이터를 제외합니다.
                if details["title"] == "제목 없음" or details["desc"] == "본문 없음":
                    print(f"[{article_id}] 유효하지 않은 title 또는 desc로 인해 해당 데이터를 제외합니다.")
                    continue
                all_articles_data.append(details)
                print("     Title :", details["title"])
                print("     Date  :", details["date"])
                preview = details["desc"][:100] + "..." if len(details["desc"]) > 100 else details["desc"]
                print("     Desc  :", preview)
            else:
                print(f"[{article_id}] 상세 데이터를 가져오지 못했습니다.")

    return all_articles_data


def save_articles_to_csv(articles, file_path):
    """
    수집한 기사 데이터를 CSV 파일로 저장합니다.
    CSV 파일은 url, title, date, desc 형식이며, desc에는 본문 내용이 들어갑니다.
    인코딩은 'utf-8-sig'로 저장합니다.
    """
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    fieldnames = ["url", "title", "date", "desc"]

    with open(file_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for article in articles:
            writer.writerow({
                "url": article["url"],
                "title": article["title"],
                "date": article["date"],
                "desc": article["desc"]
            })
    print(f"\nCSV 파일이 저장되었습니다: {file_path}")


if __name__ == "__main__":
    # 예시로 5페이지까지 스크래핑 (필요에 따라 num_pages 값을 조절)
    articles_data = scrape_arstechnica_gadgets(num_pages=5)

    # 3단계: 수집한 데이터를 CSV 파일로 저장 (컬럼: url, title, date, desc)
    csv_file_path = "../../data/raw/ars_technica_article.csv"
    save_articles_to_csv(articles_data, csv_file_path)
