"""Shared fixtures and a tmpdir-isolated Settings override."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from cv_generator.graph.state import GapAnalysis
from cv_generator.models import (
    Education,
    Experience,
    JobOffer,
    Profile,
    TailoredCV,
    TailoredExperience,
)


@pytest.fixture(autouse=True)
def _isolate_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Redirect all data/output/templates dirs to a per-test tmpdir.

    Sets ``CV_GENERATOR_IGNORE_ENV_FILE=1`` so :func:`get_settings` doesn't
    reload the project's ``.env`` (which would clobber the paths below via
    ``load_dotenv(override=True)`` and break DB isolation between tests).
    """
    from cv_generator.logging_setup import reset_logging

    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("APP_OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("APP_TEMPLATES_DIR", str(tmp_path / "templates"))
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CV_GENERATOR_IGNORE_ENV_FILE", "1")
    reset_logging()
    yield
    reset_logging()


@pytest.fixture
def sample_profile() -> Profile:
    return Profile(
        full_name="Jan Kowalski",
        headline="Senior Python Developer",
        summary="10 lat doświadczenia w budowaniu systemów backendowych.",
        email="jan@example.com",
        phone="+48 600 000 000",
        location="Warszawa",
        skills=["Python", "FastAPI", "PostgreSQL", "Docker", "AWS"],
        courses=["AWS Certified Developer", "Kubernetes Fundamentals"],
        languages=["Polski - natywny", "Angielski - C1"],
        experiences=[
            Experience(
                company="Acme Corp",
                title="Senior Backend Engineer",
                location="Warszawa",
                start_date=date(2021, 1, 1),
                is_current=True,
                summary="Praca nad platformą e-commerce.",
                bullets=[
                    "Zaprojektowałem API w FastAPI obsługujące 10k req/s.",
                    "Wdrożyłem migrację do Kubernetes.",
                ],
                technologies=["Python", "FastAPI", "Kubernetes", "PostgreSQL"],
            ),
            Experience(
                company="Beta Sp. z o.o.",
                title="Backend Developer",
                location="Kraków",
                start_date=date(2018, 6, 1),
                end_date=date(2020, 12, 31),
                bullets=["Tworzyłem mikroserwisy w Django."],
                technologies=["Python", "Django", "AWS"],
            ),
        ],
        education=[
            Education(
                institution="Politechnika Warszawska",
                degree="mgr inż.",
                field_of_study="Informatyka",
                start_date=date(2013, 10, 1),
                end_date=date(2018, 6, 30),
            )
        ],
    )


@pytest.fixture
def sample_job() -> JobOffer:
    return JobOffer(
        url="https://example.com/job/123",
        title="Senior Python Engineer",
        company="GammaTech",
        location="Remote",
        raw_text="We need a Python engineer with FastAPI and Kubernetes experience.",
        requirements=["Python", "FastAPI", "Kubernetes", "PostgreSQL"],
        nice_to_have=["AWS", "Terraform"],
        responsibilities=["Design backend services"],
        keywords=["Python", "FastAPI", "Kubernetes", "PostgreSQL", "Terraform"],
    )


@pytest.fixture
def sample_gap() -> GapAnalysis:
    return GapAnalysis(
        matched_skills=["Python", "FastAPI", "Kubernetes"],
        missing_skills=["Terraform"],
        relevant_experiences=[0],
        emphasis_notes=["Emphasize matched skills first: Python, FastAPI."],
    )


@pytest.fixture
def sample_tailored_cv() -> TailoredCV:
    return TailoredCV(
        full_name="Jan Kowalski",
        headline="Senior Python Engineer specialising in FastAPI and Kubernetes",
        summary="Backend engineer with deep FastAPI and Kubernetes experience.",
        email="jan@example.com",
        skills=["Python", "FastAPI", "Kubernetes", "PostgreSQL"],
        courses=["Kubernetes Fundamentals"],
        experiences=[
            TailoredExperience(
                company="Acme Corp",
                title="Senior Backend Engineer",
                date_range="01/2021 - obecnie",
                bullets=[
                    "Built FastAPI services serving 10k req/s on Kubernetes.",
                    "Owned PostgreSQL schema design and migrations.",
                ],
            )
        ],
    )
