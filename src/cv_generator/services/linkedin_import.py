"""Import a LinkedIn data export into a :class:`Profile`.

LinkedIn's "Get a copy of your data" feature produces a ZIP archive with
several CSV files. This module maps the relevant ones onto our Pydantic
``Profile`` model so the user can pre-fill the form instead of typing
everything by hand.

Supported CSVs (matched case-insensitively, with or without a folder prefix):

- ``Profile.csv``          → name, headline, summary, location, websites
- ``Positions.csv``        → experiences
- ``Education.csv``        → education
- ``Skills.csv``           → skills
- ``Languages.csv``        → languages
- ``Certifications.csv``   → certifications
- ``Email Addresses.csv``  → email

The importer is intentionally forgiving: missing files or columns are
skipped, and unparsable dates are dropped rather than raising. The user
reviews and corrects everything in the UI before saving.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path

from cv_generator.models import Certification, Education, Experience, Profile

__all__ = [
    "LinkedInImportError",
    "profile_from_linkedin_zip",
    "profile_from_linkedin_csv",
    "profile_from_csv_rows",
]


class LinkedInImportError(ValueError):
    """Raised when an upload cannot be interpreted as a LinkedIn export."""


# --- date parsing -----------------------------------------------------------

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _parse_date(raw: str | None) -> date | None:
    """Parse the loose date formats LinkedIn uses ("Mar 2019", "2019", ...)."""
    if not raw:
        return None
    value = raw.strip()
    if not value:
        return None

    # ISO date, e.g. "2019-03-01"
    iso = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", value)
    if iso:
        try:
            return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        except ValueError:
            return None

    # "Mar 2019" / "March 2019"
    mon = re.match(r"^([A-Za-z]{3,})\.?\s+(\d{4})$", value)
    if mon:
        month = _MONTHS.get(mon.group(1)[:3].lower())
        if month:
            return date(int(mon.group(2)), month, 1)

    # Bare year, e.g. "2019"
    year = re.match(r"^(\d{4})$", value)
    if year:
        return date(int(year.group(1)), 1, 1)

    return None


# --- CSV row mappers --------------------------------------------------------

def _get(row: Mapping[str, str], *names: str) -> str:
    """Case-insensitive lookup tolerant of LinkedIn's column-name variations."""
    lowered = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
    for name in names:
        value = lowered.get(name.lower())
        if value:
            return value
    return ""


def _profile_fields(rows: Sequence[Mapping[str, str]]) -> dict[str, object]:
    if not rows:
        return {}
    row = rows[0]
    first = _get(row, "First Name")
    last = _get(row, "Last Name")
    full_name = " ".join(part for part in (first, last) if part)

    fields: dict[str, object] = {}
    if full_name:
        fields["full_name"] = full_name
    if headline := _get(row, "Headline"):
        fields["headline"] = headline
    if summary := _get(row, "Summary"):
        fields["summary"] = summary
    if location := _get(row, "Geo Location", "Location"):
        fields["location"] = location

    for url in _extract_urls(_get(row, "Websites")):
        if "github.com" in url.lower() and "github_url" not in fields:
            fields["github_url"] = url
        elif "linkedin.com" in url.lower() and "linkedin_url" not in fields:
            fields["linkedin_url"] = url
        elif "website_url" not in fields:
            fields["website_url"] = url
    return fields


def _extract_urls(raw: str) -> list[str]:
    if not raw:
        return []
    # LinkedIn formats websites like "[PORTFOLIO:https://x],[OTHER:https://y]".
    return re.findall(r"https?://[^\s,;\]\[]+", raw)


def _experiences(rows: Sequence[Mapping[str, str]]) -> list[Experience]:
    out: list[Experience] = []
    for row in rows:
        company = _get(row, "Company Name", "Company")
        title = _get(row, "Title")
        if not company and not title:
            continue
        start = _parse_date(_get(row, "Started On", "Start Date"))
        finished = _get(row, "Finished On", "End Date")
        end = _parse_date(finished)
        out.append(
            Experience(
                company=company or "—",
                title=title or "—",
                location=_get(row, "Location") or None,
                start_date=start or date(1900, 1, 1),
                end_date=end,
                is_current=not finished,
                summary=_get(row, "Description") or None,
            )
        )
    return out


def _education(rows: Sequence[Mapping[str, str]]) -> list[Education]:
    out: list[Education] = []
    for row in rows:
        institution = _get(row, "School Name", "School")
        if not institution:
            continue
        out.append(
            Education(
                institution=institution,
                degree=_get(row, "Degree Name", "Degree") or None,
                field_of_study=_get(row, "Field Of Study") or None,
                start_date=_parse_date(_get(row, "Start Date")),
                end_date=_parse_date(_get(row, "End Date")),
                description=_get(row, "Notes", "Activities") or None,
            )
        )
    return out


def _skills(rows: Sequence[Mapping[str, str]]) -> list[str]:
    seen: list[str] = []
    for row in rows:
        name = _get(row, "Name", "Skill")
        if name and name not in seen:
            seen.append(name)
    return seen


