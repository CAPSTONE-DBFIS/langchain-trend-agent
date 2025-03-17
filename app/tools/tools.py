import os
from dotenv import load_dotenv
import time
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_milvus import Milvus
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
from langchain_community.tools import WikipediaQueryRun
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_community.utilities import WikipediaAPIWrapper
from langchain.tools import tool
from pytrends.request import TrendReq
from typing import Dict, Union, List
from app.utils.milvus import get_embedding_model, get_vector_store

load_dotenv()

@tool
def articles_tool(query: str) -> List[Dict[str, Union[str, float]]]:
    """
    Milvus에서 RAG를 이용한 뉴스 기사 검색 도구.

    Milvus에 저장된 뉴스 기사 데이터에서 입력된 키워드(query)와 가장 유사한 기사를 검색합니다.
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
        query_embedding, k=3, filter={"timestamp": {"$gte": recent_timestamp}}
    )

    # 최신 문서가 부족하면 전체 검색 추가
    if len(latest_results) < 3:
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
def daum_blog_tool(keyword, max_results=10):
    """
    Daum 블로그 검색 도구.

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
def naver_blog_tool(keyword: str, max_result: int = 10, days: int = 30) -> List[Dict[str, str]]:
    """
    네이버 블로그 검색 도구.

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
def reddit_tool(keyword: str, max_results: int = 10) -> list:
    """
    Reddit 인기 게시글 검색 도구.

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
def search_web_tool(keyword: str, max_results: int=10) -> List[Dict[str, str]]:
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
def youtube_video_tool(query: str, max_results: int = 5):
    """
    YouTube 동영상 검색 도구.

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
def request_url_tool(input_url: str) -> str:
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
def translation_tool(asking: str) -> str:
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
        runnable = prompt | ChatOpenAI(temperature=0, model="gpt-4")
        thinking = runnable.invoke({"asking": asking})

        return f"Thinking : {thinking}"
    except Exception as e:
        return f"Error: {e}"

@tool
def wikipedia_tool(query: str) -> str:
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
def google_trending_tool(query: str, startDate: str = None, endDate: str = None) -> Dict[
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