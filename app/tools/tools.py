import os

from dotenv import load_dotenv
import time
from datetime import datetime, timedelta
import requests
import re
import io
from bs4 import BeautifulSoup
from pypdf import PdfReader
from googleapiclient.discovery import build
from requests.auth import HTTPBasicAuth
from langchain.prompts import PromptTemplate
from langchain.chat_models import ChatOpenAI
from langchain.chains.llm import LLMChain
from langchain_community.tools import WikipediaQueryRun
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_community.utilities import WikipediaAPIWrapper
from langchain.tools import tool
from pytrends.request import TrendReq
from typing import Dict, Union, List
from app.utils.milvus import get_embedding_model, get_vector_store
from app.utils.db import get_db_connection
from app.utils.redis_util import get_redis_client
import matplotlib
matplotlib.use('Agg') # 백엔드에서 작업
import matplotlib.pyplot as plt
from uuid import uuid4
from docx import Document
from docx.shared import Inches
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
load_dotenv()

@tool
async def rag_news_search_tool(query: str) -> List[Dict[str, Union[str, float]]]:
    """
    Milvus에서 RAG를 이용한 의미 기반 뉴스 기사 검색 도구.

    Milvus에 저장된 뉴스 기사 데이터에서 입력된 키워드와 의미상 가장 유사한 기사를 검색합니다.
    최근 30일 내 등록된 문서를 우선 검색하며, 충분한 결과가 없을 경우 전체 데이터에서 추가 검색을 수행합니다.

    Args:
        query (str): 검색할 키워드

    Returns:
        List[Dict[str, Union[str, float]]]: 검색된 뉴스 기사 목록
            - "title" (str): 기사 제목
            - "date" (str): 기사 발행일
            - "media_company" (str): 언론사 이름
            - "url" (str): 기사 URL
            - "score" (float): 유사도 점수
    """

    # Embedding 모델 및 벡터 저장소 가져오기
    embedding_model = get_embedding_model()
    vector_store = get_vector_store()

    query_embedding = embedding_model.embed_query(query)

    # 최신 문서 우선 검색 (최근 30일 내)
    recent_timestamp = int(time.time()) - (30 * 86400)
    latest_results = vector_store.similarity_search_with_score_by_vector(
        query_embedding, k=5, filter={"timestamp": {"$gte": recent_timestamp}}
    )

    # 최신 문서가 부족하면 전체 검색 추가
    if len(latest_results) < 5:
        additional_results = vector_store.similarity_search_with_score_by_vector(query_embedding, k=5)
        combined_results = latest_results + [doc for doc in additional_results if doc not in latest_results]
    else:
        combined_results = latest_results

    return [
        {
            "title": doc.metadata["title"],
            "date": doc.metadata["date"],
            "media_company": doc.metadata["media_company"],
            "url": doc.metadata["url"],
            "score": score
        }
        for doc, score in combined_results
    ]

@tool
async def daum_blog_tool(keyword, max_results=10):
    """
    커뮤니티 트렌드 - Daum 블로그 검색 도구.

    Daum 블로그 API를 사용하여 특정 키워드(keyword)와 관련된 블로그 게시글을 검색합니다.

    Args:
        keyword (str): 검색할 키워드
        max_results (int, optional): 최대 검색 결과 수 (기본값: 10)

    Returns:
        List[Dict[str, str]]: 검색된 블로그 게시글 목록
            - "title" (str): 게시글 제목
            - "url" (str): 게시글 URL
            - "contents" (str): 게시글 내용 요약
            - "datetime" (str): 게시글 작성일 (ISO 형식)
    """

    headers = {"Authorization": f"KakaoAK {os.getenv("DAUM_API_KEY")}"}
    params = {"query": keyword, "size": max_results, "sort": "accuracy"}

    try:
        response = requests.get(os.getenv("DAUM_API_URL"), headers=headers, params=params)
        response.raise_for_status()
        data = response.json()

        results = [
            {
                "title": item["title"],
                "url": item["url"],
                "contents": item["contents"],
                "datetime": item["datetime"]
            }
            for item in data.get("documents", [])
        ]
        return results

    except requests.exceptions.RequestException as e:
        return {"error": f"Daum API 요청 실패: {str(e)}"}


def clean_html(text: str) -> str:
    """HTML 태그 및 엔티티 제거"""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)  # HTML 태그 제거
    text = re.sub(r"&[^;]*;", "", text)  # HTML 엔티티 제거
    return text

