from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, Annotated

class DomesticITNewsSearchSchema(BaseModel):
    keyword: str = Field(..., description="Primary keyword for search")
    date_start: Optional[str] = Field(None, description="Search start date (YYYY-MM-DD), defaults to 60 days ago")
    date_end: Optional[str] = Field(None, description="Search end date (YYYY-MM-DD), defaults to yesterday")

class ForeignNewsSearchSchema(BaseModel):
    en_keyword: str = Field(..., description="English keyword for search")
    lang: str = Field("en", description="Language code, defaults to 'en'")
    country: str = Field("us", description="Country code, defaults to 'us'")
    max_results: int = Field(10, description="Maximum number of articles (default 10, max 20)")

class CommunitySearchSchema(BaseModel):
    korean_keyword: str = Field(..., description="Korean keyword for search")
    english_keyword: str = Field(..., description="English keyword for search")
    platform: str = Field("all", description="Platform: 'all', 'daum', 'naver', 'reddit', 'x'")
    max_results: int = Field(20, description="Maximum number of results (default 20)")

class SearchWebSchema(BaseModel):
    keyword: str = Field(..., description="Search keyword")
    max_results: int = Field(10, description="Maximum number of results (1-20)")

class YoutubeVideoSchema(BaseModel):
    query: str = Field(..., description="Search keyword")
    max_results: int = Field(5, description="Maximum number of results (1-50)")

class RequestUrlSchema(BaseModel):
    input_url: str = Field(..., description="Absolute URL of an HTTP(S) webpage or PDF file")

class WikipediaSchema(BaseModel):
    query: str = Field(..., description="Search keyword")

class GoogleTrendsSchema(BaseModel):
    query: str = Field(..., description="Search keyword")
    start_date: Optional[str] = Field(None, description="Start date (YYYY-MM-DD), defaults to last month")
    end_date: Optional[str] = Field(None, description="End date (YYYY-MM-DD)")

class GlobalITNewsTrendReportSchema(BaseModel):
    date_start: Optional[str] = Field(None, description="Start date (YYYY-MM-DD), defaults to yesterday")
    date_end: Optional[str] = Field(None, description="End date (YYYY-MM-DD), defaults to yesterday")

class ITNewsTrendKeywordSchema(BaseModel):
    period: str = Field(..., description="'daily' or 'weekly'")
    date: str = Field(..., description="Reference date (YYYY-MM-DD)")

class NamuwikiSchema(BaseModel):
    keyword: str = Field(..., description="Search keyword")

class StockHistorySchema(BaseModel):
    symbol: str = Field(..., description="Ticker symbol")
    start: str = Field(..., description="Start date (YYYY-MM-DD)")
    end: str = Field(..., description="End date (YYYY-MM-DD)")

class Dalle3ImageGenerationSchema(BaseModel):
    prompt: str = Field(..., description="Prompt for image generation")

class PaperSearchSchema(BaseModel):
    query: str = Field(..., description="English keyword for paper search")
    max_results: int = Field(default=10, description="Maximum number of papers to return (default 10)", ge=1, le=10)
    start_date: Optional[str] = Field(None, description="Search start date (YYYY-MM-DD) (default 90 days ago)")
    end_date: Optional[str] = Field(None, description="Search end date (YYYY-MM-DD) (default today)")
    sort_by: str = Field(default="relevance", description="Sort by: 'date' (newest) or 'relevance' (most relevant)")