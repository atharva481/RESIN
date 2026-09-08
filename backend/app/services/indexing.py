import logging
from datetime import datetime, timezone
from typing import Optional
from app.core.supabase import get_supabase_client
from app.schemas.indexing import ChunkInfo, IndexPaperResponse
from app.services.chunking import TextChunker
from app.services.embeddings import EmbeddingService

logger = logging.getLogger(__name__)


class IndexingService:
    """Service for splitting papers into chunks, embedding them, and storing in pgvector."""

    def __init__(
        self,
        chunker: Optional[TextChunker] = None,
        embedding_service: Optional[EmbeddingService] = None,
    ):
        self.chunker = chunker or TextChunker()
        self.embedding_service = embedding_service or EmbeddingService()

    def index_paper(
        self,
        paper_id: str,
        full_text: Optional[str] = None,
        sections: Optional[dict] = None,
    ) -> IndexPaperResponse:
        client = get_supabase_client()

        # 1. Fetch paper from database if full_text not explicitly supplied
        paper_data = {}
        if client:
            try:
                res = client.table("papers").select("*").eq("id", paper_id).execute()
                if res.data:
                    paper_data = res.data[0]
            except Exception as e:
                logger.warning(f"Could not fetch paper {paper_id} details from Supabase: {e}")

        title = paper_data.get("title", "Untitled Paper")
        abstract = paper_data.get("abstract", "")
        db_full_text = paper_data.get("full_text") or full_text

        # 2. Chunk paper
        chunks = self.chunker.chunk_paper(
            paper_id=paper_id,
            title=title,
            abstract=abstract,
            full_text=db_full_text,
            sections=sections,
        )

        if not chunks:
            return IndexPaperResponse(
                paper_id=paper_id,
                chunks_created=0,
                chunks=[],
                status="warning",
                message="No content available to chunk.",
            )

        # 3. Generate embeddings & prepare db records
        chunk_infos = []
        db_records = []

        try:
            vectors = self.embedding_service.embed_batch([chunk.content for chunk in chunks])
        except Exception as e:
            logger.error(f"Embedding generation failed for {paper_id}: {e}")
            return IndexPaperResponse(
                paper_id=paper_id,
                chunks_created=len(chunks),
                chunks=chunk_infos,
                status="error",
                message=f"Embedding generation failed: {str(e)}",
            )

        for chunk, vector in zip(chunks, vectors):
            rec = {
                "paper_id": paper_id,
                "chunk_index": chunk.chunk_index,
                "section_title": chunk.section_title,
                "content": chunk.content,
                "embedding": vector,
                "word_count": chunk.word_count,
            }
            if chunk.page_number is not None:
                rec["page_number"] = chunk.page_number
            db_records.append(rec)
            chunk_infos.append(
                ChunkInfo(
                    chunk_index=chunk.chunk_index,
                    section_title=chunk.section_title,
                    word_count=chunk.word_count,
                )
            )

        # 4. Upsert chunks into Supabase paper_chunks table (backward compatibility)
        try:
            if not client:
                logger.warning("Supabase client not configured; generated embeddings in memory only.")
                return IndexPaperResponse(
                    paper_id=paper_id,
                    chunks_created=len(chunks),
                    chunks=chunk_infos,
                    status="success",
                    message=f"Created {len(chunks)} text chunk embeddings (in-memory).",
                )

            client.table("paper_chunks").upsert(
                db_records,
                on_conflict="paper_id,chunk_index",
            ).execute()

            # 5. Also store a single embedding for the whole paper in paper_embeddings
            # Combine title, abstract, and full_text (if available) for a holistic embedding
            combined_text = f"{title}\n{abstract}\n{db_full_text or ''}".strip()
            if combined_text:
                try:
                    paper_embedding = self.embedding_service.embed_text(combined_text)
                    supabase_client = client  # rename for clarity
                    supabase_client.table("paper_embeddings").upsert(
                        {"paper_id": paper_id, "embedding": paper_embedding},
                        on_conflict="paper_id",
                    ).execute()
                except Exception as e:
                    logger.error(f"Failed to generate/store paper-level embedding for {paper_id}: {e}")
                    # Not fatal; we still have chunk embeddings

            # Update papers.indexed_at timestamp
            now_iso = datetime.now(timezone.utc).isoformat()
            client.table("papers").update({"indexed_at": now_iso}).eq("id", paper_id).execute()

            return IndexPaperResponse(
                paper_id=paper_id,
                chunks_created=len(chunks),
                chunks=chunk_infos,
                status="success",
                message=f"Successfully indexed {len(chunks)} chunks for paper {paper_id}.",
            )
        except Exception as e:
            logger.error(f"Failed to upsert paper_chunks for {paper_id}: {e}")
            err_msg = str(e)
            if "PGRST205" in err_msg or "paper_chunks" in err_msg:
                err_msg = (
                    "Table 'paper_chunks' does not exist in Supabase database. "
                    "Please run backend/migrations/full_rag_setup.sql in your Supabase SQL Editor."
                )
            return IndexPaperResponse(
                paper_id=paper_id,
                chunks_created=len(chunks),
                chunks=chunk_infos,
                status="error",
                message=err_msg,
            )

    def index_pdf_pages(
        self,
        paper_id: str,
        pages_data: list,
        document_id: Optional[str] = None,
    ) -> IndexPaperResponse:
        """Index page-extracted PDF text with page_number and optional document_id."""
        client = get_supabase_client()
        chunks = self.chunker.chunk_pages(paper_id=paper_id, pages_data=pages_data)

        if not chunks:
            return IndexPaperResponse(
                paper_id=paper_id,
                chunks_created=0,
                chunks=[],
                status="warning",
                message="No content available to chunk from PDF pages.",
            )

        chunk_infos = []
        db_records = []
        vectors = self.embedding_service.embed_batch([chunk.content for chunk in chunks])

        for chunk, vector in zip(chunks, vectors):
            rec = {
                "paper_id": paper_id,
                "chunk_index": chunk.chunk_index,
                "section_title": chunk.section_title,
                "content": chunk.content,
                "embedding": vector,
                "word_count": chunk.word_count,
            }
            if chunk.page_number is not None:
                rec["page_number"] = chunk.page_number
            if document_id:
                rec["document_id"] = document_id
            db_records.append(rec)
            chunk_infos.append(
                ChunkInfo(
                    chunk_index=chunk.chunk_index,
                    section_title=chunk.section_title,
                    word_count=chunk.word_count,
                )
            )

        if client:
            client.table("paper_chunks").upsert(
                db_records,
                on_conflict="paper_id,chunk_index",
            ).execute()

            # Store holistic paper embedding from combined page text
            full_pdf_text = "\n".join(p.get("text", "") for p in pages_data)
            if full_pdf_text:
                try:
                    paper_embedding = self.embedding_service.embed_text(full_pdf_text[:10000])
                    client.table("paper_embeddings").upsert(
                        {"paper_id": paper_id, "embedding": paper_embedding},
                        on_conflict="paper_id",
                    ).execute()
                except Exception as e:
                    logger.error(f"Failed to generate paper-level embedding: {e}")

            now_iso = datetime.now(timezone.utc).isoformat()
            client.table("papers").update({"indexed_at": now_iso, "full_text": full_pdf_text[:50000]}).eq("id", paper_id).execute()

        return IndexPaperResponse(
            paper_id=paper_id,
            chunks_created=len(chunks),
            chunks=chunk_infos,
            status="success",
            message=f"Indexed {len(chunks)} PDF page chunks for paper {paper_id}.",
        )

