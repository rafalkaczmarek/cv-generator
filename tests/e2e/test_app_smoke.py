"""Smoke E2E tests for the Streamlit UI."""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

TAB_HEADERS = {
    "Profil": "Profil kandydata",
    "Oferta": "Oferta pracy",
    "Generuj": "Generowanie CV",
    "Podgląd": "Podgląd i edycja CV",
    "Eksport": "Eksport i historia",
}


def test_app_loads_main_screen(page: Page, streamlit_url: str) -> None:
    page.goto(streamlit_url, wait_until="domcontentloaded")
    expect(page.get_by_role("heading", name="CV Generator")).to_be_visible(timeout=30_000)
    expect(
        page.get_by_text("AI-powered, dopasowane do konkretnej oferty pracy.")
    ).to_be_visible()


def test_profile_tab_is_active_by_default(page: Page, streamlit_url: str) -> None:
    page.goto(streamlit_url)
    expect(page.get_by_role("tab", name="Profil")).to_have_attribute("aria-selected", "true")
    expect(page.get_by_role("heading", name=TAB_HEADERS["Profil"])).to_be_visible()


@pytest.mark.parametrize("tab_name", list(TAB_HEADERS))
def test_tabs_are_navigable(page: Page, streamlit_url: str, tab_name: str) -> None:
    page.goto(streamlit_url)
    page.get_by_role("tab", name=tab_name).click()
    expect(page.get_by_role("tab", name=tab_name)).to_have_attribute("aria-selected", "true")
    expect(page.get_by_role("heading", name=TAB_HEADERS[tab_name])).to_be_visible()
