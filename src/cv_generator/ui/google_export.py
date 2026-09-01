"""Shared Streamlit controls for sending a generated CV to Google Docs."""

from __future__ import annotations

import logging
from pathlib import Path

import streamlit as st

from cv_generator.config import get_settings

logger = logging.getLogger(__name__)


def document_name_for_cv(*, full_name: str, company: str | None = None) -> str:
    if company:
        return f"CV — {full_name} — {company}"
    return f"CV — {full_name}"


def render_send_to_google_docs_button(
    *,
    docx_path: Path,
    document_name: str,
    key: str,
) -> None:
    """Render a button that uploads ``docx_path`` to Drive as a Google Doc."""
    settings = get_settings()
    help_text = (
        "Wymaga `pip install -e .[google]` oraz pliku OAuth "
        f"w `{settings.google_credentials_path}`."
    )
    if st.button("Wyślij do Google Docs", key=key, help=help_text):
        try:
            from cv_generator.services.google_docs import (
                GoogleDocsUnavailable,
                upload_docx_to_drive,
            )

            with st.spinner("Wysyłam CV do Google Docs..."):
                result = upload_docx_to_drive(docx_path, document_name=document_name)
            link = result.get("web_view_link") or ""
            st.success("Utworzono dokument w Google Docs.")
            if link:
                st.markdown(f"[Otwórz w Google Docs]({link})")
        except GoogleDocsUnavailable as exc:
            logger.warning("Google Docs extra unavailable: %s", exc)
            st.error(str(exc))
        except FileNotFoundError as exc:
            logger.warning("Google Docs upload missing file: %s", exc)
            st.error(str(exc))
        except Exception as exc:  # pragma: no cover - OAuth / API errors
            logger.exception("Google Docs upload failed")
            if "invalid_grant" in str(exc).lower():
                st.error(
                    "Token Google wygasł lub został odwołany. Usuń "
                    f"`{settings.google_token_path}` i kliknij ponownie — "
                    "otworzy się logowanie Google."
                )
            else:
                st.error(f"Nie udało się wysłać do Google Docs: {exc}")
