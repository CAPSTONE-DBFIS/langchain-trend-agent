from scraper import scrape_data_by_category
from parser import parse_data, close_driver
import os
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
import time  # 시간 측정을 위한 모듈

# 데이터 저장 경로 설정
save_path = '../data/raw/article_data.csv'


def process_article(raw_html, url):
    return parse_data(raw_html, url)


if __name__ == "__main__":

    # 트렌드 키워드를 담은 CSV 파일에서 데이터 읽어오기
    trending_keywords = pd.read_csv("C:/Users/sng02/Desktop/CAPSTONE/crawling/data/raw/trending_KR_1d_20241107-2224.csv", encoding="utf-8-sig")
    categories = trending_keywords['트렌드'].head(50).tolist()  # 트렌드 컬럼의 상위 50개 키워드 리스트 추출

    # 실행 시간 측정 시작
    start_time = time.time()

    # 카테고리별로 데이터 크롤링 및 파싱
    raw_html_list, url_list = scrape_data_by_category(categories)

    if raw_html_list and url_list:
        all_data = []

        # 멀티스레딩을 사용하여 병렬 처리
        with ThreadPoolExecutor(max_workers=5) as executor:  # 최대 5개의 스레드로 병렬 처리
            results = executor.map(process_article, raw_html_list, url_list)

        all_data = list(results)

        # pandas DataFrame으로 변환
        df = pd.DataFrame(all_data)

        # CSV 파일로 저장
        df.to_csv(save_path, index=False, encoding='utf-8-sig')

        print(f"크롤링 결과가 {save_path}에 CSV 형식으로 저장되었습니다.")
    else:
        print("크롤링 실패 또는 유효한 데이터를 찾지 못했습니다.")

    # 크롤링이 끝나면 드라이버 종료
    close_driver()

    # 실행 시간 측정 종료 및 출력
    end_time = time.time()
    elapsed_time = end_time - start_time
    print(f"전체 실행 시간: {elapsed_time:.2f}초")