@tool
async def naver_blog_tool(keyword: str, max_result: int = 10, days: int = 30) -> List[Dict[str, str]]:
    """
    커뮤니티 트렌드 - 네이버 블로그 검색 도구.

    네이버 블로그에서 특정 키워드(keyword)로 최근 일정 기간(days) 내 게시된 글을 검색합니다.

    Args:
        keyword (str): 검색할 키워드
        max_result (int, optional): 최대 검색 결과 수 (기본값: 10)
        days (int, optional): 검색할 기간 (최근 N일, 기본값: 30일)

    Returns:
        List[Dict[str, str]]: 검색된 블로그 게시글 목록
            - "title" (str): 게시글 제목
            - "link" (str): 게시글 URL
            - "description" (str): 게시글 요약
            - "blogger_name" (str): 블로거 이름
            - "post_date" (str): 게시일 (YYYYMMDD)
    """

    posts = []
    cutoff_date = datetime.now() - timedelta(days=days)

    try:
        display = min(max_result, 100)  # 네이버 API 최대 제한: 100
        url = f"{os.getenv("NAVER_API_URL")}?query={keyword}&display={display}"
        headers = {
            "X-Naver-Client-Id": os.getenv("NAVER_CLIENT_ID"),
            "X-Naver-Client-Secret": os.getenv("NAVER_CLIENT_SECRET")
        }

        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            raise Exception(f"네이버 API 호출 실패: {response.status_code}, {response.text}")

        data = response.json()
        for item in data.get("items", [])[:max_result]:
            post_date = datetime.strptime(item["postdate"], "%Y%m%d")

            if post_date >= cutoff_date:
                posts.append({
                    "title": clean_html(item["title"]),
                    "link": item["link"],
                    "description": clean_html(item["description"]),
                    "blogger_name": item["bloggername"],
                    "post_date": item["postdate"]
                })

        # 최신순 정렬 후 max_result만큼 제한
        posts = sorted(posts, key=lambda x: x["post_date"], reverse=True)[:max_result]

    except Exception as e:
        raise RuntimeError(f"네이버 블로그 검색 중 오류 발생: {str(e)}")

    return posts


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

@tool
async def reddit_tool(keyword: str, max_results: int = 10) -> list:
    """
    커뮤니티 트렌드 - Reddit 인기 게시글 검색 도구.

    Reddit에서 입력된 키워드(keyword)와 관련된 인기 게시글을 검색합니다.

    Args:
        keyword (str): 검색할 키워드
        max_results (int, optional): 최대 검색 결과 수 (기본값: 10)

    Returns:
        List[Dict[str, Union[str, int]]]: 검색된 Reddit 게시글 목록
            - "title" (str): 게시글 제목
            - "url" (str): 게시글 URL
            - "score" (int): 게시글 추천 점수 (upvotes)
            - "created_utc" (str): 게시글 생성일 (UTC 기준)
    """
    # Reddit Access Token 발급
    access_token = get_reddit_access_token()

    headers = {
        "Authorization": f"bearer {access_token}",
        "User-Agent": "web:com.dbfis.chatbot:v1.0.0"
    }

    # Reddit 검색 API 요청
    url = f"https://oauth.reddit.com/search?q={keyword}&limit={max_results}&sort=hot"
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        raise Exception(f"Reddit 검색 요청 실패: {response.json()}")

    data = response.json()

    results = [
        {
            "title": item["data"]["title"],
            "url": f"https://www.reddit.com{item['data']['permalink']}",
            "score": item["data"]["score"],
            "created_utc": datetime.utcfromtimestamp(item["data"]["created_utc"]).strftime('%Y-%m-%d %H:%M:%S')
        }
        for item in data.get("data", {}).get("children", [])
    ]

    # 최신순 정렬
    results = sorted(results, key=lambda x: x["created_utc"], reverse=True)

    return results


