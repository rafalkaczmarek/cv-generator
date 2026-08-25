from __future__ import annotations

import builtins
import sys
import types
from pathlib import Path

import pytest

from cv_generator.services import google_docs


def test_flatten_for_docs_contains_required_placeholders(sample_tailored_cv) -> None:
    flat = google_docs._flatten_for_docs(sample_tailored_cv)
    assert flat["{{full_name}}"] == sample_tailored_cv.full_name
    assert sample_tailored_cv.headline in flat["{{headline}}"]
    assert "Acme Corp" in flat["{{experiences}}"]
    assert flat["{{courses}}"] == ", ".join(sample_tailored_cv.courses)


def test_flatten_for_docs_omits_projekt_company_suffix(sample_tailored_cv) -> None:
    from cv_generator.models import TailoredExperience

    cv = sample_tailored_cv.model_copy(
        update={
            "experiences": [
                TailoredExperience(
                    company="Projekt",
                    title="Pekao website",
                    date_range="01/2020 - 06/2020",
                    bullets=["Built a marketing site."],
                )
            ]
        }
    )
    flat = google_docs._flatten_for_docs(cv)
    assert "Pekao website\n" in flat["{{experiences}}"]
    assert "— Projekt" not in flat["{{experiences}}"]


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


def test_upload_docx_to_drive_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    docx = tmp_path / "cv.docx"
    docx.write_bytes(b"PK fake-docx")

    class _FakeMedia:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

    http_mod = types.ModuleType("googleapiclient.http")
    http_mod.MediaFileUpload = _FakeMedia  # type: ignore[attr-defined]
    parent = types.ModuleType("googleapiclient")
    monkeypatch.setitem(sys.modules, "googleapiclient", parent)
    monkeypatch.setitem(sys.modules, "googleapiclient.http", http_mod)
    monkeypatch.setattr(google_docs, "_require_google", lambda: None)

    class _ExecuteChain:
        def __init__(self, result: dict) -> None:
            self._result = result

        def execute(self) -> dict:
            return self._result

    class _FakeDriveAPI:
        def __init__(self) -> None:
            self.last_create: dict[str, object] | None = None

        def files(self) -> _FakeDriveAPI:
            return self

        def create(self, **kwargs: object) -> _ExecuteChain:
            self.last_create = kwargs
            return _ExecuteChain(
                {
                    "id": "doc-789",
                    "webViewLink": "https://docs.google.com/document/d/doc-789",
                }
            )

    fake_drive = _FakeDriveAPI()
    monkeypatch.setattr(google_docs, "_services", lambda: (None, fake_drive))

    result = google_docs.upload_docx_to_drive(docx, document_name="CV — Jan")

    assert result["document_id"] == "doc-789"
    assert "docs.google.com" in result["web_view_link"]
    assert fake_drive.last_create is not None
    body = fake_drive.last_create["body"]
    assert isinstance(body, dict)
    assert body["mimeType"] == "application/vnd.google-apps.document"
    assert body["name"] == "CV — Jan"


def test_upload_docx_to_drive_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.docx"
    with pytest.raises(FileNotFoundError, match="DOCX not found"):
        google_docs.upload_docx_to_drive(missing, document_name="x")


def test_upload_docx_to_drive_stub(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    docx = tmp_path / "cv.docx"
    docx.write_bytes(b"PK fake-docx")
    monkeypatch.setenv("GOOGLE_DOCS_STUB", "1")

    result = google_docs.upload_docx_to_drive(docx, document_name="CV — Jan")

    assert result["document_id"] == "stub-doc-id"
    assert result["web_view_link"].endswith("/stub-doc-id")


def test_export_cv_to_drive_stub(
    monkeypatch: pytest.MonkeyPatch, sample_tailored_cv
) -> None:
    class _Settings:
        google_drive_template_id = "template-123"

    monkeypatch.setenv("GOOGLE_DOCS_STUB", "1")
    monkeypatch.setattr(google_docs, "get_settings", lambda: _Settings())

    result = google_docs.export_cv_to_drive(
        sample_tailored_cv, document_name="CV — Jan Kowalski"
    )

    assert result["document_id"] == "stub-doc-id"
    assert "docs.google.com" in result["web_view_link"]


def test_document_name_for_cv() -> None:
    from cv_generator.ui.google_export import document_name_for_cv

    assert document_name_for_cv(full_name="Jan Kowalski") == "CV — Jan Kowalski"
    assert (
        document_name_for_cv(full_name="Jan Kowalski", company="Acme")
        == "CV — Jan Kowalski — Acme"
    )


def test_load_credentials_reauths_when_refresh_token_revoked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    token_path = tmp_path / "google_token.json"
    creds_path = tmp_path / "google_credentials.json"
    token_path.write_text('{"refresh_token": "stale"}', encoding="utf-8")
    creds_path.write_text("{}", encoding="utf-8")

    class _Settings:
        google_token_path = token_path
        google_credentials_path = creds_path

    class RefreshError(Exception):
        pass

    class Request:
        pass

    class _ExpiredCreds:
        valid = False
        expired = True
        refresh_token = "stale"

        def refresh(self, _request: object) -> None:
            raise RefreshError(
                "invalid_grant: Token has been expired or revoked.",
                {"error": "invalid_grant"},
            )

    class _FreshCreds:
        valid = True

        def to_json(self) -> str:
            return '{"access_token": "new"}'

    class Credentials:
        @staticmethod
        def from_authorized_user_file(path: str, scopes: object) -> _ExpiredCreds:
            assert Path(path) == token_path
            return _ExpiredCreds()

    class _Flow:
        def run_local_server(self, *, port: int = 0) -> _FreshCreds:
            _ = port
            return _FreshCreds()

    class InstalledAppFlow:
        @staticmethod
        def from_client_secrets_file(path: str, scopes: object) -> _Flow:
            assert Path(path) == creds_path
            return _Flow()

    monkeypatch.setattr(google_docs, "get_settings", lambda: _Settings())
    monkeypatch.setattr(google_docs, "_require_google", lambda: None)
    monkeypatch.setattr(
        google_docs,
        "_google_auth_imports",
        lambda: (RefreshError, Request, Credentials, InstalledAppFlow),
    )

    creds = google_docs._load_credentials()

    assert isinstance(creds, _FreshCreds)
    assert token_path.read_text(encoding="utf-8") == '{"access_token": "new"}'
