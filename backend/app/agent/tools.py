import asyncio
import logging
import threading
from typing import Any, Dict, List, Optional
from app.core.supabase import get_supabase_client
from app.services.background_jobs import JobStatus, background_job_service
from app.services.indexing import IndexingService
from app.services.open_access import OpenAccessService
from app.services.pdf import PDFExtractionError, PDFService, SSRFValidationError
from app.services.retrieval import RetrievalService

logger = logging.getLogger(__name__)

pdf_service = PDFService()
open_access_service = OpenAccessService()
indexing_service = IndexingService()
retrieval_service = RetrievalService()


# ---------------------------------------------------------------------------
# Background Processing Worker
# ---------------------------------------------------------------------------
def _run_async_ingestion(job_id: str, paper_id: str, pdf_url: str, user_id: str):
    """Worker thread running complete PDF ingestion pipeline asynchronously."""
    supabase = get_supabase_client()
    try:
        # Step 1: Download & validate PDF
        background_job_service.update_job(job_id, JobStatus.DOWNLOADING, "Downloading PDF with SSRF protection...")
        pdf_bytes, sha256_hash = pdf_service.download_pdf(pdf_url)

        # Step 2: Extract text & page numbers
        background_job_service.update_job(job_id, JobStatus.EXTRACTING, "Extracting text and section headers page-by-page...")
        pages_data = pdf_service.extract_pages(pdf_bytes)

        if not pages_data:
            background_job_service.update_job(job_id, JobStatus.FAILED, error="No readable text extracted from PDF.")
            return

        # Step 3: Chunk text page-by-page
        background_job_service.update_job(job_id, JobStatus.CHUNKING, "Splitting pages into section-aware text chunks...")
        
        # Step 4: Embed & index into pgvector
        background_job_service.update_job(job_id, JobStatus.EMBEDDING, "Generating 768-dim embeddings via Gemini text-embedding-004...")
        background_job_service.update_job(job_id, JobStatus.INDEXING, "Indexing chunks into PostgreSQL pgvector...")

        index_res = indexing_service.index_pdf_pages(
            paper_id=paper_id,
            pages_data=pages_data,
            document_id=sha256_hash,
        )

        # Step 5: Link paper to user_papers if supabase is configured
        if supabase:
            try:
                supabase.table("user_papers").upsert(
                    {
                        "user_id": user_id,
                        "paper_id": paper_id,
                        "status": "in_progress",
                    },
                    on_conflict="user_id,paper_id",
                ).execute()
            except Exception as e:
                logger.warning(f"Could not update user_papers for {user_id}: {e}")

        if index_res.status == "error":
            background_job_service.update_job(job_id, JobStatus.FAILED, error=index_res.message)
        else:
            background_job_service.update_job(
                job_id,
                JobStatus.COMPLETED,
                f"Successfully indexed {index_res.chunks_created} chunks with page numbers.",
            )

    except (SSRFValidationError, PDFExtractionError) as e:
        logger.error(f"Ingestion security/extraction error for job {job_id}: {e}")
        background_job_service.update_job(job_id, JobStatus.FAILED, error=str(e))
    except Exception as e:
        logger.exception(f"Unhandled error in background ingestion job {job_id}: {e}")
        background_job_service.update_job(job_id, JobStatus.FAILED, error=f"Ingestion failure: {str(e)}")


# ---------------------------------------------------------------------------
# Tool 1: search_papers
# ---------------------------------------------------------------------------
def search_papers(
    query: str,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    limit: int = 10,
    **kwargs,
) -> Dict[str, Any]:
    """Search external academic databases (Semantic Scholar / OpenAlex) for research papers."""
    from app.api.search import search_papers as api_search

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        raw_res = loop.run_until_complete(api_search(query=query, limit=max(limit, 10)))
        loop.close()

        data_list = raw_res.get("data", [])
        filtered_papers = []

        for item in data_list:
            year = item.get("year")
            if year_from is not None and year and year < year_from:
                continue
            if year_to is not None and year and year > year_to:
                continue

            authors = [a.get("name") for a in item.get("authors") or [] if isinstance(a, dict) and a.get("name")]
            oa_info = item.get("openAccessPdf") or {}
            ext_ids = item.get("externalIds") or {}

            filtered_papers.append({
                "paper_id": item.get("paperId"),
                "title": item.get("title") or "Untitled Paper",
                "authors": authors[:5],
                "year": year,
                "abstract": item.get("abstract") or "",
                "doi": ext_ids.get("DOI"),
                "arxiv_id": ext_ids.get("ArXiv"),
                "citation_count": item.get("citationCount", 0),
                "open_access_url": oa_info.get("url"),
                "source": "semantic_scholar",
            })

            if len(filtered_papers) >= limit:
                break

        return {"papers": filtered_papers}

    except Exception as e:
        logger.error(f"search_papers tool error: {e}")
        return {"papers": [], "error": str(e)}


