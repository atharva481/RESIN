import logging
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from app.core.auth import get_current_user_id
from app.schemas.indexing import IndexPaperRequest, IndexPaperResponse
from app.services.indexing import IndexingService
from app.services.open_access import OpenAccessService
from app.services.pdf import PDFService, PDFExtractionError
from app.core.supabase import get_supabase_client

logger = logging.getLogger(__name__)
router = APIRouter()
indexing_service = IndexingService()
open_access_service = OpenAccessService()
pdf_service = PDFService()


@router.post("/papers/{paper_id}/index", response_model=IndexPaperResponse)
def index_paper_endpoint(
    paper_id: str,
    payload: IndexPaperRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Trigger chunking, embedding, and storage for a paper.
    
    Priority:
    1. Full PDF via open_access_url or arxiv_id (best quality - multi-chunk with page numbers)
    2. full_text passed in the request body
    3. Abstract only (fallback - single chunk)
    """
    if payload.paper_id != paper_id:
        raise HTTPException(status_code=400, detail="Paper ID mismatch in route and body.")

    try:
        # Resolve any external ID (or UUID) to a canonical Postgres UUID and fetch/persist paper metadata
        from app.services.paper_resolution import resolve_paper_record
        canonical_id, paper_data = resolve_paper_record(
            paper_id=paper_id,
            title=payload.title,
            abstract=payload.abstract,
            doi=payload.doi,
            arxiv_id=payload.arxiv_id,
            open_access_url=payload.open_access_url,
        )

        client = get_supabase_client()
        if client and not payload.force:
            try:
                # Fast return if already indexed with multi-chunk PDF and force not set
                existing = client.table("paper_chunks").select("id", count="exact").eq("paper_id", canonical_id).limit(1).execute()
                if existing.count and existing.count >= 5:
                    logger.info(f"Paper {canonical_id} (requested {paper_id}) is already indexed ({existing.count} chunks). Skipping re-index.")
                    return IndexPaperResponse(
                        paper_id=paper_id,
                        canonical_paper_id=canonical_id,
                        chunks_created=existing.count,
                        chunks=[],
                        status="success",
                        message=f"Paper is already indexed with {existing.count} chunks.",
                    )
                elif existing.count and existing.count > 0:
                    # Clean up old partial chunks before generating full indexing
                    logger.info(f"Paper {canonical_id} had only {existing.count} chunks. Re-indexing full paper...")
                    client.table("paper_chunks").delete().eq("paper_id", canonical_id).execute()
            except Exception as e:
                logger.warning(f"Could not check existing chunks for {canonical_id}: {e}")

        # Combine database metadata with request payload fallbacks
        oa_url = paper_data.get("open_access_url") or payload.open_access_url
        arxiv_id = paper_data.get("arxiv_id") or payload.arxiv_id
        doi = paper_data.get("doi") or payload.doi
        title = paper_data.get("title") or payload.title
        abstract = paper_data.get("abstract") or payload.abstract

        # Check if paper_id itself or fields contain an arXiv identifier
        from app.services.open_access import extract_arxiv_id
        if not arxiv_id:
            arxiv_id = extract_arxiv_id(paper_id) or extract_arxiv_id(doi) or extract_arxiv_id(oa_url)

        # 1. Try full PDF indexing from discovered candidates
        candidates = open_access_service.find_pdf_candidates(
            doi=doi,
            arxiv_id=arxiv_id,
            existing_oa_url=oa_url,
            title=title,
        )

        from app.services.pdf import DownloadFailureReason

        failure_log: List[Dict[str, Any]] = []

        # Test up to 4 highest-priority candidates to keep indexing fast
        sorted_candidates = sorted(candidates, key=lambda c: c.get("priority", 0), reverse=True)
        for cand in sorted_candidates[:4]:
            pdf_url = cand["url"]
            source = cand["source"]
            prio = cand.get("priority", 0)
            logger.info(f"Trying PDF candidate for paper {canonical_id} from {source} (priority {prio}): {pdf_url}")
            try:
                dl_res = pdf_service.detailed_download(pdf_url)
                if dl_res.success and dl_res.pdf_bytes:
                    pages_data = pdf_service.extract_pages(dl_res.pdf_bytes)
                    if pages_data:
                        logger.info(f"Extracted {len(pages_data)} pages from PDF for paper {canonical_id} via {source}")
                        # Cache the working PDF URL in papers table
                        if client and (not oa_url or not oa_url.lower().endswith(".pdf")):
                            try:
                                client.table("papers").update({"open_access_url": dl_res.final_url or pdf_url}).eq("id", canonical_id).execute()
                            except Exception as e:
                                logger.warning(f"Could not cache working OA URL: {e}")

                        res = indexing_service.index_pdf_pages(
                            paper_id=canonical_id,
                            pages_data=pages_data,
                            document_id=dl_res.final_url or pdf_url,
                        )
                        res.paper_id = paper_id
                        return res
                    else:
                        failure_log.append({
                            "url": pdf_url,
                            "source": source,
                            "reason": DownloadFailureReason.INVALID_PDF,
                            "message": "Downloaded PDF contained no extractable text.",
                        })
                else:
                    failure_log.append({
                        "url": pdf_url,
                        "source": source,
                        "reason": dl_res.failure_reason,
                        "message": dl_res.error_message or dl_res.failure_reason.value,
                        "final_url": dl_res.final_url,
                        "status_code": dl_res.status_code,
                    })
                    logger.warning(
                        f"Candidate {pdf_url} ({source}) failed: {dl_res.failure_reason.value} ({dl_res.error_message}). Final URL: {dl_res.final_url}"
                    )
            except Exception as e:
                failure_log.append({"url": pdf_url, "source": source, "reason": DownloadFailureReason.NETWORK_ERROR, "message": str(e)})
                logger.warning(f"Candidate {pdf_url} ({source}) failed with error: {e}")

        # 2. If full_text was explicitly provided (e.g. manual text or extract), index that
        if payload.full_text and len(payload.full_text.strip()) > 500:
            logger.info(f"Indexing provided full_text for {canonical_id}.")
            response = indexing_service.index_paper(
                paper_id=canonical_id,
                full_text=payload.full_text,
                sections=payload.sections,
                title=title,
                abstract=abstract,
            )
            response.paper_id = paper_id
            response.canonical_paper_id = canonical_id
            return response

        # 2.5. Check for PubMed Central (PMC) full text (Open Access via NCBI E-utilities / Europe PMC)
        from app.services.open_access import extract_pmc_id, resolve_pmcid_from_doi, fetch_pmc_full_text
        pmc_id = (
            extract_pmc_id(paper_id)
            or extract_pmc_id(oa_url)
            or resolve_pmcid_from_doi(doi)
        )
        if pmc_id:
            logger.info(f"Discovered PubMed Central ID PMC{pmc_id} for paper {canonical_id}. Fetching full text...")
            pmc_sections = fetch_pmc_full_text(pmc_id)
            if pmc_sections:
                logger.info(f"Retrieved {len(pmc_sections)} full-text sections for PMC{pmc_id}. Indexing...")
                res = indexing_service.index_paper(
                    paper_id=canonical_id,
                    sections=pmc_sections,
                    title=title,
                    abstract=abstract,
                )
                res.paper_id = paper_id
                res.canonical_paper_id = canonical_id
                res.message = f"Successfully indexed {res.chunks_created} full-text sections from PubMed Central (Open Access)."
                return res

        # 3. Classify failure based on collected diagnostics
        has_bot_block = any(f.get("reason") == DownloadFailureReason.BOT_PROTECTION for f in failure_log)
        has_login = any(f.get("reason") == DownloadFailureReason.LOGIN_REQUIRED for f in failure_log)
        has_paywall = any(f.get("reason") == DownloadFailureReason.PAYWALL_DETECTED for f in failure_log)
        has_rate_limit = any(f.get("reason") == DownloadFailureReason.RATE_LIMITED for f in failure_log)

        if has_paywall or has_login:
            reason_msg = (
                "This paper is paywalled or requires institutional/subscriber access. "
                "No open-access PDF was found across OpenAlex, Unpaywall, or repositories."
            )
        elif has_bot_block:
            reason_msg = (
                "The publisher server blocked automated server downloads with a bot challenge (Cloudflare/reCAPTCHA). "
                "The paper may be viewable in your desktop browser."
            )
        elif has_rate_limit:
            reason_msg = "The publisher or repository rate-limited automated access (HTTP 429). Please wait a moment."
        else:
            reason_msg = "No free full-text PDF or repository mirror was found online for this paper."

        logger.info(f"Paper {canonical_id} indexing stopped: {reason_msg}. Skipping embedding generation.")
        return IndexPaperResponse(
            paper_id=paper_id,
            canonical_paper_id=canonical_id,
            chunks_created=0,
            chunks=[],
            status="warning",
            message=f"{reason_msg} You can upload the paper PDF directly to enable full-text AI Chat.",
        )

    except Exception as e:
        logger.exception(f"Unhandled error during paper indexing: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/papers/{paper_id}/upload-pdf", response_model=IndexPaperResponse)
async def upload_pdf_endpoint(
    paper_id: str,
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
):
    """Index a user-uploaded PDF file for any paper (enabling multi-page RAG for paywalled papers)."""
    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")
        if len(content) > 50 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File exceeds 50MB limit.")
        if not content.startswith(b"%PDF-") and b"%PDF-" not in content[:1024]:
            raise HTTPException(status_code=400, detail="Uploaded file does not have a valid PDF header.")

        from app.services.paper_resolution import resolve_paper_record
        canonical_id, _ = resolve_paper_record(paper_id=paper_id)

        pages_data = pdf_service.extract_pages(content)
        if not pages_data:
            raise HTTPException(status_code=400, detail="Could not extract text from the uploaded PDF.")

        res = indexing_service.index_pdf_pages(
            paper_id=canonical_id,
            pages_data=pages_data,
            document_id=file.filename or "uploaded.pdf",
        )
        res.paper_id = paper_id
        res.canonical_paper_id = canonical_id
        res.message = f"Successfully extracted and indexed {len(pages_data)} pages ({res.chunks_created} chunks) from uploaded PDF."
        return res

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error indexing uploaded PDF for {paper_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
