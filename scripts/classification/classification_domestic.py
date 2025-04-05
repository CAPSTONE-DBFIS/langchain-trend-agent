import os
import pandas as pd
from collections import defaultdict, Counter
from konlpy.tag import Okt
import psycopg2

class SemanticTextClassifier:
    def __init__(self, input_file, stopwords_file='../../data/raw/stopwords.txt', threshold=0.7, top_n=10):
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

    def process_and_send(self):
        try:
            df = pd.read_csv(self.input_file, encoding='utf-8-sig')
        except FileNotFoundError:
            print(f"파일을 찾을 수 없습니다: {self.input_file}")
            return

        if 'title' not in df.columns or 'date' not in df.columns:
            print("CSV 파일에 'title' 또는 'date' 열이 없습니다.")
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

            for item in word_frequencies:
                cur.execute("""
                    INSERT INTO word_frequencies (date, word, count)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (date, word) DO UPDATE SET count = EXCLUDED.count;
                """, (item["date"], item["word"], item["count"]))

            conn.commit()
            cur.close()
            conn.close()
            print("DB 저장 완료")
        except Exception as e:
            print(f"DB 저장 실패: {str(e)}")

# if __name__ == "__main__":
#     classifier = SemanticTextClassifier(
#         input_file='../../data/raw/article_data.csv',
#         output_dir='../../data/processed/',
#         flask_server_url="http://localhost:8080",
#         threshold=0.7,
#         top_n=50
#     )
#     classifier.process_and_send()
