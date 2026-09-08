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

from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

MAX_PDF_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB limit
DOWNLOAD_TIMEOUT_SECONDS = 30.0


class DownloadFailureReason(str, Enum):
    SUCCESS = "SUCCESS"
    NO_PDF_FOUND = "NO_PDF_FOUND"
    LANDING_PAGE_ONLY = "LANDING_PAGE_ONLY"
    LOGIN_REQUIRED = "LOGIN_REQUIRED"
    PAYWALL_DETECTED = "PAYWALL_DETECTED"
    BOT_PROTECTION = "BOT_PROTECTION"
    RATE_LIMITED = "RATE_LIMITED"
    SERVER_ERROR = "SERVER_ERROR"
    NOT_FOUND = "NOT_FOUND"
    INVALID_PDF = "INVALID_PDF"
    PDF_TOO_LARGE = "PDF_TOO_LARGE"
    NETWORK_ERROR = "NETWORK_ERROR"


@dataclass
class PDFDownloadResult:
    success: bool
    pdf_bytes: Optional[bytes] = None
    sha256: Optional[str] = None
    url: str = ""
    final_url: str = ""
    status_code: int = 0
    content_type: str = ""
    size: int = 0
    failure_reason: DownloadFailureReason = DownloadFailureReason.NO_PDF_FOUND
    error_message: Optional[str] = None


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

    def detailed_download(self, pdf_url: str) -> PDFDownloadResult:
        """
        Download PDF with full diagnostics, failure taxonomy, content-type and magic byte inspection.
        Returns a rich PDFDownloadResult.
        """
        try:
            safe_url = validate_url_security(pdf_url)
        except SSRFValidationError as e:
            return PDFDownloadResult(
                success=False,
                url=pdf_url,
                failure_reason=DownloadFailureReason.NETWORK_ERROR,
                error_message=f"Security check failed: {e}",
            )

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/pdf,application/xhtml+xml,text/html;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

        try:
            with httpx.Client(follow_redirects=True, timeout=DOWNLOAD_TIMEOUT_SECONDS) as client:
                resp = client.get(safe_url, headers=headers)
                final_url = str(resp.url)
                status = resp.status_code
                content_type = resp.headers.get("content-type", "").lower()
                content = resp.content
                size = len(content)

                # Validate redirected URL against SSRF
                try:
                    validate_url_security(final_url)
                except SSRFValidationError as e:
                    return PDFDownloadResult(
                        success=False,
                        url=pdf_url,
                        final_url=final_url,
                        status_code=status,
                        failure_reason=DownloadFailureReason.NETWORK_ERROR,
                        error_message=f"Redirect violated security: {e}",
                    )

                # Diagnose HTTP error codes
                if status == 401 or "/login" in final_url.lower() or "signin" in final_url.lower():
                    return PDFDownloadResult(
                        success=False,
                        url=pdf_url,
                        final_url=final_url,
                        status_code=status,
                        content_type=content_type,
                        size=size,
                        failure_reason=DownloadFailureReason.LOGIN_REQUIRED,
                        error_message="Authentication / institutional login required.",
                    )

                if status == 403:
                    html_snippet = resp.text[:3000].lower() if resp.text else ""
                    if any(bot in html_snippet for bot in ["cloudflare", "turnstile", "recaptcha", "just a moment", "bot", "challenge"]):
                        return PDFDownloadResult(
                            success=False,
                            url=pdf_url,
                            final_url=final_url,
                            status_code=status,
                            content_type=content_type,
                            size=size,
                            failure_reason=DownloadFailureReason.BOT_PROTECTION,
                            error_message="Publisher server blocked automated download via bot challenge.",
                        )
                    return PDFDownloadResult(
                        success=False,
                        url=pdf_url,
                        final_url=final_url,
                        status_code=status,
                        content_type=content_type,
                        size=size,
                        failure_reason=DownloadFailureReason.PAYWALL_DETECTED,
                        error_message="Access forbidden (403). Subscription or purchase required.",
                    )

                if status == 429:
                    return PDFDownloadResult(
                        success=False,
                        url=pdf_url,
                        final_url=final_url,
                        status_code=status,
                        content_type=content_type,
                        size=size,
                        failure_reason=DownloadFailureReason.RATE_LIMITED,
                        error_message="Publisher rate limit exceeded (429).",
                    )

                if status == 404:
                    return PDFDownloadResult(
                        success=False,
                        url=pdf_url,
                        final_url=final_url,
                        status_code=status,
                        content_type=content_type,
                        size=size,
                        failure_reason=DownloadFailureReason.NOT_FOUND,
                        error_message="File or page not found (404).",
                    )

                if status >= 500:
                    return PDFDownloadResult(
                        success=False,
                        url=pdf_url,
                        final_url=final_url,
                        status_code=status,
                        content_type=content_type,
                        size=size,
                        failure_reason=DownloadFailureReason.SERVER_ERROR,
                        error_message=f"Publisher server error ({status}).",
                    )

                if status != 200:
                    return PDFDownloadResult(
                        success=False,
                        url=pdf_url,
                        final_url=final_url,
                        status_code=status,
                        content_type=content_type,
                        size=size,
                        failure_reason=DownloadFailureReason.NETWORK_ERROR,
                        error_message=f"HTTP {status} returned.",
                    )

                # Check max size (100MB)
                if size > MAX_PDF_SIZE_BYTES:
                    return PDFDownloadResult(
                        success=False,
                        url=pdf_url,
                        final_url=final_url,
                        status_code=status,
                        content_type=content_type,
                        size=size,
                        failure_reason=DownloadFailureReason.PDF_TOO_LARGE,
                        error_message=f"PDF file size ({size / (1024*1024):.1f} MB) exceeds 100MB limit.",
                    )

                # Magic byte verification (%PDF-)
                has_magic_bytes = content.startswith(b"%PDF-") or (b"%PDF-" in content[:1024])

                if has_magic_bytes:
                    sha256 = calculate_sha256(content)
                    return PDFDownloadResult(
                        success=True,
                        pdf_bytes=content,
                        sha256=sha256,
                        url=pdf_url,
                        final_url=final_url,
                        status_code=status,
                        content_type=content_type,
                        size=size,
                        failure_reason=DownloadFailureReason.SUCCESS,
                    )

                # Content does not have %PDF- header: inspect HTML body for diagnostics
                html_text = ""
                try:
                    html_text = resp.text[:10000].lower()
                except Exception:
                    pass

                # Check for paywall / login markers
                paywall_signals = [
                    "purchase article", "purchase pdf", "buy article", "subscribe",
                    "institutional access", "access through your institution",
                    "rent this article", "pay-per-view", "readcube checkout"
                ]
                if any(sig in html_text for sig in paywall_signals):
                    return PDFDownloadResult(
                        success=False,
                        url=pdf_url,
                        final_url=final_url,
                        status_code=status,
                        content_type=content_type,
                        size=size,
                        failure_reason=DownloadFailureReason.PAYWALL_DETECTED,
                        error_message="Landing page indicates article purchase or subscription is required.",
                    )

                # Check for bot challenge
                bot_signals = ["recaptcha", "cloudflare", "challenge-running", "turnstile", "cloudpmc-viewer-pow", "preparing to download"]
                if any(sig in html_text for sig in bot_signals):
                    return PDFDownloadResult(
                        success=False,
                        url=pdf_url,
                        final_url=final_url,
                        status_code=status,
                        content_type=content_type,
                        size=size,
                        failure_reason=DownloadFailureReason.BOT_PROTECTION,
                        error_message="Publisher presented an anti-bot challenge (reCAPTCHA / Proof-of-Work).",
                    )

                # HTML landing page
                if "html" in content_type or html_text.startswith("<!doctype") or "<html" in html_text:
                    return PDFDownloadResult(
                        success=False,
                        url=pdf_url,
                        final_url=final_url,
                        status_code=status,
                        content_type=content_type,
                        size=size,
                        failure_reason=DownloadFailureReason.LANDING_PAGE_ONLY,
                        error_message="URL returned an HTML landing page instead of a PDF.",
                    )

                return PDFDownloadResult(
                    success=False,
                    url=pdf_url,
                    final_url=final_url,
                    status_code=status,
                    content_type=content_type,
                    size=size,
                    failure_reason=DownloadFailureReason.INVALID_PDF,
                    error_message="Downloaded binary content did not contain a valid %PDF- header.",
                )

        except httpx.TimeoutException:
            return PDFDownloadResult(
                success=False,
                url=pdf_url,
                failure_reason=DownloadFailureReason.NETWORK_ERROR,
                error_message="Connection timed out after 30 seconds.",
            )
        except Exception as e:
            return PDFDownloadResult(
                success=False,
                url=pdf_url,
                failure_reason=DownloadFailureReason.NETWORK_ERROR,
                error_message=str(e),
            )

    def download_pdf(self, pdf_url: str) -> Tuple[bytes, str]:
        """
        Backward-compatible download helper. Returns (pdf_bytes, sha256_checksum)
        or raises PDFExtractionError.
        """
        result = self.detailed_download(pdf_url)
        if result.success and result.pdf_bytes and result.sha256:
            return result.pdf_bytes, result.sha256
        raise PDFExtractionError(result.error_message or f"PDF extraction failed ({result.failure_reason.value})")

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
