"""Shared Playwright helpers for Streamlit E2E flows."""

from __future__ import annotations

import re
from pathlib import Path

from playwright.sync_api import Page, expect
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

E2E_PROFILE = {
    "full_name": "Jan Kowalski",
    "headline": "Senior Python Developer",
    "email": "jan@example.com",
    "skills": "Python, FastAPI, PostgreSQL, Docker",
    "courses": "AWS Certified Developer, Kubernetes Fundamentals",
    "experience_company": "Acme Corp",
    "experience_title": "Senior Backend Engineer",
}

E2E_JOB_TEXT = (
    "GammaTech is hiring a Senior Python Engineer. "
    "Requirements: Python, FastAPI, PostgreSQL. Nice to have: Docker."
)


def goto_app(page: Page, streamlit_url: str) -> None:
    page.goto(streamlit_url, wait_until="domcontentloaded")
    expect(page.get_by_role("heading", name="CV Generator")).to_be_visible(timeout=30_000)


def open_tab(page: Page, tab_name: str) -> None:
    page.get_by_role("tab", name=tab_name).click()
    expect(page.get_by_role("tab", name=tab_name)).to_have_attribute("aria-selected", "true")


def fill_minimal_profile(page: Page) -> None:
    """Fill profile form and add one experience entry."""
    open_tab(page, "Profil")
    profile = page.get_by_role("tabpanel", name="Profil")

    profile.get_by_label("Imię i nazwisko").fill(E2E_PROFILE["full_name"])
    profile.get_by_label("Headline").fill(E2E_PROFILE["headline"])
    profile.get_by_label("Email").fill(E2E_PROFILE["email"])
    profile.get_by_label("Umiejętności (oddzielone przecinkami)").fill(E2E_PROFILE["skills"])
    profile.get_by_label("Kursy (oddzielone przecinkami)").fill(E2E_PROFILE["courses"])

    profile.get_by_role("button", name="Dodaj doświadczenie").click()
    summary = profile.locator("summary").filter(has_text="#1")
    expect(summary).to_be_visible(timeout=15_000)
    details = summary.locator("xpath=ancestor::details[1]")
    if details.get_attribute("open") is None:
        summary.click()
    expect(details).to_have_js_property("open", True, timeout=5_000)
    experience = details.locator('[data-testid="stExpanderDetails"]')
    experience.get_by_label("Firma", exact=True).fill(E2E_PROFILE["experience_company"])
    experience.get_by_label("Stanowisko", exact=True).fill(E2E_PROFILE["experience_title"])


def set_profile_in_session(page: Page) -> None:
    fill_minimal_profile(page)
    page.get_by_role("button", name="Tylko ustaw w sesji (bez zapisu)").click()
    expect(page.get_by_text("Profil ustawiony.")).to_be_visible(timeout=15_000)


def save_profile_to_storage(page: Page) -> None:
    fill_minimal_profile(page)
    page.get_by_role("button", name="Zapisz profil w bazie lokalnej").click()
    expect(page.get_by_text(f"Zapisano profil dla: {E2E_PROFILE['full_name']}")).to_be_visible(
        timeout=15_000
    )


def analyze_pasted_job_offer(page: Page) -> None:
    open_tab(page, "Oferta")
    page.get_by_label("Wklejona treść oferty (opcjonalnie)").fill(E2E_JOB_TEXT)
    page.get_by_role("button", name="Analizuj ofertę").click()
    expect(
        page.get_by_text("Oferta przeanalizowana: Senior Python Engineer @ GammaTech")
    ).to_be_visible(timeout=30_000)
    expect(page.get_by_role("heading", name="Wykryte wymagania")).to_be_visible()


def run_generation_pipeline(page: Page) -> None:
    open_tab(page, "Generuj")
    page.get_by_role("button", name="Uruchom pipeline agentów").click()
    expect(page.get_by_text("Gotowe. Match score:")).to_be_visible(timeout=60_000)


