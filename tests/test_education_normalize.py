"""Tests for education degree/field normalization."""

from __future__ import annotations

from cv_generator.services.education_normalize import (
    normalize_degree_and_field,
    split_degree_and_field,
    translate_degree,
    translate_field_of_study,
)


def test_split_polish_degree_and_english_field() -> None:
    degree, field = split_degree_and_field("Inżynier (Inż.), Computer Science")
    assert degree == "Inżynier (Inż.)"
    assert field == "Computer Science"


def test_split_bachelor_of_science_in_field() -> None:
    degree, field = split_degree_and_field("Bachelor of Science in Computer Science")
    assert degree == "Bachelor of Science"
    assert field == "Computer Science"


def test_translate_polish_engineer_degree() -> None:
    assert translate_degree("Inżynier (Inż.)") == "Bachelor of Engineering"
    assert translate_degree("Magister (Mgr)") == "Master's Degree"


def test_translate_polish_field_of_study() -> None:
    assert translate_field_of_study("Informatyka") == "Computer Science"
    assert translate_field_of_study("Computer Science") == "Computer Science"


def test_normalize_splits_and_translates_combined_value() -> None:
    degree, field = normalize_degree_and_field("Inżynier (Inż.), Computer Science")
    assert degree == "Bachelor of Engineering"
    assert field == "Computer Science"


def test_normalize_splits_and_translates_polish_field() -> None:
    degree, field = normalize_degree_and_field("Inżynier (Inż.), Informatyka")
    assert degree == "Bachelor of Engineering"
    assert field == "Computer Science"
