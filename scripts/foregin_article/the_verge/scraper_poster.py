import requests
from bs4 import BeautifulSoup
import scripts.foregin_article.utils as utils
from datetime import datetime

def poster_extract_image(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")

        # 2. 그게 아니라면 이미지인지 확인
        section = soup.select_one("div.wn1wvoc")
        if section:
            return image_url_scraper(section)

        return ""  # 어떤 콘텐츠도 없을 경우

    except Exception as e:
        print(f"[ERROR] 콘텐츠 추출 중 오류 발생: {e}")
        return ""

def image_url_scraper(section):
    img = section.select_one("a.kqz8fh1")
    return img["href"] if img and img.has_attr("href") else ""


def poster_detail_scraper(url: str, category: str):
    """
    주어진 기사 URL에서 상세 정보를 수집합니다.
    수집 항목: title, date, content, image, category
    
    Args:
        url (str): 스크래핑할 기사 URL
        category (str): 기사의 카테고리 (예: 'TECH', 'AI', 'SCIENCE')
    """
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    try:
        res = requests.get(url, headers=headers)
        if res.status_code != 200:
            print(f"요청 실패: {res.status_code}")
            return None

        soup = BeautifulSoup(res.text, "html.parser")

        # 날짜 추출
        time_tag = soup.select_one("div.yrikct0 time")
        date = time_tag["datetime"] if time_tag and time_tag.has_attr("datetime") else ""
        
        # 날짜가 비어있는 경우 현재 날짜 사용
        formatted_date = ""
        if date:
            try:
                formatted_date = utils.format_date(date)
            except Exception:
                formatted_date = datetime.now().strftime("%Y-%m-%d")
        else:
            formatted_date = datetime.now().strftime("%Y-%m-%d")

        # 이미지 추출
        img = poster_extract_image(url) or ""

        # 제목 추출
        title_tag = soup.select_one("div._1t4tcr94")
        title = title_tag.get_text(strip=True) if title_tag else ""

        # 본문 추출 (여러 개의 문단이 있을 수 있음)
        content_blocks = soup.select("div.wn1wvof.wn1wvo0, div.wn1wvof")  # 두 클래스 모두 고려
        content = ""

        for block in content_blocks:
            for p in block.find_all("p"):
                # 모든 링크는 텍스트만 추출
                for a in p.find_all("a"):
                    a.replace_with(a.get_text())
                content += p.get_text(separator=" ", strip=True) + " "

        return {
            'category': category,
            'content': content,
            'date': formatted_date,
            'image_url': img,
            'title': title,
            'url': url,
        }

    except Exception as e:
        print(f"예외 발생: {e}")
        return None

if __name__ == "__main__":
    url = "https://www.theverge.com/tech/658857/android-16-beta-quick-settings-tiles-ui"
    print(poster_detail_scraper(url, category="TECH"))
