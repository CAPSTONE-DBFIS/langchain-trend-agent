# tests/test_parser.py

from scripts.domestic_article.parser import parse_data
from scripts.parser import parse_data
import pytest

def mock_selenium_scrape(url):
    return "mock_image_url", "http://mock_base_url", "0"

@pytest.fixture(autouse=True)
def mock_selenium(monkeypatch):
    # selenium_scrape를 Mock으로 대체
    monkeypatch.setattr("scripts.parser.selenium_scrape", mock_selenium_scrape)

def test_parse_data():
    # 테스트용 HTML 데이터
    raw_html = "<html><body><div class='example'>Test Data 1</div><div class='example'>Test Data 2</div></body></html>"
    url = "http://example.com"

    # parse_data 함수 실행
    result = parse_data(raw_html, url)

    # 결과 검증
    assert result["image"] == "mock_image_url"
    assert result["url"] == "http://mock_base_url"
    assert result["comment_count"] == "0"