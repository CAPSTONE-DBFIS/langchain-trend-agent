from pymilvus import connections, Collection, utility
from dotenv import load_dotenv
import os

# .env 파일 로드
load_dotenv()

# Milvus 서버 정보
MILVUS_HOST = os.getenv("MILVUS_HOST")
MILVUS_PORT = os.getenv("MILVUS_PORT")

if not MILVUS_HOST or not MILVUS_PORT:
    raise ValueError("MILVUS_HOST 또는 MILVUS_PORT가 .env 파일에 정의되어 있지 않습니다.")

def connect_to_milvus():
    connections.connect(host=MILVUS_HOST, port=MILVUS_PORT)
    print(f"Milvus에 연결되었습니다: {MILVUS_HOST}:{MILVUS_PORT}")

def create_index(collection_name):
    collection = Collection(collection_name)
    if not collection.has_index():
        print(f"컬렉션 '{collection_name}'에 인덱스를 생성 중...")
        index_params = {
            "index_type": "IVF_FLAT",
            "metric_type": "L2",
            "params": {"nlist": 128},
        }
        collection.create_index(field_name="embedding", index_params=index_params)
        print(f"컬렉션 '{collection_name}'에 인덱스가 생성되었습니다.")
    else:
        print(f"컬렉션 '{collection_name}'에 이미 인덱스가 존재합니다.")

def load_collection(collection_name):
    if collection_name not in utility.list_collections():
        print(f"컬렉션 '{collection_name}'이 존재하지 않습니다.")
        return None
    collection = Collection(collection_name)
    print(f"컬렉션 '{collection_name}' 로드 중...")
    collection.load()
    print(f"컬렉션 '{collection_name}'이 로드되었습니다.")
    return collection

def query_collection(collection_name):
    collection = load_collection(collection_name)
    if not collection:
        return

    print(f"컬렉션 '{collection_name}'의 데이터 샘플 (1개):")
    data = collection.query(
        expr="",  # 전체 데이터 조회
        output_fields=["embedding", "category", "media_company", "url", "title", "date"],  # date 필드 추가
        limit=1,
    )
    if data:
        print("데이터 1:", data[0])  # 첫 번째 데이터만 출력
    else:
        print("데이터가 없습니다.")

if __name__ == "__main__":
    try:
        # Milvus 연결
        connect_to_milvus()

        # 컬렉션 이름
        collection_name = "news_articles"

        # 인덱스 생성
        create_index(collection_name)

        # 데이터 쿼리
        query_collection(collection_name)

    except Exception as e:
        print("에러가 발생했습니다:", str(e))