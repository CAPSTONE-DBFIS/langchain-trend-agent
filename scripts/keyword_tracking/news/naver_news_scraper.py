import os
import requests
from dotenv import load_dotenv
from typing import List, Dict, Any
from datetime import datetime, timedelta
import pytz
import json
import re
import openai
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
from models import SessionLocal, TrackingKeyword, TrackingResult

# .env 파일 로드
load_dotenv()

# OpenAI API 키 가져오기
openai.api_key = os.getenv('OPENAI_API_KEY')

# 네이버 API 키 가져오기
client_id = os.getenv('NAVER_CLIENT_ID')
client_secret = os.getenv('NAVER_CLIENT_SECRET')


def clean_html(text: str) -> str:
    """HTML 태그를 제거하고 텍스트만 반환"""
    return BeautifulSoup(text, "html.parser").get_text()


# 전역변수 선언
total_articles = 0

def naver_search(query: str, target_date: str) -> tuple[list[dict[str, str | int | Any]], int]:
    url = "https://openapi.naver.com/v1/search/news.json"

    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret
    }

    results = []
    display = 100
    start = 1

    seen_links = set()

    while True:
        params = {
            "query": query,
            "display": display,
            "start": start,
            "sort": "sim"
        }

        response = requests.get(url, headers=headers, params=params)

        if response.status_code == 200:
            data = response.json()
            items = data.get('items', [])

            if not items:
                break

            for item in items:
                pubDate = item['pubDate']
                pubDate_dt = datetime.strptime(pubDate, '%a, %d %b %Y %H:%M:%S +0900')

                if pubDate_dt.strftime('%Y-%m-%d') == target_date:
                    clean_title = clean_html(item['title'])  # HTML 태그 제거
                    link = item['link']

                    if link not in seen_links:
                        seen_links.add(link)
                        comment_count = get_naver_comment_count(link) # 댓글 갯수 가져오기

                        results.append({
                            "title": clean_title,
                            "link": link,
                            "comment_count": comment_count
                        })

            start += display
            if start > 1000:
                break

        else:
            break

    # 전체 검색된 결과 수 (3개 이상은 상위 3개만 선택)
    total_results_count = len(results)

    # 댓글 갯수 상위 3개 기사만 반환
    results = sorted(results, key=lambda x: x['comment_count'], reverse=True)[:3]

    return results, total_results_count  # 댓글 갯수 상위 3개 기사와 전체 검색 결과 개수 반환


def get_naver_comment_count(article_url: str) -> int:
    oid_aid_match = re.search(r"article/(\d+)/(\d+)", article_url)

    if not oid_aid_match:
        return 0

    oid, aid = oid_aid_match.groups()
    comment_api_url = f"https://apis.naver.com/commentBox/cbox/web_neo_list_jsonp.json?ticket=news&templateId=view_politics&pool=cbox5&lang=ko&country=KR&objectId=news{oid},{aid}&pageSize=1&indexSize=10&listType=OBJECT&sort=best"

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": article_url,
    }

    response = requests.get(comment_api_url, headers=headers)

    if response.status_code != 200:
        return 0

    try:
        json_text = response.text.strip().lstrip('_callback(').rstrip(');')
        data = json.loads(json_text)
        comment_count = data['result']['count']['total']
        return comment_count

    except:
        return 0


def get_comments(article_url: str) -> List[str]:
    oid_aid_match = re.search(r"article/(\d+)/(\d+)", article_url)

    if not oid_aid_match:
        return []

    oid, aid = oid_aid_match.groups()
    comment_api_url = f"https://apis.naver.com/commentBox/cbox/web_neo_list_jsonp.json?ticket=news&templateId=view_politics&pool=cbox5&lang=ko&country=KR&objectId=news{oid},{aid}&pageSize=100&indexSize=10&listType=OBJECT&sort=best"

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": article_url,
    }

    response = requests.get(comment_api_url, headers=headers)

    if response.status_code != 200:
        return []

    try:
        json_text = response.text.strip().lstrip('_callback(').rstrip(');')
        data = json.loads(json_text)

        comments = [clean_html(comment['contents']) for comment in data['result']['commentList']]  # HTML 태그 제거

        return comments

    except:
        return []


