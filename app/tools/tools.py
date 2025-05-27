import asyncio
import io
import json
import logging
import os
import re
import time
import platform
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Dict, List, Union
from urllib.parse import quote
from uuid import uuid4

from matplotlib import font_manager as fm
import aiohttp
import FinanceDataReader as fdr
import matplotlib.pyplot as plt
import openai
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
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
from langchain_community.chat_models import ChatOpenAI
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
from twikit import Client

from app.utils.db_util import get_db_connection
from app.utils.redis_util import get_redis_client
from app.utils.s3_util import upload_chart_to_s3, get_s3_client_and_bucket
from app.utils.es_util import fetch_domestic_articles, fetch_foreign_articles, fetch_sentiment_distribution
from app.tools.tools_schema import *

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def async_time_logger(name: str):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start = time.perf_counter()
            result = await func(*args, **kwargs)
            end = time.perf_counter()
            logger.info(f"[{name}] Execution time: {(end - start):.3f} seconds")
            return result
        return wrapper
    return decorator

load_dotenv()
KST = timezone(timedelta(hours=9))

@tool(args_schema=DomesticITNewsSearchSchema)
@async_time_logger("domestic_it_news_search_tool")
async def domestic_it_news_search_tool(
    keyword: str,
    date_start: str | None = None,
    date_end: str | None = None
) -> Dict[str, Any]:
    """
    Domestic IT News Search Tool

    When to use:
        - When precise keyword-based search for domestic IT news is needed.
        - When searching for news within a specific date range.

    Args:
        keyword (str): Primary keyword for search
        date_start (str, optional): Search start date (YYYY-MM-DD), defaults to 60 days ago
        date_end (str, optional): Search end date (YYYY-MM-DD), defaults to yesterday

    Returns:
        Dict[str, Any]:
            - keyword (str): Search keyword
            - date_start (str): Start date
            - date_end (str): End date
            - results (List[Dict]): List of articles with title, content, date, url, media_company

    Notes:
        - Today's date (after 00:00) or future dates are not supported.
    """
    if date_start is None:
        date_start = (
            datetime.now(ZoneInfo("Asia/Seoul")) - timedelta(days=60)
        ).strftime("%Y-%m-%d")

    if date_end is None:
        date_end = (
            datetime.now(ZoneInfo("Asia/Seoul")) - timedelta(days=1)
        ).strftime("%Y-%m-%d")

    # 캐시 조회
    r = get_redis_client()
    cache_key = f"news:es:flat:{keyword}:{date_start}:{date_end}"
    if (cached := r.get(cache_key)):
        return json.loads(cached)

    es = Elasticsearch(
        hosts=[f"http://{os.getenv('ELASTICSEARCH_HOST')}:{os.getenv('ELASTICSEARCH_PORT')}"],
        basic_auth=(
            os.getenv("ELASTICSEARCH_USERNAME"),
            os.getenv("ELASTICSEARCH_PASSWORD")
        ),
        verify_certs=False
    )

    query = {
        "query": {
            "bool": {
                "must": [
                    {
                        "range": {
                            "date": {
                                "gte": f"{date_start}T00:00:00",
                                "lte": f"{date_end}T23:59:59"
                            }
                        }
                    },
                    {
                        "multi_match": {
                            "query": keyword,
                            "fields": ["title^2", "content"],
                        }
                    }
                ]
            }
        },
        "highlight": {
            "pre_tags": [""],
            "post_tags": [""],
            "fields": {
                "content": {
                    "fragment_size": 500,
                    "number_of_fragments": 3,
                    "no_match_size": 500
                }
            }
        },
        "sort": [
            {"date": {"order": "desc"}},
            {"_score": {"order": "desc"}}
        ],
        "from": 0,
        "size": 10
    }

    try:
        result = es.search(
            index=os.getenv("ELASTICSEARCH_DOMESTIC_INDEX_NAME"),
            body=query
        )
        hits = result.get("hits", {}).get("hits", [])

        result = {
            "keyword": keyword,
            "date_start": date_start,
            "date_end": date_end,
            "results": []
        }
        for h in hits:
            source = h["_source"]
            highlight = h.get("highlight", {})
            content_snippet = highlight.get("content", [(source.get("content") or "")[:1000]])[0]

            result["results"].append({
                "title": source.get("title", ""),
                "content": content_snippet,
                "date": source.get("date", ""),
                "url": source.get("url", ""),
                "media_company": source.get("media_company", "")
            })

        r.set(cache_key, json.dumps(result, ensure_ascii=False))
        return result

    except Exception as e:
        return {"error": f"Elasticsearch search failed: {str(e)}"}


