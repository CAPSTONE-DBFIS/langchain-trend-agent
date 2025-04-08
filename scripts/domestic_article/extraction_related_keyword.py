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

    for keyword_id, word, _ in top_keywords:
        if word not in related_keywords:
            continue

        for rank, (related_word, count) in enumerate(related_keywords[word], start=1):  # 순위 추가
            cur.execute(
                "INSERT INTO keyword_analysis (keyword_id, keyword, related_keyword, frequency, rank, date) VALUES (%s, %s, %s, %s, %s, %s)",
                (keyword_id, word, related_word, count, rank, date)  # rank 추가
            )

    conn.commit()
    cur.close()
    conn.close()


# 연관 검색어 분석 함수
def keyword_analysis(date, stopwords_file_path="../../data/raw/stopwords.txt"):
    stopwords = load_stopwords(stopwords_file_path)

    # 날짜를 문자열 형식으로 변환 (yyyy-MM-dd)
    if isinstance(date, datetime):
        date = date.strftime('%Y-%m-%d')

    top_keywords = load_top_keywords_from_db(date)
    if not top_keywords:
        print("해당 날짜에 대한 키워드가 존재하지 않습니다.")
        return [], {}

    related_keywords = {}

    for keyword_id, word, _ in top_keywords:
        print(f"\n=== 키워드 분석: {word} ===")

        # 영어 키워드는 소문자로 변환
        search_word = word.lower() if word.isascii() else word

        query_related = {
            "query": {
                "bool": {
                    "must": [
                        {
                            "bool": {
                                "should": [
                                    {"wildcard": {"title": f"*{search_word}*"}},
                                    {"wildcard": {"content": f"*{search_word}*"}}
                                ],
                                "minimum_should_match": 1
                            }
                        },
                        {
                            "range": {
                                "date": {
                                    "gte": date,
                                    "lte": date,
                                    "format": "yyyy-MM-dd"
                                }
                            }
                        }
                    ]
                }
            }
        }

        try:
            related_response = es.search(index=os.getenv("ELASTICSEARCH_INDEX_NAME"), body=query_related, size=1000)
            print(f"'{word}' 키워드 포함 문서 수: {len(related_response['hits']['hits'])}")
        except Exception as e:
            print(f"Elasticsearch Error: {e}")
            continue

        # 연관 키워드를 추출할 카운터 준비
        related_keywords_for_word = Counter()
        processed_documents = set()  # 이미 처리된 문서 추적

        for hit in related_response['hits']['hits']:
            doc_id = hit['_id']
            if doc_id in processed_documents:
                continue
            processed_documents.add(doc_id)

            # 제목에서 키워드 추출
            title = hit['_source'].get('title', "")

            extracted_keywords = extract_keywords(title, stopwords)

            # 각 문서에서 키워드가 한 번만 등장하는 것으로 카운트
            unique_keywords = set(extracted_keywords)  # 중복된 키워드를 제거하기 위해 set으로 변환
            for keyword in unique_keywords:
                related_keywords_for_word[keyword] += 1  # 해당 문서에서 키워드가 등장한 것으로 카운트

        # 자기 자신을 제외
        if word in related_keywords_for_word:
            del related_keywords_for_word[word]

        # 연관 키워드 상위 10개 추출
        related_keywords[word] = related_keywords_for_word.most_common(10)
        print(f"'{word}' 연관 키워드: {related_keywords[word]}")

    save_related_keywords_to_db(date, top_keywords, related_keywords)
    print("연관 키워드 RDB 저장 완료")

    return top_keywords, related_keywords

# print(keyword_analysis(date="2025-04-01"))
# print(keyword_analysis(date="2025-04-02"))
# print(keyword_analysis(date="2025-04-03"))
# print(keyword_analysis(date="2025-04-04"))
# print(keyword_analysis(date="2025-04-05"))
# print(keyword_analysis(date="2025-04-06"))
# print(keyword_analysis(date="2025-04-07"))