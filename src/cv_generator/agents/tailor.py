"""CVTailor — rewrites profile content to match a specific job offer.

Strict rules in the prompt forbid the LLM from inventing facts: it can only
re-phrase, reorder and emphasize what is already in the profile.
"""

from __future__ import annotations

import logging
from datetime import date

from langchain_core.prompts import ChatPromptTemplate

from cv_generator.graph.state import GapAnalysis
from cv_generator.models import Experience, JobOffer, Profile, TailoredCV, TailoredExperience
from cv_generator.services.llm import get_json_llm, get_llm, parse_llm_json

logger = logging.getLogger(__name__)

# LinkedIn import uses 1900-01-01 when a date could not be parsed.
_UNKNOWN_YEAR = 1900

_SYSTEM = (
    "You are an expert resume writer tailoring an existing profile to a specific "
    "job offer. Hard rules:\n"
    "1. NEVER invent companies, titles, dates, technologies or achievements. Only "
    "rephrase or emphasize facts that already appear in the profile.\n"
    "2. Mirror the job's vocabulary where the profile honestly supports it.\n"
    "3. Keep bullets concrete and outcome-oriented; start with a strong verb.\n"
    "4. Keep summary to 2-4 sentences. Bullets max 1-2 lines each.\n"
    "5. Include EVERY experience entry from the profile in experiences — jobs and "
    "projects alike. Do not omit, merge, or drop any. You may reorder by relevance "
    "and rewrite bullets, but the count and identity (company + title + dates) of "
    "each entry must be preserved. Always set date_range from profile start_date/"
    "end_date for every entry, including projects (company Projekt/Project).\n"
    "6. Do not output education — it is copied verbatim from the profile.\n"
    "7. Output language: {language}.\n"
    "Reply with valid JSON only."
)

_USER = (
    "Job offer:\n"
    "Title: {job_title}\nCompany: {job_company}\n"
    "Requirements: {requirements}\nNice to have: {nice_to_have}\n"
    "Keywords to emphasize when supported by the profile: {keywords}\n\n"
    "Gap analysis notes:\n{gap_notes}\n\n"
    "Candidate profile (source of truth):\n{profile_json}\n\n"
    "Previous reviewer feedback (may be empty): {feedback}\n\n"
    "Produce a TailoredCV JSON with the following fields: "
    "headline, summary, experiences (list of objects with company, title, "
    "location, date_range, bullets — one object per profile experience, none "
    "omitted), skills (ordered: most relevant first), courses, languages."
)

_SUMMARY_SYSTEM = (
    "You are an expert resume writer rewriting only the professional summary "
    "of a tailored CV for a specific job offer. Hard rules:\n"
    "1. NEVER invent companies, titles, dates, technologies or achievements. "
    "Only rephrase or emphasize facts that already appear in the profile.\n"
    "2. Mirror the job's vocabulary where the profile honestly supports it.\n"
    "3. Keep the summary to 2-4 sentences.\n"
    "4. Produce a meaningfully different wording from the current summary "
    "while staying truthful to the profile.\n"
    "5. Output language: {language}.\n"
    "Reply with valid JSON only: {{\"summary\": \"...\"}}."
)

_SUMMARY_USER = (
    "Job offer:\n"
    "Title: {job_title}\nCompany: {job_company}\n"
    "Requirements: {requirements}\nNice to have: {nice_to_have}\n"
    "Keywords to emphasize when supported by the profile: {keywords}\n\n"
    "Gap analysis notes:\n{gap_notes}\n\n"
    "Candidate profile (source of truth):\n{profile_json}\n\n"
    "Current CV headline: {headline}\n"
    "Current summary (rewrite this — do not repeat it verbatim):\n{current_summary}\n"
)


def tailor_cv(
    *,
    profile: Profile,
    job: JobOffer,
    gap: GapAnalysis,
    feedback: str = "",
    language: str = "en",
) -> TailoredCV:
    logger.info("Tailoring CV language=%s has_feedback=%s", language, bool(feedback.strip()))
    llm = get_json_llm() if _supports_json_mode() else get_llm()

    prompt = ChatPromptTemplate.from_messages([("system", _SYSTEM), ("user", _USER)])
    chain = prompt | llm

    response = chain.invoke(
        {
            "language": language,
            "job_title": job.title or "",
            "job_company": job.company or "",
            "requirements": "; ".join(job.requirements) or "(none)",
            "nice_to_have": "; ".join(job.nice_to_have) or "(none)",
            "keywords": ", ".join(job.keywords) or "(none)",
            "gap_notes": "\n".join(gap.get("emphasis_notes", []) or []) or "(none)",
            "profile_json": profile.model_dump_json(),
            "feedback": feedback or "(none)",
        }
    )

    parsed = parse_llm_json(response.content)
    return _build_tailored_cv(parsed, profile, language=language)


