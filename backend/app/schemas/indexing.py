from typing import Literal, List, Optional
from pydantic import BaseModel, Field


class IndexPaperRequest(BaseModel):
    paper_id: str = Field(..., description="UUID of the paper to chunk and embed")
    full_text: Optional[str] = Field(None, description="Full paper text if available")
    sections: Optional[dict] = Field(None, description="Optional section map {'Intro': '...', ...}")


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
