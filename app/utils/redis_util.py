import os
from dotenv import load_dotenv
import redis

load_dotenv()

def get_redis_client():
    """Redis 클라이언트 연결하는 함수"""
    required_vars = ["REDIS_HOST", "REDIS_PORT", "REDIS_PASSWORD"]
    for var in required_vars:
        if not os.getenv(var):
            raise ValueError(f"환경 변수 {var}가 설정되지 않았습니다.")

    try:
        client = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", 6379)),
            password=os.getenv("REDIS_PASSWORD", None),
            decode_responses=True
        )
        client.ping()
        return client
    except redis.AuthenticationError as e:
        raise ValueError(f"Redis 인증 실패: REDIS_PASSWORD를 확인하세요. {str(e)}")
    except redis.ConnectionError as e:
        raise ValueError(f"Redis 연결 실패: REDIS_HOST 및 REDIS_PORT를 확인하세요. {str(e)}")
    except Exception as e:
        raise ValueError(f"Redis 연결 중 오류: {str(e)}")

def clear_all_cache_db():
    """현재 선택된 Redis 데이터베이스의 모든 키를 삭제하는 함수"""
    r = get_redis_client()
    r.flushdb()
    print("현재 Redis DB의 모든 키를 삭제했습니다.")

# clear_all_cache_db()
