import os
import logging
from typing import List, Dict, Any
from elasticsearch import Elasticsearch
import asyncio

logger = logging.getLogger(__name__)

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