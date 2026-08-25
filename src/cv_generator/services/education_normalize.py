"""Split and translate education degree / field-of-study values from LinkedIn imports."""

from __future__ import annotations

import re
import unicodedata

__all__ = [
    "looks_like_degree",
    "normalize_degree_and_field",
    "split_degree_and_field",
    "translate_degree",
    "translate_field_of_study",
]

_DEGREE_HINT_RE = re.compile(
    r"(?i)\b("
    r"bachelor|master|doctor|phd|mba|bsc|msc|ba\b|ma\b|b\.?s\.?|m\.?s\.?|"
    r"licencjat|inżynier|inzynier|mgr|dr\b|engineer|degree|tytuł|tytul"
    r")\b"
)

_DEGREE_TRANSLATIONS: tuple[tuple[str, str], ...] = (
    ("magister inżynier (mgr inż.)", "Master of Engineering"),
    ("magister inzynier (mgr inz.)", "Master of Engineering"),
    ("magister (mgr inż.)", "Master of Engineering"),
    ("magister (mgr inz.)", "Master of Engineering"),
    ("mgr inż.", "Master of Engineering"),
    ("mgr inz.", "Master of Engineering"),
    ("inżynier (inż.)", "Bachelor of Engineering"),
    ("inzynier (inz.)", "Bachelor of Engineering"),
    ("magister (mgr)", "Master's Degree"),
    ("licencjat (lic.)", "Bachelor's Degree"),
    ("licencjat", "Bachelor's Degree"),
    ("inżynier", "Bachelor of Engineering"),
    ("inzynier", "Bachelor of Engineering"),
    ("magister", "Master's Degree"),
    ("doktor nauk", "Doctor of Science"),
    ("doktor", "Doctorate"),
)

_FIELD_TRANSLATIONS: dict[str, str] = {
    "informatyka": "Computer Science",
    "automatyka i robotyka": "Automation and Robotics",
    "automatyka": "Automation",
    "elektronika i telekomunikacja": "Electronics and Telecommunications",
    "elektronika": "Electronics",
    "elektrotechnika": "Electrical Engineering",
    "mechanika": "Mechanical Engineering",
    "matematyka": "Mathematics",
    "fizyka": "Physics",
}


def _normalize_key(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text or "")
    ascii_only = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", ascii_only.lower()).strip()


def looks_like_degree(text: str) -> bool:
    value = text.strip()
    if not value or len(value) > 160:
        return False
    return bool(_DEGREE_HINT_RE.search(value))


def split_degree_and_field(raw: str) -> tuple[str | None, str | None]:
    """Split values like ``Inżynier (Inż.), Computer Science`` or ``Bachelor of Science in X``."""
    text = raw.strip()
    if not text:
        return None, None
    for sep in (" in ", " IN ", " z tytułu ", " z ", ", ", ","):
        if sep not in text:
            continue
        left, right = text.split(sep, 1)
        left, right = left.strip(" ,;"), right.strip(" ,;")
        if left and right and 1 < len(right) < 80 and not looks_like_degree(right):
            return left, right
    return text, None


def translate_degree(degree: str) -> str:
    key = _normalize_key(degree)
    for pattern, english in _DEGREE_TRANSLATIONS:
        if key == _normalize_key(pattern):
            return english
    return degree


def translate_field_of_study(field: str) -> str:
    key = _normalize_key(field)
    return _FIELD_TRANSLATIONS.get(key, field)


def normalize_degree_and_field(
    degree: str | None,
    field_of_study: str | None = None,
) -> tuple[str | None, str | None]:
    """Split a combined degree string and translate Polish titles to English."""
    deg = (degree or "").strip() or None
    field = (field_of_study or "").strip() or None
    if deg and not field:
        split_degree, split_field = split_degree_and_field(deg)
        if split_field:
            deg, field = split_degree, split_field
        elif deg.lower().startswith("bachelor of science in "):
            field = deg[23:].strip() or field
            deg = "Bachelor of Science"
        elif deg.lower().startswith("master of science in "):
            field = deg[21:].strip() or field
            deg = "Master of Science"
    if deg:
        deg = translate_degree(deg)
    if field:
        field = translate_field_of_study(field)
    return deg, field