# ---------------------------------------------------------------------------
# Tool 2: find_open_access_pdf
# ---------------------------------------------------------------------------
def find_open_access_pdf(paper_id: str, **kwargs) -> Dict[str, Any]:
    """Discover open-access PDF download URL for a given paper_id using Unpaywall and arXiv."""
    supabase = get_supabase_client()
    doi = None
    arxiv_id = None
    existing_oa_url = None

    if supabase:
        try:
            res = supabase.table("papers").select("doi,arxiv_id,open_access_url").eq("id", paper_id).execute()
            if res.data:
                row = res.data[0]
                doi = row.get("doi")
                arxiv_id = row.get("arxiv_id")
                existing_oa_url = row.get("open_access_url")
        except Exception as e:
            logger.warning(f"Could not fetch paper {paper_id} details from Supabase: {e}")

    # Fallback lookup via search API details if not in DB
    if not doi and not arxiv_id and not existing_oa_url:
        from app.api.search import get_paper_details
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            details = loop.run_until_complete(get_paper_details(paper_id))
            loop.close()

            ext_ids = details.get("externalIds") or {}
            doi = ext_ids.get("DOI")
            arxiv_id = ext_ids.get("ArXiv")
            oa_info = details.get("openAccessPdf") or {}
            existing_oa_url = oa_info.get("url")
        except Exception as e:
            logger.warning(f"Could not fetch paper details from API: {e}")

    return open_access_service.find_open_access_pdf(
        doi=doi,
        arxiv_id=arxiv_id,
        existing_oa_url=existing_oa_url,
    )


# ---------------------------------------------------------------------------
# Tool 3: check_library
# ---------------------------------------------------------------------------
def check_library(paper_id: str, authenticated_user_id: str, **kwargs) -> Dict[str, Any]:
    """Check whether a paper is already saved/indexed in the authenticated user's library."""
    supabase = get_supabase_client()
    if not supabase:
        return {"exists": False}

    try:
        # Check user_papers table
        up_res = (
            supabase.table("user_papers")
            .select("paper_id,status")
            .eq("user_id", authenticated_user_id)
            .eq("paper_id", paper_id)
            .execute()
        )
        if not up_res.data:
            return {"exists": False}

        # Check paper_chunks to confirm chunk indexing
        chunk_res = (
            supabase.table("paper_chunks")
            .select("document_id")
            .eq("paper_id", paper_id)
            .limit(1)
            .execute()
        )

        document_id = chunk_res.data[0].get("document_id") if chunk_res.data else paper_id
        return {
            "exists": True,
            "document_id": document_id,
            "status": "completed" if chunk_res.data else "saved_unindexed",
        }
    except Exception as e:
        logger.error(f"check_library error for user {authenticated_user_id}, paper {paper_id}: {e}")
        return {"exists": False}


