import logging
from fastapi import APIRouter, Depends, HTTPException
from app.core.auth import get_current_user_id
from app.schemas.indexing import IndexPaperRequest, IndexPaperResponse
from app.services.indexing import IndexingService

logger = logging.getLogger(__name__)
router = APIRouter()
indexing_service = IndexingService()


@router.post("/papers/{paper_id}/index", response_model=IndexPaperResponse)
def index_paper_endpoint(
    paper_id: str,
    payload: IndexPaperRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Trigger chunking, embedding, and storage for a paper."""
    if payload.paper_id != paper_id:
        raise HTTPException(status_code=400, detail="Paper ID mismatch in route and body.")

    try:
        response = indexing_service.index_paper(
            paper_id=paper_id,
            full_text=payload.full_text,
            sections=payload.sections,
        )
        return response
    except Exception as e:
        logger.exception(f"Unhandled error during paper indexing: {e}")
        raise HTTPException(status_code=500, detail=str(e))
