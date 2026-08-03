"""Additional Playwright E2E scenarios: validation, imports and empty states."""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.fixtures_data import (
    POSITIONS_CSV,
    PROFILE_CSV,
    PROJECTS_CSV,
    build_linkedin_zip,
)
from tests.e2e.helpers import (
    E2E_PROFILE,
    analyze_pasted_job_offer,
    apply_import_conflict_choice,
    export_docx,
    fill_partial_profile,
    goto_app,
    import_linkedin_file,
    open_tab,
    run_full_generation_flow,
    run_generation_pipeline,
    set_profile_in_session,
)

pytestmark = pytest.mark.e2e


def test_job_analysis_requires_input(page: Page, streamlit_url: str) -> None:
    goto_app(page, streamlit_url)
    open_tab(page, "Oferta")
    page.get_by_role("button", name="Analizuj ofertę").click()
    expect(page.get_by_text("Podaj URL lub wklej treść oferty.")).to_be_visible()


def test_generate_tab_requires_job_offer(page: Page, streamlit_url: str) -> None:
    goto_app(page, streamlit_url)
    set_profile_in_session(page)
    open_tab(page, "Generuj")
    expect(page.get_by_text("Najpierw przeanalizuj ofertę w zakładce 'Oferta'.")).to_be_visible()


def test_preview_tab_requires_generated_cv(page: Page, streamlit_url: str) -> None:
    goto_app(page, streamlit_url)
    open_tab(page, "Podgląd")
    expect(page.get_by_text("Najpierw uruchom generowanie w zakładce 'Generuj'.")).to_be_visible()


def test_export_tab_shows_empty_history(page: Page, streamlit_url: str) -> None:
    goto_app(page, streamlit_url)
    open_tab(page, "Eksport")
    expect(page.get_by_text("Brak wpisów.")).to_be_visible()


def test_profile_invalid_email_shows_error(page: Page, streamlit_url: str) -> None:
    goto_app(page, streamlit_url)
    open_tab(page, "Profil")
    page.get_by_label("Imię i nazwisko").fill(E2E_PROFILE["full_name"])
    page.get_by_label("Email").fill("not-an-email")
    page.get_by_role("button", name="Zapisz profil w bazie lokalnej").click()
    expect(page.get_by_text("Profil ma błędy:")).to_be_visible(timeout=15_000)


def test_linkedin_csv_import_fills_profile(page: Page, streamlit_url: str) -> None:
    goto_app(page, streamlit_url)
    import_linkedin_file(page, PROFILE_CSV)
    expect(page.get_by_label("Imię i nazwisko")).to_have_value("Jan Kowalski", timeout=15_000)
    expect(page.get_by_label("Headline")).to_have_value("Senior Python Developer")
    expect(page.get_by_label("Krótkie podsumowanie")).to_have_value("Backend od 10 lat")


def test_linkedin_zip_import_fills_experiences(
    page: Page, streamlit_url: str, tmp_path: Path
) -> None:
    goto_app(page, streamlit_url)
    zip_path = build_linkedin_zip(tmp_path / "linkedin_export.zip")
    import_linkedin_file(page, zip_path)
    expect(page.get_by_label("Imię i nazwisko")).to_have_value("Jan Kowalski", timeout=15_000)
    expect(page.get_by_label("Umiejętności (oddzielone przecinkami)")).to_have_value(
        "Python, FastAPI, Docker"
    )
    expect(page.locator("summary").filter(has_text="Acme Corp")).to_be_visible()
    expect(page.locator("summary").filter(has_text="Beta Sp. z o.o.")).to_be_visible()


def test_linkedin_positions_csv_import_partial_profile(page: Page, streamlit_url: str) -> None:
    goto_app(page, streamlit_url)
    import_linkedin_file(page, POSITIONS_CSV)
    expect(page.get_by_label("Imię i nazwisko")).to_have_value("—", timeout=15_000)
    expect(page.locator("summary").filter(has_text="Acme Corp")).to_be_visible()
    expect(page.locator("summary").filter(has_text="Beta Sp. z o.o.")).to_be_visible()


def test_linkedin_projects_csv_import_sorted_newest_first(
    page: Page, streamlit_url: str
) -> None:
    """Projects.csv row order is ignored; UI shows newest start date first."""
    goto_app(page, streamlit_url)
    import_linkedin_file(page, PROJECTS_CSV)

    expect(page.get_by_label("Imię i nazwisko")).to_have_value("—", timeout=15_000)
    project_rows = page.locator("summary").filter(has_text="@ Projekt")
    expect(project_rows).to_have_count(3)
    expect(project_rows.nth(0)).to_contain_text("#1 CV Generator @ Projekt")
    expect(project_rows.nth(1)).to_contain_text("#2 Mid App @ Projekt")
    expect(project_rows.nth(2)).to_contain_text("#3 Legacy Portal @ Projekt")


def test_linkedin_zip_import_projects_sorted_after_positions(
    page: Page, streamlit_url: str, tmp_path: Path
) -> None:
    goto_app(page, streamlit_url)
    zip_path = build_linkedin_zip(tmp_path / "linkedin_export_with_projects.zip")
    import_linkedin_file(page, zip_path)

    expect(page.get_by_label("Imię i nazwisko")).to_have_value("Jan Kowalski", timeout=15_000)
    expect(page.locator("summary").filter(has_text="Acme Corp")).to_be_visible()
    expect(page.locator("summary").filter(has_text="Beta Sp. z o.o.")).to_be_visible()
    project_rows = page.locator("summary").filter(has_text="@ Projekt")
    expect(project_rows).to_have_count(3)
    expect(project_rows.nth(0)).to_contain_text("#3 CV Generator @ Projekt")
    expect(project_rows.nth(1)).to_contain_text("#4 Mid App @ Projekt")
    expect(project_rows.nth(2)).to_contain_text("#5 Legacy Portal @ Projekt")


