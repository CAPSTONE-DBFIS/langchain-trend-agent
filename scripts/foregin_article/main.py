import os
import json
from datetime import datetime
import time
import logging
from elasticsearch import Elasticsearch
from dotenv import load_dotenv

# 자체 모듈 임포트
from scraper_nyt import nyt_start
from scraper_techcrunch import techcrunch_start
from scraper_ars_technica import ars_technica_start
from scraper_zdnet import zdnet_start
from foreign_keyword_extractor import ForeignKeywordExtractor
from foreign_keyword_analyzer import ForeignKeywordAnalyzer

# 환경변수 로드
load_dotenv()

# 로깅 설정
def setup_logger():
    # 로그 디렉토리 생성
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    # 로거 설정
    logger = logging.getLogger('foreign_scraper')
    logger.setLevel(logging.INFO)
    
    # 파일 핸들러 추가
    file_handler = logging.FileHandler(os.path.join(log_dir, 'foreign.log'), encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    
    # 콘솔 핸들러 추가
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # 포맷 설정
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', '%Y-%m-%d %H:%M:%S')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # 핸들러 추가
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

# Elasticsearch 연결 설정
ES_HOST = os.getenv("ELASTICSEARCH_HOST", "localhost")
ES_PORT = int(os.getenv("ELASTICSEARCH_PORT", "9200"))
ES_USER = os.getenv("ELASTICSEARCH_USERNAME", "")
ES_PASS = os.getenv("ELASTICSEARCH_PASSWORD", "")
ES_INDEX = "foreign_news_article"  # 해외 기사용 인덱스명

# Elasticsearch 클라이언트 초기화
es = Elasticsearch(
    [{'host': ES_HOST, 'port': ES_PORT, 'scheme': 'http'}],
    basic_auth=(ES_USER, ES_PASS) if ES_USER and ES_PASS else None
)

def ensure_es_index_exists():
    """Elasticsearch 인덱스가 존재하는지 확인하고, 없으면 생성합니다."""
    if not es.indices.exists(index=ES_INDEX):
        # 인덱스 매핑 설정
        mappings = {
            "mappings": {
                "properties": {
                    "category": {"type": "keyword"},
                    "content": {"type": "text"},
                    "date": {"type": "date"},
                    "image_url": {"type": "text"},
                    "media_company": {"type": "keyword"},
                    "title": {"type": "text"},
                    "url": {"type": "text"}
                }
            }
        }
        # 인덱스 생성
        es.indices.create(index=ES_INDEX, body=mappings)
        logger.info(f"Elasticsearch index '{ES_INDEX}' created successfully")
    else:
        logger.info(f"Elasticsearch index '{ES_INDEX}' already exists")

def save_to_elasticsearch(articles):
    """스크래핑한 기사 데이터를 Elasticsearch에 저장합니다."""
    if not articles:
        logger.warning("No articles to save")
        return 0
    
    # 인덱스 존재 여부 확인
    ensure_es_index_exists()
    
    # URL 기준으로 중복 확인을 위한 기존 URL 조회
    existing_urls = set()
    
    try:
        # 이미 존재하는 URL 목록 가져오기
        query = {
            "size": 10000,
            "_source": ["url"],
            "query": {"match_all": {}}
        }
        response = es.search(index=ES_INDEX, body=query)
        
        for hit in response["hits"]["hits"]:
            if "url" in hit["_source"]:
                existing_urls.add(hit["_source"]["url"])
                
        logger.info(f"Number of existing URLs: {len(existing_urls)}")
    except Exception as e:
        logger.error(f"[EXCEPTION] Error querying existing URLs: {str(e)}")
    
    # 새 기사만 저장
    success_count = 0
    skipped_count = 0
    
    for article in articles:
        try:
            # URL이 이미 있는지 확인 (중복 기사)
            if article["url"] in existing_urls:
                skipped_count += 1
                continue
            
            # 필수 필드 확인 (제목, 본문, 이미지가 모두 있어야 함)
            if (not article.get("title") or 
                not article.get("content") or 
                not article.get("image_url") or
                article.get("title") == "제목 없음" or
                article.get("content") == "본문 없음"):
                logger.warning(f"[EXCEPTION] Article excluded due to missing required fields: {article.get('title', 'No title')}")
                skipped_count += 1
                continue
            
            # 날짜 형식 정규화 (YYYY-MM-DD)
            if "date" in article and article["date"]:
                # 이미 적절한 형식인지 확인
                if not isinstance(article["date"], str) or not article["date"].strip():
                    article["date"] = datetime.now().strftime("%Y-%m-%d")
            else:
                article["date"] = datetime.now().strftime("%Y-%m-%d")
            
            # Elasticsearch에 저장
            es.index(index=ES_INDEX, document=article)
            success_count += 1
                
        except Exception as e:
            logger.error(f"[EXCEPTION] Error saving article: {article.get('url', 'Unknown URL')} - {str(e)}")
            skipped_count += 1
    
    logger.info(f"ES save completed: {success_count} articles saved, {skipped_count} skipped")
    return success_count

def format_time(seconds):
    """초를 분:초 형식으로 변환합니다."""
    minutes = seconds // 60
    remaining_seconds = seconds % 60
    return f"{int(minutes)}min {int(remaining_seconds)}sec"

def main():
    """메인 함수: 해외 기사 스크래핑 및 키워드 분석을 실행합니다."""
    global logger
    logger = setup_logger()
    
    start_time = time.time()
    success = True
    
    logger.info("===== Foreign Article Scraping Started =====")
    
    try:
        # 스크래핑할 페이지 수 설정
        all_articles = []
        
        # 1. NYT 기사 스크래핑
        logger.info("----- New York Times Scraping Started -----")
        nyt_articles = nyt_start(1)
        all_articles.extend(nyt_articles)
        logger.info(f"NYT Scraping Completed: {len(nyt_articles)} articles")
        
        # 2. TechCrunch 기사 스크래핑
        logger.info("----- TechCrunch Scraping Started -----")
        techcrunch_articles = techcrunch_start(2)
        all_articles.extend(techcrunch_articles)
        logger.info(f"TechCrunch Scraping Completed: {len(techcrunch_articles)} articles")
        
        # 3. Ars Technica 기사 스크래핑
        logger.info("----- Ars Technica Scraping Started -----")
        ars_technica_articles = ars_technica_start(1)
        all_articles.extend(ars_technica_articles)
        logger.info(f"Ars Technica Scraping Completed: {len(ars_technica_articles)} articles")
        
        # 4. ZDNET 기사 스크래핑
        logger.info("----- ZDNET Scraping Started -----")
        zdnet_articles = zdnet_start(3)
        all_articles.extend(zdnet_articles)
        logger.info(f"ZDNET Scraping Completed: {len(zdnet_articles)} articles")
        
        # 5. 전체 스크래핑 결과 요약
        logger.info(f"Total of {len(all_articles)} articles scraped successfully")
        
        # 6. Elasticsearch에 저장
        logger.info("----- Elasticsearch Saving Started -----")
        saved_count = save_to_elasticsearch(all_articles)
        
        # 오늘 날짜 가져오기
        today = datetime.now().strftime("%Y-%m-%d")
        
        # 7. 키워드 빈도수 추출
        logger.info("----- Keyword Frequency Extraction Started -----")
        try:
            keyword_extractor = ForeignKeywordExtractor()
            keywords = keyword_extractor.process_date(today)
            logger.info(f"Keyword Frequency Extraction Completed: {len(keywords)} keywords")
        except Exception as e:
            logger.error(f"[EXCEPTION] Error extracting keyword frequencies: {str(e)}")
            success = False
        
        # 8. 연관 키워드 분석
        logger.info("----- Related Keyword Analysis Started -----")
        try:
            keyword_analyzer = ForeignKeywordAnalyzer()
            keyword_analyzer.analyze_date(today)
            logger.info("Related Keyword Analysis Completed")
        except Exception as e:
            logger.error(f"[EXCEPTION] Error analyzing related keywords: {str(e)}")
            success = False
    
    except Exception as e:
        logger.error(f"[CRITICAL ERROR] Unexpected error during scraping process: {str(e)}")
        success = False
    
    # 실행 시간 계산
    end_time = time.time()
    execution_time = end_time - start_time
    formatted_time = format_time(execution_time)
    
    # 최종 결과 로깅
    status = "SUCCESS" if success else "FAILED"
    logger.info(f"===== Foreign Article Scraping and Analysis {status} (Total time: {formatted_time}) =====")
    
    return success

if __name__ == "__main__":
    main()
