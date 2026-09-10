import logging
import re
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple
import httpx
from app.services.pdf import validate_url_security

logger = logging.getLogger(__name__)

UNPAYWALL_BASE_URL = "https://api.unpaywall.org/v2"
SEMANTIC_SCHOLAR_PAPER_URL = "https://api.semanticscholar.org/graph/v1/paper"
EMAIL = "resin.academic.reader@gmail.com"


def extract_arxiv_id(text: Optional[str]) -> Optional[str]:
    """Extract clean arXiv identifier from URL, DOI, or raw ID string."""
    if not text or not isinstance(text, str):
        return None
    # Check with standard prefixes (url, doi, arxiv:, arxiv_)
    m = re.search(
        r"(?:arxiv\.org/(?:abs|pdf)/|arxiv[:_]\s*|10\.48550/arxiv\.)([0-9]{4}\.[0-9]{4,5}(?:v[0-9]+)?|[a-z\-]+/[0-9]{7})",
        text,
        re.IGNORECASE,
    )
    if m:
        return m.group(1)
    # Check if string itself is just an arxiv identifier
    m2 = re.match(r"^([0-9]{4}\.[0-9]{4,5}(?:v[0-9]+)?|[a-z\-]+/[0-9]{7})$", text.strip(), re.IGNORECASE)
    if m2:
        return m2.group(1)
    return None


def extract_pmc_id(text: Optional[str]) -> Optional[str]:
    """Extract numeric or PMC-prefixed identifier from PMC URL, string, or ID."""
    if not text or not isinstance(text, str):
        return None
    m = re.search(r"PMC\s*([0-9]+)", text, re.IGNORECASE)
    if m:
        return m.group(1)
    m2 = re.search(r"articles/([0-9]+)", text, re.IGNORECASE)
    if m2:
        return m2.group(1)
    clean = text.strip()
    if clean.isdigit() and len(clean) >= 6:
        return clean
    return None


def resolve_pmcid_from_doi(doi: Optional[str]) -> Optional[str]:
    """Query NCBI ID converter API to resolve a DOI to a PubMed Central PMCID."""
    if not doi or not isinstance(doi, str) or not doi.strip():
        return None
    clean_doi = doi.strip().replace("https://doi.org/", "")
    url = f"https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/?ids={urllib.parse.quote(clean_doi)}&format=json"
    try:
        with httpx.Client(timeout=6.0, follow_redirects=True) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                for rec in data.get("records", []):
                    pmcid = rec.get("pmcid")
                    if pmcid:
                        return extract_pmc_id(pmcid)
    except Exception as e:
        logger.warning(f"NCBI ID converter error for DOI '{doi}': {e}")
    return None


def _parse_pmc_xml_to_sections(xml_content: bytes) -> Optional[Dict[str, str]]:
    """Helper to parse PMC XML into clean sections including abstract and direct paragraphs."""
    try:
        root = ET.fromstring(xml_content)
    except Exception:
        return None

    sections: Dict[str, str] = {}

    # 1. Abstract from <front>
    abs_el = root.find(".//abstract")
    if abs_el is not None:
        abs_text = " ".join("".join(abs_el.itertext()).split())
        if len(abs_text) > 40:
            sections["Abstract"] = abs_text

    body = root.find(".//body")
    if body is None and not sections:
        return None

    if body is not None:
        # 2. Direct body paragraphs (often the main paper text in letters / brief comms)
        direct_ps = [p for p in body.findall("p") if p.text or len(list(p))]
        if direct_ps:
            current_block = []
            current_len = 0
            part = 1
            for p in direct_ps:
                p_text = " ".join("".join(p.itertext()).split())
                if not p_text:
                    continue
                current_block.append(p_text)
                current_len += len(p_text)
                if current_len > 1800:
                    title = f"Main Text (Part {part})" if part > 1 else "Introduction & Results"
                    sections[title] = "\n\n".join(current_block)
                    current_block = []
                    current_len = 0
                    part += 1
            if current_block:
                title = "Discussion & Conclusions" if part > 1 else "Main Text"
                sections[title] = "\n\n".join(current_block)

        # 3. Structured <sec> sections
        for sec in body.findall(".//sec"):
            title_el = sec.find("title")
            title = title_el.text.strip() if title_el is not None and title_el.text else "Section"
            if "supplement" in title.lower():
                continue
            p_texts = [" ".join("".join(p.itertext()).split()) for p in sec.findall(".//p")]
            sec_text = "\n\n".join([t for t in p_texts if len(t) > 30])
            if not sec_text:
                sec_text = " ".join("".join(sec.itertext()).split())
            if len(sec_text) > 60:
                unique_title = title
                counter = 2
                while unique_title in sections:
                    unique_title = f"{title} (Part {counter})"
                    counter += 1
                sections[unique_title] = sec_text

    return sections if sections else None