@tool
async def search_web_tool(keyword: str, max_results: int=10) -> List[Dict[str, str]]:
    """
    실시간 웹 검색 도구.

    Tavily Search API를 이용하여 실시간 웹 검색을 수행합니다.

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
async def request_url_tool(input_url: str) -> str:
    """
    웹페이지 또는 PDF 문서에서 텍스트를 추출하는 도구.

    주어진 URL에서 HTML 본문 또는 PDF 텍스트를 가져옵니다.

    Args:
        input_url (str): 요청할 웹 페이지 또는 PDF 파일의 URL

    Returns:
        str: 추출된 텍스트
    """
    try:
        response = requests.get(input_url, verify=False, timeout=10)
        response.raise_for_status()  # HTTP 오류 발생 시 예외 처리

        if input_url.lower().endswith(".pdf"):
            text = ""
            with io.BytesIO(response.content) as f:
                pdf = PdfReader(f)
                for page in pdf.pages:
                    text += page.extract_text() + '\n' if page.extract_text() else ''
        else:
            soup = BeautifulSoup(response.text, "html.parser")
            text = soup.body.get_text(separator=' ', strip=True) if soup.body else "No content found"

        # 불필요한 공백 및 줄바꿈 정리
        text = re.sub(r"\s+", " ", text).strip()

        return text

    except requests.RequestException as e:
        return f"Request failed: {e}"
    except Exception as e:
        return f"Error processing the URL: {e}"

@tool
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
async def wikipedia_tool(query: str) -> str:
    """
    Wikipedia 검색 도구.

    Wikipedia에서 입력된 키워드(query)와 관련된 문서를 검색하고 요약을 제공합니다.

    Args:
        query (str): 검색할 키워드

    Returns:
        str: 검색된 Wikipedia 문서 요약 (최대 3개)
    """
    wikipedia = WikipediaQueryRun(api_wrapper=WikipediaAPIWrapper())

    try:
        result = wikipedia.run(query)  # Wikipedia 검색 실행
        summaries = result.split("\n")[:3]  # 최대 3개 요약 추출
        return "\n\n".join(summaries) if summaries else "검색된 결과가 없습니다."
    except Exception as e:
        return f"Wikipedia 검색 중 오류 발생: {str(e)}"


@tool
async def google_trending_tool(query: str, startDate: str = None, endDate: str = None) -> Dict[
    str, Union[str, List[float], List[str]]]:
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
        # pytrends API 연결
        pytrends = TrendReq(hl="ko", tz=540)

        # `timeframe` 설정: 만약 `startDate`와 `endDate`가 주어지면, 그 값을 사용
        if startDate and endDate:
            timeframe = f"{startDate} {endDate}"  # 특정 날짜 범위
        else:
            timeframe = "today 1-m"  # 기본값: 최근 1개월

        # 최대 3번 재시도
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # 검색 키워드, timeframe을 지정 설정
                pytrends.build_payload([query], cat=0, timeframe=timeframe, geo="KR", gprop="")

                # 관심도 데이터 가져오기
                trend_data = pytrends.interest_over_time()

                # 데이터 확인
                if trend_data is None or trend_data.empty:
                    return {"error": f"No trending data found for '{query}'."}

                # 관심도 데이터, 날짜를 리스트에 담기
                interest_data = trend_data[query].dropna().tolist()  # 관심도 데이터 리스트로 변환
                dates = trend_data.index.strftime('%Y-%m-%d').tolist()  # 날짜를 리스트로 변환

                return {
                    "query": query,
                    "interest_data": interest_data,
                    "dates": dates
                }

            except Exception as e:
                # 429 에러 발생 시, 10초 대기 후 재시도
                if '429' in str(e):
                    if attempt < max_retries - 1:
                        print(f"Rate limit exceeded. Retrying in 10 seconds... (Attempt {attempt + 1}/{max_retries})")
                        time.sleep(10)
                    else:
                        return {"error": "Maximum retries reached. Please try again later."}
                else:
                    return {"error": f"Error retrieving Google Trends data: {str(e)}"}

    except Exception as e:
        return {"error": f"Error retrieving Google Trends data: {str(e)}"}


@tool
async def generate_trend_report_tool(search_date: str = None) -> str:
    """
    트렌드 레포트 생성 도구.
    DB에 저장된 날짜별 네이버 뉴스 상위 키워드를 기반으로 Milvus에서 관련 뉴스를 검색하고,
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
        vector_store = get_vector_store()
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
async def get_daily_news_trend_tool(date: str) -> str:
    """
    일간 트렌드 정보를 가져오는 도구.

    특정 날짜의 뉴스 기사 상위 키워드와 각 키워드의 연관 키워드, 뉴스 기사 데이터를 가져옵니다.

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
async def keyword_news_search_tool(keyword: str, relatedKeyword: str, date: str, page: int = 0) -> str:
    """
    키워드와 연관 키워드가 포함된 네이버 뉴스 기사를 elastic search에서 검색하는 도구입니다.

    ⚠️ 주의:
        - 본 도구는 "오늘 날짜(오늘 00시 이후)" 기준 데이터는 사용할 수 없습니다.
        - 뉴스 크롤링은 매일 자정(00:00) 기준으로 하루 단위 수집되므로,
          가장 최근 사용 가능한 날짜는 "어제 날짜"입니다.

    Args:
        keyword (str): 주 검색 키워드 (예: "AI")
        relatedKeyword (str): 연관 검색 키워드 (예: "삼성")
        date (str): 검색 기준 날짜 (YYYY-MM-DD)
        page (int, optional): 페이지 번호 (기본값: 0)

    Returns:
        str: 연관 기사 검색 결과 JSON 문자열 (오류 발생 시 오류 메시지 포함)
    """

    cache_key = f"news:{keyword}:{relatedKeyword}:{date}:{page}"
    r = get_redis_client()
    # redis 캐시 조회
    cached = r.get(cache_key)
    if cached:
        return cached

    try:
        url = (f"http://localhost:8080/api/insight/related-search?"
               f"keyword={keyword}&relatedKeyword={relatedKeyword}&date={date}&page={page}")
        response = requests.get(url)
        response.raise_for_status()
        # redis 캐시 저장
        r.set(cache_key, response.text)
        return response.text
    except Exception as e:
        return f"연관 기사 검색 실패: {e}"

tools = [
    rag_news_search_tool,
    daum_blog_tool,
    naver_blog_tool,
    reddit_tool,
    search_web_tool,
    youtube_video_tool,
    request_url_tool,
    translation_tool,
    wikipedia_tool,
    google_trending_tool,
    generate_trend_report_tool,
    get_daily_news_trend_tool,
    keyword_news_search_tool
]