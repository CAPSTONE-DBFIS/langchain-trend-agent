from sqlalchemy import create_engine, Column, Integer, String, Date, ForeignKey, Text
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from dotenv import load_dotenv
import os

# .env 파일 로드
load_dotenv()

# 환경 변수에서 DB 설정 불러오기
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# SQLAlchemy 엔진 설정
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

# TrackingKeyword 모델 정의
class TrackingKeyword(Base):
    __tablename__ = "tracking_keywords"

    id = Column(Integer, primary_key=True, index=True)
    keyword = Column(String, nullable=False)
    requester_id = Column(String, nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date)
    created_at = Column(Date)

    tracking_results = relationship("TrackingResult", back_populates="tracking_keyword")



class TrackingResult(Base):
    __tablename__ = 'tracking_results'

    id = Column(Integer, primary_key=True, index=True)
    tracking_keyword_id = Column(Integer, ForeignKey('tracking_keywords.id'), nullable=False)
    collected_date = Column(Date, nullable=False)
    article_count = Column(Integer, nullable=True)

    article_title_1 = Column(String(255), nullable=True)
    article_link_1 = Column(String(500), nullable=True)
    comment_count_1 = Column(Integer, nullable=True)
    positive_count_1 = Column(Integer, nullable=True)
    negative_count_1 = Column(Integer, nullable=True)
    neutral_count_1 = Column(Integer, nullable=True)

    article_title_2 = Column(String(255), nullable=True)
    article_link_2 = Column(String(500), nullable=True)
    comment_count_2 = Column(Integer, nullable=True)
    positive_count_2 = Column(Integer, nullable=True)
    negative_count_2 = Column(Integer, nullable=True)
    neutral_count_2 = Column(Integer, nullable=True)

    article_title_3 = Column(String(255), nullable=True)
    article_link_3 = Column(String(500), nullable=True)
    comment_count_3 = Column(Integer, nullable=True)
    positive_count_3 = Column(Integer, nullable=True)
    negative_count_3 = Column(Integer, nullable=True)
    neutral_count_3 = Column(Integer, nullable=True)

    overall_description = Column(Text, nullable=True)

    # 관계 설정 추가
    tracking_keyword = relationship("TrackingKeyword", back_populates="tracking_results")


# 테이블 생성하기
# Base.metadata.create_all(bind=engine)