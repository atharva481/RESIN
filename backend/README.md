# RESIN Backend: FastAPI RAG & Autonomous Research Agent

The core computation and retrieval backend for **RESIN**, built with Python 3.11+, FastAPI, and Supabase (`pgvector`). It orchestrates multi-source open-access PDF resolution, section-aware document chunking, high-throughput Gemini batch embeddings, and real-time Server-Sent Events (SSE) streaming for grounded paper Q&A and autonomous research synthesis.

---

## 🚀 Key Responsibilities & Capabilities

1. **Section-Aware & Page-Aware RAG Engine**:
   - Chunks academic PDFs into ~600-word windows with 100-word sliding overlap, tagging exact physical page numbers and section headers.
   - Vectorizes chunks using Google Gemini's 768-dimensional embedding model (`models/gemini-embedding-001`).
   - High-throughput single-call batch vectorization (`batch_size = 100`) embedding 50+ chunks in ~2.1 seconds.
   - Computes cosine similarity via `match_paper_chunks` stored procedure in PostgreSQL `pgvector`.
   - Streams grounded answers in real-time via Server-Sent Events (`gemini-3.5-flash-lite`, TTFT ~1.1s).
   - Compacts chat conversation history to prevent rate-limit 429 delays and token bloat.

2. **Resilient Ingestion & Multi-Source PDF Discovery**:
   - Deterministic UUIDv5 canonical paper resolution (`paper_resolution.py`) preventing PostgreSQL `23505` and `23503` key conflicts.
   - Ranked Candidate Queue (Priorities 50–120): arXiv direct PDF (Priority 120), PMC/Europe PMC structured XML (Priority 100), Semantic Scholar OA (Priority 95), OpenAlex primary/secondary locations (Priorities 90/85), and Unpaywall (Priority 80).
   - Second-stage HTML PDF Discovery Engine ("Follow the PDF Button") resolving links from publisher landing pages.
   - Structured diagnostic taxonomy (`PAYWALL_DETECTED`, `LOGIN_REQUIRED`, `BOT_PROTECTION`, `HTTP_ERROR`).
   - Manual user PDF upload endpoint (`POST /api/papers/{id}/upload-pdf`) to index paywalled papers directly.

3. **Autonomous Multi-Paper Research Agent**:
   - ReAct reasoning loop (up to 15 iterations) with tool-calling:
     - `search_semantic_scholar`: Live academic search across global literature.
     - `search_user_library`: Semantic search across holistic paper embeddings in the user's library.
     - `search_paper_chunks`: Deep vector search into specific indexed papers.
     - `summarize_paper`: Retrieves structured problem/method/findings summaries.
   - Full reasoning traces streamed directly to the client via SSE.

---

## 📡 API Endpoints Overview

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/chat/stream` | Real-time SSE streaming RAG answer with page citations |
| `POST` | `/api/papers/{id}/index` | Discovers open-access PDF, parses pages, and indexes vectors |
| `POST` | `/api/papers/{id}/upload-pdf` | Indexes user-uploaded PDF file for any paper |
| `POST` | `/api/agent/stream` | Autonomous multi-paper research agent stream (ReAct loop) |
| `GET` | `/api/papers/search` | Unified search proxy across Semantic Scholar and OpenAlex |
| `GET` | `/health` | Service health status and cache check |

---

## ⚙️ Setup & Local Execution

### 1. Prerequisites
- Python 3.11+
- Virtual environment (`venv`)

### 2. Installation
```bash
# Create and activate virtual environment
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Environment Configuration
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Fill in the following variables:
```bash
VITE_SUPABASE_URL="https://your-project.supabase.co"
VITE_SUPABASE_ANON_KEY="your-anon-key"
VITE_SUPABASE_SERVICE_KEY="your-service-role-key"  # Needed for pgvector upserts
VITE_GEMINI_API_KEY="your-gemini-api-key"
VITE_GEMINI_EMBEDDING_MODEL="models/gemini-embedding-001"
VITE_GEMINI_CHAT_MODEL="models/gemini-3.5-flash-lite"
```

### 4. Run Development Server
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
Interactive Swagger API documentation will be available at `http://localhost:8000/docs`.
