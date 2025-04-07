import os
import pandas as pd
from collections import defaultdict, Counter
from konlpy.tag import Okt
import psycopg2
from datetime import datetime

class SemanticTextClassifier:
    def __init__(self, input_file, stopwords_file='../../data/raw/stopwords.txt', threshold=0.7, top_n=50):
        self.input_file = input_file
        self.threshold = threshold
        self.top_n = top_n
        self.okt = Okt()

        try:
            with open(stopwords_file, 'r', encoding='utf-8') as f:
                self.stopwords = set(line.strip() for line in f)
        except FileNotFoundError:
            print(f"불용어 파일을 찾을 수 없습니다: {stopwords_file}")
            self.stopwords = set()

    def _remove_josa_with_okt(self, text):
        tokens = self.okt.pos(text, norm=True, stem=True)
        # 불용어와 조사를 제거하고, 길이가 1인 단어도 제외
        meaningful_words = [
            word for word, pos in tokens
            if pos not in ['Josa', 'Punctuation']
            and word not in self.stopwords
            and len(word) > 1
        ]
        return meaningful_words


    def _calculate_word_frequencies(self, df):
        date_word_counts = defaultdict(Counter)

        for _, row in df.iterrows():
            date = row['date']
            if not isinstance(date, str) or len(date) < 10:
                print(f"날짜 형식 오류: {date}")
                continue

            title = row['title']
            words = self._remove_josa_with_okt(title)
            date_word_counts[date].update(words)

        result_list = []
        for date, word_counts in date_word_counts.items():
            for word, count in word_counts.most_common(self.top_n):
                result_list.append({"date": date, "word": word, "count": count})

        return result_list

    def process_and_send(self, date):
        """
            특정 날짜의 데이터만 처리하고 데이터베이스에 저장합니다.
            :param date: 처리할 날짜 (datetime 객체)
        """
        try:
            df = pd.read_csv(self.input_file, encoding='utf-8-sig')
        except FileNotFoundError:
            print(f"파일을 찾을 수 없습니다: {self.input_file}")
            return

        if 'title' not in df.columns or 'date' not in df.columns:
            print("CSV 파일에 'title' 또는 'date' 열이 없습니다.")
            return

        # target_date 문자열로 변환
        target_date_str = date.strftime('%Y-%m-%d')

        # target_date에 해당하는 데이터만 필터링
        filtered_df = df[df['date'] == target_date_str]

        if filtered_df.empty:
            print(f"{target_date_str} 날짜에 해당하는 데이터가 없습니다.")
            return

        word_frequencies = self._calculate_word_frequencies(df)
        self._save_to_database(word_frequencies)

    def _save_to_database(self, word_frequencies):
        try:
            conn = psycopg2.connect(
                host=os.getenv("DB_HOST"),
                database=os.getenv("DB_NAME"),
                user=os.getenv("DB_USER"),
                password=os.getenv("DB_PASSWORD"),
                port=os.getenv("DB_PORT")
            )
            cur = conn.cursor()

            rank = 1  # 순위 초기화
            for item in word_frequencies:
                # date 문자열을 DATE 타입으로 변환
                if isinstance(item["date"], str):
                    try:
                        item["date"] = datetime.strptime(item["date"], "%Y-%m-%d").date()
                    except ValueError:
                        print(f"날짜 변환 오류: {item['date']}")
                        continue

                cur.execute("""
                            INSERT INTO keyword_frequencies (date, keyword, frequency, rank)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT (date, keyword) DO UPDATE 
                            SET frequency = EXCLUDED.frequency, rank = EXCLUDED.rank;
                        """, (item["date"], item["word"], item["count"], rank))
                rank += 1
                if rank > self.top_n:
                    rank = 1 # 순위 초기화

            conn.commit()
            cur.close()
            conn.close()
            print("키워드 빈도수 데이터 RDB 저장 완료")

        except Exception as e:
            print(f"키워드 빈도수 데이터 RDB 저장 실패: {str(e)}")
