import os
import pandas as pd
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
import torch

# 번역 모델 (NLLB-200)
MODEL_NAME = "facebook/nllb-200-distilled-600M"
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME)

# 번역 대상 언어 설정
SRC_LANG = "eng_Latn"  # 원본 언어 (영어)
TGT_LANG = "kor_Hang"  # 번역 언어 (한국어)

# 원본 데이터 및 저장 경로 설정
RAW_DATA_PATH = "../../data/raw/"
PROCESSED_DATA_PATH = "../../data/processed/"

# 번역할 파일 목록
CSV_FILES = [
    "nyt_article.csv",
    "techcrunch_article.csv",
    "zdnet_article.csv",
    "ars_technica_article.csv"
]


def translate_text(text):
    """주어진 영어 텍스트를 한국어로 번역"""
    if not text.strip():
        return ""  # 빈 문자열 처리

    inputs = tokenizer(text, return_tensors="pt", padding=True, truncation=True, max_length=512)

    # 강제 BOS 토큰 ID 설정 (한국어)
    bos_token_id = tokenizer.convert_tokens_to_ids(TGT_LANG)

    with torch.no_grad():
        outputs = model.generate(**inputs, forced_bos_token_id=bos_token_id)

    return tokenizer.decode(outputs[0], skip_special_tokens=True)


def translate_csv(file_path, save_path):
    """CSV 파일의 'title'과 'desc' 컬럼을 번역하여 기존 데이터에 'title_ko' 및 'desc_ko' 컬럼 추가"""
    df = pd.read_csv(file_path, encoding="utf-8-sig")

    if "title" not in df.columns or "desc" not in df.columns:
        print(f"⚠️ {file_path}에 'title' 또는 'desc' 컬럼이 없습니다. 건너뜁니다.")
        return

    print(f"🔍 {file_path} 번역 중...")

    # title 컬럼 번역 (새로운 title_ko 컬럼 추가)
    df["title_ko"] = df["title"].astype(str).apply(translate_text)

    # desc 컬럼 번역 (새로운 desc_ko 컬럼 추가)
    df["desc_ko"] = df["desc"].astype(str).apply(translate_text)

    # 번역된 CSV 파일 저장
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    df.to_csv(save_path, index=False, encoding="utf-8-sig")
    print(f"✅ 번역 완료: {save_path}")

def main():
    """폴더 내 모든 해외 기사 CSV 파일 번역"""
    for file in CSV_FILES:
        raw_file_path = os.path.join(RAW_DATA_PATH, file)
        translated_file_path = os.path.join(PROCESSED_DATA_PATH, f"translated_{file}")

        if os.path.exists(raw_file_path):
            translate_csv(raw_file_path, translated_file_path)
        else:
            print(f"⚠️ 파일 없음: {raw_file_path}")

if __name__ == "__main__":
    main()
