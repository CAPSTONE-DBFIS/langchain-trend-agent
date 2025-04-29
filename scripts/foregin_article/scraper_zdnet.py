import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from utils import format_date, save_to_csv
import re
import time

# 기본 User-Agent 설정
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/115.0.0.0 Safari/537.36"
    )
}

media_company = "ZDNET"
category = "IT"  # 기본 카테고리 설정


def convert_relative_date(relative_str):
    """
    상대 날짜 문자열(예: "2 days ago", "1 week ago")를 오늘 날짜 기준의 절대 날짜("YYYY-MM-DD")로 변환합니다.
    """
    relative_str = relative_str.strip().lower()
    today = datetime.today()

    try:
        if "day" in relative_str:
            num = int(relative_str.split()[0])
            target_date = today - timedelta(days=num)
        elif "week" in relative_str:
            num = int(relative_str.split()[0])
            target_date = today - timedelta(weeks=num)
        elif "month" in relative_str:
            num = int(relative_str.split()[0])
            target_date = today - timedelta(days=num * 30)  # 대략 30일 기준
        elif "year" in relative_str:
            num = int(relative_str.split()[0])
            target_date = today - timedelta(days=num * 365)
        else:
            target_date = today
    except Exception as e:
        print(f"날짜 변환 오류 ({relative_str}): {e}")
        target_date = today

    return target_date.strftime("%Y-%m-%d")


def extract_image_url(container):
    """
    기사 컨테이너에서 이미지 주소를 찾습니다.
    
    container: c-listingDefault_item 클래스를 가진 div 요소
    return: 이미지 URL 문자열
    """
    try:
        # 그리드 컨테이너 찾기
        grid_container = container.find("div", class_="u-grid-columns")
        if not grid_container:
            print("그리드 컨테이너(u-grid-columns)를 찾을 수 없습니다.")
            return ""
            
        # c-listingDefault_itemImage 클래스를 가진 div 찾기
        img_div = grid_container.find("div", class_="c-listingDefault_itemImage")
        if not img_div:
            print("이미지 div(c-listingDefault_itemImage)를 찾을 수 없습니다.")
            return ""
            
        # 1. picture 태그 확인
        picture = img_div.find("picture")
        if picture:
            # 1.1. img 태그의 src 속성 확인 (일반적으로 기본 이미지)
            img = picture.find("img")
            if img:
                # print(f"Found img tag: {img}")
                if img.has_attr("src") and img["src"].strip():
                    return img["src"]
                # else:
                #     print("img 태그는 있지만 src 속성이 비어있습니다.")
                
            # 1.2. source 태그의 srcset 속성 확인 (이미지가 없거나 빈 문자열인 경우)
            sources = picture.find_all("source", srcset=True)
            # print(f"Found {len(sources)} source tags with srcset attribute")
            
            if sources:
                # 큰 화면용 이미지부터 확인 (일반적으로 마지막 source가 가장 해상도 높음)
                for source in reversed(sources):
                    print(f"Checking source: {source}")
                    if source.has_attr("srcset") and source["srcset"].strip():
                        srcset = source["srcset"].split()[0]
                        print(f"srcset 속성에서 URL 추출: {srcset}")
                        return srcset  # 첫 번째 URL만 가져옴
                    else:
                        print("source 태그는 있지만 srcset 속성이 비어있습니다.")
        else:
            print("picture 태그를 찾을 수 없습니다.")
        
        # picture 태그가 없는 경우 직접 img 태그 찾기
        img = img_div.find("img")
        if img:
            # print(f"Found direct img tag: {img}")
            if img.has_attr("src") and img["src"].strip():
                return img["src"]
            # else:
            #    print("직접 img 태그는 있지만 src 속성이 비어있습니다.")
            
    except Exception as e:
        print(f"이미지 URL 추출 오류: {str(e)}")
        import traceback
        traceback.print_exc()
        
    return ""  # 이미지를 찾지 못한 경우 빈 문자열 반환

