from scraper import scrape_data_by_category
from parser import parse_data, close_driver
from classification import SemanticTextClassifier
import pandas as pd
import os
import requests
from concurrent.futures import ThreadPoolExecutor
import time

# 데이터 경로 설정
raw_save_path = '../../data/raw/article_data.csv'
processed_dir = '../../data/processed/'

# Flask 서버 URL
FLASK_SERVER_URL = "http://127.0.0.1:5432/upload"

def process_article(raw_html, url):
    return parse_data(raw_html, url)

# Flask 서버로 데이터 전송
def send_to_server(data):
    response = requests.post(FLASK_SERVER_URL, json=data)
    if response.status_code == 200:
        print("데이터가 성공적으로 전송되었습니다.")
    else:
        print(f"서버 응답 오류: {response.status_code}, {response.text}")

if __name__ == "__main__":
    # 트렌드 키워드를 담은 CSV 파일에서 데이터 읽어오기
    df = pd.read_csv("../../data/raw/it_companies_and_trends.csv", encoding="utf-8-sig")
    categories = pd.concat([df['Competitors'], df['IT Trends']]).dropna().unique().tolist()

    # 실행 시간 측정 시작
    start_time = time.time()

    # 카테고리별로 데이터 크롤링 및 파싱
    raw_html_list, url_list = scrape_data_by_category(categories)

    if raw_html_list and url_list:
        all_data = []

        # 순차적으로 URL과 HTML을 처리
        for raw_html, url in zip(raw_html_list, url_list):
            result = process_article(raw_html, url)
            all_data.append(result)

        # 데이터프레임으로 변환
        df = pd.DataFrame(all_data)

        # 중복 제거 (title과 url 기준)
        df = df.drop_duplicates(subset=['title', 'url'], keep='first')

        # 중복 제거 후 데이터 저장
        df.to_csv(raw_save_path, index=False, encoding='utf-8-sig')
        print(f"크롤링 결과가 {raw_save_path}에 저장되었습니다.")
    else:
        print("크롤링 실패 또는 유효한 데이터를 찾지 못했습니다.")

    # 크롤링이 끝나면 드라이버 종료
    close_driver()

    classifier = SemanticTextClassifier(
        input_file='../../data/raw/article_data.csv',
        output_dir='../../data/processed/',
        threshold=0.7
    )
    classifier.process_and_save()

    # 데이터 전송
    # if all_data:
    #    send_to_server(all_data)

    # 실행 시간 출력
    end_time = time.time()
    print(f"전체 실행 시간: {end_time - start_time:.2f}초")
