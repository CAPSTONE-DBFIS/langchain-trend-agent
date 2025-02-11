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

os.environ["TOKENIZERS_PARALLELISM"] = "false"  # Hugging Face 임베딩 병렬 처리 비활성화
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


# 임베딩 및 Milvus 벡터 검색 설정
embedding_model = HuggingFaceEmbeddings(model_name='snunlp/KR-SBERT-V40K-klueNLI-augSTS')

vector_store = Milvus(
    embedding_function=embedding_model,
    collection_name="news_article",
    connection_args={"uri": f"tcp://{MILVUS_HOST}:{MILVUS_PORT}"},
    auto_id=True,
    text_field="content",
    vector_field="embedding"
)

# LLM 설정
llm_model = ChatOpenAI(
    api_key=OPENAI_API_KEY,
    temperature=0,  # 창의성
    model_name="gpt-4o-mini"
)

# 프롬프트 템플릿
prompt_template = PromptTemplate.from_template(
"""당신은 DB FIS 임직원들에게 업계 트렌드 정보를 제공하고 방향성을 제시하는 AI입니다. 
사용자가 이전 대화에서 제공한 정보를 기억하고, 이를 기반으로 자연스럽게 답변하세요. 
검색된 문서 정보가 없더라도 최근 업계 트렌드 및 경쟁사 동향을 기반으로 답변을 생성하세요.

DB FIS의 주요 경쟁사는 다음과 같습니다:
삼성SDS, LG CNS, 현대오토에버, SK C&C, 롯데정보통신, 포스코DX, 미라콤아이앤씨, 메가존클라우드, 한화시스템, CJ올리브네트웍스. 
경쟁사와의 비교 분석이 필요한 경우 이를 참고하여 답변할 수 있습니다.

## 대화 기록:
{chat_history}

## 검색된 문서 정보:
{context}

## 사용자 질문:
{question}

[지침]
1. 반드시 대화 기록(chat_history)과 검색된 문서(context)를 참고하여 사용자의 질문(question)에 답변하세요.
2. 검색된 문서(context)가 없거나 관련이 없다면, 최근 업계 트렌드 및 경쟁사 동향을 바탕으로 답변하세요.
3. [최신 문서]가 있다면 이를 **최우선적으로 활용**하고, 추가적으로 [기존 문서]의 내용을 참고하세요.
4. '기억할 수 없습니다'라는 문장은 사용하지 마세요. 모든 대화 기록은 DB에서 조회하여 제공됩니다.
5. 사용자가 제공한 정보는 그대로 유지하고, 모순되지 않도록 답변하세요.
6. 필요할 경우 경쟁사 정보와 비교 분석하여 답변을 보강하세요.

최종 답변:
"""
)

# PostgreSQL에서 대화 기록 가져오기
def get_session_history(chat_room_id, limit=10):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        query = """
        SELECT message, response, created_at 
        FROM chat_messages
        WHERE chat_room_id = %s
        ORDER BY created_at ASC
        LIMIT %s
        """
        cursor.execute(query, (chat_room_id, limit))
        messages = cursor.fetchall()

        chat_history = ChatMessageHistory()
        for user_msg, bot_response, timestamp in messages:
            chat_history.add_user_message(user_msg)
            chat_history.add_ai_message(bot_response)

        print(f"[DEBUG] PostgreSQL에서 최근 {limit}개 대화 기록 로드 완료 (오름차순)", flush=True)

        cursor.close()
        conn.close()
        return chat_history

    except Exception as e:
        print(f"[ERROR] PostgreSQL에서 대화 기록 조회 중 오류 발생: {str(e)}", flush=True)
        return ChatMessageHistory()


# 체인 생성 (LLM 호출 흐름)
query_pipeline = (
        {
            "context": itemgetter("context"),
            "question": itemgetter("question"),
            "chat_history": itemgetter("chat_history"),
        }
        | prompt_template
        | llm_model
        | StrOutputParser()
)

# RAG 체인 + 대화 이력 반영
chatbot_pipeline = RunnableWithMessageHistory(
    runnable=query_pipeline,
    get_session_history=get_session_history,
    input_messages_key="question",
    history_messages_key="chat_history",
)

