# RESIN: Project Overview & In-Depth RAG Specification

> [!NOTE]
> This document provides a complete technical explanation of **RESIN** and the inner mechanics of its **Retrieval-Augmented Generation (RAG)** pipeline. For full sequence diagrams, mathematical formulas, and deep code-level logic, also see **[`PROJECT_DETAILS_AND_RAG.md`](PROJECT_DETAILS_AND_RAG.md)**.

---

## 1. Executive Summary

**RESIN** (Research Engine & Synthesized Intelligence Network) is an academic workstation built to bridge the gap between static research PDFs and interactive AI workflows. Rather than passively skimming lengthy scientific papers or relying on hallucination-prone generic AI chat, RESIN indexes genuine full-text academic papers into vector representations in PostgreSQL (`pgvector`), allowing users to:

- **Chat Directly with Indexed Papers:** Grounded Q&A with real-time Server-Sent Events (SSE) streaming and clickable citation pills indicating exact PDF page numbers and section headers.
- **Synthesize Multi-Paper Research:** An autonomous ReAct Research Agent that executes multi-step reasoning, cross-paper comparisons, and user library searches.
- **Overcome Publisher Paywalls:** An automated waterfall discovery engine that locates legal open-access PDFs, structured XML alternatives, or lets users directly upload personal PDFs.
- **Receive Daily Curated Research:** A scheduled microservice that harvests recent preprints and curates daily high-impact recommendations tailored to user topics.

---

## 2. System Architecture & Tech Stack

```
+-----------------------------------------------------------------------------------------+
|                                  USER WORKSTATION (FRONTEND)                            |
|                                                                                         |
|   React 18 + Vite + TypeScript + Tailwind CSS                                           |
|   - Papers Hub & Search Proxy (Semantic Scholar + OpenAlex)                             |
|   - Personal Library & Custom Folders                                                   |
|   - Interactive PaperChat Drawer (SSE Stream Reader + Page Citation Badges)             |
|   - Autonomous Research Agent Interface (Multi-turn tool-call logs)                    |
|   - "Today's Top Reads" Daily Triage Section                                            |
+------------------------------------+----------------------------------------------------+
                                     |
                                     | HTTP / SSE / REST
                                     v
+------------------------------------+----------------------------------------------------+
|                                    BACKEND SERVICES                                     |
|                                                                                         |
|   FastAPI (Python 3.11+)                                                                |
|   - /api/chat/stream: SSE real-time RAG streaming with history compaction               |
|   - /api/papers/{id}/index: Multi-source PDF discovery, parsing, chunking, embedding    |
|   - /api/papers/{id}/upload-pdf: Direct PDF upload for paywalled or institutional papers|
|   - /api/agent/stream: ReAct autonomous multi-paper literature review agent             |
|   - /api/papers/search: Aggregated academic search proxy with 403/429 fallback          |
|                                                                                         |
|   Services Layer:                                                                       |
|   - paper_resolution.py: Deterministic UUIDv5 canonical resolution                      |
|   - open_access.py: Candidate priority queue (50-120) & HTML PDF link scoring engine   |
|   - pdf.py: PyPDF in-memory parser, SSRF IP validation, diagnostic failure taxonomy     |
|   - chunking.py: Section-aware, word-overlap, page-aware TextChunker                    |
|   - embeddings.py: High-throughput single-batch Gemini 768-dim vectorizer               |
|   - retrieval.py: Cosine similarity vector search & 2-stage library search              |
|   - rag.py: Prompt formatting, intent detection, and Gemini 3.5 Flash Lite streamer    |
+------------------------------------+----------------------------------------------------+
                                     |
                                     | SQL & Stored Procedures (RPC)
                                     v
+------------------------------------+----------------------------------------------------+
|                             DATABASE & PERSISTENCE (SUPABASE)                           |
|                                                                                         |
|   PostgreSQL 15+ with pgvector Extension                                                |
|   - public.papers: Canonical paper metadata & full text                                 |
|   - public.paper_chunks: 768-dim vector chunks with physical page numbers               |
|   - public.paper_embeddings: Holistic paper-level embeddings for whole-library search   |
|   - public.users, folders, user_papers: Protected by Row Level Security (RLS)           |
|   - Stored Procedures: match_paper_chunks() & match_paper_embeddings() (IVFFlat cosine) |
+------------------------------------+----------------------------------------------------+
                                     ^
                                     | Scheduled Cron
+------------------------------------+----------------------------------------------------+
|                              DAILY TRIAGE WORKER (resin-triage)                         |
|                                                                                         |
|   Node.js (ESM) Worker: OpenAlex API -> Gemini Re-ranking -> public.daily_triage        |
+-----------------------------------------------------------------------------------------+
```

