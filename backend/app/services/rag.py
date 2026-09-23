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

from app.agent.formatter import (
    clean_markdown_output,
    detect_question_intent,
    get_intent_formatting_instructions,
)

logger = logging.getLogger(__name__)

from app.services.gemini_service import (
    GeminiService,
    classify_gemini_error,
    ensure_gemini_configured as _ensure_configured,
)


def _with_retry(fn, *args, **kwargs):
    """Execute Gemini API call using centralized GeminiService."""
    return GeminiService.call_with_retry(fn, *args, **kwargs)


SYSTEM_RAG_PROMPT = r"""You are an expert scientific AI research assistant for the RESIN platform.
Answer the user's question accurately based strictly on the provided research paper evidence below.

ANSWER FORMAT & READABILITY RULES:
1. Always generate valid unescaped Markdown (- **Bold**, *italic*, `code`, ### Heading). Never output escaped markdown like \* \*\*text\*\*.
2. Answer DIRECTLY. Never start with "Based on the provided context...", "According to the retrieved context...", or "From the information provided...".
3. Keep paragraphs short (2-4 sentences). Use bullet lists for methods/findings, numbered lists for procedures, and Markdown tables ONLY for comparisons.
4. Adapt answer structure dynamically to the query (simple questions get direct answers; complex questions get structured sections).
5. Never expose internal system tags like [Section: Main Content].
6. Grounding: Answer strictly from provided evidence. If details are insufficient to answer confidently, state: "I couldn't find enough evidence in the indexed paper to answer that confidently."

{formatting_instructions}

Paper Evidence Context:
{context_blocks}
"""


