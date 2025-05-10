import os
import re
from datetime import datetime
from collections import Counter
from dotenv import load_dotenv
import psycopg2
from elasticsearch import Elasticsearch
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize

# 환경 변수 로드
load_dotenv()

# NLTK 데이터 다운로드 (처음 실행 시 필요)
try:
    nltk.data.find('corpora/stopwords')
except LookupError:
    nltk.download('stopwords')
    nltk.download('punkt')


class ForeignKeywordExtractor:
    """해외 뉴스 기사에서 키워드 빈도수를 추출하는 클래스"""

    def __init__(self):
        """Elasticsearch 및 PostgreSQL 연결 초기화"""
        # Elasticsearch 클라이언트 생성
        self.es = Elasticsearch(
            [{'host': os.getenv("ELASTICSEARCH_HOST"), 'port': int(os.getenv("ELASTICSEARCH_PORT")), 'scheme': 'http'}],
            basic_auth=(os.getenv("ELASTICSEARCH_USERNAME"), os.getenv("ELASTICSEARCH_PASSWORD"))
        )
        # 불용어 목록 로드
        self.stop_words = set(stopwords.words('english'))
        print("ForeignKeywordExtractor 초기화 완료")

    def extract_keywords(self, text):
        """
        텍스트에서 영어 키워드만 추출 (알파벳만 포함된 단어)
        불용어 제거 후 반환
        """
        if not text or not isinstance(text, str):
            return []

        # 텍스트 토큰화
        tokens = word_tokenize(text.lower())

        # 알파벳만 포함된 단어 필터링 및 불용어 제거
        words = [
            word for word in tokens
            if re.match(r'^[a-zA-Z]+$', word)  # 알파벳만 허용
               and word.lower() not in self.stop_words  # 불용어 제거
               and len(word) > 1  # 한 글자 단어 제거
        ]

        return words

    def get_articles_from_es(self, date):
        """
        Elasticsearch에서 특정 날짜의 해외 뉴스 기사 검색
        """
        query = {
            "query": {
                "term": {
                    "date": date
                }
            },
            "size": 10000  # 검색 결과 제한 (필요에 따라 조정)
        }

        try:
            response = self.es.search(
                index="foreign_news_article",
                body=query
            )

            print(f"{date} 날짜에 해당하는 기사 {len(response['hits']['hits'])}개 검색 완료")
            return response['hits']['hits']
        except Exception as e:
            print(f"Elasticsearch 검색 오류: {str(e)}")
            return []

    def calculate_keyword_frequencies(self, date):
        """
        특정 날짜의 기사에서 키워드 빈도수 계산
        """
        articles = self.get_articles_from_es(date)
        word_counter = Counter()

        for article in articles:
            title = article['_source'].get('title', '')
            words = self.extract_keywords(title)
            word_counter.update(words)

        # 상위 50개 키워드 추출
        top_keywords = word_counter.most_common(50)
        print(f"{date} 날짜 기사에서 상위 50개 키워드 추출 완료")

        return top_keywords

    def save_to_database(self, date, keywords):
        """
        키워드 빈도수를 PostgreSQL에 저장
        """
        if not keywords:
            print(f"{date} 날짜에 저장할 키워드가 없습니다.")
            return

        try:
            conn = psycopg2.connect(
                host=os.getenv("DB_HOST"),
                port=os.getenv("DB_PORT"),
                dbname=os.getenv("DB_NAME"),
                user=os.getenv("DB_USER"),
                password=os.getenv("DB_PASSWORD")
            )
            cur = conn.cursor()

            # 날짜 객체로 변환
            date_obj = datetime.strptime(date, "%Y-%m-%d").date() if isinstance(date, str) else date

            for rank, (word, count) in enumerate(keywords, start=1):
                # 기존 항목 확인
                cur.execute("""
                    SELECT id FROM foreign_keyword 
                    WHERE date = %s AND keyword = %s
                """, (date_obj, word))
                
                result = cur.fetchone()
                
                if result:
                    # 기존 항목 업데이트
                    cur.execute("""
                        UPDATE foreign_keyword 
                        SET frequency = %s, rank = %s
                        WHERE id = %s
                    """, (count, rank, result[0]))
                else:
                    # 새 항목 삽입
                    cur.execute("""
                        INSERT INTO foreign_keyword (date, keyword, frequency, rank)
                        VALUES (%s, %s, %s, %s)
                    """, (date_obj, word, count, rank))

            conn.commit()
            cur.close()
            conn.close()
            print(f"{date} 날짜 키워드 {len(keywords)}개 DB 저장 완료")

        except Exception as e:
            print(f"PostgreSQL 저장 오류: {str(e)}")

    def process_date(self, date):
        """
        특정 날짜의 키워드 추출 및 저장 처리
        """
        print(f"\n=== {date} 날짜 키워드 처리 시작 ===")
        keywords = self.calculate_keyword_frequencies(date)
        self.save_to_database(date, keywords)
        print(f"=== {date} 날짜 키워드 처리 완료 ===\n")
        return keywords


# 테스트 실행 코드
if __name__ == "__main__":
    extractor = ForeignKeywordExtractor()
    # 어제 날짜 기준으로 실행 (실제 사용 시 날짜 지정)
    date = datetime.now().strftime("%Y-%m-%d")
    extractor.process_date(date)
