import os
import logging
from typing import List, Dict, Any
from elasticsearch import Elasticsearch
import asyncio
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

def get_es_client() -> Elasticsearch | None:
    """
    Elasticsearch 클라이언트를 초기화하고 반환합니다.

    Returns:
        Elasticsearch | None: 초기화된 클라이언트 또는 연결 실패 시 None
    """
    try:
        es = Elasticsearch(
            hosts=[f"http://{os.getenv('ELASTICSEARCH_HOST')}:{os.getenv('ELASTICSEARCH_PORT')}"],
            basic_auth=(os.getenv("ELASTICSEARCH_USERNAME"), os.getenv("ELASTICSEARCH_PASSWORD")),
            verify_certs=False
        )
        return es
    except Exception as e:
        logger.error(f"Elasticsearch 클라이언트 초기화 실패: {str(e)}")
        return None


async def fetch_domestic_articles(
        keyword: str,
        date_start: str,
        date_end: str,
        index: str = os.getenv("ELASTICSEARCH_DOMESTIC_INDEX_NAME"),
        size: int = 5
) -> List[Dict[str, Any]]:
    """
    Elasticsearch에서 키워드와 날짜 범위로 기사를 검색합니다.

    Args:
        keyword (str): 검색 키워드
        date_start (str): 검색 시작 날짜 (YYYY-MM-DD)
        date_end (str): 검색 종료 날짜 (YYYY-MM-DD)
        index (str): 검색할 인덱스 이름
        size (int): 반환할 최대 기사 수

    Returns:
        List[Dict[str, Any]]: 검색된 기사 목록
    """
    es = get_es_client()
    if es is None:
        logger.warning("Elasticsearch 클라이언트가 초기화되지 않음")
        return []

    def sync_search():
        query = {
            "query": {
                "bool": {
                    "must": [
                        {"match": {"title": keyword}},
                        {"range": {"date": {"gte": date_start, "lte": date_end}}}
                    ]
                }
            },
            "size": size,
            "sort": [{"date": {"order": "desc"}}]
        }
        try:
            res = es.search(index=index, body=query)
            return [
                {
                    "title": hit["_source"].get("title"),
                    "date": hit["_source"].get("date"),
                    "media_company": hit["_source"].get("media_company"),
                    "url": hit["_source"].get("url"),
                    "content": hit["_source"].get("content", "")[:500] + "..."
                }
                for hit in res["hits"]["hits"]
            ]
        except Exception as e:
            logger.error(f"Elasticsearch 검색 실패: {str(e)}")
            return []

    return await asyncio.to_thread(sync_search)


async def fetch_foreign_articles(
        keyword: str,
        date_start: str,
        date_end: str,
        index: str = os.getenv("ELASTICSEARCH_FOREIGN_INDEX_NAME"),
        size: int = 3
) -> List[Dict[str, Any]]:
    """
    Elasticsearch에서 해외 키워드와 날짜 범위로 기사를 검색합니다.

    Args:
        keyword (str): 검색 키워드
        date_start (str): 검색 시작 날짜 (YYYY-MM-DD)
        date_end (str): 검색 종료 날짜 (YYYY-MM-DD)
        index (str): 검색할 인덱스 이름
        size (int): 반환할 최대 기사 수

    Returns:
        List[Dict[str, Any]]: 검색된 기사 목록
    """
    es = get_es_client()
    if es is None:
        logger.warning("Elasticsearch 클라이언트가 초기화되지 않음")
        return []

    def sync_search():
        query = {
            "query": {
                "bool": {
                    "must": [
                        {"wildcard": {"title.keyword": f"*{keyword}*"}},
                        {"range": {"date": {"gte": date_start, "lte": date_end}}}
                    ]
                }
            },
            "size": size,
            "sort": [{"date": {"order": "desc"}}]
        }
        try:
            res = es.search(index=index, body=query)
            return [
                {
                    "title": hit["_source"].get("title"),
                    "date": hit["_source"].get("date"),
                    "media_company": hit["_source"].get("media_company"),
                    "url": hit["_source"].get("url"),
                    "content": hit["_source"].get("content", "")[:500] + "..."
                }
                for hit in res["hits"]["hits"]
            ]
        except Exception as e:
            logger.error(f"Elasticsearch 검색 실패: {str(e)}")
            return []

    return await asyncio.to_thread(sync_search)

async def fetch_sentiment_distribution(keyword: str, date_start: str, date_end: str, index: str = "news_article") -> dict:
    """
    Elasticsearch 기반 뉴스 감정 분포 분석 함수

    Args:
        keyword (str): 감정 분석 대상 키워드 (뉴스 제목 내 포함 여부 기준)
        date_start (str): 검색 시작 날짜 (YYYY-MM-DD)
        date_end (str): 검색 종료 날짜 (YYYY-MM-DD)
        index (str): 조회 대상 Elasticsearch 인덱스 이름 (기본값: "news_article")

    Returns:
        dict:
            - positive_percent (int): 긍정 비율 (%)
            - negative_percent (int): 부정 비율 (%)
            - neutral_percent (int): 중립 비율 (%)
            - error (str, optional): 오류 발생 시 메시지
            - sentiment_distribution (dict): 오류 발생 시 빈 딕셔너리
            - total (int): 총 감정 분석 문서 수 (오류 발생 시 0)
    """
    es = get_es_client()
    if es is None:
        return {
            "error": "Elasticsearch client is not initialized",
            "sentiment_distribution": {},
            "total": 0
        }

    query = {
        "size": 0,
        "query": {
            "bool": {
                "must": [
                    {"match": {"title": keyword}},
                    {"range": {"date": {"gte": date_start, "lte": date_end}}}
                ]
            }
        },
        "aggs": {
            "sentiment_counts": {
                "terms": {
                    "field": "sentiment",
                    "size": 3
                }
            }
        }
    }

    try:
        res = es.search(index=index, body=query)
        total_hits = res["hits"]["total"]["value"]

        sentiment_counts = {
            bucket["key"]: bucket["doc_count"]
            for bucket in res["aggregations"]["sentiment_counts"]["buckets"]
        }

        def percent(x): return round((x * 100.0) / total_hits) if total_hits > 0 else 0

        return {
            "positive_percent": percent(sentiment_counts.get("positive", 0)),
            "negative_percent": percent(sentiment_counts.get("negative", 0)),
            "neutral_percent": percent(sentiment_counts.get("neutral", 0))
        }

    except Exception as e:
        return {
            "error": f"Sentiment search failed: {str(e)}",
            "sentiment_distribution": {},
            "total": 0
        }