import os
import requests
from dotenv import load_dotenv
from data_upload_milvus import connect_milvus, Collection

# 환경 변수 로드
load_dotenv()

# DeepL API 설정
DEEPL_API_KEY = os.getenv("DeepL_API_KEY")
DEEPL_API_URL = "https://api-free.deepl.com/v2/translate"

# Papago API 설정
PAPAGO_CLIENT_ID = os.getenv("PAPAGO_CLIENT_ID")
PAPAGO_CLIENT_SECRET = os.getenv("PAPAGO_CLIENT_SECRET")
PAPAGO_API_URL = "https://papago.apigw.ntruss.com/nmt/v1/translation"

# Flask 서버 엔드포인트
FLASK_SERVER_URL = "http://localhost:8080/api/foreign_articles/upload"

# Milvus 컬렉션 정보
COLLECTION_NAME = "foreign_article"

# Milvus 연결
connect_milvus()

# 파파고 API 사용량 측정 전역 변수
papago_character_count = 4400


# Milvus에서 기사 데이터 가져오기
def fetch_articles(limit=5):
    collection = Collection(COLLECTION_NAME)
    collection.load()

    results = collection.query(
        expr="pk >= 0",
        output_fields=["url", "title", "date", "content", "media_company"],
        limit=limit
    )
    return results


# DeepL API를 사용해 번역하는 함수
def translate_text_deppl(text, target_lang="KO"):
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


# Papago API를 사용한 번역 함수
def translate_text_papago(text, target_lang="ko"):
    global papago_character_count

    if not text:
        return ""

    headers = {
        "X-NCP-APIGW-API-KEY-ID": PAPAGO_CLIENT_ID,
        "X-NCP-APIGW-API-KEY": PAPAGO_CLIENT_SECRET
    }

    data = {
        "source": "en",
        "target": target_lang,
        "text": text
    }

    response = requests.post(PAPAGO_API_URL, headers=headers, data=data)

    if response.status_code == 200:
        # 성공 시 사용량 누적
        papago_character_count += len(text)
        return response.json()["message"]["result"]["translatedText"]
    else:
        print(f"Papago API 호출 실패: {response.status_code}, {response.text}")
        return None

# Flask 서버로 번역된 데이터 업로드
def upload_article(data):
    response = requests.post(FLASK_SERVER_URL, json=data)
    if response.status_code == 201:
        print(f"✅ 성공적으로 업로드됨: {data['title']}")
    else:
        print(f"❌ 업로드 실패: {response.status_code}, {response.text}")


# 사용량 확인
def check_deepl_usage():
    headers = {
        "Authorization": f"DeepL-Auth-Key {DEEPL_API_KEY}"
    }
    usage_url = "https://api-free.deepl.com/v2/usage"

    response = requests.get(usage_url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        character_count = data.get("character_count", 0)
        character_limit = data.get("character_limit", 500000)
        print(f"📊 사용량: {character_count}자 / {character_limit}자")
        return character_count, character_limit
    else:
        print(f"❌ 사용량 확인 실패: {response.status_code}, {response.text}")
        return None, None


# 실행 코드
if __name__ == "__main__":
    # DeepL 사용량 확인
    deepl_used, deepl_limit = check_deepl_usage()
    deepl_threshold = 490000
    papago_threshold = 490000

    # Milvus에서 기사 데이터 가져오기
    articles = fetch_articles(limit=5)

    for article in articles:
        title = article["title"]
        content = article["content"]
        date = article["date"]
        media_company = article["media_company"]
        url = article["url"]

        print(f"\n🔹 원본 제목: {title}")
        print(f"🔹 원본 본문: {content[:200]}...")

        # 번역 대상 텍스트 길이
        total_len = len(title) + len(content[:500])

        # 사용량 기준에 따라 번역 분기
        if deepl_used is not None and deepl_used + total_len < deepl_threshold:
            print("🔁 DeepL 번역 사용 중...")
            translated_title = translate_text_deppl(title, "KO")
            translated_desc = translate_text_deppl(content[:500], "KO")
            deepl_used += total_len  # 추적 갱신
        elif papago_character_count + total_len < papago_threshold:
            print("🔁 Papago 번역 사용 중...")
            translated_title = translate_text_papago(title, "ko")
            translated_desc = translate_text_papago(content[:500], "ko")
        else:
            print("❌ Papago/DeepL 사용량 모두 초과. 번역 중단.")
            break

        # 결과 출력
        print(f"✅ 번역된 제목: {translated_title}")
        print(f"✅ 번역된 본문: {translated_desc[:200]}...")

        # 업로드
        article_data = {
            "title": translated_title,
            "content": translated_desc,
            "date": date,
            "media_company": media_company,
            "url": url
        }
        upload_article(article_data)