class RAGService:
    """Service orchestrating context retrieval and Gemini Flash generation."""

    def __init__(self, retrieval_service: Optional[RetrievalService] = None):
        self.retrieval_service = retrieval_service or RetrievalService()
        self.model_name = settings.gemini_chat_model
        _ensure_configured()

    def _format_context(self, citations: List[Citation], max_snippet_chars: int = 1200) -> str:
        """Format chunk citations into clean, high-density text evidence blocks for RAG prompt."""
        if not citations:
            return "No relevant paper context chunks found."
        blocks = []
        for cit in citations:
            sec = cit.section_title or f"Chunk #{cit.chunk_index}"
            if sec.startswith("[Section:") and sec.endswith("]"):
                sec = sec[9:-1].strip()
            page_str = f" | Page {cit.page_number}" if cit.page_number else ""
            title_str = f"Paper: {cit.paper_title}\n" if cit.paper_title else ""
            snippet = cit.content_snippet.strip()
            if len(snippet) > max_snippet_chars:
                snippet = snippet[:max_snippet_chars].rsplit(" ", 1)[0] + "..."
            blocks.append(f"{title_str}Section: {sec}{page_str}\nEvidence:\n{snippet}")
        return "\n\n".join(blocks)

    def _format_context_from_papers(self, paper_rows: List[Dict[str, Any]]) -> str:
        """Format paper rows (with title, abstract) into context blocks."""
        if not paper_rows:
            return "No relevant papers found."
        blocks = []
        for idx, paper in enumerate(paper_rows, 1):
            title = paper.get("title", "Untitled")
            abstract = paper.get("abstract", "")
            block = f"Paper {idx}: {title}\nAbstract: {abstract}"
            blocks.append(block)
        return "\n\n".join(blocks)

    def _get_chat_models(self) -> List[str]:
        raw = [
            self.model_name,
            "models/gemini-3.5-flash-lite",
            "models/gemini-3.1-flash-lite",
        ]
        unique = []
        for m in raw:
            if m and m not in unique:
                unique.append(m)
        return GeminiService.get_prioritized_models(unique)

    def _get_unindexed_paper_message(self, paper_id: str, client: Optional[Any] = None) -> str:
        """
        Differentiate between in-progress/not-yet-attempted indexing and attempted-and-failed indexing.
        Check papers table's status/error fields.
        """
        if not client:
            client = get_supabase_client()

        paper_row = None
        if client and paper_id:
            try:
                res = client.table("papers").select("indexing_status,indexing_error").eq("id", paper_id).limit(1).execute()
                if not res.data:
                    res = client.table("papers").select("indexing_status,indexing_error").or_(
                        f"semantic_scholar_id.eq.{paper_id},arxiv_id.eq.{paper_id}"
                    ).limit(1).execute()
                if res.data:
                    paper_row = res.data[0]
            except Exception as e:
                logger.warning(f"Could not query indexing status for paper {paper_id}: {e}")

        status = (paper_row.get("indexing_status") or "").lower() if paper_row else ""
        error = paper_row.get("indexing_error") if paper_row else None

        if status == "failed" or error:
            reason = error or "Unknown failure reason"
            return f"Indexing failed: {reason}. Try re-indexing or use a different source PDF."

        return "This paper hasn't finished indexing yet. Please wait a moment and try again."

    def answer_question(
        self,
        paper_id: str,
        question: str,
        history: Optional[List[ChatMessage]] = None,
        timer: Optional[Any] = None,
    ) -> ChatResponse:
        """Retrieve relevant context and generate answer using Gemini (single paper)."""
        client = get_supabase_client()
        chunk_count = 0
        if client and paper_id:
            try:
                chk = client.table("paper_chunks").select("id", count="exact").eq("paper_id", paper_id).limit(1).execute()
                chunk_count = chk.count or 0
            except Exception as chk_e:
                logger.warning(f"Could not check chunk count for {paper_id}: {chk_e}")
                chunk_count = 5
        if timer:
            timer.mark("index_cache_check", extra=f"chunks={chunk_count}")

        # Short-circuit immediately if unindexed to avoid wasting ~900ms on query_embedding and retrieval RPC
        if chunk_count == 0:
            if timer:
                timer.mark("skipped_empty_index")
            answer_text = self._get_unindexed_paper_message(paper_id, client)
            return ChatResponse(
                answer=answer_text,
                citations=[],
            )

        citations = self.retrieval_service.retrieve_context(
            query=question,
            paper_id=paper_id,
            top_k=3,
            timer=timer,
        )

        intent = detect_question_intent(question)
        fmt_instructions = get_intent_formatting_instructions(intent)
        context_str = self._format_context(citations)
        system_instruction = SYSTEM_RAG_PROMPT.format(
            formatting_instructions=fmt_instructions,
            context_blocks=context_str,
        )

        prompt = question
        if history:
            # Compact history to last 2 turns with trimmed assistant replies to avoid free-tier TPM quota exhaustion
            compact_convo = []
            for msg in history[-2:]:
                content = msg.content
                if msg.role == "assistant" and len(content) > 250:
                    content = content[:250].rsplit(" ", 1)[0] + "..."
                compact_convo.append(f"{msg.role.capitalize()}: {content}")
            prompt = f"Previous conversation:\n" + "\n".join(compact_convo) + f"\n\nCurrent Question: {question}"

        full_prompt = f"{system_instruction}\n\n{prompt}"
        if timer:
            timer.mark("context_assembly")

        models = self._get_chat_models()
        default_primary = self.model_name
        last_error = None

        for idx, m_name in enumerate(models):
            is_fallback = (m_name != default_primary) or (idx > 0)
            fallback_reason = f"Previous attempt failed ({last_error})" if idx > 0 else ("Primary model on cooldown" if m_name != default_primary else "")
            GeminiService.log_model_usage(
                model_name=m_name,
                is_fallback=is_fallback,
                reason=fallback_reason,
                timer=timer,
            )
            try:
                model = genai.GenerativeModel(model_name=m_name)
                response = _with_retry(model.generate_content, full_prompt)
                if timer:
                    timer.mark("generation_complete")
                raw_answer = response.text if response and hasattr(response, "text") else "No answer generated."
                clean_answer = clean_markdown_output(raw_answer)
                return ChatResponse(answer=clean_answer, citations=citations)
            except Exception as e:
                last_error = e
                is_daily, is_transient, _ = classify_gemini_error(e)
                if is_daily:
                    logger.error(f"Gemini daily quota exhausted in answer_question: {e}")
                    user_msg = "⚠️ Gemini API daily quota reached (429 RESOURCE_EXHAUSTED). Please wait for your daily quota to reset or upgrade your tier in Google AI Studio."
                    return ChatResponse(answer=user_msg, citations=citations)

                # Mark this model on 60s cooldown so subsequent requests skip straight to healthy fallback
                GeminiService.mark_model_cooldown(m_name, cooldown_seconds=60.0, reason=str(e))
                logger.warning(f"Chat model {m_name} failed ({e}). Marked on 60s cooldown; trying next prioritized model...")

        err_msg = str(last_error)
        is_daily, is_transient, _ = classify_gemini_error(last_error) if last_error else (False, False, 0)
        if is_daily:
            user_msg = "⚠️ Gemini API daily quota reached (429 RESOURCE_EXHAUSTED). Please wait for your daily quota to reset or upgrade your tier in Google AI Studio."
        elif is_transient:
            user_msg = "Gemini rate limit reached (429). Please wait ~5 seconds and ask your question again."
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
        similarity_threshold: float = 0.20,
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
        intent = detect_question_intent(question)
        fmt_instructions = get_intent_formatting_instructions(intent)
        context_str = self._format_context_from_papers(paper_rows)
        system_instruction = SYSTEM_RAG_PROMPT.format(
            formatting_instructions=fmt_instructions,
            context_blocks=context_str,
        )

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
                raw_text = response.text if response and hasattr(response, "text") else "No answer generated."
                clean_answer = clean_markdown_output(raw_text)
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
                return ChatResponse(answer=clean_answer, citations=citations)  # type: ignore
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
        timer: Optional[Any] = None,
        user_id: Optional[str] = None,
    ) -> Generator[str, None, None]:
        """Stream RAG response chunks as Server-Sent Events."""
        try:
            # 1. Guard against unindexed / partial-indexed papers
            client = get_supabase_client()
            chunk_count = 0
            if client and paper_id:
                try:
                    chk = client.table("paper_chunks").select("id", count="exact").eq("paper_id", paper_id).limit(1).execute()
                    chunk_count = chk.count or 0
                except Exception as chk_e:
                    logger.warning(f"Could not check chunk count for {paper_id}: {chk_e}")
                    chunk_count = 5  # Assume okay on db error to not block user

            if timer:
                timer.mark("index_cache_check", extra=f"chunks={chunk_count}")

            if chunk_count == 0:
                if timer:
                    timer.mark("skipped_empty_index")
                answer_text = self._get_unindexed_paper_message(paper_id, client)
                if user_id:
                    try:
                        from app.services.chat_service import save_chat_turn
                        save_chat_turn(user_id, None, "user", question)
                        save_chat_turn(user_id, None, "assistant", answer_text)
                    except Exception as he:
                        logger.warning(f"Could not save chat turn for short-circuit: {he}")
                yield f"data: {json.dumps({'text': answer_text})}\n\n"
                return

            if 0 < chunk_count < 5:
                notice = f"> ⚠️ **Notice:** This paper was only partially indexed ({chunk_count} chunk{'s' if chunk_count > 1 else ''}). Answers may lack complete evidence. Click **Re-index** above to fetch and index the complete manuscript.\n\n"
                yield f"data: {json.dumps({'text': notice})}\n\n"

            # 2. Retrieve evidence context
            try:
                citations = self.retrieval_service.retrieve_context(
                    query=question,
                    paper_id=paper_id,
                    top_k=3,
                    timer=timer,
                )
                intent = detect_question_intent(question)
                fmt_instructions = get_intent_formatting_instructions(intent)
                context_str = self._format_context(citations)
                system_instruction = SYSTEM_RAG_PROMPT.format(
                    formatting_instructions=fmt_instructions,
                    context_blocks=context_str,
                )
            except Exception as e:
                logger.error(f"Retrieval error in stream: {e}")
                err_payload = json.dumps({"error": f"Retrieval failed: {str(e)}"})
                yield f"data: {err_payload}\n\n"
                return

            prompt = question
            if history:
                # Compact history to last 2 turns with trimmed assistant replies to avoid free-tier TPM quota exhaustion
                compact_convo = []
                for msg in history[-2:]:
                    content = msg.content
                    if msg.role == "assistant" and len(content) > 250:
                        content = content[:250].rsplit(" ", 1)[0] + "..."
                    compact_convo.append(f"{msg.role.capitalize()}: {content}")
                prompt = f"Previous conversation:\n" + "\n".join(compact_convo) + f"\n\nCurrent Question: {question}"

            full_prompt = f"{system_instruction}\n\n{prompt}"
            if timer:
                timer.mark("context_assembly")

            models = self._get_chat_models()
            default_primary = self.model_name
            stream_started = False
            first_token_received = False
            last_error = None

            for idx, m_name in enumerate(models):
                is_fallback = (m_name != default_primary) or (idx > 0)
                fallback_reason = f"Previous model attempt failed ({last_error})" if idx > 0 else ("Primary model on cooldown" if m_name != default_primary else "")
                GeminiService.log_model_usage(
                    model_name=m_name,
                    is_fallback=is_fallback,
                    reason=fallback_reason,
                    timer=timer,
                )
                try:
                    model = genai.GenerativeModel(model_name=m_name)
                    response = _with_retry(model.generate_content, full_prompt, stream=True)
                    full_response_text = ""
                    for chunk in response:
                        try:
                            text = chunk.text
                            if text:
                                full_response_text += text
                                if not first_token_received:
                                    first_token_received = True
                                    if timer:
                                        timer.mark("ttft")
                                stream_started = True
                                payload = json.dumps({"text": text})
                                yield f"data: {payload}\n\n"

                        except Exception as chunk_err:
                            logger.warning(f"Skipping unreadable stream chunk: {chunk_err}")
                    if stream_started:
                        if timer:
                            timer.mark("generation_complete")
                        if user_id and full_response_text:
                            try:
                                from app.services.chat_service import save_chat_turn
                                save_chat_turn(user_id, None, "user", question)
                                save_chat_turn(user_id, None, "assistant", full_response_text)
                            except Exception as he:
                                logger.warning(f"Could not save streaming chat turn: {he}")
                        return
                except Exception as e:
                    last_error = e
                    is_daily, is_transient, _ = classify_gemini_error(e)
                    if is_daily:
                        logger.error(f"Gemini daily quota exhausted in stream_answer: {e}")
                        err_payload = json.dumps({
                            "error": "⚠️ Gemini API daily quota reached (429 RESOURCE_EXHAUSTED). Please wait for your daily quota to reset or upgrade your tier in Google AI Studio."
                        })
                        yield f"data: {err_payload}\n\n"
                        return

                    # Mark this model on 60s cooldown so subsequent requests skip straight to healthy fallback
                    GeminiService.mark_model_cooldown(m_name, cooldown_seconds=60.0, reason=str(e))

                    if stream_started:
                        # Do not attempt secondary models if streaming has already partially delivered tokens to client
                        err_payload = json.dumps({"error": f"Stream interrupted: {str(e)}"})
                        yield f"data: {err_payload}\n\n"
                        return

                    logger.warning(f"Streaming chat model {m_name} failed ({e}). Trying next prioritized model...")

            if not stream_started and last_error:
                is_daily, is_transient, _ = classify_gemini_error(last_error)
                if is_daily:
                    user_msg = "⚠️ Gemini API daily quota reached (429 RESOURCE_EXHAUSTED). Please wait for your daily quota to reset or upgrade your tier in Google AI Studio."
                elif is_transient:
                    user_msg = "Gemini rate limit reached (429). Please wait ~5 seconds before sending your next question."
                else:
                    user_msg = f"Streaming error: {str(last_error)}"
                err_payload = json.dumps({"error": user_msg})
                yield f"data: {err_payload}\n\n"
        finally:
            if timer:
                from app.core.timing import logger as timing_logger
                timing_logger.info(f"[{timer.request_id}] SUMMARY: {timer.summary()}")