---

## 3. How the RAG System Works: Step-by-Step Breakdown

The RAG engine is the core intelligence component of RESIN. Here is exactly how an academic paper moves from an external DOI/PDF to an interactive, grounded chat stream:

### Step 1: Canonical Resolution & Ingestion Discovery
When a user clicks "Index Paper" or sends a chat message on a paper:
1. **Canonical Paper ID Resolution (`paper_resolution.py`):**
   - The paper is identified by its DOI, Semantic Scholar ID, or title.
   - If the paper does not yet exist in `public.papers`, RESIN derives a **deterministic UUIDv5** using namespace `DNS` from the identifier. This guarantees that concurrent user requests or cross-session queries never create duplicate paper entries or trigger PostgreSQL `23505` / `23503` errors.
2. **Fast Cache Check & Partial Index Guard (`GET /api/papers/{id}/index-status`):**
   - The backend checks `SELECT count(*) FROM paper_chunks WHERE paper_id = canonical_id`.
   - If `count >= 5`, the paper is already fully indexed (`is_fully_indexed: true`). The endpoint immediately returns in **~40ms**, preventing wasteful re-downloading or re-embedding.
   - **Partial Index Detection (`0 < count < 5`):** If an earlier ingestion crashed mid-embedding or suffered a network disconnect, leaving only 1–4 chunks, the backend flags `is_partial: true` and marks the recovery as `is_reindex: true`. The frontend proactively queries `/index-status` on mount and surfaces clear UI progress (*"Re-indexing paper content from source..."*) rather than silently running 10–30s ingestion inline.
3. **Ranked Candidate Priority Queue (`open_access.py`):**
   - If not indexed, the system ranks candidate sources by accessibility and speed:
     - **Priority 120 (Direct arXiv PDF):** Clean regex extraction of arXiv ID creates direct `https://arxiv.org/pdf/{arxiv_id}.pdf`. Always attempted first.
     - **Priority 100 (Europe PMC / NCBI XML):** Resolved PMC IDs point to Europe PMC open endpoints.
     - **Priority 95 (Semantic Scholar OA):** Verified `openAccessPdf.url`.
     - **Priority 90 (OpenAlex Primary Location):** `best_oa_location.pdf_url`.
     - **Priority 85 (OpenAlex Secondary Mirrors):** Institutional repositories, Zenodo, HAL.
     - **Priority 80 (Unpaywall API):** Legal institutional PDFs.
     - **Priority 65 (HTML Landing Pages):** Evaluated by the second-stage HTML PDF Button Engine.
4. **Second-Stage HTML PDF Button Engine:**
   - When an open-access URL is an HTML webpage rather than a raw PDF, BeautifulSoup scores candidate links:
     - Contains `pdf` or `download`: **+30 points**
     - Has `.pdf` extension: **+40 points**
     - Matches `cite`, `bibtex`, or `suppl`: **-40 points**
   - Downloads and verifies the highest-scoring candidate.
5. **Europe PMC Structured XML Fallback:**
   - When journal sites block automated PDF downloads with bot challenges (e.g. CloudPMC 403), RESIN fetches Europe PMC JATS XML, extracts `<abstract>`, groups direct `<body>` paragraphs into `Introduction & Results`, and parses all `<sec>` headings into **15–30 structured full-text sections**.
6. **Paywall Detection & User PDF Upload:**
   - If all automated sources encounter paywalls, RESIN **suppresses embedding** (creates 0 fake chunks) and reports the exact diagnostic reason (`PAYWALL_DETECTED`, `LOGIN_REQUIRED`, `BOT_PROTECTION`).
   - The user can click **Upload PDF** in `PaperChat` (`POST /api/papers/{id}/upload-pdf`) to supply their personal copy.

---

### Step 2: Page-Aware Text Chunking (`chunking.py`)
Once raw PDF bytes are validated (magic byte `%PDF-`), `PDFService.extract_pages(content)` extracts page texts using `PyPDF`:
- Text is processed page by page to maintain strict physical page boundaries.
- `TextChunker` executes sliding window chunking with the following parameters:
  - **Chunk Size:** 600 words (~800 tokens).
  - **Overlap Size:** 100 words (~130 tokens).
  - **Stride (Advance):** $600 - 100 = 500$ words.
  - **Minimum Chunk Size:** 100 words (discards isolated headers or blank pages).