@tool(args_schema=ForeignNewsSearchSchema)
@async_time_logger("foreign_news_search_tool")
async def foreign_news_search_tool(
    en_keyword: str, lang: str = "en", country: str = "us", max_results: int = 10
) -> Dict[str, Any]:
    """
    Foreign News Search Tool Using GNEWS API

    When to use:
        - When searching for foreign news articles.
        - When analyzing global trends with English keywords.

    Args:
        en_keyword (str): English keyword for search
        lang (str): Language code, defaults to 'en'
        country (str): Country code, defaults to 'us'
        max_results (int): Maximum number of articles (default 10, max 20)

    Returns:
        Dict[str, Any]:
            - keyword (str): Search keyword
            - lang (str): Language code
            - country (str): Country code
            - results (List[Dict]): List of articles with title, content, date, url, media_company
    """
    api_key = os.getenv("GNEWS_API_KEY")
    if not api_key:
        return {"error": "GNews API key is not set."}

    en_keyword = en_keyword.strip()
    if re.search(r"[!?&=+/\- ]", en_keyword) and not (en_keyword.startswith('"') and en_keyword.endswith('"')):
        en_keyword = f'"{en_keyword}"'
    encoded_query = quote(en_keyword)

    max_results = min(max_results, 20)
    url = f"https://gnews.io/api/v4/search?q={encoded_query}&lang={lang}&country={country}&max={max_results}&apikey={api_key}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"GNews API error {response.status}: {error_text}")
                data = await response.json()

        articles = data.get("articles", [])
        if not articles:
            return {
                "keyword": en_keyword,
                "lang": lang,
                "country": country,
                "results": []
            }

        result = {
            "keyword": en_keyword,
            "lang": lang,
            "country": country,
            "results": []
        }

        for article in articles[:max_results]:
            published_at = parser.parse(article["publishedAt"]).astimezone(KST).strftime("%Y-%m-%d %H:%M")
            result["results"].append({
                "title": article.get("title", ""),
                "content": article.get("content") or article.get("description") or "",
                "date": published_at,
                "url": article.get("url", ""),
                "media_company": article["source"]["name"]
            })

        return result

    except Exception as e:
        return {"error": f"GNews search failed: {str(e)}"}


@tool(args_schema=ITNewsTrendKeywordSchema)
@async_time_logger("it_news_trend_keyword_tool")
async def it_news_trend_keyword_tool(*, period: str, date: str) -> Dict[str, Any]:
    """
    IT News Keyword Trend Tool

    When to use:
        - When analyzing trending keywords in IT news for a specific period.
        - When retrieving keyword frequencies, sentiment analysis, and related articles.

    Args:
        period (str): Period of analysis ('daily', 'weekly', or 'monthly')
        date (str): Reference date (YYYY-MM-DD)

    Returns:
        Dict[str, Any]:
            - date (str): Reference date
            - main_chart_url (str): URL of the main keyword frequency bar chart
            - keywords (List[Dict]): List of keyword data, each containing:
                - keyword (str): Keyword
                - frequency (int): Frequency of the keyword
                - sentiment_percent (Dict): Sentiment distribution percentages
                - articles (List[Dict]): List of articles with title, content, date, url, media_company
    """

    r = get_redis_client()
    cache_key = f"{period}_trend:{date}:"
    if (cached := r.get(cache_key)):
        return json.loads(cached)

    if period == "daily":
        date_start = date_end = date

    elif period == "weekly":
        date_end = date
        date_start = (datetime.fromisoformat(date) - timedelta(days=7)).strftime("%Y-%m-%d")

    elif period == "monthly":
        date_end = date
        date_start = (datetime.fromisoformat(date) - timedelta(days=30)).strftime("%Y-%m-%d")

    else:
        return {"error": "Period must be 'daily' or 'weekly' or 'monthly'."}

    # PostgreSQL에서 키워드 조회
    conn = get_db_connection()
    cur = conn.cursor()
    if period == "daily":
        cur.execute("""
            SELECT keyword, SUM(frequency)
            FROM keyword_frequencies
            WHERE date = %s
            GROUP BY keyword
            ORDER BY SUM(frequency) DESC
            LIMIT 10
        """, (date,))

    else:
        cur.execute("""
            SELECT keyword, SUM(frequency)
            FROM keyword_frequencies
            WHERE date BETWEEN %s AND %s
            GROUP BY keyword
            ORDER BY SUM(frequency) DESC
            LIMIT 10
        """, (date_start, date_end))

    rows = cur.fetchall()
    cur.close()
    conn.close()

    if not rows:
        return {
            "date": date,
            "main_chart_url": None,
            "keywords": []
        }

    keywords = [kw for kw, _ in rows]
    keyword_frequencies = dict(rows)

    # 차트 생성
    df_main = pd.DataFrame({
        "keyword": keywords,
        "frequency": [keyword_frequencies[kw] for kw in keywords]
    })
    fig_main = px.bar(
        df_main, x="frequency", y="keyword",
        title="주요 키워드 빈도", height=400,
        labels={"frequency": "출현 빈도", "keyword": "키워드"}
    )
    fig_main.update_layout(
        margin=dict(l=120, r=20, t=50, b=20),
        yaxis=dict(categoryorder="total ascending"),
        font=dict(family="Noto Sans CJK KR")
    )
    key_main = f"{period}/{date}/main-bar.png"
    main_chart_url = upload_chart_to_s3(fig_main, key_main)

    # 병렬 작업 수집
    tasks = {}
    for kw in keywords:
        tasks[kw] = {
            "domestic": asyncio.create_task(fetch_domestic_articles(kw, date_start, date_end)),
            "sentiment": asyncio.create_task(fetch_sentiment_distribution(kw, date_start, date_end))
        }

    results = []
    for kw in keywords:
        dom = await tasks[kw]["domestic"]
        sent = await tasks[kw]["sentiment"]

        results.append({
            "keyword": kw,
            "frequency": keyword_frequencies[kw],
            "sentiment_percent": sent,
            "articles": dom,
        })

    result = {
        "date": date,
        "main_chart_url": main_chart_url,
        "keywords": results
    }

    r.set(cache_key, json.dumps(result, ensure_ascii=False))
    return result



