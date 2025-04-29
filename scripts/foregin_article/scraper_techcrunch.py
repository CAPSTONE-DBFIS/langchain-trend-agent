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


def techcrunch_url_scraper(page_count=1):
    base_url = "https://techcrunch.com/latest/"
    headers = {"User-Agent": "Mozilla/5.0"}
    links = []
    for page in range(1, page_count + 1):
        url = base_url if page == 1 else f"{base_url}page/{page}/"
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            print(f"[예외] 페이지 {page} 요청 실패: {response.status_code}")
            continue
        soup = BeautifulSoup(response.content, 'html.parser')
        page_links = []
        for a_tag in soup.find_all('a', href=True):
            link = a_tag['href']
            if re.match(r"^https://techcrunch\.com/\d{4}/", link):
                page_links.append(link)
        links.extend(page_links)
        print(f"TechCrunch: 페이지 {page}에서 {len(page_links)}개 URL 수집 완료")
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


def extract_image_url(soup):
    """TechCrunch 기사에서 이미지 URL 추출"""
    try:
        # 1. 'loop-card__figure' 클래스를 가진 figure 태그에서 이미지 찾기
        figure = soup.find('figure', class_='loop-card__figure')
        if figure:
            img = figure.find('img')
            if img and img.has_attr('src'):
                # 고해상도 이미지가 있는지 srcset 확인
                if img.has_attr('srcset'):
                    srcset = img['srcset']
                    parts = srcset.split(',')
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
                
                # srcset이 없거나 추출 실패시 src 사용
                return img['src']

        # 2. 일반 기사 내부의 이미지 찾기
        article_img = soup.find('img', class_='wp-post-image')
        if article_img and article_img.has_attr('src'):
            return article_img['src']

        # 3. 큰 이미지 찾기 (featured image)
        featured_img = soup.find('img', class_='size-large')
        if featured_img and featured_img.has_attr('src'):
            return featured_img['src']

        # 4. 기사 본문 내 첫 번째 이미지 찾기
        content = soup.find('div', class_='article-content')
        if content:
            img = content.find('img')
            if img and img.has_attr('src'):
                return img['src']

        # 5. 모든 이미지 중에서 가장 큰 이미지 선택
        all_imgs = soup.find_all('img')
        largest_img = ""
        largest_width = 0
        
        for img in all_imgs:
            if img.has_attr('width') and img.has_attr('src'):
                try:
                    width = int(img['width'])
                    if width > largest_width:
                        largest_width = width
                        largest_img = img['src']
                except ValueError:
                    continue
        
        if largest_img:
            return largest_img

    except Exception as e:
        print(f"[예외] 이미지 URL 추출 오류: {str(e)}")

    return ""  # 이미지를 찾지 못한 경우 빈 문자열 반환


def techcrunch_article_scraper(urls):
    headers = {"User-Agent": "Mozilla/5.0"}
    articles = []
    media_company = "TechCrunch"
    category = "IT"  # 기본 카테고리 설정
    failed_count = 0
    
    print(f"TechCrunch: 총 {len(urls)}개 URL 스크래핑 시작")
    
    for url in urls:
        try:
            response = requests.get(url, headers=headers)
            if response.status_code != 200:
                print(f"[예외] 기사 요청 실패: {url}")
                failed_count += 1
                continue
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            title_tag = soup.select_one("h1.article-hero__title.wp-block-post-title")
            if not title_tag:
                print(f"[예외] 제목을 찾을 수 없음: {url}")
                failed_count += 1
                continue
            
            title = title_tag.get_text(strip=True)
            if not title:
                print(f"[예외] 제목이 비어 있음: {url}")
                failed_count += 1
                continue
            
            date_str = extract_date_from_url(url)
            if date_str == "날짜를 찾을 수 없음":
                print(f"[예외] 날짜를 찾을 수 없음: {url}")
                failed_count += 1
                continue
                
            formatted_date = format_date(date_str, input_format="%Y-%m-%d")
            
            desc_div = soup.select_one(
                "div.entry-content.wp-block-post-content.is-layout-constrained.wp-block-post-content-is-layout-constrained")
            if not desc_div:
                print(f"[예외] 본문을 찾을 수 없음: {url}")
                failed_count += 1
                continue
                
            content = clean_html_text(desc_div)
            if not content or len(content.strip()) < 100:  # 본문이 너무 짧으면 무시
                print(f"[예외] 본문이 비어 있거나 너무 짧음: {url}")
                failed_count += 1
                continue
            
            # 이미지 URL 추출 (이미지는 필수 항목)
            image_url = extract_image_url(soup)
            if not image_url:
                print(f"[예외] 이미지 URL을 찾을 수 없어 기사를 건너뜁니다: {url}")
                failed_count += 1
                continue
            
            articles.append({
                "category": category,
                "content": content,
                "date": formatted_date,
                "image_url": image_url,
                "media_company": media_company,
                "title": title,
                "url": url
            })
            
        except Exception as e:
            print(f"[예외] 기사 스크래핑 중 오류 발생: {url} - {str(e)}")
            failed_count += 1
    
    print(f"TechCrunch: 총 {len(articles)}개 기사 스크래핑 성공, {failed_count}개 실패")
    return articles


def techcrunch_start(page_count=1):
    """
    TechCrunch 기사 스크래핑을 시작하는 함수. 
    지정된 페이지 수만큼 스크래핑을 시도합니다.
    
    Args:
        page_count (int): 스크래핑할 페이지 수
    
    Returns:
        list: 스크래핑된 기사 리스트
    """
    print(f"TechCrunch 기사 스크래핑 시작 (총 {page_count}페이지)")
    
    # 페이지별로 URL 수집
    urls = techcrunch_url_scraper(page_count)
    print(f"TechCrunch: 중복 제거 후 {len(urls)}개 URL 확인")
    
    # 기사 내용 스크래핑
    articles = techcrunch_article_scraper(urls)
    
    # CSV 파일 저장
    if articles:
        csv_path = "../../data/raw/techcrunch_article.csv"
        save_to_csv(articles, csv_path)
        print(f"TechCrunch: CSV 파일 저장 완료 ({csv_path})")
    
    return articles


if __name__ == "__main__":
    # 기존 코드를 start 함수 호출로 대체
    articles = techcrunch_start(page_count=1)
