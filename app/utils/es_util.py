import os
import logging
from typing import List, Dict, Any
from elasticsearch import Elasticsearch
import asyncio
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv()

def get_es_client() -> Elasticsearch | None:
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
    es = get_es_client()
    if es is None:
        logger.warning("Elasticsearch 클라이언트가 초기화되지 않음")
        return []

    def sync_search():
        query = {
            "query": {
                "bool": {
                    "must": [
                        {
                            "multi_match": {
                                "query": keyword,
                                "fields": ["title^2", "content"],
                            }
                        },
                        {
                            "range": {
                                "date": {
                                    "gte": date_start,
                                    "lte": date_end
                                }
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
                        "number_of_fragments": 1,
                        "no_match_size": 500
                    }
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
                    "content": hit.get("highlight", {}).get("content", [hit["_source"].get("content", "")[:500]])[0]
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
    size: int = 5
) -> List[Dict[str, Any]]:
    es = get_es_client()
    if es is None:
        logger.warning("Elasticsearch 클라이언트가 초기화되지 않음")
        return []

    def sync_search():
        query = {
            "query": {
                "bool": {
                    "must": [
                        {
                            "multi_match": {
                                "query": keyword,
                                "fields": ["title^2", "content"],
                            }
                        },
                        {
                            "range": {
                                "date": {
                                    "gte": date_start,
                                    "lte": date_end
                                }
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
                        "number_of_fragments": 1,
                        "no_match_size": 500
                    }
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
                    "content": hit.get("highlight", {}).get("content", [hit["_source"].get("content", "")[:500]])[0]
                }
                for hit in res["hits"]["hits"]
            ]
        except Exception as e:
            logger.error(f"Elasticsearch 검색 실패: {str(e)}")
            return []

    return await asyncio.to_thread(sync_search)


async def fetch_sentiment_distribution(
    keyword: str,
    date_start: str,
    date_end: str,
    index: str = "news_article"
) -> dict:
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
                    {
                        "match": {
                            "title": {
                                "query": keyword,
                            }
                        }
                    },
                    {
                        "range": {
                            "date": {
                                "gte": date_start,
                                "lte": date_end
                            }
                        }
                    }
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