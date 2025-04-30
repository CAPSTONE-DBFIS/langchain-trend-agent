import os
import io
import json
import re
import openai
import time
import asyncio
from uuid import uuid4
from datetime import datetime, timedelta, timezone
from dateutil import parser

from zoneinfo import ZoneInfo
from typing import Optional, List, Dict, Any, Union
from urllib.parse import quote
import aiohttp
import logging

import requests
from requests.auth import HTTPBasicAuth
import wikipedia
import yfinance as yf
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from pypdf import PdfReader
from googleapiclient.discovery import build
from docx import Document
from docx.shared import Inches
import matplotlib
matplotlib.use('Agg')  # 백엔드 설정
import matplotlib.pyplot as plt
from fake_useragent import UserAgent
from elasticsearch import Elasticsearch
from functools import wraps
import FinanceDataReader as fdr

from langchain.prompts import PromptTemplate
from langchain.chat_models import ChatOpenAI
from langchain.chains.llm import LLMChain
from langchain.tools import tool
from langchain_community.tools import WikipediaQueryRun
from langchain_tavily import TavilySearch
from langchain_community.utilities import WikipediaAPIWrapper

from app.utils.milvus_util import get_embedding_model, get_domestic_article_vector_store
from app.utils.db_util import get_db_connection
from app.utils.redis_util import get_redis_client

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def async_time_logger(name: str):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start = time.perf_counter()
            result = await func(*args, **kwargs)
            end = time.perf_counter()
            logger.info(f"[{name}] 실행 시간: {(end - start):.3f}초")
            return result
        return wrapper
    return decorator

load_dotenv()
KST = timezone(timedelta(hours=9))

@async_time_logger("rag_news_search")
async def rag_news_search(query: str, date_start: str, date_end: str) -> List[Dict[str, Union[str, float]]]:
    """
    Milvus에서 RAG를 이용한 의미 기반 IT 뉴스 기사 검색 도구 (기간 필터 포함).
    """
    # redis 캐시 조회
    r = get_redis_client()
    cache_key = f"news:rag:{query}:{date_start}:{date_end}"
    cached = r.get(cache_key)
    if cached:
        return json.loads(cached)

    embedding_model = get_embedding_model()
    vector_store = get_domestic_article_vector_store()

    query_embedding = embedding_model.embed_query(query)
    start_ts = int(datetime.strptime(date_start, "%Y-%m-%d").timestamp())
    end_ts = int(datetime.strptime(date_end, "%Y-%m-%d").timestamp())

    results = vector_store.similarity_search_with_score_by_vector(
        query_embedding, k=5, filter={"timestamp": {"$gte": start_ts, "$lte": end_ts}}
    )

    return [
        {
            "title": doc.metadata["title"],
            "content": doc.page_content,
            "date": doc.metadata["date"],
            "media_company": doc.metadata["media_company"],
            "url": doc.metadata["url"],
            "score": score
        }
        for doc, score in results
    ]

@async_time_logger("es_news_search")
async def es_news_search(keyword: str, date_start: str, date_end: str) -> str:
    """
    Elasticsearch 뉴스 검색 도구 (기간 필터 포함).
    """

    # redis 캐시 조회
    r = get_redis_client()
    cache_key = f"news:es:{keyword}:{date_start}:{date_end}"
    cached = r.get(cache_key)
    if cached:
        return cached

    es = Elasticsearch(
        hosts=[f"http://{os.getenv('ELASTICSEARCH_HOST')}:{os.getenv('ELASTICSEARCH_PORT')}"],
        basic_auth=(os.getenv("ELASTICSEARCH_USERNAME"), os.getenv("ELASTICSEARCH_PASSWORD")),
        verify_certs=False
    )

    try:
        must_clauses = [
            {
                "range": {
                    "date": {
                        "gte": f"{date_start}T00:00:00",
                        "lte": f"{date_end}T23:59:59"
                    }
                }
            }
        ]

        should_clauses = [
            {"match": {"title": keyword}}
        ]

        query = {
            "query": {
                "bool": {
                    "must": must_clauses,
                    "should": should_clauses,
                    "minimum_should_match": 1
                }
            },
            "from": 0,
            "size": 10
        }

        result = es.search(index=os.getenv("ELASTICSEARCH_DOMESTIC_INDEX_NAME"), body=query)
        return json.dumps(result.body, ensure_ascii=False, indent=2)

    except Exception as e:
        return f"Elasticsearch 검색 실패: {str(e)}"


