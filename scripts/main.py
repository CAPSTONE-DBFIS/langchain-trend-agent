from scraper import scrape_data_by_category
from parser import parse_data, close_driver
from classification import TextClassifier
import pandas as pd
import os
from concurrent.futures import ThreadPoolExecutor
import time

# 데이터 경로 설정
raw_save_path = '../data/raw/article_data.csv'
processed_dir = '../data/processed/'

def process_article(raw_html, url):
    return parse_data(raw_html, url)

if __name__ == "__main__":
    # 트렌드 키워드를 담은 CSV 파일에서 데이터 읽어오기
    df = pd.read_csv("C:/Users/sng02/Desktop/CAPSTONE/crawling/data/raw/it_companies_and_trends.csv", encoding="utf-8-sig")
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

    else:
        print("크롤링 실패 또는 유효한 데이터를 찾지 못했습니다.")

    # 크롤링이 끝나면 드라이버 종료
    close_driver()

    # 실행 시간 출력
    end_time = time.time()
    print(f"전체 실행 시간: {end_time - start_time:.2f}초")
