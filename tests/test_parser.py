# tests/test_parser.py

from scripts.domestic_article.parser import parse_data


def test_parse_data():
    # 테스트용 HTML 데이터
    raw_html = "<html><body><div class='example'>Test Data 1</div><div class='example'>Test Data 2</div></body></html>"

    # parse_data 함수 실행
    result = parse_data(raw_html)

    # 결과 검증
    assert result == ["Test Data 1", "Test Data 2"]
