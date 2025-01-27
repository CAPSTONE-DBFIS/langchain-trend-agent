import time
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_milvus import Milvus
from langchain_openai import ChatOpenAI
import os
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

# 설정값 로드
MODEL = 'snunlp/KR-SBERT-V40K-klueNLI-augSTS'
MILVUS_HOST = os.getenv("MILVUS_HOST")
MILVUS_PORT = os.getenv("MILVUS_PORT")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

URI = f"tcp://{MILVUS_HOST}:{MILVUS_PORT}"
COLLECTION_NAME = "news_article"

# 임베딩 및 Milvus 설정
embedding = HuggingFaceEmbeddings(model_name=MODEL)
vector_store = Milvus(
    embedding_function=embedding,
    collection_name=COLLECTION_NAME,
    connection_args={"uri": URI},
    auto_id=True,
    text_field="content",
    vector_field="embedding"
)

chat_model = ChatOpenAI(
    api_key=OPENAI_API_KEY,
    model_name="gpt-4o-mini"
)

# 사용자 쿼리 임베딩 변환 및 semantic search, GPT 응답 반환
def process_user_query(query):
    try:
        # 1. 쿼리 임베딩 생성 및 유사 문서 검색
        start_time = time.time()  # 시작 시간 기록
        query_embedding = embedding.embed_query(query)
        search_results = vector_store.similarity_search_with_score_by_vector(query_embedding, k=5)
        search_time = time.time() - start_time  # 종료 시간 기록

        print(f"임베딩 생성 및 검색 시간: {search_time:.4f}초")

        if not search_results:
            return {"error": "관련 문서를 찾을 수 없습니다."}

        # 검색된 문서 컨텍스트 생성
        context = "\n\n".join([f"제목: {doc.metadata['title']}\n내용: {doc.page_content}" for doc, _ in search_results])

        # 2. GPT 프롬프트 생성 및 응답
        gpt_input = f"다음 문서를 참고하여 질문에 답변해주세요:\n\n{context}\n\n사용자 질문: {query}"

        # GPT 모델로부터 응답 받기
        start_time = time.time()  # 시작 시간 기록
        gpt_response = chat_model.invoke(gpt_input)
        gpt_time = time.time() - start_time  # 종료 시간 기록

        print(f"GPT 응답 생성 시간: {gpt_time:.4f}초")

        # 최종 결과 반환
        return {
            "query": query,
            "search_results": [
                {
                    "title": doc.metadata["title"],
                    "date": doc.metadata["date"],
                    "category": doc.metadata["category"],
                    "url": doc.metadata["url"],
                    "score": score
                } for doc, score in search_results
            ],
            "gpt_response": gpt_response.content
        }

    except Exception as e:
        raise RuntimeError(f"쿼리 처리 중 오류 발생: {str(e)}")