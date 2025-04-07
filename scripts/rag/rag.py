import os
from dotenv import load_dotenv
import pandas as pd
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_milvus import Milvus
from langchain_core.documents import Document
from pymilvus import connections, FieldSchema, CollectionSchema, DataType, Collection, utility

# Huggingface Tokenizer의 멀티스레딩 비활성화
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# 환경변수 로드
load_dotenv()

# 설정(전역 변수)
MODEL = 'snunlp/KR-SBERT-V40K-klueNLI-augSTS'
DIMENSION = 768
MILVUS_HOST = os.getenv("MILVUS_HOST")
MILVUS_PORT = os.getenv("MILVUS_PORT")
URI = f"tcp://{MILVUS_HOST}:{MILVUS_PORT}"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ARTICLE_DATA_PATH_1 = "../../data/raw/article_data.csv"
ARTICLE_DATA_PATH_2 = "../../data/raw/techcrunch_article.csv"


# news_article 컬렉션에 사용할 필드
domestic_field = [
    FieldSchema(name="pk", dtype=DataType.INT64, is_primary=True, auto_id=True),
    FieldSchema(name="title", dtype=DataType.VARCHAR, max_length=255),
    FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=65535),
    FieldSchema(name="date", dtype=DataType.VARCHAR, max_length=255),
    FieldSchema(name="category", dtype=DataType.VARCHAR, max_length=255),
    FieldSchema(name="media_company", dtype=DataType.VARCHAR, max_length=255),
    FieldSchema(name="url", dtype=DataType.VARCHAR, max_length=255),
    FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=DIMENSION)
]

# foreign_article 컬렉션에 사용할 필드 (예: category 필드 없음)
foreign_fields = [
    FieldSchema(name="pk", dtype=DataType.INT64, is_primary=True, auto_id=True),
    FieldSchema(name="title", dtype=DataType.VARCHAR, max_length=255),
    FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=65535),
    FieldSchema(name="date", dtype=DataType.VARCHAR, max_length=255),
    FieldSchema(name="media_company", dtype=DataType.VARCHAR, max_length=255),
    FieldSchema(name="url", dtype=DataType.VARCHAR, max_length=255),
    FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=DIMENSION)
]


# Milvus 연결 함수
def connect_milvus():
    connections.connect(alias="default", host=MILVUS_HOST, port=MILVUS_PORT)
    print(f"Milvus에 연결되었습니다: {MILVUS_HOST}:{MILVUS_PORT}")


# 컬렉션 생성 함수.
def create_collection(collection_name, fields, description="컬렉션 생성"):
    # 스키마 생성
    schema = CollectionSchema(fields, description=description)
    # 컬렉션 생성
    collection = Collection(name=collection_name, schema=schema)

    # 인덱스 생성 (여기서는 embedding 필드가 있다고 가정)
    index_params = {
        "metric_type": "L2",
        "index_type": "IVF_FLAT",
        "params": {"nlist": 128}
    }
    collection.create_index(field_name="embedding", index_params=index_params)
    print(f"컬렉션 '{collection_name}'이(가) 생성되었으며 인덱스가 추가되었습니다.")
    return collection


# 국내 기사 컬렉션 생성
def create_domestic():
    create_collection("news_article", domestic_field, description="뉴스 기사 메타데이터")


# 해외 기사 컬렉션 생성
def create_foreign():
    create_collection("foreign_article", foreign_fields, description="해외 뉴스 기사 메타데이터")


# 컬렉션 삭제 함수
def remove_collection(collection_name):
    if utility.has_collection(collection_name):
        utility.drop_collection(collection_name)
        print(f"기존 컬렉션 '{collection_name}' 삭제 완료")