def gpt_analyze_sentiment(comments: List[str], article_title: str) -> Dict[str, int]:
    result = {"Positive": 0, "Negative": 0, "Neutral": 0}
    description = ""  # GPT가 생성한 요약 설명

    if not comments:  # 댓글이 없으면 GPT 호출하지 않음
        return result, description

    batch_size = 100  # 한 번에 보내는 댓글 수
    all_analysis = []

    for i in range(0, len(comments), batch_size):
        batch_comments = comments[i:i + batch_size]

        # GPT 모델에 전달할 prompt 작성 (기사 제목 추가)
        prompt = (
            f"다음은 '[{article_title}]'에 대한 댓글들입니다. "
            "이 댓글들을 긍정, 부정, 중립으로 분류해 주세요. "
            "또한 전체 댓글을 분석하여 간단한 요약 설명을 작성하되, "
            "긍정적인 반응과 부정적인 반응을 모두 예시와 함께 포함하여 설명하세요.\n\n"
            "응답은 반드시 JSON 형식으로 정확히 반환해야 합니다. 형식을 반드시 지켜주세요.\n\n"
            "응답 예시:\n"
            "{\n"
            "  \"comments\": [\n"
            "    {\"comment\": \"이 제품 정말 좋네요.\", \"sentiment\": \"positive\"},\n"
            "    {\"comment\": \"별로예요.\", \"sentiment\": \"negative\"}\n"
            "  ],\n"
            "  \"description\": \"이 기사에 대한 대부분의 댓글은 긍정적인 반응을 보이고 있습니다. 예를 들어, '정말 유용합니다.'와 같은 반응이 있습니다. 하지만 일부는 부정적인 의견도 존재하며, 예를 들어 '별로예요.'와 같은 반응도 보였습니다.\"\n"
            "}\n\n"
            "다음은 분석할 댓글 목록입니다:\n"
        )

        for comment in batch_comments:
            prompt += f"- {comment}\n"

        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that analyzes comments and returns results in JSON format with detailed description."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0,
        )

        response_text = response.choices[0].message['content'].strip()

        # 코드 블록 제거 및 JSON 포맷으로 변환
        if response_text.startswith("```json"):
            response_text = response_text[7:].strip()
        if response_text.endswith("```"):
            response_text = response_text[:-3].strip()

        try:
            # 응답 파싱
            parsed_response = json.loads(response_text)
            if isinstance(parsed_response, dict):
                comment_analysis = parsed_response.get("comments", [])
                description = parsed_response.get("description", "")

                for entry in comment_analysis:
                    sentiment = entry.get('sentiment', '').lower()
                    if sentiment == "positive":
                        result["Positive"] += 1
                    elif sentiment == "negative":
                        result["Negative"] += 1
                    elif sentiment == "neutral":
                        result["Neutral"] += 1

                all_analysis.extend(comment_analysis)

        except json.JSONDecodeError:
            print("GPT 응답 파싱 오류: JSON 형식으로 반환되지 않았습니다.")
            print("응답 내용:", response_text)

    return result, description


def save_to_db(db_session: Session):
    # 수집 날짜
    kst = pytz.timezone('Asia/Seoul')
    target_date = (datetime.now(kst) - timedelta(days=1)).strftime('%Y-%m-%d')

    # 현재 시각에 해당하는 키워드 조회 (start_date와 end_date 사이에 있는)
    current_time = datetime.now()
    keywords = db_session.query(TrackingKeyword).filter(
        TrackingKeyword.start_date <= current_time,
        TrackingKeyword.end_date >= current_time
    ).all()

    for tracking_keyword in keywords:
        print(f"\nTracking Keyword: {tracking_keyword.keyword}")

        top_articles, total_results_count = naver_search(tracking_keyword.keyword, target_date)  # 전체 검색된 결과 개수 포함

        sentiment_results = []
        overall_description = ""  # 전체 기사에 대한 누적 설명 (전체 설명)

        for article in top_articles:
            print(f"\n기사 제목: {article['title']}")
            print(f"댓글 갯수: {article['comment_count']}")

            comments = get_comments(article['link'])
            sentiment_result, description = gpt_analyze_sentiment(comments, article['title'])

            sentiment_results.append({
                "title": article['title'],
                "link": article['link'],
                "comment_count": article['comment_count'],
                "positive_count": sentiment_result["Positive"],
                "negative_count": sentiment_result["Negative"],
                "neutral_count": sentiment_result["Neutral"],
                "description": description
            })

            if description:
                overall_description += f"[{article['title']}]에 대한 댓글 긍부정 분석 결과:\n{description}\n\n"
            else:
                overall_description += f"[{article['title']}]에 대한 댓글 분석 결과:\n댓글이 존재하지 않습니다.\n\n"

        # DB에 저장 (전체 기사에 대한 설명을 TrackingResult에 저장)
        tracking_result = TrackingResult(
            tracking_keyword_id=tracking_keyword.id,
            collected_date=target_date,
            article_count=total_results_count if total_results_count is not None else 0,
            article_title_1=sentiment_results[0]["title"] if len(sentiment_results) > 0 else "",
            article_link_1=sentiment_results[0]["link"] if len(sentiment_results) > 0 else "",
            comment_count_1=sentiment_results[0]["comment_count"] if len(sentiment_results) > 0 else 0,
            positive_count_1=sentiment_results[0]["positive_count"] if len(sentiment_results) > 0 else 0,
            negative_count_1=sentiment_results[0]["negative_count"] if len(sentiment_results) > 0 else 0,
            neutral_count_1=sentiment_results[0]["neutral_count"] if len(sentiment_results) > 0 else 0,
            article_title_2=sentiment_results[1]["title"] if len(sentiment_results) > 1 else "",
            article_link_2=sentiment_results[1]["link"] if len(sentiment_results) > 1 else "",
            comment_count_2=sentiment_results[1]["comment_count"] if len(sentiment_results) > 1 else 0,
            positive_count_2=sentiment_results[1]["positive_count"] if len(sentiment_results) > 1 else 0,
            negative_count_2=sentiment_results[1]["negative_count"] if len(sentiment_results) > 1 else 0,
            neutral_count_2=sentiment_results[1]["neutral_count"] if len(sentiment_results) > 1 else 0,
            article_title_3=sentiment_results[2]["title"] if len(sentiment_results) > 2 else "",
            article_link_3=sentiment_results[2]["link"] if len(sentiment_results) > 2 else "",
            comment_count_3=sentiment_results[2]["comment_count"] if len(sentiment_results) > 2 else 0,
            positive_count_3=sentiment_results[2]["positive_count"] if len(sentiment_results) > 2 else 0,
            negative_count_3=sentiment_results[2]["negative_count"] if len(sentiment_results) > 2 else 0,
            neutral_count_3=sentiment_results[2]["neutral_count"] if len(sentiment_results) > 2 else 0,
            overall_description=overall_description if overall_description else ""
        )

        db_session.add(tracking_result)
        db_session.commit()


if __name__ == "__main__":
    # DB 세션 생성
    db_session = SessionLocal()

    # DB에서 키워드 조회 및 작업 수행
    save_to_db(db_session)