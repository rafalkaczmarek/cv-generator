"""Tests for Pydantic model normalization."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from cv_generator.models import Experience, JobOffer, Profile


def test_profile_normalizes_comma_separated_skills() -> None:
    profile = Profile(full_name="X", skills="python, fastapi,  docker ")
    assert profile.skills == ["python", "fastapi", "docker"]


def test_experience_normalizes_newline_bullets() -> None:
    exp = Experience(
        company="A",
        title="Dev",
        start_date=date(2020, 1, 1),
        bullets="first\n  second \n\nthird",
    )
    assert exp.bullets == ["first", "second", "third"]


def test_profile_sorted_experiences_current_first() -> None:
    profile = Profile(
        full_name="X",
        experiences=[
            Experience(company="Old", title="A", start_date=date(2015, 1, 1), end_date=date(2017, 1, 1)),
            Experience(company="Now", title="B", start_date=date(2022, 1, 1), is_current=True),
            Experience(company="Mid", title="C", start_date=date(2019, 1, 1), end_date=date(2021, 1, 1)),
        ],
    )
    ordered = [e.company for e in profile.sorted_experiences()]
    assert ordered[0] == "Now"


def test_job_offer_requires_raw_text() -> None:
    with pytest.raises(ValidationError):
        JobOffer()  # type: ignore[call-arg]


def test_job_offer_slug_is_filesystem_safe() -> None:
    offer = JobOffer(
        raw_text="...", title="Senior Python / Engineer", company="ACME Corp."
    )
    slug = offer.slug()
    assert " " not in slug
    assert "/" not in slug
    assert "." not in slug
    assert slug
