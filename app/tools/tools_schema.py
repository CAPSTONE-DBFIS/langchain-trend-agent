from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

def _kst_date(days_offset: int = 0) -> str:
    return (datetime.now(ZoneInfo("Asia/Seoul")) + timedelta(days=days_offset)).strftime("%Y-%m-%d")


class DomesticNewsSearchSchema(BaseModel):
    keyword: str = Field(
        ...,
        description="Primary keyword for search."
    )
    start_date: str = Field(
        default_factory=lambda: _kst_date(-30),
        description="Search start date (YYYY-MM-DD). Defaults to 30 days ago in Asia/Seoul (KST)."
    )
    end_date: str = Field(
        default_factory=lambda: _kst_date(-1),
        description="Search end date (YYYY-MM-DD). Defaults to yesterday in Asia/Seoul (KST)."
    )
    articles_per_day: int = Field(
        3,
        ge=1,
        le=10,
        description="Number of articles to fetch per day. Defaults to 3."
    )

class ForeignNewsSearchSchema(BaseModel):
    en_keyword: str = Field(..., description="English keyword for search")
    lang: str = Field("en", description="Language code, defaults to 'en'")
    country: str = Field("us", description="Country code, defaults to 'us'")
    max_results: int = Field(10, description="Maximum number of articles (default 10, max 20)")

class CompetitorAnalysisSchema(BaseModel):
    start_date: str = Field(
        default_factory=lambda: _kst_date(-1),
        description="Analysis start date (YYYY-MM-DD). Defaults to yesterday in Asia/Seoul (KST)."
    )
    end_date: str = Field(
        default_factory=lambda: _kst_date(-1),
        description="Analysis end date (YYYY-MM-DD). Defaults to yesterday in Asia/Seoul (KST)."
    )

class CommunitySearchSchema(BaseModel):
    korean_keyword: str = Field(..., description="Korean keyword for search")
    english_keyword: str = Field(..., description="English keyword for search")
    platform: str = Field("all", description="Platform: 'all', 'daum', 'naver', 'reddit', 'x'")
    max_results: int = Field(20, description="Maximum number of results (default 20)")

class SearchWebSchema(BaseModel):
    keyword: str = Field(..., description="Search keyword")
    max_results: int = Field(10, description="Maximum number of results (1-20)")
    include_images: bool = Field(False, description="Include images in search results")

class YoutubeVideoSchema(BaseModel):
    query: str = Field(..., description="Search keyword")
    max_results: int = Field(
        5, ge=1, le=10, description="Maximum number of results to return (1–10, default 5)"
    )
    order: str = Field("relevance", description="Sorting method: 'relevance', 'date', 'viewCount'")

class RequestUrlSchema(BaseModel):
    input_url: str = Field(..., description="Absolute URL of an HTTP(S) webpage or PDF file")

class WikipediaSchema(BaseModel):
    query: str = Field(..., description="Search keyword")

class GoogleTrendsSchema(BaseModel):
    query: str = Field(
        ...,
        description="Search keyword."
    )
    start_date: str = Field(
        default_factory=lambda: _kst_date(-30),
        description="Start date (YYYY-MM-DD). Defaults to 30 days ago in Asia/Seoul (KST)."
    )
    end_date: str = Field(
        default_factory=lambda: _kst_date(0),
        description="End date (YYYY-MM-DD). Defaults to today in Asia/Seoul (KST)."
    )

class TrendReportSchema(BaseModel):
    start_date: str = Field(
        default_factory=lambda: _kst_date(-1),
        description="Report start date (YYYY-MM-DD). Defaults to yesterday in Asia/Seoul (KST)."
    )
    end_date: str = Field(
        default_factory=lambda: _kst_date(-1),
        description="Report end date (YYYY-MM-DD). Defaults to yesterday in Asia/Seoul (KST)."
    )

class TrendKeywordSchema(BaseModel):
    period: str = Field(..., description="'daily' or 'weekly'")
    date: str = Field(..., description="Reference date (YYYY-MM-DD)")

class NamuwikiSchema(BaseModel):
    keyword: str = Field(..., description="Search keyword")

class StockHistorySchema(BaseModel):
    symbol: str = Field(..., description="Ticker symbol")
    start_date: str = Field(..., description="Start date (YYYY-MM-DD)")
    end_date: str = Field(..., description="End date (YYYY-MM-DD)")

class Dalle3ImageGenerationSchema(BaseModel):
    prompt: str = Field(..., description="Prompt for image generation")

class PaperSearchSchema(BaseModel):
    query: str = Field(
        ...,
        description="English keyword for academic paper search."
    )
    max_results: int = Field(
        10,
        ge=1,
        le=10,
        description="Maximum number of papers to return (default 10, max 10)."
    )
    start_date: str = Field(
        default_factory=lambda: _kst_date(-90),
        description="Search start date (YYYY-MM-DD). Defaults to 90 days ago in Asia/Seoul (KST)."
    )
    end_date: str = Field(
        default_factory=lambda: _kst_date(0),
        description="Search end date (YYYY-MM-DD). Defaults to today in Asia/Seoul (KST)."
    )
    sort_by: str = Field(
        "relevance",
        description="Sort by 'relevance' (default) or 'date' (newest first)."
    )