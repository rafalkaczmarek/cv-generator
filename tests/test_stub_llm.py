"""Tests for the deterministic LLM stub used by E2E flows."""

from __future__ import annotations

import json

from cv_generator.services.stub_llm import get_stub_llm


def _tailor_prompt(profile: dict) -> str:
    return (
        "You are an expert resume writer tailoring an existing profile.\n"
        "Produce a TailoredCV JSON with experiences.\n"
        "Output language: en.\n"
        "Candidate profile (source of truth):\n"
        f"{json.dumps(profile)}\n\n"
        "Previous reviewer feedback (may be empty): (none)\n"
    )


def test_stub_omits_date_range_for_projects() -> None:
    profile = {
        "full_name": "Jan Kowalski",
        "experiences": [
            {
                "company": "Acme Corp",
                "title": "Senior Backend Engineer",
                "bullets": ["Built APIs."],
            },
            {
                "company": "Projekt",
                "title": "Mid App",
                "start_date": "2021-06-01",
                "end_date": "2022-12-01",
                "bullets": ["Aplikacja pośrednia"],
            },
        ],
    }
    payload = json.loads(get_stub_llm().invoke(_tailor_prompt(profile)).content)
    by_title = {item["title"]: item for item in payload["experiences"]}
    assert "date_range" in by_title["Senior Backend Engineer"]
    assert "date_range" not in by_title["Mid App"]
    assert by_title["Mid App"]["company"] == "Projekt"


def test_stub_keeps_canned_experiences_without_profile() -> None:
    prompt = (
        "You are an expert resume writer tailoring an existing profile.\n"
        "Produce a TailoredCV JSON.\n"
        "Output language: en.\n"
    )
    payload = json.loads(get_stub_llm().invoke(prompt).content)
    assert payload["experiences"][0]["company"] == "Acme Corp"
    assert payload["experiences"][0]["date_range"] == "01/2021 - Present"