- **Metadata Tagging:** Every chunk is stamped with:
  - `paper_id`: Canonical UUIDv5
  - `chunk_index`: Sequential order (0, 1, 2, ...)
  - `page_number`: Physical PDF page (1-indexed)
  - `section_title`: e.g. `[Methods]`, `[Results]`, or `[Page 4]`
- Each chunk's text is prefixed with `[{section_title}]\n` to inject structural semantics into the embedding space.

---

### Step 3: High-Throughput Batch Vectorization & Quota Protection (`embeddings.py`)
- **Embedding Model:** `models/gemini-embedding-001` (fallbacks: `models/text-embedding-004`, `models/embedding-001`).
- **Strict Dimension Enforcement:** Output is enforced to strictly **768 dimensions** via `output_dimensionality=768` and `_enforce_768_dims()`, matching PostgreSQL `vector(768)`.
- **Single-Call Batching:** Rather than sending chunks in small batches of 5 (which required 12 sequential HTTP calls taking 20+ seconds), RESIN sends all chunks in **1 single API request** (`batch_size = 100`):
  - 50–60 chunks vectorized in **~2.1 seconds**.
- **Fail-Fast Quota Protection:** If Gemini embedding returns a 429 quota exhaustion error, the service immediately raises `EmbeddingQuotaExceeded` without burning 10–15 seconds retrying or sub-batch cascading. The indexing endpoint returns `failure_reason="EMBEDDING_QUOTA_EXCEEDED"`, surfacing an explicit notice to the user instead of mislabeling it as a paywall.
- **Holistic Paper Embedding:** The title, abstract, and first 8,000 characters of the paper are embedded into a single document vector and stored in `public.paper_embeddings` for library-wide searching.

---

### Step 4: Storage in PostgreSQL (`pgvector`)
Chunks and vectors are batch-upserted into `public.paper_chunks` in batches of 100:
- Unique constraint `UNIQUE (paper_id, chunk_index)` prevents duplicates.
- An **IVFFlat index** with 100 lists accelerates cosine similarity calculations:
  ```sql
  CREATE INDEX paper_chunks_embedding_idx
    ON public.paper_chunks USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
  ```
- Updates `public.papers.indexed_at = now()`.

---

### Step 5: Query Vectorization, Short-Circuit & Similarity Retrieval (`retrieval.py` & `rag.py`)
When the user asks a question (*"What dataset was used?"*):
1. **Zero-Chunk Short-Circuit Guard:** If `SELECT count(*) FROM paper_chunks` returns 0, the pipeline short-circuits immediately in **~40ms**. It does NOT call `embed_query` (750ms) or `match_paper_chunks` (133ms) when no chunks exist, saving ~900ms and quota.
2. **Query Vectorization:** The query text is embedded with `task_type="retrieval_query"` -> 768-dim float vector.
3. **PostgreSQL RPC Execution:** The backend calls `match_paper_chunks`:
   - `query_embedding`: 768-dim vector
   - `match_threshold`: `0.25` (discards irrelevant noise)
   - `match_count`: `3` (in streaming) or `4` (in sync)
   - `filter_paper_id`: Canonical paper UUID
4. **Cosine Distance Formula:**
   $$\text{Distance} = \text{pc.embedding} \Leftrightarrow \text{query\_embedding}$$
   $$\text{Similarity} = 1 - (\text{pc.embedding} \Leftrightarrow \text{query\_embedding})$$
5. Returns matching rows containing `content`, `page_number`, `section_title`, and `similarity`.

---

### Step 6: Context Assembly, History Compaction & Prompt Construction (`rag.py`)
1. **Intent Detection (`detect_question_intent`):**
   - Identifies if the question is a comparison, definition, methodology request, or summary.
   - Injects tailored formatting instructions (e.g. Markdown tables for comparisons, numbered steps for procedures).
2. **Context Formatting & Snippet Capping:**
   - Assembles evidence blocks with physical page numbers:
     ```text
     Section: Methods | Page 4
     Evidence:
     We evaluated the proposed model on ImageNet-1K using standard AdamW optimizer...
     ```
   - Each evidence snippet is capped at **1,200 characters** to prevent context window bloat.
3. **Multi-Turn Conversation Compaction:**
   - In multi-turn chat, passing unbounded chat history triggers Gemini token rate limits (TPM) and creates 10–20 second response lags.
   - RESIN compacts history to the **last 2 conversation turns**.
   - Prior assistant responses are truncated to **250 characters**.
   - Keeps total prompt size under ~1,500 tokens, ensuring instant model processing.
