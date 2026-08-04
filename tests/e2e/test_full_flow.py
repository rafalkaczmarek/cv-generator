"""End-to-end flows exercising backend services through the Streamlit UI."""

from __future__ import annotations

from pathlib import Path

import pytest
from docx import Document
from playwright.sync_api import Page, expect

from tests.e2e.helpers import (
    E2E_PROFILE,
    analyze_pasted_job_offer,
    export_docx,
    goto_app,
    open_tab,
    reload_saved_profile,
    run_full_generation_flow,
    run_generation_pipeline,
    save_profile_to_storage,
    set_profile_in_session,
)

pytestmark = pytest.mark.e2e


def test_generate_tab_shows_prerequisites(page: Page, streamlit_url: str) -> None:
    goto_app(page, streamlit_url)
    open_tab(page, "Generuj")
    expect(page.get_by_text("Najpierw uzupełnij i zapisz profil")).to_be_visible()


def test_profile_save_and_reload(page: Page, streamlit_url: str, e2e_workspace: Path) -> None:
    goto_app(page, streamlit_url)
    save_profile_to_storage(page)

    db_path = e2e_workspace / "data" / "cv_generator.sqlite"
    assert db_path.exists()

    page.reload(wait_until="domcontentloaded")
    expect(page.get_by_role("heading", name="CV Generator")).to_be_visible(timeout=30_000)
    reload_saved_profile(page, E2E_PROFILE["full_name"])
    profile = page.get_by_role("tabpanel", name="Profil")
    expect(profile.get_by_label("Kursy (oddzielone przecinkami)")).to_have_value(
        E2E_PROFILE["courses"]
    )


def test_job_analysis_from_pasted_text(page: Page, streamlit_url: str) -> None:
    goto_app(page, streamlit_url)
    set_profile_in_session(page)
    analyze_pasted_job_offer(page)


def test_full_cv_generation_and_export(
    page: Page, streamlit_url: str, e2e_workspace: Path
) -> None:
    goto_app(page, streamlit_url)
    set_profile_in_session(page)
    analyze_pasted_job_offer(page)
    run_generation_pipeline(page)

    open_tab(page, "Podgląd")
    expect(page.get_by_role("heading", name="Podgląd i edycja CV")).to_be_visible()
    preview = page.get_by_role("tabpanel", name="Podgląd")
    expect(preview.get_by_label("Headline")).to_have_value("Senior Python Engineer")
    expect(preview.get_by_label("Kursy (po przecinku)")).to_have_value(
        "AWS Certified Developer"
    )

    export_docx(page)

    output_dir = e2e_workspace / "output"
    docx_files = list(output_dir.glob("*.docx"))
    assert docx_files, "Expected at least one generated DOCX in output dir"
    assert docx_files[0].stat().st_size > 0
    doc_text = "\n".join(p.text for p in Document(docx_files[0]).paragraphs)
    assert "KURSY" in doc_text or "Kursy" in doc_text
    assert "AWS Certified Developer" in doc_text

    export_panel = page.get_by_role("tabpanel", name="Eksport")
    expect(export_panel.get_by_text("Historia wygenerowanych CV")).to_be_visible()
    expect(export_panel.get_by_text("score 100").first).to_be_visible()


def test_export_with_selected_template(
    page: Page, streamlit_url: str, e2e_workspace: Path
) -> None:
    goto_app(page, streamlit_url)
    run_full_generation_flow(page)

    output_dir = e2e_workspace / "output"
    before_mtime = {p.name: p.stat().st_mtime for p in output_dir.glob("*.docx")}
    export_docx(page, template_option="Kompaktowy")

    after = list(output_dir.glob("*.docx"))
    assert after, "Expected DOCX in output dir after export"
    updated = [
        p
        for p in after
        if p.name not in before_mtime or p.stat().st_mtime > before_mtime[p.name]
    ]
    assert updated, "Expected an updated DOCX after exporting with the compact template"
    assert updated[0].stat().st_size > 0
