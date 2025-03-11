import pytest
import requests

BASE_URL = "http://127.0.0.1:8080"  # Flask 서버 주소

# 서버 상태 확인 테스트
def test_home():
    response = requests.get(f"{BASE_URL}/home")
    assert response.status_code == 200
    assert response.json() == {"message": "Server is running!"}

# 기사 데이터 가져오기 테스트
def test_get_articles():
    response = requests.get(f"{BASE_URL}/api/articles")
    assert response.status_code == 200
    assert isinstance(response.json(), list)  # 결과가 리스트인지 확인

# 기사 데이터 업로드 및 삭제 테스트
def test_upload_and_delete_article():
    article_data = {
        "category": "IT",
        "media_company": "테크미디어",
        "title": "AI 기술의 발전",
        "date": "2025-03-09",
        "comment_count": 10,
        "image": "https://example.com/image.jpg",
        "url": "https://example.com/article",
        "summary": "AI 기술이 빠르게 발전하고 있다."
    }

    # 1️⃣ 기사 업로드
    response = requests.post(f"{BASE_URL}/upload", json=article_data)
    assert response.status_code == 201
    json_data = response.json()
    assert "id" in json_data
    article_id = json_data["id"]  # 저장된 ID 가져오기

    # 2️⃣ 테스트 후 데이터 삭제
    delete_response = requests.delete(f"{BASE_URL}/delete_article/{article_id}")
    assert delete_response.status_code == 200
    delete_json = delete_response.json()
    assert delete_json["id"] == article_id  # 삭제된 ID 확인

# 필수 필드 누락 테스트
@pytest.mark.parametrize("missing_field", ["category", "media_company", "title", "date", "comment_count", "image", "url", "summary"])
def test_upload_article_missing_fields(missing_field):
    article_data = {
        "category": "IT",
        "media_company": "테크미디어",
        "title": "AI 기술의 발전",
        "date": "2025-03-09",
        "comment_count": 10,
        "image": "https://example.com/image.jpg",
        "url": "https://example.com/article",
        "summary": "AI 기술이 빠르게 발전하고 있다."
    }
    del article_data[missing_field]  # 특정 필드를 삭제

    response = requests.post(f"{BASE_URL}/upload", json=article_data)
    assert response.status_code == 400  # 필수 필드 누락 시 400 오류 반환

if __name__ == "__main__":
    pytest.main()
