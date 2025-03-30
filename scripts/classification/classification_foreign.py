import pandas as pd
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from collections import defaultdict, Counter
from datetime import datetime
import requests
import re

# nltk 리소스 다운로드
nltk.download('stopwords')
nltk.download('punkt')
nltk.download('punkt_tab')

# 영어 불용어 집합 생성
stop_words = set(stopwords.words('english'))

class EnglishKeywordExtractor:
    def __init__(self, input_file, flask_server_url, top_n=10):
        """
        초기화 함수
        :param input_file: 분석할 CSV 파일 경로 (techcrunch 형식, 'title' 및 'date' 컬럼 필요)
        :param flask_server_url: flask 서버 URL (예: "http://localhost:8080")
        :param top_n: 날짜별로 추출할 상위 단어 개수
        """
        self.input_file = input_file
        self.flask_server_url = flask_server_url
        self.top_n = top_n

    def _convert_date_format(self, date_str):
        """
        날짜 문자열을 표준 'YYYY-MM-DD' 형식으로 변환
        techcrunch 파일의 날짜 형식("YYYY.MM.DD ...")을 기준으로 변환.
        """
        try:
            # 예시: "2023.03.25 ..." 형식이면 앞의 10자리만 사용
            date_obj = datetime.strptime(date_str.strip()[:10], "%Y.%m.%d")
            return date_obj.strftime("%Y-%m-%d")
        except ValueError:
            # 날짜 형식이 다를 경우, YYYY-MM-DD 형식으로도 시도
            try:
                date_obj = datetime.strptime(date_str.strip()[:10], "%Y-%m-%d")
                return date_obj.strftime("%Y-%m-%d")
            except ValueError:
                print(f"❌ 잘못된 날짜 형식: {date_str}")
                return None

    def _extract_keywords(self, text):
        """
        주어진 텍스트에서 영어 단어들을 토큰화하고, 불용어 및 알파벳(영어)만을 남긴 뒤 반환
        """
        tokens = word_tokenize(text)
        # 소문자로 변환하고, 정규식을 사용하여 a-zA-Z로만 구성된 단어 필터링
        words = [
            word.lower()
            for word in tokens
            if re.match(r'^[a-zA-Z]+$', word)  # 오직 영어 알파벳만 허용
               and word.lower() not in stop_words
        ]
        return words

    def _calculate_word_frequencies(self, df):
        """
        DataFrame의 각 행에서 'title'과 'date'를 추출하여 날짜별 단어 빈도수를 계산
        """
        date_word_counts = defaultdict(Counter)

        for _, row in df.iterrows():
            raw_date = row['date']
            date = self._convert_date_format(raw_date)
            if date is None:
                continue

            title = row['title']
            words = self._extract_keywords(title)
            date_word_counts[date].update(words)

        result_list = []
        for date, word_counts in date_word_counts.items():
            # 날짜별 상위 top_n 단어 추출
            for word, count in word_counts.most_common(self.top_n):
                result_list.append({"date": date, "word": word, "count": count})

        return result_list

    def process_and_send(self):
        """
        CSV 파일을 읽어 단어 빈도수를 계산한 후, flask 서버에 POST 요청을 통해 전송
        """
        try:
            df = pd.read_csv(self.input_file, encoding='utf-8-sig')
        except Exception as e:
            print(f"❌ CSV 파일 읽기 오류: {e}")
            return

        if 'title' not in df.columns or 'date' not in df.columns:
            print("❌ CSV 파일에 'title' 또는 'date' 컬럼이 없습니다.")
            return

        word_frequencies = self._calculate_word_frequencies(df)
        self._send_to_flask_server(word_frequencies)

    def _send_to_flask_server(self, word_frequencies):
        """
        flask 서버의 /api/word_frequencies/upload 엔드포인트로 단어 빈도 데이터 전송 (국내 기사 전용)
        """
        try:
            response = requests.post(
                f"{self.flask_server_url}/api/word_frequencies/upload",
                json=word_frequencies
            )

            if response.status_code == 201:
                print("✅ 데이터가 Flask 서버로 성공적으로 전송되었습니다.")
            else:
                print(f"❌ 데이터 전송 실패: {response.status_code}, {response.text}")
        except Exception as e:
            print(f"❌ Flask 서버 전송 오류: {e}")

# 해외 기사 단어 빈도 추출을 위한 클래스 (기존 클래스를 상속받아 엔드포인트만 수정)
class ForeignEnglishKeywordExtractor(EnglishKeywordExtractor):
    def _send_to_flask_server(self, word_frequencies):
        """
        flask 서버의 /api/foreign_word_frequencies/upload 엔드포인트로 단어 빈도 데이터 전송
        이 엔드포인트는 이미 생성된 foreign_keyword_extraction 테이블에 데이터를 저장합니다.
        """
        try:
            response = requests.post(
                f"{self.flask_server_url}/api/foreign_word_frequencies/upload",
                json=word_frequencies
            )

            if response.status_code == 201:
                print("✅ 해외 기사 데이터가 Flask 서버로 성공적으로 전송되었습니다.")
            else:
                print(f"❌ 데이터 전송 실패: {response.status_code}, {response.text}")
        except Exception as e:
            print(f"❌ Flask 서버 전송 오류: {e}")

if __name__ == "__main__":
    # 해외 기사 처리: CSV 파일 경로를 "../../data/raw/techcrunch_article.csv"로 지정
    foreign_extractor = ForeignEnglishKeywordExtractor(
        input_file='../../data/raw/techcrunch_article.csv',  # 해외 기사에 해당하는 CSV 파일 경로
        flask_server_url="http://localhost:8080",
        top_n=10
    )
    foreign_extractor.process_and_send()
