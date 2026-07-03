"""Shared Playwright helpers for Streamlit E2E flows."""

from __future__ import annotations

from playwright.sync_api import Page, expect

E2E_PROFILE = {
    "full_name": "Jan Kowalski",
    "headline": "Senior Python Developer",
    "email": "jan@example.com",
    "skills": "Python, FastAPI, PostgreSQL, Docker",
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

    page.get_by_label("Imię i nazwisko").fill(E2E_PROFILE["full_name"])
    page.get_by_label("Headline").fill(E2E_PROFILE["headline"])
    page.get_by_label("Email").fill(E2E_PROFILE["email"])
    page.get_by_label("Umiejętności (oddzielone przecinkami)").fill(E2E_PROFILE["skills"])

    page.get_by_role("button", name="Dodaj doświadczenie").click()
    page.locator("summary").filter(has_text="#1").click()
    experience = page.locator('[data-testid="stExpanderDetails"]').last
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
    expect(page.get_by_text("Oferta przeanalizowana: Senior Python Engineer @ GammaTech")).to_be_visible(
        timeout=30_000
    )
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


def export_docx(page: Page) -> None:
    open_tab(page, "Eksport")
    page.get_by_role("button", name="Zapisz jako DOCX").click()
    expect(page.get_by_text("Zapisano:")).to_be_visible(timeout=30_000)
    expect(page.get_by_role("button", name="Pobierz plik")).to_be_visible()
