"""Import profile data from a public LinkedIn profile URL.

LinkedIn publishes schema.org JSON-LD on public profile pages for search
engines. Work history on the main profile is often masked (asterisks) for
guests — the ``/details/projects/`` subpage usually exposes project history
with titles, dates and descriptions. This module merges imported data onto an
existing profile instead of replacing it.
"""

from __future__ import annotations

import json
import logging
import re
from contextlib import suppress
from datetime import date
from html import unescape
from typing import Any
from urllib.parse import urlparse

import httpx

from cv_generator.config import get_settings
from cv_generator.models import Education, Experience, Profile
from cv_generator.services.education_normalize import normalize_degree_and_field
from cv_generator.services.profile_merge import (
    education_match_index,
    fill_education_entry,
    merge_profiles,
)

__all__ = [
    "LinkedInUrlImportError",
    "merge_profiles",
    "profile_from_linkedin_html",
    "profile_from_linkedin_url",
    "is_linkedin_profile_url",
]

_MSG_BLOCKED_999 = (
    "LinkedIn zablokował automatyczne pobieranie profilu (kod 999). "
    "To ochrona antybotowa po stronie LinkedIn — nie da się jej obejść "
    "z poziomu aplikacji. Otwórz profil w przeglądarce, zapisz stronę "
    "jako HTML i wgraj plik poniżej, albo użyj oficjalnego eksportu ZIP."
)


class LinkedInUrlImportError(ValueError):
    """Raised when a LinkedIn profile URL cannot be fetched or parsed."""


_LINKEDIN_PROFILE_RE = re.compile(
    r"^https?://(?:[a-z]{2,3}\.)?linkedin\.com/in/[\w%-]+/?(?:\?.*)?$",
    re.IGNORECASE,
)

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

_DATE_RANGE_RE = re.compile(
    r"^(?P<start>(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}"
    r"|\d{4})\s*[-–—]\s*(?P<end>(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
    r"\s+\d{4}|\d{4}|Present|Obecnie)$",
    re.IGNORECASE,
)
_SINGLE_DATE_RE = re.compile(
    r"^(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}$",
    re.IGNORECASE,
)

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en,pl;q=0.9",
}

logger = logging.getLogger(__name__)


def is_linkedin_profile_url(url: str) -> bool:
    """Return True when *url* looks like a LinkedIn ``/in/`` profile page."""
    normalized = _profile_base_url(url)
    return bool(_LINKEDIN_PROFILE_RE.match(normalized))


def _profile_base_url(url: str) -> str:
    value = url.strip()
    if not value:
        return value
    if not value.startswith(("http://", "https://")):
        value = f"https://{value}"
    parsed = urlparse(value)
    if not parsed.netloc.endswith("linkedin.com"):
        return value
    path = re.sub(r"(/in/[^/]+)/details(?:/.*)?/?$", r"\1/", parsed.path, flags=re.IGNORECASE)
    if not path.endswith("/"):
        path = f"{path}/"
    return f"https://www.linkedin.com{path}"


def _details_projects_url(profile_url: str) -> str:
    base = _profile_base_url(profile_url).rstrip("/")
    return f"{base}/details/projects/"


def _details_education_url(profile_url: str) -> str:
    base = _profile_base_url(profile_url).rstrip("/")
    return f"{base}/details/education/"


def _is_masked(text: str | None) -> bool:
    if not text:
        return False
    stripped = text.strip()
    if not stripped:
        return False
    without_stars = stripped.replace("*", "").replace("\\", "").strip()
    if not without_stars:
        return True
    star_ratio = stripped.count("*") / len(stripped)
    return star_ratio >= 0.3


def _is_placeholder(text: str | None) -> bool:
    return not text or not text.strip() or text.strip() == "—"


