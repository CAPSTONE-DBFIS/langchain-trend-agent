import requests
from bs4 import BeautifulSoup
from utils import format_date, save_to_csv
import time

media_company = "ARS_Technica"


def extract_article_details(url, headers, category):
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        return None

    soup = BeautifulSoup(response.content, 'html.parser')
    title_tag = soup.find("h1", class_="dusk:text-gray-100 mb-3 px-[15px] font-serif text-3xl font-semibold leading-none text-gray-700 dark:text-gray-100 sm:px-5 md:px-0 md:text-4xl lg:text-5xl")
    title = title_tag.get_text(strip=True) if title_tag else "제목 없음"

    time_tag = soup.find("time")
    date_str = time_tag.get("datetime") if (time_tag and time_tag.has_attr("datetime")) else (time_tag.get_text(strip=True) if time_tag else "날짜 정보 없음")
    formatted_date = format_date(date_str)

    # 개선된 본문 추출 방법
    content_div = soup.find("div", class_="post-content post-content-double")
    content = ""
    
    if content_div:
        # 모든 <p> 태그를 찾아서 텍스트를 순서대로 결합
        paragraphs = content_div.find_all("p")
        if paragraphs:
            content = " ".join([p.get_text(strip=True) for p in paragraphs])
        
        # <p> 태그가 없거나 결과가 비어있는 경우 대체 방법으로 모든 텍스트 추출
        if not content.strip():
            content = content_div.get_text(separator=" ", strip=True)
    
    if not content.strip():
        content = "본문 없음"

    # 이미지 URL 추출 시도
    image_url = extract_image_url(soup)

    return {
        "category": category,
        "content": content,
        "date": formatted_date,
        "image_url": image_url,
        "media_company": media_company,
        "title": title,
        "url": url
    }


def extract_image_url(soup):
    """기사에서 이미지 URL 추출 시도 (다양한 HTML 구조 대응)"""
    try:
        # 방법 1: 메인 기사 이미지 (figure.intro-image)
        figure = soup.find("figure", class_="intro-image")
        if figure:
            img = figure.find("img", src=True)
            if img:
                return img["src"]
        
        # 방법 2: 메인 아티클 이미지 (article-image 관련 클래스)
        img = soup.find("img", class_="article-image")
        if img and img.has_attr("src"):
            return img["src"]
            
        # 방법 3: wp-post-image 클래스를 가진 이미지 (제공된 HTML 예시)
        img = soup.find("img", class_="wp-post-image")
        if img and img.has_attr("src"):
            # srcset이 있는 경우 가장 큰 이미지 URL 추출 시도
            if img.has_attr("srcset"):
                srcset = img["srcset"]
                # srcset 형식: "url1 size1w, url2 size2w, ..."
                parts = srcset.split(",")
                largest_img = ""
                largest_size = 0
                
                for part in parts:
                    part = part.strip()
                    if not part:
                        continue
                    img_parts = part.split()
                    if len(img_parts) >= 2:
                        img_url = img_parts[0]
                        # 크기 표시에서 'w' 제거하고 정수로 변환
                        try:
                            size = int(img_parts[1].replace("w", ""))
                            if size > largest_size:
                                largest_size = size
                                largest_img = img_url
                        except ValueError:
                            continue
                
                if largest_img:
                    return largest_img
            
            # srcset이 없거나 처리에 실패한 경우 기본 src 사용
            return img["src"]
            
        # 방법 4: 일반적인 기사 내 첫 번째 이미지
        img = soup.find("img", src=True)
        if img:
            return img["src"]
            
    except Exception as e:
        print(f"[예외] 이미지 URL 추출 오류: {str(e)}")
    
    return ""  # 이미지를 찾지 못한 경우 빈 문자열 반환


def get_category_from_url(section_url):
    """URL에서 카테고리 추출"""
    if "gadgets" in section_url:
        return "TECH"
    elif "security" in section_url:
        return "SECURITY"
    elif "information-technology" in section_url:
        return "INFORMATION-TECHNOLOGY"
    else:
        return "IT"  # 기본 카테고리


