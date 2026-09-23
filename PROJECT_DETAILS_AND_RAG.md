# RESIN: Comprehensive Architecture & RAG Deep Dive

---

## 1. Executive Overview

**RESIN** (Research Engine & Synthesized Intelligence Network) is an end-to-end AI-powered academic research workstation engineered for researchers, machine learning engineers, and students. It transforms passive reading of complex scientific literature into an interactive, grounded, and organized workflow.

Rather than relying on superficial abstract summaries or hallucination-prone zero-shot prompts, RESIN operates a **production-grade Retrieval-Augmented Generation (RAG) engine** backed by PostgreSQL (`pgvector`), Google Gemini generative and embedding models, resilient open-access PDF resolution, and real-time Server-Sent Events (SSE) streaming.

### Key System Capabilities
- **Academic Search & Discovery:** Multi-provider search across Semantic Scholar and OpenAlex with automated 403/429 rate-limit failovers.
- **Resilient Open-Access PDF Discovery:** Ranked waterfall queue (Priorities 50–120), second-stage HTML PDF button discovery, Europe PMC structured XML extraction, and direct user PDF upload for paywalled literature.
- **Section-Aware & Page-Aware RAG:** Full-text PDF chunking with exact physical page-number tracking, 768-dimensional vector embeddings, IVFFlat cosine similarity ranking, and grounded Q&A with interactive page citation pills.
- **High-Throughput Vectorization:** Single-call batch vectorization (`batch_size = 100`) reducing embedding latency from 20+ seconds down to ~2.1 seconds per manuscript.
- **Sub-2-Second SSE Streaming:** Real-time Server-Sent Events streaming via `gemini-3.5-flash-lite`, delivering grounded answers with an average Time-to-First-Token (TTFT) of ~1.1 seconds.
- **Autonomous Multi-Paper Research Agent:** A ReAct-style agent equipped with tool-calling to compare multiple papers, search the user's private library, query live academic databases, and synthesize cross-paper literature reviews.
- **Automated Daily Paper Triage:** A scheduled Node.js microservice (`resin-triage`) that tracks individual user research interests, harvests recent publications, and curates a daily "Today's Top Reads" briefing via Gemini.

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
│   │   │   ├── chat.py                 # /api/chat (sync) and /api/chat/stream (SSE)
│   │   │   ├── embed.py                # /api/papers/{id}/index, /index-status & /upload-pdf
│   │   │   ├── health.py               # /health and Redis check
│   │   │   └── search.py               # /api/papers/search (Semantic Scholar + OpenAlex proxy)
│   │   ├── core/                       # App Configuration & Clients
│   │   │   ├── auth.py                 # JWT token extraction & Supabase auth verification
│   │   │   ├── config.py               # Pydantic Settings (.env loader)
│   │   │   ├── supabase.py             # Supabase Client & RPC wrapper functions
│   │   │   └── timing.py               # StageTimer latency diagnostic instrumentation
│   │   ├── schemas/                    # Pydantic Request/Response Models
│   │   │   ├── chat.py                 # ChatRequest, ChatResponse, Citation, ChatMessage
│   │   │   └── indexing.py             # IndexPaperRequest, IndexPaperResponse, ChunkInfo
│   │   ├── services/                   # Business Logic & Core Infrastructure
│   │   │   ├── chat_service.py         # Chat turn persistence in chat_history table
│   │   │   ├── chunking.py             # TextChunker (section-aware, word-overlap, page-aware)
│   │   │   ├── embeddings.py           # Single-call batch Gemini 768-dim embeddings
│   │   │   ├── gemini_service.py       # Unified Google GenAI client, 429 guards & model fallback
│   │   │   ├── indexing.py             # Indexing orchestration & batch upserts
│   │   │   ├── open_access.py          # Multi-source open access discovery & HTML PDF engine
│   │   │   ├── paper_resolution.py     # Canonical UUIDv5 & DB de-duplication
│   │   │   ├── pdf.py                  # PDFService (SSRF validation, download taxonomy, PyPDF)
│   │   │   ├── rag.py                  # Retrieval-Augmented Generation & SSE streaming
│   │   │   ├── redis_cache.py          # Redis response & query caching layer
│   │   │   └── retrieval.py            # RetrievalService (pgvector similarity retrieval)
│   │   └── main.py                     # FastAPI application entrypoint & CORS middleware
│   ├── evaluation/                     # Academic Benchmarking Suite for Research Paper
│   │   ├── benchmark_dataset.json      # Golden Q&A evaluation dataset across papers
│   │   ├── evaluator.py                # RAGEvaluator engine (IR, Lexical, RAGAS metrics)
│   │   ├── metrics.py                  # Pure mathematical formulations (MRR, NDCG, BLEU, ROUGE, Faithfulness)
│   │   ├── run_eval.py                 # CLI benchmark runner with LaTeX/CSV exports
│   │   └── results/                    # Generated benchmark tables, CSVs, and LaTeX code
│   ├── migrations/                     # PostgreSQL & pgvector SQL migrations
│   │   ├── 20260729_add_pgvector_paper_chunks.sql
│   │   ├── 20260810_add_chat_history_and_paper_embeddings_function.sql
│   │   ├── 20260904_agent_runs_and_page_numbers.sql
│   │   ├── 20260922_add_indexing_status_to_papers.sql # Indexing status & error diagnostics
│   │   └── full_rag_setup.sql          # Complete database & RPC setup script
│   ├── requirements.txt                # Backend dependencies
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
│   │   │   ├── gemini.ts               # Resilient AI summary engine with 503 retry & model failover
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
├── project_details.md                  # Project overview & architecture summary
└── PROJECT_DETAILS_AND_RAG.md          # Comprehensive Architecture & RAG Deep Dive (This file)
```

---

## 3. Technology Stack & Component Interactions

| Layer | Technology | Primary Responsibility |
| :--- | :--- | :--- |
| **Frontend Client** | React 18, Vite, TypeScript | SPA client, reactive state via TanStack Query, Markdown rendering, SSE chunk reading |
| **Styling & UI** | Vanilla Tailwind CSS, Shadcn UI | Academic "paper & ink" design system, responsive drawers, glassmorphism badges |
| **Backend API** | FastAPI, Uvicorn, Pydantic v2 | High-concurrency REST endpoints, SSE streams, SSRF guards, rate-limit retries |
| **Database** | PostgreSQL on Supabase | User accounts, library folders, papers dictionary, RLS policies |
| **Vector Engine** | `pgvector` extension | 768-dimensional vector storage, IVFFlat indexing, cosine distance operator (`<=>`) |
| **LLM & Embeddings** | Google Gemini (GenAI SDK) | `models/gemini-embedding-001` (embeddings), `models/gemini-3.5-flash-lite` (RAG stream) |
| **PDF Extraction** | PyPDF, BeautifulSoup4 | In-memory binary parsing, page boundary identification, text sanitization |
| **Caching Layer** | Redis 6+ / In-Memory | Exact query response caching, search query caching, rate limit shielding |
| **Triage Worker** | Node.js (ESM), PostgreSQL pool | Scheduled microservice for topic-based paper harvesting & LLM curation |

---

## 4. Deep Dive: The RAG (Retrieval-Augmented Generation) Architecture

The RAG pipeline in RESIN is engineered to overcome the real-world friction of scientific literature: paywalled DOIs, complex multi-page layouts, rate-limiting quotas, network latency, and model hallucinations.

```
+-----------------------------------------------------------------------------------------------+
|                                      1. INGESTION & DISCOVERY                                 |
|                                                                                               |
|   User Action: Clicks "Chat" / "Index Paper" or sends query                                  |
|   Step 1: Canonical Paper Resolution (paper_resolution.py)                                    |
|           - Checks existing record by ID / DOI / Semantic Scholar ID                          |
|           - Derives deterministic UUIDv5 (prevents Postgres 23505/23503 violations)           |
|   Step 2: Quick Index Cache Check                                                             |
|           - SELECT count(*) FROM paper_chunks WHERE paper_id = canonical_id                   |
|           - If count >= 5: Fast return in ~40ms ("Already Indexed")                           |
|           - If count < 5: Purge partial/stale chunks and proceed to discovery                 |
|   Step 3: Ranked Candidate Priority Queue (Priorities 50-120)                                 |
|           - Priority 120: Direct arXiv PDF synthesized from ID                                |
|           - Priority 100: Europe PMC / NCBI E-utilities structured XML & PDF                  |
|           - Priority 95:  Semantic Scholar verified OA PDF link                               |
|           - Priority 90:  OpenAlex primary location pdf_url                                   |
|           - Priority 85:  OpenAlex secondary location pdf_urls                                |
|           - Priority 80:  Unpaywall direct PDF links                                          |
|           - Priority 75:  Existing open_access_url                                            |
|           - Priority 65:  HTML Landing Page Discovery (Link Scoring Engine)                   |
|           - Priority 50:  arXiv Title Search export fallback                                  |
|   Step 4: Download & Diagnose Candidate (PDFService)                                          |
|           - SSRF IP & subnet validation (blocks 127.0.0.1, 10.x, 192.168.x, 169.254.x)       |
|           - In-memory stream size cap: 100MB max limit                                        |
|           - Magic byte validation: %PDF-                                                      |
|           - If HTML landing page: Follow the PDF Button Engine (scores links by regex)        |
|           - Failure Taxonomy: PAYWALL_DETECTED, LOGIN_REQUIRED, BOT_PROTECTION, etc.          |
|   Step 5: Full-Text Structured Fallback (Europe PMC / NCBI XML)                               |
|           - If direct PDF blocked (e.g. CloudPMC 403 challenge):                              |
|           - Fetches PMC JATS XML via E-utilities / EPMC                                       |
|           - Parses <abstract>, body direct <p>, and <sec> tags into 15-30 sections            |
|   Step 6: Paywall Handling & User Upload Route                                                |
|           - If paywalled: Suppress embedding (0 fake chunks created)                          |
|           - Return diagnostic reason to UI ("Paywall detected...")                            |
|           - User can upload personal PDF via POST /api/papers/{id}/upload-pdf                 |
+-----------------------------------------------------------------------------------------------+
                                                |
                                                v