def extract_category_from_article(article_url):
    """
    기사 URL에서 카테고리를 추출합니다.
    """
    try:
        # URL 경로에서 카테고리 추출 시도
        # 예: https://www.zdnet.com/article/category/innovation/article-title/
        # 또는 https://www.zdnet.com/innovation/article-title/
        
        path_parts = article_url.strip('/').split('/')
        
        # /article/category/innovation/ 형태 확인
        if 'article' in path_parts and len(path_parts) > path_parts.index('article') + 2:
            article_idx = path_parts.index('article')
            if path_parts[article_idx + 1] == 'category' and len(path_parts) > article_idx + 2:
                return path_parts[article_idx + 2].capitalize()
        
        # /innovation/ 형태 확인 (기사 URL 중간에 카테고리가 있는 경우)
        for idx, part in enumerate(path_parts):
            if part in ['innovation', 'technology', 'security', 'finance', 'business', 
                      'artificial-intelligence', 'cloud', 'mobility', 'hardware']:
                return part.replace('-', ' ').capitalize()
        
        # 기사 페이지에서 직접 카테고리 추출
        response = requests.get(article_url, headers=HEADERS)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            category_element = soup.find("span", class_="c-pageArticleSingle_topicHeading")
            if category_element:
                return category_element.get_text(strip=True)
    
    except Exception as e:
        print(f"기사 카테고리 추출 오류: {str(e)}")
    
    # 카테고리를 찾지 못한 경우 기본값 반환
    return "IT"

def scrape_articles_from_page(page):
    """
    지정한 페이지 번호에 따라 최신 기사 목록 HTML을 요청한 후,
    각 기사 컨테이너에서 URL, 제목, 날짜, 설명을 추출합니다.
    """
    if page == 1:
        url = "https://www.zdnet.com/latest/"
        headers = HEADERS.copy()
    else:
        url = f"https://www.zdnet.com/latest/{page}/"
        headers = HEADERS.copy()
        headers["X-Requested-With"] = "XMLHttpRequest"  # AJAX 요청임을 알림

    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"[예외] 페이지 {page} 요청 실패, 상태 코드: {response.status_code}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    
    # 최상위 컨테이너 찾기 (전체 리스팅 컨테이너)
    main_container = soup.find("div", class_="c-listingDefault")
    
    # 개별 기사 아이템 찾기
    if main_container:
        item_containers = main_container.find_all("div", class_="c-listingDefault_item")
    else:
        # 대안: 직접 기사 아이템 찾기
        item_containers = soup.find_all("div", class_="c-listingDefault_item")
    
    if not item_containers:
        # 추가 선택자 시도
        item_containers = soup.find_all("div", class_=lambda c: c and "item" in c.lower())
    
    articles = []
    failed_count = 0

    for container in item_containers:
        try:
            # 각 아이템 안에서 그리드 컨테이너 찾기
            grid_container = container.find("div", class_="u-grid-columns")
            
            # 그리드 컨테이너가 없으면 컨테이너 자체 사용
            target_container = grid_container if grid_container else container
            
            # 컨테이너에서 링크 찾기
            a_tag = target_container.find("a", class_="c-listingDefault_itemLink")
            if not a_tag:
                failed_count += 1
                continue
                
            href = a_tag.get("href")
            if not href.startswith("http"):
                if href.startswith("/"):
                    href = "https://www.zdnet.com" + href
                else:
                    href = "https://www.zdnet.com/" + href

            # 제목 추출 (그리드 컨테이너 내 c-listingDefault_itemContent 내부)
            content_div = target_container.find("div", class_="c-listingDefault_itemContent")
            if not content_div:
                failed_count += 1
                continue
                
            title_tag = content_div.find("h3", class_="c-listingDefault_title")
            if not title_tag:
                failed_count += 1
                continue
                
            title = title_tag.get_text(strip=True)
            if not title:
                failed_count += 1
                continue

            # 설명 추출
            content_tag = content_div.find("span", class_="c-listingDefault_description")
            if not content_tag:
                content = "본문 내용 없음"
            else:
                content = content_tag.get_text(strip=True)
                
            # 기사 페이지에서 전체 본문 가져오기
            try:
                article_content = extract_article_content(href)
                if article_content:
                    content = article_content
            except Exception as e:
                print(f"[예외] 기사 본문 추출 오류: {href} - {str(e)}")
                # 원래 추출한 짧은 설명으로 계속 진행

            # 날짜 추출
            meta_div = content_div.find("div", class_="c-listingDefault_meta")
            if meta_div:
                date_tag = meta_div.find("span", class_="c-listingDefault_pubDate")
                if date_tag:
                    relative_date = date_tag.get_text(strip=True)
                    date_str = convert_relative_date(relative_date)
                    formatted_date = format_date(date_str, input_format="%Y-%m-%d")
                else:
                    formatted_date = format_date(datetime.today().strftime("%Y-%m-%d"), input_format="%Y-%m-%d")
            else:
                formatted_date = format_date(datetime.today().strftime("%Y-%m-%d"), input_format="%Y-%m-%d")
            
            # 이미지 URL 추출
            image_url = extract_image_url(container)
            
            # 이미지가 없는 경우 알림만 출력 (스킵하지 않음)
            if not image_url:
                image_url = ""  # 빈 문자열로 설정
            else:
                # 이미지 URL이 상대 경로인 경우 처리
                if not image_url.startswith(("http://", "https://")):
                    if image_url.startswith("//"):
                        image_url = "https:" + image_url
                    else:
                        image_url = "https://www.zdnet.com" + image_url
                
                # 더 큰 해상도로 URL 변환 (width=800, height=600)
                if "resize" in image_url and "width=" in image_url and "height=" in image_url:
                    try:
                        # 더 큰 해상도로 URL 파라미터 변경
                        image_url = re.sub(r'width=\d+', 'width=800', image_url)
                        image_url = re.sub(r'height=\d+', 'height=600', image_url)
                    except Exception as e:
                        print(f"[예외] 이미지 URL 리사이징 오류: {str(e)}")
            
            # 기사 URL에서 카테고리 추출
            article_category = extract_category_from_article(href)
            
            # 기사 정보 저장
            article_data = {
                "category": article_category,
                "content": content,
                "date": formatted_date,
                "image_url": image_url,
                "media_company": media_company,
                "title": title,
                "url": href
            }
            
            articles.append(article_data)
            
        except Exception as e:
            print(f"[예외] 기사 파싱 중 오류: {href if 'href' in locals() else 'unknown URL'} - {str(e)}")
            failed_count += 1
            continue
    
    print(f"ZDNET: 페이지 {page}에서 {len(articles)}개 기사 수집 완료, {failed_count}개 실패")
    return articles


