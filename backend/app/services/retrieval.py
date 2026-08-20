import logging
from typing import List, Optional, Dict, Any
from app.core.supabase import match_chunks_rpc, match_papers_rpc
from app.schemas.chat import Citation
from app.services.embeddings import EmbeddingService

logger = logging.getLogger(__name__)


class RetrievalService:
    """Service for semantic similarity retrieval over paper chunks or whole papers."""

    def __init__(self, embedding_service: Optional[EmbeddingService] = None):
        self.embedding_service = embedding_service or EmbeddingService()

    def retrieve_context(
        self,
        query: str,
        paper_id: Optional[str] = None,
        top_k: int = 4,
        similarity_threshold: float = 0.25,
    ) -> List[Citation]:
        """Perform vector search over paper_chunks and return structured context citations."""
        query_vec = self.embedding_service.embed_query(query)
        if not query_vec or query_vec[0] == 0.0:
            logger.warning("Empty query vector generated.")
            return []

        rpc_results = match_chunks_rpc(
            query_embedding=query_vec,
            match_threshold=similarity_threshold,
            match_count=top_k,
            filter_paper_id=paper_id,
        )

        citations: List[Citation] = []
        for match in rpc_results:
            citations.append(
                Citation(
                    section_title=match.get("section_title"),
                    chunk_index=match.get("chunk_index", 0),
                    content_snippet=match.get("content", ""),
                    similarity_score=float(match.get("similarity", 0.0)),
                )
            )

        return citations

    def retrieve_paper_ids_for_user(
        self,
        query: str,
        user_id: str,
        folder_id: Optional[str] = None,
        top_k: int = 5,
        similarity_threshold: float = 0.25,
    ) -> List[Dict[str, Any]]:
        """Return list of paper IDs with similarity scores for a user (optionally filtered by folder)."""
        query_vec = self.embedding_service.embed_query(query)
        if not query_vec or query_vec[0] == 0.0:
            logger.warning("Empty query vector generated.")
            return []

        rpc_results = match_papers_rpc(
            query_embedding=query_vec,
            match_threshold=similarity_threshold,
            match_count=top_k,
            filter_user_id=user_id,
            filter_folder_id=folder_id,
        )
        # rpc_results already contains dicts with paper_id and similarity
        return rpc_results
