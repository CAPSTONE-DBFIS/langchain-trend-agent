import asyncio
import io
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Any, Dict, List, Optional, Union
from urllib.parse import quote
from uuid import uuid4

import aiohttp
import FinanceDataReader as fdr
import matplotlib
import matplotlib.pyplot as plt
matplotlib.use('Agg')  # 백엔드 설정
import openai
import pandas as pd
import plotly.express as px
import requests
import wikipedia
import yfinance as yf
from bs4 import BeautifulSoup
from dateutil import parser
from docx import Document
from docx.shared import Inches
from dotenv import load_dotenv
from elasticsearch import Elasticsearch
from fake_useragent import UserAgent
from googleapiclient.discovery import build
from langchain.chat_models import ChatOpenAI
from langchain.chains.llm import LLMChain
from langchain.prompts import PromptTemplate
from langchain.tools import tool
from langchain_community.tools import WikipediaQueryRun
from langchain_community.utilities import WikipediaAPIWrapper
from langchain_tavily import TavilySearch
from pytrends.request import TrendReq
from pypdf import PdfReader
from requests.auth import HTTPBasicAuth
from unidecode import unidecode
from zoneinfo import ZoneInfo

from app.utils.db_util import get_db_connection
from app.utils.milvus_util import get_embedding_model, get_domestic_article_vector_store, get_personal_file_vector_store
from app.utils.redis_util import get_redis_client
from app.utils.s3_util import upload_chart_to_s3
from app.utils.es_util import fetch_domestic_articles

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

@tool
@async_time_logger("es_news_search_tool")
async def es_news_search_tool(
    keyword: str,
    date_start: str,
    date_end: str
) -> List[Dict[str, Any]]:
    """
    Elasticsearch IT 뉴스 검색 도구 (기간 필터 포함).

    다음과 같은 경우 사용:
    - 키워드 기반으로 국내 IT 뉴스를 정확하게 검색해야 할 때.
    - 날짜 범위 내 관련 뉴스를 찾을 때.
    """

    r = get_redis_client()
    cache_key = f"news:es:{keyword}:{date_start}:{date_end}"
    cached = r.get(cache_key)
    if cached:
        return json.loads(cached)

    es = Elasticsearch(
        hosts=[f"http://{os.getenv('ELASTICSEARCH_HOST')}:{os.getenv('ELASTICSEARCH_PORT')}"],
        basic_auth=(os.getenv("ELASTICSEARCH_USERNAME"), os.getenv("ELASTICSEARCH_PASSWORD")),
        verify_certs=False
    )

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

    try:
        result = es.search(index=os.getenv("ELASTICSEARCH_DOMESTIC_INDEX_NAME"), body=query)
        hits = result.get("hits", {}).get("hits", [])

        parsed = [
            {
                "title": item["_source"].get("title"),
                "date": item["_source"].get("date"),
                "media_company": item["_source"].get("media_company"),
                "url": item["_source"].get("url"),
                "content": item["_source"].get("content", "")[:1000],
                "score": item.get("_score", 0),
                "source": "Elasticsearch"
            }
            for item in hits
        ]

        # 캐싱
        r.set(cache_key, json.dumps(parsed, ensure_ascii=False))
        return parsed

    except Exception as e:
        return [{"error": f"Elasticsearch 검색 실패: {str(e)}"}]