def fetch_pmc_full_text(pmc_id: str) -> Optional[Dict[str, str]]:
    """
    Fetch complete open-access paper full text by PMCID from NCBI E-utilities,
    falling back to Europe PMC REST API.
    Returns a dict mapping section titles to text content.
    """
    clean_id = extract_pmc_id(pmc_id) or pmc_id.replace("PMC", "").strip()
    if not clean_id.isdigit():
        return None

    # 1. Official NCBI E-utilities API
    try:
        url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pmc&id={clean_id}&retmode=xml"
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            resp = client.get(url)
            if resp.status_code == 200 and resp.content:
                sections = _parse_pmc_xml_to_sections(resp.content)
                if sections:
                    return sections
    except Exception as e:
        logger.warning(f"NCBI E-utilities fetch failed for PMC{clean_id}: {e}")

    # 2. Europe PMC REST API fallback
    try:
        epmc_url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/PMC{clean_id}/fullTextXML"
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            resp = client.get(epmc_url)
            if resp.status_code == 200 and resp.content:
                sections = _parse_pmc_xml_to_sections(resp.content)
                if sections:
                    return sections
    except Exception as e:
        logger.warning(f"Europe PMC fullTextXML fetch failed for PMC{clean_id}: {e}")

    return None


class HTMLPDFDiscoveryEngine:
    """
    Second-stage HTML PDF Discovery Engine.
    'Follows the PDF button' on article landing pages by extracting and scoring:
    - citation_pdf_url meta tags (Score 100)
    - <link rel="alternate" type="application/pdf"> (Score 95)
    - <a> tags containing PDF keywords in inner text or aria-label (Score 90)
    - <iframe>, <embed>, <object> tags pointing to PDF (Score 85)
    - <a> tags with href containing /pdf/ or format=pdf (Score 80)
    - Inline JavaScript PDF URL assignments (Score 70)
    """

    PDF_TEXT_KEYWORDS = [
        "download pdf",
        "full text pdf",
        "view pdf",
        "download article",
        "download full text",
        "read article pdf",
        "pdf full text",
        "pdf article",
        "download",
        "pdf",
    ]

    @classmethod
    def discover_pdf_links_from_html(cls, html: str, base_url: str) -> List[Tuple[str, int]]:
        """
        Inspects HTML content and returns list of (discovered_pdf_url, score),
        sorted by score descending.
        """
        results: List[Tuple[str, int]] = []
        seen = set()

        def record(raw_url: str, score: int):
            if not raw_url:
                return
            clean = raw_url.strip()
            if clean.startswith("//"):
                clean = "https:" + clean
            full_url = urllib.parse.urljoin(base_url, clean)
            if full_url in seen or not full_url.startswith(("http://", "https://")):
                return
            try:
                validate_url_security(full_url)
                seen.add(full_url)
                results.append((full_url, score))
            except Exception:
                pass

        # 1. <meta name="citation_pdf_url" content="...">
        for m in re.finditer(
            r'<meta[^>]+name=[\x22\x27]citation_pdf_url[\x22\x27][^>]+content=[\x22\x27]([^\x22\x27]+)[\x22\x27]',
            html,
            re.I,
        ):
            record(m.group(1), 100)
        for m in re.finditer(
            r'<meta[^>]+content=[\x22\x27]([^\x22\x27]+)[\x22\x27][^>]+name=[\x22\x27]citation_pdf_url[\x22\x27]',
            html,
            re.I,
        ):
            record(m.group(1), 100)

        # 2. <link rel="alternate" type="application/pdf" href="...">
        for m in re.finditer(
            r'<link[^>]+type=[\x22\x27]application/pdf[\x22\x27][^>]+href=[\x22\x27]([^\x22\x27]+)[\x22\x27]',
            html,
            re.I,
        ):
            record(m.group(1), 95)
        for m in re.finditer(
            r'<link[^>]+href=[\x22\x27]([^\x22\x27]+)[\x22\x27][^>]+type=[\x22\x27]application/pdf[\x22\x27]',
            html,
            re.I,
        ):
            record(m.group(1), 95)

        # 3. <a> tags with PDF keywords in text or attributes
        for m in re.finditer(
            r'<a\s+([^>]*href=[\x22\x27]([^\x22\x27]+)[\x22\x27][^>]*)>(.*?)</a>',
            html,
            re.I | re.DOTALL,
        ):
            attrs = m.group(1).lower()
            href = m.group(2)
            anchor_text = re.sub(r'<[^>]+>', ' ', m.group(3)).strip().lower()

            if href.startswith(("#", "javascript:", "mailto:")):
                continue

            for kw in cls.PDF_TEXT_KEYWORDS:
                if kw in anchor_text or f"aria-label=" in attrs and kw in attrs or f"title=" in attrs and kw in attrs:
                    score = 90 if kw != "pdf" else 75
                    record(href, score)
                    break

        # 4. <iframe src="...pdf...">, <embed src="...pdf...">, <object data="...pdf...">
        for m in re.finditer(
            r'<(?:iframe|embed|object)[^>]+(?:src|data)=[\x22\x27]([^\x22\x27]+)[\x22\x27]',
            html,
            re.I,
        ):
            url_match = m.group(1)
            if any(p in url_match.lower() for p in [".pdf", "format=pdf", "/pdf/"]):
                record(url_match, 85)

        # 5. Generic <a> tags whose href clearly points to a PDF
        for m in re.finditer(
            r'href=[\x22\x27]([^\x22\x27]+\.pdf(?:[?#][^\x22\x27]*)?)[\x22\x27]',
            html,
            re.I,
        ):
            record(m.group(1), 80)

        # 6. JavaScript variables containing PDF URLs
        for m in re.finditer(
            r'(?:pdfUrl|pdf_url|downloadUrl|fullTextUrl|pdf_path)\s*[:=]\s*[\x22\x27]([^\x22\x27]+)[\x22\x27]',
            html,
            re.I,
        ):
            js_url = m.group(1)
            if ".pdf" in js_url.lower() or "/pdf" in js_url.lower():
                record(js_url, 70)

        results.sort(key=lambda x: x[1], reverse=True)
        return results

    @classmethod
    def fetch_and_discover_pdf(cls, landing_url: str) -> List[Dict[str, Any]]:
        """Fetch landing page HTML and discover candidate PDF download links."""
        if (
            not landing_url
            or landing_url.lower().endswith(".pdf")
            or "arxiv.org" in landing_url
            or "pmc.ncbi" in landing_url
            or "ncbi.nlm.nih.gov" in landing_url
        ):
            return []
        try:
            validate_url_security(landing_url)
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
            with httpx.Client(timeout=6.0, follow_redirects=True) as client:
                resp = client.get(landing_url, headers=headers)
                if resp.status_code == 200 and "html" in resp.headers.get("content-type", ""):
                    links = cls.discover_pdf_links_from_html(resp.text[:60000], base_url=str(resp.url))
                    return [
                        {
                            "url": url,
                            "source": "html_pdf_discovery",
                            "priority": score,
                            "type": "discovered_pdf",
                        }
                        for url, score in links
                    ]
        except Exception as e:
            logger.debug(f"HTML PDF discovery failed for {landing_url}: {e}")
        return []


