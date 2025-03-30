import scripts.rag.rag as rag
from scraper import scrape_articles_by_date
from parser import parse_data, close_driver
import scripts.classification.classification_domestic as classification
from datetime import datetime, timedelta
import logging
import pandas as pd
import time
import os

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

# 실행 시작 시간 기록
start_time = time.time()
logging.info("main.py 실행 시작")

if __name__ == "__main__":
    start_date = datetime.strptime("20250329", "%Y%m%d")
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

        # Classification 모듈 호출
        # classifier = SemanticTextClassifier(input_file=RAW_DATA_PATH, output_dir=PROCESSED_DIR)
        # classifier.process_and_save()

        # Milvus 연결
        # rag.connect_milvus()

        # 기존 컬렉션 삭제 (이미 존재하면 삭제)
        # rag.remove_collection("news_article")

        # 컬렉션 생성
        # rag.create_domestic()

        # 뉴스 임베딩 저장
        # rag.store_domestic()

    else:
        logging.warning("크롤링 실패 또는 유효한 데이터 없음")

    # 실행 종료 로그 기록
    end_time = time.time()
    elapsed_time = round(end_time - start_time, 2)
    logging.info(f"실행 종료 (소요 시간: {elapsed_time}초)")

    print("크롤링이 완료되었습니다.")

    # 드라이버 종료
    # close_driver()