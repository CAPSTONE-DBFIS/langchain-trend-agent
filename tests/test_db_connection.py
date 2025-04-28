import os
import psycopg2
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

def test_db_connection():
    """PostgreSQL 데이터베이스 연결 테스트"""
    try:
        # 환경 변수에서 DB 설정 가져오기
        db_host = os.getenv("DB_HOST")
        db_port = os.getenv("DB_PORT")
        db_name = os.getenv("DB_NAME")
        db_user = os.getenv("DB_USER")
        db_password = os.getenv("DB_PASSWORD")
        
        print(f"DB 연결 정보:")
        print(f"Host: {db_host}")
        print(f"Port: {db_port}")
        print(f"Database: {db_name}")
        print(f"User: {db_user}")
        print(f"Password: {'*' * len(db_password) if db_password else 'None'}")
        
        # 데이터베이스 연결
        conn = psycopg2.connect(
            host=db_host,
            port=db_port,
            dbname=db_name,
            user=db_user,
            password=db_password
        )
        
        # 커서 생성 및 간단한 쿼리 실행
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        db_version = cursor.fetchone()
        
        print("\n=== DB 연결 성공! ===")
        print(f"PostgreSQL 서버 버전: {db_version[0]}")
        
        # 연결된 데이터베이스의 테이블 목록 조회
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """)
        
        tables = cursor.fetchall()
        if tables:
            print("\n데이터베이스 테이블 목록:")
            for table in tables:
                print(f"- {table[0]}")
        else:
            print("\n데이터베이스에 테이블이 없습니다.")
        
        # 커넥션 종료
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"\n=== DB 연결 실패! ===")
        print(f"오류: {str(e)}")
        return False

if __name__ == "__main__":
    test_db_connection() 