@tool
@async_time_logger("gnews_search_tool")
async def gnews_search_tool(en_keyword: str, lang: str = "en", country: str = "us", max_results: int = 10) -> List[Dict[str, str]]:
    """
    GNews API를 이용해 해외 뉴스를 검색합니다.

    When to use:
        - 최신 해외 뉴스 기사를 빠르게 검색할 때.
        - 글로벌 IT, 경제, 사회 트렌드를 파악할 때.
        - 영문 또는 다국어 기사 제공이 필요한 경우.

    Args:
        en_keyword (str): 검색 키워드 (예: 'cloud', 'AI', "cloud trends")
        lang (str, optional): ISO 639-1 언어 코드, 기본 'en'
        country (str, optional): ISO 3166-1 알파-2 국가 코드, 기본 'us'
        max_results (int, optional): 1-100, 기본 10
    """
    try:
        # API 키 확인
        api_key = os.getenv("GNEWS_API_KEY")
        if not api_key:
            return [{"error": "GNews API 키가 설정되지 않았습니다. .env 파일에 GNEWS_API_KEY를 추가하세요."}]

        # 검색어 전처리: 특수문자나 공백 포함 → 자동 "..." 감싸기
        en_keyword = en_keyword.strip()
        if re.search(r"[!?&=+/\- ]", en_keyword) and not (en_keyword.startswith('"') and en_keyword.endswith('"')):
            en_keyword = f'"{en_keyword}"'
        encoded_query = quote(en_keyword)

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
            return [{"error": f"'{en_keyword}'에 대한 최신 뉴스를 찾을 수 없습니다."}]

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
async def newsapi_search_tool(en_keyword: str, lang: str = "en", max_results: int = 10) -> List[Dict[str, str]]:
    """
    NewsAPI를 이용해 해외 뉴스를 검색합니다.

    When to use:
        - GNews로 부족한 해외 뉴스 데이터를 보완할 때.
        - 다양한 해외 미디어의 기사를 시간순으로 정렬해 제공할 때.
        - 특정 키워드에 대한 상세한 글로벌 보도를 탐색할 때.

    Args:
        en_keyword (str): 검색 키워드(영문 권장)
        lang (str, optional): ISO 639-1 언어 코드, 기본 'en'
        max_results (int, optional): 1-100, 기본 10
    """
    try:
        # NewsAPI 요청 URL 구성
        api_key = os.getenv("NEWS_API_KEY")  # .env 파일에 NEWSAPI_KEY 추가 필요
        if not api_key:
            return [{"error": "NewsAPI 키가 설정되지 않았습니다. .env 파일에 NEWS_API_KEY를 추가하세요."}]

        max_results = min(max_results, 100)  # NewsAPI 최대 결과 수 제한
        url = (
            f"https://newsapi.org/v2/everything?"
            f"q={quote(en_keyword)}&language={lang}&sortBy=publishedAt&pageSize={max_results}&apiKey={api_key}"
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
            return [{"error": f"'{en_keyword}'에 대한 최신 뉴스를 찾을 수 없습니다."}]

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
    블로그·커뮤니티(Daum, Naver, Reddit)에서 게시글을 검색합니다.

    When to use:
        - 국내 블로그와 해외 Reddit의 여론을 동시에 파악할 때.
        - 플랫폼별 사용자 의견과 트렌드를 비교 분석할 때.
        - 시간순으로 정렬해 여론 흐름을 확인하고 싶을 때.

    Args:
        korean_keyword (str): 한글 검색어(Daum·Naver)
        english_keyword (str): 영어 검색어(Reddit)
        platform (str, optional): 'daum' | 'naver' | 'reddit' | 'all', 기본 'all'
        max_results (int, optional): 플랫폼별 최대 결과 수, 기본 10
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
                "contents": item["data"].get("selftext", "").strip()[:500],
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
    Tavily API로 실시간 웹 페이지를 검색합니다.

    When to use:
        - 최신 웹사이트, 블로그, 기사 등을 빠르게 탐색할 때.
        - 검색 결과를 구조화된 JSON으로 받아야 할 때.
        - URL 본문 추출 도구와 연계해 상세 정보를 얻고 싶을 때.

    Args:
        keyword (str): 검색 키워드
        max_results (int, optional): 1-10, 기본 10
    """

    tavily_tool = TavilySearch(
        max_results=max_results,
        include_answer=True,
        search_depth='basic'
    )
    return tavily_tool.invoke({"query": keyword})


@tool
@async_time_logger("youtube_video_tool")
async def youtube_video_tool(query: str, max_results: int = 5):
    """
    YouTube Data API로 동영상을 검색합니다.

    When to use:
        - 최신·인기 유튜브 영상 정보를 찾을 때.
        - 영상 콘텐츠를 통해 트렌드나 주제 탐색이 필요할 때.
        - 썸네일 이미지나 영상 링크를 보고서에 활용하고 싶을 때.

    Args:
        query (str): 검색 키워드
        max_results (int, optional): 1-50, 기본 5
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
    웹 또는 PDF의 원문 텍스트를 추출합니다.

    When to use:
        - 특정 URL의 본문을 장문으로 읽어야 할 때.
        - 요약, 번역, 분석을 위한 원본 텍스트가 필요할 때.

    Args:
        input_url (str): HTTP(S) 웹 페이지 또는 PDF 파일의 절대 URL
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
                text = soup.body.get_text()[:2000]
            else:
                text = soup.get_text()[:2000]
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
    GPT-4o 기반으로 단문을 번역합니다.

    When to use:
        - 한두 문장의 정확한 번역이 필요할 때.
        - 다국어 예문 학습이나 비교를 위해 적합.

    Args:
        asking (str): "what is the '...' in <language>?" 형태 질문
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
    위키피디아 문서를 요약합니다 (한국어 우선).

    When to use:
        - 공식적이고 학술적인 개념 정의가 필요할 때.
        - 한국어 문서가 없으면 영어 요약을 자동 제공할 때.

    Args:
        query (str): 검색 키워드
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
    Google Trends로 키워드 관심도를 시계열로 조회합니다.

    When to use:
        - 특정 키워드의 관심도 변화를 추적할 때.
        - 최근 트렌드 패턴을 시각적으로 분석하고 싶을 때.

    Args:
        query (str): 검색 키워드
        start_date (str, optional): YYYY-MM-DD, 기본 최근 한 달
        end_date   (str, optional): YYYY-MM-DD
    """
    try:
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
    네이버 IT 뉴스 기반 일일 트렌드 보고서를 생성합니다.

    When to use:
        - 사용자가 트렌드 보고서의 생성을 명시적으로 요구했을 때.
        - 특정 날짜의 IT 트렌드를 문서로 정리할 때.
        - 키워드 빈도와 기사 요약을 기반으로 공식 보고서가 필요할 때.

    Args:
        search_date (str, optional): YYYY-MM-DD, 기본 어제
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


def slugify(text: str) -> str:
    """한글 키워드를 ASCII 안전 문자열로 변환합니다."""
    ascii_text = unidecode(text)        # '유심' -> 'usim'
    ascii_text = ascii_text.lower()
    # 영숫자와 하이픈만 허용, 나머지는 언더바로 대체
    ascii_text = ''.join(c if c.isalnum() or c == '-' else '_' for c in ascii_text)
    return ascii_text.strip('_')

@tool
@async_time_logger("daily_news_trend_tool")
async def daily_news_trend_tool(
    *,
    search_date: str,
) -> Dict[str, Any]:
    """
    일간 트렌드를 조회하고 차트를 생성합니다.

    When to use:
        - 특정 날짜의 네이버 IT 뉴스 트렌드를 상세히 분석할 때.
        - 키워드 빈도, 연관 키워드, 기사, 차트를 한 번에 확인하고 싶을 때.

    Args:
        search_date (str): YYYY-MM-DD
    """
    # 0) Redis 캐시
    r = get_redis_client()
    cache_key = f"daily_trend_with_charts:{search_date}"
    if (cached := r.get(cache_key)):
        return json.loads(cached)

    # 1) 데이터 조회
    resp = requests.get(f"http://localhost:8080/api/insight?date={search_date}")
    resp.raise_for_status()
    data = resp.json()
    top = data.get("top_keywords", [])
    if not top:
        return {"date": search_date, "main_chart": None, "keywords": []}

    # ---------- [ 메인 차트 생성 ] ----------
    df_main = pd.DataFrame({
        "keyword": [kw["keyword"] for kw in top],
        "frequency": [kw["frequency"] for kw in top],
    })
    fig_main = px.bar(
        df_main, x="frequency", y="keyword", orientation="h",
        title=f"{search_date} 일간 메인 키워드", height=400
    )
    fig_main.update_layout(
        margin=dict(l=120, r=20, t=50, b=20),
        yaxis=dict(categoryorder="total ascending")
    )
    key_main = f"daily/{search_date}/main-bar.png"
    chart_url = upload_chart_to_s3(fig_main, key_main)

    main_chart = {
        "type": "bar",
        "url": chart_url,
        "description": "네이버 뉴스 IT 카테고리 일간 키워드 TOP 빈도수 막대 그래프",
        "top_keywords": [
            {"keyword": row["keyword"], "frequency": int(row["frequency"])}
            for _, row in df_main.iterrows()
        ]
    }

    # ---------- [ 키워드별 도넛 차트 + 기사 조회 ] ----------
    keywords_data = []

    # 기사 조회 병렬화
    article_tasks = {
        kw["keyword"]: asyncio.create_task(fetch_domestic_articles(
            keyword=kw["keyword"],
            date_start=search_date,
            date_end=search_date
        ))
        for kw in top
    }

    for kw in top:
        keyword_name = kw["keyword"]
        frequency = kw["frequency"]

        # --- 관련 키워드 도넛 차트 ---
        rels = kw.get("relatedKeywords", [])[:10]
        df_pie = pd.DataFrame([
            {"related": r["relatedKeyword"], "freq": r["frequency"]}
            for r in rels if r["frequency"] > 0
        ])
        related_chart = None
        if not df_pie.empty:
            fig_pie = px.pie(
                df_pie, names="related", values="freq", hole=0.4,
                title=f"{keyword_name} 연관 키워드 TOP{len(df_pie)}", height=350
            )
            fig_pie.update_traces(textposition="inside", textinfo="percent+label")
            fig_pie.update_layout(margin=dict(l=20, r=20, t=40, b=20))
            key_pie = f"daily/{search_date}/pie_{kw['id']}.png"
            pie_url = upload_chart_to_s3(fig_pie, key_pie)

            related_chart = {
                "type": "pie",
                "url": pie_url,
                "description": f"{keyword_name} 연관 키워드 비율 차트"
            }

        # --- 기사 ---
        articles_raw = await article_tasks[keyword_name]
        articles = [
            {
                "title": a["title"],
                "url": a["url"],
                "media_company": a["media_company"],
                "date": a["date"],
                "content": a["content"]
            }
            for a in articles_raw[:5]
        ]

        # --- 관련 키워드 목록 (snake_case로 바꿈) ---
        related_keywords = [
            {
                "keyword": r["relatedKeyword"],
                "frequency": r["frequency"]
            }
            for r in rels if r["frequency"] > 0
        ][:5]

        keywords_data.append({
            "keyword": keyword_name,
            "frequency": frequency,
            "related_keywords": related_keywords,
            "related_chart": related_chart,
            "articles": articles
        })

    result = {
        "date": search_date,
        "main_chart": main_chart,
        "keywords": keywords_data
    }

    # ---------- [ 캐싱 ] ----------
    r.set(cache_key, json.dumps(result, ensure_ascii=False))
    return result


@tool
@async_time_logger("weekly_news_trend_tool")
async def weekly_news_trend_tool(
    *,
    date: str,
) -> Dict[str, Any]:
    """
    주간 트렌드를 조회하고 차트를 생성합니다.

    When to use:
        - 특정 날짜 기준 최근 7일의 IT 뉴스 트렌드를 분석할 때.
        - 주간 키워드 패턴과 기사 흐름을 파악하고 싶을 때.

    Args:
        date (str): YYYY-MM-DD
    """
    # 0) Redis 캐시
    r = get_redis_client()
    cache_key = f"weekly_trend_with_charts:{date}"
    if (cached := r.get(cache_key)):
        return json.loads(cached)

    # 1) 주간 데이터 조회
    resp = requests.get(f"http://localhost:8080/api/insight/weekly?date={date}")
    resp.raise_for_status()
    weekly = resp.json().get("top_weekly_keywords", [])
    if not weekly:
        return {"date": date, "main_chart": None, "keywords": []}

    # ---------- [ 메인 차트 생성 ] ----------
    df_main = pd.DataFrame({
        "keyword": [kw["keyword"] for kw in weekly],
        "frequency": [kw["totalFrequency"] for kw in weekly],
    })
    fig_main = px.bar(
        df_main, x="frequency", y="keyword", orientation="h",
        title=f"{date} 주간 메인 키워드 총빈도", height=400
    )
    fig_main.update_layout(
        margin=dict(l=120, r=20, t=50, b=20),
        yaxis=dict(categoryorder="total ascending")
    )
    key_main = f"weekly/{date}/main-bar.png"
    chart_url = upload_chart_to_s3(fig_main, key_main)

    main_chart = {
        "type": "bar",
        "url": chart_url,
        "description": "네이버 뉴스 IT 카테고리 주간 키워드 총빈도 막대 그래프",
        "top_keywords": [
            {"keyword": row["keyword"], "frequency": int(row["frequency"])}
            for _, row in df_main.iterrows()
        ]
    }

    # ---------- [ 키워드별 도넛 차트 + 기사 조회 ] ----------
    keywords_data = []

    # 기사 조회 병렬화
    start_date = (datetime.fromisoformat(date) - timedelta(days=6)).strftime("%Y-%m-%d")
    article_tasks = {
        kw["keyword"]: asyncio.create_task(fetch_domestic_articles(
            keyword=kw["keyword"],
            date_start=start_date,
            date_end=date
        ))
        for kw in weekly
    }

    for kw in weekly:
        keyword_name = kw["keyword"]
        frequency = kw["totalFrequency"]

        # --- 관련 키워드 도넛 차트 ---
        rels = kw.get("relatedKeywords", [])[:10]
        df_pie = pd.DataFrame([
            {"related": r["relatedKeyword"], "freq": r["frequency"]}
            for r in rels if r["frequency"] > 0
        ])
        related_keyword_chart = None
        if not df_pie.empty:
            fig_pie = px.pie(
                df_pie, names="related", values="freq", hole=0.4,
                title=f"{keyword_name} 연관 키워드 TOP{len(df_pie)}", height=350
            )
            fig_pie.update_traces(textposition="inside", textinfo="percent+label")
            fig_pie.update_layout(margin=dict(l=20, r=20, t=40, b=20))
            key_pie = f"weekly/{date}/pie_{kw['keywordId']}.png"
            pie_url = upload_chart_to_s3(fig_pie, key_pie)

            related_keyword_chart = {
                "type": "pie",
                "url": pie_url,
                "description": f"{keyword_name} 연관 키워드 비율 차트"
            }

        # --- 기사 ---
        articles_raw = await article_tasks[keyword_name]
        articles = [
            {
                "title": a["title"],
                "url": a["url"],
                "media_company": a["media_company"],
                "date": a["date"],
                "content": a["content"]
            }
            for a in articles_raw[:5]
        ]

        # --- 관련 키워드 목록 (snake_case) ---
        related_keywords = [
            {
                "keyword": r["relatedKeyword"],
                "frequency": r["frequency"]
            }
            for r in rels if r["frequency"] > 0
        ][:5]

        keywords_data.append({
            "keyword": keyword_name,
            "frequency": frequency,
            "related_keywords": related_keywords,
            "related_keyword_chart": related_keyword_chart,
            "articles": articles
        })

    result = {
        "date": date,
        "main_chart": main_chart,
        "keywords": keywords_data
    }

    # ---------- [ 캐싱 ] ----------
    r.set(cache_key, json.dumps(result, ensure_ascii=False))
    return result


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
    미국·글로벌 주식 OHLCV 데이터를 조회합니다 (yfinance).

    When to use:
        - 글로벌 주식의 시세 데이터를 확인할 때.
        - 배당·분할 보정된 주식 흐름을 분석하고 싶을 때.

    Args:
        symbol (str): 티커 심볼
        period | start/end: 조회 범위 지정 (둘 중 하나)
        interval (str, optional): 1m-1mo, 기본 '1d'
        auto_adjust (bool): 배당·분할 보정 여부, 기본 True
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
    한국 주식 OHLCV 데이터를 조회합니다 (FinanceDataReader).

    When to use:
        - 한국 주식의 일별 시세 데이터를 확인할 때.
        - 국내 시장 분석이나 투자 트렌드를 파악하고 싶을 때.

    Args:
        symbol (str): 6자리 숫자 티커(예: '005930')
        period | start/end: 조회 범위 지정
        interval (str, optional): 현재 '1d' 고정
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
    나무위키 본문을 크롤링해 요약합니다.

    When to use:
        - 한국어 기반 상세한 정보 요약이 필요할 때.
        - 위키피디아보다 비공식적이고 최신 정보를 얻고 싶을 때.

    Args:
        keyword (str): 검색 키워드
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
@async_time_logger("dalle3_image_generation_tool")
async def dalle3_image_generation_tool(prompt: str) -> str:
    """
    DALL·E 3으로 이미지를 생성합니다.

    When to use:
        - 트렌드나 개념을 시각화한 이미지가 필요할 때.
        - 창의적인 콘텐츠 제작이나 보고서에 삽입할 이미지를 만들 때.

    Args:
        prompt (str): 원본 프롬프트(자연어)
    """

    openai.api_key = os.getenv("DALLE_API_KEY")

    try:
        llm = ChatOpenAI(model_name="gpt-4o-mini", temperature=0.7)

        template = PromptTemplate.from_template("""
            You are an expert prompt engineer for DALL·E 3.
            Rewrite the following description in **English**, adding vivid, concrete visual details.

            Instructions:
            - Describe the **scene**, **characters/objects**, and **background**.
            - Specify a **style** (e.g., photorealistic, watercolor, cyberpunk).
            - Add a **mood/atmosphere** and, if relevant, **lighting** (e.g., warm sunlight, neon glow).
            - If possible, suggest a **camera angle** (e.g., wide shot, close-up).

            Original prompt:
            "{prompt}"

            Output a detailed prompt of 50-100 words in English.
        """)

        formatted_prompt = template.format(prompt=prompt)
        enhanced_prompt = llm.invoke(formatted_prompt)

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

@tool
@async_time_logger("weather_tool")
async def weather_tool(
    location: str = "Seoul,KR",
    lang: str = "kr",
    units: str = "metric",
    forecast_types: str = "current,hourly,daily",
    include_extras: bool = True,
    today_only: bool = False
) -> Dict[str, Union[Dict, List, str]]:
    """
    OpenWeatherMap API로 날씨 정보를 조회합니다.

    When to use:
        - 특정 지역의 현재, 시간별, 일별 날씨를 확인할 때.
        - 날씨가 트렌드나 이벤트에 미치는 영향을 분석하고 싶을 때.

    Args:
        location (str): 도시명과 국가 코드 (예: "Seoul,KR")
        lang (str): 날씨 설명 언어 (예: "kr"은 한국어)
        units (str): 온도 단위 ("metric"은 °C)
        forecast_types (str): "current", "hourly", "daily" 또는 조합
        include_extras (bool): 체감 온도, 풍속 등 추가 정보 포함
        today_only (bool): 당일 데이터만 반환
    """
    # API 키 확인
    api_key = os.getenv("OPENWEATHERMAP_API_KEY")
    if not api_key:
        logger.error("OPENWEATHERMAP_API_KEY 환경 변수가 설정되지 않음")
        return {"error": "OPENWEATHERMAP_API_KEY 환경 변수가 설정되지 않았습니다."}

    # 데이터 유형 파싱
    types = [t.strip() for t in forecast_types.split(",")]
    if not all(t in ["current", "hourly", "daily"] for t in types):
        logger.error(f"잘못된 forecast_types: {forecast_types}")
        return {"error": f"잘못된 forecast_types: {forecast_types}. 'current', 'hourly', 'daily' 중 선택하세요."}

    # 공통 파라미터
    params = {
        "q": location,
        "appid": api_key,
        "lang": lang,
        "units": units
    }

    result = {}
    try:
        async with aiohttp.ClientSession() as session:
            # 현재 날씨
            if "current" in types:
                current_url = "https://api.openweathermap.org/data/2.5/weather"
                async with session.get(current_url, params=params) as response:
                    if response.status != 200:
                        error_msg = f"현재 날씨 API 호출 실패: {response.status} - {await response.text()}"
                        logger.error(error_msg)
                        return {"error": error_msg}
                    current_data = await response.json()

                current_temp = current_data["main"]["temp"]
                current_formatted_temp = f"영하 {-current_temp}°C" if current_temp < 0 else f"{current_temp}°C"
                result["current"] = {
                    "temp": current_formatted_temp,
                    "weather": current_data["weather"][0]["description"],
                    "humidity": current_data["main"]["humidity"]
                }
                if include_extras:
                    result["current"]["extras"] = {
                        "feels_like": f"영하 {-current_data['main']['feels_like']}°C" if current_data["main"]["feels_like"] < 0 else f"{current_data['main']['feels_like']}°C",
                        "wind_speed": f"{current_data['wind']['speed']} m/s",
                        "pressure": f"{current_data['main']['pressure']} hPa",
                        "precipitation": f"{current_data.get('rain', {}).get('1h', 0)} mm"
                    }

            # 시간별 및 일별 예보
            if "hourly" in types or "daily" in types:
                forecast_url = "https://api.openweathermap.org/data/2.5/forecast"
                async with session.get(forecast_url, params=params) as response:
                    if response.status != 200:
                        error_msg = f"예보 API 호출 실패: {response.status} - {await response.text()}"
                        logger.error(error_msg)
                        return {"error": error_msg}
                    forecast_data = await response.json()

                # 시간별 예보 (3시간 간격)
                if "hourly" in types:
                    forecast_list = []
                    today = datetime.now().strftime("%Y-%m-%d") if today_only else None
                    for item in forecast_data["list"]:
                        forecast_time = datetime.fromtimestamp(item["dt"]).strftime("%Y-%m-%d %H:00")
                        if today_only and not forecast_time.startswith(today):
                            continue
                        forecast_temp = item["main"]["temp"]
                        forecast_formatted_temp = f"영하 {-forecast_temp}°C" if forecast_temp < 0 else f"{forecast_temp}°C"
                        forecast_item = {
                            "time": forecast_time,
                            "temp": forecast_formatted_temp,
                            "weather": item["weather"][0]["description"]
                        }
                        if include_extras:
                            forecast_item["extras"] = {
                                "feels_like": f"영하 {-item['main']['feels_like']}°C" if item["main"]["feels_like"] < 0 else f"{item['main']['feels_like']}°C",
                                "wind_speed": f"{item['wind']['speed']} m/s",
                                "precipitation": f"{item.get('pop', 0) * 100}%",
                                "pressure": f"{item['main']['pressure']} hPa"
                            }
                        forecast_list.append(forecast_item)
                    result["hourly"] = forecast_list

                # 일별 예보
                if "daily" in types:
                    daily_dict = {}
                    today = datetime.now().strftime("%Y-%m-%d") if today_only else None
                    for item in forecast_data["list"]:
                        date = datetime.fromtimestamp(item["dt"]).strftime("%Y-%m-%d")
                        if today_only and date != today:
                            continue
                        if date not in daily_dict:
                            daily_dict[date] = {
                                "temps": [],
                                "weathers": [],
                                "pops": [],
                                "winds": []
                            }
                        daily_dict[date]["temps"].append(item["main"]["temp"])
                        daily_dict[date]["weathers"].append(item["weather"][0]["description"])
                        daily_dict[date]["pops"].append(item.get("pop", 0) * 100)
                        daily_dict[date]["winds"].append(item["wind"]["speed"])

                    daily_list = []
                    for date, data in daily_dict.items():
                        temp_max = max(data["temps"])
                        temp_min = min(data["temps"])
                        weather_counts = {}
                        for w in data["weathers"]:
                            weather_counts[w] = weather_counts.get(w, 0) + 1
                        main_weather = max(weather_counts, key=weather_counts.get)
                        daily_item = {
                            "date": date,
                            "temp_max": f"영하 {-temp_max}°C" if temp_max < 0 else f"{temp_max}°C",
                            "temp_min": f"영하 {-temp_min}°C" if temp_min < 0 else f"{temp_min}°C",
                            "weather": main_weather
                        }
                        if include_extras:
                            daily_item["extras"] = {
                                "precipitation": f"{sum(data['pops']) / len(data['pops'])}%",
                                "wind_speed": f"{sum(data['winds']) / len(data['winds'])} m/s"
                            }
                        daily_list.append(daily_item)
                    result["daily"] = daily_list

        logger.info(f"{location} 날씨 데이터 조회 완료: {forecast_types}")
        return result

    except aiohttp.ClientError as e:
        logger.error(f"API 호출 중 네트워크 오류: {str(e)}")
        return {"error": f"네트워크 오류: {str(e)}"}
    except Exception as e:
        logger.error(f"예상치 못한 오류: {str(e)}")
        return {"error": f"오류 발생: {str(e)}"}

tools = [
    es_news_search_tool,
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
    daily_news_trend_tool,
    weekly_news_trend_tool,
    namuwiki_tool,
    stock_history_tool,
    dalle3_image_generation_tool,
    kr_stock_history_tool,
    weather_tool
]