from elasticsearch import Elasticsearch
from collections import Counter
from konlpy.tag import Okt
import psycopg2
import os
from datetime import datetime
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

# Elasticsearch 클라이언트 생성
es = Elasticsearch(
    [{'host': os.getenv("ELASTICSEARCH_HOST"), 'port': int(os.getenv("ELASTICSEARCH_PORT")), 'scheme': 'http'}],
    basic_auth=(os.getenv("ELASTICSEARCH_USERNAME"), os.getenv("ELASTICSEARCH_PASSWORD"))
)

# 형태소 분석기 설정
okt = Okt()

# stopword 경로
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
STOPWORDS_PATH = os.path.join(BASE_DIR, "data", "raw", "stopwords.txt")


class CategoryRelatedKeywordExtractor:
    """국내 뉴스 기사의 카테고리별 상위 키워드에 대한 연관 키워드를 분석하는 클래스"""
    
    def __init__(self, stopwords_file=STOPWORDS_PATH, top_n=10):
        """
        초기화 메서드
        
        Args:
            stopwords_file: 불용어 목록 파일 경로
            top_n: 각 키워드마다 추출할 상위 연관 키워드 수
        """
        self.top_n = top_n
        self.okt = Okt()
        
        # 불용어 로드
        self.stopwords = self._load_stopwords(stopwords_file)
        
        # Elasticsearch 클라이언트 설정
        self.es = Elasticsearch(
            [{'host': os.getenv("ELASTICSEARCH_HOST"), 'port': int(os.getenv("ELASTICSEARCH_PORT")), 'scheme': 'http'}],
            basic_auth=(os.getenv("ELASTICSEARCH_USERNAME"), os.getenv("ELASTICSEARCH_PASSWORD"))
        )
        
        print("CategoryRelatedKeywordExtractor 초기화 완료")
    
    def _load_stopwords(self, file_path):
        """
        불용어 목록을 로드합니다.
        
        Args:
            file_path: 불용어 목록 파일 경로
            
        Returns:
            불용어 집합
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                stopwords = file.read().splitlines()
            return set(stopwords)
        except FileNotFoundError:
            print(f"불용어 파일을 찾을 수 없습니다: {file_path}")
            return set()
    
    def _extract_keywords(self, text):
        """
        텍스트에서 키워드를 추출합니다.
        
        Args:
            text: 키워드를 추출할 텍스트
            
        Returns:
            추출된 키워드 리스트
        """
        nouns = self.okt.nouns(text)
        return [noun for noun in nouns if noun not in self.stopwords and len(noun) > 1]
    
    def load_top_keywords_by_category(self, date, category):
        """
        PostgreSQL에서 특정 날짜, 특정 카테고리의 상위 10개 키워드를 불러옵니다.
        
        Args:
            date: 데이터를 불러올 날짜
            category: 불러올 카테고리
            
        Returns:
            상위 키워드 목록 [(id, keyword, frequency), ...]
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
            
            # 특정 카테고리의 상위 10개 키워드 조회 (id 포함)
            cur.execute("""
                SELECT id, keyword, frequency 
                FROM category_keyword_frequencies
                WHERE date = %s::date AND category = %s
                ORDER BY frequency DESC
                LIMIT 10;
            """, (date, category))
            
            top_keywords = cur.fetchall()
            cur.close()
            conn.close()
            
            print(f"{date} 날짜, {category} 카테고리 상위 10개 키워드 불러오기 완료")
            return top_keywords
            
        except Exception as e:
            print(f"DB 조회 오류: {str(e)}")
            return []
    
    def find_related_keywords(self, date, word):
        """
        특정 키워드의 연관 키워드를 추출합니다.
        
        Args:
            date: 데이터를 검색할 날짜
            word: 연관 키워드를 찾을 대상 단어
            
        Returns:
            연관 키워드 목록 [(keyword, frequency), ...]
        """
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
            related_response = self.es.search(index=os.getenv("ELASTICSEARCH_DOMESTIC_INDEX_NAME"), body=query_related, size=1000)
            print(f"'{word}' 키워드 포함 문서 수: {len(related_response['hits']['hits'])}")
        except Exception as e:
            print(f"Elasticsearch Error: {e}")
            return []
        
        # 연관 키워드를 추출할 카운터 준비
        related_keywords_counter = Counter()
        processed_documents = set()  # 이미 처리된 문서 추적
        
        for hit in related_response['hits']['hits']:
            doc_id = hit['_id']
            if doc_id in processed_documents:
                continue
            processed_documents.add(doc_id)
            
            # 제목에서 키워드 추출
            title = hit['_source'].get('title', "")
            
            extracted_keywords = self._extract_keywords(title)
            
            # 각 문서에서 키워드가 한 번만 등장하는 것으로 카운트
            unique_keywords = set(extracted_keywords)  # 중복된 키워드를 제거하기 위해 set으로 변환
            for keyword in unique_keywords:
                related_keywords_counter[keyword] += 1  # 해당 문서에서 키워드가 등장한 것으로 카운트
        
        # 자기 자신을 제외
        if word in related_keywords_counter:
            del related_keywords_counter[word]
        
        # 연관 키워드 상위 N개 추출
        return related_keywords_counter.most_common(self.top_n)
    
    def save_related_keywords_to_db(self, date, category, top_keywords, related_keywords):
        """
        연관 키워드를 PostgreSQL에 저장합니다.
        
        Args:
            date: 저장할 날짜
            category: 카테고리
            top_keywords: 상위 키워드 목록 [(id, keyword, frequency), ...]
            related_keywords: 연관 키워드 딕셔너리 {keyword: [(related_keyword, frequency), ...], ...}
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
                        INSERT INTO category_keyword_analysis 
                        (keyword_id, keyword, related_keyword, frequency, date, rank) 
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (keyword_id, related_keyword, date) DO UPDATE 
                        SET frequency = EXCLUDED.frequency, rank = EXCLUDED.rank;
                    """, (keyword_id, word, related_word, count, date, rank))
            
            conn.commit()
            cur.close()
            conn.close()
            print(f"{category} 카테고리 연관 키워드 저장 완료")
            
        except Exception as e:
            print(f"연관 키워드 저장 오류: {str(e)}")
    
    def analyze_category(self, date, category):
        """
        특정 날짜와 카테고리의 키워드에 대한 연관 키워드를 분석하고 저장합니다.
        
        Args:
            date: 분석할 날짜
            category: 분석할 카테고리
            
        Returns:
            top_keywords: 상위 키워드 목록 [(id, keyword, frequency), ...]
            related_keywords: 연관 키워드 딕셔너리 {keyword: [(related_keyword, frequency), ...], ...}
        """
        print(f"\n=== {date} 날짜, {category} 카테고리 연관 키워드 분석 시작 ===")
        
        # 해당 카테고리의 상위 키워드 불러오기
        top_keywords = self.load_top_keywords_by_category(date, category)
        if not top_keywords:
            print(f"{date} 날짜, {category} 카테고리에 대한 키워드가 존재하지 않습니다.")
            return [], {}
        
        # 각 키워드별 연관 키워드 분석
        related_keywords = {}
        for keyword_id, word, _ in top_keywords:
            print(f"\n=== 키워드 분석: {word} ===")
            related_keywords[word] = self.find_related_keywords(date, word)
            print(f"'{word}' 연관 키워드: {related_keywords[word]}")
        
        # 연관 키워드 DB 저장
        self.save_related_keywords_to_db(date, category, top_keywords, related_keywords)
        print(f"=== {date} 날짜, {category} 카테고리 연관 키워드 분석 완료 ===\n")
        
        return top_keywords, related_keywords
    
    def analyze_all_categories(self, date):
        """
        특정 날짜의 모든 카테고리에 대한 연관 키워드를 분석합니다.
        
        Args:
            date: 분석할 날짜
            
        Returns:
            results: 카테고리별 분석 결과 딕셔너리 {category: (top_keywords, related_keywords), ...}
        """
        # 데이터베이스에서 모든 카테고리 조회
        categories = self.get_categories_from_db()
        if not categories:
            print(f"{date} 날짜에 카테고리 데이터가 없습니다.")
            return {}
        
        results = {}
        for category in categories:
            top_keywords, related_keywords = self.analyze_category(date, category)
            results[category] = (top_keywords, related_keywords)
        
        return results
    
    def get_categories_from_db(self):
        """
        데이터베이스에서 모든 카테고리 목록을 가져옵니다.
        
        Returns:
            카테고리 목록
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
            
            cur.execute("SELECT DISTINCT category FROM category_keyword_frequencies")
            categories = [row[0] for row in cur.fetchall()]
            
            cur.close()
            conn.close()
            
            return categories
            
        except Exception as e:
            print(f"카테고리 목록 조회 실패: {str(e)}")
            return [] 