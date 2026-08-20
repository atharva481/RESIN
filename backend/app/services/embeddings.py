import logging
import time
from typing import Any, List
import google.generativeai as genai
from app.core.config import settings

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 1.0  # seconds

def _ensure_configured():
    if settings.gemini_api_key and settings.gemini_api_key != "placeholder-gemini-key":
        genai.configure(api_key=settings.gemini_api_key)


# Configure Gemini client globally if key exists
_ensure_configured()


def _with_retry(fn, *args, max_retries=MAX_RETRIES, retry_delay=RETRY_DELAY, **kwargs):
    """Retry a Gemini API call with exponential backoff."""
    _ensure_configured()
    last_exc = None
    for attempt in range(1, max_retries + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_exc = e
            err_str = str(e)
            if "404" in err_str or "not found" in err_str:
                raise e
            if attempt < max_retries:
                wait = retry_delay * (2 ** (attempt - 1))
                logger.warning(f"Gemini API attempt {attempt} failed: {e}. Retrying in {wait}s...")
                time.sleep(wait)
    logger.error(f"Gemini API failed after {max_retries} attempts: {last_exc}")
    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"Gemini API failed after {max_retries} attempts.")


def _get_embedding_models() -> List[str]:
    """Query Gemini API for models supporting embedContent."""
    _ensure_configured()
    supported = []
    try:
        for m in genai.list_models():
            methods = getattr(m, "supported_generation_methods", [])
            if "embedContent" in methods or "embed_content" in str(methods):
                supported.append(m.name)
    except Exception as e:
        logger.warning(f"Could not list genai models: {e}")

    fallbacks = ["models/embedding-001", "models/text-embedding-004", "embedding-001"]
    for f in fallbacks:
        if f not in supported:
            supported.append(f)
    return supported


def _enforce_768_dims(val: Any) -> Any:
    """Enforce that single vectors, batch vectors, or dict responses are strictly sliced to 768 dimensions for pgvector."""
    if isinstance(val, list) and val:
        if isinstance(val[0], list):
            return [v[:768] for v in val]
        elif isinstance(val[0], dict) and "embedding" in val[0]:
            return [v["embedding"][:768] for v in val if isinstance(v, dict)]
        elif isinstance(val[0], (int, float)):
            return val[:768]
    elif isinstance(val, dict) and "embedding" in val:
        return _enforce_768_dims(val["embedding"])
    return val


class EmbeddingService:
    """Service for generating text embeddings using Gemini embedding models."""

    def __init__(self, model_name: str = settings.gemini_embedding_model):
        self.model_name = model_name
        _ensure_configured()

    def _call_embed(self, contents: Any, task_type: str):
        """Call genai.embed_content with dynamic model discovery, fallback, and 768-dim truncation."""
        _ensure_configured()
        candidate_models = [self.model_name] + _get_embedding_models()
        models_to_try = []
        for m in candidate_models:
            if m and m not in models_to_try:
                models_to_try.append(m)

        last_err = None
        for model in models_to_try:
            try:
                try:
                    res = _with_retry(
                        genai.embed_content,
                        model=model,
                        content=contents,
                        task_type=task_type,
                        output_dimensionality=768,
                    )
                except Exception as inner_err:
                    err_str = str(inner_err)
                    if "404" in err_str or "not found" in err_str or "no longer available" in err_str:
                        raise inner_err
                    # Fallback for models or API wrappers that do not accept output_dimensionality parameter
                    res = _with_retry(
                        genai.embed_content,
                        model=model,
                        content=contents,
                        task_type=task_type,
                    )
                return _enforce_768_dims(res)
            except Exception as e:
                last_err = e
                err_str = str(e)
                if "404" in err_str or "not found" in err_str or "supported" in err_str:
                    logger.warning(f"Embedding model '{model}' not supported or 404. Retrying next model...")
                    continue
                raise e
        if last_err is not None:
            raise last_err
        raise RuntimeError("No embedding models available or all attempts failed.")

    def embed_text(self, text: str) -> List[float]:
        """Generate 768-dim embedding vector for a single text query or document."""
        return self._call_embed(text, task_type="retrieval_document")

    def embed_query(self, query: str) -> List[float]:
        """Generate 768-dim embedding vector for a search query."""
        return self._call_embed(query, task_type="retrieval_query")

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of text chunks using the batch API."""
        if not texts:
            return []
        try:
            return self._call_embed(texts, task_type="retrieval_document")
        except Exception as e:
            logger.error(f"Failed to generate batch embeddings via Gemini: {e}")
            raise
