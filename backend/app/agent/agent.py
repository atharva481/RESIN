import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional
import google.generativeai as genai
from app.agent.prompt import RESEARCH_AGENT_SYSTEM_PROMPT
from app.agent.tools import TOOL_DECLARATIONS, TOOL_REGISTRY
from app.core.config import settings
from app.core.supabase import get_supabase_client
from app.schemas.chat import ChatMessage, ChatResponse, Citation

from app.agent.formatter import (
    clean_markdown_output,
    detect_question_intent,
    get_intent_formatting_instructions,
)

logger = logging.getLogger(__name__)

MAX_TOOL_CALLS = 15


def _ensure_configured():
    if settings.gemini_api_key and settings.gemini_api_key != "placeholder-gemini-key":
        genai.configure(api_key=settings.gemini_api_key)


_ensure_configured()


class ResearchAgent:
    """Autonomous Research Agent powered by Gemini Tool Calling and Full-PDF RAG."""

    def __init__(self):
        self.model_name = settings.gemini_chat_model
        _ensure_configured()

    def _log_agent_run(self, user_id: str, status: str = "RUNNING") -> Optional[str]:
        supabase = get_supabase_client()
        if not supabase:
            return None
        try:
            res = (
                supabase.table("agent_runs")
                .insert({"user_id": user_id, "status": status})
                .execute()
            )
            if res.data:
                return res.data[0].get("id")
        except Exception as e:
            logger.warning(f"Could not log agent run for user {user_id}: {e}")
        return None

    def _update_agent_run(self, run_id: Optional[str], status: str):
        if not run_id:
            return
        supabase = get_supabase_client()
        if not supabase:
            return
        try:
            from datetime import datetime, timezone
            supabase.table("agent_runs").update({
                "status": status,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", run_id).execute()
        except Exception as e:
            logger.warning(f"Could not update agent run {run_id}: {e}")

    def _log_tool_call(
        self,
        run_id: Optional[str],
        tool_name: str,
        arguments: dict,
        result: dict,
        status: str = "SUCCESS",
    ):
        if not run_id:
            return
        supabase = get_supabase_client()
        if not supabase:
            return
        try:
            # Filter out sensitive internal keys before logging
            clean_args = {k: v for k, v in arguments.items() if k not in ("authenticated_user_id", "api_key", "secret")}
            supabase.table("tool_calls").insert({
                "agent_run_id": run_id,
                "tool_name": tool_name,
                "arguments": clean_args,
                "result": result,
                "status": status,
            }).execute()
        except Exception as e:
            logger.warning(f"Could not log tool call {tool_name} for run {run_id}: {e}")

    def execute_agent_loop(
        self,
        user_id: str,
        user_prompt: str,
        folder_id: Optional[str] = None,
        history: Optional[List[ChatMessage]] = None,
        on_event: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> ChatResponse:
        """
        Execute the autonomous agent loop:
        1. Initialize agent run log.
        2. Detect question intent & inject formatting instructions.
        3. Send user prompt and tools to Gemini.
        4. Loop up to MAX_TOOL_CALLS:
           - If Gemini calls a tool: execute tool, log call, stream status event, feed result back to Gemini.
           - Else if Gemini returns final text: sanitize response, format citations, update log, return ChatResponse.
        """
        _ensure_configured()
        run_id = self._log_agent_run(user_id=user_id)
        if on_event:
            on_event({"type": "status", "message": "Initializing Research Agent..."})

        # Detect intent and build prompt instructions
        intent = detect_question_intent(user_prompt)
        fmt_instructions = get_intent_formatting_instructions(intent)
        full_system_instruction = f"{RESEARCH_AGENT_SYSTEM_PROMPT}\n\n{fmt_instructions}"

        # Format conversation messages
        convo_messages = []
        if history:
            for msg in history[-4:]:
                convo_messages.append({"role": "user" if msg.role == "user" else "model", "parts": [msg.content]})

        convo_messages.append({"role": "user", "parts": [user_prompt]})

        # Initialize Gemini Model with tools & system instruction
        models_to_try = [self.model_name, "models/gemini-3.6-flash", "models/gemini-3.5-flash", "gemini-flash-latest"]
        model = None
        for m_name in models_to_try:
            try:
                model = genai.GenerativeModel(
                    model_name=m_name,
                    system_instruction=full_system_instruction,
                    tools=TOOL_DECLARATIONS,
                )
                break
            except Exception as e:
                logger.warning(f"Could not initialize GenerativeModel with {m_name}: {e}")

        if not model:
            # Fallback without system instruction parameter if unsupported by SDK version
            model = genai.GenerativeModel(model_name="models/gemini-flash-latest", tools=TOOL_DECLARATIONS)

        chat = model.start_chat(history=convo_messages[:-1])
        all_citations: List[Citation] = []

        step = 0
        current_input = convo_messages[-1]["parts"][0]

        while step < MAX_TOOL_CALLS:
            step += 1
            try:
                response = chat.send_message(current_input)
            except Exception as e:
                err_str = str(e)
                logger.error(f"Gemini API error in step {step}: {err_str}")
                if "429" in err_str or "quota" in err_str.lower():
                    time.sleep(5.0)
                    try:
                        response = chat.send_message(current_input)
                    except Exception as retry_err:
                        self._update_agent_run(run_id, "FAILED")
                        return ChatResponse(answer="Rate limit reached on Gemini API. Please wait a moment and try again.", citations=[])
                else:
                    self._update_agent_run(run_id, "FAILED")
                    return ChatResponse(answer=f"Agent error: {err_str}", citations=[])

            # Check if Gemini requested function/tool call(s)
            tool_calls = []
            if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    fn_call = getattr(part, "function_call", None)
                    if fn_call and getattr(fn_call, "name", None):
                        tool_calls.append(fn_call)

            if not tool_calls:
                # No function calls -> Gemini generated final answer text
                raw_answer = response.text if hasattr(response, "text") and response.text else "Research task completed."
                clean_answer = clean_markdown_output(raw_answer)
                self._update_agent_run(run_id, "COMPLETED")
                if on_event:
                    on_event({"type": "final", "answer": clean_answer, "citations": [c.model_dump() for c in all_citations]})
                return ChatResponse(answer=clean_answer, citations=all_citations)


            # Execute tool calls
            for fn_call in tool_calls:
                t_name = fn_call.name
                t_args = dict(fn_call.args) if fn_call.args else {}

                # Security override: force authenticated user ID into tool arguments
                t_args["authenticated_user_id"] = user_id
                if folder_id and "folder_id" not in t_args:
                    t_args["folder_id"] = folder_id

                if on_event:
                    on_event({
                        "type": "tool_call",
                        "tool_name": t_name,
                        "message": f"Executing tool '{t_name}'...",
                    })

                tool_fn = TOOL_REGISTRY.get(t_name)
                if not tool_fn:
                    result = {"error": f"Unknown tool '{t_name}'."}
                    status = "FAILED"
                else:
                    try:
                        result = tool_fn(**t_args)
                        status = "SUCCESS"
                        # Extract citations from search_library results if present
                        if t_name == "search_library" and isinstance(result, dict) and "results" in result:
                            for res_item in result["results"]:
                                all_citations.append(
                                    Citation(
                                        paper_id=res_item.get("paper_id"),
                                        paper_title=res_item.get("title"),
                                        document_id=res_item.get("document_id"),
                                        chunk_index=res_item.get("chunk_index", 0),
                                        page_number=res_item.get("page_number"),
                                        section_title=res_item.get("section_title"),
                                        content_snippet=res_item.get("content", ""),
                                        similarity_score=float(res_item.get("similarity", 0.0)),
                                    )
                                )
                    except Exception as tool_err:
                        logger.error(f"Error executing tool {t_name}: {tool_err}")
                        result = {"error": f"Tool execution failed: {str(tool_err)}"}
                        status = "FAILED"

                self._log_tool_call(run_id, t_name, t_args, result, status)

                if on_event:
                    on_event({
                        "type": "tool_result",
                        "tool_name": t_name,
                        "result_summary": str(result)[:200],
                    })

                # Feed function output back into current_input
                current_input = {
                    "role": "function",
                    "parts": [
                        genai.types.FunctionResponse(
                            name=t_name,
                            response={"result": result},
                        )
                    ],
                }

        # Safe termination if MAX_TOOL_CALLS reached
        self._update_agent_run(run_id, "MAX_CALLS_REACHED")
        final_msg = "Reached maximum tool call limit for this research task. Here is the progress summarized so far."
        return ChatResponse(answer=final_msg, citations=all_citations)
