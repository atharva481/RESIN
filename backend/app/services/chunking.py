import logging
import re
from typing import Dict, List, Optional, Union
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class TextChunk(BaseModel):
    chunk_index: int
    section_title: Optional[str] = None
    content: str
    word_count: int
    paper_id: str


class TextChunker:
    """Service for section-aware text chunking with word overlap."""

    def __init__(self, chunk_size: int = 600, overlap_size: int = 100, min_chunk_size: int = 100):
        self.chunk_size = chunk_size
        self.overlap_size = overlap_size
        self.min_chunk_size = min_chunk_size

        if overlap_size >= chunk_size:
            raise ValueError("Overlap size must be less than chunk size")

    def _split_into_words(self, text: str) -> List[str]:
        return re.findall(r"\S+", text)

    def _reconstruct_text(self, words: List[str]) -> str:
        return " ".join(words)

    def chunk_paper(
        self,
        paper_id: str,
        title: str,
        abstract: str,
        full_text: Optional[str] = None,
        sections: Optional[Union[Dict[str, str], str, list]] = None,
    ) -> List[TextChunk]:
        """Chunk paper using section structure or fall back to text overlap."""
        chunks: List[TextChunk] = []

        # If explicit sections provided
        if sections and isinstance(sections, dict):
            idx = 0
            for sec_title, sec_content in sections.items():
                sec_words = self._split_into_words(sec_content)
                word_count = len(sec_words)

                if word_count <= self.chunk_size:
                    chunks.append(
                        TextChunk(
                            chunk_index=idx,
                            section_title=sec_title,
                            content=f"[{sec_title}]\n{sec_content.strip()}",
                            word_count=word_count,
                            paper_id=paper_id,
                        )
                    )
                    idx += 1
                else:
                    # Sub-chunk section
                    sub_chunks = self.chunk_text(
                        text=sec_content,
                        paper_id=paper_id,
                        start_index=idx,
                        section_title=sec_title,
                    )
                    chunks.extend(sub_chunks)
                    idx += len(sub_chunks)

            if chunks:
                return chunks

        # Fallback: full text or title + abstract
        combined_text = full_text if full_text and len(full_text.strip()) > 0 else f"Title: {title}\n\nAbstract: {abstract}"
        return self.chunk_text(text=combined_text, paper_id=paper_id, start_index=0, section_title="Main Content")

    def chunk_text(
        self,
        text: str,
        paper_id: str,
        start_index: int = 0,
        section_title: Optional[str] = None,
    ) -> List[TextChunk]:
        words = self._split_into_words(text)
        if not words:
            return []

        chunks: List[TextChunk] = []
        i = 0
        chunk_idx = start_index

        while i < len(words):
            chunk_words = words[i : i + self.chunk_size]
            chunk_str = self._reconstruct_text(chunk_words)

            prefix = f"[{section_title}]\n" if section_title else ""
            chunks.append(
                TextChunk(
                    chunk_index=chunk_idx,
                    section_title=section_title,
                    content=f"{prefix}{chunk_str}",
                    word_count=len(chunk_words),
                    paper_id=paper_id,
                )
            )
            chunk_idx += 1

            if i + self.chunk_size >= len(words):
                break
            i += self.chunk_size - self.overlap_size

        return chunks