@tool
@async_time_logger("hybrid_news_search_tool")
async def hybrid_news_search_tool(query: str, keyword: str, date_start: str = None, date_end: str = None) -> list:
    """
    네이버 IT 카테고리 뉴스 통합 검색 도구 (Elasticsearch + Milvus)

    When to use
        • 국내 IT 뉴스에서 키워드 매칭 정확도와 의미 유사도(질문식)를 동시 활용하고 싶을 때
        • 1년 이내 기사만, 또는 임의 기간 필터가 필요할 때

    Args
        query (str): 의미 기반 검색용 질문 문장
        keyword (str): Elasticsearch 키워드 (단어·구문)
        date_start (str, optional): YYYY-MM-DD, 기본값 최근 365 일 전
        date_end   (str, optional): YYYY-MM-DD, 기본값 오늘

    Returns
        list[dict]: 중복 제거 후 스코어 내림차순 정렬된 기사 목록
            title, date, media_company, url, content, score, source 필드 포함


    Notes
        • Elasticsearch 결과가 우선 정렬된다(source='Elasticsearch' ⇒ 0).
        • 기사 크롤링 주기는 하루 1 회(00:00). 따라서 “오늘자” 기사는 포함되지 않는다.
    """
    try:
        # redis 캐싱
        r = get_redis_client()
        today = datetime.now().date()
        if not date_start or not date_end:
            date_start = (today - timedelta(days=365)).strftime("%Y-%m-%d")
            date_end = today.strftime("%Y-%m-%d")

        cache_key = f"news:hybrid:{query}:{keyword}:{date_start}:{date_end}"
        cached = r.get(cache_key)
        if cached:
            return json.loads(cached)

        es_task = es_news_search(keyword, date_start, date_end)
        rag_task = rag_news_search(query, date_start, date_end)

        es_result_raw, rag_result = await asyncio.gather(es_task, rag_task)

        es_results = json.loads(es_result_raw)
        es_hits = es_results.get("hits", {}).get("hits", []) if isinstance(es_results, dict) else []

        parsed_es = [
            {
                "title": item["_source"].get("title"),
                "date": item["_source"].get("date"),
                "media_company": item["_source"].get("media_company"),
                "url": item["_source"].get("url"),
                "content": item["_source"].get("content", ""),
                "score": item.get("_score", 0),
                "source": "Elasticsearch"
            }
            for item in es_hits
        ]

        parsed_rag = [
            {
                "title": item.get("title"),
                "date": item.get("date"),
                "media_company": item.get("media_company"),
                "url": item.get("url"),
                "content": item.get("content"),
                "score": item.get("score", 0),
                "source": "Milvus"
            }
            for item in rag_result
        ]

        combined = parsed_es + parsed_rag
        unique_by_url = {item["url"]: item for item in combined}.values()
        final_sorted = sorted(
            unique_by_url,
            key=lambda x: (0 if x["source"] == "Elasticsearch" else 1, -x["score"])
        )
        return list(final_sorted)

    except Exception as e:
        return [{"error": f"하이브리드 뉴스 검색 실패: {str(e)}"}]

from urllib.parse import quote
import re

@tool
@async_time_logger("gnews_search_tool")
async def gnews_search_tool(query: str, lang: str = "en", country: str = "us", max_results: int = 10) -> List[Dict[str, str]]:
    """
    GNews API 해외 헤드라인 검색 도구

    When to use
        • 영문·다국어 키워드로 영문·다국어 일반 뉴스를 열람할 때

    Args:
        query (str): 검색 키워드 (예: 'cloud', 'AI', "cloud trends")
        lang (str, optional): ISO 639-1 언어 코드, 기본 'en'
        country (str, optional): ISO 3166-1 알파-2 국가 코드, 기본 'us'
        max_results (int, optional): 1-100, 기본 10

    Returns:
        list[dict]: title, date(KST), media_company, url, content, source='GNews'

    Notes:
        • GNews는 다중 단어 입력 시 정확한 구문 검색을 위해 큰따옴표("...")를 사용해야 하며, 공백은 AND로 동작합니다.
        • 특수문자 포함 또는 문장형 쿼리는 자동으로 escape 처리됩니다.
        • 한국어 키워드는 정확도가 낮아 hybrid_news_search_tool 사용을 권장합니다.
    """
    try:
        # API 키 확인
        api_key = os.getenv("GNEWS_API_KEY")
        if not api_key:
            return [{"error": "GNews API 키가 설정되지 않았습니다. .env 파일에 GNEWS_API_KEY를 추가하세요."}]

        # 검색어 전처리: 특수문자나 공백 포함 → 자동 "..." 감싸기
        query = query.strip()
        if re.search(r"[!?&=+/\- ]", query) and not (query.startswith('"') and query.endswith('"')):
            query = f'"{query}"'
        encoded_query = quote(query)

        # 요청 URL 구성
        max_results = min(max_results, 20)
        url = f"https://gnews.io/api/v4/search?q={encoded_query}&lang={lang}&country={country}&max={max_results}&apikey={api_key}"

        # API 호출
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"GNews API 요청 실패: {response.status} - {error_text}")
                data = await response.json()

        # 응답 파싱
        articles = data.get("articles", [])
        if not articles:
            return [{"error": f"'{query}'에 대한 최신 뉴스를 찾을 수 없습니다."}]

        parsed_articles = []
        for article in articles:
            published_at = parser.parse(article["publishedAt"]).astimezone(KST).strftime("%Y-%m-%d %H:%M")
            parsed_articles.append({
                "title": article.get("title", ""),
                "date": published_at,
                "media_company": article["source"]["name"],
                "url": article["url"],
                "content": article.get("content") or article.get("description") or "",
                "source": "GNews"
            })

        return parsed_articles

    except Exception as e:
        return [{"error": f"GNews 검색 실패: {str(e)}"}]


@tool
@async_time_logger("newsapi_search_tool")
async def newsapi_search_tool(query: str, lang: str = "en", max_results: int = 10) -> List[Dict[str, str]]:
    """
    NewsAPI 해외 종합 뉴스 검색 도구

    When to use
        • 폭넓은 언어·매체에서 키워드 기반 최신 뉴스를 수집할 때
        • 정렬 옵션(publishedAt)과 페이지 사이즈 제어가 필요할 때

    Args
        query (str): 검색 키워드(영문 권장)
        lang (str, optional): ISO 639-1 언어 코드, 기본 'en'
        max_results (int, optional): 1-100, 기본 10
    Returns
        list[dict]: title, date(KST), media_company, url, content, source='NewsAPI'

    Notes
        • 동일 키워드 연속 호출 시 rate-limit(HTTP 429) 가능성 있음.
        • 비영어 기사도 지원하지만 언어 코드 정확히 지정해야 검색률이 높다.
    """
    try:
        # NewsAPI 요청 URL 구성
        api_key = os.getenv("NEWS_API_KEY")  # .env 파일에 NEWSAPI_KEY 추가 필요
        if not api_key:
            return [{"error": "NewsAPI 키가 설정되지 않았습니다. .env 파일에 NEWS_API_KEY를 추가하세요."}]

        max_results = min(max_results, 100)  # NewsAPI 최대 결과 수 제한
        url = (
            f"https://newsapi.org/v2/everything?"
            f"q={quote(query)}&language={lang}&sortBy=publishedAt&pageSize={max_results}&apiKey={api_key}"
        )

        # API 호출
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"NewsAPI 요청 실패: {response.status} - {error_text}")
                data = await response.json()

        # 응답 데이터 확인
        articles = data.get("articles", [])
        if not articles:
            return [{"error": f"'{query}'에 대한 최신 뉴스를 찾을 수 없습니다."}]

        # NewsAPI 응답을 LangChain 도구 형식으로 변환
        parsed_articles = []
        for article in articles:
            published_at = parser.parse(article["publishedAt"]).astimezone(KST).strftime("%Y-%m-%d %H:%M")
            parsed_articles.append({
                "title": article["title"],
                "date": published_at,
                "media_company": article["source"]["name"],
                "url": article["url"],
                "content": article["description"] or article["content"] or "",
                "source": "NewsAPI"
            })

        return parsed_articles

    except Exception as e:
        return [{"error": f"NewsAPI 검색 실패: {str(e)}"}]