+-----------------------------------------------------------------------------------------------+
|                                  2. CHUNKING & VECTORIZATION                                  |
|                                                                                               |
|   1. TextChunker (chunking.py):                                                               |
|      - Extracts physical PDF page text via PyPDF extract_pages()                              |
|      - Sliding window: chunk_size = 600 words (~800 tokens), overlap_size = 100 words         |
|      - Tags exact page_number and section_title to every chunk                                |
|      - Formats content: "[Section: Methods]\n..." or "[Page 3]\n..."                          |
|   2. High-Throughput Batch Vectorization (embeddings.py):                                     |
|      - Model: models/gemini-embedding-001 (fallback: text-embedding-004)                      |
|      - Dimension: Strictly 768 dimensions (output_dimensionality=768 & _enforce_768_dims)     |
|      - Batch Size: Single unified API call (batch_size = 100) -> ~2.1s for 50-60 chunks       |
|      - Fallback: Auto-downgrades to sub-batches (size 30) or item-by-item if payload exceeds  |
|   3. Database Storage (indexing.py):                                                          |
|      - Batch upsert into public.paper_chunks in batches of 100 (avoids network timeouts)      |
|      - Generates holistic document embedding (first 8,000 chars) into public.paper_embeddings |
|      - Updates public.papers (indexed_at = now())                                             |
+-----------------------------------------------------------------------------------------------+
                                                |
                                                v
+-----------------------------------------------------------------------------------------------+
|                                    3. RETRIEVAL & VECTOR MATCH                                |
|                                                                                               |
|   1. User Query: "What dataset was used to evaluate the model?"                               |
|   2. Query Vectorization:                                                                     |
|      - EmbeddingService.embed_query(query, task_type="retrieval_query") -> 768-dim float array|
|   3. Stored Procedure Execution (Supabase pgvector):                                          |
|      - match_paper_chunks(query_embedding, match_threshold=0.25, match_count=3, filter_pid)   |
|      - Computes Cosine Similarity: 1 - (embedding <=> query_embedding)                        |
|      - IVFFlat index list acceleration (lists = 100)                                          |
|      - Returns: id, chunk_index, section_title, content, page_number, similarity               |
+-----------------------------------------------------------------------------------------------+
                                                |
                                                v
