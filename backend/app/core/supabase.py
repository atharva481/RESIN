import logging
from typing import Any, Dict, List, Optional
from supabase import Client, create_client
from app.core.config import settings

logger = logging.getLogger(__name__)

_supabase_client: Optional[Client] = None


def get_supabase_client() -> Optional[Client]:
    global _supabase_client
    if _supabase_client is None:
        key = (
            settings.supabase_service_key
            if settings.supabase_service_key != "placeholder-key"
            else settings.supabase_anon_key
        )
        if settings.supabase_url and not settings.supabase_url.startswith("https://placeholder"):
            try:
                _supabase_client = create_client(settings.supabase_url, key)
            except Exception as e:
                logger.error(f"Failed to initialize Supabase client: {e}")
                return None
    return _supabase_client


def match_chunks_rpc(
    query_embedding: List[float],
    match_threshold: float = 0.3,
    match_count: int = 5,
    filter_paper_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Execute match_paper_chunks RPC on Supabase via service role client."""
    client = get_supabase_client()
    if not client:
        logger.warning("Supabase client is not initialized.")
        return []
    try:
        payload = {
            "query_embedding": query_embedding,
            "match_threshold": match_threshold,
            "match_count": match_count,
            "filter_paper_id": filter_paper_id,
        }
        response = client.rpc("match_paper_chunks", payload).execute()
        return response.data or []
    except Exception as e:
        logger.error(f"Error calling match_paper_chunks RPC: {e}")
        return []


def match_papers_rpc(
    query_embedding: List[float],
    match_threshold: float = 0.3,
    match_count: int = 5,
    filter_user_id: Optional[str] = None,
    filter_folder_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Execute match_paper_embeddings RPC on Supabase via service role client."""
    client = get_supabase_client()
    if not client:
        logger.warning("Supabase client is not initialized.")
        return []
    try:
        payload = {
            "query_embedding": query_embedding,
            "match_threshold": match_threshold,
            "match_count": match_count,
            "filter_user_id": filter_user_id,
            "filter_folder_id": filter_folder_id,
        }
        response = client.rpc("match_paper_embeddings", payload).execute()
        return response.data or []
    except Exception as e:
        logger.error(f"Error calling match_paper_embeddings RPC: {e}")
        return []
