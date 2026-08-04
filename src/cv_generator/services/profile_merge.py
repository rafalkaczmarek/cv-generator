"""Merge profiles incrementally and surface scalar-field conflicts for resolution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from difflib import SequenceMatcher
from html import escape
from typing import Any, Literal

from cv_generator.models import Education, Experience, Profile

__all__ = [
    "Choice",
    "FieldConflict",
    "ProfileMergeResult",
    "apply_conflict_resolutions",
    "highlight_text_diff",
    "merge_profiles",
    "merge_profiles_with_conflicts",
]

Choice = Literal["current", "incoming"]

SCALAR_FIELDS: tuple[tuple[str, str], ...] = (
    ("full_name", "Imię i nazwisko"),
    ("headline", "Headline"),
    ("summary", "Krótkie podsumowanie"),
    ("email", "Email"),
    ("phone", "Telefon"),
    ("location", "Lokalizacja"),
    ("linkedin_url", "LinkedIn URL"),
    ("github_url", "GitHub URL"),
    ("website_url", "Strona WWW"),
)


@dataclass(frozen=True, slots=True)
class FieldConflict:
    field: str
    label: str
    current: str
    incoming: str


@dataclass(frozen=True, slots=True)
class ProfileMergeResult:
    """Auto-merged profile plus scalar conflicts that need a user choice."""

    profile: Profile
    conflicts: list[FieldConflict]


def _is_placeholder(text: str | None) -> bool:
    return not text or not text.strip() or text.strip() == "—"


def _as_text(value: object | None) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _values_equal(a: object | None, b: object | None) -> bool:
    return _as_text(a) == _as_text(b)


def _experience_key(exp: Experience) -> tuple[str, str, date]:
    return (exp.company.lower().strip(), exp.title.lower().strip(), exp.start_date)


def _education_key(edu: Education) -> tuple[str, date | None]:
    return (edu.institution.lower().strip(), edu.start_date)


def _merge_list_fields(
    existing: Profile,
    incoming: Profile,
) -> dict[str, Any]:
    merged_experiences = list(existing.experiences)
    seen_exp = {_experience_key(e) for e in merged_experiences}
    for exp in incoming.experiences:
        key = _experience_key(exp)
        if key not in seen_exp:
            merged_experiences.append(exp)
            seen_exp.add(key)

    merged_education = list(existing.education)
    seen_edu = {_education_key(e) for e in merged_education}
    for edu in incoming.education:
        key = _education_key(edu)
        if key not in seen_edu:
            merged_education.append(edu)
            seen_edu.add(key)

    merged_skills = list(existing.skills)
    for skill in incoming.skills:
        if skill not in merged_skills:
            merged_skills.append(skill)

    merged_courses = list(existing.courses)
    for course in incoming.courses:
        if course not in merged_courses:
            merged_courses.append(course)

    merged_languages = list(existing.languages)
    for language in incoming.languages:
        if language not in merged_languages:
            merged_languages.append(language)

    return {
        "experiences": merged_experiences,
        "education": merged_education,
        "skills": merged_skills,
        "courses": merged_courses,
        "languages": merged_languages,
    }


def merge_profiles(existing: Profile | None, incoming: Profile) -> Profile:
    """Fill gaps in *existing* with data from *incoming*; append new list items.

    When both sides have a non-empty scalar value, *existing* wins.
    """
    return merge_profiles_with_conflicts(existing, incoming).profile


def merge_profiles_with_conflicts(
    existing: Profile | None,
    incoming: Profile,
) -> ProfileMergeResult:
    """Like :func:`merge_profiles`, but also reports differing non-empty scalars."""
    if existing is None:
        return ProfileMergeResult(profile=incoming, conflicts=[])

    lists = _merge_list_fields(existing, incoming)
    conflicts: list[FieldConflict] = []
    scalars: dict[str, Any] = {}

    for field, label in SCALAR_FIELDS:
        current_val = getattr(existing, field)
        incoming_val = getattr(incoming, field)
        current_text = _as_text(current_val)
        incoming_text = _as_text(incoming_val)

        if _is_placeholder(current_text):
            scalars[field] = incoming_val if not _is_placeholder(incoming_text) else current_val
            continue

        if _is_placeholder(incoming_text) or _values_equal(current_val, incoming_val):
            scalars[field] = current_val
            continue

        conflicts.append(
            FieldConflict(
                field=field,
                label=label,
                current=current_text,
                incoming=incoming_text,
            )
        )
        scalars[field] = current_val

    if _is_placeholder(_as_text(scalars.get("full_name"))):
        scalars["full_name"] = existing.full_name

    profile = Profile(**scalars, **lists)
    return ProfileMergeResult(profile=profile, conflicts=conflicts)


def apply_conflict_resolutions(
    profile: Profile,
    conflicts: list[FieldConflict],
    choices: dict[str, Choice],
) -> Profile:
    """Apply per-field choices (``current`` / ``incoming``) onto *profile*."""
    updates: dict[str, Any] = {}
    by_field = {c.field: c for c in conflicts}
    for field, choice in choices.items():
        conflict = by_field.get(field)
        if conflict is None:
            continue
        value = conflict.current if choice == "current" else conflict.incoming
        if field == "full_name":
            updates[field] = value or "—"
        else:
            updates[field] = value or None
    if not updates:
        return profile
    return profile.model_copy(update=updates)


def highlight_text_diff(left: str, right: str) -> tuple[str, str]:
    """Return HTML snippets for *left* and *right* with differing spans marked."""
    matcher = SequenceMatcher(None, left, right)
    left_parts: list[str] = []
    right_parts: list[str] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        left_chunk = escape(left[i1:i2])
        right_chunk = escape(right[j1:j2])
        if tag == "equal":
            left_parts.append(left_chunk)
            right_parts.append(right_chunk)
        elif tag == "delete":
            left_parts.append(f'<mark style="background:#ffd6d6">{left_chunk}</mark>')
        elif tag == "insert":
            right_parts.append(f'<mark style="background:#d6ffd6">{right_chunk}</mark>')
        else:  # replace
            left_parts.append(f'<mark style="background:#ffd6d6">{left_chunk}</mark>')
            right_parts.append(f'<mark style="background:#d6ffd6">{right_chunk}</mark>')
    empty = '<span style="color:#888">(puste)</span>'
    return (
        "".join(left_parts) or empty,
        "".join(right_parts) or empty,
    )