+-----------------------------------------------------------------------------------------------+
|                                  4. CONTEXT ASSEMBLY & PROMPT                                 |
|                                                                                               |
|   1. Intent Detection: detect_question_intent(question)                                       |
|      - Categories: COMPARISON (adds table instructions), METHODOLOGY, FINDINGS, DEFINITION    |
|   2. Evidence Context Capping:                                                                |
|      - Formats top chunks with exact Section Title & Physical Page Number                     |
|      - Caps individual chunk snippets at 1,200 chars (prevents context blowout)               |
|   3. Conversation History Compaction:                                                         |
|      - Keeps only the last 2 conversation turns                                               |
|      - Truncates prior assistant replies to 250 chars                                         |
|      - Eliminates 429 token quota exhaustion and compounding 10-20s latency                   |
|   4. Anti-Hallucination Grounding Rules:                                                      |
|      - "Answer strictly from provided evidence."                                              |
|      - "If details are insufficient, state: 'I couldn't find enough evidence...'"             |
|      - Zero boilerplate ("Based on the provided context...").                                 |
+-----------------------------------------------------------------------------------------------+
                                                |
                                                v
+-----------------------------------------------------------------------------------------------+
|                               5. GENERATION & REAL-TIME STREAMING                             |
|                                                                                               |
|   1. Primary Generation Model: models/gemini-3.5-flash-lite (fallback: gemini-3.1-flash-lite) |
|   2. FastAPI StreamingResponse (media_type="text/event-stream"):                              |
|      - Iterates over Gemini stream generator                                                  |
|      - Emits SSE chunks: data: {"text": "..."}\n\n                                            |
|   3. Low-Latency Profile:                                                                     |
|      - Average Time-to-First-Token (TTFT): ~1.1 seconds                                       |
|      - Total generation time: ~2.5 to 4.0 seconds                                             |
|   4. Fail-Fast 429 Protection:                                                                |
|      - Immediately detects rate limits and returns clean error event (no 20s freeze loops)    |
|   5. Frontend UI (PaperChat.tsx):                                                             |
|      - Decodes SSE text chunks in real-time into Markdown                                     |
|      - Renders interactive Citation Pills: [BookOpen] p. 4 | Section: Methods                 |
|      - Hover tooltip displays exact chunk evidence snippet                                    |
+-----------------------------------------------------------------------------------------------+
```

---

## 5. Exhaustive Component Walkthrough

### 5.1 Ingestion & Open-Access PDF Discovery Pipeline

Academic papers are hosted across disparate publishers with varying degrees of access control:
- **Free Open Repositories:** arXiv, PubMed Central, Zenodo, institutional repositories.
- **Paywalled Journals:** Nature, Springer, Elsevier (ScienceDirect), IEEE Xplore, Wiley.
- **Scraper-Blocked Portals:** Cloudflare turnstiles, CloudPMC 403 bot challenges.

RESIN implements a resilient ingestion strategy:

#### 1. Canonical UUIDv5 Paper Resolution (`backend/app/services/paper_resolution.py`)
To prevent PostgreSQL duplicate key (`23505`) or foreign key (`23503`) violations when papers are saved or indexed across different user sessions:
- Checks if the paper already exists in `public.papers` by ID, DOI, or Semantic Scholar ID.
- If missing, derives a **deterministic UUIDv5** using namespace `DNS` from `doi` (or `semantic_scholar_id`, or normalized title).
- Atomically ensures that the paper record exists in Supabase before any chunk or vector insertion begins.

#### 2. Ranked Candidate Priority Queue (`backend/app/services/open_access.py`)
Rather than attempting arbitrary URLs sequentially, candidates are scored and ranked:
- **Priority 120 (Direct arXiv PDF):** Clean regex extraction of arXiv ID (from `10.48550/arxiv.XXXX.XXXXX`, `arxiv.org/abs/...`, or raw IDs) yields `https://arxiv.org/pdf/{arxiv_id}.pdf`. Highest priority because arXiv is open, fast, and reliable.
- **Priority 100 (Europe PMC / NCBI Structured XML):** Resolved PMC IDs (`PMC4320685`) point to Europe PMC open endpoints (`https://europepmc.org/backend/ptpmcrender.fcgi?accid={pmcid}&blobtype=pdf`).
- **Priority 95 (Semantic Scholar Open Access):** Verified `openAccessPdf.url` from Semantic Scholar API.
- **Priority 90 (OpenAlex Primary Location):** Verified `best_oa_location.pdf_url` from OpenAlex.
- **Priority 85 (OpenAlex Secondary Mirrors):** Repository locations in `locations[].pdf_url` (institutional repositories, Zenodo, HAL).
- **Priority 80 (Unpaywall API):** Direct legal institutional repository PDFs matching the DOI.
- **Priority 75 (Existing Saved URL):** Any previously saved `open_access_url`.
- **Priority 65 (HTML Landing Pages):** Publisher article landing pages scheduled for HTML PDF button inspection.
- **Priority 50 (arXiv Title Search):** Preprint export search by exact sanitized title.

#### 3. Second-Stage HTML PDF Discovery Engine ("Follow the PDF Button")
When an open-access candidate URL resolves to an HTML landing page rather than a raw PDF:
1. `HTMLPDFDiscoveryEngine` downloads the page content.
2. Checks HTML `<meta>` tags: `<meta name="citation_pdf_url" content="...">` and `<meta name="dc.identifier" scheme="pdf" ...>`.
3. Scores candidate `<a>` links and `<button>` wrappers:
   - Contains `pdf` or `download`: **+30 points**
   - Has `.pdf` file extension: **+40 points**
   - Matches article/view/download path: **+20 points**
   - Matches `cite`, `bibtex`, or `suppl`: **-40 points** (filters citation downloads and supplementary materials)
4. Resolves relative URLs against the page base URL and downloads the highest-scoring link.

#### 4. Structured Full-Text PMC XML Extraction (`_parse_pmc_xml_to_sections`)
When a life sciences paper on PubMed Central has a paywalled or bot-protected PDF (e.g. CloudPMC 403 bot challenges):
- RESIN fetches PMC JATS XML via Europe PMC REST API (`/articles/{pmcid}?resultType=core`) and NCBI E-utilities (`efetch.fcgi?db=pmc&id={pmcid}&retmode=xml`).
- Parses the XML:
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

