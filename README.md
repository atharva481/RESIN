# RESIN: Research Engine & Synthesized Intelligence Network

<div align="center">

![License](https://img.shields.io/badge/License-MIT-blue.svg)
![React](https://img.shields.io/badge/Frontend-React%2018%20%7C%20Vite%20%7C%20TypeScript-61DAFB?logo=react)
![FastAPI](https://img.shields.io/badge/Backend-FastAPI%20%7C%20Python%203.11+-009688?logo=fastapi)
![Supabase](https://img.shields.io/badge/Database-PostgreSQL%20%7C%20pgvector-3ECF8E?logo=supabase)
![Gemini](https://img.shields.io/badge/AI-Google%20Gemini%20Flash%20%7C%20Embeddings-4285F4?logo=google)
![Tailwind](https://img.shields.io/badge/Styling-Tailwind%20CSS-38B2AC?logo=tailwindcss)

**An end-to-end AI-powered academic research workstation featuring section-aware RAG, autonomous multi-paper research agents, resilient open-access PDF discovery, and automated daily paper triage.**

[Features](#-core-features) • [Architecture](#-architecture--how-it-works) • [Quickstart](#-quickstart) • [Environment Variables](#-environment-variables) • [Database Setup](#-database--pgvector-setup) • [Documentation](#-documentation)

</div>

---

## 📌 Overview

**RESIN** transforms how researchers, machine learning engineers, and students interact with academic literature. Rather than passively reading dense PDFs or skimming abstracts, RESIN indexes full-text scientific papers into high-dimensional vector embeddings, allowing users to:
1. **Chat grounded directly against paper pages** with exact clickable citations and zero hallucinations.
2. **Execute autonomous cross-paper synthesis** using a ReAct research agent.
3. **Discover legal open-access PDFs automatically** across publisher paywalls and institutional landing pages.
4. **Receive personalized daily research briefings** tailored to individual topic interests.

---

## 🚀 Core Features

### 1. Robust Multi-Source PDF Discovery & Diagnostics
- **Ranked Candidate Queue (Priorities 50–120):** Waterfall resolution prioritizing instant open-access arXiv IDs (Priority 120), Europe PMC / NCBI structured XML (Priority 100), Semantic Scholar OA (Priority 95), OpenAlex primary & secondary locations (`locations[].pdf_url`), Unpaywall, and publisher mirrors.
- **Second-Stage HTML PDF Discovery Engine ("Follow the PDF Button"):** If a candidate URL returns an HTML landing page, the parser extracts, resolves, and scores candidate PDF links (evaluating `<meta name="citation_pdf_url">`, PDF download buttons, anchors matching `download-pdf`, etc.) and downloads the genuine document.
- **PubMed Central (PMC) Full-Text Structured XML Extraction:** When journal portals block direct PDF bots, RESIN fetches Europe PMC / NCBI E-utilities XML, parses `<abstract>`, groups direct `<body>` paragraphs into `Introduction & Results`, and segments all `<sec>` headings into 15–30 granular sections.
- **Paywall & Bot-Protection Diagnostic Classification:** Accurately differentiates `PAYWALL_DETECTED`, `LOGIN_REQUIRED`, `BOT_PROTECTION` (Cloudflare / CloudPMC challenges), `HTTP_ERROR`, and `PARSE_ERROR`.
- **Embedding Suppression & User PDF Upload:** Prevents false 1-chunk abstract embedding on paywalled papers. Allows users to directly upload their personal PDF via `POST /api/papers/{id}/upload-pdf` to index full-text instantly.

### 2. High-Performance Section-Aware RAG
- **Single-Call Batch Vectorization:** Chunks are vectorized in a single unified Gemini API call (`batch_size = 100`), reducing paper embedding latency from 20+ seconds down to **~2.1 seconds** for entire manuscripts.
- **Granular Page Chunking:** Sliding window chunking (~600 words, 100-word overlap) preserving physical PDF page numbers and section headers.
- **pgvector Cosine Search:** Fast vector similarity search via `vector(768)` IVFFlat indexes in PostgreSQL.
- **Sub-2-Second SSE Streaming:** Real-time Server-Sent Events streaming via `gemini-3.5-flash-lite`, delivering grounded answers with interactive page citation pills and an average Time-to-First-Token (TTFT) of ~1.1 seconds.
- **Context Density Optimization:** Automated context compaction preserving recent conversational history without hitting Gemini token or rate-limit thresholds.
- **Holistic Paper Embeddings:** Generates paper-level semantic embeddings for whole-library semantic search.

### 3. Resilient AI Summaries with Demand Failover
- **503 High-Demand Spike Auto-Retry:** Gracefully handles upstream Gemini capacity spikes with automatic jittered retry and seamless candidate model failover (`gemini-3.5-flash-lite` → `gemini-3.1-flash-lite` → `gemini-flash-lite-latest` → `gemini-flash-latest`).
- **5-Point Structured Digest:** Extracts Problem, Method, Findings, Limitations, and Significance in seconds.

### 4. Autonomous Multi-Paper Research Agent
- ReAct reasoning loop (up to 15 iterations) equipped with tool-calling capabilities:
  - `search_semantic_scholar`: Live academic search across global literature.
  - `search_user_library`: Semantic search across saved papers in the user's library.
  - `search_paper_chunks`: Deep vector search into specific indexed papers.
  - `summarize_paper`: Retrieves structured problem/method/findings summaries.
- Real-time step-by-step reasoning streamed directly to the frontend.

### 5. Canonical Paper Resolution & De-duplication
- **Deterministic UUIDv5 Generation:** Resolves papers by DOI, Semantic Scholar ID, or title hash, completely eliminating Postgres `23505` duplicate key and `23503` foreign key violations during indexing.
- Seamless library folder management and reference exports (BibTeX, APA, MLA).

### 6. Automated Daily Paper Triage
- Background worker (`resin-triage`) running scheduled topic queries against OpenAlex.
- Uses Gemini to filter spam, compare candidates against existing library interests, and curate a daily "Today's Top Reads" banner with rationale.

---

## 🏗 Architecture & How It Works

```
                        +----------------------------+
                        |   React 18 + Vite Frontend |
                        +--------------+-------------+
                                       |
                +----------------------+----------------------+
                |                                             |
                v                                             v
+--------------------------------+           +---------------------------------+
|   Supabase (PostgreSQL)        |           |   FastAPI RAG Backend           |
| - Auth & Row Level Security    |           | - /api/chat/stream (SSE)        |
| - Library, Folders, Metadata   |           | - /api/papers/{id}/index        |
| - pgvector paper_chunks (768d) |<--------->| - /api/papers/{id}/upload-pdf   |
| - match_paper_chunks RPC       |           | - /api/agent/stream (ReAct)     |
+--------------------------------+           +----------------+----------------+
                                                              |
                 +--------------------------------------------+
                 |
                 v
+-------------------------------------------------------------------------------+
|                      Resilient Ingestion Engine                               |
| 1. Canonical UUID Resolution (backend/app/services/paper_resolution.py)       |
| 2. Candidate Priority Queue (arXiv -> OpenAlex -> Unpaywall -> PMC XML)       |
| 3. HTML "Follow the PDF Button" Engine (regex link scoring & SSRF validation) |
| 4. Failure Diagnostics (Paywall vs Login vs Bot Protection)                  |
| 5. PyPDF Page Extraction -> Batch Gemini 768d Embeddings -> pgvector Upsert   |
+-------------------------------------------------------------------------------+
```

---

## 📁 Repository Structure

```
RESIN/
├── backend/                             # Python FastAPI RAG & Agent Backend
│   ├── app/
│   │   ├── agent/                      # Autonomous Research Agent (ReAct loop, tools)
│   │   ├── api/                        # REST & SSE Endpoints (chat, embed, search, agent)
│   │   ├── core/                       # Auth, Config, Supabase Clients
│   │   ├── schemas/                    # Pydantic request/response schemas
│   │   ├── services/                   # Core business logic
│   │   │   ├── chunking.py             # Section & page-aware text chunking
│   │   │   ├── embeddings.py           # Single-call batch Gemini 768-dim embeddings
│   │   │   ├── gemini_service.py       # Unified Google GenAI client & model fallback
│   │   │   ├── indexing.py             # Indexing orchestration & batch upserts
│   │   │   ├── open_access.py          # HTML discovery engine & candidate queue
│   │   │   ├── paper_resolution.py     # Canonical UUIDv5 & DB de-duplication
│   │   │   ├── pdf.py                  # PDF validation, download taxonomy, PyPDF parser
│   │   │   ├── rag.py                  # Retrieval-Augmented Generation & SSE streaming
│   │   │   ├── redis_cache.py          # Response & query caching layer
│   │   │   └── retrieval.py            # pgvector similarity queries
│   │   └── main.py                     # FastAPI entrypoint & middleware
│   ├── migrations/                     # SQL migration scripts for pgvector & tables
│   ├── requirements.txt                # Backend dependencies
│   ├── .gitignore                      # Backend-specific ignore rules
│   └── .env.example                    # Backend environment template
│
├── frontend/                            # React 18 + Vite + TypeScript Frontend
│   ├── src/
│   │   ├── components/                 # UI Components (PaperCard, PaperChat, Drawer, Triage)
│   │   ├── lib/                        # API clients (ragApi, semanticScholar, supabase, gemini)
│   │   ├── pages/                      # Application routes (Papers, Library, Agent, Graph)
│   │   ├── App.tsx                     # Main Router
│   │   └── main.tsx                    # React DOM entry
│   ├── package.json                    # Frontend dependencies
│   ├── vite.config.ts                  # Vite bundler config
│   ├── .gitignore                      # Frontend-specific ignore rules
│   └── .env.example                    # Frontend environment template
│
├── resin-triage/                        # Background Node.js Triage Microservice
│   ├── daily-triage.js                 # Daily user topic scanner & Gemini curator
│   ├── package.json                    # Triage dependencies
│   ├── .gitignore                      # Triage-specific ignore rules
│   └── .env.example                    # Triage environment template
│
├── .gitignore                           # Comprehensive root gitignore
├── .env.example                         # Root environment reference guide
├── PROJECT_DETAILS_AND_RAG.md          # Comprehensive Architecture & RAG Deep Dive
└── README.md                            # Project Overview & Quickstart (This file)
```

---

## ⚡ Quickstart

### 1. Prerequisites
- **Node.js** 18+ and **npm**
- **Python** 3.11+
- **Supabase Account** (with `pgvector` enabled)
- **Google Gemini API Key** (from [Google AI Studio](https://aistudio.google.com/))

---

### 2. Database Setup (Supabase)
1. In your Supabase Dashboard, open the **SQL Editor**.
2. Run the migration script located at [`backend/migrations/full_rag_setup.sql`](file:///c:/Users/VARAD/Documents/GitHub/RESIN/backend/migrations/full_rag_setup.sql).
3. This creates:
   - `pgvector` extension
   - `papers`, `paper_chunks`, `paper_embeddings`, `chat_history`, `agent_runs`, `daily_triage` tables
   - `match_paper_chunks` stored procedure for vector cosine similarity

---

### 3. Backend Setup
```bash
cd backend

# Create and activate virtual environment
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your Supabase URL, Service Key, and Gemini API Key

# Start FastAPI development server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
The backend will be running at `http://localhost:8000` (API documentation at `http://localhost:8000/docs`).

---

### 4. Frontend Setup
```bash
cd frontend

# Install dependencies
npm install

# Configure environment
cp .env.example .env
# Edit .env with your Supabase URL, Anon Key, and VITE_RAG_BACKEND_URL=http://localhost:8000

# Start Vite development server
npm run dev
```
Open `http://localhost:5173` in your browser.

---

### 5. Daily Triage Microservice (Optional)
```bash
cd resin-triage

# Install dependencies
npm install

# Configure environment
cp .env.example .env
# Edit .env with your Supabase database pooler URL and Gemini API Key

# Run triage worker manually
node daily-triage.js
```

---

## 🔑 Environment Variables

| Variable | Service | Required | Description |
| :--- | :--- | :--- | :--- |
| `VITE_SUPABASE_URL` | Frontend & Backend | **Yes** | Your Supabase project URL (`https://xyz.supabase.co`) |
| `VITE_SUPABASE_ANON_KEY` | Frontend & Backend | **Yes** | Public Supabase anon API key |
| `VITE_SUPABASE_SERVICE_KEY` | Backend | **Yes** | Supabase service role key (for pgvector write operations) |
| `VITE_GEMINI_API_KEY` | Backend | **Yes** | Google AI Studio Gemini API Key |
| `VITE_GEMINI_EMBEDDING_MODEL` | Backend | Optional | Default: `models/gemini-embedding-001` |
| `VITE_GEMINI_CHAT_MODEL` | Backend | Optional | Default: `models/gemini-3.5-flash-lite` |
| `VITE_RAG_BACKEND_URL` | Frontend | **Yes** | URL pointing to FastAPI (`http://localhost:8000`) |
| `REDIS_URL` | Backend | Optional | Redis cache URL (default: falls back gracefully to in-memory) |
| `VITE_SEMANTIC_SCHOLAR_API_KEY`| Backend & Frontend | Optional | Semantic Scholar API key for higher rate limits |

---

## 📖 Documentation

For a comprehensive technical deep dive into vector math, tokenization, prompt structures, candidate queuing algorithms, and sequence diagrams, refer to:
👉 **[`PROJECT_DETAILS_AND_RAG.md`](PROJECT_DETAILS_AND_RAG.md)**

---

## 📄 License

This project is licensed under the MIT License.
