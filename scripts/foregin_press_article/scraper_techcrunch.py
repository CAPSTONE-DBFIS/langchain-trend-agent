import requests
import re
import time
from bs4 import BeautifulSoup
from utils import format_date, save_to_csv


def extract_date_from_url(url):
    parts = url.split("/")
    try:
        year, month, day = parts[3], int(parts[4]), int(parts[5])
        date_str = f"{year}-{month:02d}-{day:02d}"
        return date_str
    except Exception as e:
        print(f"날짜 추출 오류 ({url}): {e}")
        return "날짜를 찾을 수 없음"


def techcrunch_url_scraper():
    base_url = "https://techcrunch.com/latest/"
    headers = {"User-Agent": "Mozilla/5.0"}
    links = []
    for page in range(1, 2):
        url = base_url if page == 1 else f"{base_url}page/{page}/"
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            print(f"페이지 {page} 요청 실패: {response.status_code}")
            continue
        soup = BeautifulSoup(response.content, 'html.parser')
        for a_tag in soup.find_all('a', href=True):
            link = a_tag['href']
            if re.match(r"^https://techcrunch\.com/\d{4}/", link):
                links.append(link)
        time.sleep(2)
    # 중복 제거
    unique_links = []
    seen = set()
    for link in links:
        if link not in seen:
            unique_links.append(link)
            seen.add(link)
    return unique_links


def clean_html_text(soup):
    for tag in soup(['script', 'style', 'aside', 'form']):
        tag.decompose()
    paragraphs = soup.find_all("p")
    cleaned_text = " ".join(p.get_text(separator=" ", strip=True) for p in paragraphs)
    return re.sub(r'\s+', ' ', cleaned_text)[:5000]


def techcrunch_article_scraper(urls):
    headers = {"User-Agent": "Mozilla/5.0"}
    articles = []
    media_company = "TechCrunch"
    for url in urls:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            print(f"기사 요청 실패: {url}")
            continue
        soup = BeautifulSoup(response.content, 'html.parser')
        title_tag = soup.select_one("h1.article-hero__title.wp-block-post-title")
        title = title_tag.get_text(strip=True) if title_tag else "제목을 찾을 수 없음"
        date_str = extract_date_from_url(url)
        formatted_date = format_date(date_str, input_format="%Y-%m-%d")
        desc_div = soup.select_one(
            "div.entry-content.wp-block-post-content.is-layout-constrained.wp-block-post-content-is-layout-constrained")
        content = clean_html_text(desc_div) if desc_div else "본문을 찾을 수 없음"
        articles.append({
            "media_company": media_company,
            "date": formatted_date,
            "title": title,
            "content": content,
            "url": url
        })
    return articles


if __name__ == "__main__":
    urls = techcrunch_url_scraper()
    articles = techcrunch_article_scraper(urls)
    csv_path = "../../data/raw/techcrunch_article.csv"
    save_to_csv(articles, csv_path)
