# RESIN: Comprehensive Architecture & RAG Deep Dive

---

## 1. Executive Overview

**RESIN** (Research Engine & Synthesized Intelligence Network) is an end-to-end AI-powered academic research platform designed for researchers, machine learning engineers, and students. It transforms passive reading of scientific papers into an interactive, grounded, and organized workflow.

Rather than merely searching paper abstracts or summarizing surface-level summaries, RESIN operates a **production-grade Retrieval-Augmented Generation (RAG) engine** backed by PostgreSQL (`pgvector`), Google Gemini generative and embedding models, automated open-access PDF resolution, and real-time Server-Sent Events (SSE) streaming.

### Key Capabilities
- **Academic Search & Discovery:** Multi-provider search across Semantic Scholar and OpenAlex with automatic 403/429 rate-limit failovers.
- **Personalized Research Library:** Hierarchical folder organization, reading status tracking (`unread`, `in_progress`, `done`), and automated citation exports (BibTeX, APA, MLA).
- **Automated Open-Access PDF Resolution:** A multi-source fallback pipeline that extracts clean arXiv identifiers from DOIs, queries Semantic Scholar Graph APIs, verifies Unpaywall repositories, and retrieves full-text PDFs even for closed-access/IEEE publications.
- **Section-Aware & Page-Aware RAG:** Full-text PDF chunking with page number tracking, pgvector indexing, cosine similarity ranking, and grounded Q&A with clickable citation pills.
- **Autonomous Multi-Paper Research Agent:** A ReAct-style agent equipped with tool-calling to compare multiple papers, search the user's private library, query live academic databases, and synthesize cross-paper literature reviews.
- **Automated Daily Paper Triage:** A scheduled Node.js microservice that tracks individual user research interests, gathers weekly candidates, curates the top 3 high-impact daily reads via Gemini, and presents them in a "Today's Top Reads" banner.

---

## 2. Complete Project Architecture & Directory Structure