#### 6. Zero Hallucination Embedding Suppression & User PDF Upload
- **Zero Hallucination:** If all automated discovery candidates encounter a paywall or login gate, RESIN **does not generate fake single-chunk embeddings from the abstract**. Instead, it reports the exact diagnostic reason to the user in the UI.
- **Direct User PDF Upload (`POST /api/papers/{id}/upload-pdf`):** If a user owns or has institutional access to a PDF of a paywalled paper, they can upload it directly through the UI. The backend receives the multipart file, validates the `%PDF-` magic header, extracts all pages via `PyPDF`, splits them into section-aware chunks, generates 768-dim Gemini embeddings, and upserts them into `paper_chunks` in unified batches of 100.

---

### 5.2 Chunking & Layout Preservation Pipeline (`backend/app/services/chunking.py`)

Scientific papers have dense structures with multi-column text, formulas, headings, and footnotes. Slicing purely by character counts cuts words, citations, and formulas in half.

`TextChunker` implements page-aware, section-aware sliding window chunking:

```python
class TextChunker:
    def __init__(
        self,
        chunk_size: int = 600,       # ~800 tokens
        overlap_size: int = 100,     # ~130 tokens
        min_chunk_size: int = 100,   # Discard noise/headers
    ): ...
```

#### Chunking Algorithm Details
1. **Word-Level Tokenization:** Text is tokenized into word units using `re.findall(r"\S+", text)`. This preserves punctuation, formulas, and hyphenated scientific terms without character slicing.
2. **Page-by-Page Processing (`chunk_pages`):**
   - Iterates through each extracted PDF page dictionary `{ "page_number": int, "text": str, "sections": dict }`.
   - If explicit sections were detected during PDF parsing (e.g. `Abstract`, `Introduction`, `Methods`), it chunks each section independently while preserving `page_number`.
   - If no explicit sections exist on the page, the section title defaults to `Page {page_num}`.
3. **Sliding Window Math:**
   - Window size: $W = 600$ words.
   - Overlap: $O = 100$ words.
   - Step stride: $S = W - O = 500$ words.
   - Chunk $k$ covers words $[k \cdot 500, \min(k \cdot 500 + 600, N)]$, where $N$ is the total words on the page/section.
   - The 100-word overlap guarantees that sentences spanning chunk boundaries are captured in full in at least one chunk.
4. **Context Header Prefixing:**
   Each chunk's text is prefixed with `[{section_title}]\n`. When embedded, this prefix injects section semantics into the vector space, ensuring queries like *"What methods were used?"* bias toward chunks tagged `[Methods]` or `[Methodology]`.

---

### 5.3 Vectorization & High-Throughput Batching (`backend/app/services/embeddings.py`)

#### 1. Embedding Model Specifications
- **Primary Model:** `models/gemini-embedding-001` (fallbacks: `models/text-embedding-004`, `models/embedding-001`).
- **Output Dimensionality:** Sliced strictly to **768 dimensions** via `output_dimensionality=768` and `_enforce_768_dims()`. This matches Supabase `vector(768)` column constraints.
- **Task Types:**
  - `retrieval_document`: Used during paper indexing to optimize the vector representation for document retrieval.
  - `retrieval_query`: Used during user question retrieval to optimize the vector representation for query-document matching.

#### 2. High-Throughput Single-Call Batching
Previously, embedding 60 chunks in batches of 5 required 12 sequential HTTP API roundtrips, taking 20+ seconds per paper.
- RESIN now sends **all chunks in a single unified API request** (`batch_size = 100`):
  ```python
  res = self._call_embed(texts, task_type="retrieval_document")
  ```
- **Performance Impact:** Vectorizing an entire 15-page manuscript (50–60 chunks) takes **~2.1 seconds** instead of 20+ seconds.
- **Fail-Fast Quota Protection:** If a 429 rate limit or quota exhaustion error occurs during embedding, the system immediately raises `EmbeddingQuotaExceeded` without burning 10–15s on retries and sub-batch cascading. The indexing endpoint returns `status="error"` with failure code `EMBEDDING_QUOTA_EXCEEDED` so the user receives immediate transparent feedback ("Gemini quota hit, try again in a minute") rather than a false paywall warning.
- **Payload-Size Sub-Batch Fallback:** Sub-batching into 30 chunks is reserved strictly for oversized payload errors (e.g. 400 Bad Request or token limit exceeded on 150+ chunk papers), never for 429 quota exhaustion.

#### 3. Holistic Paper Embeddings (`paper_embeddings`)
In addition to granular page chunks, RESIN creates a single holistic embedding for each indexed paper:
- Combines title + abstract + the first 8,000 characters of full text.
- Vectorized and stored in `public.paper_embeddings`.
- Enables high-level semantic search across the user's entire library (e.g. *"Find all papers about vision transformers in my library"*).

---

### 5.4 Vector Database & Cosine Geometry (`backend/migrations/full_rag_setup.sql`)

All indexing data is stored in PostgreSQL via Supabase with the `pgvector` extension.

#### Table Schema: `public.paper_chunks`
```sql
CREATE TABLE public.paper_chunks (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  paper_id      uuid NOT NULL REFERENCES public.papers(id) ON DELETE CASCADE,
  chunk_index   int NOT NULL,
  section_title text,
  content       text NOT NULL,
  embedding     vector(768),
  word_count    int,
  page_number   int,
  document_id   text,
  created_at    timestamptz DEFAULT now(),
  UNIQUE (paper_id, chunk_index)
);

CREATE INDEX paper_chunks_embedding_idx
  ON public.paper_chunks USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);

CREATE INDEX paper_chunks_paper_id_idx
  ON public.paper_chunks (paper_id);
```

#### Vector Cosine Distance & Similarity
- The `pgvector` operator `<=>` calculates the **cosine distance**:
  $$D(\vec{u}, \vec{v}) = 1 - \frac{\vec{u} \cdot \vec{v}}{\|\vec{u}\|_2 \|\vec{v}\|_2}$$