@async_time_logger("search_daum_blogs")
async def search_daum_blogs(keyword: str, max_results: int = 10) -> List[Dict[str, str]]:
    """
    Daum 블로그 게시글 검색 함수

    Args:
        keyword (str): 검색 키워드
        max_results (int): 검색 결과 수 제한

    Returns:
        List[Dict[str, str]]: 각 게시글에 대해 다음 필드를 포함한 딕셔너리 리스트
            - title: 제목
            - url: 링크
            - contents: 본문 요약
            - datetime: 작성일 (KST 기준, 'YYYY-MM-DD HH:MM' 형식)
            - source: "daum"
    """
    headers = {"Authorization": f"KakaoAK {os.getenv('DAUM_API_KEY')}"}
    params = {"query": keyword, "size": max_results, "sort": "accuracy"}

    try:
        response = requests.get(os.getenv("DAUM_API_URL"), headers=headers, params=params)
        response.raise_for_status()
        data = response.json()

        return [
            {
                "title": item["title"],
                "url": item["url"],
                "contents": item["contents"],
                "datetime": parser.parse(item["datetime"]).strftime("%Y-%m-%d %H:%M"),
                "source": "daum"
            }
            for item in data.get("documents", [])
        ]
    except Exception as e:
        raise RuntimeError(f"Daum API 오류: {str(e)}")


def clean_html(text: str) -> str:
    """HTML 태그 및 엔티티 제거"""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)  # HTML 태그 제거
    text = re.sub(r"&[^;]*;", "", text)  # HTML 엔티티 제거
    return text

@async_time_logger("search_naver_blogs")
async def search_naver_blogs(keyword: str, max_result: int = 10) -> List[Dict[str, str]]:
    """
    Naver 블로그 검색 함수

    Args:
        keyword (str): 검색 키워드
        max_result (int): 검색 결과 수 제한

    Returns:
        List[Dict[str, str]]: 각 게시글에 대해 다음 필드를 포함한 딕셔너리 리스트
            - title: 제목
            - url: 링크
            - contents: 본문 요약
            - datetime: 작성일 (KST 기준, 'YYYY-MM-DD HH:MM' 형식, 시간은 00:00 고정)
            - source: "naver"
    """
    posts = []

    try:
        display = min(max_result, 100)
        url = f"{os.getenv('NAVER_API_URL')}?query={keyword}&display={display}"
        headers = {
            "X-Naver-Client-Id": os.getenv("NAVER_CLIENT_ID"),
            "X-Naver-Client-Secret": os.getenv("NAVER_CLIENT_SECRET")
        }

        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()

        for item in data.get("items", [])[:max_result]:
            post_date = datetime.strptime(item["postdate"], "%Y%m%d")
            posts.append({
                "title": clean_html(item["title"]),
                "url": item["link"],
                "contents": clean_html(item["description"]),
                "datetime": post_date.strftime("%Y-%m-%d 00:00"),
                "source": "naver"
            })
        return posts
    except Exception as e:
        raise RuntimeError(f"Naver 블로그 검색 오류: {str(e)}")

@tool
@async_time_logger("community_search_tool")
async def community_search_tool(korean_keyword: str, english_keyword: str, platform: str = "all", max_results: int = 10) -> List[Dict[str, str]]:
    """
    블로그·커뮤니티 통합 검색 도구 (Daum, Naver, Reddit)

    When to use
        • 키워드에 대한 국내 블로그 여론과 해외 Reddit 토론을 동시에 조사할 때
        • 플랫폼별 결과를 시간순 정렬하여 비교하고 싶을 때

    Args
        korean_keyword (str): 한글 검색어(Daum·Naver)
        english_keyword (str): 영어 검색어(Reddit)
        platform (str, optional): 'daum' | 'naver' | 'reddit' | 'all', 기본 'all'
        max_results (int, optional): 플랫폼별 최대 결과 수, 기본 10
    Returns
        list[dict]: title, url, contents, datetime(KST), source

    Notes
        • datetime 내림차순으로 반환되며, platform='all'이면 최대 3 배 결과가 될 수 있다.
        • Reddit API는 토큰 만료가 빠르므로 10초 내 재호출 시 오류 가능.
    """
    tasks = []
    if platform in ["all", "daum"]:
        tasks.append(search_daum_blogs(korean_keyword, max_results))
    if platform in ["all", "naver"]:
        tasks.append(search_naver_blogs(korean_keyword, max_results))
    if platform in ["all", "reddit"]:
        tasks.append(search_reddit_posts(english_keyword, max_results))

    results_nested = await asyncio.gather(*tasks)
    results = [item for sublist in results_nested for item in sublist]
    return sorted(results, key=lambda x: x["datetime"], reverse=True)[:max_results * (3 if platform == "all" else 1)]


