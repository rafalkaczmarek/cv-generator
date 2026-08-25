"""Playwright E2E coverage for Google Docs send flow (stubbed via GOOGLE_DOCS_STUB)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from cv_generator.models import BoardOffer, BoardSource, TailoredCV
from cv_generator.services.docx_generator import ensure_builtin_templates, render_cv
from cv_generator.services.storage import Storage
from tests.e2e.helpers import (
    E2E_PROFILE,
    export_docx,
    goto_app,
    open_tab,
    run_full_generation_flow,
    send_to_google_docs,
    set_profile_in_session,
)

pytestmark = pytest.mark.e2e


def _db_path(e2e_workspace: Path) -> Path:
    return e2e_workspace / "data" / "cv_generator.sqlite"


@pytest.fixture
def clean_boards(e2e_workspace: Path):
    storage = Storage(db_path=_db_path(e2e_workspace))
    with storage._connect() as conn:
        conn.execute("DELETE FROM board_offers")
        conn.execute("DELETE FROM offer_matches")
        conn.execute("DELETE FROM generated_cvs")
    yield storage
    with storage._connect() as conn:
        conn.execute("DELETE FROM board_offers")
        conn.execute("DELETE FROM offer_matches")
        conn.execute("DELETE FROM generated_cvs")


def test_export_tab_shows_google_docs_setup_expanders(page: Page, streamlit_url: str) -> None:
    goto_app(page, streamlit_url)
    open_tab(page, "Eksport")
    export = page.get_by_role("tabpanel", name="Eksport")
    expect(export.get_by_text("Google Docs — konfiguracja")).to_be_visible()
    expect(export.get_by_text("Google Docs — szablon Drive (opcjonalne)")).to_be_visible()

    summary = export.locator("summary").filter(has_text="Google Docs — szablon Drive")
    details = summary.locator("xpath=ancestor::details[1]")
    if details.get_attribute("open") is None:
        summary.click()
    expect(details).to_have_js_property("open", True, timeout=5_000)
    expect(export.get_by_text("GOOGLE_DRIVE_TEMPLATE_ID", exact=False)).to_be_visible()


def test_export_send_to_google_docs_after_docx_save(page: Page, streamlit_url: str) -> None:
    goto_app(page, streamlit_url)
    run_full_generation_flow(page)
    export_docx(page)

    export = page.get_by_role("tabpanel", name="Eksport")
    expect(export.get_by_role("button", name="Pobierz plik (English)")).to_be_visible()
    expect(export.get_by_role("button", name="Wyślij do Google Docs")).to_be_visible()

    send_to_google_docs(page, scope=export)


def test_offers_send_to_google_docs_for_existing_cv(
    page: Page,
    streamlit_url: str,
    e2e_workspace: Path,
    clean_boards: Storage,
) -> None:
    offer = BoardOffer(
        source=BoardSource.JUSTJOIN,
        external_id="gdocs-existing",
        url="https://example.com/justjoin/gdocs-existing",
        title="Senior Python Engineer",
        company="GammaTech",
        skills=["Python", "FastAPI", "PostgreSQL", "Docker"],
        published_at=datetime.now(),
        is_active=True,
    )
    clean_boards.upsert_board_offers([offer])

    templates_dir = e2e_workspace / "templates"
    ensure_builtin_templates(templates_dir)
    output_dir = e2e_workspace / "output"
    output_dir.mkdir(exist_ok=True)

    cv = TailoredCV(
        full_name=E2E_PROFILE["full_name"],
        headline="Senior Python Engineer",
        summary="Preseeded CV for Google Docs E2E.",
        experiences=[],
        skills=["Python", "FastAPI"],
        courses=["AWS Certified Developer"],
        languages=[],
        education_lines=[],
        match_score=88,
        language="en",
    )
    filename = f"cv_{offer.offer_key.replace(':', '_')}.docx"
    cv_path = render_cv(
        cv,
        template_path=templates_dir / "cv_template.docx",
        filename=filename,
        output_dir=output_dir,
    )
    clean_boards.record_generated_cv(
        profile_name=E2E_PROFILE["full_name"],
        job_slug="e2e-gdocs",
        file_path=cv_path,
        cv=cv,
        offer_key=offer.offer_key,
    )

    goto_app(page, streamlit_url)
    set_profile_in_session(page)
    open_tab(page, "Oferty")
    offers = page.get_by_role("tabpanel", name="Oferty")

    expect(offers.get_by_role("heading", name="Senior Python Engineer")).to_be_visible(
        timeout=15_000
    )
    expect(offers.get_by_role("button", name="Pobierz CV")).to_be_visible()
    expect(offers.get_by_role("button", name="Wyślij do Google Docs")).to_be_visible()

    send_to_google_docs(page, scope=offers)
