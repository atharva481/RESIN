from typing import Literal, List, Optional
from pydantic import BaseModel, Field


class IndexPaperRequest(BaseModel):
    paper_id: str = Field(..., description="UUID or identifier of the paper to chunk and embed")
    full_text: Optional[str] = Field(None, description="Full paper text if available")
    sections: Optional[dict] = Field(None, description="Optional section map {'Intro': '...', ...}")
    force: bool = Field(False, description="Force re-indexing even if paper chunks already exist")
    title: Optional[str] = Field(None, description="Paper title")
    doi: Optional[str] = Field(None, description="Paper DOI")
    arxiv_id: Optional[str] = Field(None, description="Paper arXiv ID")
    open_access_url: Optional[str] = Field(None, description="Paper open-access URL")
    abstract: Optional[str] = Field(None, description="Paper abstract")


class ChunkInfo(BaseModel):
    chunk_index: int
    section_title: Optional[str] = None
    word_count: int


class IndexPaperResponse(BaseModel):
    paper_id: str
    chunks_created: int
    chunks: List[ChunkInfo]
    status: Literal["success", "warning", "error"] = "success"
    message: str = "Paper successfully chunked and embedded."
