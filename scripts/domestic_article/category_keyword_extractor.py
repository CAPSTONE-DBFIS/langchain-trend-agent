import os
import pandas as pd
from collections import defaultdict, Counter
from konlpy.tag import Okt
import psycopg2
from datetime import datetime
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

# 불용어 경로
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
STOPWORDS_PATH = os.path.join(BASE_DIR, "data", "raw", "stopwords.txt")

class CategoryKeywordExtractor:
    """국내 뉴스 기사에서 카테고리별 키워드 빈도수를 추출하는 클래스"""
    
    def __init__(self, input_file, stopwords_file=STOPWORDS_PATH, top_n_per_category=10):
        """
        초기화 메서드
        
        Args:
            input_file: 분석할 CSV 파일 경로
            stopwords_file: 불용어 목록 파일 경로
            top_n_per_category: 각 카테고리별로 추출할 상위 키워드 수
        """
        self.input_file = input_file
        self.top_n_per_category = top_n_per_category
        self.okt = Okt()
        
        try:
            with open(stopwords_file, 'r', encoding='utf-8') as f:
                self.stopwords = set(line.strip() for line in f)
        except FileNotFoundError:
            print(f"불용어 파일을 찾을 수 없습니다: {stopwords_file}")
            self.stopwords = set()
    
    def _extract_keywords(self, text):
        """
        텍스트에서 키워드를 추출합니다.
        
        Args:
            text: 키워드를 추출할 텍스트
            
        Returns:
            추출된 키워드 리스트
        """
        tokens = self.okt.pos(text, norm=True, stem=True)
        # 불용어와 조사를 제거하고, 길이가 1인 단어도 제외
        meaningful_words = [
            word for word, pos in tokens
            if pos not in ['Josa', 'Punctuation']
            and word not in self.stopwords
            and len(word) > 1
        ]
        return meaningful_words
    
    def _calculate_word_frequencies_by_category(self, df, date):
        """
        데이터프레임에서 카테고리별 키워드 빈도수를 계산합니다.
        
        Args:
            df: 분석할 데이터프레임
            date: 분석할 날짜
            
        Returns:
            카테고리별 키워드 빈도수를 담은 리스트
        """
        # 카테고리별 단어 빈도수를 저장할 사전
        category_word_counts = defaultdict(Counter)
        
        # 필터링된 데이터프레임의 각 행을 순회하며 키워드 추출
        for _, row in df.iterrows():
            category = row.get('category', '기타')  # 카테고리가 없으면 '기타'로 설정
            title = row.get('title', '')
            
            if not title:
                continue
                
            # 제목에서 키워드 추출
            keywords = self._extract_keywords(title)
            
            # 해당 카테고리의 카운터에 키워드 추가
            category_word_counts[category].update(keywords)
        
        # 결과 리스트 생성
        result_list = []
        
        # 각 카테고리별로 상위 N개 키워드 추출
        for category, word_counts in category_word_counts.items():
            for word, count in word_counts.most_common(self.top_n_per_category):
                result_list.append({
                    "date": date,
                    "word": word,
                    "count": count,
                    "category": category
                })
        
        return result_list
    
    def process_and_save(self, date):
        """
        특정 날짜의 데이터를 처리하고 데이터베이스에 저장합니다.
        
        Args:
            date: 처리할 날짜 (datetime 객체)
        """
        try:
            df = pd.read_csv(self.input_file, encoding='utf-8-sig')
        except FileNotFoundError:
            print(f"파일을 찾을 수 없습니다: {self.input_file}")
            return
        
        # 필수 컬럼 확인
        required_columns = ['title', 'date', 'category']
        for col in required_columns:
            if col not in df.columns:
                print(f"CSV 파일에 '{col}' 열이 없습니다.")
                return
        
        # target_date 문자열로 변환
        target_date_str = date.strftime('%Y-%m-%d')
        
        # target_date에 해당하는 데이터만 필터링
        filtered_df = df[df['date'] == target_date_str]
        
        if filtered_df.empty:
            print(f"{target_date_str} 날짜에 해당하는 데이터가 없습니다.")
            return
        
        # 카테고리별 단어 빈도수 계산
        word_frequencies = self._calculate_word_frequencies_by_category(filtered_df, date)
        
        # 데이터베이스에 저장
        self._save_to_database(word_frequencies)
        
        return word_frequencies
    
    def _save_to_database(self, word_frequencies):
        """
        키워드 빈도수를 데이터베이스에 저장합니다.
        
        Args:
            word_frequencies: 저장할 키워드 빈도수 정보를 담은 리스트
        """
        if not word_frequencies:
            print("저장할 키워드 데이터가 없습니다.")
            return
            
        try:
            conn = psycopg2.connect(
                host=os.getenv("DB_HOST"),
                database=os.getenv("DB_NAME"),
                user=os.getenv("DB_USER"),
                password=os.getenv("DB_PASSWORD"),
                port=os.getenv("DB_PORT")
            )
            cur = conn.cursor()
            
            # 카테고리-날짜별 순위 매기기 위한 사전
            category_rank = defaultdict(int)
            
            for item in word_frequencies:
                # date 문자열을 DATE 타입으로 변환
                if isinstance(item["date"], str):
                    try:
                        item["date"] = datetime.strptime(item["date"], "%Y-%m-%d").date()
                    except ValueError:
                        print(f"날짜 변환 오류: {item['date']}")
                        continue
                
                # 복합 키 생성 (날짜+카테고리)
                category_date_key = f"{item['date']}_{item['category']}"
                
                # 해당 카테고리의 순위 증가
                category_rank[category_date_key] += 1
                
                # 데이터베이스에 저장
                cur.execute("""
                    INSERT INTO category_keyword_frequencies 
                    (date, keyword, frequency, category) 
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (date, keyword, category) DO UPDATE 
                    SET frequency = EXCLUDED.frequency;
                """, (item["date"], item["word"], item["count"], item["category"]))
            
            conn.commit()
            cur.close()
            conn.close()
            print("카테고리별 키워드 빈도수 데이터 RDB 저장 완료")
            
        except Exception as e:
            print(f"카테고리별 키워드 빈도수 데이터 RDB 저장 실패: {str(e)}")
            
    def get_categories_from_db(self):
        """
        데이터베이스에서 모든 카테고리 목록을 가져옵니다.
        
        Returns:
            카테고리 목록
        """
        try:
            conn = psycopg2.connect(
                host=os.getenv("DB_HOST"),
                database=os.getenv("DB_NAME"),
                user=os.getenv("DB_USER"),
                password=os.getenv("DB_PASSWORD"),
                port=os.getenv("DB_PORT")
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