import os
import pandas as pd
import requests
from collections import defaultdict, Counter
from konlpy.tag import Okt
from datetime import datetime

class SemanticTextClassifier:
    def __init__(self, input_file, output_dir, flask_server_url, stopwords_file='../../data/raw/stopwords.txt', threshold=0.7, top_n=10):
        self.input_file = input_file
        self.output_dir = output_dir
        self.threshold = threshold
        self.top_n = top_n
        self.flask_server_url = flask_server_url
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

    def _convert_date_format(self, date_str):
        try:
            date_obj = datetime.strptime(date_str.strip()[:10], "%Y.%m.%d")
            return date_obj.strftime("%Y-%m-%d")
        except ValueError:
            print(f"❌ 잘못된 날짜 형식: {date_str}")
            return None

    def _calculate_word_frequencies(self, df):
        date_word_counts = defaultdict(Counter)

        for _, row in df.iterrows():
            raw_date = row['date']
            date = self._convert_date_format(raw_date)
            if date is None:
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
        self._send_to_flask_server(word_frequencies)

    def _send_to_flask_server(self, word_frequencies):
        response = requests.post(f"{self.flask_server_url}/api/word_frequencies/upload", json=word_frequencies)

        if response.status_code == 201:
            print("✅ 데이터가 Flask 서버로 성공적으로 전송되었습니다.")
        else:
            print(f"❌ 전송 실패: {response.status_code}, {response.json()}")

if __name__ == "__main__":
    classifier = SemanticTextClassifier(
        input_file='../../data/raw/article_data.csv',
        output_dir='../../data/processed/',
        flask_server_url="http://localhost:8080",
        threshold=0.7,
        top_n=50
    )
    classifier.process_and_send()
