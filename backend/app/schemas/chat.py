from typing import List, Optional
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str = Field(..., description="Role of the speaker: 'user' or 'assistant'")
    content: str = Field(..., description="Message text content")


class ChatRequest(BaseModel):
    paper_id: str = Field(..., description="Target paper UUID")
    message: str = Field(..., description="User question / prompt")
    history: Optional[List[ChatMessage]] = Field(default=[], description="Previous conversation turns")


class Citation(BaseModel):
    section_title: Optional[str] = Field(None, description="Section heading in the paper")
    chunk_index: int = Field(..., description="Index of the chunk cited")
    content_snippet: str = Field(..., description="Snippet of context cited")
    similarity_score: float = Field(..., description="Vector similarity score")


class ChatResponse(BaseModel):
    answer: str = Field(..., description="Generated answer from RAG model")
    citations: List[Citation] = Field(default=[], description="List of source citations used")
