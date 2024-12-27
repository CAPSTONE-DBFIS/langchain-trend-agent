from langchain.vectorstores import Milvus
from langchain.embeddings.openai import OpenAIEmbeddings
from dotenv import load_dotenv
import os
from pymilvus import connections, Collection, utility

# .env 파일 로드
load_dotenv()

# Milvus 서버 정보
MILVUS_HOST = os.getenv("MILVUS_HOST")
MILVUS_PORT = os.getenv("MILVUS_PORT")

if not MILVUS_HOST or not MILVUS_PORT:
    raise ValueError("MILVUS_HOST 또는 MILVUS_PORT가 .env 파일에 정의되지 않았습니다.")

# Milvus 연결
def connect_to_milvus():
    connections.connect(host=MILVUS_HOST, port=MILVUS_PORT)
    print(f"Milvus에 연결되었습니다: {MILVUS_HOST}:{MILVUS_PORT}")

# 저장된 데이터 조회 함수 (벡터 및 메타데이터 조회)
def verify_data_in_milvus(collection_name="news_article"):
    # 컬렉션이 Milvus에 존재하는지 확인
    if collection_name not in utility.list_collections():
        print(f"컬렉션 '{collection_name}'이 Milvus에 존재하지 않습니다.")
        return
    
    # 컬렉션 로드
    collection = Collection(collection_name)
    print(f"컬렉션 '{collection_name}'이 로드되었습니다.")
    
    # 벡터와 메타데이터를 쿼리하여 존재 여부 확인
    data = collection.query(
        expr="",  # 모든 데이터 조회
        output_fields=["vector", "category", "media_company", "url", "title", "date"],  # 벡터 및 메타데이터 조회
        limit=1,  # 첫 번째 데이터만 조회
    )
    
    if data:
        print("Milvus에 저장된 데이터 샘플 (벡터 + 메타데이터):")
        for doc in data:
            print(doc)  # 벡터 및 메타데이터 출력
    else:
        print("Milvus에 저장된 데이터가 없습니다.")

if __name__ == "__main__":
    try:
        # Milvus 연결
        connect_to_milvus()

        # 데이터 확인 (저장된 벡터 및 메타데이터 조회)
        verify_data_in_milvus()

    except Exception as e:
        print("에러가 발생했습니다:", str(e))