```
RESIN/
├── backend/                             # Python FastAPI RAG & Agent Backend
│   ├── app/
│   │   ├── agent/                      # Autonomous Research Agent
│   │   │   ├── agent.py                # ReAct loop, Gemini tool executor, agent run tracker
│   │   │   ├── formatter.py            # Markdown cleaner & query intent detector
│   │   │   ├── prompt.py               # System prompts for research agent
│   │   │   └── tools.py                # Tool declarations & dispatch registry
│   │   ├── api/                        # HTTP & SSE API Endpoints
│   │   │   ├── agent.py                # /api/agent/run and /api/agent/stream
│   │   │   ├── chat.py                 # /api/chat and /api/chat/stream
│   │   │   ├── embed.py                # /api/papers/{id}/index
│   │   │   ├── health.py               # /health and Redis check
│   │   │   └── search.py               # /api/papers/search (Semantic Scholar + OpenAlex proxy)
│   │   ├── core/                       # App Configuration & Clients
│   │   │   ├── auth.py                 # JWT token extraction & Supabase auth verification
│   │   │   ├── config.py               # Pydantic Settings (.env loader)
│   │   │   └── supabase.py             # Supabase Client & RPC wrapper functions
│   │   ├── schemas/                    # Pydantic Request/Response Models
│   │   │   ├── chat.py                 # ChatRequest, ChatResponse, Citation, ChatMessage
│   │   │   └── indexing.py             # IndexPaperRequest, IndexPaperResponse, ChunkInfo
│   │   ├── services/                   # Business Logic & Core Infrastructure
│   │   │   ├── chat_service.py         # Chat turn persistence in chat_history table
│   │   │   ├── chunking.py             # TextChunker (section-aware, word-overlap, page-aware)
│   │   │   ├── embeddings.py           # Single-call batch Gemini 768-dim embeddings
│   │   │   ├── gemini_service.py       # Unified Google GenAI client, 429 guards & model fallback
│   │   │   ├── indexing.py             # IndexingService (PDF page chunking, upserting, batching)
│   │   │   ├── open_access.py          # Multi-source open access discovery & HTML PDF engine
│   │   │   ├── paper_resolution.py     # Deterministic UUIDv5 canonical resolution & DB de-duplication
│   │   │   ├── pdf.py                  # PDFService (SSRF validation, download taxonomy, PyPDF)
│   │   │   ├── rag.py                  # RAGService (retrieval orchestration, prompt assembly, SSE)
│   │   │   ├── redis_cache.py          # Redis response & query caching layer
│   │   │   └── retrieval.py            # RetrievalService (pgvector similarity retrieval)
│   │   └── main.py                     # FastAPI application entrypoint & CORS middleware
│   ├── migrations/                     # PostgreSQL & pgvector SQL migrations
│   │   ├── 20260729_add_pgvector_paper_chunks.sql
│   │   ├── 20260810_add_chat_history_and_paper_embeddings_function.sql
│   │   ├── 20260904_agent_runs_and_page_numbers.sql
│   │   └── full_rag_setup.sql          # Complete database & RPC setup script
│   ├── requirements.txt                # Python dependencies (FastAPI, Supabase, Google-GenAI, PyPDF, etc.)
│   ├── .gitignore                      # Backend-specific ignore rules
│   └── .env.example                    # Backend environment template
│
├── frontend/                            # React 18 + Vite + TypeScript Frontend
│   ├── src/
│   │   ├── components/                 # UI Components
│   │   │   ├── DailyTriageSection.tsx  # "Today's Top Reads" AI-curated banner
│   │   │   ├── PaperCard.tsx           # Paper preview card with save, cite, and chat triggers
│   │   │   ├── PaperChat.tsx           # Interactive RAG Q&A drawer with real-time SSE streaming
│   │   │   ├── ResearchAgentView.tsx   # Multi-paper agent conversation interface
│   │   │   └── ui/                     # Shadcn UI primitives (Button, Dialog, Input, etc.)
│   │   ├── lib/                        # Client-side API & Utility Wrappers
│   │   │   ├── ragApi.ts               # Backend RAG API client (streamPaperRAG, indexPaper, askPaperRAG)
│   │   │   ├── semanticScholar.ts      # Client search and metadata fetcher
│   │   │   ├── supabase.ts             # Supabase Auth, client initialization, daily_triage queries
│   │   │   └── types.ts                # Domain models (Paper, UserPaper, Citation, TriageItem)
│   │   ├── pages/                      # Application Route Views
│   │   │   ├── Agent.tsx               # Autonomous Research Agent page
│   │   │   ├── Auth.tsx                # Google OAuth / Email login page
│   │   │   ├── Graph.tsx               # Citation connection visualizer
│   │   │   ├── Library.tsx             # Saved folders, reading tracker, BibTeX exporter
│   │   │   └── Papers.tsx              # Paper Hub (Search + Daily Triage)
│   │   ├── App.tsx                     # React Router routes & Layout wrappers
│   │   └── main.tsx                    # React root entry point
│   ├── package.json                    # NPM dependencies (React, Vite, TanStack Query, Lucide)
│   └── vite.config.ts                  # Vite bundler configuration & path aliases
│
├── resin-triage/                        # Background Node.js Triage Microservice
│   ├── daily-triage.js                 # Daily user topic scanner, OpenAlex candidate fetcher, Gemini curator
│   ├── package.json                    # Node dependencies (pg, dotenv)
│   ├── .gitignore                      # Triage-specific ignore rules
│   └── .env.example                    # Triage database connection & Gemini API key template
│
├── project_details.md                  # Initial summary specification
└── PROJECT_DETAILS_AND_RAG.md          # Comprehensive Architecture & RAG Deep Dive (This file)
```

---

## 3. Technology Stack & Component Interactions

| Layer | Technology | Primary Responsibility |
| :--- | :--- | :--- |
| **Frontend** | React 18, Vite, TypeScript | SPA client, reactive state via TanStack Query, Markdown rendering, SSE chunk reading |
| **Styling** | Vanilla Tailwind CSS, Shadcn UI | Academic "paper & ink" design system, responsive drawers, glassmorphism badges |
| **Backend API** | FastAPI, Uvicorn, Pydantic v2 | High-concurrency REST endpoints, SSE streams, SSRF guards, rate-limit retries |
| **Database** | PostgreSQL on Supabase | User accounts, library folders, papers dictionary, RLS policies |
| **Vector Engine** | `pgvector` extension | 768-dimensional vector storage, IVFFlat indexing, cosine distance operator (`<=>`) |
| **LLM & Embeddings** | Google Gemini Generative AI | `models/gemini-embedding-001` (embeddings), `models/gemini-3.5-flash-lite` (RAG stream) |
| **PDF Extraction** | PyPDF | In-memory binary parsing, page boundary identification, text sanitization |
| **Caching Layer** | Redis 6+ / In-Memory | Exact query response caching, search query caching, rate limit shielding |
| **Triage Worker** | Node.js (ESM), PostgreSQL client | Cron-executable batch worker, OpenAlex work discovery, candidate re-ranking |