# ---------------------------------------------------------------------------
# Tool 4: ingest_paper
# ---------------------------------------------------------------------------
def ingest_paper(
    paper_id: str,
    pdf_url: str,
    authenticated_user_id: str,
    **kwargs,
) -> Dict[str, Any]:
    """Download, validate, extract, and index a PDF in the background for the authenticated user."""
    # Check if already processed
    lib_check = check_library(paper_id=paper_id, authenticated_user_id=authenticated_user_id)
    if lib_check.get("exists") and lib_check.get("status") == "completed":
        return {
            "success": True,
            "document_id": lib_check.get("document_id"),
            "status": "already_exists",
            "message": "Paper is already fully indexed in user library.",
        }

    # Ensure paper record exists in DB
    supabase = get_supabase_client()
    if supabase:
        try:
            # Check if paper row exists; if not, create placeholder row
            paper_res = supabase.table("papers").select("id").eq("id", paper_id).execute()
            if not paper_res.data:
                # Fetch metadata to save basic info
                from app.api.search import get_paper_details
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    details = loop.run_until_complete(get_paper_details(paper_id))
                    loop.close()

                    ext_ids = details.get("externalIds") or {}
                    authors = [a.get("name") for a in details.get("authors") or [] if isinstance(a, dict)]

                    supabase.table("papers").upsert({
                        "id": paper_id,
                        "title": details.get("title") or "Untitled Paper",
                        "abstract": details.get("abstract") or "",
                        "year": details.get("year"),
                        "authors": authors,
                        "doi": ext_ids.get("DOI"),
                        "arxiv_id": ext_ids.get("ArXiv"),
                    }).execute()
                except Exception as meta_err:
                    logger.warning(f"Could not fetch metadata for paper {paper_id}: {meta_err}")
                    supabase.table("papers").upsert({
                        "id": paper_id,
                        "title": f"Paper {paper_id}",
                    }).execute()
        except Exception as e:
            logger.warning(f"Failed to verify/create paper record in Supabase: {e}")

    # Launch background job
    job_id = background_job_service.create_job(paper_id=paper_id, pdf_url=pdf_url)

    t = threading.Thread(
        target=_run_async_ingestion,
        kwargs={
            "job_id": job_id,
            "paper_id": paper_id,
            "pdf_url": pdf_url,
            "user_id": authenticated_user_id,
        },
        daemon=True,
    )
    t.start()

    return {
        "success": True,
        "document_id": paper_id,
        "job_id": job_id,
        "status": "queued",
        "message": f"Background PDF ingestion job '{job_id}' started.",
    }


# ---------------------------------------------------------------------------
# Tool 5: get_ingestion_status
# ---------------------------------------------------------------------------
def get_ingestion_status(job_id: str, **kwargs) -> Dict[str, Any]:
    """Check status of a background PDF ingestion job."""
    return background_job_service.get_job_status(job_id)


