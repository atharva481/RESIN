import json
import logging
from typing import Optional
import redis
from app.core.config import settings

logger = logging.getLogger(__name__)


class RedisCacheService:
    """Optional redis query response caching service."""

    def __init__(self, redis_url: str = settings.redis_url):
        try:
            self.client = redis.from_url(redis_url, decode_responses=True)
            self.client.ping()
            self.available = True
        except Exception as e:
            logger.warning(f"Redis cache unavailable at {redis_url}: {e}")
            self.client = None
            self.available = False

    def get_cached_response(self, paper_id: str, query: str) -> Optional[dict]:
        if not self.available or not self.client:
            return None
        try:
            key = f"rag:{paper_id}:{hash(query)}"
            data = self.client.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            logger.error(f"Redis get error: {e}")
        return None

    def set_cached_response(self, paper_id: str, query: str, response: dict, ttl_seconds: int = 3600):
        if not self.available or not self.client:
            return
        try:
            key = f"rag:{paper_id}:{hash(query)}"
            self.client.setex(key, ttl_seconds, json.dumps(response))
        except Exception as e:
            logger.error(f"Redis set error: {e}")
