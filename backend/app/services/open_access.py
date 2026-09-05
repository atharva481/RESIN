import logging
from typing import Any, Dict, Optional
import httpx
from app.services.pdf import validate_url_security

logger = logging.getLogger(__name__)

UNPAYWALL_BASE_URL = "https://api.unpaywall.org/v2"
EMAIL = "resin-academic-app@example.com"


class OpenAccessService:
    """Service to discover open-access PDF download URLs via Unpaywall, arXiv, and Semantic Scholar."""

    def find_open_access_pdf(
        self,
        doi: Optional[str] = None,
        arxiv_id: Optional[str] = None,
        existing_oa_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Find best available open-access PDF URL for a paper.
        Returns: {"available": bool, "pdf_url": str | None, "source": str, "content_type": "application/pdf"}
        """
        # 1. Try existing openAccessPdf URL if already present in paper record
        if existing_oa_url and isinstance(existing_oa_url, str) and existing_oa_url.strip():
            url = existing_oa_url.strip()
            try:
                validate_url_security(url)
                return {
                    "available": True,
                    "pdf_url": url,
                    "source": "semantic_scholar / paper_record",
                    "content_type": "application/pdf",
                }
            except Exception as e:
                logger.warning(f"Existing OA URL '{url}' failed security check: {e}")

        # 2. Try arXiv direct PDF if arxiv_id is present
        if arxiv_id and isinstance(arxiv_id, str) and arxiv_id.strip():
            clean_arxiv = arxiv_id.strip().replace("arXiv:", "")
            arxiv_pdf_url = f"https://arxiv.org/pdf/{clean_arxiv}.pdf"
            try:
                validate_url_security(arxiv_pdf_url)
                return {
                    "available": True,
                    "pdf_url": arxiv_pdf_url,
                    "source": "arxiv",
                    "content_type": "application/pdf",
                }
            except Exception as e:
                logger.warning(f"arXiv PDF URL '{arxiv_pdf_url}' failed security check: {e}")

        # 3. Try Unpaywall API using DOI
        if doi and isinstance(doi, str) and doi.strip():
            clean_doi = doi.strip().replace("https://doi.org/", "")
            unpaywall_url = f"{UNPAYWALL_BASE_URL}/{clean_doi}"
            try:
                with httpx.Client(timeout=8.0) as client:
                    resp = client.get(unpaywall_url, params={"email": EMAIL})
                    if resp.status_code == 200:
                        data = resp.json()
                        best_oa = data.get("best_oa_location") or {}
                        pdf_url = best_oa.get("url_for_pdf") or best_oa.get("url")
                        if pdf_url:
                            validate_url_security(pdf_url)
                            return {
                                "available": True,
                                "pdf_url": pdf_url,
                                "source": "unpaywall",
                                "content_type": "application/pdf",
                            }
            except Exception as e:
                logger.warning(f"Unpaywall lookup error for DOI {doi}: {e}")

        return {
            "available": False,
            "reason": "No open-access PDF found or accessible for this paper.",
        }