def rewrite_summary(
    *,
    profile: Profile,
    job: JobOffer,
    gap: GapAnalysis,
    current_summary: str,
    headline: str = "",
    language: str = "en",
) -> str:
    """Generate an alternative professional summary for an existing tailored CV."""
    logger.info("Rewriting CV summary language=%s", language)
    llm = get_json_llm() if _supports_json_mode() else get_llm()

    prompt = ChatPromptTemplate.from_messages(
        [("system", _SUMMARY_SYSTEM), ("user", _SUMMARY_USER)]
    )
    chain = prompt | llm

    response = chain.invoke(
        {
            "language": language,
            "job_title": job.title or "",
            "job_company": job.company or "",
            "requirements": "; ".join(job.requirements) or "(none)",
            "nice_to_have": "; ".join(job.nice_to_have) or "(none)",
            "keywords": ", ".join(job.keywords) or "(none)",
            "gap_notes": "\n".join(gap.get("emphasis_notes", []) or []) or "(none)",
            "profile_json": profile.model_dump_json(),
            "headline": headline or profile.headline or "",
            "current_summary": current_summary or "(empty)",
        }
    )

    parsed = parse_llm_json(response.content)
    summary = str(parsed.get("summary") or "").strip()
    if not summary:
        summary = (current_summary or profile.summary or "").strip()
    return summary


def _build_tailored_cv(parsed: dict, profile: Profile, *, language: str = "en") -> TailoredCV:
    experiences_raw = parsed.get("experiences") or []
    unused = list(profile.experiences)
    experiences: list[TailoredExperience] = []
    for item in experiences_raw:
        if not isinstance(item, dict):
            continue
        matched = _pop_matching_experience(item, unused)
        date_range = (
            _format_date_range(
                matched.start_date, matched.end_date, matched.is_current, language=language
            )
            if matched
            else ""
        )
        if not date_range:
            date_range = str(item.get("date_range") or "")
        experiences.append(
            TailoredExperience(
                company=str(item.get("company") or ""),
                title=str(item.get("title") or ""),
                location=item.get("location") or (matched.location if matched else None),
                date_range=date_range,
                bullets=[str(b) for b in (item.get("bullets") or []) if str(b).strip()],
            )
        )

    if not experiences:
        experiences = [
            _fallback_experience(exp, language=language) for exp in profile.sorted_experiences()
        ]

    return TailoredCV(
        full_name=profile.full_name,
        headline=str(parsed.get("headline") or profile.headline or "").strip(),
        summary=str(parsed.get("summary") or profile.summary or "").strip(),
        email=str(profile.email) if profile.email else None,
        phone=profile.phone,
        location=profile.location,
        linkedin_url=str(profile.linkedin_url) if profile.linkedin_url else None,
        github_url=str(profile.github_url) if profile.github_url else None,
        website_url=str(profile.website_url) if profile.website_url else None,
        experiences=experiences,
        education_lines=[_format_education(e) for e in profile.education],
        skills=_as_str_list(parsed.get("skills")) or profile.skills,
        courses=_as_str_list(parsed.get("courses")) or profile.courses,
        languages=_as_str_list(parsed.get("languages")) or profile.languages,
        language=language,
    )


def _fallback_experience(exp: Experience, *, language: str = "en") -> TailoredExperience:
    return TailoredExperience(
        company=exp.company,
        title=exp.title,
        location=exp.location,
        date_range=_format_date_range(
            exp.start_date, exp.end_date, exp.is_current, language=language
        ),
        bullets=list(exp.bullets),
    )


def _norm_key(value: str) -> str:
    return value.strip().casefold()


def _pop_matching_experience(item: dict, unused: list[Experience]) -> Experience | None:
    """Pop the profile experience that corresponds to an LLM experience object."""
    company = _norm_key(str(item.get("company") or ""))
    title = _norm_key(str(item.get("title") or ""))
    if not company and not title:
        return None

    for index, exp in enumerate(unused):
        if _norm_key(exp.company) == company and _norm_key(exp.title) == title:
            return unused.pop(index)

    title_hits = [i for i, exp in enumerate(unused) if title and _norm_key(exp.title) == title]
    if len(title_hits) == 1:
        return unused.pop(title_hits[0])
    return None


def _format_date_range(
    start: date,
    end: date | None,
    is_current: bool,
    *,
    language: str = "en",
) -> str:
    start_str = start.strftime("%m/%Y") if start.year > _UNKNOWN_YEAR else ""
    end_str = end.strftime("%m/%Y") if end is not None and end.year > _UNKNOWN_YEAR else ""
    if is_current:
        present = "obecnie" if language.lower().startswith("pl") else "Present"
        return f"{start_str} - {present}" if start_str else present
    if start_str and end_str:
        return f"{start_str} - {end_str}"
    return start_str or end_str


def _education_title(edu) -> str | None:
    degree = (edu.degree or "").strip() or None
    field = (edu.field_of_study or "").strip() or None
    if degree and field and field.lower() not in degree.lower():
        return f"{degree}, {field}"
    return degree or field


def _education_years(edu) -> str | None:
    start = str(edu.start_date.year) if edu.start_date else ""
    end = str(edu.end_date.year) if edu.end_date else ""
    if start and end:
        return f"{start} - {end}"
    return start or end or None


def _format_education(edu) -> str:
    title = _education_title(edu)
    institution = (edu.institution or "").strip() or None
    line = " — ".join(part for part in (title, institution) if part)
    years = _education_years(edu)
    if years:
        return f"{line} ({years})" if line else years
    return line


def _as_str_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _supports_json_mode() -> bool:
    from cv_generator.config import get_settings

    return get_settings().llm_provider in ("openai", "gemini")