@tool(args_schema=GlobalITNewsTrendReportSchema)
async def global_it_news_trend_report_tool(date_start=None, date_end=None):
    """
        Global IT News Trend Report Generation Tool (Domestic + Foreign)

        When to use:
            - When a structured IT industry trend report is needed for a given time range.
            - When analyzing domestic and foreign keyword frequencies and summarizing relevant news articles.
            - When generating a downloadable document (DOCX) with visualizations.

        Args:
            date_start (str, optional): Start date in format YYYY-MM-DD. Defaults to yesterday.
            date_end (str, optional): End date in format YYYY-MM-DD. Defaults to yesterday.

        Returns:
            List[Dict[str, Any]]:
                - On success: [{'content': download_message, 'url': presigned_url}]
                - On failure: [{'error': error_message}]

        Notes:
            - Combines top keywords from both domestic and foreign news databases.
            - Generates bar charts for each and summarizes news in structured document format.
            - Report sections: 개요 → 국내 뉴스 분석 → 해외 뉴스 분석 → 결론.
    """

    kst = ZoneInfo("Asia/Seoul")
    now = datetime.now(kst)
    yesterday = (now - timedelta(days=1)).strftime('%Y-%m-%d')

    date_start = date_start or yesterday
    date_end = date_end or yesterday

    cache_key = f"trend_report:{date_start}:{date_end}"
    r = get_redis_client()
    if cached := r.get(cache_key):
        return cached

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT keyword, SUM(frequency)
        FROM keyword_analysis
        WHERE date BETWEEN %s AND %s
        GROUP BY keyword
        ORDER BY SUM(frequency) DESC
        LIMIT 10
    """, (date_start, date_end))
    dom_rows = cur.fetchall()

    if not dom_rows:
        return [{"error": f"No domestic keywords found between {date_start} and {date_end}."}]

    cur.execute("""
        SELECT keyword, SUM(frequency)
        FROM foreign_keyword_analysis
        WHERE date BETWEEN %s AND %s
        GROUP BY keyword
        ORDER BY SUM(frequency) DESC
        LIMIT 10
    """, (date_start, date_end))
    for_rows = cur.fetchall()

    if not for_rows:
        return [{"error": f"No foriegn keywords found between {date_start} and {date_end}."}]

    cur.close()
    conn.close()

    def make_chart(rows, title_prefix):
        labels, freqs = zip(*rows)

        system = platform.system()
        font_path = None

        if system == "Darwin":
            candidates = [
                "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
                "/Library/Fonts/AppleGothic.ttf",
                "/System/Library/Fonts/AppleSDGothicNeo.ttc"
            ]
        elif system == "Linux":
            candidates = [
                "/usr/share/fonts/noto/NotoSansCJKkr-Regular.otf"
            ]
        elif system == "Windows":
            candidates = [
                "C:/Windows/Fonts/malgun.ttf",
                "C:/Windows/Fonts/batang.ttc",
                "C:/Windows/Fonts/gulim.ttc"
            ]
        else:
            candidates = []

        for path in candidates:
            if os.path.exists(path):
                font_path = path
                break

        if font_path:
            fm.fontManager.addfont(font_path)
            font_prop = fm.FontProperties(fname=font_path)
            font_name = font_prop.get_name()
            plt.rcParams['font.family'] = font_name
            print(f"[DEBUG] 적용된 폰트: {font_name} @ {font_path}")
        else:
            plt.rcParams['font.family'] = 'Arial'
            print("[DEBUG] 폰트 파일 없음, Arial 사용됨")

        plt.rcParams['axes.unicode_minus'] = False

        plt.figure(figsize=(8, 5))
        bars = plt.bar(labels, freqs, color='skyblue')
        plt.title(f"{date_start} ~ {date_end} {title_prefix} 키워드 빈도")
        for bar in bars:
            yval = bar.get_height()
            plt.text(bar.get_x() + bar.get_width() / 2, yval + 0.2, int(yval), ha='center')
        base_dir = os.path.abspath("./data/reports")
        os.makedirs(base_dir, exist_ok=True)
        filename = f"{title_prefix}_keywords_{date_start}_{date_end}_{uuid4().hex[:6]}.png"
        path = os.path.join(base_dir, filename)
        plt.tight_layout()
        plt.savefig(path)
        plt.close()
        return path, '\n'.join([f"- {kw}: {fr} 빈도" for kw, fr in rows])

    dom_chart_path, dom_kw_summary = make_chart(dom_rows, "국내")
    for_chart_path, for_kw_summary = make_chart(for_rows, "해외")

    async def summarize_articles(article_list):
        summaries = []
        for article in article_list:
            summary = f"- {article['title']} ({article['date']}, {article['media_company']})\n  {article['content'].strip()}"
            summaries.append(summary)
        return "\n".join(summaries)

    dom_articles = ""
    for kw, _ in dom_rows:
        articles = await fetch_domestic_articles(kw, date_start, date_end)
        dom_articles += f"[국내 키워드: {kw}]\n"
        dom_articles += await summarize_articles(articles) + "\n\n"

    for_articles = ""
    for kw, _ in for_rows:
        articles = await fetch_foreign_articles(kw, date_start, date_end)
        for_articles += f"[해외 키워드: {kw}]\n"
        for_articles += await summarize_articles(articles) + "\n\n"

    prompt = PromptTemplate.from_template("""
    당신은 기업 리서치 보고서를 전문적으로 작성하는 AI입니다.
    다음은 국내외 IT 뉴스 키워드 빈도 분석 및 관련 기사 내용을 요약한 결과입니다.
    작성 시 다음 규칙을 반드시 따르세요:
    - 각 섹션은 다음과 같이 시작: "개요:", "국내 뉴스 분석:", "해외 뉴스 분석:", "결론:"
    - 섹션 제목은 반드시 맨 앞에 한 줄로 출력하세요 (예: "개요:")
    - markdown/기호 사용 없이 서술식 문단 작성
    - 분석에 활용된 키워드는 반드시 요약문에 녹여서 설명
    - 통계/수치가 포함될 경우 자연스럽게 설명에 포함

    [분석 기간]
    {date_start} ~ {date_end}

    [국내 키워드 요약]
    {domestic_keywords}

    [국내 뉴스 기사]
    {domestic_articles}

    [해외 키워드 요약]
    {foreign_keywords}

    [해외 뉴스 기사]
    {foreign_articles}
    """)

    chain = LLMChain(
        llm=ChatOpenAI(model="gpt-4o-mini", temperature=0.3),
        prompt=prompt
    )

    result = chain.invoke({
        "date_start": date_start,
        "date_end": date_end,
        "domestic_keywords": dom_kw_summary,
        "domestic_articles": dom_articles,
        "foreign_keywords": for_kw_summary,
        "foreign_articles": for_articles
    })
    gpt_text = result["text"]

    def extract_section(text, title):
        pattern = rf"{title}:\s*(.*?)(?=\n(?:개요|국내 뉴스 분석|해외 뉴스 분석|결론):|\Z)"
        match = re.search(pattern, text, re.DOTALL)
        return match.group(1).strip() if match else "[내용 없음]"

    doc = Document()
    doc.add_heading("개요", level=1)
    doc.add_paragraph(extract_section(gpt_text, "개요"))

    doc.add_heading("국내 뉴스 분석", level=1)
    doc.add_picture(dom_chart_path, width=Inches(5.5))
    doc.add_paragraph(extract_section(gpt_text, "국내 뉴스 분석"))

    doc.add_heading("해외 뉴스 분석", level=1)
    doc.add_picture(for_chart_path, width=Inches(5.5))
    doc.add_paragraph(extract_section(gpt_text, "해외 뉴스 분석"))

    doc.add_heading("결론", level=1)
    doc.add_paragraph(extract_section(gpt_text, "결론"))

    report_filename = f"Industry_Trend_Report_{date_start}_{date_end}_{uuid4().hex[:8]}.docx"
    report_path = os.path.join("./data/reports", report_filename)
    doc.save(report_path)

    s3_key = f"report/{os.path.basename(report_path)}"
    s3, bucket = get_s3_client_and_bucket()
    with open(report_path, "rb") as f:
        s3.put_object(
            Body=f,
            Bucket=bucket,
            Key=s3_key,
            ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

    url = f"https://{bucket}.s3.amazonaws.com/{s3_key}"
    r.setex(cache_key, timedelta(days=7), url)
    return url



@tool(args_schema=GoogleTrendsSchema)
@async_time_logger("google_trends_tool")
async def google_trends_tool(query: str, start_date: str = None, end_date: str = None) -> Dict[str, Union[str, List[float], List[str]]]:
    """
    Google Trends Tool

    When to use:
        - When tracking changes in keyword interest over time.
        - When visualizing recent trend patterns.

    Args:
        query (str): Search keyword
        start_date (str, optional): Start date (YYYY-MM-DD), defaults to last month
        end_date (str, optional): End date (YYYY-MM-DD)

    Returns:
        Dict[str, Union[str, List[float], List[str]]]:
            - query (str): Searched keyword
            - interest_data (List[float]): Interest scores by date
            - dates (List[str]): Dates (YYYY-MM-DD)
            - chart_url (str): URL of the interest timeseries chart on S3
            - chart_description (str): Description of the chart
            - error (str, optional): Error message if applicable

    Notes:
        - chart_url and chart_description are used for visualization insertion.
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

        # 시계열 그래프 생성
        df_trend = pd.DataFrame({
            "date": dates,
            "interest": interest_data
        })

        fig = px.line(
            df_trend, x="date", y="interest",
            title=f"Google 트렌드 관심도 추이: {query}",
            markers=True
        )
        fig.update_layout(
            xaxis_title="날짜",
            yaxis_title="관심도",
            height=400,
            font=dict(family="Noto Sans CJK KR")
        )

        # S3에 업로드
        key = f"google_trends/{slugify(query)}_trend.png"
        chart_url = upload_chart_to_s3(fig, key)

        return {
            "query": query,
            "interest_data": interest_data,
            "dates": dates,
            "chart_url": chart_url,
            "chart_description": f"Google Trends interest timeseries chart for {query}"
        }

    except Exception as e:
        if '429' in str(e):
            return {"error": f"Rate limit exceeded for query '{query}'. Try again later."}
        return {"error": f"Error retrieving Google Trends data: {str(e)}"}