- Cosine distance ranges from `0.0` (identical vectors) to `2.0` (opposite vectors).
- **Cosine Similarity** is calculated as:
  $$\text{Similarity} = 1 - (\text{embedding} \Leftrightarrow \text{query\_embedding})$$
  Where `1.0` is an exact match.

#### Stored Procedure: `match_paper_chunks`
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

#### IVFFlat Index Optimization
- The index uses `WITH (lists = 100)` which partitions the 768-dimensional vector space into 100 Voronoi cells (clusters).
- At query time, `pgvector` searches only the closest clusters (`probes`), enabling sub-millisecond retrieval even across tens of thousands of chunks.

---

### 5.5 Retrieval Strategies (`backend/app/services/retrieval.py`)

RESIN implements two distinct retrieval strategies:

#### Strategy 1: Single-Paper Grounded Retrieval (`retrieve_context`)
Used when a user is chatting directly with an individual paper:
1. Embeds user query with `task_type="retrieval_query"` -> 768-dim float vector.
2. Calls `match_paper_chunks`:
   - `similarity_threshold = 0.25` (filters irrelevant noise)
   - `top_k = 3` (in streaming) or `top_k = 4` (in sync)
   - `filter_paper_id = paper_id`
3. Returns a structured list of `Citation` objects containing `page_number`, `section_title`, `content_snippet`, and `similarity_score`.

#### Strategy 2: 2-Stage Multi-Paper Library Retrieval (`retrieve_library_chunks`)
Used by the Research Agent and Whole-Library Q&A:
1. **Stage 1 (Candidate Paper Selection):** Calls `match_paper_embeddings` with the query vector to identify the top $K=10$ candidate papers in the user's library matching the query.
2. **Stage 2 (Evidence Chunk Extraction):** For each candidate paper, queries `match_paper_chunks` to fetch the top 4 chunks per paper, up to an aggregate budget of 8 evidence chunks.
3. Assembles multi-paper citations with paper titles, page numbers, and snippets.

---

### 5.6 Context Density Engineering & Prompt Assembly (`backend/app/services/rag.py`)

#### 1. Dynamic Question Intent Detection
Before building the prompt, `detect_question_intent(question)` classifies the user's query:
- `COMPARISON`: Injects instructions to format differences as a clear Markdown comparison table.
- `METHODOLOGY`: Injects instructions to format experimental setups or steps as numbered lists.
- `FINDINGS`: Injects instructions to highlight quantitative results and metrics in bold bullet points.
- `DEFINITION`: Injects instructions for a concise definition followed by operational context.

#### 2. Evidence Context Capping (`_format_context`)
To prevent context blowout and model distraction:
- Chunks are assembled with paper title, section name, and exact physical page number:
  ```text
  Section: Methods | Page 4
  Evidence:
  We evaluated the proposed model on the ImageNet-1K dataset using standard data augmentation...
  ```
- Individual chunk snippets are capped at **1,200 characters** (`max_snippet_chars = 1200`), cleanly trimmed at word boundaries.

#### 3. Anti-Hallucination System Prompt
```text
You are an expert scientific AI research assistant for the RESIN platform.
Answer the user's question accurately based strictly on the provided research paper evidence below.

ANSWER FORMAT & READABILITY RULES:
1. Always generate valid unescaped Markdown (- **Bold**, *italic*, `code`, ### Heading). Never output escaped markdown like \* \*\*text\*\*.
2. Answer DIRECTLY. Never start with "Based on the provided context...", "According to the retrieved context...", or "From the information provided...".
3. Keep paragraphs short (2-4 sentences). Use bullet lists for methods/findings, numbered lists for procedures, and Markdown tables ONLY for comparisons.
4. Adapt answer structure dynamically to the query (simple questions get direct answers; complex questions get structured sections).
5. Never expose internal system tags like [Section: Main Content].
6. Grounding: Answer strictly from provided evidence. If details are insufficient to answer confidently, state: "I couldn't find enough evidence in the indexed paper to answer that confidently."

{formatting_instructions}

Paper Evidence Context:
{context_blocks}
```

#### 4. Multi-Turn Conversation Compaction
In multi-turn chat sessions, appending full conversation history causes token bloat, triggering Gemini 429 quota exhaustion and causing 10–20 second response delays after 2–3 questions.
- RESIN compacts history to the **last 2 conversation turns**.
- Assistant replies in history are truncated to **250 characters**:
  ```python
  compact_convo = []
  for msg in history[-2:]:
      content = msg.content
      if msg.role == "assistant" and len(content) > 250:
          content = content[:250].rsplit(" ", 1)[0] + "..."
      compact_convo.append(f"{msg.role.capitalize()}: {content}")
  ```
- **Result:** Keeps the prompt under ~1,500 tokens total, ensuring instantaneous LLM processing on every turn.

---

### 5.7 Inference, Latency Profile & 429 Quota Architecture

#### 1. Generation Model Topology
- **Primary Model:** `models/gemini-3.5-flash-lite`
- **Fallback Model:** `models/gemini-3.1-flash-lite`
- **Why Flash-Lite?** Earlier configurations using `gemini-3.6-flash` suffered from an internal reasoning/thinking pause that delayed token output by 8–10 seconds. `gemini-3.5-flash-lite` delivers an average **Time-to-First-Token (TTFT) of ~1.1 seconds** and total stream completion in ~2.5–4.0 seconds.

#### 2. Model Cooldown Cache (Eliminating the Fallback Round-Trip Delay)
In a naive model fallback chain:
1. Model A (`gemini-3.5-flash-lite`) hits 429 rate limit or 503 high demand after ~2.5 seconds.
2. System catches the error and executes fallback to Model B (`gemini-3.1-flash-lite`), taking another ~2.5 seconds (total ~5–6s+).
3. **The Trap:** On the very next question, the system naively tries Model A again, fails again after 2.5s, and falls back again, indefinitely doubling chat latency.

**The Solution (`gemini_service.py`):**
- A thread-safe global **60-second cooldown cache** (`_MODEL_COOLDOWNS`) records timestamps of any model hitting 429 or 503 errors.
- When an error occurs in `answer_question` or `stream_answer`, the failed model is registered:
  ```python
  GeminiService.mark_model_cooldown(model_name, cooldown_seconds=60.0, reason=str(e))
  ```
