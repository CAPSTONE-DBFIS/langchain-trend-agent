import os
from dotenv import load_dotenv
from elasticsearch import Elasticsearch
import pandas as pd
import logging
import time
from datetime import datetime, timedelta
from scraper import scrape_all_categories_in_parallel
from parser import parse_articles_in_parallel
import extraction_keyword
import extraction_related_keyword
import scripts.rag.rag as rag
from zoneinfo import ZoneInfo

load_dotenv()

# 현재 파일 기준 절대 경로 설정
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
LOG_DIR = os.path.join(BASE_DIR, "logs")

# 로그 디렉토리가 없으면 생성
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOG_DIR, "project.log")

# 데이터 저장 경로 설정 (절대 경로)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
raw_save_path = os.path.join(BASE_DIR, "data", "raw", "article_data.csv")

#stopword 경로
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
STOPWORDS_PATH = os.path.join(BASE_DIR, "data", "raw", "stopwords.txt")

# 로그 설정
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    filemode='a',
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    encoding="utf-8"
)

# Elasticsearch 클라이언트 생성 (비밀번호 추가)
es = Elasticsearch(
    [{'host': os.getenv("ELASTICSEARCH_HOST"), 'port': int(os.getenv("ELASTICSEARCH_PORT")), 'scheme': 'http'}],
    basic_auth=(os.getenv("ELASTICSEARCH_USERNAME"), os.getenv("ELASTICSEARCH_PASSWORD"))
)

# 실행 시작 시간 기록
start_time = time.time()
logging.info("main.py run start")

if __name__ == "__main__":
    max_workers = 4  # 스레드 수 (시스템 사양에 따라 조절)

    kst_now = datetime.now(ZoneInfo("Asia/Seoul"))  # 현재 KST 시간으로 크롤링 시작
    start_date = kst_now - timedelta(days=1)
    end_date = start_date

    # 크롤링할 날짜 범위 반복
    current_date = start_date
    while current_date <= end_date:
        date_str = current_date.strftime('%Y-%m-%d')
        print(f"{current_date.strftime('%Y-%m-%d')} 크롤링 시작")
        logging.info(f"{date_str} Start date crawling")

        # Scraper: 모든 카테고리의 기사 URL과 해당 카테고리 정보를 딕셔너리 리스트로 병렬로 수집
        article_info_list = scrape_all_categories_in_parallel(current_date, max_workers)

        if not article_info_list:
            print("URL 수집 실패 또는 유효한 URL이 없음")
            logging.warning(f"{date_str} Crawling failed or no valid data")
            current_date += timedelta(days=1)
            continue

        # Parser: 수집된 기사 정보(각 dict에 "url", "category" 포함)를 기반으로 HTML 병렬 파싱
        parsed_data = parse_articles_in_parallel(article_info_list, max_workers)

        # 파싱된 데이터 DataFrame으로 변환 및 CSV로 저장
        df = pd.DataFrame(parsed_data)
        df = df[["category", "media_company", "title", "date", "content", "url", "image_url"]]  # 이미지 URL 포함
        df.to_csv(raw_save_path, index=False, encoding="utf-8-sig")

        logging.info(f"{current_date.strftime('%Y-%m-%d')} Crawling completed: {len(df)}articles saved")

        # CSV 파일에서 데이터 읽기
        df = pd.read_csv(raw_save_path, encoding="utf-8-sig")

        # Elasticsearch에 저장
        for _, article in df.iterrows():
            # 데이터가 올바른 형식인지 확인 후 Elasticsearch에 저장
            doc = {
                "category": article['category'] if isinstance(article['category'], str) else '',
                "media_company": article['media_company'] if isinstance(article['media_company'], str) else '',
                "title": article['title'] if isinstance(article['title'], str) else '',
                "date": article['date'] if isinstance(article['date'], str) else '',
                "content": article['content'] if isinstance(article['content'], str) else '',
                "url": article['url'] if isinstance(article['url'], str) else '',
                "image_url": article['image_url'] if isinstance(article['image_url'], str) else ''
            }

            # 날짜가 str 형식이면 변환, 이미 날짜 형식이면 그대로 둠
            if isinstance(doc['date'], str):
                doc['date'] = datetime.strptime(doc['date'], '%Y-%m-%d').strftime('%Y-%m-%d')

            # Elasticsearch에 저장
            doc_id = article['url']  # URL을 고유한 id로 사용하여 중복 방지
            es.index(index=os.getenv("ELASTICSEARCH_INDEX_NAME"), id=doc_id, document=doc)

        logging.info(f"Complete saving of articles to Elasticsearch")
        print(f"Elasticsearch에 기사 저장 완료")

        # 키워드 빈도수 추출 후 RDB 저장
        classifier = extraction_keyword.SemanticTextClassifier(input_file=raw_save_path)
        classifier.process_and_send(date=current_date)

        # 연관 키워드 추출 후 RDB 저장
        top_keywords, related_keywords = extraction_related_keyword.keyword_analysis(
            date=current_date,
            stopwords_file_path=STOPWORDS_PATH
        )

        # 본문 임베딩 저장
        rag.store_domestic()

        current_date += timedelta(days=1)  # 다음 날짜로 이동

    # 실행 종료 로그 기록
    end_time = time.time()
    elapsed_time = round(end_time - start_time, 2)
    logging.info(f"runtime: {elapsed_time}sec)")
    print(f"실행 종료 (소요 시간: {elapsed_time}초)")
    print("크롤링이 완료되었습니다.")