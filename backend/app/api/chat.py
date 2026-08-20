from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from app.core.auth import get_current_user_id
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.rag import RAGService
from app.services.redis_cache import RedisCacheService
from app.services.chat_service import save_chat_turn, load_chat_history

router = APIRouter()
rag_service = RAGService()
cache_service = RedisCacheService()


@router.post("/chat", response_model=ChatResponse)
def chat_endpoint(
    payload: ChatRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Synchronous RAG Q&A over paper chunks (single paper)."""
    cached = cache_service.get_cached_response(payload.paper_id, payload.message)
    if cached:
        return ChatResponse(**cached)

    response = rag_service.answer_question(
        paper_id=payload.paper_id,
        question=payload.message,
        history=payload.history,
    )

    # persist user and assistant turns
    save_chat_turn(user_id, None, "user", payload.message)
    save_chat_turn(user_id, None, "assistant", response.answer)

    cache_service.set_cached_response(payload.paper_id, payload.message, response.model_dump())
    return response


@router.post("/chat/stream")
def chat_stream_endpoint(
    payload: ChatRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Server-Sent Events streaming RAG endpoint (single paper)."""
    return StreamingResponse(
        rag_service.stream_answer(
            paper_id=payload.paper_id,
            question=payload.message,
            history=payload.history,
        ),
        media_type="text/event-stream",
    )


@router.post("/folder_chat", response_model=ChatResponse)
def folder_chat_endpoint(
    payload: ChatRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    RAG Q&A over all papers in a user's library (or a specific folder).
    Persists conversation in chat_history.
    """
    # Persist user turn
    save_chat_turn(user_id, payload.folder_id, "user", payload.message)

    # Get answer using folder-level retrieval
    response = rag_service.answer_question_for_user(
        user_id=user_id,
        question=payload.message,
        folder_id=payload.folder_id,
        history=payload.history,
    )

    # Persist assistant turn
    save_chat_turn(user_id, payload.folder_id, "assistant", response.answer)

    return response


@router.get("/folder_chat_history")
def get_folder_chat_history(
    folder_id: Optional[str] = None,
    user_id: str = Depends(get_current_user_id),
):
    """
    Retrieve chat history for a user, optionally filtered by folder.
    Returns list of messages in chronological order.
    """
    history = load_chat_history(user_id, folder_id, limit=200)
    # Convert to list of dicts matching ChatMessage shape for frontend
    return {"history": history}
