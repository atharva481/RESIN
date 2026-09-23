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


# Model cooldown tracking: model_name -> cooldown_until_timestamp
_MODEL_COOLDOWNS: dict = {}


class GeminiService:
    """Centralized service for invoking Gemini models with structured error handling and cooldown tracking."""

    @classmethod
    def mark_model_cooldown(cls, model_name: str, cooldown_seconds: float = 60.0, reason: str = "") -> None:
        """
        Mark a model on cooldown for a given duration (default 60s) due to rate-limiting or errors.
        This prevents subsequent requests from trying and failing on this model, allowing them
        to immediately skip straight to the healthy fallback model.
        """
        if not model_name:
            return
        norm_name = model_name.strip()
        cooldown_until = time.time() + cooldown_seconds
        _MODEL_COOLDOWNS[norm_name] = cooldown_until
        logger.warning(
            f"Gemini model '{norm_name}' placed on {cooldown_seconds:.0f}s cooldown (until +{cooldown_seconds:.0f}s). "
            f"Reason: {reason or 'rate-limited / transient error'}"
        )

    @classmethod
    def is_model_on_cooldown(cls, model_name: str) -> bool:
        """Check if a model is currently in its cooldown window."""
        if not model_name:
            return False
        norm_name = model_name.strip()
        cooldown_until = _MODEL_COOLDOWNS.get(norm_name, 0.0)
        if time.time() < cooldown_until:
            return True
        if norm_name in _MODEL_COOLDOWNS:
            _MODEL_COOLDOWNS.pop(norm_name, None)
        return False

    @classmethod
    def get_prioritized_models(cls, candidates: list) -> list:
        """
        Reorder candidate models so healthy (non-cooldown) models appear first.
        If the primary model was recently rate-limited, this allows the next request
        to immediately skip straight to the fallback model without paying the round-trip
        failure delay on the primary model again.
        """
        now = time.time()
        healthy: list = []
        in_cooldown: list = []

        seen = set()
        for m in candidates:
            if not m or m in seen:
                continue
            seen.add(m)
            norm_name = m.strip()
            cooldown_until = _MODEL_COOLDOWNS.get(norm_name, 0.0)
            if now < cooldown_until:
                in_cooldown.append((cooldown_until, m))
            else:
                healthy.append(m)

        # In-cooldown models sorted by earliest recovery time
        in_cooldown.sort(key=lambda x: x[0])
        cooldown_sorted = [m for _, m in in_cooldown]

        result = healthy + cooldown_sorted
        if not healthy and cooldown_sorted:
            logger.info(f"All candidate models are on cooldown. Using earliest-expiring model: {result[0]}")
        elif in_cooldown and healthy:
            logger.info(
                f"Model cooldown active: prioritizing healthy models {healthy} over cooldown models {[m for _, m in in_cooldown]}"
            )

        return result or candidates

    @classmethod
    def log_model_usage(
        cls,
        model_name: str,
        is_fallback: bool = False,
        reason: str = "",
        timer: Any = None,
    ) -> None:
        """Log model used and warning if fallback was triggered."""
        from app.core.timing import logger as timing_logger
        req_id = getattr(timer, "request_id", "rag") if timer else "rag"
        timing_logger.info(f"[{req_id}] model_used: {model_name}")
        if is_fallback:
            timing_logger.warning(f"[{req_id}] FALLBACK TRIGGERED, reason: {reason}")


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