def reload_saved_profile(page: Page, profile_name: str) -> None:
    open_tab(page, "Profil")
    page.get_by_label("Wczytaj zapisany profil").click()
    page.get_by_text(profile_name, exact=True).last.click()
    page.get_by_role("button", name="Wczytaj").click()
    expect(page.get_by_label("Imię i nazwisko")).to_have_value(profile_name, timeout=15_000)


def _template_combobox(page: Page):
    return page.get_by_role("combobox", name="Szablon CV")


def select_cv_template(page: Page, option_substring: str) -> None:
    """Pick a template in the Eksport tab by visible option text (e.g. 'Nowoczesny')."""
    open_tab(page, "Eksport")
    box = _template_combobox(page)
    expect(box).to_be_visible()
    box.click()
    page.get_by_role("option", name=re.compile(re.escape(option_substring))).click()
    expect(box).to_have_value(re.compile(re.escape(option_substring)), timeout=15_000)


def export_docx(page: Page, *, template_option: str | None = None) -> None:
    open_tab(page, "Eksport")
    expect(_template_combobox(page)).to_be_visible()
    if template_option is not None:
        select_cv_template(page, template_option)
    page.get_by_role("button", name="Zapisz jako DOCX").click()
    expect(page.get_by_text("Zapisano:")).to_be_visible(timeout=30_000)
    expect(page.get_by_role("button", name="Pobierz plik")).to_be_visible()


def _open_details(page: Page, summary_text: str) -> None:
    """Ensure a Streamlit expander ``<details>`` is open (survives widget reruns)."""
    summary = page.locator("summary").filter(has_text=summary_text)
    expect(summary).to_be_visible(timeout=15_000)
    details = summary.locator("xpath=ancestor::details[1]")
    if details.get_attribute("open") is None:
        summary.click()
    expect(details).to_have_js_property("open", True, timeout=5_000)


def import_linkedin_file(page: Page, file_path: Path) -> None:
    open_tab(page, "Profil")
    _open_details(page, "Importuj z eksportu LinkedIn")
    page.locator('[data-testid="stFileUploaderDropzone"] input[type="file"]').set_input_files(
        str(file_path)
    )
    # File upload triggers a Streamlit rerun; the expander may collapse briefly.
    button = page.get_by_role("button", name="Wczytaj dane z LinkedIn")
    last_error: Exception | None = None
    for _ in range(4):
        _open_details(page, "Importuj z eksportu LinkedIn")
        try:
            button.click(timeout=5_000)
            return
        except PlaywrightTimeoutError as exc:
            last_error = exc
    assert last_error is not None
    raise last_error


def fill_partial_profile(
    page: Page,
    *,
    full_name: str,
    headline: str,
    email: str = "jan@example.com",
) -> None:
    """Fill only basic scalar fields (no experience) before a LinkedIn merge import."""
    open_tab(page, "Profil")
    page.get_by_label("Imię i nazwisko").fill(full_name)
    page.get_by_label("Headline").fill(headline)
    page.get_by_label("Email").fill(email)


def apply_import_conflict_choice(
    page: Page,
    *,
    field_label: str,
    use_incoming: bool,
    source: str = "eksport LinkedIn",
) -> None:
    """Pick current/incoming for one conflict field and apply all choices."""
    summary = page.locator("summary").filter(has_text="Konflikty importu")
    expect(summary).to_be_visible(timeout=15_000)
    details = summary.locator("xpath=ancestor::details[1]")
    if details.get_attribute("open") is None:
        summary.click()

    choice_label = (
        f"Użyj z ({source}) — {field_label}"
        if use_incoming
        else f"Zachowaj aktualne — {field_label}"
    )
    page.get_by_text(choice_label, exact=True).click()
    page.get_by_role("button", name="Zastosuj wybrane wartości").click()
    expect(page.locator("summary").filter(has_text="Konflikty importu")).to_have_count(
        0, timeout=15_000
    )


def run_full_generation_flow(page: Page) -> None:
    set_profile_in_session(page)
    analyze_pasted_job_offer(page)
    run_generation_pipeline(page)
