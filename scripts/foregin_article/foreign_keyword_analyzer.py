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

class ForeignKeywordAnalyzer:
    """해외 뉴스 기사의 상위 키워드에 대한 연관 키워드를 분석하는 클래스"""
    
    def __init__(self):
        """Elasticsearch 및 PostgreSQL 연결 초기화"""
        # Elasticsearch 클라이언트 생성
        self.es = Elasticsearch(
            [{'host': os.getenv("ELASTICSEARCH_HOST"), 'port': int(os.getenv("ELASTICSEARCH_PORT")), 'scheme': 'http'}],
            basic_auth=(os.getenv("ELASTICSEARCH_USERNAME"), os.getenv("ELASTICSEARCH_PASSWORD"))
        )
        # 불용어 목록 로드
        self.stop_words = set(stopwords.words('english'))
        print("ForeignKeywordAnalyzer 초기화 완료")

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

    def load_top_keywords_from_db(self, date):
        """
        PostgreSQL에서 특정 날짜의 상위 10개 키워드 불러오기
        """
        try:
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
            
            # 상위 10개 키워드 조회 (id 포함)
            cur.execute("""
                SELECT id, keyword, frequency 
                FROM foreign_keyword
                WHERE date = %s::date
                ORDER BY frequency DESC
                LIMIT 10;
            """, (date,))
            
            top_keywords = cur.fetchall()
            cur.close()
            conn.close()
            
            print(f"{date} 날짜 상위 10개 키워드 불러오기 완료")
            return top_keywords
            
        except Exception as e:
            print(f"DB 조회 오류: {str(e)}")
            return []

    def find_related_keywords(self, date, keyword):
        """
        특정 키워드와 관련된 키워드 추출
        """
        # 키워드 소문자 변환
        search_word = keyword.lower()
        
        # Elasticsearch 쿼리 구성
        query = {
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
                            "term": {
                                "date": date
                            }
                        }
                    ]
                }
            },
            "size": 1000
        }
        
        try:
            response = self.es.search(
                index="foreign_news_article",
                body=query
            )
            
            hits = response['hits']['hits']
            print(f"'{keyword}' 키워드 관련 기사 {len(hits)}개 검색 완료")
            
            # 연관 키워드 카운터 초기화
            related_keywords_counter = Counter()
            processed_documents = set()  # 이미 처리된 문서 추적
            
            for hit in hits:
                doc_id = hit['_id']
                if doc_id in processed_documents:
                    continue
                processed_documents.add(doc_id)
                
                # 제목에서 키워드 추출
                title = hit['_source'].get('title', '')
                extracted_keywords = self.extract_keywords(title)
                
                # 중복 키워드 제거 (각 문서에서 같은 단어는 한 번만 카운트)
                unique_keywords = set(extracted_keywords)
                
                # 자기 자신 제외
                if search_word in unique_keywords:
                    unique_keywords.remove(search_word)
                
                # 연관 키워드 카운트 업데이트
                for word in unique_keywords:
                    related_keywords_counter[word] += 1
            
            # 상위 10개 연관 키워드 반환
            top_related = related_keywords_counter.most_common(10)
            print(f"'{keyword}' 연관 키워드 상위 10개 추출 완료")
            
            return top_related
            
        except Exception as e:
            print(f"Elasticsearch 검색 오류: {str(e)}")
            return []

    def save_related_keywords_to_db(self, date, top_keywords, related_keywords):
        """
        연관 키워드를 PostgreSQL에 저장
        """
        try:
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
                
            for keyword_id, word, _ in top_keywords:
                if word not in related_keywords:
                    continue
                    
                for rank, (related_word, count) in enumerate(related_keywords[word], start=1):
                    cur.execute("""
                        INSERT INTO foreign_keyword_analysis (keyword_id, keyword, related_keyword, frequency, rank, date)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (keyword_id, related_keyword, date) DO UPDATE
                        SET frequency = EXCLUDED.frequency, rank = EXCLUDED.rank;
                    """, (keyword_id, word, related_word, count, rank, date))
            
            conn.commit()
            cur.close()
            conn.close()
            print("연관 키워드 DB 저장 완료")
            
        except Exception as e:
            print(f"DB 저장 오류: {str(e)}")

    def analyze_date(self, date):
        """
        특정 날짜의 키워드 연관 분석 및 저장 처리
        """
        print(f"\n=== {date} 날짜 연관 키워드 분석 시작 ===")
        
        # 상위 10개 키워드 불러오기
        top_keywords = self.load_top_keywords_from_db(date)
        if not top_keywords:
            print(f"{date} 날짜에 대한 키워드가 존재하지 않습니다.")
            return
        
        # 각 키워드별 연관 키워드 분석
        related_keywords = {}
        for keyword_id, word, _ in top_keywords:
            print(f"\n=== 키워드 분석: {word} ===")
            related_keywords[word] = self.find_related_keywords(date, word)
            
        # 연관 키워드 DB 저장
        self.save_related_keywords_to_db(date, top_keywords, related_keywords)
        print(f"=== {date} 날짜 연관 키워드 분석 완료 ===\n")
        
        return top_keywords, related_keywords

# 테스트 실행 코드
if __name__ == "__main__":
    analyzer = ForeignKeywordAnalyzer()
    # 어제 날짜 기준으로 실행 (실제 사용 시 날짜 지정)
    date = datetime.now().strftime("%Y-%m-%d")
    analyzer.analyze_date(date) 