# 문서 임베딩 저장 함수
def store_article_embedding(
        collection_name,
        article_data_path,
        text_field,
        metadata_mapping,
        chunk_size=2000,
        chunk_overlap=200
):
    """
        Milvus 컬렉션에 데이터를 저장합니다.

        Args:
            collection_name,    # 컬렉션 이름
            article_data_path,  # 데이터 경로
            text_field,         # 읽어올 컬럼 이름
            metadata_mapping,   # 예: {"title": "title", "date": "date", "category": "category", ...}
            chunk_size=2000,    # 텍스트 분할시 사이즈
            chunk_overlap=200   # 텍스트 중첩 길이
    """

    # CSV 파일 로드
    df = pd.read_csv(article_data_path, index_col=False)

    # 임베딩 모델 초기화
    embedding = HuggingFaceEmbeddings(model_name=MODEL)

    # 텍스트 스플리터 초기화
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    # Milvus 벡터 스토어 초기화
    try:
        vector_store = Milvus(
            embedding_function=embedding,
            collection_name=collection_name,
            connection_args={"uri": URI},
            auto_id=True,
            text_field=text_field,
            vector_field="embedding"
        )
        print("Milvus 벡터 스토어 초기화 완료")
    except Exception as e:
        print(f"Milvus 벡터 스토어 초기화 중 오류 발생: {e}")
        return

    # 컬렉션 불러오기
    collection = Collection(collection_name)
    collection.load()

    new_documents = []
    for _, row in df.iterrows():
        text_content = row.get(text_field, None)

        # 본문 타입 예외 처리
        if not isinstance(text_content, str):
            print(f"유효하지 않은 텍스트 데이터 (index: {_}): {text_content}")
            continue  # 텍스트가 아니면 건너뜀

        if len(text_content.strip()) == 0:
            print(f"빈 텍스트 데이터 (index: {_})")
            continue  # 빈 문자열이면 건너뜀

        try:
            chunks = text_splitter.split_text(text_content)
        except Exception as e:
            print(f"텍스트 분할 중 오류 발생 (index: {_}): {e}")
            continue

        # 중복 확인 (URL 기준)
        filter_expression = f"url == '{row['url']}'"
        existing_docs = collection.query(
            expr=filter_expression,
            output_fields=["url"]
        )

        if existing_docs:
            continue

        # 메타데이터 생성: metadata_mapping의 키는 Document 메타데이터의 키, 값은 CSV 컬럼 이름
        metadata = {key: row[csv_key] for key, csv_key in metadata_mapping.items()}

        for chunk in chunks:
            new_documents.append(
                Document(
                    page_content=chunk,
                    metadata=metadata
                )
            )

    # 새 문서 추가
    if new_documents:
        try:
            vector_store.add_documents(documents=new_documents)
            print(f"{len(new_documents)}개의 새 문서가 Milvus에 삽입되었습니다.")
        except Exception as e:
            print(f"문서 삽입 중 오류 발생: {e}")
            if new_documents:
                print("첫 번째 문서 메타데이터:", new_documents[0].metadata)
    else:
        print("새롭게 삽입할 문서가 없습니다.")


# 국내 기사 저장
def store_domestic():
    connect_milvus()

    # news_article 컬렉션에 필요한 메타데이터 매핑 설정
    news_metadata_mapping = {
        "title": "title",
        "date": "date",
        "category": "category",
        "media_company": "media_company",
        "url": "url"
    }

    store_article_embedding(
        collection_name="news_article",
        article_data_path=ARTICLE_DATA_PATH_1,                 # CSV 파일 경로
        text_field="content",                                  # 텍스트를 분할할 컬럼
        metadata_mapping=news_metadata_mapping,
        chunk_size=2000,                                       # 청크 크기
        chunk_overlap=200                                      # 청크 간 중첩 길이
    )


# 해외 기사 저장
def store_foreign():
    # foreign_article 컬렉션에 필요한 메타데이터 매핑 설정 (예: category 필드가 없을 경우)
    foreign_metadata_mapping = {
        "title": "title",
        "date": "date",
        "media_company": "media_company",
        "url": "url"
    }

    store_article_embedding(
        collection_name="foreign_article",
        article_data_path=ARTICLE_DATA_PATH_2,                  # 다른 CSV 파일 경로
        text_field="content",                                   # 동일하게 텍스트 분할 컬럼 지정
        metadata_mapping=foreign_metadata_mapping,
        chunk_size=5000,                                        # foreign_article에 맞는 청크 크기 조정
        chunk_overlap=200                                       # 청크 중첩 길이
    )


# 컬렉션 로드
def load_collection(collection_name):
    collection = Collection(collection_name)
    collection.load()
    print(f"컬렉션 '{collection_name}'이(가) 로드되었습니다.")


def show_all_articles(collection_name, output_fields=None, query_expr="pk >= 0", limit=100):
    """
    Milvus 컬렉션의 데이터를 조회하고 출력합니다.

    Args:
        collection_name (str): 조회할 컬렉션의 이름.
        output_fields (list, optional): 출력할 필드 리스트. 기본값은 None인 경우 기본 필드 사용.
        query_expr (str, optional): Milvus 쿼리 표현식. 기본값은 "pk >= 0".
        limit (int, optional): 조회 제한 수.
    """
    # 기본 출력 필드 설정 (필요에 따라 변경)
    if output_fields is None:
        output_fields = ["pk", "title", "date", "media_company", "url"]

    collection = Collection(collection_name)
    collection.load()

    results = collection.query(
        expr=query_expr,
        output_fields=output_fields,
        limit=limit
    )

    # 조회 결과를 동적으로 출력 (출력 형식은 자유롭게 커스터마이즈 가능)
    for i, r in enumerate(results):
        # 예시: 각 필드의 값을 key: value 형식으로 출력
        print(f"[{i + 1}]")
        for field in output_fields:
            print(f"{field}: {r.get(field)}")
        print("-" * 40)


# 국내 기사 조회
def show_domestic(count=10):
    show_all_articles("news_article", limit=count)


# 해외 기사 조회
def show_foreign(count=10):
    custom_fields = ["pk", "title", "date", "media_company", "url", "content"]
    show_all_articles("foreign_article", output_fields=custom_fields, limit=count)
