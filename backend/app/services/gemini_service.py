import logging
import re
import time
from typing import Any, Callable, Optional, Tuple
import google.generativeai as genai
from app.core.config import settings

logger = logging.getLogger(__name__)

# Daily quota exhaustion keywords returned by Gemini API
_DAILY_QUOTA_PATTERNS = [
    "resource_exhausted",
    "generatecontentrequestsperday",
    "free_tier_requests",
    "quota exceeded",
    "daily limit",
    "limit: 20",
]


def ensure_gemini_configured() -> bool:
    """Ensure google.generativeai is configured with the valid API key."""
    if settings.gemini_api_key and settings.gemini_api_key != "placeholder-gemini-key":
        genai.configure(api_key=settings.gemini_api_key)
        return True
    return False


# Initial configuration
ensure_gemini_configured()


def classify_gemini_error(exc: Exception) -> Tuple[bool, bool, float]:
    """
    Classify a Gemini API exception.
    Returns:
      (is_daily_quota, is_transient_rate_limit, retry_after_seconds)
    """
    err_str = str(exc).lower()

    # 1. Check for Daily Quota Exhaustion (Fail-Fast: do not retry, do not model-hop)
    is_daily_quota = any(pat in err_str for pat in _DAILY_QUOTA_PATTERNS)
    if is_daily_quota:
        return True, False, 0.0

    # 2. Check for Transient 429 (Per-Minute / Per-Token rate limits)
    is_transient = "429" in err_str or "rate limit" in err_str or "too many requests" in err_str
    retry_after = 2.5
    if is_transient:
        match = re.search(r"retry in ([0-9\.]+)s", err_str)
        if match:
            try:
                retry_after = float(match.group(1))
            except ValueError:
                pass

    return False, is_transient, retry_after


class GeminiService:
    """Centralized service for invoking Gemini models with structured error handling."""

    @staticmethod
    def call_with_retry(
        fn: Callable,
        *args,
        max_retries: int = 2,
        retry_delay: float = 2.0,
        **kwargs,
    ) -> Any:
        """
        Execute a Gemini API callable with intelligent retry:
        - Daily quota exhausted (429 RESOURCE_EXHAUSTED) -> Fail fast immediately.
        - Transient 429 / 503 -> Exponential backoff using retry-after guidance.
        - 404 / NotFound -> Raise immediately.
        """
        ensure_gemini_configured()
        last_exc = None

        for attempt in range(1, max_retries + 1):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                last_exc = e
                err_str = str(e)

                # 404 Not Found -> Fail immediately
                if "404" in err_str or "not found" in err_str:
                    raise e

                is_daily, is_transient, wait_sec = classify_gemini_error(e)

                # Daily quota: stop immediately, do not waste retries
                if is_daily:
                    logger.error(f"Gemini daily quota exhausted (fail-fast): {e}")
                    raise RuntimeError(
                        "Gemini API daily quota reached (429 RESOURCE_EXHAUSTED). "
                        "Please wait for your daily quota to reset or upgrade your Gemini API tier in Google AI Studio."
                    ) from e

                # Transient rate limit (RPM/TPM): wait and retry
                if is_transient and attempt < max_retries:
                    wait = min(wait_sec, 15.0)
                    logger.warning(f"Gemini API rate limited (429). Retrying in {wait:.1f}s (attempt {attempt}/{max_retries})...")
                    time.sleep(wait)
                    continue

                # Other transient errors (500, 503): standard exponential backoff
                if attempt < max_retries:
                    wait = retry_delay * (2 ** (attempt - 1))
                    logger.warning(f"Gemini API error ({e}). Retrying in {wait:.1f}s (attempt {attempt}/{max_retries})...")
                    time.sleep(wait)

        if last_exc is not None:
            raise last_exc
        raise RuntimeError("Gemini API call failed after retries.")
