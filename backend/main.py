import logging
import warnings
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Silence upstream SDK deprecation banner on startup
warnings.filterwarnings("ignore", category=FutureWarning, message=r"(?s).*google\.generativeai.*")

from app.api import chat, embed, health, search, citations, summarize, news
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.core.config import settings
from app.core.limiter import limiter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("resin-backend")

is_production = settings.environment.lower() == "production"

app = FastAPI(
    title="RESIN RAG API Engine",
    description="FastAPI Backend for Paper Chunking, Embedding, pgvector Search, and Gemini RAG Q&A",
    version="1.0.0",
    docs_url="/docs" if settings.enable_docs and not is_production else None,
    redoc_url="/redoc" if settings.enable_docs and not is_production else None,
    openapi_url="/openapi.json" if settings.enable_docs and not is_production else None,
)

# Attach rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Configure CORS for frontend access
cors_kwargs = {
    "allow_origins": settings.cors_origins,
    "allow_credentials": True,
    "allow_methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    "allow_headers": ["Authorization", "Content-Type", "Accept", "Origin", "User-Agent", "X-Requested-With"],
}
if not is_production:
    cors_kwargs["allow_origin_regex"] = r"https?://(localhost|127\.0\.0\.1)(:\d+)?"

app.add_middleware(CORSMiddleware, **cors_kwargs)


@app.middleware("http")
async def limit_request_body_size(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > settings.max_request_body_size:
                return JSONResponse(
                    status_code=413,
                    content={"detail": "Request entity too large."}
                )
        except ValueError:
            pass
    return await call_next(request)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none'; object-src 'none';"
    return response

# Include routers
app.include_router(health.router, tags=["Health"])
app.include_router(chat.router, prefix="/api", tags=["RAG Chat"])
app.include_router(embed.router, prefix="/api", tags=["Paper Indexing"])
app.include_router(citations.router, prefix="/api/citations", tags=["Citations Graph"])
app.include_router(search.router, prefix="/api/papers", tags=["Paper Search Proxy"])
app.include_router(summarize.router, prefix="/api", tags=["Summaries"])
app.include_router(news.router, prefix="/api", tags=["News"])


@app.get("/")
def root():
    return {"message": "Welcome to RESIN RAG Engine API. Access /docs for API schema."}