def get_reddit_access_token():
    """
    Reddit 액세스 토큰 발급
    """

    auth = HTTPBasicAuth(os.getenv("REDDIT_CLIENT_ID"), os.getenv("REDDIT_CLIENT_SECRET"))
    headers = {
        "User-Agent": "web:com.dbfis.chatbot:v1.0.0 (by /u/Hot_Mission1860)",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {
        "grant_type": "password",
        "username": os.getenv("REDDIT_USERNAME"),
        "password": os.getenv("REDDIT_PASSWORD")
    }

    response = requests.post("https://www.reddit.com/api/v1/access_token", headers=headers, auth=auth, data=data)

    if response.status_code != 200:
        raise Exception(f"Reddit OAuth 인증 실패: {response.json()}")

    return response.json().get("access_token")

@async_time_logger("search_reddit_posts")
async def search_reddit_posts(keyword: str, max_result: int = 10) -> List[Dict[str, str]]:
    try:
        access_token = get_reddit_access_token()
        headers = {
            "Authorization": f"bearer {access_token}",
            "User-Agent": "web:com.dbfis.chatbot:v1.0.0"
        }
        url = f"https://oauth.reddit.com/search?q={keyword}&limit={max_result}&sort=hot"
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            raise Exception(f"Reddit 검색 실패: {response.json()}")
        data = response.json()
        return [
            {
                "title": item["data"]["title"],
                "url": f"https://www.reddit.com{item['data']['permalink']}",
                "contents": item["data"].get("selftext", "").strip(),
                "datetime": datetime.utcfromtimestamp(item["data"]["created_utc"]).replace(tzinfo=timezone.utc).astimezone(KST).strftime('%Y-%m-%d %H:%M'),
                "source": "reddit"
            }
            for item in data.get("data", {}).get("children", [])
        ]
    except Exception as e:
        raise RuntimeError(f"Reddit 검색 오류: {str(e)}")


@tool
@async_time_logger("search_web_tool")
async def search_web_tool(keyword: str, max_results: int=10) -> List[Dict[str, str]]:
    """
    Tavily API 실시간 웹 페이지 검색 도구

    When to use
        • 빠른 일반 웹 검색이 필요하고, 자세한 본문이 필요한 경우 request_url_tool과 연계할 때
        • 검색 엔진 결과를 JSON 형태로 즉시 받고 싶을 때

    Args
        keyword (str): 검색 키워드
        max_results (int, optional): 1-10, 기본 10
    Returns
        list[dict]: Tavily 검색 결과 원본(Results:{0:)

    Notes
        • 결과에는 AI answer 필드가 포함될 수 있으나 신뢰도는 별도 검증 필요.
        • 깊이 있는 크롤링은 request_url_tool로 URL을 후속 조회해야 한다.
    """

    tavily_tool = TavilySearch(
        max_results=max_results,
        include_answer=True,
        include_raw_content=True,
        search_depth='basic'
    )
    return tavily_tool.invoke({"query": keyword})


@tool
@async_time_logger("youtube_video_tool")
async def youtube_video_tool(query: str, max_results: int = 5):
    """
    YouTube Data API 동영상 검색 도구

    When to use
        • 특정 키워드와 관련된 최신·인기 영상을 확인하거나 트렌드 분석용 썸네일이 필요할 때

    Args
        query (str): 검색 키워드
        max_results (int, optional): 1-50, 기본 5
    Returns
        list[dict]: videoId, title, description, channelTitle, publishedAt, thumbnailUrl, videoUrl

    Notes
        • regionCode 고정을 KR로 두어 한국 인기 순위와 다를 수 있음.
        • API 쿼터 초과 시 하루 제한(HTTP 403) 발생.
    """
    youtube = build("youtube", "v3", developerKey=os.getenv("YOUTUBE_API_KEY"))

    search_response = youtube.search().list(
        q=query,
        part="snippet",
        type="video",
        maxResults=max_results,
        regionCode="KR",
        order="relevance"
    ).execute()

    results = [
        {
            "videoId": item["id"]["videoId"],
            "title": item["snippet"]["title"],
            "description": item["snippet"]["description"],
            "channelTitle": item["snippet"]["channelTitle"],
            "publishedAt": item["snippet"]["publishedAt"],
            "thumbnailUrl": item["snippet"]["thumbnails"]["high"]["url"],
            "videoUrl": f"https://www.youtube.com/watch?v={item['id']['videoId']}"
        }
        for item in search_response["items"]
    ]
    return results

@tool
@async_time_logger("request_url_tool")
async def request_url_tool(input_url: str) -> str | None:
    """
    웹/PDF 원문 텍스트 추출 도구

    When to use
        • 특정 URL의 본문을 장문으로 읽어야 할 때
        • 후속 요약·번역·분석을 위한 원본 텍스트가 필요할 때

    Args
        input_url (str): HTTP(S) 웹 페이지 또는 PDF 파일의 절대 URL
    Returns
        str | None: 추출된 텍스트, 100 자 미만이면 None 반환

    Notes
        • SSL 인증서 오류 시 안전 이유로 차단한다.
        • PDF는 pypdf 를 사용해 텍스트 추출; 이미지·스캔 PDF는 지원하지 않는다.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    try:
        response = requests.get(input_url, headers=headers, timeout=10, verify=True)
        response.raise_for_status()

        if input_url.lower().endswith(".pdf"):
            text = ""
            with io.BytesIO(response.content) as f:
                pdf = PdfReader(f)
                for page in pdf.pages:
                    extracted = page.extract_text()
                    if extracted:
                        text += extracted + "\n"
            if not text.strip():
                return None
        else:
            soup = BeautifulSoup(response.text, "html.parser")
            if soup.body:
                text = soup.body.get_text()
            else:
                text = soup.get_text()
            text = re.sub(r"\s+", " ", text).strip()
            if not text or len(text) < 100:
                return None

        if "example domain" in text.lower() or len(text) < 100:
            return None

        return text

    except requests.exceptions.SSLError:
        return "[차단됨] SSL 인증서가 유효하지 않아 보안되지 않은 사이트로 판단됨"
    except requests.RequestException as e:
        return f"[요청 실패] {str(e)}"
    except Exception as e:
        return f"[처리 오류] {str(e)}"

@tool
@async_time_logger("translation_tool")
async def translation_tool(asking: str) -> str:
    """
    GPT-4o 기반 단문 번역 도구

    When to use
        • 한두 문장의 정확한 번역이 필요할 때
        • 다국어 예문 학습·비교 목적

    Args
        asking (str): "what is the '...' in <language>?" 형태 질문
    Returns
        str: GPT 응답(Thinking : … 형식)

    Notes
        • 길이가 긴 문단·형식 문서는 품질 저하 가능, 전문 번역엔 권장하지 않는다.
    """

    try:
        prompt = PromptTemplate.from_template("You are a translator. Please give me the translation. {asking}")
        runnable = prompt | ChatOpenAI(temperature=0, model="gpt-4o-mini")
        thinking = runnable.invoke({"asking": asking})

        return f"Thinking : {thinking}"
    except Exception as e:
        return f"Error: {e}"

@tool
@async_time_logger("wikipedia_tool")
async def wikipedia_tool(query: str) -> str:
    """
    위키피디아 문서 요약 도구 (한국어 우선)

    When to use
        • 공식·학술적인 개념 정의가 필요할 때
        • 한국어 문서가 없으면 영어 대체 요약을 자동 수신하고 싶을 때

    Args
        query (str): 검색 키워드
    Returns
        str: 최대 5 문장 요약 또는 오류 메시지

    Notes
        • disambiguation 페이지는 첫 번째 항목으로 자동 선택될 수 있다.
        • 요약 길이 1500 자 제한, 원문 전문이 필요하면 request_url_tool 사용.
    """
    # redis 캐싱
    r = get_redis_client()

    # 한국어 우선, 실패 시 영어
    for lang in ["ko", "en"]:
        try:
            cache_key = f"wiki:{lang}:{query}"
            cached = r.get(cache_key)
            if cached:
                return cached

            # wiki_client로 wikipedia 모듈 전달
            api_wrapper = WikipediaAPIWrapper(
                wiki_client=wikipedia,       # wikipedia-api 클라이언트
                top_k_results=2,            # 최대 2개 문서
                doc_content_chars_max=1500, # 요약 최대 1500자
                lang=lang                   # 언어 설정
            )
            wikipedia_tool = WikipediaQueryRun(
                api_wrapper=api_wrapper,
            )
            result = wikipedia_tool.run(query)
            summaries = result.split("\n")[:5]  # 최대 5줄 요약
            return f"위키피디아 요약 ({lang}):\n" + "\n".join(summaries) if summaries else f"위키피디아({lang})에서 '{query}'에 대한 정보를 찾을 수 없습니다."
        except Exception as e:
            if lang == "en":  # 영어까지 실패 시
                return f"Wikipedia 검색 중 오류 발생: {str(e)}"
            continue


@tool
@async_time_logger("google_trending_tool")
async def google_trending_tool(query: str, start_date: str = None, end_date: str = None) -> Dict[str, Union[str, List[float], List[str]]]:
    """
    Google Trends 키워드 관심도 시계열 조회 도구

    When to use
        • 검색량 변화를 데이터 포인트로 시각화·보고서 작성 시
        • 특정 기간(최대 최근 5년)을 지정해 국내(KR) 트렌드만 비교할 때

    Args
        query (str): 검색 키워드
        start_date (str, optional): YYYY-MM-DD, 기본 최근 한 달
        end_date   (str, optional): YYYY-MM-DD
    Returns
        dict: {'query', 'interest_data': List[float], 'dates': List[str]} 또는 error

    Notes
        • Google Trends 빈도가 낮은 키워드는 데이터가 비어 있을 수 있다.
        • pytrends API는 호출 과다 시 429 응답 반환.
    """
    try:
        from pytrends.request import TrendReq

        pytrends = TrendReq(hl="ko", tz=540)

        # 날짜 범위 설정
        if start_date and end_date:
            timeframe = f"{start_date} {end_date}"
        else:
            timeframe = "today 1-m"

        # 요청
        pytrends.build_payload([query], cat=0, timeframe=timeframe, geo="KR", gprop="")

        trend_data = pytrends.interest_over_time()

        if trend_data is None or trend_data.empty:
            return {"error": f"No trending data found for '{query}'."}

        interest_data = trend_data[query].dropna().tolist()
        dates = trend_data.index.strftime('%Y-%m-%d').tolist()

        return {
            "query": query,
            "interest_data": interest_data,
            "dates": dates
        }

    except Exception as e:
        if '429' in str(e):
            return {"error": f"Rate limit exceeded for query '{query}'. Try again later."}
        return {"error": f"Error retrieving Google Trends data: {str(e)}"}


@tool
@async_time_logger("generate_trend_report_tool")
async def generate_trend_report_tool(search_date: str = None) -> str:
    """
    네이버 IT 뉴스 기반 일일 트렌드 보고서 생성 도구

    When to use
        • 지정일(최신 n-1일) 기준 키워드 빈도와 RAG 기사 내용을 종합 분석해야 할 때
        • Word (docx) 형식의 그래프 포함 보고서를 S3 URL로 받아야 할 때

    Args
        search_date (str, optional): YYYY-MM-DD, 기본 어제
    Returns
        str: 보고서 S3 presigned URL 또는 상태 메시지

    Notes
        • 오늘 날짜(00시 이후) 데이터는 크롤링 완료 전이라 생성 불가.
        • Redis 캐시 7 일, 동일 날짜 재요청 시 즉시 URL 반환.
    """

    kst = ZoneInfo("Asia/Seoul")
    kst_now = datetime.now(kst)

    if search_date is None:
        search_date = (kst_now - timedelta(days=1)).strftime('%Y-%m-%d')

    if search_date == kst_now.strftime('%Y-%m-%d'):
        return "[요청 오류] 오늘 날짜의 뉴스 데이터는 아직 수집되지 않았습니다."

    r = get_redis_client() # redis 연결

    cache_key = f"trend_report:{search_date}"
    cached_url = r.get(cache_key)
    if cached_url:
        return f"Redis에 캐시된 보고서입니다.\n[다운로드 링크]({cached_url}) (7일간 유효)"

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT keyword, frequency FROM keyword_frequencies
            WHERE date = %s
            ORDER BY rank ASC
            LIMIT 10
        """, (search_date,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        return f"[DB 연결 실패] {str(e)}"

    if not rows:
        return f"[데이터 없음] {search_date} 날짜에 해당하는 키워드가 없습니다."

    keywords = [row[0] for row in rows]
    frequencies = [row[1] for row in rows]
    keyword_summary = "\n".join([f"- {w}: {c}회" for w, c in rows])

    try:
        embedding_model = get_embedding_model()
        vector_store = get_domestic_article_vector_store()
    except Exception as e:
        return f"[Milvus 연결 실패] {str(e)}"

    # 병렬 실행
    tasks = [search_keyword(kw, search_date, embedding_model, vector_store) for kw in keywords]
    results = await asyncio.gather(*tasks)
    combined_contents = "".join(results)

    if not combined_contents.strip():
        return f"[뉴스 없음] {search_date} 기준 키워드로 검색된 뉴스가 없습니다."

    # GPT 리포트 생성
    prompt = PromptTemplate.from_template("""
    너는 기업 리서치 기관의 보고서를 작성하는 전문 AI야.

    아래의 키워드 출현 빈도 및 관련 기사 내용을 기반으로,
    [개요 - 본론 - 결론] 형식을 따르는 공식적인 보고서를 작성해줘.

    마크다운이나 기호 없이, 일반 문단 형식으로 작성해줘.
    각 섹션은 '개요', '본론', '결론' 제목으로 구분해줘.
    본론에서 키워드 빈도수를 언급하고, 해당 키워드가 언급된 기사 요약은 통합적으로 정리하되, 어떤 흐름이 있었는지 중심으로 작성해줘.

    {date} 기준 IT 키워드 트렌드:

    [키워드 요약]
    {keywords}

    [관련 뉴스 기사 요약]
    {articles}
    """)

    chain = LLMChain(
        llm=ChatOpenAI(model="gpt-4o-mini", temperature=0),
        prompt=prompt
    )

    try:
        result = chain.invoke({
            "date": search_date,
            "keywords": keyword_summary,
            "articles": combined_contents
        })
        gpt_text = result["text"]

        # 시각화 + Word 저장
        chart_path = generate_keyword_bar_chart(keywords, frequencies, search_date)
        filename = f"TRENDB_daily_report_{search_date}_{uuid4().hex[:8]}.docx"
        file_path = save_report_as_docx(gpt_text, filename, image_path=chart_path)

        # S3 업로드
        presigned_url = upload_report_to_spring(file_path)

        # 보고서 url redis 캐시 저장 (TTL = 7일 = presigned url 만료기간)
        r.setex(cache_key, timedelta(days=7), presigned_url)
        return f"보고서 생성 완료!\n [다운로드 링크]({presigned_url}) (7일간 유효)"

    except Exception as e:
        return f"[GPT 처리 실패] {str(e)}"

async def search_keyword(kw, search_date, embedding_model, vector_store):
    try:
        query_embedding = embedding_model.embed_query(kw)
        results = vector_store.similarity_search_with_score_by_vector(
            query_embedding,
            k=10,
            filter={"date": {"$contains": search_date}}
        )
        entries = ""
        for doc, score in results:
            title = doc.metadata.get("title", "")
            content = doc.page_content.strip()
            date = doc.metadata.get("date", "null")
            media = doc.metadata.get("media_company", "null")
            url = doc.metadata.get("url", "null")
            if content and search_date in date:
                entries += f"\n[키워드: {kw}] | 기사 제목: {title} | 기사 날짜: {date} | 언론사: {media} | 링크: {url}\n{content}\n"
        return entries
    except Exception as e:
        return f"\n['{kw}' 검색 실패] {str(e)}\n"


def generate_keyword_bar_chart(keywords: List[str], counts: List[int], search_date: str) -> str:
    plt.rcParams['font.family'] = 'AppleGothic'
    plt.rcParams['axes.unicode_minus'] = False

    plt.figure(figsize=(8, 5))
    bars = plt.bar(keywords, counts, color='skyblue')
    plt.title(f"{search_date} 네이버뉴스 키워드 빈도수", fontsize=14)
    plt.xlabel("키워드")
    plt.ylabel("빈도수")

    for bar in bars:
        yval = bar.get_height()
        plt.text(bar.get_x() + bar.get_width()/2, yval + 0.2, int(yval), ha='center', va='bottom')
    os.makedirs("crawling/data/reports", exist_ok=True)
    filename = f"crawling/data/reports/keyword_chart_{search_date}_{uuid4().hex[:6]}.png"
    plt.tight_layout()
    plt.savefig(filename)
    plt.close()
    return filename


def save_report_as_docx(content: str, filename: str, image_path: str = None) -> str:
    doc = Document()

    lines = content.split("\n")
    current_section = None
    added_chart = False

    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue

        if line.startswith("개요"):
            doc.add_heading("개요", level=1)
            current_section = "개요"

        elif line.startswith("본론"):
            doc.add_heading("본론", level=1)
            current_section = "본론"

            # 본론 시작 직후 그래프 삽입
            if image_path and os.path.exists(image_path):
                doc.add_picture(image_path, width=Inches(5.5))
                doc.add_paragraph("")  # 그래프와 본문 사이 여백

            added_chart = True

        elif line.startswith("결론"):
            doc.add_heading("결론", level=1)
            current_section = "결론"

        else:
            doc.add_paragraph(line)

    # 저장 경로 설정
    os.makedirs("../../data/reports", exist_ok=True)
    full_path = f"../../data/reports/{filename}"
    doc.save(full_path)
    return full_path


def upload_report_to_spring(file_path: str):
    url = "http://localhost:8080/api/public-reports/upload"
    with open(file_path, "rb") as f:
        files = {
            "file": (os.path.basename(file_path), f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        }
        response = requests.post(url, files=files)
        if response.status_code == 200:
            return response.json()["url"]
        else:
            raise Exception(f"Spring 업로드 실패: {response.status_code} {response.text}")

@tool
@async_time_logger("get_daily_news_trend_tool")
async def get_daily_news_trend_tool(date: str) -> str:
    """
    Spring API 일간 트렌드 키워드·뉴스 데이터 조회 도구

    When to use
        • 특정 날짜 네이버 IT 뉴스 상위 키워드와 연관 기사를 구조화 데이터로 가져올 때

    Args
        date (str): YYYY-MM-DD
    Returns
        str: JSON 문자열 (Spring API 원본) 또는 오류 메시지

    Notes
        • 오늘 날짜 데이터는 제공되지 않는다.
        • Redis 캐시가 있으면 즉시 반환하여 Spring API 호출 수를 절약한다.
    """
    # redis 캐시 조회
    r = get_redis_client()
    cache_key = f"daily_trend:{date}"
    cached = r.get(cache_key)
    if cached:
        return cached

    try:
        url = f"http://localhost:8080/api/insight?date={date}"
        response = requests.get(url)
        response.raise_for_status()
        # redis 캐시 저장
        r.set(cache_key, response.text)
        return response.text
    except Exception as e:
        return f"트렌드 리포트 데이터 조회 실패: {e}"


@tool
@async_time_logger("stock_history_tool")
async def stock_history_tool(
    symbol: str,
    period: Optional[str] = None,
    interval: Optional[str] = "1d",
    start: Optional[str] = None,
    end: Optional[str] = None,
    auto_adjust: bool = True,
    back_adjust: bool = False,
) -> Dict[str, Any]:
    """
    미국·글로벌 주식 OHLCV 조회 도구 (yfinance)

    When to use
        • 미국 상장사 혹은 해외 ETF 가격 히스토리가 필요할 때
        • 배당 조정·분할 보정(auto_adjust) 옵션을 사용하고 싶을 때

    Args
        symbol (str): 티커 심볼
        period | start/end: 조회 범위 지정 (둘 중 하나)
        interval (str, optional): 1m-1mo, 기본 '1d'
        auto_adjust (bool): 배당·분할 보정 여부, 기본 True
    Returns
        dict: {'history': List[OHLCV], 'info': company_info, 'status', 'message'}

    Notes
        • yfinance는 실시간 데이터가 아니며 최대 15분 지연.
        • Invalid symbol 입력 시 df.empty → status='failed' 로 반환.
    """
    # 기본 응답 구조
    response = {
        "symbol": symbol,
        "history": [],
        "info": {},
        "status": "failed",
        "message": None
    }

    # 티커 심볼 검증
    if not symbol or not symbol.strip():
        response["message"] = "티커 심볼이 비어 있습니다."
        return response

    try:
        # Ticker 객체 생성
        ticker = yf.Ticker(symbol)

        # 기간 vs 날짜 범위 조회
        if period and not (start or end):
            df = ticker.history(
                period=period,
                interval=interval,
                auto_adjust=auto_adjust,
                back_adjust=back_adjust
            )
        else:
            if not start or not end:
                response["message"] = "start와 end 날짜를 모두 지정해야 합니다."
                return response
            df = ticker.history(
                start=start,
                end=end,
                interval=interval,
                auto_adjust=auto_adjust,
                back_adjust=back_adjust
            )

        # 데이터가 비어 있는 경우 처리
        if df.empty:
            response["message"] = f"티커 '{symbol}'에 대한 데이터를 가져올 수 없습니다. 티커 심볼이 올바른지 확인하세요."
            return response

        # DataFrame → 리스트 of dict
        records: List[Dict[str, Any]] = []
        for idx, row in df.iterrows():
            records.append({
                "date": idx.strftime("%Y-%m-%d %H:%M:%S"),
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": int(row["Volume"])
            })

        # ticker.info 안전하게 가져오기
        try:
            info = ticker.info or {}
        except Exception as e:
            print(f"회사 정보 가져오기 실패 ({symbol}): {str(e)}")
            info = {}

        # 성공 응답
        response.update({
            "history": records,
            "info": info,
            "status": "success",
            "message": None
        })
        return response

    except Exception as e:
        response["message"] = f"주식 데이터를 가져오는 데 실패했습니다: {str(e)}"
        return response

@tool
@async_time_logger("kr_stock_history_tool")
async def kr_stock_history_tool(
    symbol: str,
    period: Optional[str] = None,
    interval: Optional[str] = "1d",
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> Dict[str, Any]:
    """
    한국 주식 OHLCV 조회 도구 (FinanceDataReader)

    When to use
        • KRX/코스닥 종목 일간 가격 데이터를 받아야 할 때
        • 해외 API 대신 국내 공개 데이터 소스를 활용하고 싶을 때

    Args
        symbol (str): 6자리 숫자 티커(예: '005930')
        period | start/end: 조회 범위 지정
        interval (str, optional): 현재 '1d' 고정
    Returns
        dict: history, info(빈 dict), status, message

    Notes
        • FinanceDataReader는 회사 프로필을 제공하지 않는다.
        • interval != '1d' 요청 시 status='failed'.
    """
    # 기본 응답 구조
    response = {
        "symbol": symbol,
        "history": [],
        "info": {},  # FinanceDataReader는 회사 정보를 제공하지 않음
        "status": "failed",
        "message": None
    }

    # 티커 심볼 검증
    if not symbol or not symbol.strip():
        response["message"] = "티커 심볼이 비어 있습니다."
        return response

    # FinanceDataReader는 interval을 직접 지원하지 않으므로 1d로 고정
    if interval != "1d":
        response["message"] = "현재는 '1d' 간격만 지원합니다."
        return response

    try:
        # 날짜 설정
        if period and not (start or end):
            # period를 날짜 범위로 변환 (간단히 max로 설정 후 필터링)
            df = fdr.DataReader(symbol, start='2000-01-01', end=datetime.now().strftime('%Y-%m-%d'))
            # period에 따라 필터링 (예: '1d' → 최근 1일)
            if period == '1d':
                df = df.tail(1)
            elif period == '5d':
                df = df.tail(5)
            elif period == '1mo':
                df = df.tail(30)
            elif period == '1y':
                df = df.tail(365)
            elif period == 'max':
                pass  # 이미 전체 데이터
            else:
                response["message"] = f"지원하지 않는 period 값입니다: {period}"
                return response
        else:
            if not start or not end:
                response["message"] = "start와 end 날짜를 모두 지정해야 합니다."
                return response
            df = fdr.DataReader(symbol, start=start, end=end)

        # 데이터가 비어 있는 경우 처리
        if df.empty:
            response["message"] = f"티커 '{symbol}'에 대한 데이터를 가져올 수 없습니다. 티커 심볼이 올바른지 확인하세요."
            return response

        # DataFrame → 리스트 of dict
        records: List[Dict[str, Any]] = []
        for idx, row in df.iterrows():
            records.append({
                "date": idx.strftime("%Y-%m-%d"),
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": int(row["Volume"])
            })

        # 성공 응답
        response.update({
            "history": records,
            "status": "success",
            "message": None
        })
        return response

    except Exception as e:
        response["message"] = f"주식 데이터를 가져오는 데 실패했습니다: {str(e)}"
        return response

@tool
@async_time_logger("namuwiki_tool")
async def namuwiki_tool(keyword: str) -> str:
    """
    나무위키 본문 크롤링·요약 도구

    When to use
        • 대중문화·밈·비공식 정보 등 Wikipedia에 없는 주제를 다룰 때

    Args
        keyword (str): 검색 키워드
    Returns
        str: 본문 요약(최대 30 단락) 또는 오류 메시지

    Notes
        • 공식 API가 없으므로 레이아웃 변경 시 파서가 실패할 수 있다.
    """
    # redis 캐싱
    r = get_redis_client()
    cache_key = f"namuwiki:{keyword}"
    cached = r.get(cache_key)
    if cached:
        return cached

    try:
        base_url = "https://namu.wiki"
        encoded_keyword = quote(keyword)
        headers = {"User-Agent": UserAgent().random}

        # 직접 url 접근
        direct_url = f"{base_url}/w/{encoded_keyword}"
        response = requests.get(direct_url, headers=headers, timeout=10)
        html = response.text

        # HTML 파싱
        soup = BeautifulSoup(html, "html.parser")
        all_divs = soup.find_all("div")

        # 제거할 키워드 + 정규식 패턴 정의
        irrelevant_keywords = [
            "CC BY-NC-SA", "namu.wiki", "umanle S.R.L",
            "Google Privacy Policy", "Términos de uso",
            "문서 가져오기", "최근 수정 시각", "틀", "분류:",
            "펼치기", "접기",
            "편집 요청", "편집 권한이 부족합니다", "ACL 탭", "도움말"
        ]
        heading_pattern = re.compile(r"^\d+(\s*\.\s*\d+)*\s*\.")

        extracted, seen = [], set()
        for div in all_divs:
            text = div.get_text(separator=" ", strip=True)
            if (
                text
                and len(text) > 40
                and text not in seen
                and not any(bad in text for bad in irrelevant_keywords)
                and not heading_pattern.match(text)
            ):
                extracted.append(text)
                seen.add(text)

        return "\n\n".join(extracted[:30]) if extracted else "본문이 비어 있습니다."

    except Exception as e:
        return f"[오류 발생] 나무위키 요청 실패: {str(e)}"

@tool
def generate_dalle3_enhanced(prompt: str) -> str:
    """
    DALL·E 3 이미지 생성용 프롬프트 리라이팅 도구

    When to use
        • 사용자 러프 프롬프트를 영어 시각 묘사 중심으로 보강한 뒤 이미지를 생성할 때

    Args
        prompt (str): 원본 프롬프트(자연어)
    Returns
        str: 생성 이미지 URL 또는 오류 메시지

    Notes
        • GPT-4o-mini → DALL·E 3 두 단계 호출이므로 평균 10-15초 소요.
        • DALLE_API_KEY 누락 시 즉시 오류 메시지를 반환한다.
    """

    openai.api_key = os.getenv("DALLE_API_KEY")

    try:
        llm = ChatOpenAI(model_name="gpt-4o-mini", temperature=0.7)

        template = PromptTemplate.from_template("""
            You are a prompt engineer for DALL·E 3.
            Rewrite the following prompt in **English**, with vivid, concrete visual details:
            "{prompt}"
            Avoid abstract language. Keep it concise and realistic.
            """)

        formatted_prompt = template.format(prompt=prompt)
        enhanced_prompt = llm.invoke(formatted_prompt)

        # 프롬프트 확인용
        # print("GPT 보완 프롬프트:", enhanced_prompt.content)

        dalle_response = openai.images.generate(
            model="dall-e-3",
            prompt=enhanced_prompt.content,
            size="1024x1024",
            quality="standard",
            n=1
        )
        return dalle_response.data[0].url

    except Exception as e:
        print(f"DALL·E 생성 오류: {str(e)}")
        return f"이미지 생성 실패: {str(e)}"

tools = [
    hybrid_news_search_tool,
    gnews_search_tool,
    newsapi_search_tool,
    community_search_tool,
    search_web_tool,
    youtube_video_tool,
    request_url_tool,
    translation_tool,
    wikipedia_tool,
    google_trending_tool,
    generate_trend_report_tool,
    get_daily_news_trend_tool,
    namuwiki_tool,
    stock_history_tool,
    generate_dalle3_enhanced,
    kr_stock_history_tool
]

# 도구 분류
news_tools = [
    hybrid_news_search_tool,
    get_daily_news_trend_tool,
    search_web_tool,
    wikipedia_tool,
    google_trending_tool,
    generate_trend_report_tool
]

community_tools = [
    community_search_tool,
    youtube_video_tool,
    search_web_tool
]

common_tools = [
    request_url_tool,
    translation_tool,
    stock_history_tool
]
