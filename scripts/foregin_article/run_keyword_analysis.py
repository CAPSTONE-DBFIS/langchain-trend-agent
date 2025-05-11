import sys
from datetime import datetime
from foreign_keyword_extractor import ForeignKeywordExtractor
from foreign_keyword_analyzer import ForeignKeywordAnalyzer
from datetime import datetime, timedelta


def run_keyword_analysis(date_str):
    """
    지정된 날짜에 대해 키워드 추출 및 분석을 수행합니다.
    
    Args:
        date_str (str): 'YYYY-MM-DD' 형식의 날짜 문자열
    """
    try:
        # 날짜 형식 검증
        datetime.strptime(date_str, "%Y-%m-%d")

        print(f"===== {date_str} 날짜에 대한 키워드 분석 시작 =====")

        # 1. 키워드 추출 및 저장 (내림차순 정렬)
        print("\n[1단계] 상위 키워드 추출 시작")
        extractor = ForeignKeywordExtractor()
        keywords = extractor.process_date(date_str)
        print(f"[1단계] 상위 키워드 {len(keywords)}개 추출 및 저장 완료")

        # 2. 연관 키워드 분석 및 저장 (내림차순 정렬)
        print("\n[2단계] 연관 키워드 분석 시작")
        analyzer = ForeignKeywordAnalyzer()
        analyzer.analyze_date(date_str)
        print("[2단계] 연관 키워드 분석 및 저장 완료")

        print(f"\n===== {date_str} 날짜에 대한 키워드 분석 완료 =====")

    except ValueError:
        print(f"오류: 유효하지 않은 날짜 형식입니다. 'YYYY-MM-DD' 형식으로 입력해주세요.")
    except Exception as e:
        print(f"오류 발생: {str(e)}")


if __name__ == "__main__":
    start_date = datetime.strptime("2025-05-04", "%Y-%m-%d")
    end_date = datetime.strptime("2025-05-04", "%Y-%m-%d")

    current_date = start_date
    while current_date <= end_date:
        date_str = current_date.strftime("%Y-%m-%d")
        run_keyword_analysis(date_str)
        current_date += timedelta(days=1)
