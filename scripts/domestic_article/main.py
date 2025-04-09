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

load_dotenv()

# 로그 디렉토리 설정
LOG_DIR = "../../logs"
LOG_FILE = os.path.join(LOG_DIR, "project.log")

# 로그 디렉토리가 없으면 생성
os.makedirs(LOG_DIR, exist_ok=True)

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
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

es = Elasticsearch([{'host': os.getenv("ELASTICSEARCH_HOST"), 'port': int(os.getenv("ELASTICSEARCH_PORT")), 'scheme': 'http'}])

# 실행 시작 시간 기록
start_time = time.time()
logging.info("main.py 실행 시작")

if __name__ == "__main__":
    max_workers = 4  # 스레드 수 (시스템 사양에 따라 조절)

    start_date = datetime.now() - timedelta(days=1)
    end_date = start_date

    # 크롤링할 날짜 범위 반복
    current_date = start_date
    while current_date <= end_date:
        print(f"{current_date.strftime('%Y-%m-%d')} 크롤링 시작")
        logging.info(f"{current_date.strftime('%Y-%m-%d')} 날짜 크롤링 시작")

        # URL 수집 단계
        category_urls = scrape_all_categories_in_parallel(current_date, max_workers)  # 모든 URL을 수집하여 딕셔너리로 반환

        # URL들을 단일 리스트로 변환
        article_urls = []
        for urls in category_urls.values():
            if isinstance(urls, list):
                article_urls.extend(urls)

        if not article_urls:
            print("URL 수집 실패 또는 유효한 URL이 없음")
            logging.warning(f"{current_date.strftime('%Y-%m-%d')} 크롤링 실패 또는 유효한 데이터 없음")
            current_date += timedelta(days=1)
            continue  # 다음 날짜로 이동

        # URL들을 병렬로 파싱
        parsed_data = parse_articles_in_parallel(article_urls, max_workers)

        # 파싱된 데이터 DataFrame으로 변환 및 CSV로 저장
        df = pd.DataFrame(parsed_data)
        df = df[["category", "media_company", "title", "date", "content", "url", "image_url"]]  # 이미지 URL 포함
        df.to_csv(raw_save_path, index=False, encoding="utf-8-sig")

        logging.info(f"{current_date.strftime('%Y-%m-%d')} 크롤링 완료: {len(df)}개의 기사 저장됨")

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

        logging.info(f"Elasticsearch에 기사 저장 완료")
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
    logging.info(f"실행 종료 (소요 시간: {elapsed_time}초)")
    print(f"실행 종료 (소요 시간: {elapsed_time}초)")
    print("크롤링이 완료되었습니다.")