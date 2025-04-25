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

from langchain.prompts import PromptTemplate
from langchain.chat_models import ChatOpenAI
from langchain.chains.llm import LLMChain
from langchain.tools import tool
from langchain_community.tools import WikipediaQueryRun
from langchain_community.tools.tavily_search import TavilySearchResults
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

@async_time_logger("rag_news_search_tool")
async def rag_news_search_tool(query: str, date_start: str, date_end: str) -> List[Dict[str, Union[str, float]]]:
    """
    Milvus에서 RAG를 이용한 의미 기반 IT 뉴스 기사 검색 도구 (기간 필터 포함).
    """
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

@async_time_logger("keyword_news_search_tool")
async def keyword_news_search_tool(keyword: str, date_start: str, date_end: str) -> str:
    """
    Elasticsearch 뉴스 검색 도구 (기간 필터 포함).
    """
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
    Elasticsearch + Milvus 병렬 하이브리드 네이버 IT 카테고리 뉴스 검색 도구

    이 함수는 두 가지 방식의 뉴스 검색을 병렬로 수행합니다:

    1. **Elasticsearch**: 키워드 기반의 문자열 검색
    2. **Milvus (RAG)**: 임베딩 기반의 의미 유사도 검색 (질문 기반)

    ### Args:
    - query (str): 의미 기반 검색을 위한 질문 문장 (예: "AI가 기업 생산성에 미치는 영향은?")
    - keyword (str): Elasticsearch용 주요 키워드 (예: "AI", "삼성", "반도체")
    - date_start (str, optional): 검색 시작 날짜 (형식: YYYY-MM-DD). 지정하지 않으면 최근 365일 기준 자동 설정됨.
    - date_end (str, optional): 검색 종료 날짜 (형식: YYYY-MM-DD). 지정하지 않으면 오늘 날짜 기준으로 자동 설정됨.

    ### 결과 항목
    - title: 기사 제목
    - date: 발행일
    - media_company: 언론사
    - url: 기사 링크
    - content: 본문 요약 or 전체 본문
    - score: 점수 (ES의 경우 `_score`, Milvus의 경우 유사도 점수)
    - source: "Elasticsearch" 또는 "Milvus"

    ### 사용 시 주의사항
    - **뉴스 기사는 매일 자정에 자동 크롤링 및 업데이트**됩니다.
      - 따라서 가장 최신 기사는 **"현재 시간 기준 하루 전"**입니다.
    - Elasticsearch는 **UTC 기준 날짜**로 저장되며, 한국 기준 하루 차이 날 수 있습니다.
    - Milvus는 의미 기반으로 질문을 벡터화하여 유사한 문서를 검색하며, 날짜 필터는 적용되지만 의미 정확도는 질문 문장 품질에 따라 달라질 수 있습니다.
    - 반환 결과는 `url` 기준 중복 제거 후, `score` 기준으로 정렬됩니다.

    Returns:
        list: 뉴스 기사 결과 목록 (최대 10~20개, 중복 제거됨)
    """
    try:
        if not date_start or not date_end:
            today = datetime.utcnow().date()
            date_start = (today - timedelta(days=365)).strftime("%Y-%m-%d")
            date_end = today.strftime("%Y-%m-%d")

        es_task = keyword_news_search_tool(keyword, date_start, date_end)
        rag_task = rag_news_search_tool(query, date_start, date_end)

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
@async_time_logger("community_search_tool")
async def community_search_tool(korean_keyword: str, english_keyword: str, platform: str = "all", max_results: int = 10) -> List[Dict[str, str]]:
    """
    커뮤니티 통합 검색 도구

    필수 입력:
    - korean_keyword (str): 블로그 검색용 한글 키워드 (Daum, Naver용)
    - english_keyword (str): Reddit 검색용 영어 키워드 (Reddit용)

    선택 입력:
    - platform (str): "daum", "naver", "reddit", "all" 중 선택 (기본: all)
    - max_results (int): 각 플랫폼별 최대 검색 결과 수 (기본: 10)

    Args:
        korean_keyword (str): 한글 검색 키워드
        english_keyword (str): 영어 검색 키워드
        platform (str): "daum", "naver", "reddit", "all"
        max_results (int): 각 플랫폼별 최대 검색 수

    Returns:
        List[Dict[str, str]]: 통합된 게시글 리스트
            - title, url, contents, datetime (KST), source
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



