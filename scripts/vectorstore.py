from langchain.vectorstores import Milvus
from langchain.embeddings.openai import OpenAIEmbeddings
from dotenv import load_dotenv
import os

# 환경 변수(.env) 로드
load_dotenv()

# Milvus 설정
MILVUS_HOST = os.getenv("MILVUS_HOST")
MILVUS_PORT = os.getenv("MILVUS_PORT")

if not MILVUS_HOST or not MILVUS_PORT:
    raise ValueError("Milvus 호스트와 포트가 .env 파일에 정의되지 않았습니다.")

# OpenAI 임베딩 설정
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("OpenAI API 키가 .env 파일에 정의되지 않았습니다.")
embeddings = OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY)

# Milvus 기반 LangChain VectorStore 초기화 함수
def initialize_vectorstore(collection_name="news_article"):
    vectorstore = Milvus(
        embedding_function=embeddings,
        connection_args={"host": MILVUS_HOST, "port": MILVUS_PORT},
        collection_name=collection_name  # 컬렉션 이름을 명시적으로 지정
    )
    print(f"VectorStore가 초기화되었습니다. 컬렉션: {collection_name}")
    return vectorstore

# VectorStore 문서 추가 함수
def add_documents_to_vectorstore(vectorstore, documents):
    try:
        vectorstore.add_texts(
            texts=[doc["text"] for doc in documents],
            metadatas=[doc["metadata"] for doc in documents],
        )
        print("VectorStore에 문서가 성공적으로 추가되었습니다.")
    except Exception as e:
        print(f"VectorStore 문서 추가 중 오류 발생: {e}")


# Milvus에 존재하는 모든 컬렉션 이름을 조회하는 함수
def list_collections():
    collections = utility.list_collections()  # 모든 컬렉션 이름을 반환
    if collections:
        print("현재 Milvus에 저장된 컬렉션들:")
        for collection_name in collections:
            print(collection_name)
        return collections
    else:
        print("Milvus에 컬렉션이 없습니다.")
        return []

# 특정 컬렉션 삭제하는 함수
def delete_collection(collection_name):
    collection = Collection(collection_name)
    collection.drop()  # 컬렉션 삭제
    print(f"컬렉션 '{collection_name}'이 Milvus에서 삭제되었습니다.")

# 모든 컬렉션 삭제 함수
def delete_all_collections():
    collections = utility.list_collections()  # 모든 컬렉션 이름을 반환
    if collections:
        print("Milvus에 존재하는 컬렉션들:")
        for collection_name in collections:
            print(f"삭제 중: {collection_name}")
            collection = Collection(collection_name)
            collection.drop()  # 컬렉션 삭제
            print(f"컬렉션 '{collection_name}'이 삭제되었습니다.")
    else:
        print("Milvus에 삭제할 컬렉션이 없습니다.")