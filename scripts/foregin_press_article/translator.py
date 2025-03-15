import os
import requests
from dotenv import load_dotenv
from data_upload_milvus import connect_milvus, Collection

# 환경 변수 로드
load_dotenv()

# DeepL API 설정
DEEPL_API_KEY = os.getenv("DeepL_API_KEY")
DEEPL_API_URL = "https://api-free.deepl.com/v2/translate"

# Flask 서버 엔드포인트
FLASK_SERVER_URL = "http://localhost:8080/api/foreign_articles/upload"

# Milvus 컬렉션 정보
COLLECTION_NAME = "foreign_article"

# Milvus 연결
connect_milvus()


# Milvus에서 기사 데이터 가져오기
def fetch_articles(limit=5):
    collection = Collection(COLLECTION_NAME)
    collection.load()

    results = collection.query(
        expr="pk >= 0",
        output_fields=["url", "title", "date", "desc"],
        limit=limit
    )
    return results


# DeepL API를 사용해 번역하는 함수
def translate_text(text, target_lang="KO"):
    if not text:
        return ""

    data = {
        "auth_key": DEEPL_API_KEY,
        "text": text,
        "target_lang": target_lang
    }

    response = requests.post(DEEPL_API_URL, data=data)
    if response.status_code == 200:
        return response.json()["translations"][0]["text"]
    else:
        print(f"DeepL API 호출 실패: {response.status_code}, {response.text}")
        return None


# Flask 서버로 번역된 데이터 업로드
def upload_article(data):
    response = requests.post(FLASK_SERVER_URL, json=data)
    if response.status_code == 201:
        print(f"✅ 성공적으로 업로드됨: {data['title']}")
    else:
        print(f"❌ 업로드 실패: {response.status_code}, {response.text}")


# 실행 코드
if __name__ == "__main__":
    # Milvus에서 기사 데이터 가져오기
    articles = fetch_articles(limit=5)

    for article in articles:
        url, title, date, desc = article["url"], article["title"], article["date"], article["desc"]

        print(f"\n🔹 원본 제목: {title}")
        print(f"🔹 원본 본문: {desc[:200]}...")  # 본문 일부 출력

        translated_title = translate_text(title, "KO")
        translated_desc = translate_text(desc[:500], "KO")  # DeepL Free API 제한 고려

        print(f"✅ 번역된 제목: {translated_title}")
        print(f"✅ 번역된 본문: {translated_desc[:200]}...")  # 번역된 본문 일부 출력

        # Flask 서버에 데이터 전송
        article_data = {
            "url": url,
            "title": translated_title,
            "date": date,
            "description": translated_desc
        }
        upload_article(article_data)