def zdnet_start(page_count=1):
    """
    ZDNET 기사 스크래핑을 시작하는 함수.
    지정된 페이지 수만큼 스크래핑을 시도합니다.
    
    Args:
        page_count (int): 스크래핑할 페이지 수
    
    Returns:
        list: 스크래핑된 기사 리스트
    """
    print(f"ZDNET 기사 스크래핑 시작 (총 {page_count}페이지)")
    
    all_articles = []
    total_failed = 0
    
    # 페이지별로 스크래핑
    for page in range(1, page_count + 1):
        page_articles = scrape_articles_from_page(page)
        
        # 기사 내용 추출
        articles_with_content = []
        page_failed = 0
        for article in page_articles:
            # 제목 검증
            if not article.get('title') or article.get('title') == "제목 없음":
                print(f"[예외] 제목이 없는 기사 건너뛰기: {article.get('url', '알 수 없는 URL')}")
                page_failed += 1
                continue
                
            # 이미지 검증 (주석 처리됨)
            # if not article.get('image_url'):
            #     print(f"이미지가 없는 기사 건너뛰기: {article.get('title')}")
            #     continue
                
            url = article.get('url')
            if url:
                content = extract_article_content(url)
                if content:
                    article['content'] = content
                    articles_with_content.append(article)
                else:
                    print(f"[예외] 본문이 없는 기사 건너뛰기: {article.get('title')}")
                    page_failed += 1
            else:
                print(f"[예외] URL이 없는 기사 건너뛰기: {article.get('title')}")
                page_failed += 1
        
        all_articles.extend(articles_with_content)
        total_failed += page_failed
        print(f"ZDNET: 페이지 {page} 최종 처리 완료, {len(articles_with_content)}개 기사 유효, {page_failed}개 실패")
        
        # 페이지 간 지연 시간 추가
        time.sleep(2)
    
    print(f"ZDNET: 총 {len(all_articles)}개 기사 스크래핑 성공, {total_failed}개 실패")
    
    # CSV 파일 저장
    if all_articles:
        csv_path = "../../data/raw/zdnet_article.csv"
        save_to_csv(all_articles, csv_path)
        print(f"ZDNET: CSV 파일 저장 완료 ({csv_path})")
    
    return all_articles