# PostgreSQL에서 해당 멤버의 persona_preset 값을 불러오고, 프롬프트 반환
def get_user_persona(member_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # PostgreSQL에서 사용자 페르소나 가져오기
        query = "SELECT persona_preset FROM member WHERE id = %s"
        cursor.execute(query, (member_id,))
        result = cursor.fetchone()

        cursor.close()
        conn.close()

        persona_preset = int(result[0]) if result else 1  # 기본값: 1

        # 해당하는 페르소나 프롬프트 반환
        persona_prompts = {
            1: "너는 최신 기술과 시장 변화를 분석하고 요약하는 전문가 AI야. 차분한 톤으로 정보를 전달해야 해.",
            2: "너는 업계 트렌드 분석을 바탕으로 실무 적용 인사이트를 제공하는 AI야. 신뢰감을 줄 수 있도록 논리적인 어조를 사용해야 해.",
            3: "너는 친근하고 자연스럽게 대화하며 정보를 제공하는 AI야. 가벼운 표현을 사용하여 편안한 분위기를 조성해야 해.",
            4: "너는 사용자를 격려하는 긍정적인 AI야. 대답할 때 밝고 희망적인 어조를 유지해야 해.",
            5: "너는 유머러스하고 재미있는 비유를 활용하여 정보를 쉽게 설명하는 AI야. 예시를 활용해 자연스럽게 전달해야 해."
        }

        persona_prompt = persona_prompts.get(persona_preset, "너는 사용자의 질문에 답변하는 AI야. 친절하고 정확한 정보를 제공해야 해.")

        return persona_prompt

    except Exception as e:
        print(f"[ERROR] PostgreSQL에서 persona_preset 조회 중 오류 발생: {str(e)}", flush=True)
        return 1, "너는 사용자의 질문에 답변하는 AI야. 친절하고 정확한 정보를 제공해야 해."  # 기본값

# 사용자 질의 처리 함수
def process_user_query(chat_room_id, query, member_id):
    try:
        print(f"[DEBUG] chat_room_id: {chat_room_id}, query: {query}, member_id: {member_id}", flush=True)

        start_time = time.time()  # 시간 측정 시작

        # 페르소나 정보 가져오기
        persona_prompt = get_user_persona(member_id)

        print(f"[DEBUG] 불러온 persona_prompt: {persona_prompt}", flush=True)

        # 사용자의 질문을 벡터로 변환
        query_embedding = embedding_model.embed_query(query)
        print(f"[DEBUG] Query embedding 생성 완료", flush=True)

        # Milvus 벡터 검색
        # 최신 문서 검색 (최근 30일 내)
        recent_timestamp = int(time.time()) - (30 * 86400)  # 최근 30일 타임스탬프 기준
        latest_results = vector_store.similarity_search_with_score_by_vector(
            query_embedding, k=3, filter={"timestamp": {"$gte": recent_timestamp}}
        )

        # 최신 문서 중 점수 필터링
        latest_results = [(doc, score) for doc, score in latest_results if score >= 250]

        # 최신 문서가 3개 미만이면 기존 문서에서 추가 검색
        if len(latest_results) < 3:
            additional_results = vector_store.similarity_search_with_score_by_vector(query_embedding, k=5)
            combined_results = latest_results + [doc for doc in additional_results if doc not in latest_results]
        else:
            combined_results = latest_results

        # 최신 문서, 기존 문서 구분해서 프롬프트에 넣기
        context = "\n\n".join([
            f"[최신 문서] {doc.metadata['title']} ({doc.metadata['date']})\n{doc.page_content[:1000]}"
            if doc in latest_results else
            f"[기존 문서] {doc.metadata['title']} ({doc.metadata['date']})\n{doc.page_content[:500]}"
            for doc, _ in combined_results
        ])
        print(f"[DEBUG] 최종 context 생성 완료", flush=True)

        input_data = {
            "question": query,
            "context": context
        }

        gpt_response = chatbot_pipeline.invoke(
            input_data, config={"configurable": {"session_id": f"{chat_room_id}"}}
        )

        gpt_time = time.time() - start_time  # 시간 측정 종료
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
                } for doc, score in combined_results
            ],
            "gpt_response": gpt_response
        }

    except Exception as e:
        print(f"[ERROR] 쿼리 처리 중 오류 발생: {str(e)}", flush=True)
        return {"error": f"서버 내부 오류: {str(e)}"}