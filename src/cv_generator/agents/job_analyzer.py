"""Extract structured requirements from a job description."""

from __future__ import annotations

import logging

from langchain_core.prompts import ChatPromptTemplate

from cv_generator.models import JobOffer
from cv_generator.services.job_fetcher import JobFetchError, fetch_job_text
from cv_generator.services.llm import get_json_llm, parse_llm_json

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are a recruitment analyst. Given the raw text of a job offer, extract "
    "a structured summary with: company, job title, location, hard requirements, "
    "nice-to-have, responsibilities and the ATS keywords most worth matching. "
    "Be concise, deduplicate, and return only what is actually mentioned. "
    "Reply with valid JSON only."
)

_USER = (
    "Job offer source URL: {url}\n\n"
    "Raw text:\n---\n{raw_text}\n---\n\n"
    "Return JSON with keys: title, company, location, requirements (list of strings), "
    "nice_to_have (list), responsibilities (list), keywords (list of short tokens, "
    "ideally tools/technologies/skill names)."
)


def analyze_job(*, url: str | None, raw_text: str | None) -> JobOffer:
    """Build a JobOffer from a URL, raw text, or both.

    If `raw_text` is missing, the URL is fetched and parsed. If both are given,
    the explicit raw_text wins (user already curated it).
    """
    if not raw_text and not url:
        raise ValueError("Either url or raw_text must be provided")

    source = "raw_text" if raw_text else "url"
    text = raw_text or fetch_job_text(url)  # type: ignore[arg-type]
    logger.info("Analyzing job offer source=%s chars=%d", source, len(text))

    llm = get_json_llm()
    prompt = ChatPromptTemplate.from_messages([("system", _SYSTEM), ("user", _USER)])
    chain = prompt | llm

    response = chain.invoke({"url": url or "(pasted text, no URL)", "raw_text": text[:12000]})
    parsed = parse_llm_json(response.content)

    offer = JobOffer(
        url=url,
        raw_text=text,
        title=parsed.get("title"),
        company=parsed.get("company"),
        location=parsed.get("location"),
        requirements=_as_str_list(parsed.get("requirements")),
        nice_to_have=_as_str_list(parsed.get("nice_to_have")),
        responsibilities=_as_str_list(parsed.get("responsibilities")),
        keywords=_as_str_list(parsed.get("keywords")),
    )
    logger.info(
        "Job analyzed title=%s company=%s requirements=%d keywords=%d",
        offer.title,
        offer.company,
        len(offer.requirements),
        len(offer.keywords),
    )
    return offer


def _as_str_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


__all__ = ["analyze_job", "JobFetchError"]
