from flask import Flask, render_template, request, jsonify
import psycopg2
import os
import json
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)


# DB 연결 함수
def get_db_connection():
    return psycopg2.connect(
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
    )


# 500 Internal Server Error 로그 출력
@app.errorhandler(500)
def internal_server_error(e):
    return jsonify({"error": str(e)}), 500


# 서버 상태 확인
@app.route("/", methods=["GET"])
def home():
    return jsonify({"message": "Server is running!"}), 200


# 기사 데이터 가져오기
@app.route("/api/articles", methods=["GET"])
def get_articles():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, category, media_company, title, date, image, url, summary FROM article_data;")
        articles = cur.fetchall()
        cur.close()
        conn.close()

        article_list = [
            {
                "id": article[0],
                "category": article[1],
                "media_company": article[2],
                "title": article[3],
                "date": article[4],
                "image": article[5],
                "url": article[6],
                "summary": article[7],
            }
            for article in articles
        ]

        return jsonify(article_list), 200

    except Exception as e:
        print("❌ get_articles() 오류:", e)
        return jsonify({"error": str(e)}), 500


# 기사 데이터를 HTML로 렌더링
@app.route("/articles", methods=["GET"])
def get_articles_html():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, category, media_company, title, date, image, url, summary FROM article_data;")
        articles = cur.fetchall()
        cur.close()
        conn.close()

        return render_template("articles.html", articles=articles)

    except Exception as e:
        print("❌ get_articles_html() 오류:", e)
        return jsonify({"error": str(e)}), 500


# 기사 데이터 업로드
@app.route("/upload", methods=["POST"])
def upload_article():
    data = request.json

    # 필수 필드 확인
    required_fields = ["category", "media_company", "title", "date", "image", "url", "summary"]
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"'{field}' 필드가 누락되었습니다."}), 400

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO article_data (category, media_company, title, date, image, url, summary)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
            """,
            (
                data["category"][:255],
                data["media_company"][:255],
                data["title"],
                data["date"],
                data["image"][:255],
                data["url"],
                data["summary"],
            ),
        )

        new_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"message": "Article added successfully", "id": new_id}), 201

    except Exception as e:
        print("❌ upload_article() 오류:", e)
        return jsonify({"error": str(e)}), 500


# 특정 기사 삭제 엔드포인트
@app.route("/delete_article/<int:article_id>", methods=["DELETE"])
def delete_article(article_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM article_data WHERE id = %s RETURNING id;", (article_id,))
        deleted_id = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        if deleted_id:
            return jsonify({"message": "Article deleted successfully", "id": deleted_id[0]}), 200
        else:
            return jsonify({"error": "Article not found"}), 404

    except Exception as e:
        print("❌ delete_article() 오류:", e)
        return jsonify({"error": str(e)}), 500


# 단어 빈도 데이터를 HTML로 렌더링
@app.route("/word_frequencies", methods=["GET"])
def get_word_frequencies_html():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT date, word, count FROM word_frequencies ORDER BY date DESC, count DESC;")
        word_frequencies = cur.fetchall()
        cur.close()
        conn.close()

        return render_template("word_frequencies.html", word_frequencies=word_frequencies)

    except Exception as e:
        print("❌ get_word_frequencies_html() 오류:", e)
        return jsonify({"error": str(e)}), 500


# 날짜별 상위 10개 단어 빈도 조회
@app.route("/api/word_frequencies/upload", methods=["POST"])
def upload_word_frequencies():
    data = request.json  # JSON 데이터 받기

    if not isinstance(data, list):
        return jsonify({"error": "데이터 형식이 잘못되었습니다. 리스트 형태여야 합니다."}), 400

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        create_table_query = """
        CREATE TABLE IF NOT EXISTS word_frequencies (
            id SERIAL PRIMARY KEY,
            date DATE NOT NULL,
            word TEXT NOT NULL,
            count INTEGER NOT NULL,
            UNIQUE(date, word)
        );
        """
        cur.execute(create_table_query)
        conn.commit()

        for entry in data:
            date = entry["date"]
            word = entry["word"]
            count = entry["count"]

            insert_query = """
            INSERT INTO word_frequencies (date, word, count)
            VALUES (%s, %s, %s)
            ON CONFLICT (date, word) DO UPDATE
            SET count = EXCLUDED.count;
            """
            cur.execute(insert_query, (date, word, count))

        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"message": "단어 빈도 데이터가 저장되었습니다."}), 201

    except Exception as e:
        print("❌ upload_word_frequencies() 오류:", e)
        return jsonify({"error": str(e)}), 500


# 해외 기사 단어 빈도 데이터를 저장하는 엔드포인트 (테이블: foreign_keyword_extraction)
@app.route("/api/foreign_word_frequencies/upload", methods=["POST"])
def upload_foreign_keyword_extraction():
    data = request.json  # JSON 데이터 받기

    if not isinstance(data, list):
        return jsonify({"error": "데이터 형식이 잘못되었습니다. 리스트 형태여야 합니다."}), 400

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # 이미 생성된 테이블 foreign_keyword_extraction 에 데이터를 삽입
        for entry in data:
            date = entry["date"]
            word = entry["word"]
            count = entry["count"]

            insert_query = """
            INSERT INTO foreign_keyword_extraction (date, word, count)
            VALUES (%s, %s, %s)
            ON CONFLICT (date, word) DO UPDATE
            SET count = EXCLUDED.count;
            """
            cur.execute(insert_query, (date, word, count))

        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"message": "외국 기사 단어 빈도 데이터가 저장되었습니다."}), 201

    except Exception as e:
        print("❌ upload_foreign_keyword_extraction() 오류:", e)
        return jsonify({"error": str(e)}), 500


# 해외 기사 데이터를 HTML로 렌더링
@app.route("/foreign_articles", methods=["GET"])
def get_foreign_articles_html():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, url, title, date, description FROM foreign_press_articles;")
        foreign_articles = cur.fetchall()
        cur.close()
        conn.close()

        return render_template("foreign_articles.html", foreign_articles=foreign_articles)

    except Exception as e:
        print("❌ get_foreign_articles_html() 오류:", e)
        return jsonify({"error": str(e)}), 500


# foreign_articles 테이블에 기사 데이터 업로드
@app.route("/api/foreign_articles/upload", methods=["POST"])
def foreign_upload_article():
    data = request.json

    # 필수 필드 확인
    required_fields = ["url", "title", "date", "content", "media_company"]
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"'{field}' 필드가 누락되었습니다."}), 400

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO foreign_articles (url, title, date, content, media_company)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id;
            """,
            (
                data["url"],
                data["title"],
                data["date"],
                data["content"],
                data["media_company"],
            ),
        )

        new_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"message": "Article added successfully", "id": new_id}), 201

    except Exception as e:
        print("❌ upload_article() 오류:", e)
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=8080)
