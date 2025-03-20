from pymilvus import connections, FieldSchema, CollectionSchema, DataType, Collection, utility
import os
import pandas as pd
from dotenv import load_dotenv
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_milvus import Milvus
from langchain_core.documents import Document

# 환경변수 로드
load_dotenv()

# 설정
COLLECTION_NAME = "foreign_article"
DIMENSION = 768
MILVUS_HOST = os.getenv("MILVUS_HOST")
MILVUS_PORT = os.getenv("MILVUS_PORT")
URI = f"tcp://{MILVUS_HOST}:{MILVUS_PORT}"
ARTICLE_DATA_PATH = "../../data/raw/techcrunch_article.csv"


# Milvus 연결
def connect_milvus():
    connections.connect(alias="default", host=MILVUS_HOST, port=MILVUS_PORT)
    print(f"Milvus에 연결되었습니다: {MILVUS_HOST}:{MILVUS_PORT}")


# 컬렉션 스키마 정의
fields = [
    FieldSchema(name="pk", dtype=DataType.INT64, is_primary=True, auto_id=True),  # 기본 키 (자동 증가)
    FieldSchema(name="title", dtype=DataType.VARCHAR, max_length=255),  # 기사 제목
    FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=65535),  # 기사 내용
    FieldSchema(name="date", dtype=DataType.VARCHAR, max_length=255),  # 기사 날짜
    FieldSchema(name="media_company", dtype=DataType.VARCHAR, max_length=255),  # 기사 본문
    FieldSchema(name="url", dtype=DataType.VARCHAR, max_length=255),  # 기사 URL
    FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=768)  # SBERT 임베딩 벡터
]

collection_schema = CollectionSchema(fields, description="해외 뉴스 기사 메타데이터")


# 컬렉션 생성 및 인덱스 추가
def create_collection(collection_name):
    collection = Collection(name=collection_name, schema=collection_schema)
    print(f"컬렉션 '{collection_name}' 생성 완료")

    # 인덱스 생성 (IVF_FLAT)
    index_params = {
        "metric_type": "L2",          # 유클리드 거리 기반 검색
        "index_type": "IVF_FLAT",     # IVF_FLAT 인덱스 사용
        "params": {"nlist": 128}      # 클러스터 개수 (검색 성능 조정)
    }
    collection.create_index(field_name="embedding", index_params=index_params)
    print(f"컬렉션 '{collection_name}'에 인덱스 생성 완료")


# 컬렉션 삭제
def remove_collection(collection_name):
    if utility.has_collection(collection_name):
        utility.drop_collection(collection_name)
        print(f"컬렉션 '{collection_name}' 삭제 완료")
    else:
        print(f"컬렉션 '{collection_name}'이 존재하지 않습니다.")


# 컬렉션 로드
def load_collection(collection_name):
    collection = Collection(collection_name)
    collection.load()
    print(f"컬렉션 '{collection_name}'이(가) 로드되었습니다.")


# 기사 데이터 저장 (상위 10개만)
def store_article_embedding(collection_name):
    # CSV 파일 로드 (상위 10개 기사만)
    df = pd.read_csv(ARTICLE_DATA_PATH, index_col=False).head(10)
    print(f"총 {len(df)}개의 기사 데이터 로드 완료.")

    # 임베딩 모델 초기화
    embedding = HuggingFaceEmbeddings(model_name="snunlp/KR-SBERT-V40K-klueNLI-augSTS")

    # 텍스트 스플리터 초기화
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=5000, chunk_overlap=200)

    # Milvus 벡터 스토어 초기화
    try:
        vector_store = Milvus(
            embedding_function=embedding,
            collection_name=collection_name,
            connection_args={"uri": URI},
            auto_id=True,
            text_field="desc",
            vector_field="embedding"
        )
        print("Milvus 벡터 스토어 초기화 완료")
    except Exception as e:
        print(f"Milvus 벡터 스토어 초기화 중 오류 발생: {e}")
        return

    # 컬렉션 불러오기
    collection = Collection(collection_name)
    collection.load()

    # Document 객체 생성 및 중복 확인
    new_documents = []
    for _, row in df.iterrows():
        chunks = text_splitter.split_text(row['desc'])  # 긴 본문을 청크로 나누기

        # Milvus에 해당 URL이 존재하는지 조회
        filter_expression = f"url == '{row['url']}'"
        existing_docs = collection.query(
            expr=filter_expression,
            output_fields=["url"]
        )

        if existing_docs:
            print(f"이미 존재하는 문서: {row['url']} -> 저장 생략")
            continue  # 중복이므로 저장 생략

        for chunk in chunks:
            new_documents.append(
                Document(
                    page_content=chunk,
                    metadata={
                        "title": row['title'],
                        "date": row['date'],
                        "url": row['url']
                    }
                )
            )

    # 중복되지 않은 문서 추가
    if new_documents:
        try:
            vector_store.add_documents(documents=new_documents)  # 문서 삽입
            print(f"{len(new_documents)}개의 새 문서가 Milvus에 삽입되었습니다.")
        except Exception as e:
            print(f"문서 삽입 중 오류 발생: {e}")
            if new_documents:
                print("삽입하려는 첫 번째 문서 메타데이터:", new_documents[0].metadata)
    else:
        print("새롭게 삽입할 문서가 없습니다.")



if __name__ == "__main__":
    connect_milvus()
    load_collection(COLLECTION_NAME)
