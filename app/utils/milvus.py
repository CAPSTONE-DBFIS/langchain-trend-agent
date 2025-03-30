import os
from dotenv import load_dotenv
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_milvus import Milvus

# 환경 변수 로드
load_dotenv()

os.environ["TOKENIZERS_PARALLELISM"] = "false"

def get_embedding_model():
    """HuggingFace 임베딩 모델을 반환"""
    return HuggingFaceEmbeddings(model_name='snunlp/KR-SBERT-V40K-klueNLI-augSTS')

def get_vector_store():
    """Milvus 벡터 저장소를 반환"""
    return Milvus(
        embedding_function=get_embedding_model(),
        collection_name="news_article",
        connection_args={"uri": f"tcp://{os.getenv("MILVUS_HOST")}:{os.getenv("MILVUS_PORT")}"},
        auto_id=True,
        text_field="content",
        vector_field="embedding"
    )