def scrape_arstechnica_section(section_url):
    """
    지정된 Ars Technica 섹션 URL에서 첫 페이지의 기사를 스크래핑합니다.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/98.0.4758.102 Safari/537.36"
        )
    }

    # URL에서 카테고리 결정
    category = get_category_from_url(section_url)
    articles_data = []
    failed_count = 0

    response = requests.get(section_url, headers=headers)
    if response.status_code != 200:
        print(f"[예외] 페이지를 가져오는데 실패했습니다: {section_url} (상태 코드: {response.status_code})")
        return articles_data, failed_count

    soup = BeautifulSoup(response.content, "html.parser")
    # id 속성이 있는 <article> 태그 찾기
    articles = soup.find_all("article", id=True)
    if not articles:
        print(f"[예외] id 속성이 있는 <article> 태그를 찾지 못했습니다: {section_url}")
        return articles_data, failed_count

    for article in articles:
        article_id = article.get("id")
        # 각 article 내부에서 a 태그의 href(기사 링크) 추출
        a_tag = article.find("a", href=True)
        if not a_tag:
            failed_count += 1
            continue
        article_link = a_tag["href"]

        # 상세 페이지에서 title, date, 본문(desc) 추출
        details = extract_article_details(article_link, headers, category)
        if details:
            # 유효성 검사: 제목, 본문, 이미지 URL이 모두 있어야 함
            if details["title"] == "제목 없음" or details["content"] == "본문 없음":
                failed_count += 1
                continue
                
            # 이미지 URL이 없는 경우도 제외
            if not details["image_url"]:
                failed_count += 1
                continue
                
            articles_data.append(details)
        else:
            failed_count += 1
            continue

    return articles_data, failed_count


def ars_technica_start(page_count=1):
    """
    Ars Technica 기사 스크래핑을 시작하는 함수.
    지정된 페이지 수를 고려하여 각 섹션에서 스크래핑을 시도합니다.
    
    Args:
        page_count (int): 고려할 페이지 수 (각 섹션별로 적용)
    
    Returns:
        list: 스크래핑된 기사 리스트
    """
    print(f"Ars Technica 기사 스크래핑 시작 (각 섹션당 최대 {page_count}페이지)")
    
    # 스크래핑할 섹션 URL 목록
    section_urls = [
        "https://arstechnica.com/gadgets/",
        "https://arstechnica.com/security/",
        "https://arstechnica.com/information-technology/"
    ]
    
    all_articles_data = []
    total_failed = 0
    
    # 각 섹션별로 지정된 페이지만큼 스크래핑
    for section_index, section_url in enumerate(section_urls):
        print(f"Ars Technica: 섹션 {section_index+1}/{len(section_urls)} 스크래핑 시작")
        
        # 기본 섹션 URL (1페이지)
        section_articles, failed = scrape_arstechnica_section(section_url)
        all_articles_data.extend(section_articles)
        total_failed += failed
        
        # 추가 페이지 스크래핑 (page_count가 1보다 큰 경우)
        for page in range(2, page_count + 1):
            page_url = f"{section_url}/page/{page}/"
            page_articles, page_failed = scrape_arstechnica_section(page_url)
            all_articles_data.extend(page_articles)
            total_failed += page_failed
            # 페이지 간 지연 시간 추가
            time.sleep(2)
        
        print(f"Ars Technica: 섹션 {section_index+1} 스크래핑 완료, {len(section_articles)}개 기사 추출")
    
    print(f"Ars Technica: 총 {len(all_articles_data)}개 기사 스크래핑 성공, {total_failed}개 실패")
    
    # CSV 파일 저장
    if all_articles_data:
        csv_file_path = "../../data/raw/ars_technica_article.csv"
        save_to_csv(all_articles_data, csv_file_path)
        print(f"Ars Technica: CSV 파일 저장 완료 ({csv_file_path})")
    
    return all_articles_data


if __name__ == "__main__":
    # 기존 코드를 start 함수 호출로 대체
    articles = ars_technica_start(page_count=1)
