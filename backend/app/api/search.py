import logging
import time
from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException, Query
import httpx
from app.core.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)

SS_BASE_URL = "https://api.semanticscholar.org/graph/v1"
FIELDS = "paperId,externalIds,title,abstract,year,authors.name,citationCount,openAccessPdf"

# In-memory simple TTL cache for search queries & paper details
_cache: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SECONDS = 600  # 10 minutes


def get_ss_headers() -> dict:
    headers = {}
    api_key = getattr(settings, "semantic_scholar_api_key", None)
    if api_key and api_key != "placeholder-key" and len(api_key.strip()) > 10:
        headers["x-api-key"] = api_key.strip()
    return headers


def reconstruct_abstract(inverted_index: Optional[dict]) -> str:
    """Reconstruct text abstract from OpenAlex inverted index dict."""
    if not inverted_index or not isinstance(inverted_index, dict):
        return ""
    word_pos = []
    for word, positions in inverted_index.items():
        if isinstance(positions, list):
            for pos in positions:
                word_pos.append((pos, word))
    word_pos.sort(key=lambda x: x[0])
    return " ".join(w[1] for w in word_pos)


def convert_openalex_item(item: dict) -> dict:
    """Transform OpenAlex work entity to Semantic Scholar SSPaper schema."""
    raw_id = item.get("id", "")
    work_id = raw_id.split("/")[-1] if raw_id else "unknown"

    doi_raw = item.get("doi") or ""
    doi = doi_raw.replace("https://doi.org/", "") if doi_raw else None

    arxiv_id = None
    ids = item.get("ids") or {}
    if "arxiv" in ids:
        arxiv_raw = str(ids["arxiv"])
        arxiv_id = arxiv_raw.split("/")[-1].replace("arXiv:", "")

    authors = []
    for auth in item.get("authorships") or []:
        author_name = auth.get("author", {}).get("display_name")
        if author_name:
            authors.append({"name": author_name})

    oa_info = item.get("open_access") or {}
    oa_url = oa_info.get("oa_url") if oa_info.get("is_oa") else None
    abstract = reconstruct_abstract(item.get("abstract_inverted_index"))

    return {
        "paperId": work_id,
        "externalIds": {
            **({"DOI": doi} if doi else {}),
            **({"ArXiv": arxiv_id} if arxiv_id else {}),
        },
        "title": item.get("title") or "Untitled Paper",
        "abstract": abstract if abstract else None,
        "year": item.get("publication_year"),
        "authors": authors,
        "citationCount": item.get("cited_by_count", 0),
        "openAccessPdf": {"url": oa_url} if oa_url else None,
    }


async def fetch_openalex_search(query: str, limit: int = 20) -> dict:
    """Search OpenAlex (250M+ open papers, 10 req/sec free limit)."""
    url = "https://api.openalex.org/works"
    params = {
        "search": query,
        "per_page": limit,
        "mailto": "resin-academic-app@example.com",
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params, timeout=10.0)
        if resp.status_code == 200:
            data = resp.json()
            results = data.get("results", [])
            converted = [convert_openalex_item(item) for item in results]
            return {"total": len(converted), "offset": 0, "data": converted}
        raise HTTPException(status_code=resp.status_code, detail="OpenAlex API search error")


async def fetch_openalex_paper(paper_id: str) -> dict:
    """Fetch single paper details from OpenAlex by ID or DOI."""
    target_id = paper_id if paper_id.startswith("W") else f"W{paper_id}"
    url = f"https://api.openalex.org/works/{target_id}"
    params = {"mailto": "resin-academic-app@example.com"}
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params, timeout=10.0)
        if resp.status_code == 200:
            return convert_openalex_item(resp.json())
        raise HTTPException(status_code=resp.status_code, detail="OpenAlex paper not found")


@router.get("/search")
async def search_papers(query: str = Query(..., min_length=1), limit: int = 20):
    """Proxy paper search to Semantic Scholar API with automatic OpenAlex fallback."""
    cache_key = f"search:{query.lower().strip()}:{limit}"
    now = time.time()

    if cache_key in _cache and (now - _cache[cache_key]["ts"] < CACHE_TTL_SECONDS):
        logger.info(f"Returning cached search results for: '{query}'")
        return _cache[cache_key]["data"]

    url = f"{SS_BASE_URL}/paper/search"
    params = {
        "query": query,
        "limit": limit,
        "fields": FIELDS,
    }
    headers = get_ss_headers()

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, params=params, headers=headers, timeout=8.0)
            if resp.status_code == 403 and headers:
                logger.warning("Semantic Scholar API key returned 403 Forbidden. Retrying without API key.")
                resp = await client.get(url, params=params, timeout=8.0)

            if resp.status_code == 200:
                data = resp.json()
                _cache[cache_key] = {"data": data, "ts": now}
                return data

            logger.warning(
                f"Semantic Scholar returned status {resp.status_code}. Falling back to OpenAlex API..."
            )
        except Exception as e:
            logger.warning(f"Semantic Scholar request error ({e}). Falling back to OpenAlex API...")

    # OpenAlex Fallback
    try:
        data = await fetch_openalex_search(query, limit)
        _cache[cache_key] = {"data": data, "ts": now}
        return data
    except Exception as e:
        if cache_key in _cache:
            return _cache[cache_key]["data"]
        logger.error(f"OpenAlex fallback search error: {e}")
        raise HTTPException(status_code=502, detail="Failed to fetch papers from both Semantic Scholar and OpenAlex")


@router.get("/{paper_id}")
async def get_paper_details(paper_id: str):
    """Proxy single paper details request to Semantic Scholar with OpenAlex fallback."""
    cache_key = f"paper:{paper_id}"
    now = time.time()

    if cache_key in _cache and (now - _cache[cache_key]["ts"] < CACHE_TTL_SECONDS):
        return _cache[cache_key]["data"]

    if paper_id.startswith("W"):
        # Direct OpenAlex ID
        try:
            data = await fetch_openalex_paper(paper_id)
            _cache[cache_key] = {"data": data, "ts": now}
            return data
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"Paper {paper_id} not found: {e}")

    url = f"{SS_BASE_URL}/paper/{paper_id}"
    params = {"fields": FIELDS}
    headers = get_ss_headers()

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, params=params, headers=headers, timeout=8.0)
            if resp.status_code == 403 and headers:
                resp = await client.get(url, params=params, timeout=8.0)

            if resp.status_code == 200:
                data = resp.json()
                _cache[cache_key] = {"data": data, "ts": now}
                return data

            if resp.status_code == 404:
                raise HTTPException(status_code=404, detail="Paper not found")
        except Exception as e:
            logger.warning(f"Semantic Scholar error for {paper_id}: {e}. Trying OpenAlex fallback...")

    # OpenAlex fallback by ID
    try:
        data = await fetch_openalex_paper(paper_id)
        _cache[cache_key] = {"data": data, "ts": now}
        return data
    except Exception:
        if cache_key in _cache:
            return _cache[cache_key]["data"]
        raise HTTPException(status_code=404, detail="Paper details not found on Semantic Scholar or OpenAlex")
