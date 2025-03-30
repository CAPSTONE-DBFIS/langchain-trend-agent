import os
import pandas as pd
from datetime import datetime
from dateutil import parser


def format_date(date_str, input_format=None, output_format="%Y-%m-%d"):
    """
    날짜 문자열을 지정된 output_format으로 변환합니다.
    input_format이 제공되면 datetime.strptime를 사용하고, 그렇지 않으면 dateutil.parser를 사용합니다.
    """
    from dateutil import parser
    try:
        if input_format:
            dt = datetime.strptime(date_str, input_format)
        else:
            dt = parser.parse(date_str)
        return dt.strftime(output_format)
    except Exception as e:
        print(f"날짜 파싱 오류: {e}")
        return date_str


def save_to_csv(articles, filepath):
    """
    기사 데이터 리스트를 pandas DataFrame으로 변환하여 CSV 파일로 저장합니다.
    모든 파일에서 동일한 컬럼 순서와 인코딩(utf-8-sig)을 사용합니다.
    """

    if not articles:
        print("저장할 데이터가 없습니다. CSV 저장을 중단합니다.")
        return

    df = pd.DataFrame(articles)

    # 날짜가 datetime 객체인 경우 문자열로 변환
    if not df.empty and isinstance(df.loc[0, 'date'], datetime):
        df['date'] = df['date'].apply(lambda d: d.strftime("%Y-%m-%d"))
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    df.to_csv(filepath, index=False, encoding='utf-8-sig', quotechar='"')
    print(f"CSV 파일이 저장되었습니다: {filepath}")
