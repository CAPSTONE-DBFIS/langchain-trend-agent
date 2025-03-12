import os
import json
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
        self.okt = Okt()  # Initialize Okt

        # Load stopwords from file
        try:
            with open(stopwords_file, 'r', encoding='utf-8') as f:
                self.stopwords = set(line.strip() for line in f)
        except FileNotFoundError:
            print(f"불용어 파일을 찾을 수 없습니다: {stopwords_file}")
            self.stopwords = set()

    def _remove_josa_with_okt(self, text):
        """Use Okt to remove particles (조사) and extract meaningful words."""
        tokens = self.okt.pos(text, norm=True, stem=True)
        meaningful_words = [word for word, pos in tokens if pos not in ['Josa', 'Punctuation'] and word not in self.stopwords]
        return meaningful_words

    def _convert_date_format(self, date_str):
        """날짜 문자열을 YYYY.MM.DD. 형식에서 YYYY-MM-DD로 변환"""
        try:
            # 날짜만 추출하여 변환 (시간 정보 제외)
            date_obj = datetime.strptime(date_str.strip()[:10], "%Y.%m.%d")
            return date_obj.strftime("%Y-%m-%d")  # YYYY-MM-DD 형식으로 변환
        except ValueError:
            print(f"❌ 잘못된 날짜 형식: {date_str}")
            return None

    def _calculate_word_frequencies(self, df):
        """Calculates word frequencies grouped by date, keeping top N words per day."""
        date_word_counts = defaultdict(Counter)

        for _, row in df.iterrows():
            raw_date = row['date']
            date = self._convert_date_format(raw_date)  # 날짜 변환 적용
            if date is None:
                continue  # 날짜 변환 실패 시 해당 행 무시

            title = row['title']
            words = self._remove_josa_with_okt(title)
            date_word_counts[date].update(words)

        # 날짜별 상위 N개의 단어만 유지
        top_n_date_word_counts = {}
        for date, word_counts in date_word_counts.items():
            top_n_words = dict(word_counts.most_common(self.top_n))  # 상위 10개 단어 선택
            top_n_date_word_counts[date] = top_n_words

        return top_n_date_word_counts

    def process_and_send(self):
        """Processes the input file and sends results to Flask server."""
        # Read input CSV
        try:
            df = pd.read_csv(self.input_file, encoding='utf-8-sig')
        except FileNotFoundError:
            print(f"파일을 찾을 수 없습니다: {self.input_file}")
            return

        if 'title' not in df.columns or 'date' not in df.columns:
            print("CSV 파일에 'title' 또는 'date' 열이 없습니다.")
            return

        # 날짜별 단어 빈도 계산 (상위 10개 단어만 저장)
        date_word_frequencies = self._calculate_word_frequencies(df)

        # 데이터를 Flask 서버로 전송
        self._send_to_flask_server(date_word_frequencies)

    def _send_to_flask_server(self, date_word_frequencies):
        """Sends processed data to Flask server via HTTP POST request."""
        data = [{"date": date, "word_counts": word_counts} for date, word_counts in date_word_frequencies.items()]

        response = requests.post(f"{self.flask_server_url}/api/word_frequencies/upload", json=data)

        if response.status_code == 201:
            print("✅ 데이터가 Flask 서버로 성공적으로 전송되었습니다.")
        else:
            print(f"❌ 전송 실패: {response.status_code}, {response.json()}")

# Example usage
if __name__ == "__main__":
    classifier = SemanticTextClassifier(
        input_file='../../data/raw/article_data.csv',
        output_dir='../../data/processed/',
        flask_server_url="http://localhost:8080",
        threshold=0.7,
        top_n=10  # 날짜별 상위 10개 단어만 저장
    )
    classifier.process_and_send()