def test_linkedin_import_keeps_filled_fields_and_appends_experiences(
    page: Page, streamlit_url: str
) -> None:
    """Partial LinkedIn CSV must not wipe already filled scalars."""
    goto_app(page, streamlit_url)
    fill_partial_profile(
        page,
        full_name="Anna Nowak",
        headline="Lokalny headline",
        email="anna@example.com",
    )
    import_linkedin_file(page, POSITIONS_CSV)

    expect(page.get_by_label("Imię i nazwisko")).to_have_value("Anna Nowak", timeout=15_000)
    expect(page.get_by_label("Headline")).to_have_value("Lokalny headline")
    expect(page.get_by_label("Email")).to_have_value("anna@example.com")
    expect(page.locator("summary").filter(has_text="Acme Corp")).to_be_visible()
    expect(page.locator("summary").filter(has_text="Beta Sp. z o.o.")).to_be_visible()
    expect(page.locator("summary").filter(has_text="Konflikty importu")).to_have_count(0)


def test_linkedin_import_fills_empty_fields_and_shows_conflicts(
    page: Page, streamlit_url: str
) -> None:
    goto_app(page, streamlit_url)
    fill_partial_profile(
        page,
        full_name="Anna Nowak",
        headline="Lokalny headline",
        email="anna@example.com",
    )
    import_linkedin_file(page, PROFILE_CSV)

    expect(page.get_by_label("Imię i nazwisko")).to_have_value("Anna Nowak", timeout=15_000)
    expect(page.get_by_label("Headline")).to_have_value("Lokalny headline")
    expect(page.get_by_label("Email")).to_have_value("anna@example.com")
    expect(page.get_by_label("Krótkie podsumowanie")).to_have_value("Backend od 10 lat")
    expect(page.get_by_label("Lokalizacja")).to_have_value("Warszawa, Poland")
    expect(page.locator("summary").filter(has_text="Konflikty importu")).to_be_visible()
    expect(page.get_by_text("Aktualne w formularzu", exact=True)).to_have_count(2)
    expect(page.get_by_text("Z (eksport LinkedIn)", exact=True)).to_have_count(2)


def test_linkedin_import_conflict_apply_incoming_updates_field(
    page: Page, streamlit_url: str
) -> None:
    goto_app(page, streamlit_url)
    fill_partial_profile(
        page,
        full_name="Jan Kowalski",
        headline="Lokalny headline",
    )
    import_linkedin_file(page, PROFILE_CSV)

    expect(page.locator("summary").filter(has_text="Konflikty importu")).to_be_visible(
        timeout=15_000
    )
    apply_import_conflict_choice(page, field_label="Headline", use_incoming=True)

    expect(page.get_by_label("Headline")).to_have_value("Senior Python Developer", timeout=15_000)
    expect(page.get_by_label("Imię i nazwisko")).to_have_value("Jan Kowalski")
    expect(page.locator("summary").filter(has_text="Konflikty importu")).to_have_count(0)


def test_linkedin_import_conflict_skip_keeps_current_values(
    page: Page, streamlit_url: str
) -> None:
    goto_app(page, streamlit_url)
    fill_partial_profile(
        page,
        full_name="Anna Nowak",
        headline="Lokalny headline",
    )
    import_linkedin_file(page, PROFILE_CSV)

    expect(page.locator("summary").filter(has_text="Konflikty importu")).to_be_visible(
        timeout=15_000
    )
    page.get_by_role("button", name="Pomiń konflikty (zostaw aktualne)").click()

    expect(page.locator("summary").filter(has_text="Konflikty importu")).to_have_count(
        0, timeout=15_000
    )
    expect(page.get_by_label("Imię i nazwisko")).to_have_value("Anna Nowak")
    expect(page.get_by_label("Headline")).to_have_value("Lokalny headline")
    expect(page.get_by_label("Krótkie podsumowanie")).to_have_value("Backend od 10 lat")


def test_preview_edit_persists_before_export(page: Page, streamlit_url: str) -> None:
    goto_app(page, streamlit_url)
    run_full_generation_flow(page)

    open_tab(page, "Podgląd")
    preview = page.get_by_role("tabpanel", name="Podgląd")
    preview.get_by_label("Headline").fill("Lead Python Engineer for GammaTech")
    preview.get_by_label("Podsumowanie").fill("Custom summary before export.")

    export_docx(page)

    open_tab(page, "Podgląd")
    preview = page.get_by_role("tabpanel", name="Podgląd")
    expect(preview.get_by_label("Headline")).to_have_value("Lead Python Engineer for GammaTech")
    expect(preview.get_by_label("Podsumowanie")).to_have_value("Custom summary before export.")


def test_generate_tab_shows_matched_profile_and_job(page: Page, streamlit_url: str) -> None:
    goto_app(page, streamlit_url)
    set_profile_in_session(page)
    analyze_pasted_job_offer(page)
    open_tab(page, "Generuj")
    expect(page.get_by_text(f"Profil: {E2E_PROFILE['full_name']}")).to_be_visible()
    expect(page.get_by_text("Oferta: Senior Python Engineer @ GammaTech")).to_be_visible()
    run_generation_pipeline(page)
