from fastapi import APIRouter
import httpx
from app.services.redis_cache import RedisCacheService

router = APIRouter()
redis_service = RedisCacheService()


@router.get("/health")
async def health_check():
    ss_status = "unknown"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.semanticscholar.org/graph/v1/paper/search?query=test&limit=1",
                timeout=5.0,
            )
            if resp.status_code == 200:
                ss_status = "connected"
            elif resp.status_code == 429:
                ss_status = "rate_limited"
            else:
                ss_status = f"error_{resp.status_code}"
    except Exception:
        ss_status = "unreachable"

    return {
        "status": "healthy",
        "service": "RESIN RAG API",
        "redis": "connected" if redis_service.available else "disconnected",
        "semantic_scholar": ss_status,
    }
