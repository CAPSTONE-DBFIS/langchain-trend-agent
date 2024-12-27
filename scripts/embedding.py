import os
import openai
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

# OpenAI API 설정
openai.api_key = os.getenv("OPENAI_API_KEY")
if not openai.api_key:
    raise ValueError("OpenAI API 키가 설정되지 않았습니다. .env 파일을 확인하세요.")

# 기사 본문 임베딩 생성
def get_embedding(text):
    try:
        response = openai.Embedding.create(
            input=text,
            model="text-embedding-3-small" # 임베딩 모델
        )
        return response['data'][0]['embedding']
    except Exception as e:
        print(f"임베딩 생성 실패: {str(e)}")
        return None