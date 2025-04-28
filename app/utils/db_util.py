import os
import psycopg2
from dotenv import load_dotenv
from langchain_community.chat_message_histories import ChatMessageHistory
from datetime import datetime

# 환경 변수 로드
load_dotenv()

# PostgreSQL 연결 함수
def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        port=os.getenv("DB_PORT")
    )


# 대화 기록 불러오기
def get_session_history(chat_room_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        query = """
        SELECT message, response, created_at 
        FROM chat_messages
        WHERE chat_room_id = %s
        ORDER BY created_at ASC
        """
        cursor.execute(query, (chat_room_id,))
        messages = cursor.fetchall()

        chat_history = ChatMessageHistory()

        for user_msg, bot_response, _ in messages:
            chat_history.add_user_message(user_msg)
            chat_history.add_ai_message(bot_response)

        cursor.close()
        conn.close()
        return chat_history

    except Exception as e:
        print(f"[ERROR] PostgreSQL 대화 기록 조회 중 오류 발생: {str(e)}")
        return ChatMessageHistory()


# 사용자 페르소나 불러오기
def get_user_persona(persona_id, member_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        query = """
        SELECT name, prompt
        FROM persona
        WHERE id = %s
          AND (owner_id = %s OR owner_id = 'SYSTEM')
        """
        cursor.execute(query, (persona_id, member_id))
        result = cursor.fetchone()

        cursor.close()
        conn.close()

        if result:
            name, prompt = result
            return name, prompt
        else:
            return None, None

    except Exception as e:
        print(f"[ERROR] PostgreSQL 페르소나 조회 중 오류 발생: {str(e)}")
        return None, None


def save_chat_to_db(query: str, response: str, chat_room_id: str, member_id: str):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO chat_messages (message, response, chat_room_id, sender, created_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (query, response, chat_room_id, member_id, datetime.now())
        )

        conn.commit()
        cursor.close()
        conn.close()

        print("[SAVED] chat message saved to DB")
    except Exception as e:
        print(f"[ERROR] Failed to save chat message: {str(e)}")


async def update_chatroom_name_if_first(chat_room_id: int, member_id: str, new_name: str):
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT name FROM chat_room 
            WHERE id = %s AND member_id = %s
        """, (chat_room_id, member_id))
        row = cur.fetchone()

        if row and (row[0] is None or row[0].strip() in "새 채팅방"):
            cur.execute("""
                UPDATE chat_room SET name = %s WHERE id = %s AND member_id = %s
            """, (new_name, chat_room_id, member_id))
            conn.commit()

        cur.close()
        conn.close()
        print("[SAVED] changed chatroom name saved to DB")

    except Exception as e:
        print(f"[ERROR] Failed to save chat message: {str(e)}")