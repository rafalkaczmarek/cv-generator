"""Google Docs integration (Phase 2).

Requires the optional `google` extra:

    pip install -e .[google]

Primary workflow (upload generated DOCX):
1. OAuth flow on first use, token cached at GOOGLE_TOKEN_PATH.
2. Upload a local ``.docx`` via Drive API and convert it to a Google Doc.

Optional template workflow (GOOGLE_DRIVE_TEMPLATE_ID):
1. Copy template doc into a new file via Drive API.
2. Replace ``{{placeholders}}`` via Docs API ``documents.batchUpdate``.

Template placeholders match ``_flatten_for_docs``:
{{full_name}}, {{headline}}, {{summary}}, {{contact_line}}, {{skills}},
{{courses}}, {{languages}}, {{education}}, {{experiences}}.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from cv_generator.config import get_settings
from cv_generator.models import TailoredCV

_STUB_DOC_ID = "stub-doc-id"
_STUB_WEB_VIEW_LINK = f"https://docs.google.com/document/d/{_STUB_DOC_ID}"


def _stub_enabled() -> bool:
    """E2E / local harness: skip real Google APIs when ``GOOGLE_DOCS_STUB=1``."""
    return os.environ.get("GOOGLE_DOCS_STUB", "").strip() == "1"


def _stub_result(*, document_name: str) -> dict[str, str]:
    _ = document_name  # kept for call-site symmetry / future stub logging
    return {"document_id": _STUB_DOC_ID, "web_view_link": _STUB_WEB_VIEW_LINK}

if TYPE_CHECKING:  # pragma: no cover - type-only imports
    from googleapiclient.discovery import Resource


_SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.file",
]

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_GOOGLE_DOC_MIME = "application/vnd.google-apps.document"


class GoogleDocsUnavailable(RuntimeError):
    """Raised when optional Google dependencies are not installed."""


def _require_google():
    try:
        from google.auth.transport.requests import Request  # noqa: F401
        from google.oauth2.credentials import Credentials  # noqa: F401
        from google_auth_oauthlib.flow import InstalledAppFlow  # noqa: F401
        from googleapiclient.discovery import build  # noqa: F401
        from googleapiclient.http import (
            MediaFileUpload,  # noqa: F401
            MediaIoBaseDownload,  # noqa: F401
        )
    except ImportError as exc:  # pragma: no cover - depends on optional extras
        raise GoogleDocsUnavailable(
            "Google Docs integration requires the 'google' extra. "
            "Install with: pip install -e .[google]"
        ) from exc


def _load_credentials():
    _require_google()
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    settings = get_settings()
    token_path: Path = settings.google_token_path
    creds_path: Path = settings.google_credentials_path

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), _SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not creds_path.exists():
                raise FileNotFoundError(
                    f"Missing Google OAuth credentials at {creds_path}. "
                    "Download client secret JSON from Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), _SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds


def _services() -> tuple[Resource, Resource]:
    _require_google()
    from googleapiclient.discovery import build

    creds = _load_credentials()
    docs = build("docs", "v1", credentials=creds, cache_discovery=False)
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)
    return docs, drive


def _flatten_for_docs(cv: TailoredCV) -> dict[str, str]:
    """Render lists as ready-to-paste multi-line strings for Docs placeholders."""
    contact_parts = [cv.email, cv.phone, cv.location, cv.linkedin_url, cv.github_url]
    contact_line = " | ".join(p for p in contact_parts if p)

    experiences = "\n\n".join(
        f"{exp.heading}\n{exp.date_range}\n" + "\n".join(f"• {b}" for b in exp.bullets)
        for exp in cv.experiences
    )
    education = "\n".join(f"• {line}" for line in cv.education_lines)

    return {
        "{{full_name}}": cv.full_name,
        "{{headline}}": cv.headline,
        "{{summary}}": cv.summary,
        "{{contact_line}}": contact_line,
        "{{skills}}": ", ".join(cv.skills),
        "{{courses}}": ", ".join(cv.courses),
        "{{languages}}": ", ".join(cv.languages),
        "{{education}}": education,
        "{{experiences}}": experiences,
    }


def upload_docx_to_drive(docx_path: Path, *, document_name: str) -> dict[str, str]:
    """Upload a local ``.docx`` and convert it to a Google Doc.

    Returns dict with keys: ``document_id``, ``web_view_link``.
    """
    path = Path(docx_path)
    if not path.is_file():
        raise FileNotFoundError(f"DOCX not found: {path}")

    if _stub_enabled():
        return _stub_result(document_name=document_name)

    _require_google()
    from googleapiclient.http import MediaFileUpload

    _, drive = _services()
    metadata = {"name": document_name, "mimeType": _GOOGLE_DOC_MIME}
    media = MediaFileUpload(str(path), mimetype=_DOCX_MIME, resumable=True)
    created = (
        drive.files()
        .create(body=metadata, media_body=media, fields="id, webViewLink")
        .execute()
    )
    return {
        "document_id": str(created["id"]),
        "web_view_link": str(created.get("webViewLink", "")),
    }


def export_cv_to_drive(cv: TailoredCV, *, document_name: str) -> dict[str, str]:
    """Copy template, fill placeholders, return the new doc IDs and links.

    Returns dict with keys: `document_id`, `web_view_link`.
    """
    settings = get_settings()
    template_id = settings.google_drive_template_id
    if not template_id:
        raise RuntimeError("GOOGLE_DRIVE_TEMPLATE_ID is not configured")

    if _stub_enabled():
        return _stub_result(document_name=document_name)

    docs, drive = _services()

    copy = drive.files().copy(
        fileId=template_id,
        body={"name": document_name},
        fields="id, webViewLink",
    ).execute()
    new_id: str = copy["id"]

    replacements = _flatten_for_docs(cv)
    requests = [
        {
            "replaceAllText": {
                "containsText": {"text": placeholder, "matchCase": True},
                "replaceText": value,
            }
        }
        for placeholder, value in replacements.items()
    ]
    docs.documents().batchUpdate(documentId=new_id, body={"requests": requests}).execute()

    return {"document_id": new_id, "web_view_link": copy.get("webViewLink", "")}


def download_as_docx(document_id: str, target_path: Path) -> Path:
    """Export a Google Doc as a .docx file written to `target_path`."""
    _require_google()
    import io

    from googleapiclient.http import MediaIoBaseDownload

    _, drive = _services()
    request = drive.files().export_media(fileId=document_id, mimeType=_DOCX_MIME)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(buffer.getvalue())
    return target_path


__all__ = [
    "GoogleDocsUnavailable",
    "upload_docx_to_drive",
    "export_cv_to_drive",
    "download_as_docx",
]