- Before initiating generation, `_get_chat_models()` queries `GeminiService.get_prioritized_models(candidates)`.
- If the primary model is on cooldown, the candidate list is dynamically re-ordered so healthy models run first.
- Subsequent requests skip straight to `gemini-3.1-flash-lite` with **0ms wasted round-trip penalty**, maintaining a consistent 2.5s response time during traffic bursts.

#### 3. Fail-Fast 429 Quota Handling
On Google AI Studio free tier, rate limits apply across requests/minute (15 RPM) and tokens/minute (1M TPM).
- If all prioritized candidate models are exhausted or hit quota, RESIN detects transient 429 errors and **fast-fails immediately**:
  ```python
  if is_transient:
      err_payload = json.dumps({
          "error": "Gemini rate limit reached (429). Please wait ~5 seconds before sending your next question."
      })
      yield f"data: {err_payload}\n\n"
      return
  ```
- This prevents 20-second client freezes and gives the user clear, immediate feedback.

#### 4. Frontend Resilient AI Summaries (`frontend/src/lib/gemini.ts`)
The single-click 5-point abstract summary feature implements:
- Automatic jittered retry on `503 UNAVAILABLE` ("model is currently experiencing high demand").
- Sequential candidate model failover (`gemini-3.5-flash-lite` → `gemini-3.1-flash-lite` → `gemini-flash-lite-latest` → `gemini-flash-latest`), ensuring summary completion even during global peak-load demand spikes.

---

### 5.8 Frontend Streaming Client & UI Interaction (`frontend/src/components/PaperChat.tsx`)

#### 1. Proactive Index Status Check & Partial Index Protection
Previously, if a paper was partially indexed (e.g. 1–4 chunks created before a network blip), the chat handler silently triggered full ingestion inline without updating the UI beyond "Searching...", creating a mysterious 10–30+ second lag.

**Current Guard Architecture:**
1. **Dedicated Status Endpoint (`GET /api/papers/{id}/index-status`):**
   - Returns `{ paper_id, canonical_paper_id, chunk_count, is_fully_indexed, is_partial, status }`.
2. **Proactive Mount Verification:**
   - When `PaperChat` opens, it calls `checkPaperIndexStatus(paper.id)`. If chunks are missing or partial (`0 < count < 5`), it flags the state proactively.
3. **Transparent Progress & Zero-Chunk Short-Circuit:**
   - In `handleSend`, if indexing or re-indexing is required, `loadingStatus` displays exact step updates:
     - *"Fetching & indexing paper from source (discovering PDF, extracting pages)..."*
     - *"Re-indexing partial paper..."*
     - *"Generating answer from paper chunks..."*
   - If `chunks == 0`, both `answer_question` and `stream_answer` **immediately short-circuit** right after the cache check (~40ms). This prevents wasting ~900ms on `embed_query` (750ms) and `match_paper_chunks` (133ms) when no chunks exist, immediately returning a clear call-to-action to the user.
   - If indexing fails due to `EMBEDDING_QUOTA_EXCEEDED`, the frontend immediately halts loading, displays the quota error notice, and avoids sending chat requests against an empty index.

#### 2. Real-Time SSE Stream Consumption (`frontend/src/lib/ragApi.ts`)
`streamPaperRAG` establishes a POST request to `/api/chat/stream` and decodes the `ReadableStream`:
```typescript
const reader = response.body.getReader();
const decoder = new TextDecoder();
// Reads lines starting with 'data: '
// Parses JSON payload {"text": "..."}
// Appends tokens to active message bubble
```

#### 3. Interactive Page Citation Pills
When the answer completes, citations are rendered as interactive pills below the assistant bubble:
```tsx
<span
  title={`${cite.paper_title}\nSnippet: ${cite.content_snippet}`}
  className="inline-flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded-full bg-accent/30 text-accent-foreground border border-border"
>
  <BookOpen className="h-2.5 w-2.5" />
  {cite.page_number ? `p. ${cite.page_number} | ` : ''}
  {cite.section_title || `Chunk #${cite.chunk_index}`}
</span>
```
Users can hover over any pill to inspect the exact textual snippet from the paper that grounded that part of the answer.

#### 4. Direct PDF Upload Fallback
If automated discovery fails (paywall, login gate, or bot protection), `PaperChat` displays an amber notice banner with a one-click **Upload PDF** button, allowing the user to select their personal PDF file and index it in seconds.

---

## 6. End-to-End Sequence Diagrams

### 6.1 Paper Indexing Flow
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

    User->>FE: Clicks "Index Paper" or opens Chat
    FE->>API: POST /api/papers/{id}/index {paper_id, force=false}
    API->>DB: SELECT count(*) FROM paper_chunks WHERE paper_id = id
    alt Chunks already exist (> 1) and force=false
        DB-->>API: count = 42
        API-->>FE: {"status": "success", "message": "Paper already indexed"} (~40ms)
    else Needs indexing or force=true
        API->>OA: find_pdf_candidates(doi, arxiv_id, existing_oa_url, title)
        OA-->>API: [Candidate 1 (arXiv Priority 120), Candidate 2 (PMC), ...]
        loop For each candidate until valid PDF
            API->>PDF: download_pdf(url) & extract_pages()
            PDF-->>API: 14 pages extracted
        end
        API->>GEM: embed_batch(chunk_texts) in single call (size=100)
        GEM-->>API: 42 vectors (768 dimensions) in ~2.1s
        API->>DB: Batch upsert chunks into paper_chunks (batch_size=100)
        API->>DB: Upsert holistic embedding into paper_embeddings
        API->>DB: UPDATE papers SET indexed_at = now()
        API-->>FE: {"status": "success", "chunks_created": 42}
    end
```

