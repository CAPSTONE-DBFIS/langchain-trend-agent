import os
from dotenv import load_dotenv
import redis

load_dotenv()

def get_redis_client():
    # Redis 연결
    r = redis.Redis(
        host=os.getenv("REDIS_HOST"),
        port=os.getenv("REDIS_PORT"),
        password=os.getenv("REDIS_PASSWORD"),
        decode_responses=True
    )