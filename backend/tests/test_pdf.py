import pytest
from app.services.pdf import (
    PDFService,
    SSRFValidationError,
    calculate_sha256,
    validate_url_security,
)


def test_ssrf_validation_valid_urls():
    assert validate_url_security("https://arxiv.org/pdf/2301.12345.pdf") == "https://arxiv.org/pdf/2301.12345.pdf"
    assert validate_url_security("http://example.com/paper.pdf") == "http://example.com/paper.pdf"


def test_ssrf_validation_rejects_forbidden_schemes():
    with pytest.raises(SSRFValidationError, match="Forbidden URL scheme"):
        validate_url_security("file:///etc/passwd")

    with pytest.raises(SSRFValidationError, match="Forbidden URL scheme"):
        validate_url_security("ftp://127.0.0.1/paper.pdf")


def test_ssrf_validation_rejects_localhost_and_private_ips():
    with pytest.raises(SSRFValidationError, match="Forbidden target host"):
        validate_url_security("http://localhost:8000/pdf")

    with pytest.raises(SSRFValidationError, match="Forbidden target host"):
        validate_url_security("http://127.0.0.1/secret.pdf")

    with pytest.raises(SSRFValidationError, match="Forbidden target host"):
        validate_url_security("http://0.0.0.0/internal.pdf")


def test_sha256_checksum():
    data = b"%PDF-1.4 test pdf content"
    checksum = calculate_sha256(data)
    assert isinstance(checksum, str)
    assert len(checksum) == 64


def test_pdf_clean_text():
    service = PDFService()
    raw = "Header\n\n\n\nSection 1\x00\r\nSome   text   with   spaces."
    cleaned = service.clean_text(raw)
    assert "\x00" not in cleaned
    assert "Some text with spaces." in cleaned
