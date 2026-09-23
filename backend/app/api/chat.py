import json
import queue
import threading
from typing import Generator, Optional
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from app.agent.agent import ResearchAgent
from app.core.auth import get_current_user_id
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_service import load_chat_history, save_chat_turn
from app.services.rag import RAGService
from app.services.redis_cache import RedisCacheService

from app.core.timing import StageTimer, logger as timing_logger

router = APIRouter()
rag_service = RAGService()
cache_service = RedisCacheService()
research_agent = ResearchAgent()


@router.post("/chat", response_model=ChatResponse)
def chat_endpoint(
    payload: ChatRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Synchronous single-paper RAG Q&A with Redis response caching."""
    timer = StageTimer()
    try:
        if payload.paper_id:
            from app.services.paper_resolution import resolve_paper_record
            canonical_id, _ = resolve_paper_record(
                paper_id=payload.paper_id,
                doi=payload.doi,
                title=payload.title,
            )

            cached = cache_service.get_cached_response(canonical_id, payload.message)
            if cached is not None:
                timing_logger.info(f"[{timer.request_id}] CACHE HIT")
                timer.mark("cache_hit")
                return ChatResponse(**cached)
            else:
                timing_logger.info(f"[{timer.request_id}] CACHE MISS")
                timer.mark("cache_miss")

            response = rag_service.answer_question(
                paper_id=canonical_id,
                question=payload.message,
                history=payload.history,
                timer=timer,
            )

            save_chat_turn(user_id, None, "user", payload.message)
            save_chat_turn(user_id, None, "assistant", response.answer)
            if not response.answer.startswith("This paper hasn't") and not response.answer.startswith("Indexing failed:"):
                cache_service.set_cached_response(canonical_id, payload.message, response.model_dump())
            return response

        # If paper_id is omitted, delegate to ResearchAgent
        save_chat_turn(user_id, payload.folder_id, "user", payload.message)
        response = research_agent.execute_agent_loop(
            user_id=user_id,
            user_prompt=payload.message,
            folder_id=payload.folder_id,
            history=payload.history,
        )
        save_chat_turn(user_id, payload.folder_id, "assistant", response.answer)
        return response
    finally:
        timing_logger.info(f"[{timer.request_id}] SUMMARY: {timer.summary()}")


@router.post("/chat/stream")
def chat_stream_endpoint(
    payload: ChatRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Server-Sent Events streaming RAG & Agent endpoint."""
    timer = StageTimer()
    if payload.paper_id:
        from app.services.paper_resolution import resolve_paper_record
        canonical_id, _ = resolve_paper_record(
            paper_id=payload.paper_id,
            doi=payload.doi,
            title=payload.title,
        )

        return StreamingResponse(
            rag_service.stream_answer(
                paper_id=canonical_id,
                question=payload.message,
                history=payload.history,
                timer=timer,
                user_id=user_id,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # Stream agent execution events for multi-paper / library research
    def agent_event_generator() -> Generator[str, None, None]:
        q: queue.Queue = queue.Queue()

        def event_callback(event_dict: dict):
            q.put(event_dict)

        def run_agent():
            try:
                save_chat_turn(user_id, payload.folder_id, "user", payload.message)
                res = research_agent.execute_agent_loop(
                    user_id=user_id,
                    user_prompt=payload.message,
                    folder_id=payload.folder_id,
                    history=payload.history,
                    on_event=event_callback,
                )
                save_chat_turn(user_id, payload.folder_id, "assistant", res.answer)
            except Exception as e:
                q.put({"type": "error", "message": str(e)})
            finally:
                q.put(None)  # Sentinel to end stream

        t = threading.Thread(target=run_agent, daemon=True)
        t.start()

        while True:
            evt = q.get()
            if evt is None:
                break
            payload_str = json.dumps(evt)
            yield f"data: {payload_str}\n\n"

    return StreamingResponse(agent_event_generator(), media_type="text/event-stream")


@router.post("/folder_chat", response_model=ChatResponse)
def folder_chat_endpoint(
    payload: ChatRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Autonomous Agentic Research Assistant Q&A over library or folder.
    Executes search, OA PDF discovery, ingestion, 2-stage retrieval, and citations.
    """
    save_chat_turn(user_id, payload.folder_id, "user", payload.message)

    response = research_agent.execute_agent_loop(
        user_id=user_id,
        user_prompt=payload.message,
        folder_id=payload.folder_id,
        history=payload.history,
    )

    save_chat_turn(user_id, payload.folder_id, "assistant", response.answer)
    return response


@router.get("/folder_chat_history")
def get_folder_chat_history(
    folder_id: Optional[str] = None,
    user_id: str = Depends(get_current_user_id),
):
    """Retrieve chat history for a user, optionally filtered by folder."""
    history = load_chat_history(user_id, folder_id, limit=200)
    return {"history": history}
