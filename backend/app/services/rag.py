import json
import logging
import re
import time
from typing import Any, Dict, Generator, List, Optional
import google.generativeai as genai
from app.core.config import settings
from app.core.supabase import get_supabase_client
from app.schemas.chat import ChatMessage, ChatResponse, Citation
from app.services.retrieval import RetrievalService

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 2.0  # seconds


def _ensure_configured():
    if settings.gemini_api_key and settings.gemini_api_key != "placeholder-gemini-key":
        genai.configure(api_key=settings.gemini_api_key)


_ensure_configured()


def _parse_retry_delay(error_msg: str) -> float:
    """Parse recommended retry seconds from 429 error message if available."""
    match = re.search(r"retry in ([0-9\.]+)s", error_msg, re.IGNORECASE)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass
    return 10.0


def _with_retry(fn, *args, max_retries=MAX_RETRIES, retry_delay=RETRY_DELAY, **kwargs):
    """Retry a Gemini API call with exponential backoff and 429 rate-limit handling."""
    _ensure_configured()
    last_exc = None
    for attempt in range(1, max_retries + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_exc = e
            err_str = str(e)
            if "404" in err_str or "not found" in err_str or "no longer available" in err_str:
                raise e
            if "429" in err_str or "quota" in err_str.lower():
                wait = _parse_retry_delay(err_str)
                if attempt < max_retries:
                    logger.warning(
                        f"Gemini API rate limited (429). Waiting {wait:.1f}s before retry (attempt {attempt}/{max_retries})..."
                    )
                    time.sleep(min(wait, 12.0))
                    continue
            elif attempt < max_retries:
                wait = retry_delay * (2 ** (attempt - 1))
                logger.warning(f"Gemini API attempt {attempt} failed: {e}. Retrying in {wait}s...")
                time.sleep(wait)
    logger.error(f"Gemini API failed after {max_retries} attempts: {last_exc}")
    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"Gemini API failed after {max_retries} attempts.")


SYSTEM_RAG_PROMPT = """You are an expert scientific AI research assistant for the RESIN platform.
Answer the user's question accurately based strictly on the provided research paper context chunks below.

Guidelines:
1. Cite relevant paper sections using inline section titles, e.g. [Section: Abstract] or [Section: Results].
2. If the context does not contain sufficient details to answer the question, state that clearly rather than hallucinating.
3. Be clear, concise, and academically rigorous.

Paper Context Chunks:
{context_blocks}
"""