def slugify(text: str) -> str:
    """Convert Korean keywords to ASCII strings."""
    ascii_text = unidecode(text)
    ascii_text = ascii_text.lower()
    # 영숫자와 하이픈만 허용, 나머지는 언더바로 대체
    ascii_text = ''.join(c if c.isalnum() or c == '-' else '_' for c in ascii_text)
    return ascii_text.strip('_')


@async_time_logger("search_daum_blogs")
async def search_daum_blogs(keyword: str, max_results: int = 10) -> List[Dict[str, str]]:
    """
    Daum Blog Post Search Function

    Args:
        keyword (str): Search keyword
        max_results (int): Maximum number of results

    Returns:
        List[Dict[str, str]]: List of blog posts with title, url, content, datetime, source
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
                "content": item["contents"],
                "datetime": parser.parse(item["datetime"]).strftime("%Y-%m-%d %H:%M"),
                "source": "daum_blog"
            }
            for item in data.get("documents", [])
        ]
    except Exception as e:
        raise RuntimeError(f"Daum API error: {str(e)}")

def clean_html(text: str) -> str:
    """Remove HTML tags and entities"""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)  # Remove HTML tags
    text = re.sub(r"&[^;]*;", "", text)  # Remove HTML entities
    return text

@async_time_logger("search_naver_blogs")
async def search_naver_blogs(keyword: str, max_result: int = 10) -> List[Dict[str, str]]:
    """
    Naver Blog Search Function

    Args:
        keyword (str): Search keyword
        max_result (int): Maximum number of results

    Returns:
        List[Dict[str, str]]: List of blog posts with title, url, content, datetime, source
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
                "content": clean_html(item["description"]),
                "datetime": post_date.strftime("%Y-%m-%d 00:00"),
                "source": "naver_blog"
            })
        return posts
    except Exception as e:
        raise RuntimeError(f"Naver blog search error: {str(e)}")


