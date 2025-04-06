import os
from dotenv import load_dotenv
from elasticsearch import Elasticsearch
import pandas as pd
import logging
import time
from datetime import datetime, timedelta
from scraper import scrape_all_categories_in_parallel
from parser import parse_articles_in_parallel
from scripts.domestic_article import extraction_keyword
from scripts.domestic_article import extraction_related_keyword
import scripts.rag.rag as rag

load_dotenv()

# 로그 디렉토리 설정
LOG_DIR = "../../logs"
LOG_FILE = os.path.join(LOG_DIR, "project.log")

# 로그 디렉토리가 없으면 생성
os.makedirs(LOG_DIR, exist_ok=True)

# 데이터 저장 경로 설정
raw_save_path = "../../data/raw/article_data.csv"

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
    max_workers = 7 # 스레드 수 (시스템 사양에 따라 조절)
    start_date = datetime.strptime("20250403", "%Y%m%d")  # 시작 날짜
    end_date = datetime.strptime("20250405", "%Y%m%d")  # 종료 날짜

    # 크롤링할 날짜 범위 반복
    current_date = start_date
    while current_date <= end_date:
        print(f"{current_date.strftime('%Y-%m-%d')} 크롤링 시작")
        logging.info(f"{current_date.strftime('%Y-%m-%d')} 날짜 크롤링 시작")

        # URL 수집 단계 (scraper.py 사용)
        category_urls = scrape_all_categories_in_parallel(current_date, max_workers)  # 모든 URL을 수집하여 딕셔너리로 반환

        # URL들을 단일 리스트로 변환
        article_urls = []
        for urls in category_urls.values():
            if isinstance(urls, list):  # 리스트일 때만 추가
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
        df = df[["category", "media_company", "title", "date", "content", "url"]]
        df.to_csv(raw_save_path, index=False, encoding="utf-8-sig")

        logging.info(f"{current_date.strftime('%Y-%m-%d')} 크롤링 완료: {len(df)}개의 기사 저장됨")

        # Elasticsearch 저장
        for _, article in df.iterrows():
            doc = {
                "category": article['category'],
                "media_company": article['media_company'],
                "title": article['title'],
                "date": article['date'],
                "content": article['content'],
                "url": article['url']
            }

            try:
                doc_id = article['url']  # URL을 고유한 id로 사용하여 중복 방지
                es.index(index=os.getenv("ELASTICSEARCH_INDEX_NAME"), id=doc_id, document=doc)
                logging.info(f"Elasticsearch에 문서 저장 완료: {article['title']}")
            except Exception as e:
                logging.error(f"Error indexing document: {e}")

        # 키워드 빈도수 추출 후 RDB 저장
        classifier = extraction_keyword.SemanticTextClassifier(input_file=raw_save_path)
        classifier.process_and_send(date=current_date)

        # 연관 키워드 추출 후 RDB 저장
        top_keywords, related_keywords = extraction_related_keyword.keyword_analysis(
            date=current_date,
            stopwords_file_path="../../data/raw/stopwords.txt"
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