import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import chat, embed, health, search
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("resin-backend")

app = FastAPI(
    title="RESIN RAG API Engine",
    description="FastAPI Backend for Paper Chunking, Embedding, pgvector Search, and Gemini RAG Q&A",
    version="1.0.0",
)

# Configure CORS for frontend access
origins = [
    "http://localhost:5173",
    "http://localhost:8081",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:8081",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, tags=["Health"])
app.include_router(chat.router, prefix="/api", tags=["RAG Chat"])
app.include_router(embed.router, prefix="/api", tags=["Paper Indexing"])
app.include_router(search.router, prefix="/api/papers", tags=["Paper Search Proxy"])


@app.get("/")
def root():
    return {"message": "Welcome to RESIN RAG Engine API. Access /docs for API schema."}
