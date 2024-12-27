# milvus.py
import os
from dotenv import load_dotenv
from pymilvus import connections, utility, Collection, FieldSchema, CollectionSchema, DataType

# 환경 변수 로드
load_dotenv()

# Milvus 서버 정보
MILVUS_HOST = os.getenv("MILVUS_HOST")
MILVUS_PORT = os.getenv("MILVUS_PORT")

# Milvus 연결 함수
def connect_to_milvus():
    """
    Milvus 서버에 연결합니다.
    """
    try:
        connections.connect(host=MILVUS_HOST, port=MILVUS_PORT)
        print(f"Milvus에 연결되었습니다: {MILVUS_HOST}:{MILVUS_PORT}")
    except Exception as e:
        print(f"Milvus 연결 실패: {str(e)}")

def delete_collection_if_exists(collection_name):
    """
    지정된 이름의 컬렉션을 삭제합니다. 컬렉션이 없으면 경고 메시지를 출력합니다.
    """
    try:
        if utility.has_collection(collection_name):
            utility.drop_collection(collection_name)
            print(f"컬렉션 '{collection_name}'이 성공적으로 삭제되었습니다.")
        else:
            print(f"컬렉션 '{collection_name}'이 존재하지 않습니다.")
    except Exception as e:
        print(f"컬렉션 삭제 실패: {str(e)}")

# Milvus 컬렉션 생성 함수
def create_collection_if_not_exists(collection_name):
    """
    컬렉션이 존재하지 않으면 생성하고, 존재하면 반환합니다.
    """
    if utility.has_collection(collection_name):
        return Collection(collection_name)
    
    # 컬렉션 필드 정의
    fields = [
        FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),  # ID 필드
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=1536),        # 1536차원의 벡터
        FieldSchema(name="category", dtype=DataType.VARCHAR, max_length=100),        # 카테고리
        FieldSchema(name="media_company", dtype=DataType.VARCHAR, max_length=100),   # 언론사
        FieldSchema(name="url", dtype=DataType.VARCHAR, max_length=300),             # URL
        FieldSchema(name="title", dtype=DataType.VARCHAR, max_length=300),           # 제목
        FieldSchema(name="date", dtype=DataType.VARCHAR, max_length=50)              # 날짜 필드 추가
    ]

    # 컬렉션 스키마 생성
    schema = CollectionSchema(fields=fields, description="뉴스 기사 메타데이터 및 임베딩")
    collection = Collection(name=collection_name, schema=schema)
    print(f"컬렉션 '{collection_name}'이 생성되었습니다.")
    return collection

def insert_into_collection(collection, embeddings, metadata):
    """
    Milvus 컬렉션에 데이터를 삽입합니다.
    """
    try:
        # 데이터 길이 확인
        if not (
            len(embeddings) == len(metadata["category"]) == len(metadata["media_company"]) == 
            len(metadata["url"]) == len(metadata["title"]) == len(metadata["date"])
        ):
            raise ValueError("데이터 길이가 일치하지 않습니다.")

        # Milvus에 삽입할 데이터 배열 생성
        data = [
            embeddings,
            metadata["category"],
            metadata["media_company"],
            metadata["url"],
            metadata["title"],
            metadata["date"],
        ]
        collection.insert(data)
        print(f"{len(embeddings)}개의 데이터를 Milvus에 성공적으로 삽입했습니다.")
    except Exception as e:
        print(f"Milvus에 데이터 삽입 실패: {str(e)}")