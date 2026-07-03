"""In-process backend checks for paths exercised by Playwright E2E flows.

Streamlit runs in a separate OS process, so pytest-cov cannot attribute UI-driven
execution to the test runner. These tests mirror the Playwright happy paths inside
pytest and keep ``cv-generator-e2e-cov`` meaningful.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cv_generator.agents.job_analyzer import analyze_job
from cv_generator.agents.validator import validate
from cv_generator.graph import pipeline
from cv_generator.graph.pipeline import generate_cv
from cv_generator.models import Profile, TailoredCV
from cv_generator.services.docx_generator import render_cv
from cv_generator.services.linkedin_import import (
    LinkedInImportError,
    profile_from_linkedin_csv,
    profile_from_linkedin_zip,
)
from cv_generator.services.storage import Storage

from tests.e2e.fixtures_data import POSITIONS_CSV, PROFILE_CSV, build_linkedin_zip

pytestmark = pytest.mark.e2e


@pytest.fixture
def e2e_profile() -> Profile:
    return Profile.model_validate(
        {
            "full_name": "Jan Kowalski",
            "headline": "Senior Python Developer",
            "email": "jan@example.com",
            "skills": ["Python", "FastAPI", "PostgreSQL", "Docker"],
            "experiences": [
                {
                    "company": "Acme Corp",
                    "title": "Senior Backend Engineer",
                    "start_date": "2021-01-01",
                    "is_current": True,
                    "bullets": ["Built FastAPI services on Kubernetes."],
                    "technologies": ["Python", "FastAPI", "Kubernetes"],
                }
            ],
        }
    )


def test_stub_llm_job_analysis_and_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    e2e_profile: Profile,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("APP_OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("APP_TEMPLATES_DIR", str(tmp_path / "templates"))
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    monkeypatch.setenv("CV_GENERATOR_IGNORE_ENV_FILE", "1")

    offer = analyze_job(
        url=None,
        raw_text="GammaTech hiring Senior Python Engineer with FastAPI and PostgreSQL.",
    )
    assert offer.title == "Senior Python Engineer"
    assert offer.company == "GammaTech"

    cv = generate_cv(e2e_profile, offer)
    assert cv.headline == "Senior Python Engineer"
    assert cv.match_score >= 70
    assert any(exp.company == "Acme Corp" for exp in cv.experiences)


def test_analyze_job_requires_input(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    monkeypatch.setenv("CV_GENERATOR_IGNORE_ENV_FILE", "1")

    with pytest.raises(ValueError, match="Either url or raw_text"):
        analyze_job(url=None, raw_text=None)


def test_analyze_job_can_use_fetched_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    monkeypatch.setenv("CV_GENERATOR_IGNORE_ENV_FILE", "1")
    monkeypatch.setattr(
        "cv_generator.agents.job_analyzer.fetch_job_text",
        lambda _url: "GammaTech hiring Senior Python Engineer.",
    )

    offer = analyze_job(url="https://example.com/jobs/1", raw_text=None)
    assert offer.title == "Senior Python Engineer"
    assert "GammaTech" in (offer.company or "")


def test_stub_llm_export_roundtrip(
    monkeypatch: pytest.MonkeyPatch,
    e2e_profile: Profile,
    tmp_path: Path,
) -> None:
    templates = tmp_path / "templates"
    templates.mkdir()
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("APP_OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("APP_TEMPLATES_DIR", str(templates))
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    monkeypatch.setenv("CV_GENERATOR_IGNORE_ENV_FILE", "1")

    offer = analyze_job(url=None, raw_text="Senior Python Engineer at GammaTech.")
    cv = generate_cv(e2e_profile, offer)

    storage = Storage()
    storage.save_profile(e2e_profile)
    storage.save_job_offer(offer)

    path = render_cv(cv, filename="cv_e2e.docx")
    assert path.exists()
    assert path.stat().st_size > 0

    record_id = storage.record_generated_cv(
        profile_name=e2e_profile.full_name,
        job_slug=offer.slug(),
        file_path=path,
        cv=cv,
    )
    assert record_id > 0
    rows = storage.list_generated_cvs()
    assert rows and rows[0]["profile_name"] == e2e_profile.full_name


def test_linkedin_csv_and_zip_import(tmp_path: Path) -> None:
    profile = profile_from_linkedin_csv("Profile.csv", PROFILE_CSV.read_bytes())
    assert profile.full_name == "Jan Kowalski"
    assert profile.headline == "Senior Python Developer"

    positions = profile_from_linkedin_csv("Positions.csv", POSITIONS_CSV.read_bytes())
    assert len(positions.experiences) == 2
    assert positions.experiences[0].company == "Acme Corp"

    zip_path = build_linkedin_zip(tmp_path / "export.zip")
    merged = profile_from_linkedin_zip(zip_path)
    assert merged.full_name == "Jan Kowalski"
    assert len(merged.experiences) == 2
    assert "Python" in merged.skills


def test_linkedin_import_rejects_unknown_csv() -> None:
    with pytest.raises(LinkedInImportError, match="Nierozpoznany plik CSV"):
        profile_from_linkedin_csv("Connections.csv", b"a,b\n1,2\n")


def test_storage_delete_and_job_roundtrip(
    monkeypatch: pytest.MonkeyPatch,
    e2e_profile: Profile,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    monkeypatch.setenv("CV_GENERATOR_IGNORE_ENV_FILE", "1")

    storage = Storage()
    name = storage.save_profile(e2e_profile)
    assert name in storage.list_profiles()

    offer = analyze_job(url=None, raw_text="Senior Python Engineer at GammaTech.")
    slug = storage.save_job_offer(offer)
    loaded_offer = storage.load_job_offer(slug)
    assert loaded_offer is not None
    assert loaded_offer.company == "GammaTech"

    storage.delete_profile(name)
    assert name not in storage.list_profiles()
    assert storage.load_profile(name) is None


def test_pipeline_retries_when_validator_score_is_low(
    monkeypatch: pytest.MonkeyPatch,
    e2e_profile: Profile,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    monkeypatch.setenv("CV_GENERATOR_IGNORE_ENV_FILE", "1")

    offer = analyze_job(url=None, raw_text="Senior Python Engineer at GammaTech.")
    tailor_calls = 0
    original_tailor = pipeline.tailor_cv

    def counting_tailor(**kwargs) -> TailoredCV:
        nonlocal tailor_calls
        tailor_calls += 1
        return original_tailor(**kwargs)

    monkeypatch.setattr(pipeline, "tailor_cv", counting_tailor)

    def fake_validate(**kwargs) -> tuple[int, str, TailoredCV]:
        cv = kwargs["cv"].model_copy(update={"match_score": 40})
        return 40, "Needs work.", cv

    monkeypatch.setattr(pipeline, "validate", fake_validate)

    cv = generate_cv(e2e_profile, offer)
    assert cv.match_score == 40
    assert tailor_calls == 2

    score, feedback, checked = validate(profile=e2e_profile, job=offer, cv=cv)
    assert score >= 60
    assert checked.match_score >= 60
