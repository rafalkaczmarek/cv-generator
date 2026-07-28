"""Tests for incremental profile merge and conflict resolution."""

from __future__ import annotations

from datetime import date

from cv_generator.models import Experience, Profile
from cv_generator.services.profile_merge import (
    apply_conflict_resolutions,
    highlight_text_diff,
    merge_profiles,
    merge_profiles_with_conflicts,
)


def test_merge_fills_empty_scalars_and_keeps_existing() -> None:
    existing = Profile(
        full_name="Jan Kowalski",
        headline="Mój nagłówek",
        email="jan@example.com",
        skills=["Python"],
    )
    incoming = Profile(
        full_name="Z LinkedIn",
        headline="Inny headline",
        location="Warszawa",
        skills=["Angular"],
        languages=["Polish"],
    )

    merged = merge_profiles(existing, incoming)

    assert merged.full_name == "Jan Kowalski"
    assert merged.headline == "Mój nagłówek"
    assert merged.location == "Warszawa"
    assert merged.skills == ["Python", "Angular"]
    assert merged.languages == ["Polish"]


def test_merge_with_conflicts_reports_differing_scalars() -> None:
    existing = Profile(
        full_name="Jan Kowalski",
        headline="Lokalny headline",
        summary="Moje podsumowanie",
        phone="+48 111",
    )
    incoming = Profile(
        full_name="Jan Nowak",
        headline="LinkedIn headline",
        summary="Moje podsumowanie",
        phone="+48 222",
        location="Kraków",
    )

    result = merge_profiles_with_conflicts(existing, incoming)

    assert result.profile.location == "Kraków"
    assert result.profile.headline == "Lokalny headline"
    assert result.profile.summary == "Moje podsumowanie"
    fields = {c.field for c in result.conflicts}
    assert fields == {"full_name", "headline", "phone"}
    assert "summary" not in fields


def test_merge_appends_new_experiences_only() -> None:
    existing = Profile(
        full_name="Jan",
        experiences=[
            Experience(
                company="Acme",
                title="Dev",
                start_date=date(2020, 1, 1),
            )
        ],
    )
    incoming = Profile(
        full_name="Jan",
        experiences=[
            Experience(
                company="Acme",
                title="Dev",
                start_date=date(2020, 1, 1),
                summary="z LinkedIn",
            ),
            Experience(
                company="Beta",
                title="Lead",
                start_date=date(2022, 1, 1),
            ),
        ],
    )

    merged = merge_profiles(existing, incoming)
    assert len(merged.experiences) == 2
    assert merged.experiences[0].summary is None
    assert merged.experiences[1].company == "Beta"


def test_apply_conflict_resolutions_picks_incoming() -> None:
    profile = Profile(full_name="Jan Kowalski", headline="Stary")
    result = merge_profiles_with_conflicts(
        profile,
        Profile(full_name="Jan Nowak", headline="Nowy"),
    )
    resolved = apply_conflict_resolutions(
        result.profile,
        result.conflicts,
        {"full_name": "incoming", "headline": "current"},
    )
    assert resolved.full_name == "Jan Nowak"
    assert resolved.headline == "Stary"


def test_highlight_text_diff_marks_changes() -> None:
    left, right = highlight_text_diff("xxx", "yyy")
    assert left == '<mark style="background:#ffd6d6">xxx</mark>'
    assert right == '<mark style="background:#d6ffd6">yyy</mark>'
    same_l, same_r = highlight_text_diff("same", "same")
    assert same_l == "same"
    assert same_r == "same"
    empty_l, empty_r = highlight_text_diff("", "value")
    assert "(puste)" in empty_l
    assert "value" in empty_r