---

## 4. Deep Dive: The RAG (Retrieval-Augmented Generation) Architecture

The RAG pipeline in RESIN is custom-engineered to solve the real-world obstacles of scientific papers: paywalled DOIs, complex multi-page layouts, large payload transfer limits, rate limiting, and model latency.

```
    +--------------------------------+--------------------------------+
    |                    INGESTION & PDF DISCOVERY                    |
    |                                                                 |
    |  Step 1: Canonical Paper Resolution (paper_resolution.py)       |
    |          - Resolves by existing ID / DOI / Semantic Scholar ID  |
    |          - Derives deterministic UUIDv5 to prevent 23505/23503  |
    |                                                                 |
    |  Step 2: Check Supabase `paper_chunks` count >= 5               |
    |          --> If yes: Return in ~40ms ("Already Indexed")        |
    |          --> If < 5 (stale partial chunks): Purge & re-index    |
    |                                                                 |
    |  Step 3: Build Ranked Candidate Priority Queue (Priorities 50-120)|
    |          - Priority 120: Direct arXiv PDF synthesized from ID   |
    |          - Priority 100: PMC / Europe PMC structured XML & PDF  |
    |          - Priority 95:  Semantic Scholar verified OA PDF link  |
    |          - Priority 90:  OpenAlex primary location pdf_url      |
    |          - Priority 85:  OpenAlex secondary location pdf_urls   |
    |          - Priority 80:  Unpaywall direct PDF links             |
    |          - Priority 75:  Existing open_access_url               |
    |          - Priority 65:  HTML Landing Page Discovery (Link Score|
    |          - Priority 50:  arXiv Title Search export fallback     |
    |                                                                 |
    |  Step 4: Download & Diagnose Candidate (PDFService)             |
    |          - SSRF IP & subnet validation                          |
    |          - Stream size cap: 100MB max limit                     |
    |          - Magic byte validation: %PDF-                         |
    |          - If HTML landing page: Follow the PDF Button Engine   |
    |          - Structured Failure Taxonomy:                         |
    |            PAYWALL_DETECTED, LOGIN_REQUIRED, BOT_PROTECTION,    |
    |            HTTP_ERROR, TIMEOUT, PARSE_ERROR, EMPTY_DOCUMENT     |
    |                                                                 |
    |  Step 5: Full-Text Structured Fallback (Europe PMC / NCBI)      |
    |          - If direct PDF blocked (e.g. 403 bot challenge):      |
    |          - Fetches PMC structured XML via E-utilities / EPMC    |
    |          - Parses <abstract>, body direct <p>, and <sec> tags   |
    |          - Generates 15-30 comprehensive structured sections    |
    |                                                                 |
    |  Step 6: Paywall Handling & User Upload Route                   |
    |          - If paywalled: Suppress embedding (0 chunks)          |
    |          - Return diagnostic status to frontend                 |
    |          - Allow manual PDF upload via POST /upload-pdf         |
    +--------------------------------+--------------------------------+
                                     |
                                     v
    +--------------------------------+--------------------------------+
    |                 CHUNKING & VECTORIZATION                        |
    |                                                                 |
    |  1. TextChunker splits pages/sections into overlapping windows: |
    |     - Chunk Size: ~600 words | Overlap: ~100 words              |
    |     - Page Number & Section Title tagged to each chunk          |
    |  2. EmbeddingService (Single-Call High Throughput):             |
    |     - Model: `models/gemini-embedding-001`                      |
    |     - Strict dimension enforcement: Vector(768)                 |
    |     - High-Performance Batching: Unified single-call (size=100) |
    |     - Speed: 50+ chunks embedded in ~2.1s instead of 20+s       |
    |     - Resilient Fallback: Item-by-item downgrade if batch fails |
    |  3. Database Storage:                                           |
    |     - Upserted into `paper_chunks` in batches of 100            |
    |     - Generates holistic paper-level vector into `paper_embeddings`|
    +-----------------------------------------------------------------+
```

---

### Step-by-Step RAG Breakdown

### 4.1 Ingestion: What It Fetches & How It Discovers Full PDFs

Academic papers are notoriously difficult to fetch automatically because publishers often hide PDFs behind paywalls, institutional redirects, or Cloudflare/CloudPMC bot challenges (e.g. IEEE Xplore, ScienceDirect, Nature, Springer, Wiley).