def get_reddit_access_token():
    """
    Obtain Reddit access token
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
        raise Exception(f"Reddit OAuth authentication failed: {response.json()}")

    return response.json().get("access_token")


@async_time_logger("search_reddit_posts")
async def search_reddit_posts(keyword: str, max_result: int = 10) -> List[Dict[str, str]]:
    """
    Reddit Post Search Function
    """
    try:
        access_token = get_reddit_access_token()
        headers = {
            "Authorization": f"bearer {access_token}",
            "User-Agent": "web:com.dbfis.chatbot:v1.0.0"
        }
        url = f"https://oauth.reddit.com/search?q={keyword}&limit={max_result}&sort=hot"
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            raise Exception(f"Reddit search failed: {response.json()}")
        data = response.json()
        return [
            {
                "title": item["data"]["title"],
                "url": f"https://www.reddit.com{item['data']['permalink']}",
                "content": item["data"].get("selftext", "").strip()[:500],
                "datetime": datetime.utcfromtimestamp(item["data"]["created_utc"]).replace(tzinfo=timezone.utc).astimezone(KST).strftime('%Y-%m-%d %H:%M'),
                "source": "reddit"
            }
            for item in data.get("data", {}).get("children", [])
        ]
    except Exception as e:
        raise RuntimeError(f"Reddit search error: {str(e)}")


@async_time_logger("search_x_tweets")
async def search_x_tweets(keyword: str, max_results: int = 10, min_faves: int = 10) -> List[Dict[str, Any]]:
    logger.info(f"[X] search_x_tweets 호출됨 | keyword: {keyword}, max_results: {max_results}, min_faves: {min_faves}")

    KST = timezone(timedelta(hours=9))
    SPAM_WORDS = ["무료", "프로모션", "클릭", "구독", "이벤트", "광고", "free", "click", "promo", "win"]

    load_dotenv()
    username = os.getenv("X_USERNAME")
    email = os.getenv("X_EMAIL")
    password = os.getenv("X_PASSWORD")
    cookies_file = "twitter_cookies.json"

    if not all([username, email, password]):
        logger.error("[X] 인증 정보 누락: .env 확인")
        return [{"source": "x", "error": "X_USERNAME, X_EMAIL, 또는 X_PASSWORD 환경 변수가 설정되지 않았습니다."}]

    max_results = max(10, min(max_results, 100))

    try:
        client = Client(language="ko-KR")

        if os.path.exists(cookies_file):
            try:
                client.load_cookies(cookies_file)
                logger.info("[X] 쿠키 로드 완료, 유효성 검사 중...")
                await client.get_user_by_screen_name(username)
            except Exception as e:
                logger.warning(f"[X] 쿠키 유효하지 않음. 재로그인 시도: {e}")
                await client.login(auth_info_1=username, auth_info_2=email, password=password)
                await client.get_user_by_screen_name(username)
                client.save_cookies(cookies_file)
        else:
            logger.info("[X] 쿠키 없음. 로그인 시도")
            await client.login(auth_info_1=username, auth_info_2=email, password=password)
            await client.get_user_by_screen_name(username)
            client.save_cookies(cookies_file)

        query = f"{keyword} -filter:replies" if min_faves == 0 else f"{keyword} -filter:replies min_faves:{min_faves}"
        logger.info(f"[X] 트윗 검색 쿼리: {query}")

        tweets = await client.search_tweet(query=query, product="Latest")
        logger.info(f"[X] 원본 트윗 수: {len(tweets)}")

        tweet_list = []
        for tweet in tweets:
            text = tweet.text.strip()
            if len(text) <= 20: continue
            if any(spam_word.lower() in text.lower() for spam_word in SPAM_WORDS): continue
            if text.count("#") > 5: continue
            if tweet.user.followers_count < 100: continue

            tweet_list.append({
                "id": tweet.id,
                "text": text,
                "created_at": parser.parse(tweet.created_at),
                "url": f"https://x.com/i/status/{tweet.id}"
            })

        logger.info(f"[X] 필터링 후 트윗 수: {len(tweet_list)}")

        tweet_list.sort(key=lambda x: x["created_at"], reverse=True)

        results = [
            {
                "title": f"트윗 ID: {tweet['id']}",
                "url": tweet['url'],
                "content": tweet['text'][:500],
                "datetime": tweet['created_at'].astimezone(KST).strftime("%Y-%m-%d %H:%M"),
                "source": "x"
            }
            for tweet in tweet_list[:max_results]
        ]

        logger.info(f"[X] 최종 반환 결과 수: {len(results)}")

        if not results:
            logger.warning(f"[X] '{keyword}'에 대한 결과 없음")
            return []

        await asyncio.sleep(5)
        return results

    except Exception as e:
        logger.error(f"[X] 트윗 검색 오류: {str(e)}")
        return [{"source": "x", "error": f"트윗 검색 실패: {str(e)}"}]


@tool(args_schema=CommunitySearchSchema)
@async_time_logger("community_search_tool")
async def community_search_tool(
    korean_keyword: str,
    english_keyword: str,
    platform: str = "all",
    max_results: int = 20
) -> Dict[str, Any]:
    """
    Blog(Naver, Daum) and Community(Reddit, X) Post Search Tool

    When to use:
        - When analyzing public sentiment on blogs or Social Network platforms.

    Args:
        korean_keyword (str): Korean keyword for search
        english_keyword (str): English keyword for search
        platform (str): 'all', 'daum', 'naver', 'reddit', 'x'
        max_results (int): Maximum number of results (default: 20)

    Returns:
        Dict[str, Any]:
            - korean_keyword (str): Korean keyword
            - english_keyword (str): English keyword
            - platform (str): Platform used
            - results (List[Dict]): List of posts with title, url, content, datetime, source
            - errors (List[Dict]): List of errors from platforms
    """
    # 플랫폼별 max_results 제한 (최대 20개)
    platform_max_results = min(max_results // 2, 20)

    tasks = []
    if platform in ["all", "daum"]:
        tasks.append(search_daum_blogs(korean_keyword, platform_max_results))
    if platform in ["all", "naver"]:
        tasks.append(search_naver_blogs(korean_keyword, platform_max_results))
    if platform in ["all", "reddit"]:
        tasks.append(search_reddit_posts(english_keyword, platform_max_results))
    if platform in ["all", "x"]:
        tasks.append(search_x_tweets(english_keyword, platform_max_results))

    results_nested = await asyncio.gather(*tasks, return_exceptions=True)
    results = []
    errors = []

    for sublist in results_nested:
        if isinstance(sublist, Exception):
            errors.append({"source": "unknown", "error": str(sublist)})
            continue
        for item in sublist:
            if "error" in item:
                errors.append(item)
            else:
                results.append(item)

    # 최신순 정렬
    results_sorted = sorted(
        results,
        key=lambda x: x["datetime"] if isinstance(x["datetime"], datetime) else parser.parse(x["datetime"]),
        reverse=True
    )

    if platform != "all":
        return {
            "korean_keyword": korean_keyword,
            "english_keyword": english_keyword,
            "platform": platform,
            "results": results_sorted[:max_results],
            "errors": errors
        }

    # platform == "all"인 경우 균등 분배
    platforms = set(post["source"] for post in results_sorted)
    per_platform = max_results // max(len(platforms), 1)

    balanced_results = []
    for plat in platforms:
        posts = [post for post in results_sorted if post["source"] == plat][:per_platform]
        balanced_results.extend(posts)

    # 부족한 경우 남은 거 채우기
    remaining = [post for post in results_sorted if post not in balanced_results]
    needed = max_results - len(balanced_results)
    balanced_results.extend(remaining[:needed])

    return {
        "korean_keyword": korean_keyword,
        "english_keyword": english_keyword,
        "platform": platform,
        "results": balanced_results[:max_results],
        "errors": errors
    }


@tool(args_schema=YoutubeVideoSchema)
@async_time_logger("youtube_video_tool")
async def youtube_video_tool(query: str, max_results: int = 5):
    """
    YouTube Video Search Tool using YouTube Data API

    When to use:
        - When searching for recent or popular YouTube videos.
        - When exploring trends or topics through video content.
        - When thumbnails or video links are needed for reports.

    Args:
        query (str): Search keyword
        max_results (int, optional): Maximum number of results (1-50, default 5)

    Returns:
        List[Dict]: List of videos with videoId, title, description, channelTitle, publishedAt, thumbnailUrl, url
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
            "url": f"https://www.youtube.com/watch?v={item['id']['videoId']}"
        }
        for item in search_response["items"]
    ]
    return results