def _fetch_profile_html(url: str) -> str:
    settings = get_settings()
    headers = {**_BROWSER_HEADERS, "Accept-Language": "en,pl;q=0.9"}
    if settings.http_user_agent and "CVGeneratorBot" not in settings.http_user_agent:
        headers["User-Agent"] = settings.http_user_agent
    try:
        with httpx.Client(
            headers=headers,
            timeout=settings.http_timeout_seconds,
            follow_redirects=True,
        ) as client:
            response = client.get(url)
            html = response.text
            if response.status_code == 999:
                if _extract_json_ld_blocks(html) or _section_plain_text(html, "Projects"):
                    logger.warning("LinkedIn HTTP 999 but page still contained usable data")
                    return html
                logger.warning("LinkedIn anti-bot response (HTTP 999)")
                raise LinkedInUrlImportError(_MSG_BLOCKED_999)
            response.raise_for_status()
            logger.info("Fetched LinkedIn HTML status=%s chars=%d", response.status_code, len(html))
            return html
    except LinkedInUrlImportError:
        raise
    except httpx.HTTPError as exc:
        logger.warning("LinkedIn profile fetch failed: %s", exc)
        raise LinkedInUrlImportError(
            f"Nie udało się pobrać profilu LinkedIn ({url}): {exc}"
        ) from exc


