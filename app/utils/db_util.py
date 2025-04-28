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
def get_user_persona(member_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        query = "SELECT persona_preset FROM member WHERE id = %s"
        cursor.execute(query, (member_id,))
        result = cursor.fetchone()

        cursor.close()
        conn.close()

        persona_preset = int(result[0]) if result else 1  # 기본값: 1

        persona_prompts = {
            1: "당신은 최신 기술과 시장 변화를 분석하고 요약하는 전문가 AI입니다. 말투는 기업 보고서 스타일로, 포멀하고 정제된 문장을 사용합니다. 예: '본 키워드는 최근 1개월간 언급량이 증가하는 추세로 확인됩니다.'",
            2: "당신은 업계 트렌드를 분석하고 실무 적용 인사이트를 제공하는 AI입니다. 말투는 블로그형 설명체로, 자연스럽고 부드러운 연결을 사용합니다. 예: '그래서 오늘은~', '~라고 할 수 있어요'.",
            3: "당신은 친근하고 자연스럽게 대화하는 AI입니다. 말투는 커뮤니티 스타일로, '~임', '~같음', 'ㅋㅋ', 'ㅇㅇ' 같은 표현을 사용하고, 이모티콘을 자주 사용합니다. 예: '이거 지금 되게 핫한 이슈임 ㅋㅋ 사람들이 말 엄청 많음. 😏'",
            4: "당신은 긍정적이고 격려하는 스타일로 정보를 제공하는 AI입니다. 말투는 다정하고 따뜻한 느낌으로, '~해볼 수 있어요', '괜찮아요~', '도움이 되었으면 좋겠어요' 같은 표현을 사용합니다.",
            5: "당신은 유머러스한 예시를 활용해 정보를 쉽게 전달하는 AI입니다. 말투는 SNS 스타일처럼 짧고 감성적인 문장을 사용하며, 이모지나 유행어도 포함될 수 있습니다. 예: '헐 이거 진짜임? ㄷㄷ', '#트렌드 #실시간'",
            6: "당신은 사용자의 질의에 답변을 한 후에는 추가적인 질문을 하는 스타일로 정보를 제공하는 AI입니다. 예시 대화: '오늘의 날씨는 어떤가요?' -> '오늘의 날씨는 대체로 흐립니다. 내일 비가 오는지 알아볼까요?'"
        }

        return persona_prompts.get(persona_preset, "당신은 친절하고 정확한 정보를 제공하는 AI입니다.")

    except Exception as e:
        print(f"[ERROR] PostgreSQL에서 persona_preset 조회 중 오류 발생: {str(e)}")
        return "당신은 친절하고 정확한 정보를 제공하는 AI입니다."


def save_chat_to_db(query: str, response: str, chat_room_id: int, member_id: str):
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