@tool(args_schema=SearchWebSchema)
@async_time_logger("web_search_tool")
async def web_search_tool(keyword: str, max_results: int=10) -> List[Dict[str, str]]:
    """
    Real-time Web Page Search Tool using Tavily API

    When to use:
        - When quickly exploring recent websites, blogs, or articles.
        - When structured JSON search results are required.
        - When integrating with a URL content extraction tool for detailed information.

    Args:
        keyword (str): Search keyword
        max_results (int, optional): Maximum number of results (1-20, default 10)

    Returns:
        List[Dict[str, str]]: List of search results with title, content, and URL
    """
    try:
        tavily_tool = TavilySearch(
            max_results=max_results,
            include_images=True
        )
        result = await tavily_tool.ainvoke({"query": keyword})
        logger.info(f"Tavily search result: {result}")
        return result
    except Exception as e:
        logger.error(f"Tavily search failed: {str(e)}")
        return []


@tool(args_schema=RequestUrlSchema)
@async_time_logger("request_url_tool")
async def request_url_tool(input_url: str) -> List[Dict[str, Any]]:
    """
    Web or PDF Content Extraction Tool

    When to use:
        - When extracting full text from a specific URL.
        - When raw text is needed for summarization, translation, or analysis.

    Args:
        input_url (str): Absolute URL of an HTTP(S) webpage or PDF file

    Returns:
        List[Dict[str, Any]]: List containing extracted content or error message
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
                return [{"error": "Unable to extract text from PDF."}]
            return [{"content": text.strip()}]
        else:
            soup = BeautifulSoup(response.text, "html.parser")
            if soup.body:
                text = soup.body.get_text()[:5000]
            else:
                text = soup.get_text()[:5000]
            text = re.sub(r"\s+", " ", text).strip()
            if not text or len(text) < 100:
                return [{"error": "No valid text found."}]
            if "example domain" in text.lower():
                return [{"error": "No valid text found."}]
            return [{"content": text}]

    except requests.exceptions.SSLError:
        return [{"error": "[Blocked] Invalid SSL certificate detected, site deemed insecure."}]
    except requests.RequestException as e:
        return [{"error": f"[Request Failed] {str(e)}"}]
    except Exception as e:
        return [{"error": f"[Processing Error] {str(e)}"}]


@tool(args_schema=WikipediaSchema)
@async_time_logger("wikipedia_tool")
async def wikipedia_tool(query: str) -> List[Dict[str, Any]]:
    """
    Wikipedia Summary Tool (Korean prioritized)

    When to use:
        - When formal and academic definitions are needed.
        - When English summaries are automatically provided if Korean is unavailable.

    Args:
        query (str): Search keyword

    Returns:
        List[Dict[str, Any]]: List containing summarized content or error message
    """
    # redis 캐싱
    r = get_redis_client()

    # 한국어 우선, 실패 시 영어
    for lang in ["ko", "en"]:
        try:
            cache_key = f"wiki:{lang}:{query}"
            cached = r.get(cache_key)
            if cached:
                return [{"content": cached}]

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
            summaries = result.split("\n")[:10]  # 최대 10줄 요약
            content = f"Wikipedia Summary ({lang}):\n" + "\n".join(summaries) if summaries else f"No information found for '{query}' on Wikipedia ({lang})."
            r.set(cache_key, content)
            return [{"content": content}]
        except Exception as e:
            if lang == "en":  # 영어까지 실패 시
                return [{"error": f"Wikipedia search error: {str(e)}"}]
            continue


@tool(args_schema=NamuwikiSchema)
@async_time_logger("namuwiki_tool")
async def namuwiki_tool(keyword: str) -> List[Dict[str, Any]]:
    """
    Namuwiki Content Crawling and Summary Tool

    When to use:
        - When detailed Korean-based information is needed.
        - When seeking more informal and up-to-date information compared to Wikipedia.

    Args:
        keyword (str): Search keyword

    Returns:
        List[Dict[str, Any]]: List containing summarized content or error message
    """
    # redis 캐싱
    r = get_redis_client()
    cache_key = f"namuwiki:{keyword}"
    cached = r.get(cache_key)
    if cached:
        return [{"content": cached}]

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

        content = "\n\n".join(extracted[:30]) if extracted else "Content is empty."
        r.set(cache_key, content)
        return [{"content": content}]

    except Exception as e:
        return [{"error": f"[Error] Namuwiki request failed: {str(e)}"}]


@tool(args_schema=StockHistorySchema)
@async_time_logger("stock_history_tool")
async def stock_history_tool(
    symbol: str,
    start: str,
    end: str,
) -> Dict[str, Any]:
    """
    Unified Stock OHLCV Retrieval Tool (Global + Korean)

    Args:
        symbol (str): Stock ticker (e.g., 'AAPL') or 6-digit Korean stock code (e.g., '005930').
        start (str): Start date in 'YYYY-MM-DD' format.
        end (str): End date in 'YYYY-MM-DD' format.

    Returns:
        dict: {
            symbol (str): Queried stock symbol,
            history (list[dict]): List of daily OHLCV data (open, high, low, close, volume),
            info (dict): Additional metadata (only for global stocks),
            status (str): 'success' or 'failed',
            message (str|None): Error details if failed,
            chart_url (str): S3 URL to the generated stock chart,
            chart_description (str): Human-readable description of the chart
        }
    """
    def is_korean_symbol(sym: str) -> bool:
        return bool(re.fullmatch(r"\d{6}", sym))

    response = {
        "symbol": symbol,
        "history": [],
        "info": {},
        "status": "failed",
        "message": None
    }

    try:
        if is_korean_symbol(symbol):
            df = fdr.DataReader(symbol, start=start, end=end)
            info = {}
        else:
            ticker = yf.Ticker(symbol)
            df = ticker.history(
                start=start,
                end=end,
                interval="1d",
                auto_adjust=True,
                back_adjust=False
            )
            df = df.dropna(subset=["Close", "Volume"])
            df = df[df["Volume"] > 0]
            info = ticker.info or {}

        if df.empty:
            response["message"] = f"No valid trading records found for '{symbol}'."
            return response

        records = [{
            "date": idx.strftime("%Y-%m-%d"),
            "open": float(row["Open"]),
            "high": float(row["High"]),
            "low": float(row["Low"]),
            "close": float(row["Close"]),
            "volume": int(row["Volume"])
        } for idx, row in df.iterrows()]

        response.update({
            "history": records,
            "info": info,
            "status": "success"
        })

        df_vis = pd.DataFrame(records)
        df_vis["date"] = pd.to_datetime(df_vis["date"])

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_vis["date"], y=df_vis["close"],
            name="Close Price", mode="lines+markers",
            line=dict(color="blue")
        ))
        fig.add_trace(go.Bar(
            x=df_vis["date"], y=df_vis["volume"],
            name="Volume", yaxis="y2",
            marker_color="lightgray", opacity=0.5
        ))

        fig.update_layout(
            title=f"{symbol} 주가 및 거래량",
            xaxis=dict(title="날짜"),
            yaxis=dict(title="종가"),
            yaxis2=dict(title="거래량", overlaying="y", side="right"),
            height=400,
            font=dict(family="Noto Sans CJK KR")
        )
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])

        key = f"stocks/{slugify(symbol)}_chart.png"
        chart_url = upload_chart_to_s3(fig, key)

        response.update({
            "chart_url": chart_url,
            "chart_description": f"{symbol} stock price and volume chart"
        })

        return response

    except Exception as e:
        response["message"] = f"Failed to retrieve stock data: {str(e)}"
        return response


@tool(args_schema=Dalle3ImageGenerationSchema)
@async_time_logger("dalle3_image_generation_tool")
async def dalle3_image_generation_tool(prompt: str) -> List[Dict[str, Any]]:
    """
    DALL·E 3 Image Generation Tool

    When to use:
        - When visualizations of trends or concepts are needed.

    Args:
        prompt (str): Image description (natural language)

    Returns:
        List[Dict]:
            - content (str): 'Image generated successfully'
            - url (str): Image URL
    """
    openai.api_key = os.getenv("DALLE_API_KEY")

    try:
        llm = ChatOpenAI(model_name="gpt-4o-mini", temperature=0.7)

        template = PromptTemplate.from_template(rf"""
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
        return [{"content": "Image generated successfully", "url": dalle_response.data[0].url}]

    except Exception as e:
        print(f"DALL·E generation error: {str(e)}")
        return [{"error": f"Image generation failed: {str(e)}"}]