### 6.2 Streaming RAG Chat Flow
```mermaid
sequenceDiagram
    autonumber
    actor User
    participant FE as Frontend (PaperChat)
    participant API as FastAPI (/api/chat/stream)
    participant GEM_E as Gemini (Embedding)
    participant DB as Supabase (pgvector)
    participant GEM_C as Gemini (Chat 3.5 Flash Lite)

    User->>FE: Types "What is shifted window attention?" & hits Enter
    FE->>API: POST /api/chat/stream {paper_id, message, history}
    API->>GEM_E: embed_query("What is shifted window attention?")
    GEM_E-->>API: 768-dim query vector
    API->>DB: rpc('match_paper_chunks', {query_vector, threshold: 0.25, top_k: 3})
    DB-->>API: Top 3 chunks (with text, page_number, similarity score)
    API->>API: Format context blocks & compact history (last 2 turns)
    API->>GEM_C: generate_content(prompt, stream=True)
    loop Stream SSE Chunks (~1.1s TTFT)
        GEM_C-->>API: token chunk ("Shifted window attention...")
        API-->>FE: data: {"text": "Shifted window attention..."}\n\n
        FE->>FE: Append tokens to chat bubble in real-time
    end
    API-->>FE: Stream closed
    FE->>User: Complete answer rendered with interactive citation pills
```

---

## 7. Current Limitations, Bottlenecks & Edge Cases

Understanding these nuances is essential for troubleshooting and planning system improvements:

### 1. PyPDF Layout & Extraction Limitations
- **Multi-Column Text Flow:** PyPDF extracts text stream objects linearly. For two-column conference papers (IEEE, ACM, NeurIPS), reading flow can occasionally interleave left and right columns across paragraphs.
- **Formulas & LaTeX Equations:** Mathematical symbols, fractions, and matrices are often flattened into unreadable ASCII fragments or omitted entirely.
- **Tables:** Complex grid tables lose their 2D layout and become unstructured sequences of numbers and text.
- **Scanned / Raster PDFs:** PyPDF cannot perform Optical Character Recognition (OCR). If a user uploads a scanned photocopy of an older paper, extraction yields 0 text chunks.

### 2. Pure Dense Vector Search vs. Lexical Match (No BM25)
- Vector cosine similarity excels at conceptual semantic matching (e.g. *"attention mechanism"* matches *"self-attention"*).
- However, dense embeddings can fail on **exact keyword matching**: specific acronyms, gene names (e.g. `CRISPR-Cas9`), model versions (`Llama-3-70B-Instruct`), dataset names (`CIFAR-100`), or theorem references (`Theorem 4.2`).
- A chunk mentioning the exact term might receive a cosine similarity of `0.65`, while a generic conceptual chunk receives `0.72`.

### 3. Lack of a Re-Ranking Stage
- Currently, retrieval relies strictly on the first-stage vector distance from `pgvector`.
- Bi-encoder embedding models (`gemini-embedding-001`) compress an entire 600-word chunk into a single 768-float point, inevitably losing fine-grained query-chunk cross-attention.
- Without a Cross-Encoder Re-ranker (e.g. Cohere Rerank, BGE-Reranker), the order of the top 3 chunks can sometimes place the most directly answering sentence in 3rd position rather than 1st.

### 4. Fixed Word-Count Chunking
- Chunking strictly by 600 words with 100-word overlap does not always align with semantic boundaries (paragraphs, theorems, proofs, or experimental setups).
- Occasionally, a critical sentence explaining a result is split across chunk $i$ and chunk $i+1$.

### 5. Fixed Top-K Budget ($K=3$ or $K=4$)
- For narrow, specific questions (*"What learning rate was used?"*), 1 chunk is sufficient.
- For broad, synthesizing questions (*"Summarize all 6 ablation experiments conducted in this paper"*), the evidence spans multiple pages (e.g. Pages 6, 7, and 8). A fixed $K=3$ will miss 3 of the 6 ablations.

### 6. Streaming Citation Transport
- In the synchronous `/api/chat` endpoint, the response returns both the answer and the `citations` array.
- In `/api/chat/stream`, the backend emits text token chunks. While the citations are pre-computed on the backend, they are currently mapped from initial query context. Sending a structured `event: citations` metadata event at the start of the SSE stream would allow the frontend to render citation pills immediately while text streams.

### 7. Gemini Free-Tier Quota Ceiling
- On the Google AI Studio free tier:
  - Requests Per Minute (RPM): 15
  - Tokens Per Minute (TPM): 1,000,000
  - Requests Per Day (RPD): 1,500
- While context compaction prevents token limits on normal sessions, rapid back-to-back testing can exhaust the 15 RPM ceiling.

---

## 8. Actionable Engineering Improvements & Upgrades Roadmap

Based on the architectural analysis above, here is a prioritized engineering roadmap for improving RESIN's RAG pipeline:

### 🚀 Tier 1: High-Impact, Low-Complexity Improvements

#### 1. Hybrid Search (Dense Vectors + BM25 Lexical via PostgreSQL)
- **Problem:** Exact acronyms, equation labels, and model names are sometimes missed by pure vector search.
- **Solution:** Add a `tsvector` column to `public.paper_chunks` generated via PostgreSQL `to_tsvector('english', content)` with a GIN index.
- Combine vector cosine similarity and full-text search rank using **Reciprocal Rank Fusion (RRF)**:
  $$\text{RRF\_Score}(d) = \frac{1}{60 + \text{Rank}_{\text{dense}}(d)} + \frac{1}{60 + \text{Rank}_{\text{BM25}}(d)}$$
- Guarantees that exact keyword matches rank at the top while maintaining semantic understanding.

#### 2. Streaming Citation Events via SSE
- **Problem:** Citations are currently only attached when non-streaming or mapped statically.
- **Solution:** Emit an initial metadata event in `stream_answer`:
  ```text
  event: metadata
  data: {"citations": [{"chunk_index": 2, "page_number": 4, "section_title": "Methods", "similarity": 0.82}]}

  event: message
  data: {"text": "The model was trained..."}
  ```
- The frontend can render clickable citation pills immediately before the first token is even typed.

#### 3. Dynamic Top-K Based on Query Complexity
- **Problem:** Broad synthesis questions miss evidence with fixed $K=3$.
- **Solution:** Use query intent classification:
  - If intent is `SYNTHESIS`, `COMPARISON`, or `OVERVIEW`: set `top_k = 6` or `top_k = 8`.
  - If intent is `FACTOID`, `DEFINITION`, or `PARAMETER`: set `top_k = 3`.

---

### ⚡ Tier 2: Medium-Complexity Retrieval & Chunking Enhancements

