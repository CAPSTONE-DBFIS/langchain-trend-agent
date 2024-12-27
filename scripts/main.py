# main.py
import pandas as pd
import os
import time
from concurrent.futures import ThreadPoolExecutor
from embedding import get_embedding
from milvus import connect_to_milvus, create_collection_if_not_exists, insert_into_collection, delete_collection_if_exists
from scraper import scrape_data_by_category
from parser import parse_data, close_driver
from classification import TextClassifier

# 데이터 경로 설정
raw_save_path = '/Users/taehyungkim/study/crawling/data/raw/article_data.csv'
processed_dir = '/Users/taehyungkim/study/crawling/data/processed/'
collection_name = "news_articles"

def process_article(raw_html, url):
    """
    각 기사 HTML과 URL을 파싱하여 정리된 데이터를 반환.
    """
    return parse_data(raw_html, url)

if __name__ == "__main__":
    # 트렌드 키워드를 담은 CSV 파일에서 데이터 읽어오기
    df = pd.read_csv("/Users/taehyungkim/study/crawling/data/raw/it_companies_and_trends.csv", encoding="utf-8-sig")    
    categories = pd.concat([df['Competitors'], df['IT Trends']]).dropna().unique().tolist()

    # 실행 시간 측정 시작
    start_time = time.time()

    # 카테고리별로 데이터 크롤링 및 파싱
    raw_html_list, url_list = scrape_data_by_category(categories)

    if raw_html_list and url_list:
        all_data = []

        # 멀티스레딩으로 병렬 처리
        with ThreadPoolExecutor(max_workers=5) as executor:
            results = executor.map(process_article, raw_html_list, url_list)

        all_data = list(results)

        # 데이터프레임으로 변환 및 CSV 저장
        df = pd.DataFrame(all_data)
        df.to_csv(raw_save_path, index=False, encoding='utf-8-sig')
        print(f"크롤링 결과가 {raw_save_path}에 저장되었습니다.")

        # Classification 모듈 호출
        classifier = TextClassifier(input_file=raw_save_path, output_dir=processed_dir)
        classifier.process_and_save()

        # Milvus 연결 및 컬렉션 설정
        connect_to_milvus()
        collection = create_collection_if_not_exists(collection_name)

        # OpenAI 임베딩 생성 및 Milvus 저장
        embeddings = []
        metadata = {
            "category": [],
            "media_company": [],
            "url": [],
            "title": [],
            "date": [],
        }

        for article in all_data:
            content = article.get('content')  # 파싱된 본문 내용
            if content:
                embedding = get_embedding(content)
                if embedding:
                    embeddings.append(embedding)
                    metadata["category"].append(article.get("category"))
                    metadata["media_company"].append(article.get("media_company"))
                    metadata["url"].append(article.get("url"))
                    metadata["title"].append(article.get("title"))
                    metadata["date"].append(article.get("date"))

        # Milvus에 데이터 삽입
        insert_into_collection(collection, embeddings, metadata)
        print(f"Milvus에 총 {len(embeddings)}개의 임베딩이 저장되었습니다.")

    else:
        print("크롤링 실패 또는 유효한 데이터를 찾지 못했습니다.")

    # 크롤링이 끝나면 드라이버 종료
    close_driver()

    # 실행 시간 출력
    end_time = time.time()
    print(f"전체 실행 시간: {end_time - start_time:.2f}초")