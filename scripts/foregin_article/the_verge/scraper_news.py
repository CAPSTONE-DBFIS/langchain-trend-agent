import requests
from bs4 import BeautifulSoup
import scripts.foregin_article.utils as utils
from datetime import datetime

def news_extract_image(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(url, headers=headers)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")

    # 이미지가 들어있는 컨테이너 선택
    section = soup.select_one("div._1b9pgly1._1b9pgly2")
    if not section:
        return ""

    img = section.find("img")
    if not img:
        return ""

    # src에서 이미지 url을 찾는다.
    if img.has_attr("src"):
        return img["src"]

    # 없다면 srcset에서 가장 첫번째 것을 가져온다.
    if img.has_attr("srcset"):
        # "url1 200w, url2 400w, …" 꼴이므로
        first = img["srcset"].split(",")[0].strip()
        return first.split()[0]

    return ""

def image_url_scraper(section):
    img = section.select_one("div._1ymtmqpn _1ymtmqpw")
    print(img)
    return img["src"] if img and img.has_attr("src") else ""

def news_detail_scraper(url: str, category: str):
    """
    주어진 기사 URL에서 상세 정보를 수집합니다.
    수집 항목: title, date, content, image, category
    
    Args:
        url (str): 스크래핑할 기사 URL
        category (str): 기사의 카테고리 (예: 'TECH', 'AI', 'SCIENCE')
    """
    response = requests.get(url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')

    # Title (._1p1nf4x0 내부의 h1._8enl991 ... 클래스)
    title_tag = soup.select_one('._1p1nf4x0 h1._8enl991._8enl990._8enl996._1xwticta._1xwtict9')
    title = title_tag.get_text(strip=True) if title_tag else ""

    # Date (duet--article--timestamp ... 내부의 <time>)
    time_tag = soup.select_one('.duet--article--timestamp.tvl9dp3.tvl9dp1.tvl9dp0._1xwtict5._1xwticta time')
    if time_tag and time_tag.has_attr('datetime'):
        date = time_tag['datetime']
    else:
        date = time_tag.get_text(strip=True) if time_tag else ""
    
    # 날짜가 비어있거나 None인 경우 현재 날짜 사용
    formatted_date = ""
    if date:
        formatted_date = utils.format_date(date)
    else:
        formatted_date = datetime.now().strftime("%Y-%m-%d")

    # Content (_1ymtmqpz 내부의 자식 컨테이너 텍스트)
    content_div = soup.select_one('._1ymtmqpz')
    content = ''
    if content_div:
        paragraphs = []
        # 직접적인 자식 요소만 순회하여 텍스트 추출
        for elem in content_div.find_all(recursive=False):
            text = elem.get_text(separator=' ', strip=True)
            if text:
                paragraphs.append(text)
        content = '\n\n'.join(paragraphs)

    # Image 수집
    image = news_extract_image(url)

    return {
        'category': category,
        'content': content,
        'date': formatted_date,
        'image_url': image,
        'title': title,
        'url': url,
    }

if __name__ == "__main__":
    url = "https://www.theverge.com/news/659301/apple-executive-lied-under-oath-epic-alex-roman"
    print(news_detail_scraper(url, "TECH"))