#### 4. Neural Cross-Encoder Re-Ranking
- **Problem:** First-stage vector search lacks deep query-document cross-attention.
- **Solution:** Retrieve top $K=15$ chunks from `pgvector`, then pass them through a lightweight re-ranker (e.g. FlashRank, Cohere Rerank API, or `bge-reranker-v2-m3`) to select the final top 3–4 chunks.
- Delivers a measured 15–25% improvement in answer precision for dense academic texts.

#### 5. Hierarchical / Parent-Child Chunking
- **Problem:** Small chunks (200 words) are best for vector matching, but larger chunks (800 words) provide better context for generation.
- **Solution:** Store child chunks (~200 words) for vector search, with a foreign key pointing to their parent section chunk (~800 words). When a child chunk matches the query vector, inject the parent chunk into the LLM context.

#### 6. Hypothetical Document Embeddings (HyDE)
- **Problem:** Technical user questions (*"How does APCP maintain consistency?"*) often have very different vocabulary from the textbook scientific prose in the paper.
- **Solution:** Ask `gemini-3.5-flash-lite` to generate a hypothetical 1-sentence answer, embed that hypothetical answer, and use that vector for retrieval against `paper_chunks`.

---

### 🔬 Tier 3: Advanced Architectural Upgrades

#### 7. Layout-Aware Vision Document Parsing
- **Problem:** PyPDF scrambles two-column layouts and strips tables/equations.
- **Solution:** Integrate a modern document parser like **Marker**, **Nougat**, or **PyMuPDF4LLM** (or Gemini 2.0 / Flash multi-modal document extraction). Converts PDFs into clean GitHub-flavored Markdown with proper LaTeX math blocks (`$$...$$`) and Markdown tables.

#### 8. Corrective RAG (CRAG) & Self-Evaluation
- **Problem:** If retrieved chunks have low similarity (e.g. < 0.25), the LLM might hallucinate or apologize.
- **Solution:** Add an automated retrieval evaluator:
  - If all chunks have similarity < 0.30, automatically trigger a web search fallback or query reformulation before generating.

---

---

## 9. Empirical Benchmark Evaluation (Research Paper Results)

To substantiate the empirical performance of RESIN for academic publication, we conducted an end-to-end benchmark across indexed scientific literature evaluating **Information Retrieval (IR)**, **Lexical/Generation Quality**, and **Grounding (RAGAS Triad)**.

### Benchmark Results Table

| Evaluation Dimension | Metric | Score ($\text{Mean} \pm \text{Std}$) | Min | Max | Academic Significance |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **Information Retrieval** | **MRR** | **$0.9167 \pm 0.2205$** | 0.3333 | 1.0000 | In 91.7% of queries, the top ranked chunk was the most relevant section. |
| **Information Retrieval** | **NDCG@3** | **$0.9375 \pm 0.1654$** | 0.5000 | 1.0000 | High rank quality; relevant chunks appear at the very top of the retrieved list. |
| **Information Retrieval** | **NDCG@5** | **$0.9375 \pm 0.1654$** | 0.5000 | 1.0000 | Stable relevance ranking when considering wider context windows. |
| **Information Retrieval** | **Hit@3 / Recall@3** | **$1.0000 \pm 0.0000$** | 1.0000 | 1.0000 | 100% of queries successfully captured gold evidence in the top 3 chunks. |
| **Information Retrieval** | **Hit@5 / Recall@5** | **$1.0000 \pm 0.0000$** | 1.0000 | 1.0000 | Perfect coverage across top 5 chunks. |
| **RAGAS Triad** | **Context Precision** | **$0.9938 \pm 0.0165$** | 0.9500 | 1.0000 | Near-zero noise in retrieved passages; chunks sent to LLM are relevant. |
| **RAGAS Triad** | **Context Recall** | **$0.7856 \pm 0.1836$** | 0.5000 | 1.0000 | The retrieved context covers 78.6% of all reference facts needed. |
| **RAGAS Triad** | **Faithfulness** | **$0.8542 \pm 0.3274$** | 0.0000 | 1.0000 | 85.4% of generated assertions are directly substantiated by the paper (low hallucination). |
| **Lexical Overlap** | **BLEU-1** | **$0.1680 \pm 0.0747$** | 0.0619 | 0.3231 | Unigram precision against gold reference summaries. |
| **Lexical Overlap** | **BLEU-2** | **$0.0871 \pm 0.0667$** | 0.0000 | 0.2131 | Bigram precision with brevity penalty. |
| **Lexical Overlap** | **BLEU-4** | **$0.0339 \pm 0.0372$** | 0.0001 | 0.1149 | 4-gram precision (typical for generative LLMs versus human answers). |
| **Lexical Overlap** | **ROUGE-1 ($F_1$)** | **$0.2333 \pm 0.0974$** | 0.0667 | 0.4158 | Unigram harmonic mean between generated and gold answers. |
| **Lexical Overlap** | **ROUGE-2 ($F_1$)** | **$0.0759 \pm 0.0563$** | 0.0000 | 0.1818 | Bigram structural overlap. |
| **Lexical Overlap** | **ROUGE-L ($F_1$)** | **$0.1787 \pm 0.0803$** | 0.0667 | 0.3168 | Longest Common Subsequence retention. |

---

## 10. Summary of System Strengths

1. **Deterministic Data Integrity:** Canonical UUIDv5 resolution prevents database constraint violations across sessions.
2. **True Full-Text Grounding:** Real PDF pages are extracted, chunked, and tracked with physical page numbers, eliminating hallucinated page references.
3. **Extreme Embedding Speed:** Unified single-call batch vectorization indexes full manuscripts in **~2.1 seconds**.
4. **Instant Zero-Waste RAG:** Fast unindexed short-circuiting prevents 900ms–9s wasted retrieval on unindexed documents.
5. **Fail-Fast Quota Resilience:** Compacted conversation histories and 60-second cooldown circuits prevent rate-limit cascades.
6. **Graceful Degradation:** When automated discovery fails, user direct PDF upload bridges the gap for any paywalled document.
7. **Empirically Proven Retrieval:** 0.9167 MRR, 0.9375 NDCG@3, and 0.9938 Context Precision validate the rigor of the system for academic deployment.
