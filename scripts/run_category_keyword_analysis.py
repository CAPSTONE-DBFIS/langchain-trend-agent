#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import argparse
from datetime import datetime, timedelta
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 카테고리별 키워드 추출 및 연관어 분석 클래스 임포트
from scripts.domestic_article.category_keyword_extractor import CategoryKeywordExtractor
from scripts.domestic_article.category_related_keyword_extractor import CategoryRelatedKeywordExtractor

def parse_args():
    """
    명령행 인자를 파싱합니다.
    """
    parser = argparse.ArgumentParser(description='카테고리별 키워드 추출 및 연관어 분석')
    
    # 날짜 인자 (기본값: 어제)
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    parser.add_argument('--date', type=str, default=yesterday,
                        help='분석할 날짜 (YYYY-MM-DD 형식, 기본값: 어제)')
    
    # 카테고리별 상위 키워드 수
    parser.add_argument('--top-n', type=int, default=10,
                        help='각 카테고리별로 추출할 상위 키워드 수 (기본값: 10)')
    
    # CSV 파일 경로
    default_csv = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                              'data', 'processed', 'domestic_articles.csv')
    parser.add_argument('--csv', type=str, default=default_csv,
                        help='분석할 CSV 파일 경로 (기본값: data/processed/domestic_articles.csv)')
    
    # 연관어 분석 여부
    parser.add_argument('--analyze-related', action='store_true',
                        help='키워드 추출 후 연관어 분석도 수행 (기본값: False)')
    
    return parser.parse_args()

def main():
    """
    메인 함수
    """
    args = parse_args()
    
    try:
        # 날짜 파싱
        date = datetime.strptime(args.date, '%Y-%m-%d')
    except ValueError:
        print(f"잘못된 날짜 형식입니다: {args.date}. YYYY-MM-DD 형식을 사용하세요.")
        return 1
    
    print(f"===== {date.strftime('%Y-%m-%d')} 날짜 카테고리별 키워드 분석 시작 =====")
    
    # 1. 카테고리별 키워드 추출
    try:
        print("1. 카테고리별 키워드 추출 시작...")
        extractor = CategoryKeywordExtractor(
            input_file=args.csv,
            top_n_per_category=args.top_n
        )
        keywords = extractor.process_and_save(date)
        print("1. 카테고리별 키워드 추출 완료")
    except Exception as e:
        print(f"카테고리별 키워드 추출 중 오류 발생: {str(e)}")
        return 1
    
    # 2. 연관어 분석 (선택적)
    if args.analyze_related:
        try:
            print("2. 카테고리별 연관어 분석 시작...")
            analyzer = CategoryRelatedKeywordExtractor(top_n=args.top_n)
            results = analyzer.analyze_all_categories(date)
            print("2. 카테고리별 연관어 분석 완료")
        except Exception as e:
            print(f"카테고리별 연관어 분석 중 오류 발생: {str(e)}")
            return 1
    
    print(f"===== {date.strftime('%Y-%m-%d')} 날짜 카테고리별 키워드 분석 완료 =====")
    return 0

if __name__ == "__main__":
    sys.exit(main()) 