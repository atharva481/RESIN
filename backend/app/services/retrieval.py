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
                    paper_id=match.get("paper_id") or paper_id,
                    document_id=match.get("document_id"),
                    chunk_index=match.get("chunk_index", 0),
                    page_number=match.get("page_number"),
                    section_title=match.get("section_title"),
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
        top_k: int = 10,
        similarity_threshold: float = 0.20,
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
        return rpc_results

    def retrieve_library_chunks(
        self,
        query: str,
        user_id: str,
        folder_id: Optional[str] = None,
        candidate_paper_k: int = 10,
        evidence_chunk_k: int = 8,
        similarity_threshold: float = 0.20,
    ) -> List[Citation]:
        """
        2-Stage Full-PDF RAG Retrieval Pipeline:
        Stage 1: Retrieve top candidate paper IDs in user's library matching query vector.
        Stage 2: Retrieve top evidence text chunks across candidate papers, retaining page & section info.
        """
        query_vec = self.embedding_service.embed_query(query)
        if not query_vec or query_vec[0] == 0.0:
            logger.warning("Empty query vector generated.")
            return []

        # Stage 1: Get paper candidates
        paper_matches = match_papers_rpc(
            query_embedding=query_vec,
            match_threshold=similarity_threshold,
            match_count=candidate_paper_k,
            filter_user_id=user_id,
            filter_folder_id=folder_id,
        )

        candidate_paper_ids = [m["paper_id"] for m in paper_matches if "paper_id" in m]

        # Stage 2: Gather chunk-level evidence across candidate papers
        all_chunk_matches: List[Dict[str, Any]] = []

        if candidate_paper_ids:
            for pid in candidate_paper_ids:
                chunks = match_chunks_rpc(
                    query_embedding=query_vec,
                    match_threshold=similarity_threshold,
                    match_count=4,
                    filter_paper_id=pid,
                )
                all_chunk_matches.extend(chunks)
        else:
            # Fallback: search all chunks without filtering paper_id
            all_chunk_matches = match_chunks_rpc(
                query_embedding=query_vec,
                match_threshold=similarity_threshold,
                match_count=evidence_chunk_k,
                filter_paper_id=None,
            )

        # Sort all chunks by similarity score descending
        all_chunk_matches.sort(key=lambda x: float(x.get("similarity", 0.0)), reverse=True)

        # Take top K evidence chunks
        top_chunks = all_chunk_matches[:evidence_chunk_k]

        citations: List[Citation] = []
        for match in top_chunks:
            citations.append(
                Citation(
                    paper_id=match.get("paper_id"),
                    document_id=match.get("document_id"),
                    chunk_index=match.get("chunk_index", 0),
                    page_number=match.get("page_number"),
                    section_title=match.get("section_title"),
                    content_snippet=match.get("content", ""),
                    similarity_score=float(match.get("similarity", 0.0)),
                )
            )

        return citations

