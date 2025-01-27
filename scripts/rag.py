import os
from dotenv import load_dotenv
import pandas as pd
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_milvus import Milvus
from langchain_core.documents import Document
from pymilvus import connections, FieldSchema, CollectionSchema, DataType, Collection, utility

# 환경변수 로드
load_dotenv()

# 설정(전역 변수)
MODEL = 'snunlp/KR-SBERT-V40K-klueNLI-augSTS'
# COLLECTION_NAME = "news_article"
DIMENSION = 768
MILVUS_HOST = os.getenv("MILVUS_HOST")
MILVUS_PORT = os.getenv("MILVUS_PORT")
URI = f"tcp://{MILVUS_HOST}:{MILVUS_PORT}"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ARTICLE_DATA_PATH = os.path.join(BASE_DIR, '..', 'data', 'raw', 'article_data.csv')

# Milvus 연결 함수
def connect_milvus():
    connections.connect(alias="default", host=MILVUS_HOST, port=MILVUS_PORT)
    print(f"Milvus에 연결되었습니다: {MILVUS_HOST}:{MILVUS_PORT}")

# 컬렉션 삭제 함수
def remove_collection(collection_name):
    if utility.has_collection(collection_name):
        utility.drop_collection(collection_name)
        print(f"기존 컬렉션 '{collection_name}' 삭제 완료")

# 컬렉션 생성 함수
def create_collection(collection_name):
    fields = [
        FieldSchema(name="pk", dtype=DataType.INT64, is_primary=True, auto_id=True),
        FieldSchema(name="title", dtype=DataType.VARCHAR, max_length=255),
        FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=65535),
        FieldSchema(name="date", dtype=DataType.VARCHAR, max_length=255),
        FieldSchema(name="category", dtype=DataType.VARCHAR, max_length=255),
        FieldSchema(name="media_company", dtype=DataType.VARCHAR, max_length=255),
        FieldSchema(name="url", dtype=DataType.VARCHAR, max_length=255),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=DIMENSION)
    ]
    schema = CollectionSchema(fields, description="뉴스 기사 메타데이터")
    
    # 컬렉션 생성
    collection = Collection(name=collection_name, schema=schema)

    # 인덱스 생성
    index_params = {
        "metric_type": "L2",
        "index_type": "IVF_FLAT",
        "params": {"nlist": 128}
    }
    collection.create_index(field_name="embedding", index_params=index_params)
    print(f"컬렉션 '{collection_name}'과 인덱스 생성 완료")

# 문서 임베딩 저장 함수
def store_article_embedding(collection_name):
    # CSV 파일 로드
    df = pd.read_csv(ARTICLE_DATA_PATH, index_col=False)

    # 임베딩 모델 초기화
    embedding = HuggingFaceEmbeddings(model_name=MODEL)

    # 텍스트 스플리터 초기화
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=500)

    # Milvus 벡터 스토어 초기화
    try:
        vector_store = Milvus(
            embedding_function=embedding,
            collection_name=collection_name,
            connection_args={"uri": URI},
            auto_id=True,
            text_field="content",
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
        chunks = text_splitter.split_text(row['content'])  # 긴 본문을 청크로 나누기

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
                        "category": row['category'],
                        "media_company": row['media_company'],
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