4. **Anti-Hallucination Directives:**
   - Zero boilerplate ("Based on the provided context...").
   - Strict grounding: "If details are insufficient to answer confidently, state: 'I couldn't find enough evidence in the indexed paper to answer that confidently.'"

---

### Step 7: Low-Latency Generation, Cooldown Cache & Real-Time Streaming (`rag.py` & `api/chat.py`)
1. **Primary Chat Model:** `models/gemini-3.5-flash-lite` (fallback: `models/gemini-3.1-flash-lite`).
   - Generates tokens with an average **Time-to-First-Token (TTFT) of ~1.1 seconds**.
   - Total stream completion in ~2.5–4.0 seconds.
2. **60s Rate-Limit Cooldown Cache (`gemini_service.py`):**
   - In a naive fallback chain, when the primary model encounters a 429 or 503 error, the fallback takes over, but subsequent user questions would still try-and-fail on the primary model first, adding a wasteful 2.5–3s penalty on every request.
   - RESIN implements a global **60-second cooldown cache** (`_MODEL_COOLDOWNS`). When a model fails with 429 or 503, it is automatically marked with a 60-second cooldown via `GeminiService.mark_model_cooldown()`.
   - On all subsequent requests during the cooldown window, `GeminiService.get_prioritized_models()` skips the failing primary model and routes directly to the healthy fallback model (`gemini-3.1-flash-lite`), eliminating duplicate roundtrips and keeping latency flat at ~2.5s.
3. **FastAPI `StreamingResponse`:**
   - Streams chunks as Server-Sent Events: `data: {"text": "..."}\n\n`.
4. **Fail-Fast 429 Handling:**
   - If all upstream Gemini free-tier models are constrained, it immediately emits a clear error event rather than looping endlessly, preventing UI freezes.

---

### Step 8: Frontend Stream Consumption & Interactive Citations (`PaperChat.tsx`)
1. **Real-Time Index Status Verification:**
   - When the chat drawer opens, `PaperChat` queries `GET /api/papers/{id}/index-status`. If chunks are missing or partial, it initiates indexing and renders real-time dynamic status: *"Fetching & indexing paper from source (discovering PDF, extracting pages)..."* followed by *"Generating answer from paper chunks..."*.
2. `streamPaperRAG` in `frontend/src/lib/ragApi.ts` reads the SSE stream using a `ReadableStreamDefaultReader` and appends incoming tokens to the active assistant message in real-time.
3. Once streaming finishes, citations are rendered as interactive pills below the answer bubble:
   - Displays physical page number: `p. 4 | Section: Methods`.
   - Hover tooltip displays the exact text snippet extracted from the PDF that grounded the answer.
4. If streaming fails due to network disruption, it automatically falls back to synchronous `askPaperRAG`.

---

## 4. Key Technical Parameters Summary

| Parameter | Value | Location in Code | Purpose |
| :--- | :--- | :--- | :--- |
| **Chunk Size** | 600 words (~800 tokens) | `chunking.py:21` | Captures complete scientific arguments and context |
| **Overlap Size** | 100 words (~130 tokens) | `chunking.py:21` | Preserves cross-chunk sentence continuity |
| **Min Chunk Size** | 100 words | `chunking.py:21` | Discards blank pages, standalone headers, or noise |
| **Vector Dimensions** | 768 | `embeddings.py:95` | Matches Supabase `vector(768)` column specification |
| **Embedding Batch Size** | 100 chunks | `embeddings.py:117` | Vectorizes whole papers in a single API call (~2.1s) |
| **Similarity Threshold** | 0.25 | `retrieval.py:21` | Filters out irrelevant or low-confidence chunks |
| **Top-K Chunks** | 3 (stream) / 4 (sync) | `rag.py:109, 271` | Optimal balance between context density and speed |
| **Max Evidence Snippet**| 1,200 characters | `rag.py:58` | Prevents context window blowout |
| **History Compaction** | Last 2 turns | `rag.py:124, 290` | Eliminates 429 rate limits and 10–20s response pauses |
| **Assistant History Trim**| 250 characters | `rag.py:126, 292` | Compacts prior assistant responses |
| **Generation Model** | `gemini-3.5-flash-lite` | `rag.py:90` | Provides ultra-fast TTFT (~1.1s) without reasoning pauses |
| **Model Cooldown Cache**| 60 seconds | `gemini_service.py:25` | Skips rate-limited models directly to fallback, saving 2.5s+ per turn |
| **Min Chunks Threshold** | 5 chunks | `embed.py:137, rag.py:245` | Detects partial/stale indexes and guards against silent re-index |
| **IVFFlat Lists** | 100 lists | `full_rag_setup.sql:19` | Clusters vector space for sub-millisecond retrieval |