def extract_article_content(url):
    """
    기사 URL에서 전체 본문 내용을 추출합니다.
    """
    try:
        response = requests.get(url, headers=HEADERS)
        
        if response.status_code != 200:
            print(f"[예외] 기사 페이지 접근 실패: {url} (상태 코드: {response.status_code})")
            return ""
            
        soup = BeautifulSoup(response.text, "html.parser")
        
        # 방법 1: c-ShortcodeContent 클래스에서 추출 (일반적인 기사)
        content_div = soup.find("div", class_="c-ShortcodeContent")
        if content_div:
            # 모든 텍스트 내용 가져오기 (p 태그뿐만 아니라 모든 텍스트)
            # get_text()는 공백을 유지하면서 모든 하위 텍스트를 가져옴
            full_content = content_div.get_text(separator="\n\n", strip=True)
            if full_content:
                return full_content
            
            # 위 방법이 실패한 경우, 모든 p 태그 시도
            paragraphs = content_div.find_all(["p", "h2", "h3", "li", "blockquote"])
            if paragraphs:
                full_content = "\n\n".join([p.get_text(strip=True) for p in paragraphs])
                if full_content:
                    return full_content
        
        # 방법 2: article 태그 내에서 추출
        article = soup.find("article")
        if article:
            # 방법 2-1: article 내의 구조화된 콘텐츠 클래스 찾기
            content_section = article.find("div", class_=lambda c: c and ("content" in c.lower() or "article" in c.lower()))
            if content_section:
                # 전체 텍스트 시도
                full_content = content_section.get_text(separator="\n\n", strip=True)
                if full_content:
                    return full_content
                
                # 모든 요소 시도
                elements = content_section.find_all(["p", "h2", "h3", "li", "blockquote"])
                if elements:
                    full_content = "\n\n".join([el.get_text(strip=True) for el in elements])
                    if full_content:
                        return full_content
            
            # 방법 2-2: article 내의 모든 텍스트
            full_content = article.get_text(separator="\n\n", strip=True)
            if full_content:
                return full_content
        
        # 방법 3: main 태그에서 추출
        main = soup.find("main")
        if main:
            # 전체 텍스트 추출
            full_content = main.get_text(separator="\n\n", strip=True)
            if full_content:
                return full_content
            
            # 컨텐츠 섹션 찾기
            content_section = main.find("div", class_=lambda c: c and ("content" in c.lower() or "article" in c.lower()))
            if content_section:
                full_content = content_section.get_text(separator="\n\n", strip=True)
                if full_content:
                    return full_content
        
        # 방법 4: 모든 본문 관련 클래스에서 추출 시도
        content_containers = soup.find_all(["div", "section"], class_=lambda c: c and any(term in str(c).lower() for term in ["content", "article", "text", "body", "story"]))
        for container in content_containers:
            full_content = container.get_text(separator="\n\n", strip=True)
            if full_content and len(full_content) > 200:  # 최소 길이 확인
                return full_content
        
        print(f"[예외] 본문 추출 실패: {url}")
        return ""
        
    except Exception as e:
        print(f"[예외] 기사 본문 추출 오류: {url} - {str(e)}")
        return ""


if __name__ == "__main__":
    # 기존 코드를 start 함수 호출로 대체
    articles = zdnet_start(page_count=1)
