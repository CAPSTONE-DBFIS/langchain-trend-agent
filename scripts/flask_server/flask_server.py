from flask import Flask, request, jsonify
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
import os

app = Flask(__name__)

# .env 파일 로드
load_dotenv()

DB_CONFIG = {
    'dbname': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST'),
    'port': os.getenv('DB_PORT')
}

def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)

@app.route('/', methods=['GET'])
def index():
    return 'Flask Server is Running!'

@app.route('/upload', methods=['POST'])
def upload_data():
    data = request.json  # JSON 데이터 받기

    if not data:
        return jsonify({'message': 'No data received'}), 400

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # 데이터를 PostgreSQL 테이블에 삽입
        insert_query = """
        INSERT INTO articles (category, media_company, title, date, comment_count, image, url)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        for item in data:
            cursor.execute(insert_query, (
                item['category'],
                item['media_company'],
                item['title'],
                item['date'],
                item['comment_count'],
                item['image'],
                item['url']
            ))
        conn.commit()

        return jsonify({'message': 'Data uploaded successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


if __name__ == '__main__':
    app.run(debug=True, port=5432)
