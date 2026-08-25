"""Tests for incremental profile merge and conflict resolution."""

from __future__ import annotations

from datetime import date

from cv_generator.models import Education, Experience, Profile
from cv_generator.services.profile_merge import (
    apply_conflict_resolutions,
    fill_education_entry,
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
        courses=["AWS Developer"],
        languages=["Polish"],
    )

    merged = merge_profiles(existing, incoming)

    assert merged.full_name == "Jan Kowalski"
    assert merged.headline == "Mój nagłówek"
    assert merged.location == "Warszawa"
    assert merged.skills == ["Python", "Angular"]
    assert merged.courses == ["AWS Developer"]
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


def test_merge_fills_missing_education_degree() -> None:
    existing = Profile(
        full_name="Jan",
        education=[
            Education(
                institution="Lodz University of Technology",
                degree="",
                field_of_study="",
                start_date=date(2011, 1, 1),
                end_date=date(2015, 1, 1),
            )
        ],
    )
    incoming = Profile(
        full_name="Jan",
        education=[
            Education(
                institution="Łódź University of Technology",
                degree="Bachelor of Science in Computer Science",
                field_of_study="Computer Science",
                # Different dates than existing — still the same school.
                start_date=date(2011, 10, 1),
                end_date=date(2015, 6, 1),
            )
        ],
    )

    merged = merge_profiles(existing, incoming)
    assert len(merged.education) == 1
    assert merged.education[0].degree == "Bachelor of Science in Computer Science"
    assert merged.education[0].field_of_study == "Computer Science"
    # Keep original dates when already set; only fill blanks.
    assert merged.education[0].start_date == date(2011, 1, 1)


def test_merge_fills_degree_from_csv_with_blank_school_name() -> None:
    existing = Profile(
        full_name="Jan",
        education=[
            Education(
                institution="Lodz University of Technology",
                degree="",
                field_of_study="",
                start_date=date(2011, 1, 1),
                end_date=date(2015, 1, 1),
            )
        ],
    )
    incoming = Profile(
        full_name="—",
        education=[
            Education(
                institution="—",
                degree="Inżynier (Inż.)",
                start_date=date(2011, 1, 1),
                end_date=date(2015, 1, 1),
            )
        ],
    )
    merged = merge_profiles(existing, incoming)
    assert len(merged.education) == 1
    assert merged.education[0].institution == "Lodz University of Technology"
    assert merged.education[0].degree == "Inżynier (Inż.)"


def test_merge_fills_single_stub_education_from_different_school_label() -> None:
    existing = Profile(
        full_name="Jan",
        education=[
            Education(
                institution="Lodz University of Technology",
                degree="",
                start_date=date(2011, 1, 1),
            )
        ],
    )
    incoming = Profile(
        full_name="Jan",
        education=[
            Education(
                institution="Politechnika Łódzka",
                degree="Bachelor of Science",
                field_of_study="Computer Science",
            )
        ],
    )
    merged = merge_profiles(existing, incoming)
    assert len(merged.education) == 1
    assert merged.education[0].degree == "Bachelor of Science"
    assert merged.education[0].field_of_study == "Computer Science"


def test_merge_html_imported_education_by_matching_years() -> None:
    existing = Profile(
        full_name="Jan",
        education=[
            Education(
                institution="Lodz University of Technology",
                degree="Bachelor",
                start_date=date(2011, 1, 1),
                end_date=date(2015, 1, 1),
            )
        ],
    )
    incoming = Profile(
        full_name="Jan",
        education=[
            Education(
                institution="Politechnika Łódzka",
                degree="Inżynier (Inż.), Informatyka",
                start_date=date(2011, 1, 1),
                end_date=date(2015, 1, 1),
            )
        ],
    )
    merged = merge_profiles(existing, incoming)
    assert len(merged.education) == 1
    assert merged.education[0].institution == "Lodz University of Technology"
    assert merged.education[0].degree == "Bachelor"


def test_fill_education_skips_institution_name_in_degree_field() -> None:
    existing = Education(
        institution="Lodz University of Technology",
        degree="",
        start_date=date(2011, 1, 1),
        end_date=date(2015, 1, 1),
    )
    incoming = Education(
        institution="Inżynier (Inż.)",
        degree="Politechnika Łódzka",
        start_date=date(2011, 1, 1),
        end_date=date(2015, 1, 1),
    )
    filled = fill_education_entry(existing, incoming)
    assert filled.degree == ""


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
