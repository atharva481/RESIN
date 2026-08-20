import logging
from typing import List, Optional
from app.core.supabase import get_supabase_client

logger = logging.getLogger(__name__)


def save_chat_turn(user_id: str, folder_id: Optional[str], role: str, content: str) -> None:
    """
    Save a single chat turn (user or assistant) to the chat_history table.
    """
    supabase = get_supabase_client()
    if not supabase:
        logger.error("Supabase client not initialized; cannot save chat turn.")
        return
    try:
        supabase.table("chat_history").insert(
            {
                "user_id": user_id,
                "folder_id": folder_id,
                "role": role,
                "content": content,
            }
        ).execute()
    except Exception as e:
        logger.error(f"Failed to save chat turn: {e}")


def load_chat_history(user_id: str, folder_id: Optional[str], limit: int = 100) -> List[dict]:
    """
    Load chat history for a user, optionally filtered by folder.
    Returns list of dicts with keys: role, content, created_at (oldest first).
    """
    supabase = get_supabase_client()
    if not supabase:
        logger.error("Supabase client not initialized; cannot load chat history.")
        return []
    try:
        query = supabase.table("chat_history").select("role,content,created_at").eq("user_id", user_id)
        if folder_id is not None:
            query = query.eq("folder_id", folder_id)
        # Order by created_at ascending to get chronological conversation
        query = query.order("created_at", desc=False).limit(limit)
        resp = query.execute()
        return resp.data or []
    except Exception as e:
        logger.error(f"Failed to load chat history: {e}")
        return []