def resolve_landing_page_pdf(landing_url: str) -> Optional[str]:
    """Inspect HTML landing page and return highest-scoring discovered PDF link."""
    discovered = HTMLPDFDiscoveryEngine.fetch_and_discover_pdf(landing_url)
    if discovered:
        return discovered[0]["url"]
    return None


def query_openalex_locations(doi: Optional[str] = None, title: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Query OpenAlex for all repository mirrors, locations, and PDF URLs.
    Inspects best_oa_location, locations[], and primary_location.
    """
    locations: List[Dict[str, Any]] = []
    seen = set()

    def add_loc(url: Optional[str], source_type: str, priority: int, name: str = ""):
        if not url or not isinstance(url, str):
            return
        clean = url.strip()
        if clean in seen:
            return
        try:
            validate_url_security(clean)
            seen.add(clean)
            locations.append({
                "url": clean,
                "source": f"openalex_{source_type}",
                "type": "direct_pdf" if clean.lower().endswith(".pdf") else "landing_page",
                "priority": priority,
                "name": name,
            })
        except Exception:
            pass

    if not doi and not title:
        return locations

    try:
        if doi:
            clean_doi = doi.strip().replace("https://doi.org/", "")
            query_url = f"https://api.openalex.org/works/https://doi.org/{clean_doi}"
            params = {"mailto": "resin-academic-app@example.com"}
        else:
            query_url = "https://api.openalex.org/works"
            params = {"search": title.strip(), "per_page": "1", "mailto": "resin-academic-app@example.com"}

        with httpx.Client(timeout=8.0, follow_redirects=True) as client:
            resp = client.get(query_url, params=params)
            if resp.status_code == 200:
                data = resp.json()
                work = data["results"][0] if "results" in data and data["results"] else data

                # 1. best_oa_location
                best_oa = work.get("best_oa_location") or {}
                if best_oa.get("pdf_url"):
                    add_loc(best_oa["pdf_url"], "best_oa_pdf", 105, "OpenAlex Best OA PDF")
                elif best_oa.get("landing_page_url"):
                    add_loc(best_oa["landing_page_url"], "best_oa_landing", 50, "OpenAlex Best OA Landing")

                # 2. Iterate through all locations[] (Zenodo, institutional repositories, preprints)
                for loc in work.get("locations") or []:
                    pdf_url = loc.get("pdf_url")
                    source_name = loc.get("source", {}).get("display_name", "Repository")
                    if pdf_url:
                        add_loc(pdf_url, "location_pdf", 100, source_name)
                    landing = loc.get("landing_page_url")
                    if landing and loc.get("is_oa"):
                        add_loc(landing, "location_landing", 50, source_name)

                # 3. primary_location
                primary = work.get("primary_location") or {}
                if primary.get("pdf_url"):
                    add_loc(primary["pdf_url"], "primary_pdf", 95, "Primary Location PDF")

    except Exception as e:
        logger.warning(f"OpenAlex location lookup error: {e}")

    return locations


def query_unpaywall_locations(doi: str) -> List[Dict[str, Any]]:
    """Query Unpaywall API and inspect all oa_locations[]."""
    results: List[Dict[str, Any]] = []
    if not doi:
        return results
    clean_doi = doi.strip().replace("https://doi.org/", "")
    try:
        with httpx.Client(timeout=8.0) as client:
            resp = client.get(f"{UNPAYWALL_BASE_URL}/{clean_doi}", params={"email": EMAIL})
            if resp.status_code == 200:
                data = resp.json()
                best = data.get("best_oa_location") or {}
                if best.get("url_for_pdf"):
                    results.append({"url": best["url_for_pdf"], "source": "unpaywall_best_pdf", "priority": 90, "type": "direct_pdf"})
                elif best.get("url"):
                    results.append({"url": best["url"], "source": "unpaywall_best_landing", "priority": 50, "type": "landing_page"})

                for loc in data.get("oa_locations") or []:
                    pdf = loc.get("url_for_pdf")
                    if pdf and pdf != best.get("url_for_pdf"):
                        results.append({"url": pdf, "source": "unpaywall_mirror_pdf", "priority": 85, "type": "direct_pdf"})
    except Exception as e:
        logger.warning(f"Unpaywall query error for {doi}: {e}")
    return results


class OpenAccessService:
    """Service to discover open-access PDF download URLs via ranked candidate queues."""

    def find_pdf_candidates(
        self,
        doi: Optional[str] = None,
        arxiv_id: Optional[str] = None,
        existing_oa_url: Optional[str] = None,
        title: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Discover a ranked list of candidate PDF URLs to try, sorted by priority.
        Each entry: {"url": str, "source": str, "type": str, "priority": int, "arxiv_id": str | None}
        """
        candidates: List[Dict[str, Any]] = []
        seen_urls = set()

        def add_candidate(url: str, source: str, priority: int = 50, c_type: str = "direct_pdf", aid: Optional[str] = None):
            clean_url = url.strip()
            # Normalize http to https for arxiv
            if "arxiv.org" in clean_url and clean_url.startswith("http://"):
                clean_url = clean_url.replace("http://", "https://")
            # Ensure .pdf extension for arxiv direct links
            if "arxiv.org/abs/" in clean_url:
                clean_url = clean_url.replace("/abs/", "/pdf/") + ".pdf"
            if clean_url in seen_urls:
                return
            try:
                validate_url_security(clean_url)
                seen_urls.add(clean_url)
                candidates.append({
                    "url": clean_url,
                    "source": source,
                    "type": c_type,
                    "priority": priority,
                    "arxiv_id": aid,
                })
            except Exception as e:
                logger.warning(f"Candidate URL '{clean_url}' failed security check: {e}")

        # 1. Direct arXiv ID check from arxiv_id field, DOI, or existing_oa_url (Priority: 100)
        discovered_aid = (
            extract_arxiv_id(arxiv_id)
            or extract_arxiv_id(doi)
            or extract_arxiv_id(existing_oa_url)
        )
        if discovered_aid:
            add_candidate(
                f"https://arxiv.org/pdf/{discovered_aid}.pdf",
                source="arxiv_direct",
                priority=120,
                c_type="direct_pdf",
                aid=discovered_aid,
            )

        # 2. OpenAlex Multi-Location & Repository Query (Priority: 100 - 105)
        oa_locations = query_openalex_locations(doi=doi, title=title)
        for loc in oa_locations:
            add_candidate(
                loc["url"],
                source=loc["source"],
                priority=loc["priority"],
                c_type=loc["type"],
                aid=discovered_aid,
            )

        # 3. Existing OA URL from paper record (Priority: 95 for PDF, 50 for landing)
        if existing_oa_url:
            prio = 95 if existing_oa_url.lower().endswith(".pdf") else 50
            add_candidate(
                existing_oa_url,
                source="paper_record_url",
                priority=prio,
                c_type="direct_pdf" if prio == 95 else "landing_page",
                aid=discovered_aid,
            )

        # 4. Semantic Scholar API lookup by DOI (Priority: 95 for direct PDF)
        if doi and isinstance(doi, str) and doi.strip():
            clean_doi = doi.strip().replace("https://doi.org/", "")
            try:
                s2_url = f"{SEMANTIC_SCHOLAR_PAPER_URL}/{clean_doi}?fields=openAccessPdf,externalIds"
                with httpx.Client(timeout=8.0) as client:
                    resp = client.get(s2_url)
                    if resp.status_code == 200:
                        s2_data = resp.json()
                        s2_arxiv = s2_data.get("externalIds", {}).get("ArXiv")
                        if s2_arxiv:
                            add_candidate(
                                f"https://arxiv.org/pdf/{s2_arxiv}.pdf",
                                source="semantic_scholar_arxiv",
                                priority=120,
                                c_type="direct_pdf",
                                aid=s2_arxiv,
                            )
                        oa_info = s2_data.get("openAccessPdf") or {}
                        pdf_url = oa_info.get("url")
                        if pdf_url:
                            add_candidate(
                                pdf_url,
                                source="semantic_scholar_oa",
                                priority=95 if pdf_url.lower().endswith(".pdf") else 50,
                                c_type="direct_pdf" if pdf_url.lower().endswith(".pdf") else "landing_page",
                                aid=s2_arxiv,
                            )
            except Exception as e:
                logger.warning(f"Semantic Scholar DOI lookup error for {doi}: {e}")

        # 5. Unpaywall API using DOI with all mirror locations (Priority: 85 - 90)
        if doi and isinstance(doi, str) and doi.strip():
            unpaywall_locs = query_unpaywall_locations(doi)
            for loc in unpaywall_locs:
                add_candidate(
                    loc["url"],
                    source=loc["source"],
                    priority=loc["priority"],
                    c_type=loc["type"],
                    aid=discovered_aid,
                )

        # 6. Search arXiv API by paper title (Priority: 90)
        if title and isinstance(title, str) and len(title.strip()) > 5 and not discovered_aid:
            try:
                clean_title = title.strip()
                encoded_title = urllib.parse.quote(clean_title)
                arxiv_query_url = f"https://export.arxiv.org/api/query?search_query=ti:%22{encoded_title}%22&max_results=1"
                with httpx.Client(timeout=8.0) as client:
                    resp = client.get(arxiv_query_url)
                    if resp.status_code == 200:
                        root = ET.fromstring(resp.text)
                        for entry in root.findall("{http://www.w3.org/2005/Atom}entry"):
                            id_elem = entry.find("{http://www.w3.org/2005/Atom}id")
                            if id_elem is not None and id_elem.text:
                                raw_arxiv = id_elem.text.strip().split("/abs/")[-1]
                                add_candidate(
                                    f"https://arxiv.org/pdf/{raw_arxiv}.pdf",
                                    source="arxiv_title_match",
                                    priority=90,
                                    c_type="direct_pdf",
                                    aid=raw_arxiv,
                                )
            except Exception as e:
                logger.warning(f"arXiv title search error for '{title}': {e}")

        # 7. For landing pages in the candidate list, run Second-Stage HTML PDF Discovery ("Follow the PDF Button")
        landing_candidates = [c for c in candidates if c.get("type") == "landing_page" or not c["url"].lower().endswith(".pdf")]
        for lc in landing_candidates[:3]:  # inspect top 3 landing pages to avoid excessive network latency
            discovered = HTMLPDFDiscoveryEngine.fetch_and_discover_pdf(lc["url"])
            for disc in discovered:
                add_candidate(
                    disc["url"],
                    source=f"{lc['source']}_button_discovery",
                    priority=disc["priority"],
                    c_type="discovered_pdf",
                    aid=discovered_aid,
                )

        # Sort all candidates by priority descending
        candidates.sort(key=lambda x: x.get("priority", 0), reverse=True)
        return candidates

    def find_open_access_pdf(
        self,
        doi: Optional[str] = None,
        arxiv_id: Optional[str] = None,
        existing_oa_url: Optional[str] = None,
        title: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Backward-compatible helper returning the top candidate if available."""
        cands = self.find_pdf_candidates(doi=doi, arxiv_id=arxiv_id, existing_oa_url=existing_oa_url, title=title)
        if cands:
            top = cands[0]
            return {
                "available": True,
                "pdf_url": top["url"],
                "source": top["source"],
                "content_type": "application/pdf",
                "arxiv_id": top.get("arxiv_id"),
                "priority": top.get("priority", 0),
            }
        return {"available": False, "reason": "No open-access PDF found for this paper."}
