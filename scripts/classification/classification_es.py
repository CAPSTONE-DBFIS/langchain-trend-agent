from elasticsearch import Elasticsearch
from collections import Counter
from konlpy.tag import Okt
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

# Elasticsearch 연결 설정
es = Elasticsearch(
    [{'host': os.getenv("ELASTICSEARCH_HOST"), 'port': int(os.getenv("ELASTICSEARCH_PORT")), 'scheme': 'http'}])

# 형태소 분석기 설정
okt = Okt()

# stopwords.txt에서 불필요한 단어들 불러오기
def load_stopwords(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        stopwords = file.read().splitlines()  # 파일에서 한 줄씩 읽어 리스트로 반환
    return set(stopwords)

# 텍스트에서 명사만 추출하는 함수
def extract_keywords(text, stopwords):
    nouns = okt.nouns(text)
    # 불필요한 단어들 필터링
    return [noun for noun in nouns if noun not in stopwords]

# PostgreSQL에 키워드 및 관련 키워드 저장
def save_keywords_to_db(date, top_keywords, related_keywords):
    # PostgreSQL 연결 설정
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD")
    )
    cur = conn.cursor()

    # 키워드와 관련된 키워드 저장
    for word, _ in top_keywords:
        for related_word, count in related_keywords[word]:
            cur.execute(
                "INSERT INTO keyword_analysis (keyword, related_keyword, frequency, date) VALUES (%s, %s, %s, %s)",
                (word, related_word, count, date)  # 날짜와 함께 저장
            )

    conn.commit()
    cur.close()
    conn.close()

# 키워드 분석 함수
def keyword_analysis(date, stopwords_file_path):
    stopwords = load_stopwords(stopwords_file_path)
    query = {
        "query": {
            "match": {
                "date": date  # 해당 날짜의 문서 검색
            }
        }
    }

    # 해당 날짜의 기사들을 가져오기
    response = es.search(index=os.getenv("ELASTICSEARCH_INDEX_NAME"), body=query, size=1000)

    title_keywords = []
    # 제목에서 명사 추출
    for hit in response['hits']['hits']:
        title = hit['_source']['title']
        title_keywords.extend(extract_keywords(title, stopwords))

    # 키워드 빈도 계산
    keyword_count = Counter(title_keywords)
    top_keywords = keyword_count.most_common(10)

    # 관련 키워드 추출
    related_keywords = {}

    for word, _ in top_keywords:
        query_related = {
            "query": {
                "match_phrase": {
                    "content": word  # 해당 키워드를 포함한 다른 문서 검색
                }
            }
        }

        related_response = es.search(index=os.getenv("ELASTICSEARCH_INDEX_NAME"), body=query_related)

        related_keywords_for_word = Counter()
        for hit in related_response['hits']['hits']:
            content = hit['_source']['content']
            related_keywords_for_word.update(extract_keywords(content, stopwords))

        # 관련 키워드 상위 10개
        related_keywords[word] = related_keywords_for_word.most_common(10)

    # RDB에 저장
    save_keywords_to_db(date, top_keywords, related_keywords)

    return top_keywords, related_keywords