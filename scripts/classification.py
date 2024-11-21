import pandas as pd
from collections import Counter
import os

class TextClassifier:
    def __init__(self, input_file, output_dir):
        self.input_file = input_file
        self.output_dir = output_dir

    def process_and_save(self):
        # CSV 파일 읽기
        try:
            df = pd.read_csv(self.input_file, encoding='utf-8-sig')
        except FileNotFoundError:
            print(f"파일을 찾을 수 없습니다: {self.input_file}")
            return

        # 제목 열에서 텍스트 추출
        if 'title' not in df.columns:
            print("CSV 파일에 'title' 열이 없습니다.")
            return

        titles = df['title'].dropna().tolist()

        # 단어별 빈도 계산
        word_counter = Counter()
        for title in titles:
            words = title.split()
            word_counter.update(words)

        # 데이터프레임 생성
        word_count_df = pd.DataFrame(word_counter.items(), columns=['Word', 'Count']).sort_values(by='Count', ascending=False)

        # 저장 경로 확인 및 디렉터리 생성
        os.makedirs(self.output_dir, exist_ok=True)
        output_file = os.path.join(self.output_dir, 'word_frequencies.csv')

        # CSV로 저장
        word_count_df.to_csv(output_file, index=False, encoding='utf-8-sig')
        print(f"단어 빈도 데이터가 {output_file}에 저장되었습니다.")
