# tests/test_scraper.py

from scripts.domestic_article.scraper import scrape_data
import pytest
from scripts.scraper import scrape_data_by_category

def test_scrape_data_by_category(monkeypatch):
    # MockResponse 클래스 수정
    class MockResponse:
        def __init__(self, text, status_code):
            self.text = text  # text 속성 추가
            self.status_code = status_code

        def json(self):
            return {
                "items": [
                    {"link": "http://n.news.naver.com/mock1"},
                    {"link": "http://n.news.naver.com/mock2"}
                ]
            }

    # requests.get 메서드를 mock 객체로 대체
    def mock_get(*args, **kwargs):
        return MockResponse("<html>Mock HTML Content</html>", 200)  # text 값 추가

    monkeypatch.setattr("requests.get", mock_get)

    # 테스트 실행
    categories = ["example_category"]
    raw_html_list, url_list = scrape_data_by_category(categories)

    # 결과 검증
    assert len(raw_html_list) == 2
    assert len(url_list) == 2
    assert raw_html_list[0] == "<html>Mock HTML Content</html>"
    assert url_list[0] == "http://n.news.naver.com/mock1"