def _languages(rows: Sequence[Mapping[str, str]]) -> list[str]:
    out: list[str] = []
    for row in rows:
        name = _get(row, "Name", "Language")
        if not name:
            continue
        proficiency = _get(row, "Proficiency")
        out.append(f"{name} - {proficiency}" if proficiency else name)
    return out


def _certifications(rows: Sequence[Mapping[str, str]]) -> list[Certification]:
    out: list[Certification] = []
    for row in rows:
        name = _get(row, "Name")
        if not name:
            continue
        url = _get(row, "Url", "URL")
        out.append(
            Certification(
                name=name,
                issuer=_get(row, "Authority", "Issuer") or None,
                issued=_parse_date(_get(row, "Started On", "Issued On")),
                url=url if url.lower().startswith("http") else None,
            )
        )
    return out


def _primary_email(rows: Sequence[Mapping[str, str]]) -> str | None:
    fallback: str | None = None
    for row in rows:
        email = _get(row, "Email Address", "Email")
        if not email:
            continue
        fallback = fallback or email
        if _get(row, "Primary").lower() in {"yes", "true", "1"}:
            return email
    return fallback


# --- file/section dispatch --------------------------------------------------

# Maps a normalized base filename to the profile section it feeds.
_SECTIONS = {
    "profile": "profile",
    "positions": "positions",
    "education": "education",
    "skills": "skills",
    "languages": "languages",
    "certifications": "certifications",
    "email addresses": "email",
}


def _section_for(filename: str) -> str | None:
    base = Path(filename).name.lower()
    if not base.endswith(".csv"):
        return None
    return _SECTIONS.get(base[:-4].strip())


def _read_rows(text: str) -> list[dict[str, str]]:
    text = text.lstrip("\ufeff")
    reader = csv.DictReader(io.StringIO(text))
    return [dict(row) for row in reader]


def profile_from_csv_rows(sections: Mapping[str, Sequence[Mapping[str, str]]]) -> Profile:
    """Build a Profile from already-parsed CSV rows, keyed by section name.

    Section keys: ``profile``, ``positions``, ``education``, ``skills``,
    ``languages``, ``certifications``, ``email``.
    """
    fields: dict[str, object] = {}
    fields.update(_profile_fields(sections.get("profile", [])))

    if email := _primary_email(sections.get("email", [])):
        fields.setdefault("email", email)

    fields.setdefault("full_name", fields.get("full_name") or "")
    if not fields["full_name"]:
        # full_name is required by the model; leave a placeholder for the user.
        fields["full_name"] = "—"

    return Profile(
        **fields,  # type: ignore[arg-type]
        experiences=_experiences(sections.get("positions", [])),
        education=_education(sections.get("education", [])),
        skills=_skills(sections.get("skills", [])),
        languages=_languages(sections.get("languages", [])),
        certifications=_certifications(sections.get("certifications", [])),
    )


def profile_from_linkedin_zip(source: bytes | str | Path) -> Profile:
    """Parse a LinkedIn export ZIP archive into a Profile.

    ``source`` may be the archive bytes, or a path to a ``.zip`` file or to a
    directory that contains the extracted CSVs.
    """
    sections: dict[str, list[dict[str, str]]] = {}

    if isinstance(source, (str, Path)) and Path(source).is_dir():
        for csv_path in Path(source).glob("*.csv"):
            section = _section_for(csv_path.name)
            if section:
                sections[section] = _read_rows(csv_path.read_text(encoding="utf-8-sig"))
    else:
        try:
            buffer = source if isinstance(source, bytes) else Path(source).read_bytes()
            with zipfile.ZipFile(io.BytesIO(buffer)) as zf:
                for name in zf.namelist():
                    section = _section_for(name)
                    if section:
                        sections[section] = _read_rows(zf.read(name).decode("utf-8-sig"))
        except zipfile.BadZipFile as exc:
            raise LinkedInImportError(
                "Plik nie jest poprawnym archiwum ZIP eksportu LinkedIn."
            ) from exc

    if not sections:
        raise LinkedInImportError(
            "W archiwum nie znaleziono rozpoznawalnych plików CSV "
            "(Profile.csv, Positions.csv, ...)."
        )
    return profile_from_csv_rows(sections)


def profile_from_linkedin_csv(filename: str, data: bytes | str) -> Profile:
    """Parse a single LinkedIn CSV file into a (partial) Profile.

    Useful when the user uploads just one CSV (e.g. ``Positions.csv``) instead
    of the whole archive.
    """
    section = _section_for(filename)
    if section is None:
        raise LinkedInImportError(
            f"Nierozpoznany plik CSV: {filename}. Oczekiwano jednego z: "
            "Profile.csv, Positions.csv, Education.csv, Skills.csv, "
            "Languages.csv, Certifications.csv, Email Addresses.csv."
        )
    text = data.decode("utf-8-sig") if isinstance(data, bytes) else data
    return profile_from_csv_rows({section: _read_rows(text)})