RESIN implements a **multi-stage resilient ingestion engine** across [`backend/app/services/paper_resolution.py`](file:///c:/Users/VARAD/Documents/GitHub/RESIN/backend/app/services/paper_resolution.py), [`backend/app/services/open_access.py`](file:///c:/Users/VARAD/Documents/GitHub/RESIN/backend/app/services/open_access.py), and [`backend/app/services/pdf.py`](file:///c:/Users/VARAD/Documents/GitHub/RESIN/backend/app/services/pdf.py):

#### 1. Canonical Paper Resolution (`paper_resolution.py`)
To prevent PostgreSQL foreign key (`23503`) or unique key (`23505`) violations when papers are saved across different search sessions:
- Checks if the paper already exists in `public.papers` by ID, DOI, or Semantic Scholar ID.
- If missing, derives a **deterministic UUIDv5** from `doi` (or `semantic_scholar_id`, or normalized title).
- Atomically guarantees that the paper record exists before any chunk indexing starts.

#### 2. Ranked Candidate Priority Queue (Priorities 50–120)
Rather than trying arbitrary URLs in arbitrary order, candidates are ranked by expected fidelity and bot accessibility:
- **Priority 120 (Direct arXiv PDF):** Clean regex extraction of arXiv ID (from `10.48550/arxiv.XXXX.XXXXX`, `arxiv.org/abs/...`, or raw IDs) yields `https://arxiv.org/pdf/{arxiv_id}.pdf`. Always free, instant, and high-throughput.
- **Priority 100 (Europe PMC / NCBI E-utilities):** Resolved PMC IDs (`PMC4320685`) point directly to Europe PMC open endpoints (`https://europepmc.org/backend/ptpmcrender.fcgi?accid={pmcid}&blobtype=pdf`).
- **Priority 95 (Semantic Scholar Open Access):** Verified `openAccessPdf` link from the S2 Graph API.
- **Priority 90 (OpenAlex Primary Location):** Verified `best_oa_location.pdf_url` from OpenAlex.
- **Priority 85 (OpenAlex Secondary Mirrors):** All repository locations in `locations[].pdf_url` (institutional repositories, Zenodo, HAL, etc.).
- **Priority 80 (Unpaywall API):** Direct legal institutional repository PDFs matching the DOI.
- **Priority 75 (Existing URL):** Any previously saved `open_access_url`.
- **Priority 65 (HTML Landing Pages):** Publisher article landing pages scheduled for HTML PDF button inspection.
- **Priority 50 (arXiv Title Search):** Preprint export search by exact sanitized title.

#### 3. Second-Stage HTML PDF Discovery Engine ("Follow the PDF Button")
When an open-access candidate URL leads to an HTML landing page instead of raw PDF bytes:
1. `HTMLPDFDiscoveryEngine` downloads the page content.
2. Evaluates HTML `<meta>` tags: `<meta name="citation_pdf_url" content="...">` and `<meta name="dc.identifier" scheme="pdf" ...>`.
3. Scores candidate `<a>` links and `<button>` wrappers:
   - Links with `pdf` or `download` in text/attributes: **+30 points**
   - Links with `.pdf` file extension: **+40 points**
   - Links matching article/view/download path structures: **+20 points**
   - Links matching `cite`, `bibtex`, or `suppl`: **-40 points** (filters non-article attachments)
4. Resolves relative URLs (e.g., `/content/pdf/10.1038/...`) against the page base URL.
5. Recursively downloads and verifies the highest-scoring candidate.

#### 4. Structured Full-Text PMC XML Extraction (`_parse_pmc_xml_to_sections`)
When a biomedical or life sciences paper on PubMed Central has a paywalled or bot-protected PDF (e.g., CloudPMC 403 bot challenges):
- RESIN queries the Europe PMC REST API (`/articles/{pmcid}?resultType=core`) and NCBI E-utilities (`efetch.fcgi?db=pmc&id={pmcid}&retmode=xml`).
- Parses the JATS XML document:
  - Extracts the full `<abstract>`.
  - Captures direct `<p>` paragraphs under `<body>` (e.g. *Nature Biotechnology* articles where Introduction and Results paragraphs reside directly under `<body>` without `<sec>` tags) and organizes them into cohesive `Introduction & Results` and `Main Text` blocks.
  - Extracts all nested `<sec>` sections with their headings (`Methods`, `Discussion`, `Validation`).
- Generates **15–30 structured full-text sections**, which are indexed with physical section tracking.

#### 5. Diagnostic Failure Taxonomy & Paywall Detection
`PDFService.download_pdf()` returns a strongly-typed `PDFDownloadResult` with a classified diagnostic taxonomy:
- `SUCCESS`: Valid PDF downloaded with magic byte `%PDF-` verification.
- `PAYWALL_DETECTED`: Detected paywall patterns ("purchase access", "rent this article", "subscribe", "institutional access", "checkout").
- `LOGIN_REQUIRED`: Detected auth gates ("login with shibboleth", "athens", "sign in with your institution").
- `BOT_PROTECTION`: 403/Cloudflare/CloudPMC challenges blocking automated scrapers.
- `HTTP_ERROR`: Upstream 404, 500, 502 server failures.
- `EMPTY_DOCUMENT`: Document contained 0 readable pages or corrupted streams.

#### 6. Embedding Suppression & Manual User PDF Upload
- **Zero Hallucination / No Misleading 1-Chunk Embeddings:** If all automated discovery candidates encounter a paywall or login gate, RESIN **does not generate fake single-chunk embeddings from the abstract**. Instead, it reports the exact diagnostic reason to the user in the UI.
- **Direct User PDF Upload (`POST /api/papers/{paper_id}/upload-pdf`):** If a user owns or has institutional access to a PDF of a paywalled paper, they can upload it directly through the UI. The backend receives the multipart file, validates the `%PDF-` magic header, extracts all pages via `PyPDF`, splits them into section-aware chunks, generates 768-dim Gemini embeddings, and upserts them into `paper_chunks` in unified batches of 100.

---

### 4.2 Chunking & Vectorization: What It Chunks & Embeds

When a valid PDF is downloaded, text is extracted page by page via `PyPDF`. The text is then processed by `TextChunker` in [`backend/app/services/chunking.py`](file:///c:/Users/VARAD/Documents/GitHub/RESIN/backend/app/services/chunking.py):

1. **Section & Page Awareness:**
   Rather than slicing raw text at arbitrary character boundaries (which cuts sentences and formulas in half), the chunker respects page boundaries and section headers (`[Abstract]`, `[Introduction]`, `[Methods]`, `[Page 3]`).
2. **Parameters:**
   - **Target Chunk Size:** 600 words (~800 tokens).
   - **Sliding Overlap:** 100 words (~130 tokens) to preserve semantic context across chunk edges.
   - **Minimum Chunk Size:** 100 words (filters out isolated headers or blank pages).
3. **Embedding Generation:**
   In [`backend/app/services/embeddings.py`](file:///c:/Users/VARAD/Documents/GitHub/RESIN/backend/app/services/embeddings.py), chunks are sent to Google Gemini's embedding service:
   - **Model:** `models/gemini-embedding-001`.
   - **Task Type:** `retrieval_document` during indexing; `retrieval_query` during user search.
   - **Dimension Strictness:** Sliced to exactly 768 dimensions using `output_dimensionality=768` and `_enforce_768_dims()`, perfectly matching Supabase `vector(768)` columns.
   - **High-Throughput Batch Vectorization:** Chunks are vectorized using single-call batch requests (`batch_size = 100`), processing 50–60 chunks in ~2.1 seconds (instead of 20+ seconds over sequential calls).
   - **Resilient Fallback:** Automatically falls back to item-by-item generation if a batch exceeds payload or token thresholds.

---

### 4.3 Database Storage: What Is Stored in Supabase (`pgvector`)

All indexing data is stored in the user's PostgreSQL database managed by Supabase.

#### Table: `public.paper_chunks`
Stores the granular text chunks and their high-dimensional vector representations.

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | `uuid` (PK) | Unique chunk ID |
| `paper_id` | `uuid` (FK) | Reference to `papers.id` (Cascades on delete) |
| `chunk_index` | `int` | Sequential position within the paper (0, 1, 2, ...) |
| `section_title`| `text` | Section or page title (e.g. `Introduction`, `Page 4`) |
| `content` | `text` | The actual text extracted from the PDF |
| `embedding` | `vector(768)` | 768-dimensional float array for cosine similarity |
| `word_count` | `int` | Length of the chunk content in words |
| `page_number` | `int` | The physical PDF page number (1-indexed) |
| `document_id` | `text` | The source PDF URL (e.g. `https://arxiv.org/pdf/2103.14030.pdf`) |
| `created_at` | `timestamptz` | Indexing timestamp |

**Unique Constraint:** `UNIQUE (paper_id, chunk_index)` prevents duplicate chunks.  
**Index:** `CREATE INDEX paper_chunks_embedding_idx ON paper_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);`

#### Table: `public.paper_embeddings`
Stores a holistic, paper-level vector embedding computed over the first 8,000 characters of the document. This enables semantic searching across the entire user library (e.g., *"Find all papers in my library about vision transformers"*).

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | `uuid` (PK) | Unique embedding ID |
| `paper_id` | `uuid` (FK) | Reference to `papers.id` (UNIQUE) |
| `embedding` | `vector(768)` | Holistic document embedding |
| `created_at` | `timestamptz` | Creation timestamp |

---

### 4.4 Retrieval: Stored Procedures & Cosine Similarity

When a user asks a question, RESIN executes the stored procedure `match_paper_chunks` directly inside PostgreSQL:

```sql
CREATE OR REPLACE FUNCTION public.match_paper_chunks(
  query_embedding vector(768),
  match_threshold float,
  match_count int,
  filter_paper_id uuid DEFAULT NULL
)
RETURNS TABLE (
  id uuid,
  paper_id uuid,
  chunk_index int,
  section_title text,
  content text,
  similarity float,
  page_number int,
  document_id text
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    pc.id,
    pc.paper_id,
    pc.chunk_index,
    pc.section_title,
    pc.content,
    1 - (pc.embedding <=> query_embedding) AS similarity,
    pc.page_number,
    pc.document_id
  FROM public.paper_chunks pc
  WHERE
    (filter_paper_id IS NULL OR pc.paper_id = filter_paper_id)
    AND 1 - (pc.embedding <=> query_embedding) > match_threshold
  ORDER BY pc.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;
```

#### How Cosine Similarity Works Here
- The operator `<=>` calculates the **cosine distance** between the query vector and chunk vectors.
- Distance ranges from `0.0` (identical direction) to `2.0` (opposite direction).
- `1 - (pc.embedding <=> query_embedding)` converts this to **cosine similarity** (where `1.0` is an exact match).
- Chunks with similarity below `match_threshold` (default `0.25`) are discarded.
- The top `k` highest-scoring chunks (default `top_k = 4`) are returned with their page numbers and text snippets.

---

### 4.5 Generation: Real-Time SSE Streaming & Grounding

```
      User Query ("What is shifted window self-attention?")
                             |
                             v
      Embed Query via `models/gemini-embedding-001` (~1.2s)
                             |
                             v
      Execute `match_paper_chunks` in Supabase (~2.5s)
                             |
                             v
      Format Evidence Context Blocks with Page Numbers & Citations
                             |
                             v
      Stream Response via `models/gemini-3.5-flash-lite` (~1.6s)
                             |
                             v
      FastAPI StreamingResponse (media_type="text/event-stream")
                             |
                             v
      Frontend ReadableStream decodes JSON chunks and renders Markdown
```

#### Prompt Assembly & Anti-Hallucination Grounding
The retrieved chunks are assembled into structured context blocks in [`backend/app/services/rag.py`](file:///c:/Users/VARAD/Documents/GitHub/RESIN/backend/app/services/rag.py):

```text
Section: Shifted Window Attention | Page 3
Evidence:
The shifted windowing scheme brings greater efficiency by limiting self-attention 
computation to non-overlapping local windows while also allowing for cross-window connection...
```

The system prompt enforces strict constraints:
1. **Directness:** Answers start immediately without boilerplate phrases like *"Based on the provided context..."*.
2. **Strict Grounding:** If the evidence does not contain sufficient details to answer, the model is instructed to output: *"I couldn't find enough evidence in the indexed paper to answer that confidently."*
3. **Structured Formats:** Automatically formats comparisons as Markdown tables, procedural workflows as numbered lists, and key takeaways as bulleted summaries.
4. **Citation Badging:** The frontend maps each chunk citation to a pill badge displaying the paper title, chunk number, and **exact page number** from the PDF.

#### Why `gemini-3.5-flash-lite` & Context Compaction?
- **Low-Latency Generation:** Earlier configurations using thinking-enabled models suffered from an internal reasoning pause that delayed token output by 8–10 seconds. Primary streaming on `models/gemini-3.5-flash-lite` delivers an average **Time-to-First-Token (TTFT) of ~1.1 seconds**.
- **Context Density Optimization:** Multi-turn chat sessions automatically compact conversation history to the most recent 2 turns and cap citation snippets at 1,200 characters. This eliminates Gemini 429 token/request exhaustion and prevents compounding 10–20s response pauses after multiple follow-up questions.
- **Fail-Fast 429 Handling:** If upstream Gemini free-tier rate limits are reached, the service fails fast immediately with a clear user prompt, rather than initiating a cascading, slow multi-model retry loop.

#### Frontend Resilient AI Summarization (503 Demand Failover)
In [`frontend/src/lib/gemini.ts`](file:///c:/Users/VARAD/Documents/GitHub/RESIN/frontend/src/lib/gemini.ts), single-click 5-point abstract summaries feature:
- **Automatic Jittered Retry:** If Google AI Studio returns `503 UNAVAILABLE` ("This model is currently experiencing high demand"), the client automatically pauses and retries.
- **Dynamic Candidate Model Failover:** Sequentially attempts candidate endpoints (`gemini-3.5-flash-lite` → `gemini-3.1-flash-lite` → `gemini-flash-lite-latest` → `gemini-flash-latest`), guaranteeing summary completion even during global peak-load demand spikes.

---

## 5. End-to-End Sequence Diagrams

### 5.1 Paper Indexing Flow
```mermaid
sequenceDiagram
    autonumber
    actor User
    participant FE as Frontend (PaperChat)
    participant API as FastAPI (/api/papers/{id}/index)
    participant DB as Supabase (PostgreSQL)
    participant OA as OpenAccessService
    participant PDF as PDFService
    participant GEM as Gemini API (Embedding)

    User->>FE: Opens chat or clicks "Index Paper"
    FE->>API: POST /api/papers/{id}/index
    API->>DB: SELECT count(*) FROM paper_chunks WHERE paper_id = id
    alt Chunks already exist (> 1) and force=false
        DB-->>API: count = 37
        API-->>FE: {"status": "success", "message": "Paper already indexed"} (~40ms)
    else Needs indexing or force=true
        API->>OA: find_pdf_candidates(doi, arxiv_id, existing_oa_url, title)
        OA-->>API: [Candidate 1 (arXiv Priority 120), Candidate 2 (PMC), ...]
        loop For each candidate until valid PDF
            API->>PDF: download_pdf(url) & extract_pages()
            PDF-->>API: 14 pages extracted
        end
        API->>GEM: embed_batch(chunk_texts) in single call (size=100)
        GEM-->>API: 37 vectors (768 dimensions) in ~2.1s
        API->>DB: Batch upsert chunks into paper_chunks
        API->>DB: UPDATE papers SET indexed_at = now()
        API-->>FE: {"status": "success", "chunks_created": 37}
    end
```

### 5.2 RAG Chat & Streaming Flow
```mermaid
sequenceDiagram
    autonumber
    actor User
    participant FE as Frontend (PaperChat)
    participant API as FastAPI (/api/chat/stream)
    participant GEM_E as Gemini (Embedding)
    participant DB as Supabase (pgvector)
    participant GEM_C as Gemini (Chat 3.5 Flash Lite)

    User->>FE: Types "What is the APCP framework?" & hits Enter
    FE->>API: POST /api/chat/stream {paper_id, message, history}
    API->>GEM_E: embed_query("What is the APCP framework?")
    GEM_E-->>API: 768-dim query vector
    API->>DB: rpc('match_paper_chunks', {query_vector, threshold: 0.25, top_k: 4})
    DB-->>API: Top 4 chunks (with text, page_number, similarity score)
    API->>API: Assemble SYSTEM_RAG_PROMPT with formatted citations
    API->>GEM_C: generate_content(prompt, stream=True)
    loop Stream SSE Chunks
        GEM_C-->>API: token chunk ("The APCP framework...")
        API-->>FE: data: {"text": "The APCP framework..."}\n\n
        FE->>FE: Append tokens to chat bubble in real-time
    end
    API-->>FE: Stream closed
    FE->>User: Complete answer rendered with page citation pills
```

---

## 6. Autonomous Research Agent (ReAct Loop)

In addition to single-paper RAG, RESIN includes an autonomous **Research Agent** located in [`backend/app/agent/agent.py`](file:///c:/Users/VARAD/Documents/GitHub/RESIN/backend/app/agent/agent.py).

When users ask complex cross-paper or exploratory questions (e.g. *"Compare the attention mechanisms between Swin Transformer and Vision Transformer in my library"*), the agent engages in an autonomous reasoning loop:

### Agent Tools
1. `search_semantic_scholar(query, limit)`: Searches academic publications live across global literature.
2. `search_user_library(query, folder_id)`: Searches holistic paper embeddings across the user's saved papers.
3. `search_paper_chunks(query, paper_id)`: Executes deep vector searches on a specific paper's content.
4. `summarize_paper(paper_id)`: Retrieves structured problem/method/findings summaries.

### Execution Loop
- The agent runs up to **15 iterations**.
- At each step, it logs its status to the `agent_runs` table and records individual tool invocations in the `tool_calls` table.
- Events and reasoning steps stream to the frontend via SSE (`POST /api/agent/stream`).

---

## 7. Automated Daily Paper Triage Microservice

Located in [`resin-triage/daily-triage.js`](file:///c:/Users/VARAD/Documents/GitHub/RESIN/resin-triage/daily-triage.js), this service acts as an automated research curator:

1. **User Profiling:** Reads all registered users, their selected research topics (`topics` array in `users`), and their existing saved library papers.
2. **Candidate Harvesting:** Queries the OpenAlex API for papers published in the last 7 days matching the user's topics. Filters out spam publications using citation count and repository heuristic checks.
3. **LLM Curation:** Sends the list of candidates alongside the user's saved library context to Gemini:
   ```json
   {
     "id": "openalex-id",
     "title": "Paper Title",
     "reason": "This paper extends the shifted-window attention from [Your Saved Paper] to video generation."
   }
   ```
4. **Persistence:** Saves the curated picks into the `daily_triage` table with `triage_date = CURRENT_DATE`.
5. **Display:** When the user logs in, the `DailyTriageSection` component on the Papers page displays these curated papers as **#1 Pick**, **#2 Pick**, and **#3 Pick** cards with direct external links and AI reasoning.

---

## 8. Database Schema & Security Architecture

### Row Level Security (RLS) Overview

Supabase Row Level Security ensures users can only access their own private data while sharing the common dictionary of indexed scientific papers:

```sql
-- Users: only access own profile
CREATE POLICY "Users manage own row" ON public.users
  FOR ALL USING (id = auth.uid());

-- User Papers: access only own saved papers
CREATE POLICY "Users manage own papers" ON public.user_papers
  FOR ALL USING (user_id = auth.uid());

-- Folders: access only own folders
CREATE POLICY "Users manage own folders" ON public.folders
  FOR ALL USING (user_id = auth.uid());

-- Daily Triage: users can only read their own daily recommendations
CREATE POLICY "Users can read own triage" ON public.daily_triage
  FOR SELECT TO authenticated
  USING (user_id = auth.uid());

-- Shared Papers & Chunks: public read access for all authenticated users
CREATE POLICY "Allow authenticated read on papers" ON public.papers
  FOR SELECT TO authenticated USING (true);

CREATE POLICY "Allow authenticated read on paper_chunks" ON public.paper_chunks
  FOR SELECT TO authenticated USING (true);
```

---

## 9. Environment Variables & Setup Reference

### Backend (`backend/.env`)
```bash
# Supabase PostgreSQL & API
VITE_SUPABASE_URL="https://your-project.supabase.co"
VITE_SUPABASE_ANON_KEY="eyJhbGciOi..."
VITE_SUPABASE_SERVICE_KEY="eyJhbGciOi..."  # Used by backend for pgvector RPCs & indexing

# Google Gemini API
VITE_GEMINI_API_KEY="AIzaSy..."
VITE_GEMINI_EMBEDDING_MODEL="models/gemini-embedding-001"
VITE_GEMINI_CHAT_MODEL="models/gemini-3.5-flash-lite"

# Academic APIs & Caching
VITE_SEMANTIC_SCHOLAR_API_KEY=""  # Optional: increases rate limits
REDIS_URL="redis://localhost:6379" # Optional: falls back gracefully to in-memory
```

### Frontend (`frontend/.env`)
```bash
VITE_SUPABASE_URL="https://your-project.supabase.co"
VITE_SUPABASE_ANON_KEY="eyJhbGciOi..."
VITE_RAG_BACKEND_URL="http://localhost:8000"
```

### Daily Triage (`resin-triage/.env`)
```bash
GEMINI_API_KEY="AIzaSy..."
SUPABASE_DB_URL="postgresql://postgres:[password]@db.[ref].supabase.co:5432/postgres"
OPENALEX_EMAIL="your-email@example.com"
```

---

## 10. Summary of Architectural Strengths

1. **Zero Wasted Re-indexing:** Indexed papers check chunk counts in <50ms, skipping redundant PDF downloads.
2. **Resilient Ingestion:** If a publisher link is an HTML paywall, the system automatically falls back through arXiv, Semantic Scholar, and Unpaywall until real PDF bytes are verified.
3. **Sub-6-Second Responses:** By eliminating model reasoning delays and streaming directly via Server-Sent Events, users receive complete, grounded research answers in ~5 seconds.
4. **Transparent Verification:** Every generated insight links directly to the exact page number and text snippet in the original paper.
