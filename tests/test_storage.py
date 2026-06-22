from __future__ import annotations

from cv_generator.services.storage import Storage


def test_storage_roundtrip_profile(sample_profile) -> None:
    storage = Storage()
    name = storage.save_profile(sample_profile)
    assert name in storage.list_profiles()

    loaded = storage.load_profile(name)
    assert loaded is not None
    assert loaded.full_name == sample_profile.full_name
    assert loaded.experiences[0].company == sample_profile.experiences[0].company


def test_storage_roundtrip_job(sample_job) -> None:
    storage = Storage()
    slug = storage.save_job_offer(sample_job)
    loaded = storage.load_job_offer(slug)
    assert loaded is not None
    assert loaded.title == sample_job.title


def test_storage_records_generated_cv(tmp_path, sample_tailored_cv) -> None:
    storage = Storage()
    file_path = tmp_path / "cv.docx"
    file_path.write_bytes(b"fake")

    cv_id = storage.record_generated_cv(
        profile_name="Jan Kowalski",
        job_slug="acme_engineer",
        file_path=file_path,
        cv=sample_tailored_cv,
    )
    assert cv_id > 0

    rows = storage.list_generated_cvs()
    assert rows and rows[0]["profile_name"] == "Jan Kowalski"
