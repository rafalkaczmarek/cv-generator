"""Google Docs integration (Phase 2).

Requires the optional `google` extra:

    pip install -e .[google]

Workflow:
1. OAuth flow on first use, token cached at GOOGLE_TOKEN_PATH.
2. Copy template doc (GOOGLE_DRIVE_TEMPLATE_ID) into a new file via Drive API.
3. Replace `{{placeholders}}` via Docs API `documents.batchUpdate`.
4. Export the resulting doc as `.docx`.

The template is expected to contain placeholders matching `_flatten_for_docs`:
{{full_name}}, {{headline}}, {{summary}}, {{contact_line}}, {{skills}},
{{languages}}, {{certifications}}, {{education}}, {{experiences}}.

For loops/conditional logic stay with `docxtpl`; Google Docs flow is intended
for users who want a Drive-native template editing experience.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from cv_generator.config import get_settings
from cv_generator.models import TailoredCV

if TYPE_CHECKING:  # pragma: no cover - type-only imports
    from googleapiclient.discovery import Resource


_SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.file",
]

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class GoogleDocsUnavailable(RuntimeError):
    """Raised when optional Google dependencies are not installed."""


def _require_google():
    try:
        from google.auth.transport.requests import Request  # noqa: F401
        from google.oauth2.credentials import Credentials  # noqa: F401
        from google_auth_oauthlib.flow import InstalledAppFlow  # noqa: F401
        from googleapiclient.discovery import build  # noqa: F401
        from googleapiclient.http import MediaIoBaseDownload  # noqa: F401
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


def _services() -> tuple["Resource", "Resource"]:
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
        f"{exp.title} — {exp.company}\n{exp.date_range}\n" + "\n".join(f"• {b}" for b in exp.bullets)
        for exp in cv.experiences
    )
    education = "\n".join(f"• {line}" for line in cv.education_lines)
    certs = "\n".join(f"• {c}" for c in cv.certifications)

    return {
        "{{full_name}}": cv.full_name,
        "{{headline}}": cv.headline,
        "{{summary}}": cv.summary,
        "{{contact_line}}": contact_line,
        "{{skills}}": ", ".join(cv.skills),
        "{{languages}}": ", ".join(cv.languages),
        "{{certifications}}": certs,
        "{{education}}": education,
        "{{experiences}}": experiences,
    }


def export_cv_to_drive(cv: TailoredCV, *, document_name: str) -> dict[str, str]:
    """Copy template, fill placeholders, return the new doc IDs and links.

    Returns dict with keys: `document_id`, `web_view_link`.
    """
    settings = get_settings()
    template_id = settings.google_drive_template_id
    if not template_id:
        raise RuntimeError("GOOGLE_DRIVE_TEMPLATE_ID is not configured")

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
    "export_cv_to_drive",
    "download_as_docx",
]
