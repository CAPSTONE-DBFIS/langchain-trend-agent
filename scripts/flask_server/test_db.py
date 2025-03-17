import psycopg2
import os
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()


def test_db_connection():
    try:
        conn = psycopg2.connect(
            dbname=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT"),
        )
        cur = conn.cursor()
        cur.execute("SELECT version();")  # PostgreSQL 버전 확인
        db_version = cur.fetchone()
        print("✅ PostgreSQL 연결 성공!")
        print(f"📌 DB 버전: {db_version[0]}")

        cur.close()
        conn.close()
        return True
    except Exception as e:
        print("❌ DB 연결 실패:", e)
        return False


if __name__ == "__main__":
    if test_db_connection():
        print("🎯 DB 연결이 정상적으로 이루어졌습니다!")
    else:
        print("⚠️ DB 연결에 문제가 있습니다. 설정을 확인하세요!")
