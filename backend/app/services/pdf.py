import hashlib
import io
import ipaddress
import logging
import re
import socket
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse
import httpx
import pypdf

logger = logging.getLogger(__name__)

MAX_PDF_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB limit
DOWNLOAD_TIMEOUT_SECONDS = 30.0

PRIVATE_IP_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/32"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


class SSRFValidationError(ValueError):
    """Raised when a URL violates SSRF security policies."""
    pass


class PDFExtractionError(RuntimeError):
    """Raised when PDF extraction fails."""
    pass


def validate_url_security(url: str) -> str:
    """
    Validate that a URL is safe against SSRF attacks.
    Enforces http/https scheme and checks that target IP addresses are not private/loopback/link-local.
    """
    if not url or not isinstance(url, str):
        raise SSRFValidationError("Invalid URL provided.")

    parsed = urlparse(url.strip())
    if parsed.scheme.lower() not in ("http", "https"):
        raise SSRFValidationError(f"Forbidden URL scheme '{parsed.scheme}'. Only HTTP and HTTPS are permitted.")

    hostname = parsed.hostname
    if not hostname:
        raise SSRFValidationError("URL lacks a valid hostname.")

    hostname_lower = hostname.lower()
    if hostname_lower in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
        raise SSRFValidationError(f"Forbidden target host '{hostname}'.")

    # Resolve IP address to prevent DNS rebinding / internal access
    try:
        addr_info = socket.getaddrinfo(hostname, None)
        for family, socktype, proto, canonname, sockaddr in addr_info:
            ip_str = sockaddr[0]
            ip_obj = ipaddress.ip_address(ip_str)
            for net in PRIVATE_IP_NETWORKS:
                if ip_obj in net:
                    raise SSRFValidationError(f"Target host '{hostname}' resolves to private/internal IP address '{ip_str}'.")
    except socket.gaierror as e:
        raise SSRFValidationError(f"Could not resolve hostname '{hostname}': {e}")

    return url


def calculate_sha256(content_bytes: bytes) -> str:
    """Return SHA-256 checksum hex string of given bytes."""
    return hashlib.sha256(content_bytes).hexdigest()


class PDFService:
    """Service for securely downloading, validating, and extracting text/pages from PDFs."""

    def download_pdf(self, pdf_url: str) -> Tuple[bytes, str]:
        """
        Download PDF from validated URL with size checking and SSRF protection.
        Returns tuple of (pdf_bytes, sha256_checksum).
        """
        safe_url = validate_url_security(pdf_url)

        headers = {
            "User-Agent": "ResinAcademicBot/1.0 (Research Assistant; mailto:resin@example.com)"
        }

        try:
            with httpx.Client(follow_redirects=True, timeout=DOWNLOAD_TIMEOUT_SECONDS) as client:
                # Initial HEAD check or streaming GET to validate content-length
                resp = client.get(safe_url, headers=headers)

                # Validate final redirected URL
                validate_url_security(str(resp.url))

                if resp.status_code != 200:
                    raise PDFExtractionError(f"HTTP error {resp.status_code} while fetching PDF from {pdf_url}")

                pdf_bytes = resp.content
                if len(pdf_bytes) > MAX_PDF_SIZE_BYTES:
                    raise PDFExtractionError(f"PDF file size ({len(pdf_bytes)} bytes) exceeds max limit of 50MB.")

                # Validate magic bytes for PDF (%PDF-)
                if not pdf_bytes.startswith(b"%PDF-"):
                    # Check first 1024 bytes in case of leading whitespace
                    if b"%PDF-" not in pdf_bytes[:1024]:
                        raise PDFExtractionError("Downloaded content does not have a valid PDF header.")

                sha256 = calculate_sha256(pdf_bytes)
                return pdf_bytes, sha256

        except (SSRFValidationError, PDFExtractionError):
            raise
        except Exception as e:
            logger.error(f"Error downloading PDF from {pdf_url}: {e}")
            raise PDFExtractionError(f"Failed to download PDF: {str(e)}")

    def extract_pages(self, pdf_bytes: bytes) -> List[Dict[str, Any]]:
        """
        Extract page text page-by-page from raw PDF bytes.
        Returns list of dicts: [{"page_number": 1, "text": "...", "sections": [...]}]
        """
        try:
            reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
            pages_data = []

            for idx, page in enumerate(reader.pages, start=1):
                raw_text = page.extract_text() or ""
                cleaned_text = self.clean_text(raw_text)

                if cleaned_text.strip():
                    sections = self.detect_sections(cleaned_text)
                    pages_data.append({
                        "page_number": idx,
                        "text": cleaned_text,
                        "sections": sections,
                    })

            if not pages_data:
                logger.warning("No readable text extracted from PDF.")

            return pages_data

        except Exception as e:
            logger.error(f"Failed to extract text from PDF bytes: {e}")
            raise PDFExtractionError(f"PDF parsing error: {str(e)}")

    def clean_text(self, text: str) -> str:
        """Clean extracted PDF raw text (remove excessive whitespace, null bytes, etc.)."""
        if not text:
            return ""
        # Remove null characters
        text = text.replace("\x00", "")
        # Standardize line endings
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        # Replace multiple spaces with a single space
        text = re.sub(r"[ \t]+", " ", text)
        # Reduce more than 3 consecutive linebreaks to 2
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def detect_sections(self, text: str) -> Dict[str, str]:
        """
        Attempt to segment page text into section title -> content mapping.
        Recognizes common academic headers like 1. Introduction, Abstract, Methods, Results, etc.
        """
        section_pattern = re.compile(
            r"^(?:(?:\d+\.?\s*)?(?:Abstract|Introduction|Related Work|Background|Methods?|Methodology|Model|Experiments?|Results?|Discussion|Conclusion|References|Acknowledgements?))\b",
            re.IGNORECASE | re.MULTILINE,
        )

        lines = text.split("\n")
        sections: Dict[str, List[str]] = {}
        current_section = "General"

        for line in lines:
            stripped = line.strip()
            match = section_pattern.match(stripped)
            if match and len(stripped) < 80:
                current_section = stripped
                if current_section not in sections:
                    sections[current_section] = []
            else:
                if current_section not in sections:
                    sections[current_section] = []
                sections[current_section].append(stripped)

        return {sec: "\n".join(content_lines).strip() for sec, content_lines in sections.items() if content_lines}
