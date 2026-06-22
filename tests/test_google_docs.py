from __future__ import annotations

import builtins

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


def test_require_google_raises_when_deps_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__

    def fake_import(name: str, *args: object, **kwargs: object):
        if name == "google.auth.transport.requests" or name.startswith("google."):
            raise ImportError("google extra not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(google_docs.GoogleDocsUnavailable, match="google"):
        google_docs._require_google()


def test_export_cv_to_drive_success(monkeypatch: pytest.MonkeyPatch, sample_tailored_cv) -> None:
    import cv_generator.config as cfg

    class _Settings:
        google_drive_template_id = "template-123"

    monkeypatch.setattr(google_docs, "get_settings", lambda: _Settings())
    cfg._settings = None  # type: ignore[attr-defined]

    class _ExecuteChain:
        def __init__(self, result: dict) -> None:
            self._result = result

        def execute(self) -> dict:
            return self._result

    class _FakeDocsAPI:
        def documents(self) -> _FakeDocsAPI:
            return self

        def batchUpdate(self, **kwargs: object) -> _ExecuteChain:
            return _ExecuteChain({})

    class _FakeDriveAPI:
        def files(self) -> _FakeDriveAPI:
            return self

        def copy(self, **kwargs: object) -> _ExecuteChain:
            return _ExecuteChain(
                {"id": "doc-456", "webViewLink": "https://docs.google.com/document/d/doc-456"}
            )

    monkeypatch.setattr(google_docs, "_services", lambda: (_FakeDocsAPI(), _FakeDriveAPI()))

    result = google_docs.export_cv_to_drive(sample_tailored_cv, document_name="Jan Kowalski CV")

    assert result["document_id"] == "doc-456"
    assert "docs.google.com" in result["web_view_link"]

