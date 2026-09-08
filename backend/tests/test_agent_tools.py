from unittest.mock import MagicMock, patch
import pytest
from app.agent.tools import (
    TOOL_DECLARATIONS,
    TOOL_REGISTRY,
    check_library,
    find_open_access_pdf,
    get_ingestion_status,
    get_paper,
    search_library,
)


def test_tool_registry_contains_all_seven_tools():
    expected_tools = {
        "search_papers",
        "find_open_access_pdf",
        "check_library",
        "ingest_paper",
        "get_ingestion_status",
        "search_library",
        "get_paper",
    }
    assert set(TOOL_REGISTRY.keys()) == expected_tools
    assert len(TOOL_DECLARATIONS) == 7


def test_check_library_unauthenticated():
    with patch("app.agent.tools.get_supabase_client", return_value=None):
        res = check_library(paper_id="paper_123", authenticated_user_id="user_abc")
        assert res["exists"] is False


def test_get_ingestion_status_non_existent():
    res = get_ingestion_status(job_id="job_non_existent")
    assert res["status"] == "FAILED"
    assert "not found" in res["error"]


def test_find_open_access_pdf_fallback():
    with patch("app.agent.tools.get_supabase_client", return_value=None):
        with patch("app.api.search.get_paper_details", side_effect=Exception("API Error")):
            res = find_open_access_pdf(paper_id="paper_123")
            assert res["available"] is False
            assert "No open-access PDF found" in res["reason"]
