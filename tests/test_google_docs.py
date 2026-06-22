from __future__ import annotations

import pytest

from cv_generator.services import google_docs


def test_flatten_for_docs_contains_required_placeholders(sample_tailored_cv) -> None:
    flat = google_docs._flatten_for_docs(sample_tailored_cv)
    assert flat["{{full_name}}"] == sample_tailored_cv.full_name
    assert sample_tailored_cv.headline in flat["{{headline}}"]
    assert "Acme Corp" in flat["{{experiences}}"]


def test_export_requires_template_id(monkeypatch: pytest.MonkeyPatch, sample_tailored_cv) -> None:
    monkeypatch.delenv("GOOGLE_DRIVE_TEMPLATE_ID", raising=False)
    import cv_generator.config as cfg

    cfg._settings = None  # type: ignore[attr-defined]
    with pytest.raises(RuntimeError, match="GOOGLE_DRIVE_TEMPLATE_ID"):
        google_docs.export_cv_to_drive(sample_tailored_cv, document_name="x")
