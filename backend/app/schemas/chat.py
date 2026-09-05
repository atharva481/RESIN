from typing import List, Optional
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str = Field(..., description="Role of the speaker: 'user' or 'assistant'")
    content: str = Field(..., description="Message text content")


class ChatRequest(BaseModel):
    paper_id: Optional[str] = Field(None, description="Target paper UUID (optional for library chat)")
    message: str = Field(..., description="User question / prompt")
    history: Optional[List[ChatMessage]] = Field(default=[], description="Previous conversation turns")
    folder_id: Optional[str] = Field(None, description="Optional folder UUID for scoped search")


class Citation(BaseModel):
    paper_id: Optional[str] = Field(None, description="Target paper UUID")
    paper_title: Optional[str] = Field(None, description="Title of cited paper")
    document_id: Optional[str] = Field(None, description="Document checksum or ID")
    chunk_id: Optional[str] = Field(None, description="Chunk UUID or identifier")
    chunk_index: int = Field(0, description="Index of the chunk cited")
    page_number: Optional[int] = Field(None, description="PDF page number of snippet")
    section_title: Optional[str] = Field(None, description="Section heading in the paper")
    content_snippet: str = Field(..., description="Snippet of context cited")
    similarity_score: float = Field(0.0, description="Vector similarity score")


class ChatResponse(BaseModel):
    answer: str = Field(..., description="Generated answer from RAG model")
    citations: List[Citation] = Field(default=[], description="List of source citations used")

