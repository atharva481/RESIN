# RESIN: Project Overview & System Specification

> [!NOTE]
> For the comprehensive technical deep dive into vector mathematics, section-aware chunking algorithms, prompt assembly, and end-to-end sequence diagrams, please refer to **[`PROJECT_DETAILS_AND_RAG.md`](PROJECT_DETAILS_AND_RAG.md)**.

---

## 📌 Executive Summary

**RESIN** (Research Engine & Synthesized Intelligence Network) is an end-to-end academic workstation designed for researchers, machine learning engineers, and students. Rather than passively skimming PDFs or relying on hallucinated summaries, RESIN indexes scientific literature into section-aware high-dimensional vector embeddings, empowering users to:

1. **Grounded Paper Chat (RAG)**: Ask technical questions with real-time SSE streaming and clickable citations pinpointing exact PDF pages and sections.
2. **Autonomous Multi-Paper Research Agent**: Synthesize literature across multiple papers using an iterative ReAct reasoning loop.
3. **Resilient Open-Access Discovery**: Automatically harvest verified open-access PDFs across arXiv, OpenAlex, Europe PMC XML, and publisher mirrors.
4. **Daily Paper Triage**: Receive an automated daily briefing curated specifically for individual research topic interests.

---

## 🏗 Architecture & Technology Stack

| Layer | Technology | Purpose |
| :--- | :--- | :--- |
| **Frontend** | React 18, Vite, TypeScript | SPA workstation, reactive UI via TanStack Query, SSE chunk stream consumer |
| **Styling** | Vanilla Tailwind CSS, Shadcn UI | Academic "paper & ink" design language, responsive drawers, glassmorphic badges |
| **Backend API** | FastAPI, Python 3.11+, Uvicorn | High-concurrency REST & SSE streaming, SSRF guards, PDF validation |
| **Database** | PostgreSQL on Supabase | User accounts, library folders, papers dictionary, RLS access control |
| **Vector Engine** | `pgvector` (`vector(768)`) | IVFFlat indexed similarity search using cosine distance operator (`<=>`) |
| **AI Models** | Google Gemini (GenAI SDK) | `gemini-embedding-001` (vectors), `gemini-3.5-flash-lite` (low-latency streaming & reasoning) |
| **PDF Extraction** | PyPDF, BeautifulSoup4 | In-memory binary parsing, page boundary identification, HTML PDF discovery |
| **Triage Service**| Node.js (ESM), PostgreSQL pool | Scheduled microservice for topic-based paper harvesting & LLM curation |

---

## 🗄 Core Database Schema (PostgreSQL on Supabase)

### `papers`
Shared canonical repository of scientific papers saved across all users.
- `id`: `uuid` (Primary Key, resolved deterministically via UUIDv5)
- `doi`: `text` (Indexed)
- `title`: `text` (NOT NULL)
- `authors`: `text[]`
- `year`: `integer`
- `abstract`: `text`
- `citation_count`: `integer`
- `open_access_url`: `text`
- `semantic_scholar_id`: `text` (UNIQUE)
- `arxiv_id`: `text` (UNIQUE)
- `indexed_at`: `timestamptz`

### `paper_chunks`
Granular text segments extracted from paper pages with vector embeddings for RAG retrieval.
- `id`: `uuid` (Primary Key)
- `paper_id`: `uuid` (Foreign Key -> `papers.id` ON DELETE CASCADE)
- `chunk_index`: `integer` (0-indexed position)
- `section_title`: `text` (Section header or page marker)
- `content`: `text` (Chunk text content)
- `embedding`: `vector(768)` (IVFFlat cosine indexed)
- `word_count`: `integer`
- `page_number`: `integer` (1-indexed physical PDF page)
- `document_id`: `text` (Source PDF identifier)

### `paper_embeddings`
Holistic paper-level 768-dimensional embedding for whole-library semantic search.
- `id`: `uuid` (Primary Key)
- `paper_id`: `uuid` (Foreign Key -> `papers.id` UNIQUE)
- `embedding`: `vector(768)`

### `users` & `user_papers` & `folders`
User management, hierarchical folders, reading statuses (`unread`, `in_progress`, `done`), and personal notes secured strictly via PostgreSQL Row Level Security (RLS).

### `daily_triage`
AI-curated daily top 3 paper picks with rationale tailored to user topic preferences.

---

## 🔒 Security & Access Control (Row Level Security)

- **User Isolation**: User libraries, custom folders, and daily triage entries are protected by strict RLS policies bound to `auth.uid()`.
- **Shared Knowledge Base**: Authenticated users share read access to canonical papers and vectorized chunks to eliminate redundant embedding compute.
- **SSRF Guards**: The PDF download service enforces strict private IP and loopback blocking against Server-Side Request Forgery.
- **Service Role Isolation**: Vector writes and administrative RPCs are executed securely by the backend using the Supabase Service Role Key.
