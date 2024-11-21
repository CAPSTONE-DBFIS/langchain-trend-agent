# tests/test_scraper.py

import pytest
from scripts.scraper import scrape_data

def test_scrape_data(monkeypatch):
    # 가짜 응답 데이터를 생성하여 요청이 성공적으로 이루어졌는지 테스트
    class MockResponse:
        def __init__(self, text, status_code):
            self.text = text
            self.status_code = status_code

    def mock_get(*args, **kwargs):
        return MockResponse("<html><body><div class='example'>Test Data</div></body></html>", 200)

    # requests.get 메서드를 mock 객체로 대체
    monkeypatch.setattr("requests.get", mock_get)

    # scrape_data 함수를 호출하고 결과 검증
    result = scrape_data()
    assert result == "<html><body><div class='example'>Test Data</div></body></html>"