@tool(args_schema=PaperSearchSchema)
@async_time_logger("paper_search_tool")
async def paper_search_tool(
        query: str,
        max_results: int = 10,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        sort_by: str = "relevance"
) -> Dict[str, Any]:
    """
    OpenAlex Academic Paper Search Tool

    When to use:
        - When exploring academic papers across all disciplines (including arXiv, journals, etc.).
        - When retrieving paper titles, abstracts, URLs, authors, and metadata.

    Args:
        query (str): Search keyword
        max_results (int): Maximum number of papers to return (default 10, max 10)
        start_date (str, optional): Search start date (YYYY-MM-DD) (default 90 days ago)
        end_date (str, optional): Search end date (YYYY-MM-DD) (default today)
        sort_by (str): Sort by 'relevance' or 'date'

    Returns:
        Dict[str, Any]:
            - query (str): Search keyword
            - results (List[Dict]): List of papers with title, abstract, published_date, url, authors
            - error (str, optional): Error message if applicable
    """
    # 기본 날짜 설정
    if start_date is None:
        start_date = (datetime.today() - timedelta(days=90)).strftime("%Y-%m-%d")
    if end_date is None:
        end_date = datetime.today().strftime("%Y-%m-%d")

    # 캐시 키 생성
    cache_key = f"paper:openalex:{query}:{max_results}:{start_date or ''}:{end_date or ''}:{sort_by}"
    r = get_redis_client()
    if cached := r.get(cache_key):
        return json.loads(cached)

    # 정렬 및 필터 설정
    filter_params = [f"title.search:{query.replace(' ', '%20')}"]
    if start_date:
        filter_params.append(f"from_publication_date:{start_date}")
    if end_date:
        filter_params.append(f"to_publication_date:{end_date}")

    sort_param = "relevance_score:desc" if sort_by == "relevance" else "publication_date:desc"
    if max_results > 10:
        max_results = 10  # OpenAlex 페이지당 최대 25, 여기서는 10으로 제한

    # OpenAlex API URL
    base_url = "https://api.openalex.org/works"
    query_url = f"{base_url}?filter={','.join(filter_params)}&sort={sort_param}&per_page={max_results}"

    try:
        # API 요청
        response = requests.get(query_url)
        response.raise_for_status()
        data = response.json()

        # 결과 수집
        results = []
        for paper in data.get("results", []):
            published_date = paper.get("publication_date", "N/A")
            abstract = paper.get("abstract") or paper.get("abstract_inverted_index")
            if isinstance(abstract, dict):
                abstract = " ".join(word for word, _ in abstract.items())[:1000]
            elif not abstract:
                abstract = "No abstract available."

            results.append({
                "title": paper.get("title", "No title"),
                "abstract": abstract.strip()[:1000],
                "published_date": published_date,
                "url": paper.get("primary_location", {}).get("landing_page_url", paper.get("id")),
                "authors": [author["author"]["display_name"] for author in paper.get("authorships", [])]
            })

        # 결과가 없거나 필터링 후 비어 있는 경우
        if not results:
            result = {
                "query": query,
                "results": [],
                "message": "No papers found."
            }
        else:
            result = {
                "query": query,
                "results": results[:max_results]
            }

        # 캐시에 저장 (7일 TTL)
        r.setex(cache_key, timedelta(days=7), json.dumps(result, ensure_ascii=False))
        return result

    except Exception as e:
        logger.error(f"OpenAlex search failed: {str(e)}")
        return {"error": f"Paper search failed: {str(e)}"}


tools = [
    web_search_tool,
    domestic_it_news_search_tool,
    foreign_news_search_tool,
    global_it_news_trend_report_tool,
    it_news_trend_keyword_tool,
    google_trends_tool,
    community_search_tool,
    youtube_video_tool,
    request_url_tool,
    wikipedia_tool,
    namuwiki_tool,
    stock_history_tool,
    dalle3_image_generation_tool,
    paper_search_tool
]