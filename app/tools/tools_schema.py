from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class DomesticITNewsSearchSchema(BaseModel):
    keyword: str = Field(..., description="검색할 주요 키워드")
    date_start: Optional[str] = Field(None, description="검색 시작일 (YYYY-MM-DD), 기본 60일 전")
    date_end: Optional[str] = Field(None, description="검색 종료일 (YYYY-MM-DD), 기본 어제")

class ForeignNewsSearchSchema(BaseModel):
    en_keyword: str = Field(..., description="영문 키워드")
    lang: str = Field("en", description="언어 코드, 기본 'en'")
    country: str = Field("us", description="국가 코드, 기본 'us'")
    max_results: int = Field(10, description="최대 기사 수 (기본 10, 최대 20)")

class CommunitySearchSchema(BaseModel):
    korean_keyword: str = Field(..., description="한국어 키워드")
    english_keyword: str = Field(..., description="영어 키워드")
    platform: str = Field("all", description="'all' | 'daum' | 'naver' | 'reddit'")
    max_results: int = Field(10, description="최대 결과 수")

class SearchWebSchema(BaseModel):
    keyword: str = Field(..., description="검색 키워드")
    max_results: int = Field(10, description="최대 결과 수")

class YoutubeVideoSchema(BaseModel):
    query: str = Field(..., description="검색 키워드")
    max_results: int = Field(5, description="최대 결과 수")

class RequestUrlSchema(BaseModel):
    input_url: str = Field(..., description="HTTP(S) 웹 페이지 또는 PDF 파일의 절대 URL")

class WikipediaSchema(BaseModel):
    query: str = Field(..., description="검색 키워드")

class GoogleTrendsTimeseriesSchema(BaseModel):
    query: str = Field(..., description="검색 키워드")
    start_date: Optional[str] = Field(None, description="시작 날짜 (YYYY-MM-DD), 기본 최근 한 달")
    end_date: Optional[str] = Field(None, description="종료 날짜 (YYYY-MM-DD)")

class GenerateNewsTrendReportSchema(BaseModel):
    date_start: Optional[str] = Field(None, description="시작 날짜 (YYYY-MM-DD), 기본 어제")
    date_end: Optional[str] = Field(None, description="종료 날짜 (YYYY-MM-DD), 기본 어제")

class ITNewsTrendKeywordSchema(BaseModel):
    period: str = Field(..., description="'daily' 또는 'weekly'")
    date: str = Field(..., description="기준 날짜 (YYYY-MM-DD)")

class NamuwikiSchema(BaseModel):
    keyword: str = Field(..., description="검색 키워드")

class StockHistorySchema(BaseModel):
    symbol: str = Field(..., description="티커 심볼")
    start: str = Field(..., description="시작일 (YYYY-MM-DD)")
    end: str = Field(..., description="종료일 (YYYY-MM-DD)")
    auto_adjust: bool = Field(True, description="배당·분할 보정 여부")
    back_adjust: bool = Field(False, description="백어드저스트 여부")

class Dalle3ImageGenerationSchema(BaseModel):
    prompt: str = Field(..., description="사용자 입력 쿼리")

class KRStockHistorySchema(BaseModel):
    symbol: str = Field(..., description="6자리 종목 코드")
    start: str = Field(..., description="시작일 (YYYY-MM-DD)")
    end: str = Field(..., description="종료일 (YYYY-MM-DD)")

class WeatherSchema(BaseModel):
    location: str = Field("Seoul,KR", description="도시명+국가코드 (예: 'Seoul,KR')")
    lang: str = Field("kr", description="언어 (기본 'kr')")
    units: str = Field("metric", description="단위 (기본 'metric')")
    forecast_types: str = Field("current,hourly,daily", description="'current', 'hourly', 'daily' 조합")
    include_extras: bool = Field(True, description="추가 정보 포함 여부")
    today_only: bool = Field(False, description="당일 데이터만 반환 여부")


class PaperSearchSchema(BaseModel):
    query: str = Field(..., description="검색할 논문의 영어 키워드")
    max_results: int = Field(default=5, description="반환할 최대 논문 수 (1~10)", ge=1, le=10)
    start_date: Optional[str] = Field(None, description="검색 시작 날짜 (YYYY-MM-DD)")
    end_date: Optional[str] = Field(None, description="검색 종료 날짜 (YYYY-MM-DD)")
    sort_by: str = Field(default="relevance", description="정렬 기준: 'date' (최신순) 또는 'relevance' (관련도순)")