def _extract_json_ld_blocks(html: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for match in re.finditer(
        r'<script type="application/ld\+json">(.*?)</script>',
        html,
        flags=re.DOTALL | re.IGNORECASE,
    ):
        raw = match.group(1).strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            blocks.append(payload)
    return blocks


def _person_entity(blocks: list[dict[str, Any]]) -> dict[str, Any] | None:
    for block in blocks:
        main = block.get("mainEntity")
        if isinstance(main, dict) and main.get("@type") == "Person":
            return main
        if block.get("@type") == "Person":
            return block
        graph = block.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                if isinstance(item, dict) and item.get("@type") == "Person":
                    return item
    return None


def _parse_loose_date(raw: str | None) -> date | None:
    if not raw:
        return None
    value = raw.strip()
    if not value:
        return None
    mon = re.match(r"^([A-Za-z]{3,})\.?\s+(\d{4})$", value)
    if mon:
        month = _MONTHS.get(mon.group(1)[:3].lower())
        if month:
            return date(int(mon.group(2)), month, 1)
    year = re.match(r"^(\d{4})$", value)
    if year:
        return date(int(year.group(1)), 1, 1)
    return None


def _parse_date_range(raw: str) -> tuple[date | None, date | None, bool]:
    text = _normalize_date_text(raw)
    if not text or text == "-":
        return None, None, False
    if re.search(r"present|obecnie", text, re.IGNORECASE):
        start_part = re.split(r"\s*-\s*", text, maxsplit=1)[0].strip()
        return _parse_loose_date(start_part), None, True
    match = _DATE_RANGE_RE.match(text)
    if match:
        end_raw = match.group("end")
        is_current = bool(re.search(r"present|obecnie", end_raw, re.IGNORECASE))
        return (
            _parse_loose_date(match.group("start")),
            None if is_current else _parse_loose_date(end_raw),
            is_current,
        )
    if _SINGLE_DATE_RE.match(text):
        return _parse_loose_date(text), None, False
    return None, None, False


def _schema_date(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, int):
        return date(value, 1, 1)
    if isinstance(value, str):
        return _parse_loose_date(value.strip())
    return None


def _location_from_address(address: object) -> str | None:
    if not isinstance(address, dict):
        return None
    locality = str(address.get("addressLocality") or "").strip()
    country = str(address.get("addressCountry") or "").strip()
    parts = [part for part in (locality, country) if part]
    return ", ".join(parts) if parts else None


# Tailwind arbitrary variants (e.g. ``[&>*]:mb-0``) put ``>`` inside quoted attributes —
# naive ``<[^>]+>`` stops too early and leaks CSS fragments into plain text.
_TAG_RE = re.compile(r"<(?:[^>\"']|\"[^\"]*\"|'[^']*')*>", re.IGNORECASE)


def _html_to_plain(html: str) -> str:
    text = re.sub(
        r"<(script|style)(?:[^>\"']|\"[^\"]*\"|'[^']*')*>.*?</\1>",
        "",
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</(p|div|h[1-6]|li|span)>", "\n", text, flags=re.IGNORECASE)
    text = _TAG_RE.sub(" ", text)
    text = unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _section_plain_text(html: str, heading: str, stop_headings: tuple[str, ...] = ()) -> str:
    plain = _html_to_plain(html)
    if stop_headings:
        stops = "|".join(re.escape(item) for item in stop_headings)
        pattern = (
            rf"(?is)(?:^|\n)\s*{re.escape(heading)}\s*\n+"
            rf"(.*?)(?=\n\s*(?:{stops})\s*(?:\n|$)|\Z)"
        )
    else:
        pattern = rf"(?is)(?:^|\n)\s*{re.escape(heading)}\s*\n+(.*)\Z"
    match = re.search(pattern, plain)
    return match.group(1).strip() if match else ""


def _extract_technologies(text: str) -> tuple[str, list[str]]:
    techs: list[str] = []
    cleaned = text
    for match in re.finditer(r"\(([^)]+)\)", text):
        inner = match.group(1)
        if any(ch.isalpha() for ch in inner) and not inner.lower().startswith("http"):
            parts = [p.strip() for p in re.split(r",|;", inner) if p.strip()]
            if 1 < len(parts) <= 12:
                techs.extend(parts)
                cleaned = cleaned.replace(match.group(0), " ").strip()
    return cleaned, techs


def _infer_company(project_name: str, description: str) -> str:
    haystack = f"{project_name} {description}".lower()
    mapping = {
        "pekao": "Bank Pekao S.A.",
        "virtamed": "Virtamed",
        "jemyjemy": "JemyJemy",
        "bph": "Bank BPH",
        "bgk": "Bank Gospodarstwa Krajowego",
        "otherdocs": "Otherdocs",
        "lunch for 5km": "Lunch for 5km",
    }
    for needle, company in mapping.items():
        if needle in haystack:
            return company
    return "Projekt"


def _normalize_date_text(text: str) -> str:
    return text.replace("–", "-").replace("—", "-").strip()


def _looks_like_degree_title(text: str) -> bool:
    return bool(_DEGREE_HINT_RE.search(text))


def _looks_like_institution_name(text: str) -> bool:
    return bool(_INSTITUTION_HINT_RE.search(text))


def _is_date_line(line: str) -> bool:
    normalized = _normalize_date_text(line)
    return bool(_DATE_RANGE_RE.match(normalized) or _SINGLE_DATE_RE.match(line.strip()))


# Tailwind arbitrary variants (e.g. ``[&>*]:mb-0``) contain ``>`` inside attributes —
# naive ``<h3[^>]*>`` stops too early and leaks CSS into titles.
_H3_BLOCK_RE = re.compile(
    r"<h3\b((?:[^>\"']|\"[^\"]*\"|'[^']*')*)>(.*?)</h3>",
    re.DOTALL | re.IGNORECASE,
)

_JUNK_PROJECT_TITLE_RE = re.compile(
    r"(?i)(sign in|contact info|email or phone|password|liked by|"
    r"interesting post|join now|user agreement|forgot password|"
    r"mutual connections|explore top content|see all courses|"
    r"see their title)"
)


def _clean_project_title(raw: str) -> str:
    title = _html_to_plain(raw) if "<" in raw else raw
    title = title.strip()
    if '">' in title:
        title = title.rsplit('">', 1)[-1]
    title = re.sub(r'^[\s"\'>]+', "", title)
    return re.sub(r"\s+", " ", title).strip()


def _is_junk_project_entry(title: str, description: str) -> bool:
    if not title or len(title) > 150:
        return True
    if _JUNK_PROJECT_TITLE_RE.search(title):
        return True
    if re.search(r"text-\[\d+px\]|\*\]:mb-0|font-semibold\">", title):
        return True
    if description and re.search(
        r"(?is)\d+\s+followers.*view profile|view profile.*\d+\s+followers",
        description,
    ):
        return True
    return False


def _projects_html_slice(html: str) -> str:
    """HTML or plain text for the Projects section only (excludes Courses, feed, etc.)."""
    match = re.search(
        r"(?is)<h2[^>]*>\s*Projects\s*</h2>(.*?)(?=<h2\b|</section>|$)",
        html,
    )
    if match:
        return match.group(1)
    return _section_plain_text(
        html,
        "Projects",
        stop_headings=(
            "Languages",
            "Courses",
            "View ",
            "Explore ",
            "Activity",
            "People",
            "Interests",
        ),
    )


def _projects_from_h3_html(html: str) -> list[tuple[str, str, str]]:
    entries: list[tuple[str, str, str]] = []
    h3_matches = list(_H3_BLOCK_RE.finditer(html))
    for index, match in enumerate(h3_matches):
        title = _clean_project_title(match.group(2))
        if not title or _is_masked(title):
            continue
        next_start = h3_matches[index + 1].start() if index + 1 < len(h3_matches) else len(html)
        body_html = html[match.end() : next_start]
        body = _html_to_plain(body_html).strip()
        lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
        date_line = ""
        desc_lines: list[str] = []
        for line in lines:
            if not date_line and _is_date_line(line):
                date_line = line
            elif line.lower() not in {"see project", "github"}:
                desc_lines.append(line)
        description = "\n".join(desc_lines)
        if _is_junk_project_entry(title, description):
            continue
        entries.append((title, date_line, description))
    return entries


def _projects_line_entries(section_text: str) -> list[tuple[str, str, str]]:
    """Parse plain-text Projects section (no HTML tags)."""
    skip = {"see project", "github", "projects"}
    entries: list[tuple[str, str, str]] = []
    lines = [ln.strip() for ln in section_text.splitlines()]
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line or line.lower() in skip or _is_date_line(line):
            index += 1
            continue

        title = line
        index += 1
        date_line = ""
        if index < len(lines) and _is_date_line(lines[index]):
            date_line = lines[index]
            index += 1

        desc_lines: list[str] = []
        while index < len(lines):
            nxt = lines[index]
            if not nxt:
                index += 1
                continue
            if _is_date_line(nxt):
                break
            if nxt.lower() in skip:
                index += 1
                continue
            if index + 1 < len(lines) and _is_date_line(lines[index + 1]):
                break
            desc_lines.append(nxt)
            index += 1

        if not _is_masked(title):
            entries.append((title, date_line, "\n".join(desc_lines)))

    return entries


def _projects_section_entries(section_text: str) -> list[tuple[str, str, str]]:
    """Return ``(title, date_line, description)`` tuples parsed from a Projects section."""
    if re.search(r"<h3\b", section_text, re.IGNORECASE):
        return _projects_from_h3_html(section_text)
    return _projects_line_entries(section_text)


def _experiences_from_projects_html(html: str) -> list[Experience]:
    projects_slice = _projects_html_slice(html)
    if not projects_slice:
        return []
    raw_entries = _projects_section_entries(projects_slice)

    experiences: list[Experience] = []
    for title, date_line, description in raw_entries:
        title = _clean_project_title(title)
        if _is_masked(title) or _is_masked(description) or _is_junk_project_entry(title, description):
            continue
        summary, technologies = _extract_technologies(description)
        start, end, is_current = _parse_date_range(date_line) if date_line else (None, None, False)
        bullets = [ln.strip() for ln in summary.splitlines() if ln.strip()]
        experiences.append(
            Experience(
                company=_infer_company(title, summary),
                title=title,
                start_date=start or date(1900, 1, 1),
                end_date=end,
                is_current=is_current,
                summary=summary or None,
                bullets=bullets[1:] if len(bullets) > 1 else [],
                technologies=technologies,
            )
        )
    return experiences


def _courses_html_slice(html: str) -> str:
    """HTML or plain text for the Courses section only."""
    match = re.search(
        r"(?is)<h2[^>]*>\s*Courses\s*</h2>(.*?)(?=<h2\b|</section>|$)",
        html,
    )
    if match:
        return match.group(1)
    return _section_plain_text(
        html,
        "Courses",
        stop_headings=("Projects", "Languages", "View ", "Explore ", "Activity"),
    )


def _skills_from_courses_html(html: str) -> list[str]:
    section = _courses_html_slice(html)
    skills: list[str] = []

    if re.search(r"<h3\b", section, re.IGNORECASE):
        for match in _H3_BLOCK_RE.finditer(section):
            line = _clean_project_title(match.group(2))
            if not line or line == "-" or _is_masked(line):
                continue
            if _is_junk_project_entry(line, ""):
                continue
            if line.lower() in {"courses", "see project"}:
                continue
            if line not in skills:
                skills.append(line)
        return skills

    plain = _html_to_plain(section) if "<" in section else section
    for line in plain.splitlines():
        line = line.strip()
        if not line or line == "-" or _is_masked(line):
            continue
        if line.lower() in {"courses", "see project"}:
            continue
        if _is_junk_project_entry(line, ""):
            continue
        if line not in skills:
            skills.append(line)
    return skills


_JUNK_EDU_LINE_RE = re.compile(
    r"(?i)(see all|show all|sign in|view profile|followers|contact info|"
    r"join now|user agreement|forgot password|mutual connections)"
)

_INSTITUTION_HINT_RE = re.compile(
    r"(?i)\b(university|uniwersytet|politechnik\w*|akademia|college|school|institute|technolog\w*)\b"
)
_DEGREE_HINT_RE = re.compile(
    r"(?i)\b(inżynier|ingenieur|bachelor|master|mgr|licencjat|doktor|ph\.?d|"
    r"m\.?sc|b\.?sc|engineer|diploma|magister|licencj)\b"
)

_EDU_HEADINGS = ("Education", "Wykształcenie", "Edukacja")
_EDU_STOP_HEADINGS = (
    "Experience",
    "Projects",
    "Courses",
    "Languages",
    "Skills",
    "Licenses",
    "Licences",
    "Volunteer",
    "Activity",
    "People",
    "Interests",
    "About",
    "View ",
    "Explore ",
)


def _education_title_text(edu: Education) -> str:
    return f"{edu.degree or ''} {edu.field_of_study or ''}".strip()


def _make_education(
    *,
    institution: str,
    degree: str | None = None,
    field_of_study: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    description: str | None = None,
) -> Education:
    normalized_degree, normalized_field = normalize_degree_and_field(degree, field_of_study)
    return Education(
        institution=institution,
        degree=normalized_degree,
        field_of_study=normalized_field,
        start_date=start_date,
        end_date=end_date,
        description=description,
    )


def _degree_from_edu_item(item: dict[str, Any]) -> str | None:
    institution = str(item.get("name") or "").strip().lower()
    role = item.get("member") if isinstance(item.get("member"), dict) else {}
    for source in (role, item):
        for key in ("roleName", "description", "credentialCategory"):
            value = source.get(key)
            if not isinstance(value, str):
                continue
            text = value.strip()
            if not text or _is_masked(text) or text.lower() == institution:
                continue
            if _is_date_line(text) or _JUNK_EDU_LINE_RE.search(text):
                continue
            return text
    return None


def _alumni_items(person: dict[str, Any]) -> list[dict[str, Any]]:
    raw = person.get("alumniOf") or []
    if isinstance(raw, dict):
        return [raw]
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    return []


def _education_from_person(person: dict[str, Any]) -> list[Education]:
    out: list[Education] = []
    for item in _alumni_items(person):
        institution = str(item.get("name") or "").strip()
        if not institution or _is_masked(institution):
            continue
        role = item.get("member") if isinstance(item.get("member"), dict) else {}
        out.append(
            _make_education(
                institution=institution,
                degree=_degree_from_edu_item(item),
                start_date=_schema_date(role.get("startDate")),
                end_date=_schema_date(role.get("endDate")),
            )
        )
    return out


def _education_html_slice(html: str) -> str:
    for heading in _EDU_HEADINGS:
        match = re.search(
            r"(?is)<h2\b(?:[^>\"']|\"[^\"]*\"|'[^']*')*>"
            r"(?:(?!</h2>).)*?" + re.escape(heading) + r"\b"
            r"(?:(?!</h2>).)*?</h2>"
            r"(.*?)(?=<h2\b|</section>|$)",
            html,
        )
        if match:
            return match.group(1)
        text = _section_plain_text(html, heading, stop_headings=_EDU_STOP_HEADINGS)
        if text:
            return text
    return ""


def _is_junk_edu_line(line: str) -> bool:
    if not line or len(line) > 180:
        return True
    if _JUNK_EDU_LINE_RE.search(line):
        return True
    if re.search(r"text-\[\d+px\]|\*\]:mb-0|font-semibold\">", line):
        return True
    return _is_junk_project_entry(line, "")


def _education_from_h3_html(html: str) -> list[Education]:
    out: list[Education] = []
    h3_matches = list(_H3_BLOCK_RE.finditer(html))
    for index, match in enumerate(h3_matches):
        heading = _clean_project_title(match.group(2))
        if not heading or _is_masked(heading) or _is_junk_edu_line(heading):
            continue
        if heading.lower() in {h.lower() for h in _EDU_HEADINGS}:
            continue
        next_start = h3_matches[index + 1].start() if index + 1 < len(h3_matches) else len(html)
        body = _html_to_plain(html[match.end() : next_start]).strip()
        lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
        date_line = ""
        degree_line = ""
        institution = heading

        if _looks_like_degree_title(heading) and not _looks_like_institution_name(heading):
            degree_line = heading
            institution = ""
            for line in lines:
                if _is_date_line(line):
                    if not date_line:
                        date_line = line
                    continue
                if not institution and not _is_junk_edu_line(line):
                    institution = line
            if not institution:
                continue
        else:
            for line in lines:
                if _is_date_line(line):
                    if not date_line:
                        date_line = line
                    continue
                if not degree_line and not _is_junk_edu_line(line):
                    degree_line = line
        start, end, _is_current = _parse_date_range(date_line) if date_line else (None, None, False)
        out.append(
            _make_education(
                institution=institution,
                degree=degree_line or None,
                start_date=start,
                end_date=end,
            )
        )
    return out


def _education_from_plain_text(section_text: str) -> list[Education]:
    skip = {h.lower() for h in _EDU_HEADINGS} | {"see all", "show all"}
    lines = [ln.strip() for ln in section_text.splitlines() if ln.strip()]
    out: list[Education] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.lower() in skip or _is_date_line(line) or _is_junk_edu_line(line):
            index += 1
            continue
        institution = line
        index += 1
        degree_line = ""
        date_line = ""
        if index < len(lines) and not _is_date_line(lines[index]):
            nxt = lines[index]
            if not _is_junk_edu_line(nxt):
                degree_line = nxt
                index += 1
        if index < len(lines) and _is_date_line(lines[index]):
            date_line = lines[index]
            index += 1
        start, end, _is_current = _parse_date_range(date_line) if date_line else (None, None, False)
        out.append(
            _make_education(
                institution=institution,
                degree=degree_line or None,
                start_date=start,
                end_date=end,
            )
        )
    return out


def _education_from_html(html: str) -> list[Education]:
    section = _education_html_slice(html)
    if not section:
        return []
    if re.search(r"<h3\b", section, re.IGNORECASE):
        return _education_from_h3_html(section)
    return _education_from_plain_text(_html_to_plain(section) if "<" in section else section)


def _merge_education(base: list[Education], extra: list[Education]) -> list[Education]:
    out = list(base)
    for edu in extra:
        idx = education_match_index(out, edu)
        if idx is None:
            out.append(edu)
        else:
            out[idx] = fill_education_entry(out[idx], edu)
    return out


def _languages_from_person(person: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for item in person.get("knowsLanguage") or []:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            if name and not _is_masked(name):
                out.append(name)
        elif isinstance(item, str) and item.strip() and not _is_masked(item):
            out.append(item.strip())
    return out


def _experiences_from_person(person: dict[str, Any]) -> list[Experience]:
    """JSON-LD work history — skipped when LinkedIn masks titles/companies."""
    works_for = person.get("worksFor") or []
    titles = person.get("jobTitle") or []
    if not isinstance(works_for, list):
        return []

    out: list[Experience] = []
    for index, item in enumerate(works_for):
        if not isinstance(item, dict):
            continue
        company = str(item.get("name") or "").strip()
        location = str(item.get("location") or "").strip() or None
        title = ""
        if isinstance(titles, list) and index < len(titles):
            title = str(titles[index] or "").strip()

        if _is_masked(company) or _is_masked(title) or _is_masked(location or ""):
            continue
        if not company and not title:
            continue

        role = item.get("member") if isinstance(item.get("member"), dict) else {}
        start = _schema_date(role.get("startDate"))
        end = _schema_date(role.get("endDate"))
        is_current = end is None and start is not None

        out.append(
            Experience(
                company=company or "—",
                title=title or "—",
                location=location,
                start_date=start or date(1900, 1, 1),
                end_date=end,
                is_current=is_current,
            )
        )
    return out


def _headline_from_og_title(html: str, full_name: str) -> str | None:
    match = re.search(
        r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"',
        html,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    title = match.group(1).strip()
    for suffix in (" | LinkedIn", " – LinkedIn", " - LinkedIn"):
        if title.endswith(suffix):
            title = title[: -len(suffix)].strip()
            break
    if full_name and title.startswith(full_name):
        remainder = title[len(full_name) :].lstrip(" -–—|")
        return remainder or None
    return title or None


def _profile_from_person(
    person: dict[str, Any],
    *,
    source_url: str,
    html: str,
    experiences: list[Experience],
    skills: list[str],
    education: list[Education] | None = None,
) -> Profile:
    full_name = str(person.get("name") or "").strip() or "—"
    if _is_masked(full_name):
        full_name = "—"
    description = str(person.get("description") or "").strip() or None
    if description and _is_masked(description):
        description = None
    headline = _headline_from_og_title(html, full_name) or description

    linkedin_url = str(person.get("sameAs") or person.get("url") or source_url).strip()
    if linkedin_url and not linkedin_url.startswith("http"):
        linkedin_url = source_url

    return Profile(
        full_name=full_name,
        headline=headline,
        summary=description,
        location=_location_from_address(person.get("address")),
        linkedin_url=linkedin_url or source_url,
        experiences=experiences,
        education=education if education is not None else _education_from_person(person),
        skills=skills,
        languages=_languages_from_person(person),
    )


def _source_url_from_html(html: str, fallback: str) -> str:
    person = _person_entity(_extract_json_ld_blocks(html))
    if person:
        for key in ("sameAs", "url"):
            raw = str(person.get(key) or "").strip()
            if raw:
                candidate = _profile_base_url(raw)
                if _LINKEDIN_PROFILE_RE.match(candidate):
                    return candidate
    match = re.search(
        r'<meta[^>]+property="og:url"[^>]+content="([^"]+)"',
        html,
        flags=re.IGNORECASE,
    )
    if match:
        candidate = _profile_base_url(match.group(1))
        if _LINKEDIN_PROFILE_RE.match(candidate):
            return candidate
    return fallback


def _build_profile_from_pages(
    *,
    source_url: str,
    html_main: str,
    projects_html: str = "",
    education_html: str = "",
) -> Profile:
    blocks = _extract_json_ld_blocks(html_main)
    person = _person_entity(blocks)
    projects_source = projects_html or html_main

    experiences = _experiences_from_projects_html(projects_source)
    if not experiences and projects_source != html_main:
        experiences = _experiences_from_projects_html(html_main)
    if not experiences:
        experiences = _experiences_from_person(person or {})

    skills = _skills_from_courses_html(projects_source)
    education = _merge_education(
        _education_from_person(person or {}),
        _education_from_html(html_main),
    )
    if education_html:
        education = _merge_education(education, _education_from_html(education_html))

    if person is None and not experiences and not skills and not education:
        raise LinkedInUrlImportError(
            "Na stronie profilu nie znaleziono publicznych danych. "
            "Profil może być prywatny lub wymagać logowania — użyj eksportu LinkedIn."
        )

    if person is None:
        person = {"name": "", "description": ""}

    profile = _profile_from_person(
        person,
        source_url=source_url,
        html=html_main,
        experiences=experiences,
        skills=skills,
        education=education,
    )
    if (
        _is_placeholder(profile.full_name)
        and not profile.experiences
        and not profile.education
        and not profile.skills
    ):
        raise LinkedInUrlImportError(
            "Nie udało się odczytać danych profilu z podanej strony."
        )
    return profile


def profile_from_linkedin_html(html: str, *, source_url: str | None = None) -> Profile:
    """Build a :class:`Profile` from LinkedIn profile HTML saved in a browser.

    Use when LinkedIn blocks automated URL fetches (HTTP 999). Open the public
    profile (and optionally ``/details/projects/``) in a browser, save the page
    as HTML, then pass the file contents here.
    """
    text = html.strip()
    if not text:
        raise LinkedInUrlImportError("Plik HTML jest pusty.")

    logger.info("Importing LinkedIn profile from saved HTML chars=%d", len(text))

    fallback = "https://www.linkedin.com/in/imported/"
    if source_url:
        candidate = _profile_base_url(source_url)
        if _LINKEDIN_PROFILE_RE.match(candidate):
            fallback = candidate
    resolved = _source_url_from_html(text, fallback)
    return _build_profile_from_pages(
        source_url=resolved,
        html_main=text,
        projects_html=text,
        education_html="",
    )


def profile_from_linkedin_url(url: str) -> Profile:
    """Fetch a public LinkedIn profile and build a :class:`Profile`.

    Reads schema.org JSON-LD from the main profile page and project history
    from ``/details/projects/``. Education titles (degree / field of study)
    are taken from the public Education section when JSON-LD omits them.
    Masked guest-only fields (asterisks) are ignored. For complete data use
    the official LinkedIn export or a browser-saved HTML page.
    """
    base_url = _profile_base_url(url)
    if not _LINKEDIN_PROFILE_RE.match(base_url):
        raise LinkedInUrlImportError(
            "Podaj poprawny URL profilu LinkedIn, np. "
            "https://www.linkedin.com/in/jan-kowalski/"
        )

    logger.info("Importing LinkedIn profile from URL")
    html_main = _fetch_profile_html(base_url)

    projects_html = html_main
    with suppress(LinkedInUrlImportError):
        projects_html = _fetch_profile_html(_details_projects_url(base_url))

    education_html = ""
    person = _person_entity(_extract_json_ld_blocks(html_main))
    education_seed = _merge_education(
        _education_from_person(person or {}),
        _education_from_html(html_main),
    )
    if education_seed and any(not _education_title_text(item) for item in education_seed):
        with suppress(LinkedInUrlImportError):
            education_html = _fetch_profile_html(_details_education_url(base_url))

    return _build_profile_from_pages(
        source_url=base_url,
        html_main=html_main,
        projects_html=projects_html,
        education_html=education_html,
    )
