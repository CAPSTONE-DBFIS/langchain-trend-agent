import os
import pandas as pd
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from collections import Counter
from konlpy.tag import Okt


class SemanticTextClassifier:
    def __init__(self, input_file, output_dir, stopwords_file='../../data/raw/stopwords.txt', threshold=0.7):
        self.input_file = input_file
        self.output_dir = output_dir
        self.threshold = threshold
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
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

    def _calculate_word_frequencies(self, texts):
        """Calculates word frequencies from the given texts."""
        word_counter = Counter()
        for text in texts:
            # Preprocess text using Okt for tokenization and stopword removal
            words = self._remove_josa_with_okt(text)
            word_counter.update(words)
        return word_counter

    def process_and_save(self):
        """Processes the input file and saves results to the output directory."""
        # Read input CSV
        try:
            df = pd.read_csv(self.input_file, encoding='utf-8-sig')
        except FileNotFoundError:
            print(f"파일을 찾을 수 없습니다: {self.input_file}")
            return

        if 'title' not in df.columns:
            print("CSV 파일에 'title' 열이 없습니다.")
            return

        # 제목 데이터 추출
        titles = df['title'].dropna().tolist()

        # Calculate word frequencies for titles
        title_word_frequencies = self._calculate_word_frequencies(titles)

        # Filter words with frequency <= 0
        filtered_word_frequencies = {word: count for word, count in title_word_frequencies.items() if count > 0}

        # Save filtered word frequencies
        os.makedirs(self.output_dir, exist_ok=True)
        word_freq_file = os.path.join(self.output_dir, 'word_frequencies.csv')
        word_freq_df = pd.DataFrame(filtered_word_frequencies.items(), columns=['Word', 'Count']).sort_values(by='Count',
                                                                                                               ascending=False)
        word_freq_df.to_csv(word_freq_file, index=False, encoding='utf-8-sig')

        print(f"단어 빈도 데이터가 {word_freq_file}에 저장되었습니다.")


# Example usage
if __name__ == "__main__":

    classifier = SemanticTextClassifier(
        input_file='../../data/raw/article_data.csv',
        output_dir='../../data/processed/',
        threshold=0.7
    )
    classifier.process_and_save()