@tool
@async_time_logger("search_web_tool")
async def search_web_tool(keyword: str, max_results: int=10) -> List[Dict[str, str]]:
    """
    실시간 웹 검색 도구.

    Tavily Search API를 이용하여 실시간 웹 검색을 수행합니다.

    자세한 웹 페이지의 탐색을 위해 이후 request_url_tool을 호출해 탐색하는 것이 권장됩니다.

    Args:
        keyword (str): 검색할 키워드
        max_results (int, optional): 최대 검색 결과 수 (기본값: 10)

    Returns:
        List[Dict[str, str]]: 검색된 웹 페이지 목록
    """

    tavily_tool = TavilySearchResults(
        max_results=max_results,
        include_answer=True,
        include_raw_content=True
    )
    return tavily_tool.invoke({"query": keyword})


@tool
@async_time_logger("youtube_video_tool")
async def youtube_video_tool(query: str, max_results: int = 5):
    """
    커뮤니티 트렌드 - YouTube 동영상 검색 도구.

    YouTube API를 사용하여 특정 키워드(query)와 관련된 동영상을 검색합니다.

    Args:
        query (str): 검색할 키워드
        max_results (int, optional): 최대 검색 결과 수 (기본값: 5)

    Returns:
        List[Dict[str, str]]: 검색된 동영상 목록
            - "videoId" (str): YouTube 동영상 ID
            - "title" (str): 동영상 제목
            - "description" (str): 동영상 설명
            - "channelTitle" (str): 채널 이름
            - "publishedAt" (str): 업로드 날짜
            - "thumbnailUrl" (str): 썸네일 이미지 URL
            - "videoUrl" (str): 동영상 URL
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
    웹페이지 또는 PDF 문서에서 텍스트를 추출하는 도구.

    주어진 URL에서 HTML 본문 또는 PDF 텍스트를 가져옵니다.
    유효한 SSL 인증서가 없는 경우 접근하지 않습니다.

    Args:
        input_url (str): 요청할 웹 페이지 또는 PDF 파일의 URL

    Returns:
        str: 추출된 텍스트
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
    ChatGPT를 이용한 번역 도구.

    입력된 문장을 특정 언어로 번역합니다.
    프롬프트 형식: "what is the '...' in <language>?"
    예: "what is the 'hello my friend!' in Spanish?"

    Args:
        asking (str): 번역할 문장이 포함된 질문

    Returns:
        str: 번역된 문장을 포함한 응답
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
    Wikipedia 검색 도구.

    한국어 Wikipedia에서 입력된 키워드(query)와 관련된 문서를 검색하고 요약을 제공합니다.
    한국어 문서가 없으면 영어로 대체된 결과가 반환됩니다.

    Args:
        query (str): 검색할 키워드

    Returns:
        str: 검색된 Wikipedia 문서 요약 (최대 5문장) 또는 오류 메시지
    """
    # 한국어 우선, 실패 시 영어
    for lang in ["ko", "en"]:
        try:
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
async def google_trending_tool(query: str, startDate: str = None, endDate: str = None) -> Dict[str, Union[str, List[float], List[str]]]:
    """
    Google Trends 키워드 검색 도구.

    특정 키워드(query)에 대한 Google Trends 검색량 변화를 조회합니다.

    Args:
        query (str): 검색할 키워드
        startDate (str, optional): 검색 시작 날짜 (YYYY-MM-DD 형식, 기본값: 최근 1개월)
        endDate (str, optional): 검색 종료 날짜 (YYYY-MM-DD 형식)

    Returns:
        Dict[str, Union[str, List[float], List[str]]]: 트렌드 검색 결과
            - "query" (str): 검색한 키워드
            - "interest_data" (List[float]): 검색량 변화 데이터
            - "dates" (List[str]): 해당 날짜 목록 (YYYY-MM-DD)
    """
    try:
        from pytrends.request import TrendReq

        pytrends = TrendReq(hl="ko", tz=540)

        # 날짜 범위 설정
        if startDate and endDate:
            timeframe = f"{startDate} {endDate}"
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
    트렌드 레포트 생성 도구.
    DB에 저장된 날짜별 네이버 IT 뉴스 상위 키워드를 기반으로 Milvus에서 관련 뉴스를 검색하고,
    GPT를 통해 종합적인 트렌드 분석 보고서를 생성합니다.

    ⚠️ 주의:
        - 본 도구는 "오늘 날짜(오늘 00시 이후)" 기준 데이터는 사용할 수 없습니다.
        - 뉴스 크롤링은 매일 자정(00:00) 기준으로 하루 단위 수집되므로,
          가장 최근 사용 가능한 날짜는 "어제 날짜"입니다.
        - Redis 캐시로 7일간 보고서 재사용 가능

    Args:
        search_date (str, optional): 보고서를 생성할 날짜 (예: '2025-03-12').
                                     기본값은 오늘 날짜 기준 어제(n-1일)로 자동 설정됩니다.

    Returns:
        str: 트렌드 인사이트 보고서가 저장된 Amazon S3 presigned URL
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
    Spring API를 이용해 일간 트렌드 정보를 가져오는 도구.

    특정 날짜의 네이버 IT 뉴스 기사 상위 키워드와 각 키워드의 연관 키워드, 뉴스 기사 데이터를 가져옵니다.

    ⚠️ 주의:
        - 본 도구는 "오늘 날짜(오늘 00시 이후)" 기준 데이터는 사용할 수 없습니다.
        - 뉴스 크롤링은 매일 자정(00:00) 기준으로 하루 단위 수집되므로,
          가장 최근 사용 가능한 날짜는 "어제 날짜"입니다.

    Args:
        date (str): 조회 날짜 (YYYY-MM-DD)

    Returns:
        str: 트렌드 리포트 데이터 JSON 문자열 (오류 발생 시 오류 메시지 포함)
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
    주식 티커에 대한 히스토리를 조회하는 도구

    Args:
        symbol: 조회할 티커 심볼 (예: 'AAPL', 'LUMN')
        period: 조회 기간 (예: '1d','5d','1mo','1y','max' 등). start/end와 동시에 사용할 수 없습니다.
        interval: 데이터 간격 (예: '1m','5m','1h','1d','1wk','1mo' 등)
        start: 조회 시작일 (YYYY-MM-DD), period 없이 사용 시 필수
        end: 조회 종료일 (YYYY-MM-DD), start와 함께 사용
        auto_adjust: 배당·분할 이후 가격 자동 보정 여부
        back_adjust: 과거 가격 보정 여부

    Returns:
        {
          "symbol": symbol,
          "history": [  # 날짜별 OHLCV 리스트
            {
              "date": "2024-06-07",
              "open": 123.45,
              "high": 125.00,
              "low": 122.80,
              "close": 124.10,
              "volume": 987654
            },
            ...
          ],
          "info": { ... }  # 회사 정보
        }
    """
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
        df = ticker.history(
            start=start,
            end=end,
            interval=interval,
            auto_adjust=auto_adjust,
            back_adjust=back_adjust
        )

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

    return {
        "symbol": symbol,
        "history": records,
        "info": ticker.info
    }

@tool
@async_time_logger("namuwiki_tool")
async def namuwiki_tool(keyword: str) -> str:
    """
    나무위키 검색 도구

    입력된 키워드(query)에 해당하는 나무위키 문서를 검색하고,
    본문 텍스트 일부를 반환합니다. 나무위키는 크롤링을 통해 접근합니다.

    Args:
        keyword (str): 검색 키워드

    Returns:
        str: 나무위키 본문 요약 텍스트 또는 오류 메시지
    """

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


# ------------------------
# Deep Research 단계별 툴
# ------------------------
@tool
async def planner_tool(topic: str, steps: int = 3) -> List[Dict[str, Any]]:
    """
    사용자의 주제에 대한 질문, 키워드 및 사용할 도구를 추천합니다.
    각 도구에 대해 적합한 검색 키워드 및 도구를 제공합니다.
    """
    prompt_text = f"""
    당신은 리서치 검색 툴의 planner입니다.
    사용자의 주제: "{topic}"
    아래의 조건에 맞게 질문과 그에 적합한 검색 키워드, 사용할 도구를 가능한 많이 추천하세요.
    이 주제에 대해 검색할 수 있는 도구를 추천하고, 각 도구별 검색 특성을 반영하여 어떤 검색어를 사용해야 할지 반환해 주세요.

    출력 형식 예시:
    [
      {{
        "question": "삼성전자의 최신 기술은?",
        "search_tools": [
          {{
            "search_tool": "wikipedia_tool",
            "keyword": "삼성전자 최신 기술"
          }},
          {{
            "search_tool": "rag_news_search_tool",
            "keyword": "삼성전자 기술 2025"
          }}
        ]
      }}
    ]

    사용 가능한 도구 목록:
    - wikipedia_tool
    - reddit_tool
    - naver_blog_tool
    - daum_blog_tool
    - rag_news_search_tool
    - search_web_tool
    """

    llm = ChatOpenAI(temperature=0, streaming=True)
    chain = LLMChain(llm=llm, prompt=PromptTemplate.from_template("{prompt}"))
    output = await chain.arun(prompt=prompt_text)

    # 결과를 JSON 형식으로 파싱하여 반환
    result = json.loads(output)

    # 디버깅: result 내용 확인
    print(f"[planner_tool] result: {result}")

    # 데이터를 추출
    final_result = []
    for item in result:
        question = item.get("question", "")
        keyword = item.get("keyword", "")
        search_tools = item.get("search_tools", [])

        # 검색 도구별로 키워드 매핑 처리
        search_tool_list = [{"search_tool": tool["search_tool"], "keyword": tool["keyword"]} for tool in search_tools]

        # 최종 결과 생성
        final_result.append({
            "question": question,
            "keyword": keyword,
            "search_tools": search_tool_list
        })

    return final_result

@tool
async def summarizer_tool(content: Any, source: str = "") -> str:
    """
    웹/뉴스/블로그 등의 개별 콘텐츠를 요약하는 도구.
    """
    llm = ChatOpenAI(temperature=0, streaming=True)
    prompt = PromptTemplate.from_template("""
      당신은 리서치 검색 툴의 summarizer 입니다. 
      당신의 역할은 각 소스에서 수집된 정보들을 가진 의미를 잃지 않으면서, 적절한 길이로 줄이는 것입니다.
      다음은 [{source}]에서 수집한 문서입니다. 이 문서의 핵심 내용을 적절하게 요약하세요. 
      전체 문장의 의미를 잃지 않도록 주의하고, 과도하게 내용을 축소하지 않도록 합니다. 
      요약은 문서의 핵심 아이디어를 유지하며 작성해 주세요.
  
      문서 내용:
      {content}
    """)
    chain = LLMChain(llm=llm, prompt=prompt)
    return await chain.ainvoke({"content": content, "source": source})

@tool
async def analyzer_tool(context: str, question: str) -> str:
    """
    인사이트 추출 도구.

    주어진 문서와 조사 질문을 바탕으로 사용자가 실제로 리서치에 활용할 수 있는
    통찰력 있는 인사이트를 서술형 문단 형식으로 생성합니다.
    """

    llm = ChatOpenAI(streaming=True, temperature=0)

    template = PromptTemplate.from_template("""
    당신은 리서치 툴의 analyzer입니다.
    당신의 역할은 주어진 문서들을 바탕으로 사용자가 실제로 리서치에 활용할 수 있는 통찰력 있는 인사이트를 서술하는 것입니다.
    다음은 사용자가 제시한 질문과 이에 대한 참고 문서입니다.

    [질문]
    {question}

    [문서]
    {context}

    위 정보를 바탕으로 다음을 수행하세요:

    [요구사항]
    - 질문에 대한 답변을 넘어서, 의미 있는 인사이트 2~3개를 추론해 작성합니다.
    - 각 인사이트는 논리적 근거를 포함하며, 가능하면 문서에서 직접 인용합니다.
    - 단순 정보 요약이 아닌 '해석', '비판적 분석', '의미 도출'을 포함해야 합니다.
    - 전체 응답은 서술형 문단 형식으로 작성합니다.
    - 리스트, 마크다운, 줄바꿈 없이 하나의 문단으로 작성합니다.

    인사이트:
    """)

    chain = LLMChain(llm=llm, prompt=template)
    return await chain.arun(context=context, question=question)


@tool
async def fact_check_tool(context: str) -> str:
    """
    콘텐츠 신뢰도 평가 도구.

    주어진 기사나 웹 텍스트(context)에 포함된 주장이나 정보의 신뢰성을 평가합니다.

    Args:
        context (str): 기사 본문 또는 웹 페이지 텍스트

    Returns:
        str: 신뢰도 평가 결과 (사실 여부, 출처 확인, 신뢰 수준 등 포함)
    """
    llm = ChatOpenAI(streaming=True, temperature=0)
    template = PromptTemplate.from_template("""
    당신은 리서치 툴의 신뢰도 평가자입니다.
    다음은 사용자가 수집한 웹 기사 또는 콘텐츠입니다:

    [본문]
    {context}

    위 정보의 신뢰성을 다음 기준에 따라 평가하세요:
    - 과학적 근거, 통계, 인용 등 신뢰 가능한 출처가 있는지 확인
    - 음모론, 과장된 주장, 출처 미확인 정보는 경고
    - 사실 여부 판단이 어려운 경우, 그 이유를 설명
    - 종합적으로 이 콘텐츠의 신뢰 수준을 "높음 / 보통 / 낮음" 중 하나로 판단

    출력 형식 예시:
    - 신뢰 수준: 보통
    - 근거: 출처가 명확하지 않지만 특정 사실은 확인됨
    - 주의할 점: 일부 과장된 표현 존재
    """)
    chain = LLMChain(llm=llm, prompt=template)
    return await chain.arun(context=context)

@tool
async def synthesizer_tool(insights: List[str]) -> str:
    """
    최종 보고서 작성 도구.

    수집된 인사이트들을 기반으로 정식 리서치 보고서를 작성합니다.
    [개요-본론-결론] 형식을 갖춘, 기업/정책/트렌드 리포트에 준하는 구조로 문서화합니다.
    """

    llm = ChatOpenAI(streaming=True, temperature=0)

    combined = "\n".join(insights)

    template = PromptTemplate.from_template("""
    당신은 리서치 툴의 최종 보고서 작성자입니다.
    수집된 인사이트들을 기반으로 리서치 보고서를 작성합니다.
    
    다음은 사용자가 조사한 주제에 대한 주요 인사이트 목록입니다:
    
    [인사이트 목록]
    {content}

    위 내용을 바탕으로 다음과 같은 형식의 보고서를 작성하세요.

    [요구사항]
    - 전체 구조는 '개요 → 본론 → 결론' 순으로 작성하세요.
    - 개요: 전체 주제 및 조사 목적 요약
    - 본론: 핵심 인사이트를 근거와 함께 서술 (논리 전개 필요)
    - 결론: 요약 및 향후 시사점 또는 전망 포함
    - 보고서 문체는 공적인 문서 형식으로 작성
    - 마크다운, 기호, 줄번호 없이 일반 문단으로 작성

    리포트:
    """)

    chain = LLMChain(llm=llm, prompt=template)
    return await chain.arun(content=combined)

@tool
def generate_dalle3_enhanced(prompt: str) -> str:
    """
    GPT-4o-mini로 프롬프트를 보완한 뒤, DALL·E 3 API로 이미지 생성

    Args:
        prompt (str): 사용자 입력 프롬프트

    Returns:
        str: 생성된 이미지 URL 또는 오류 메시지
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
    community_search_tool,
    search_web_tool,
    youtube_video_tool,
    request_url_tool,
    translation_tool,
    wikipedia_tool,
    google_trending_tool,
    generate_trend_report_tool,
    get_daily_news_trend_tool,
    keyword_news_search_tool,
    namuwiki_tool,
    stock_history_tool,
    generate_dalle3_enhanced
]

# 도구 분류
news_tools = [
    hybrid_news_search_tool,
    get_daily_news_trend_tool,
    keyword_news_search_tool,
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
