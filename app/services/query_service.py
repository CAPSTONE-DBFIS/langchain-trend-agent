import time
import os
import psycopg2
from dotenv import load_dotenv
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_milvus import Milvus
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.output_parsers import StrOutputParser
from langchain_community.chat_message_histories import ChatMessageHistory
from operator import itemgetter

# 환경 변수 로드
load_dotenv()

MILVUS_HOST = os.getenv("MILVUS_HOST")
MILVUS_PORT = os.getenv("MILVUS_PORT")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_PORT = os.getenv("DB_PORT")

# PostgreSQL 연결 함수
def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        port=DB_PORT
    )

# 임베딩 및 Milvus 설정
embedding = HuggingFaceEmbeddings(model_name='snunlp/KR-SBERT-V40K-klueNLI-augSTS')
vector_store = Milvus(
    embedding_function=embedding,
    collection_name="news_article",
    connection_args={"uri": f"tcp://{MILVUS_HOST}:{MILVUS_PORT}"},
    auto_id=True,
    text_field="content",
    vector_field="embedding"
)

# llm 설정
llm = ChatOpenAI(
    api_key=OPENAI_API_KEY,
    temperature=0,  # 창의성
    model_name="gpt-4o-mini"  # 모델명
)

# 프롬프트
prompt = PromptTemplate.from_template(
    """당신은 사용자의 질문에 답변하는 AI 어시스턴트입니다. 
사용자가 이전 대화에서 제공한 정보를 기억하고, 이를 기반으로 자연스럽게 답변하세요. 
검색된 문서 정보가 없더라도 일반적인 배경 지식을 바탕으로 답변을 제공해야 합니다.

## 대화 기록:
{chat_history}

## 검색된 문서 정보:
{context}

## 사용자 질문:
{question}

[지침]
1. 반드시 대화 기록(chat_history)을 참고하여 답변하세요.
2. 검색된 문서(context)가 없더라도, 일반적인 정보를 바탕으로 답변하세요.
3. "기억할 수 없습니다"라는 문장은 사용하지 마세요. 모든 대화 기록은 db에서 조회해서 당신에게 제공하고 있습니다.
4. 사용자가 제공한 정보는 그대로 유지하고, 모순된 답변을 하지 마세요.

최종 답변:
"""
)

# PostgreSQL에서 직접 대화 기록 가져오기
def get_session_history(chat_room_id):
    """PostgreSQL에서 해당 채팅방의 대화 기록을 불러옴"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        query = """
        SELECT message, response, created_at FROM chat_messages
        WHERE chat_room_id = %s
        ORDER BY created_at ASC
        """
        cursor.execute(query, (chat_room_id,))
        messages = cursor.fetchall()

        chat_history = ChatMessageHistory()
        for user_msg, bot_response, timestamp in messages:
            chat_history.add_user_message(user_msg)
            chat_history.add_ai_message(bot_response)

        print(f"[DEBUG] PostgreSQL에서 대화 기록 로드 완료 ({len(messages)}개 메시지)", flush=True)

        cursor.close()
        conn.close()
        return chat_history

    except Exception as e:
        print(f"[ERROR] PostgreSQL에서 대화 기록 조회 중 오류 발생: {str(e)}", flush=True)
        return ChatMessageHistory()

# 체인 생성
chain = (
    {
        "context": itemgetter("question"),
        "question": itemgetter("question"),
        "chat_history": itemgetter("chat_history"),
    }
    | prompt
    | llm
    | StrOutputParser()
)

# RAG 체인 생성
rag_with_history = RunnableWithMessageHistory(
    runnable=chain,
    get_session_history=get_session_history,  # PostgreSQL에서 대화 기록 불러오기
    input_messages_key="question",
    history_messages_key="chat_history",
)

def process_user_query(chat_room_id, query):
    try:
        print(f"[DEBUG] chat_room_id: {chat_room_id}, query: {query}", flush=True)

        start_time = time.time()
        query_embedding = embedding.embed_query(query)
        print(f"[DEBUG] Query embedding 생성 완료", flush=True)

        search_results = vector_store.similarity_search_with_score_by_vector(query_embedding, k=5)
        search_time = time.time() - start_time

        scores = [score for _, score in search_results]
        print(f"[DEBUG] 검색된 문서 점수 목록: {scores}", flush=True)

        print(f"[DEBUG] 검색 완료, 소요 시간: {search_time:.4f}초", flush=True)

        filtered_results = [(doc, score) for doc, score in search_results if score >= 300] # threshold 값 지정

        if not filtered_results:
            print("[WARNING] 관련 문서 없음, GPT에게 일반 답변 요청", flush=True)
            context = "현재 검색된 문서가 없습니다. 일반적인 정보를 바탕으로 답변해 주세요."
        else:
            context = "\n\n".join([
                f"제목: {doc.metadata['title']}\n내용: {doc.page_content}" for doc, _ in filtered_results
            ])
            print(f"[DEBUG] 필터링된 Context 생성 완료", flush=True)

        input_data = {
            "question": query,
            "context": context
        }

        start_time = time.time()
        gpt_response = rag_with_history.invoke(
            input_data, config={"configurable": {"session_id": f"{chat_room_id}"}}
        )
        gpt_time = time.time() - start_time

        print(f"[DEBUG] GPT 응답 생성 완료, 소요 시간: {gpt_time:.4f}초", flush=True)

        return {
            "query": query,
            "search_results": [
                {
                    "title": doc.metadata["title"],
                    "date": doc.metadata["date"],
                    "category": doc.metadata["category"],
                    "url": doc.metadata["url"],
                    "score": score
                } for doc, score in filtered_results
            ],
            "gpt_response": gpt_response
        }

    except Exception as e:
        print(f"[ERROR] 쿼리 처리 중 오류 발생: {str(e)}", flush=True)
        return {"error": f"서버 내부 오류: {str(e)}"}