---

## 5. Current Limitations & Known Bottlenecks

This section outlines known limitations in the current implementation to help guide debugging and future improvements:

### 1. Document Extraction Obstacles (PyPDF)
- **Multi-Column Formatting:** Academic PDFs with 2-column layouts are parsed linearly. Paragraphs from the left and right columns can occasionally get interleaved.
- **Mathematical Formulas:** LaTeX formulas and inline math symbols are often flattened into plain ASCII or garbled strings.
- **Tables & Figures:** PyPDF cannot extract tabular structures; tables become unstructured sequences of numbers and labels.
- **Scanned / Image-Only PDFs:** Scanned photocopy papers contain no digital text stream; PyPDF returns 0 characters (requires OCR).

### 2. Retrieval Precision Constraints
- **Dense Vector Search without BM25:** Dense embeddings match concepts well, but can miss **exact technical keywords** (e.g. acronyms like `LoRA`, exact dataset names like `COCO-2017`, or specific protein identifiers).
- **No Cross-Encoder Re-Ranking:** The top 3 chunks are selected purely by cosine distance. A bi-encoder embedding compresses 600 words into a single vector, losing fine-grained cross-attention.
- **Fixed Top-K ($K=3$):** Questions requiring multi-page synthesis (*"List all datasets and baselines compared in this study"*) will miss evidence if the information spans 5+ pages.

### 3. API & Infrastructure Boundaries
- **Gemini Free-Tier Rate Limits:** 15 Requests Per Minute (RPM) and 1,000,000 Tokens Per Minute (TPM). While context compaction protects against TPM limits, automated testing or rapid follow-up queries can hit the 15 RPM ceiling.
- **Streaming Citation Metadata:** Citations are rendered after the answer finishes or mapped from initial query context. Emitting an explicit `event: citations` at stream start would enable instant pill rendering while text is typing.

---

## 6. Actionable Roadmap for Future RAG Improvements

Below is a prioritized list of concrete enhancements that can be made to the RAG pipeline:

### 🎯 High-Priority / Immediate Wins
1. **Hybrid Search (Dense Vectors + BM25 via PostgreSQL Full-Text Search):**
   - Add a `tsvector` column on `public.paper_chunks` and combine vector cosine similarity with lexical BM25 using **Reciprocal Rank Fusion (RRF)**.
   - Ensures exact keywords and acronyms always appear at the top.
2. **Streaming Citation Event via SSE:**
   - In `stream_answer`, emit an initial `metadata` event with citations before yielding text tokens:
     ```text
     event: metadata
     data: {"citations": [...]}
     ```
   - Allows the frontend to display citation pills instantly.
3. **Dynamic Top-K Selection:**
   - Use question intent: set $K=6$ for synthesis/comparison questions and $K=3$ for factoid/definition questions.

### ⚡ Medium-Priority Enhancements
4. **Neural Re-Ranking (Cross-Encoder):**
   - Retrieve top 15 chunks from `pgvector`, pass them through a lightweight re-ranker (e.g. FlashRank or Cohere Rerank API), and keep the top 3–4 for generation.
   - Significantly reduces context noise and improves answer relevance.
5. **Hierarchical / Parent-Child Chunking:**
   - Store small 200-word child chunks for vector matching, linked to 800-word parent sections. When a child matches, feed the parent chunk to the LLM.
6. **Hypothetical Document Embeddings (HyDE):**
   - Generate a 1-sentence hypothetical answer using Gemini Flash Lite, embed the hypothetical answer, and retrieve chunks using that vector.

### 🔬 Advanced Upgrades
7. **Vision / Multi-Modal Document Parsing:**
   - Replace or augment PyPDF with a layout-aware parser (e.g. **PyMuPDF4LLM**, **Nougat**, or **Marker**) to extract LaTeX formulas and Markdown tables cleanly.
8. **Corrective RAG (CRAG):**
   - If retrieved chunk similarity scores fall below 0.30, automatically trigger web search or query reformulation before generating an answer.

---

## 7. Database Security & Row Level Security (RLS)

- **`papers` & `paper_chunks`:** Shared read access across all authenticated users to eliminate redundant extraction and embedding compute.
- **`user_papers` & `folders`:** Protected by strict RLS policies ensuring users can only read, insert, or modify their own saved libraries (`auth.uid() = user_id`).
- **`daily_triage`:** RLS restricts read access to the user whose research topics generated the briefing (`user_id = auth.uid()`).
- **Service Role Key:** Used exclusively by the backend for vector upserts and administrative RPC functions.