class RAGService:
    """Service orchestrating context retrieval and Gemini Flash generation."""

    def __init__(self, retrieval_service: Optional[RetrievalService] = None):
        self.retrieval_service = retrieval_service or RetrievalService()
        self.model_name = settings.gemini_chat_model
        _ensure_configured()

    def _format_context(self, citations: List[Citation]) -> str:
        """Format chunk citations into text blocks for RAG prompt."""
        if not citations:
            return "No relevant paper context chunks found."
        blocks = []
        for cit in citations:
            sec = cit.section_title or f"Chunk {cit.chunk_index}"
            snippet = cit.content_snippet
            blocks.append(f"--- Section: {sec} ---\n{snippet}")
        return "\n\n".join(blocks)

    def _format_context_from_papers(self, paper_rows: List[Dict[str, Any]]) -> str:
        """Format paper rows (with title, abstract) into context blocks."""
        if not paper_rows:
            return "No relevant papers found."
        blocks = []
        for idx, paper in enumerate(paper_rows, 1):
            title = paper.get("title", "Untitled")
            abstract = paper.get("abstract", "")
            block = f"--- Paper {idx} ---\nTitle: {title}\nAbstract: {abstract}"
            blocks.append(block)
        return "\n\n".join(blocks)

    def _get_chat_models(self) -> List[str]:
        raw = [
            self.model_name,
            "models/gemini-flash-latest",
            "models/gemini-3.6-flash",
            "models/gemini-3.5-flash",
            "gemini-flash-latest",
        ]
        unique = []
        for m in raw:
            if m and m not in unique:
                unique.append(m)
        return unique

    def answer_question(
        self,
        paper_id: str,
        question: str,
        history: Optional[List[ChatMessage]] = None,
    ) -> ChatResponse:
        """Retrieve relevant context and generate answer using Gemini (single paper)."""
        citations = self.retrieval_service.retrieve_context(
            query=question,
            paper_id=paper_id,
            top_k=4,
        )

        context_str = self._format_context(citations)
        system_instruction = SYSTEM_RAG_PROMPT.format(context_blocks=context_str)

        prompt = question
        if history:
            prev_convo = "\n".join([f"{msg.role.capitalize()}: {msg.content}" for msg in history[-4:]])
            prompt = f"Previous conversation:\n{prev_convo}\n\nCurrent Question: {question}"

        full_prompt = f"{system_instruction}\n\n{prompt}"
        models = self._get_chat_models()

        last_error = None
        for m_name in models:
            try:
                model = genai.GenerativeModel(model_name=m_name)
                response = _with_retry(model.generate_content, full_prompt)
                answer_text = response.text if response and hasattr(response, "text") else "No answer generated."
                return ChatResponse(answer=answer_text, citations=citations)
            except Exception as e:
                last_error = e
                logger.warning(f"Chat model {m_name} failed: {e}. Trying next chat model...")

        err_msg = str(last_error)
        if "429" in err_msg or "quota" in err_msg.lower():
            user_msg = "Gemini free tier rate limit reached. Please wait ~10 seconds and ask your question again."
        else:
            user_msg = f"I encountered an error generating the answer: {err_msg}"

        return ChatResponse(answer=user_msg, citations=citations)

    def answer_question_for_user(
        self,
        user_id: str,
        question: str,
        folder_id: Optional[str] = None,
        history: Optional[List[ChatMessage]] = None,
        top_k: int = 5,
        similarity_threshold: float = 0.25,
    ) -> ChatResponse:
        """Retrieve relevant papers for a user (optionally folder) and generate answer using Gemini."""
        # 1. Get candidate paper IDs with similarity scores
        paper_matches = self.retrieval_service.retrieve_paper_ids_for_user(
            query=question,
            user_id=user_id,
            folder_id=folder_id,
            top_k=top_k,
            similarity_threshold=similarity_threshold,
        )
        if not paper_matches:
            # No relevant papers
            answer = "I couldn't find any relevant papers in your library to answer that question."
            return ChatResponse(answer=answer, citations=[])

        paper_ids = [m["paper_id"] for m in paper_matches]

        # 2. Fetch paper details (title, abstract) from papers table
        supabase = get_supabase_client()
        if not supabase:
            logger.error("Supabase client not initialized.")
            answer = "Internal error: could not access database."
            return ChatResponse(answer=answer, citations=[])

        try:
            papers_resp = (
                supabase.table("papers")
                .select("id,title,abstract")
                .in_("id", paper_ids)
                .execute()
            )
            paper_rows = papers_resp.data or []
        except Exception as e:
            logger.error(f"Failed to fetch papers: {e}")
            answer = "Internal error while fetching paper details."
            return ChatResponse(answer=answer, citations=[])

        # 3. Build context from paper title+abstract
        context_str = self._format_context_from_papers(paper_rows)
        system_instruction = SYSTEM_RAG_PROMPT.format(context_blocks=context_str)

        # 4. Build prompt with history
        prompt = question
        if history:
            prev_convo = "\n".join([f"{msg.role.capitalize()}: {msg.content}" for msg in history[-4:]])
            prompt = f"Previous conversation:\n{prev_convo}\n\nCurrent Question: {question}"

        full_prompt = f"{system_instruction}\n\n{prompt}"
        models = self._get_chat_models()

        last_error = None
        for m_name in models:
            try:
                model = genai.GenerativeModel(model_name=m_name)
                response = _with_retry(model.generate_content, full_prompt)
                answer_text = response.text if response and hasattr(response, "text") else "No answer generated."
                # Build citations list for compatibility (we can reuse paper_matches as citations)
                citations = [
                    {
                        "paper_id": m["paper_id"],
                        "similarity": m.get("similarity", 0.0),
                        "title": next((p.get("title", "") for p in paper_rows if p.get("id") == m["paper_id"]), ""),
                        "abstract": next((p.get("abstract", "") for p in paper_rows if p.get("id") == m["paper_id"]), ""),
                    }
                    for m in paper_matches
                ]
                return ChatResponse(answer=answer_text, citations=citations)  # type: ignore
            except Exception as e:
                last_error = e
                logger.warning(f"Chat model {m_name} failed: {e}. Trying next chat model...")

        err_msg = str(last_error)
        if "429" in err_msg or "quota" in err_msg.lower():
            user_msg = "Gemini free tier rate limit reached. Please wait ~10 seconds and ask your question again."
        else:
            user_msg = f"I encountered an error generating the answer: {err_msg}"
        return ChatResponse(answer=user_msg, citations=[])

    def stream_answer(
        self,
        paper_id: str,
        question: str,
        history: Optional[List[ChatMessage]] = None,
    ) -> Generator[str, None, None]:
        """Stream RAG response chunks as Server-Sent Events."""
        try:
            citations = self.retrieval_service.retrieve_context(
                query=question,
                paper_id=paper_id,
                top_k=4,
            )
            context_str = self._format_context(citations)
            system_instruction = SYSTEM_RAG_PROMPT.format(context_blocks=context_str)
        except Exception as e:
            logger.error(f"Retrieval error in stream: {e}")
            err_payload = json.dumps({"error": f"Retrieval failed: {str(e)}"})
            yield f"data: {err_payload}\n\n"
            return

        prompt = question
        if history:
            prev_convo = "\n".join(
                [f"{msg.role.capitalize()}: {msg.content}" for msg in history[-4:]]
            )
            prompt = f"Previous conversation:\n{prev_convo}\n\nCurrent Question: {question}"

        full_prompt = f"{system_instruction}\n\n{prompt}"
        models = self._get_chat_models()

        stream_started = False
        last_error = None

        for m_name in models:
            try:
                model = genai.GenerativeModel(model_name=m_name)
                response = _with_retry(model.generate_content, full_prompt, stream=True)
                for chunk in response:
                    try:
                        text = chunk.text
                        if text:
                            stream_started = True
                            payload = json.dumps({"text": text})
                            yield f"data: {payload}\n\n"
                    except Exception as chunk_err:
                        logger.warning(f"Skipping unreadable stream chunk: {chunk_err}")
                if stream_started:
                    return
            except Exception as e:
                last_error = e
                logger.warning(f"Streaming chat model {m_name} failed: {e}")

        if not stream_started and last_error:
            err_msg = str(last_error)
            if "429" in err_msg or "quota" in err_msg.lower():
                user_msg = "Gemini free tier rate limit reached. Please wait ~10 seconds before asking again."
            else:
                user_msg = f"Streaming error: {err_msg}"
            err_payload = json.dumps({"error": user_msg})
            yield f"data: {err_payload}\n\n"
