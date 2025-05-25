import boto3
from io import BytesIO
import os
import matplotlib.pyplot as plt
import logging

logger = logging.getLogger(__name__)

def get_s3_client_and_bucket():
    """S3 클라이언트와 버킷 이름을 반환하는 함수 """
    s3 = boto3.client(
        "s3",
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        region_name=os.environ.get("AWS_REGION", "ap-northeast-2"),
    )
    bucket = os.environ.get("S3_BUCKET", "trend-charts")
    return s3, bucket


def upload_chart_to_s3(chart_data, key: str) -> str:
    """차트 데이터를 S3에 업로드하고 URL을 반환하는 함수"""
    s3, bucket = get_s3_client_and_bucket()

    # 차트 데이터를 BytesIO로 변환
    if isinstance(chart_data, plt.Figure):
        buf = BytesIO()
        chart_data.savefig(buf, format="png")
        buf.seek(0)
    elif hasattr(chart_data, 'to_image'):  # Plotly Figure
        buf = BytesIO()
        buf.write(chart_data.to_image(format="png"))
        buf.seek(0)
    elif isinstance(chart_data, BytesIO):
        buf = chart_data
        buf.seek(0)
    else:
        raise ValueError("지원되지 않는 차트 데이터 형식입니다.")

    # S3에 업로드
    s3.put_object(Body=buf, Bucket=bucket, Key=key, ContentType="image/png")

    # URL 생성
    url = f"https://{bucket}.s3.amazonaws.com/{key}"
    return url