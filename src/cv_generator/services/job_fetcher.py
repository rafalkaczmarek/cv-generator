"""Fetch and extract main text from a job-offer URL.

Uses httpx for HTTP and trafilatura for boilerplate-free text extraction.
"""

from __future__ import annotations

import logging

import httpx
import trafilatura

from cv_generator.config import get_settings

logger = logging.getLogger(__name__)


class JobFetchError(RuntimeError):
    """Raised when the URL cannot be fetched or no text can be extracted."""


def fetch_job_text(url: str) -> str:
    settings = get_settings()
    logger.info("Fetching job offer url=%s", url)
    headers = {"User-Agent": settings.http_user_agent, "Accept-Language": "en,pl;q=0.9"}
    try:
        with httpx.Client(
            headers=headers,
            timeout=settings.http_timeout_seconds,
            follow_redirects=True,
        ) as client:
            response = client.get(url)
            response.raise_for_status()
            html = response.text
    except httpx.HTTPError as exc:
        logger.warning("Job fetch failed url=%s: %s", url, exc)
        raise JobFetchError(f"Failed to fetch {url}: {exc}") from exc

    extracted = trafilatura.extract(html, include_comments=False, include_tables=False)
    if not extracted or not extracted.strip():
        logger.warning("Job fetch extracted no text url=%s", url)
        raise JobFetchError("Could not extract readable content from the page")
    logger.info("Extracted job text url=%s chars=%d", url, len(extracted))
    return extracted.strip()