# ---------------------------------------------------------------------------
# Tool 6: search_library
# ---------------------------------------------------------------------------
def search_library(
    query: str,
    authenticated_user_id: str,
    top_k: int = 8,
    folder_id: Optional[str] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Perform 2-stage vector search over indexed papers in the authenticated user's library."""
    try:
        citations = retrieval_service.retrieve_library_chunks(
            query=query,
            user_id=authenticated_user_id,
            folder_id=folder_id,
            evidence_chunk_k=top_k,
        )

        supabase = get_supabase_client()
        paper_titles = {}
        if supabase and citations:
            pids = list({c.paper_id for c in citations if c.paper_id})
            if pids:
                try:
                    p_res = supabase.table("papers").select("id,title").in_("id", pids).execute()
                    for row in p_res.data or []:
                        paper_titles[row["id"]] = row.get("title", "")
                except Exception as e:
                    logger.warning(f"Could not fetch paper titles for library search: {e}")

        results = []
        for c in citations:
            results.append({
                "paper_id": c.paper_id,
                "document_id": c.document_id,
                "title": paper_titles.get(c.paper_id, "Research Paper"),
                "chunk_id": f"{c.paper_id}_c{c.chunk_index}",
                "chunk_index": c.chunk_index,
                "page_number": c.page_number,
                "section_title": c.section_title or f"Chunk #{c.chunk_index}",
                "content": c.content_snippet,
                "similarity": round(c.similarity_score, 4),
            })

        return {"results": results}

    except Exception as e:
        logger.error(f"search_library tool error for user {authenticated_user_id}: {e}")
        return {"results": [], "error": str(e)}


# ---------------------------------------------------------------------------
# Tool 7: get_paper
# ---------------------------------------------------------------------------
def get_paper(paper_id: str, **kwargs) -> Dict[str, Any]:
    """Retrieve paper metadata details (title, authors, abstract, year, DOI). Does NOT return full PDF text."""
    supabase = get_supabase_client()
    if supabase:
        try:
            res = supabase.table("papers").select("*").eq("id", paper_id).execute()
            if res.data:
                paper = res.data[0]
                return {
                    "paper_id": paper.get("id"),
                    "title": paper.get("title"),
                    "authors": paper.get("authors") or [],
                    "year": paper.get("year"),
                    "abstract": paper.get("abstract"),
                    "doi": paper.get("doi"),
                    "arxiv_id": paper.get("arxiv_id"),
                    "indexed_at": paper.get("indexed_at"),
                }
        except Exception as e:
            logger.warning(f"Could not fetch paper {paper_id} from Supabase: {e}")

    # Fallback to search API
    from app.api.search import get_paper_details
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        details = loop.run_until_complete(get_paper_details(paper_id))
        loop.close()

        authors = [a.get("name") for a in details.get("authors") or [] if isinstance(a, dict)]
        ext_ids = details.get("externalIds") or {}

        return {
            "paper_id": details.get("paperId"),
            "title": details.get("title"),
            "authors": authors,
            "year": details.get("year"),
            "abstract": details.get("abstract"),
            "doi": ext_ids.get("DOI"),
            "arxiv_id": ext_ids.get("ArXiv"),
        }
    except Exception as e:
        return {"error": f"Paper details for {paper_id} not found: {str(e)}"}


# ---------------------------------------------------------------------------
# Tool Declarations for Gemini Function Calling
# ---------------------------------------------------------------------------
TOOL_DECLARATIONS = [
    {
        "name": "search_papers",
        "description": "Search external academic research sources (Semantic Scholar/OpenAlex) for papers matching a topic query.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "Research topic or keywords"},
                "year_from": {"type": "INTEGER", "description": "Optional starting publication year"},
                "year_to": {"type": "INTEGER", "description": "Optional ending publication year"},
                "limit": {"type": "INTEGER", "description": "Number of paper metadata items to return (default 10)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "find_open_access_pdf",
        "description": "Discover open-access PDF download URL for a paper using Unpaywall, arXiv, and academic database records.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "paper_id": {"type": "STRING", "description": "Target paper UUID or ID"},
            },
            "required": ["paper_id"],
        },
    },
    {
        "name": "check_library",
        "description": "Check if a paper is already saved and fully indexed in the user's research library.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "paper_id": {"type": "STRING", "description": "Target paper UUID or ID"},
            },
            "required": ["paper_id"],
        },
    },
    {
        "name": "ingest_paper",
        "description": "Download, validate, extract, and index a PDF in the background for full-text RAG vector search.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "paper_id": {"type": "STRING", "description": "Target paper UUID"},
                "pdf_url": {"type": "STRING", "description": "Direct HTTP/HTTPS PDF URL"},
            },
            "required": ["paper_id", "pdf_url"],
        },
    },
    {
        "name": "get_ingestion_status",
        "description": "Check status of a background PDF downloading, extraction, and vector indexing job.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "job_id": {"type": "STRING", "description": "Background ingestion job ID returned by ingest_paper"},
            },
            "required": ["job_id"],
        },
    },
    {
        "name": "search_library",
        "description": "Search full-PDF text chunks and sections across papers in the user's indexed research library using vector similarity.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "Search query or detailed research question"},
                "top_k": {"type": "INTEGER", "description": "Number of evidence text chunks to retrieve (default 8)"},
                "folder_id": {"type": "STRING", "description": "Optional folder UUID to restrict library search"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_paper",
        "description": "Retrieve paper metadata details (title, authors, year, abstract, DOI).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "paper_id": {"type": "STRING", "description": "Target paper UUID"},
            },
            "required": ["paper_id"],
        },
    },
]

TOOL_REGISTRY = {
    "search_papers": search_papers,
    "find_open_access_pdf": find_open_access_pdf,
    "check_library": check_library,
    "ingest_paper": ingest_paper,
    "get_ingestion_status": get_ingestion_status,
    "search_library": search_library,
    "get_paper": get_paper,
}
