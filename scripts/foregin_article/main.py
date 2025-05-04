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
from scripts.foregin_article.the_verge.main_verge import the_verge_start
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
        logger.info(f"Elasticsearch 인덱스 '{ES_INDEX}' 생성 완료")
    else:
        logger.info(f"Elasticsearch 인덱스 '{ES_INDEX}' 확인 완료")

def save_to_elasticsearch(articles):
    """스크래핑한 기사 데이터를 Elasticsearch에 저장합니다."""
    if not articles:
        logger.warning("저장할 기사가 없습니다.")
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
                
        logger.info(f"이미 저장된 URL 수: {len(existing_urls)}")
    except Exception as e:
        logger.error(f"[예외] 기존 URL 조회 오류: {str(e)}")
    
    # 새 기사만 저장
    success_count = 0
    skipped_count = 0
    
    for article in articles:
        try:
            # URL이 이미 있는지 확인 (중복 기사)
            if article["url"] in existing_urls:
                logger.debug(f"URL 중복으로 건너뜀: {article['url']}")
                skipped_count += 1
                continue
            
            # 필수 필드 확인 (제목, 본문)
            if not article.get("title"):
                logger.warning(f"제목 누락으로 기사 제외: {article.get('url', '알 수 없는 URL')}")
                skipped_count += 1
                continue
            
            if not article.get("content"):
                logger.warning(f"본문 누락으로 기사 제외: {article.get('title', '제목 없음')}, URL: {article.get('url', '알 수 없는 URL')}")
                skipped_count += 1
                continue
            
            if article.get("title") == "제목 없음":
                logger.warning(f"유효하지 않은 제목으로 기사 제외: {article.get('url', '알 수 없는 URL')}")
                skipped_count += 1
                continue
            
            if article.get("content") == "본문 없음":
                logger.warning(f"유효하지 않은 본문으로 기사 제외: {article.get('title', '제목 없음')}, URL: {article.get('url', '알 수 없는 URL')}")
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
            logger.error(f"[예외] 기사 저장 오류: {article.get('url', '알 수 없는 URL')} - {str(e)}")
            skipped_count += 1
    
    logger.info(f"ES 저장 완료: {success_count}개 기사 저장, {skipped_count}개 건너뜀")
    return success_count

def format_time(seconds):
    """초를 분:초 형식으로 변환합니다."""
    minutes = seconds // 60
    remaining_seconds = seconds % 60
    return f"{int(minutes)}분 {int(remaining_seconds)}초"

def main():
    """메인 함수: 해외 기사 스크래핑 및 키워드 분석을 실행합니다."""
    global logger
    logger = setup_logger()
    
    start_time = time.time()
    success = True
    
    logger.info("===== 해외 기사 스크래핑 시작 =====")
    
    try:
        # 스크래핑할 페이지 수 설정
        all_articles = []
        
        # 1. NYT 기사 스크래핑
        logger.info("----- New York Times 스크래핑 시작 -----")
        nyt_articles = nyt_start(1)
        all_articles.extend(nyt_articles)
        logger.info(f"NYT 스크래핑 완료: {len(nyt_articles)}개 기사")
        
        # 2. TechCrunch 기사 스크래핑
        logger.info("----- TechCrunch 스크래핑 시작 -----")
        techcrunch_articles = techcrunch_start(2)
        all_articles.extend(techcrunch_articles)
        logger.info(f"TechCrunch 스크래핑 완료: {len(techcrunch_articles)}개 기사")
        
        # 3. Ars Technica 기사 스크래핑
        logger.info("----- Ars Technica 스크래핑 시작 -----")
        ars_technica_articles = ars_technica_start(1)
        all_articles.extend(ars_technica_articles)
        logger.info(f"Ars Technica 스크래핑 완료: {len(ars_technica_articles)}개 기사")
        
        # 4. ZDNET 기사 스크래핑
        logger.info("----- ZDNET 스크래핑 시작 -----")
        zdnet_articles = zdnet_start(3)
        all_articles.extend(zdnet_articles)
        logger.info(f"ZDNET 스크래핑 완료: {len(zdnet_articles)}개 기사")

        # 5. THE VERGE 기사 스크래핑
        logger.info("----- THE VERGE 스크래핑 시작 -----")
        the_verge_articles = the_verge_start(page_count=3)
        all_articles.extend(the_verge_articles)
        logger.info(f"THE VERGE 스크래핑 완료: {len(the_verge_articles)}개 기사")
        
        # 6. 전체 스크래핑 결과 요약
        logger.info(f"총 {len(all_articles)}개 기사 스크래핑 완료")
        
        # 7. Elasticsearch에 저장
        logger.info("----- Elasticsearch 저장 시작 -----")
        saved_count = save_to_elasticsearch(all_articles)
        
        # 오늘 날짜 가져오기
        today = datetime.now().strftime("%Y-%m-%d")
        
        # 8. 키워드 빈도수 추출
        logger.info("----- 키워드 빈도수 추출 시작 -----")
        try:
            keyword_extractor = ForeignKeywordExtractor()
            keywords = keyword_extractor.process_date(today)
            logger.info(f"키워드 빈도수 추출 완료: {len(keywords)}개 키워드")
        except Exception as e:
            logger.error(f"[예외] 키워드 빈도수 추출 오류: {str(e)}")
            success = False
        
        # 9. 연관 키워드 분석
        logger.info("----- 연관 키워드 분석 시작 -----")
        try:
            keyword_analyzer = ForeignKeywordAnalyzer()
            keyword_analyzer.analyze_date(today)
            logger.info("연관 키워드 분석 완료")
        except Exception as e:
            logger.error(f"[예외] 연관 키워드 분석 오류: {str(e)}")
            success = False
    
    except Exception as e:
        logger.error(f"[심각한 오류] 스크래핑 과정에서 예상치 못한 오류 발생: {str(e)}")
        success = False
    
    # 실행 시간 계산
    end_time = time.time()
    execution_time = end_time - start_time
    formatted_time = format_time(execution_time)
    
    # 최종 결과 로깅
    status = "성공" if success else "실패"
    logger.info(f"===== 해외 기사 스크래핑 및 분석 {status} (총 소요시간: {formatted_time}) =====")
    
    return success

if __name__ == "__main__":
    main()
