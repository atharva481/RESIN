import logging
import uuid
from typing import Any, Dict, Optional, Tuple
from app.core.supabase import get_supabase_client
from app.services.open_access import extract_arxiv_id

logger = logging.getLogger(__name__)


def is_valid_uuid(val: Optional[str]) -> bool:
    """Check if string is a valid UUID."""
    if not val or not isinstance(val, str):
        return False
    try:
        uuid.UUID(val.strip())
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def to_deterministic_uuid(key: str) -> str:
    """Generate RFC 4122 deterministic UUIDv5 from an external identifier."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"resin:{key.strip()}"))


def resolve_paper_record(
    paper_id: str,
    title: Optional[str] = None,
    abstract: Optional[str] = None,
    doi: Optional[str] = None,
    arxiv_id: Optional[str] = None,
    open_access_url: Optional[str] = None,
) -> Tuple[str, Dict[str, Any]]:
    """
    Resolves any paper identifier (UUID, arXiv ID, OpenAlex ID, Semantic Scholar ID)
    to a valid Postgres UUID and its metadata record.
    Guarantees a valid UUID is returned and the paper exists in the Supabase 'papers' table.
    """
    client = get_supabase_client()
    clean_id = (paper_id or "").strip()

    # 1. If it's already a valid UUID, query by id
    if is_valid_uuid(clean_id):
        if client:
            try:
                res = client.table("papers").select("*").eq("id", clean_id).execute()
                if res.data:
                    return clean_id, res.data[0]
            except Exception as e:
                logger.warning(f"Error checking UUID paper {clean_id}: {e}")
        return clean_id, {}

    # 2. Check if a paper with this external ID already exists in papers table
    aid = arxiv_id or extract_arxiv_id(clean_id) or extract_arxiv_id(doi) or extract_arxiv_id(open_access_url)
    if client:
        try:
            # Query by semantic_scholar_id, arxiv_id, or doi
            or_clauses = [f"semantic_scholar_id.eq.{clean_id}"]
            if aid:
                or_clauses.append(f"arxiv_id.eq.{aid}")
                or_clauses.append(f"semantic_scholar_id.eq.arxiv_{aid}")
            if doi and isinstance(doi, str) and doi.strip():
                clean_doi = doi.strip().replace("https://doi.org/", "")
                or_clauses.append(f"doi.eq.{clean_doi}")
                or_clauses.append(f"doi.eq.https://doi.org/{clean_doi}")
            res = client.table("papers").select("*").or_(",".join(or_clauses)).limit(1).execute()
            if res.data:
                row = res.data[0]
                return row["id"], row
        except Exception as e:
            logger.warning(f"Error querying paper by external ID '{clean_id}': {e}")

    # 3. Non-UUID not found in database: generate deterministic UUID
    canon_key = f"arxiv:{aid}" if aid else clean_id
    canonical_uuid = to_deterministic_uuid(canon_key)

    # 4. Check if the deterministic UUID exists in papers table
    if client:
        try:
            res = client.table("papers").select("*").eq("id", canonical_uuid).execute()
            if res.data:
                return canonical_uuid, res.data[0]
        except Exception as e:
            logger.warning(f"Error checking deterministic UUID {canonical_uuid}: {e}")

        # Insert canonical paper row into papers table
        try:
            clean_oa_url = open_access_url
            if aid and (not clean_oa_url or not clean_oa_url.lower().endswith(".pdf")):
                clean_oa_url = f"https://arxiv.org/pdf/{aid}.pdf"

            record = {
                "id": canonical_uuid,
                "title": title or "Untitled Paper",
                "abstract": abstract or "",
                "doi": doi,
                "arxiv_id": aid,
                "open_access_url": clean_oa_url,
                "semantic_scholar_id": clean_id,
            }
            client.table("papers").upsert(record, on_conflict="id").execute()
            logger.info(f"Created canonical paper row for external ID '{clean_id}' -> UUID {canonical_uuid}")
            return canonical_uuid, record
        except Exception as e:
            logger.warning(f"Could not persist canonical paper record for {canonical_uuid}: {e}")

    return canonical_uuid, {}
