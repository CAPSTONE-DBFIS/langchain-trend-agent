import os
from dotenv import load_dotenv
from elasticsearch import Elasticsearch
import pandas as pd
import logging
import time
from datetime import datetime, timedelta
from scraper import scrape_articles_by_date
from parser import parse_data
from scripts.classification import classification_es
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
    start_date = datetime.strptime("20250404", "%Y%m%d")
    # 현재 날짜의 전날을 종료 날짜로 설정
    end_date = datetime.today() - timedelta(days=1)

    logging.info(f"크롤링 범위: {start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}")

    # 크롤링 시작
    article_data_list = scrape_articles_by_date(start_date, end_date)

    if article_data_list:
        all_data = []

        for article_data in article_data_list:
            result = parse_data(article_data["html"], article_data["url"])
            if result:  # None이 아닌 경우만 저장
                result["category"] = article_data["category"]  # 카테고리 추가
                all_data.append(result)

        # CSV 저장 (제목 없는 기사 제외됨)
        df = pd.DataFrame(all_data)
        df.to_csv(raw_save_path, index=False, encoding="utf-8-sig")
        # 댓글 개수 추가시 comment_count 추가
        df = df[["category", "media_company", "title", "date", "content", "image", "url"]]
        df.to_csv(raw_save_path, index=False, encoding="utf-8-sig")

        logging.info(f"크롤링 완료: {len(df)}개의 기사 저장됨")

        # Elasticsearch에 저장
        for _, article in df.iterrows():
            doc = {
                "category": article['category'],
                "media_company": article['media_company'],
                "title": article['title'],
                "date": article['date'],
                "content": article['content'],
                "image": article['image'],
                "url": article['url']
            }

            try:
                es.index(index=os.getenv("ELASTICSEARCH_INDEX_NAME"), document=doc)
                logging.info(f"Elasticsearch에 문서 저장 완료: {article['title']}")
            except Exception as e:
                logging.error(f"Error indexing document: {e}")

        # 키워드 빈도수 추출 후 rdb 저장
        # classifier = classification.SemanticTextClassifier(input_file=raw_save_path)
        # classifier.process_and_send()

        # 키워드 빈도수, 연관 키워드 추출 후 rdb 저장
        top_keywords, related_keywords = classification_es.keyword_analysis(date=start_date,
                                                                            stopwords_file_path="../../data/raw/stopwords.txt")

        # Milvus 연결
        rag.connect_milvus()

        # 뉴스 임베딩 저장
        rag.store_domestic()

    else:
        logging.warning("크롤링 실패 또는 유효한 데이터 없음")

    # 실행 종료 로그 기록
    end_time = time.time()
    elapsed_time = round(end_time - start_time, 2)
    logging.info(f"실행 종료 (소요 시간: {elapsed_time}초)")

    print("크롤링이 완료되었습니다.")

    # 드라이버 종료
    # close_driver()