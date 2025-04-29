import os
import json
from datetime import datetime
import time
from elasticsearch import Elasticsearch
from dotenv import load_dotenv

# 자체 모듈 임포트
from scraper_nyt import nyt_start
from scraper_techcrunch import techcrunch_start
from scraper_ars_technica import ars_technica_start
from scraper_zdnet import zdnet_start
from foreign_keyword_extractor import ForeignKeywordExtractor
from foreign_keyword_analyzer import ForeignKeywordAnalyzer

# 환경변수 로드
load_dotenv()

# Elasticsearch 클라이언트 초기화
es = Elasticsearch(
    [{'host': os.getenv("ELASTICSEARCH_HOST"), 'port': int(os.getenv("ELASTICSEARCH_PORT")), 'scheme': 'http'}],
    basic_auth=(os.getenv("ELASTICSEARCH_USERNAME"), os.getenv("ELASTICSEARCH_PASSWORD"))
)


def ensure_es_index_exists():
    """Elasticsearch 인덱스가 존재하는지 확인하고, 없으면 생성합니다."""
    if not es.indices.exists(index=os.getenv("ELASTICSEARCH_FOREIGN_INDEX_NAME")):
        # 인덱스 매핑 설정
        mappings = {
            "mappings": {
                "properties": {
                    "category": {"type": "keyword"},
                    "content": {"type": "text"},
                    "date": {"type": "date"},
                    "image_url": {"type": "text"},
                    "media_company": {"type": "keyword"},
                    "title": {"type": "text"},
                    "url": {"type": "text"}
                }
            }
        }
        # 인덱스 생성
        es.indices.create(index=os.getenv("ELASTICSEARCH_FOREIGN_INDEX_NAME"), body=mappings)
        print(f"Elasticsearch 인덱스 '{os.getenv("ELASTICSEARCH_FOREIGN_INDEX_NAME")}' 생성 완료")
    else:
        print(f"Elasticsearch 인덱스 '{os.getenv("ELASTICSEARCH_FOREIGN_INDEX_NAME")}' 확인 완료")


def save_to_elasticsearch(articles):
    """스크래핑한 기사 데이터를 Elasticsearch에 저장합니다."""
    if not articles:
        print("저장할 기사가 없습니다.")
        return 0

    # 인덱스 존재 여부 확인
    ensure_es_index_exists()

    # URL 기준으로 중복 확인을 위한 기존 URL 조회
    existing_urls = set()

    try:
        # 이미 존재하는 URL 목록 가져오기
        query = {
            "size": 10000,
            "_source": ["url"],
            "query": {"match_all": {}}
        }
        response = es.search(index=os.getenv("ELASTICSEARCH_FOREIGN_INDEX_NAME"), body=query)

        for hit in response["hits"]["hits"]:
            if "url" in hit["_source"]:
                existing_urls.add(hit["_source"]["url"])

        print(f"이미 저장된 URL 수: {len(existing_urls)}")
    except Exception as e:
        print(f"[예외] 기존 URL 조회 오류: {str(e)}")

    # 새 기사만 저장
    success_count = 0
    skipped_count = 0

    for article in articles:
        try:
            # URL이 이미 있는지 확인 (중복 기사)
            if article["url"] in existing_urls:
                skipped_count += 1
                continue

            # 필수 필드 확인 (제목, 본문, 이미지가 모두 있어야 함)
            if (not article.get("title") or
                    not article.get("content") or
                    not article.get("image_url") or
                    article.get("title") == "제목 없음" or
                    article.get("content") == "본문 없음"):
                print(f"[예외] 필수 정보 누락으로 기사 제외: {article.get('title', '제목 없음')}")
                skipped_count += 1
                continue

            # 날짜 형식 정규화 (YYYY-MM-DD)
            if "date" in article and article["date"]:
                # 이미 적절한 형식인지 확인
                if not isinstance(article["date"], str) or not article["date"].strip():
                    article["date"] = datetime.now().strftime("%Y-%m-%d")
            else:
                article["date"] = datetime.now().strftime("%Y-%m-%d")

            # Elasticsearch에 저장
            es.index(index=os.getenv("ELASTICSEARCH_FOREIGN_INDEX_NAME"), document=article)
            success_count += 1

        except Exception as e:
            print(f"[예외] 기사 저장 오류: {article.get('url', '알 수 없는 URL')} - {str(e)}")
            skipped_count += 1

    print(f"ES 저장 완료: {success_count}개 기사 저장, {skipped_count}개 건너뜀")
    return success_count


def main():
    """메인 함수: 해외 기사 스크래핑 및 키워드 분석을 실행합니다."""
    print(f"===== 해외 기사 스크래핑 시작 ({datetime.now().strftime('%Y-%m-%d')}) =====")

    # 스크래핑할 페이지 수 설정
    page_count = 15
    all_articles = []

    # 1. NYT 기사 스크래핑
    print("\n----- New York Times 스크래핑 시작 -----")
    nyt_articles = nyt_start(page_count)
    all_articles.extend(nyt_articles)
    print(f"NYT 스크래핑 완료: {len(nyt_articles)}개 기사")

    # 2. TechCrunch 기사 스크래핑
    print("\n----- TechCrunch 스크래핑 시작 -----")
    techcrunch_articles = techcrunch_start(page_count)
    all_articles.extend(techcrunch_articles)
    print(f"TechCrunch 스크래핑 완료: {len(techcrunch_articles)}개 기사")

    # 3. Ars Technica 기사 스크래핑
    print("\n----- Ars Technica 스크래핑 시작 -----")
    ars_technica_articles = ars_technica_start(page_count)
    all_articles.extend(ars_technica_articles)
    print(f"Ars Technica 스크래핑 완료: {len(ars_technica_articles)}개 기사")

    # 4. ZDNET 기사 스크래핑
    # print("\n----- ZDNET 스크래핑 시작 -----")
    # zdnet_articles = zdnet_start(page_count)
    # all_articles.extend(zdnet_articles)
    # print(f"ZDNET 스크래핑 완료: {len(zdnet_articles)}개 기사")

    # 5. 전체 스크래핑 결과 요약
    print(f"\n총 {len(all_articles)}개 기사 스크래핑 완료")

    # 6. Elasticsearch에 저장
    print("\n----- Elasticsearch 저장 시작 -----")
    saved_count = save_to_elasticsearch(all_articles)

    # 오늘 날짜 가져오기
    today = datetime.now().strftime("%Y-%m-%d")

    # 7. 키워드 빈도수 추출
    print("\n----- 키워드 빈도수 추출 시작 -----")
    try:
        keyword_extractor = ForeignKeywordExtractor()
        keywords = keyword_extractor.process_date(today)
        print(f"키워드 빈도수 추출 완료: {len(keywords)}개 키워드")
    except Exception as e:
        print(f"[예외] 키워드 빈도수 추출 오류: {str(e)}")

    # 8. 연관 키워드 분석
    print("\n----- 연관 키워드 분석 시작 -----")
    try:
        keyword_analyzer = ForeignKeywordAnalyzer()
        keyword_analyzer.analyze_date(today)
        print("연관 키워드 분석 완료")
    except Exception as e:
        print(f"[예외] 연관 키워드 분석 오류: {str(e)}")

    print(f"\n===== 해외 기사 스크래핑 및 분석 완료 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) =====")


if __name__ == "__main__":
    main()
