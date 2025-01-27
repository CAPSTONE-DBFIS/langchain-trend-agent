import pandas as pd
import time
import os
from scraper import scrape_data_by_category
from parser import parse_data, close_driver
from classification import SemanticTextClassifier
from rag import *

# 현재 스크립트 위치 기준으로 상대 경로 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_DATA_PATH = os.path.join(BASE_DIR, '..', 'data', 'raw', 'article_data.csv')
PROCESSED_DIR = os.path.join(BASE_DIR, '..', 'data', 'processed')
SEARCH_KEYWORD_CSV_PATH = os.path.join(BASE_DIR, '..', 'data', 'raw', 'it_companies_and_trends.csv')

def process_article(raw_html, url):
    return parse_data(raw_html, url)

if __name__ == "__main__":
    start_time = time.time()

    # 트렌드 키워드 로드
    df = pd.read_csv(SEARCH_KEYWORD_CSV_PATH, encoding="utf-8-sig")
    categories = pd.concat([df['Competitors'], df['IT Trends']]).dropna().unique().tolist()

    # 카테고리별로 데이터 크롤링 및 파싱
    raw_html_list, url_list = scrape_data_by_category(categories)

    if raw_html_list and url_list:
        all_data = []

        # 순차적으로 처리
        for raw_html, url in zip(raw_html_list, url_list):
            data = process_article(raw_html, url)
            all_data.append(data)

        # 데이터프레임으로 변환 및 CSV 저장
        df = pd.DataFrame(all_data)
        df.to_csv(RAW_DATA_PATH, index=False, encoding='utf-8-sig')
        print(f"크롤링 결과가 {RAW_DATA_PATH}에 저장되었습니다.")

        # Classification 모듈 호출
        classifier = SemanticTextClassifier(input_file=RAW_DATA_PATH, output_dir=PROCESSED_DIR)
        classifier.process_and_save()

        # Milvus 연결
        connect_milvus()

        # 기존 컬렉션 삭제 (이미 존재하면 삭제)
        # remove_collection("news_article")

        # 컬렉션 생성
        # create_collection("news_article")

        # 뉴스 임베딩 저장
        store_article_embedding("news_article")

    else:
        print("크롤링 실패 또는 유효한 데이터를 찾지 못했습니다.")

    # 드라이버 종료 및 실행 시간 출력
    close_driver()
    end_time = time.time()
    print(f"전체 실행 시간: {end_time - start_time:.2f}초")