from elasticsearch import Elasticsearch
from collections import Counter
from konlpy.tag import Okt
import psycopg2
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Elasticsearch 연결 설정
es = Elasticsearch(
    [{'host': os.getenv("ELASTICSEARCH_HOST"), 'port': int(os.getenv("ELASTICSEARCH_PORT")), 'scheme': 'http'}])

# 형태소 분석기 설정
okt = Okt()


# stopwords.txt에서 불용어 불러오기
def load_stopwords(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        stopwords = file.read().splitlines()
    return set(stopwords)


# 텍스트에서 명사만 추출하는 함수
def extract_keywords(text, stopwords):
    nouns = okt.nouns(text)
    return [noun for noun in nouns if noun not in stopwords and len(noun) > 1]


# PostgreSQL에서 상위 10개의 키워드를 불러오는 함수
def load_top_keywords_from_db(date):
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD")
    )
    cur = conn.cursor()

    # 날짜 타입이 datetime.date라면 문자열로 변환
    if isinstance(date, datetime):
        date = date.strftime('%Y-%m-%d')

    # 상위 10개의 키워드 불러오기 (id 포함)
    cur.execute("""
        SELECT id, keyword, frequency FROM keyword_frequencies
        WHERE date = %s::date
        ORDER BY frequency DESC
        LIMIT 10;
    """, (date,))

    top_keywords = cur.fetchall()
    cur.close()
    conn.close()

    return top_keywords


# PostgreSQL에 연관 키워드 저장 (keyword_id 사용)
def save_related_keywords_to_db(date, top_keywords, related_keywords):
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD")
    )
    cur = conn.cursor()

    for keyword_id, word, _ in top_keywords:  # keyword_id 추가됨
        for related_word, count in related_keywords[word]:
            cur.execute(
                "INSERT INTO keyword_analysis (keyword_id, keyword, related_keyword, frequency, date) VALUES (%s, %s, %s, %s, %s)",
                (keyword_id, word, related_word, count, date)
            )

    conn.commit()
    cur.close()
    conn.close()


# 연관 검색어 분석 함수
def keyword_analysis(date, stopwords_file_path="../../data/raw/stopwords.txt"):
    stopwords = load_stopwords(stopwords_file_path)

    # PostgreSQL에서 상위 10개의 키워드 로드
    top_keywords = load_top_keywords_from_db(date)
    if not top_keywords:
        print("해당 날짜에 대한 키워드 데이터가 없습니다.")
        return [], {}

    related_keywords = {}

    for keyword_id, word, _ in top_keywords:
        query_related = {
            "query": {
                "bool": {
                    "must": [
                        {
                            "match": {
                                "content": word
                            }
                        },
                        {
                            "range": {
                                "date": {
                                    "gte": date,
                                    "lte": date
                                }
                            }
                        }
                    ]
                }
            }
        }

        # Elasticsearch에서 해당 키워드가 포함된 문서 검색
        related_response = es.search(index=os.getenv("ELASTICSEARCH_INDEX_NAME"), body=query_related, size=1000)

        related_keywords_for_word = Counter()
        processed_documents = set()  # 처리한 문서 ID를 기록

        for hit in related_response['hits']['hits']:
            doc_id = hit['_id']  # Elasticsearch에서 문서 ID를 가져옴

            # 이미 처리한 문서라면 건너뛰기
            if doc_id in processed_documents:
                continue

            processed_documents.add(doc_id)  # 문서 ID 기록

            content = hit['_source']['content']
            related_keywords_for_word.update(extract_keywords(content, stopwords))

        # 검색 키워드 자신을 제거
        if word in related_keywords_for_word:
            del related_keywords_for_word[word]

        # 관련 키워드 상위 10개 저장
        related_keywords[word] = related_keywords_for_word.most_common(10)

    # RDB에 저장
    save_related_keywords_to_db(date, top_keywords, related_keywords)
    print("연관 키워드 RDB 저장 완료")

    return top_keywords, related_keywords

# # 예시 실행
# keyword_analysis(date=datetime.strptime("20250401", "%Y%m%d"))