import os
import pandas as pd
from datetime import datetime
from dateutil import parser


def format_date(date_str, input_format=None, output_format="%Y-%m-%d"):
    """
    날짜 문자열을 지정된 output_format으로 변환합니다.
    input_format이 제공되면 datetime.strptime를 사용하고, 그렇지 않으면 dateutil.parser를 사용합니다.
    """
    # 날짜가 None이거나 빈 문자열인 경우 현재 날짜 반환
    if not date_str:
        return datetime.now().strftime(output_format)
        
    try:
        if input_format:
            dt = datetime.strptime(date_str, input_format)
        else:
            dt = parser.parse(date_str)
        return dt.strftime(output_format)
    except Exception as e:
        print(f"날짜 파싱 오류: {e}")
        # 파싱 실패 시 현재 날짜 반환
        return datetime.now().strftime(output_format)


def sanitize_for_csv(text):
    """
    CSV 저장을 위해 텍스트를 정리합니다.
    - 줄바꿈 문자를 공백으로 대체
    - 특수문자 처리 등
    """
    if not text or not isinstance(text, str):
        return ""
    
    # 줄바꿈 문자를 공백으로 대체
    text = text.replace('\n', ' ').replace('\r', ' ')
    
    # 연속된 공백을 하나로 줄임
    text = ' '.join(text.split())
    
    # 내용이 너무 길 경우 잘라내기 (선택 사항)
    max_length = 5000
    if len(text) > max_length:
        text = text[:max_length] + "..."
    
    return text


def save_to_csv(articles, filepath):
    """
    기사 데이터 리스트를 pandas DataFrame으로 변환하여 CSV 파일로 저장합니다.
    모든 파일에서 동일한 컬럼 순서와 인코딩(utf-8-sig)을 사용합니다.
    category, content, date, image_url, media_company, title, url 순서로 저장합니다.
    """

    if not articles:
        print("저장할 데이터가 없습니다. CSV 저장을 중단합니다.")
        return

    # 필수 필드 확인 및 기본값 설정
    for article in articles:
        # 카테고리가 없으면 기본값 'IT'로 설정
        if 'category' not in article:
            article['category'] = 'IT'
        # 이미지 URL이 없으면 빈 문자열로 설정
        if 'image_url' not in article:
            article['image_url'] = ''
        # content 필드의 줄바꿈 문자 처리
        if 'content' in article:
            article['content'] = sanitize_for_csv(article['content'])
        # title 필드의 줄바꿈 문자 처리
        if 'title' in article:
            article['title'] = sanitize_for_csv(article['title'])

    df = pd.DataFrame(articles)

    # 날짜가 datetime 객체인 경우 문자열로 변환
    if not df.empty and 'date' in df.columns and isinstance(df.loc[0, 'date'], datetime):
        df['date'] = df['date'].apply(lambda d: d.strftime("%Y-%m-%d"))
    
    # 컬럼 순서 조정
    columns_order = ['category', 'content', 'date', 'image_url', 'media_company', 'title', 'url']
    
    # 존재하는 컬럼만 사용
    available_columns = [col for col in columns_order if col in df.columns]
    
    # 순서대로 정렬하여 저장
    df = df[available_columns]
    
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    df.to_csv(filepath, index=False, encoding='utf-8-sig', quotechar='"', escapechar='\\', lineterminator='\n')
    print(f"CSV 파일이 저장되었습니다: {filepath}, 기사 수: {len(df)}")
    print(f"저장된 컬럼: {', '.join(df.columns.tolist())}")
