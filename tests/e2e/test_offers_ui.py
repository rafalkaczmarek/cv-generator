"""Playwright flows for the 'Oferty' tab (Polish IT boards)."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from cv_generator.models import BoardOffer, BoardSource, TailoredCV
from cv_generator.services.docx_generator import ensure_builtin_templates, render_cv
from cv_generator.services.storage import Storage
from tests.e2e.helpers import (
    E2E_PROFILE,
    goto_app,
    open_tab,
    set_profile_in_session,
)

pytestmark = pytest.mark.e2e


def _db_path(e2e_workspace: Path) -> Path:
    return e2e_workspace / "data" / "cv_generator.sqlite"


def _recent(*, days_ago: int = 0) -> datetime:
    return datetime.now() - timedelta(days=days_ago)


def _build_offer(
    source: BoardSource,
    external_id: str,
    *,
    title: str,
    company: str,
    skills: list[str],
    published_at: datetime | None = None,
    is_active: bool = True,
    location: str | None = None,
) -> BoardOffer:
    return BoardOffer(
        source=source,
        external_id=external_id,
        url=f"https://example.com/{source.value}/{external_id}",
        title=title,
        company=company,
        skills=skills,
        published_at=published_at if published_at is not None else _recent(),
        location=location,
        is_active=is_active,
    )


@pytest.fixture
def clean_boards(e2e_workspace: Path):
    """Reset the board_offers / offer_matches / generated_cvs tables per test."""
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


def _preseed_offers(storage: Storage, offers: list[BoardOffer]) -> None:
    """Insert offers straight into the board_offers table (honours is_active)."""
    if offers:
        storage.upsert_board_offers(offers)


def _open_filters_expander(offers_panel) -> None:
    summary = offers_panel.locator("summary").filter(has_text="Filtry i źródła")
    expect(summary).to_be_visible(timeout=15_000)
    details = summary.locator("xpath=ancestor::details[1]")
    if details.get_attribute("open") is None:
        summary.click()
    expect(details).to_have_js_property("open", True, timeout=5_000)


def _set_offers_checkbox(offers_panel, label: str, *, checked: bool) -> None:
    """Set a Streamlit checkbox inside the offers 'Filtry i źródła' expander.

    Streamlit wraps each checkbox in a react-aria ``<label>`` that intercepts
    pointer events aimed at the input, so we click the checkbox with
    ``force=True`` after opening the expander. The target state is enforced
    explicitly because prior tests may leave widgets in an unexpected state.
    """
    _open_filters_expander(offers_panel)
    checkbox = offers_panel.get_by_role("checkbox", name=label)
    expect(checkbox).to_be_visible(timeout=10_000)
    if checkbox.is_checked() != checked:
        checkbox.click(force=True)
    expect(checkbox).to_be_checked(checked=checked, timeout=15_000)


def test_offers_tab_requires_profile(page: Page, streamlit_url: str) -> None:
    goto_app(page, streamlit_url)
    open_tab(page, "Oferty")
    expect(page.get_by_role("heading", name="Oferty pracy (portale PL)")).to_be_visible()
    expect(
        page.get_by_text(
            "Najpierw wczytaj lub zapisz profil w zakładce",
            exact=False,
        )
    ).to_be_visible()


def test_offers_tab_lists_preseeded_offers_with_scores(
    page: Page,
    streamlit_url: str,
    e2e_workspace: Path,
    clean_boards: Storage,
) -> None:
    _preseed_offers(
        clean_boards,
        [
            _build_offer(
                BoardSource.JUSTJOIN,
                "e2e-strong",
                title="Senior Python Engineer",
                company="GammaTech",
                skills=["Python", "FastAPI", "PostgreSQL", "Docker"],
                published_at=_recent(),
                location="Warszawa",
            ),
            _build_offer(
                BoardSource.NOFLUFF,
                "e2e-medium",
                title="Backend Developer",
                company="Betas",
                skills=["Python", "Django"],
                published_at=_recent(days_ago=1),
            ),
        ],
    )

    goto_app(page, streamlit_url)
    set_profile_in_session(page)
    open_tab(page, "Oferty")

    offers_panel = page.get_by_role("tabpanel", name="Oferty")

    expect(offers_panel.get_by_role("heading", name="Senior Python Engineer")).to_be_visible(
        timeout=15_000
    )
    expect(offers_panel.get_by_role("heading", name="Backend Developer")).to_be_visible()
    expect(offers_panel.get_by_text("GammaTech", exact=False)).to_be_visible()

    metrics = offers_panel.locator('[data-testid="stMetricValue"]')
    expect(metrics.first).to_have_text("100%", timeout=15_000)

    expect(offers_panel.get_by_role("button", name="Generuj CV")).to_have_count(2)


def test_offers_tab_min_score_filter_hides_weak_matches(
    page: Page,
    streamlit_url: str,
    e2e_workspace: Path,
    clean_boards: Storage,
) -> None:
    _preseed_offers(
        clean_boards,
        [
            _build_offer(
                BoardSource.JUSTJOIN,
                "match-1",
                title="Senior Python Engineer",
                company="GammaTech",
                skills=["Python", "FastAPI", "PostgreSQL"],
                published_at=_recent(),
            ),
            _build_offer(
                BoardSource.NOFLUFF,
                "match-0",
                title="Erlang Guru",
                company="RareStack",
                skills=["Erlang", "Haskell", "Rust"],
                published_at=_recent(),
            ),
        ],
    )

    goto_app(page, streamlit_url)
    set_profile_in_session(page)
    open_tab(page, "Oferty")
    offers_panel = page.get_by_role("tabpanel", name="Oferty")

    expect(offers_panel.get_by_role("heading", name="Senior Python Engineer")).to_be_visible(
        timeout=15_000
    )
    expect(offers_panel.get_by_role("heading", name="Erlang Guru")).to_have_count(0)


def test_offers_tab_hides_zero_percent_and_skillless_offers(
    page: Page,
    streamlit_url: str,
    e2e_workspace: Path,
    clean_boards: Storage,
) -> None:
    """0% offers (empty skills or no overlap) must not appear on the list."""
    _preseed_offers(
        clean_boards,
        [
            _build_offer(
                BoardSource.JUSTJOIN,
                "keep-me",
                title="Senior Python Engineer",
                company="GammaTech",
                skills=["Python", "FastAPI", "PostgreSQL"],
                published_at=_recent(),
            ),
            _build_offer(
                BoardSource.PRACUJ,
                "no-skills",
                title="Skilless Mystery Role",
                company="BlankCorp",
                skills=[],
                published_at=_recent(),
            ),
            _build_offer(
                BoardSource.NOFLUFF,
                "zero-overlap",
                title="Cobol Mainframe Expert",
                company="LegacySoft",
                skills=["Cobol", "Fortran", "Ada"],
                published_at=_recent(),
            ),
        ],
    )

    goto_app(page, streamlit_url)
    set_profile_in_session(page)
    open_tab(page, "Oferty")
    offers_panel = page.get_by_role("tabpanel", name="Oferty")

    expect(offers_panel.get_by_role("heading", name="Senior Python Engineer")).to_be_visible(
        timeout=15_000
    )
    expect(offers_panel.get_by_role("heading", name="Skilless Mystery Role")).to_have_count(0)
    expect(offers_panel.get_by_role("heading", name="Cobol Mainframe Expert")).to_have_count(0)
    expect(offers_panel.get_by_text("BlankCorp", exact=False)).to_have_count(0)
    expect(offers_panel.get_by_text("LegacySoft", exact=False)).to_have_count(0)

    metrics = offers_panel.locator('[data-testid="stMetricValue"]')
    expect(metrics).to_have_count(1)
    expect(metrics.first).not_to_have_text("0%")


def test_offers_tab_shows_and_toggles_inactive_offers(
    page: Page,
    streamlit_url: str,
    e2e_workspace: Path,
    clean_boards: Storage,
) -> None:
    _preseed_offers(
        clean_boards,
        [
            _build_offer(
                BoardSource.JUSTJOIN,
                "still-here",
                title="Active Python Role",
                company="ActiveCo",
                skills=["Python", "FastAPI"],
                published_at=_recent(),
            ),
            _build_offer(
                BoardSource.JUSTJOIN,
                "removed",
                title="Ghost Python Role",
                company="GhostCo",
                skills=["Python", "FastAPI"],
                published_at=_recent(days_ago=1),
                is_active=False,
            ),
        ],
    )

    goto_app(page, streamlit_url)
    set_profile_in_session(page)
    open_tab(page, "Oferty")

    offers_panel = page.get_by_role("tabpanel", name="Oferty")
    expect(offers_panel.get_by_text("Active Python Role", exact=False)).to_be_visible(
        timeout=15_000
    )
    expect(offers_panel.get_by_text("Ghost Python Role", exact=False)).to_be_visible()
    expect(offers_panel.get_by_text("wyszarzona", exact=False).first).to_be_visible()

    _set_offers_checkbox(
        offers_panel,
        "Pokaż oferty nieaktywne (wyszarzone)",
        checked=False,
    )

    expect(offers_panel.get_by_role("heading", name="Ghost Python Role")).to_have_count(
        0, timeout=15_000
    )
    expect(offers_panel.get_by_role("heading", name="Active Python Role")).to_be_visible()


def test_offers_tab_download_button_appears_when_cv_already_exists(
    page: Page,
    streamlit_url: str,
    e2e_workspace: Path,
    clean_boards: Storage,
) -> None:
    offer = _build_offer(
        BoardSource.JUSTJOIN,
        "with-existing-cv",
        title="Senior Python Engineer",
        company="GammaTech",
        skills=["Python", "FastAPI", "PostgreSQL", "Docker"],
        published_at=_recent(),
    )
    _preseed_offers(clean_boards, [offer])

    templates_dir = e2e_workspace / "templates"
    ensure_builtin_templates(templates_dir)

    output_dir = e2e_workspace / "output"
    output_dir.mkdir(exist_ok=True)

    cv = TailoredCV(
        full_name=E2E_PROFILE["full_name"],
        headline="Senior Python Engineer",
        summary="Preseeded CV for E2E download check.",
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
    assert cv_path.exists()

    clean_boards.record_generated_cv(
        profile_name=E2E_PROFILE["full_name"],
        job_slug="e2e-existing",
        file_path=cv_path,
        cv=cv,
        offer_key=offer.offer_key,
    )

    goto_app(page, streamlit_url)
    set_profile_in_session(page)
    open_tab(page, "Oferty")
    offers_panel = page.get_by_role("tabpanel", name="Oferty")

    expect(offers_panel.get_by_role("heading", name="Senior Python Engineer")).to_be_visible(
        timeout=15_000
    )
    expect(offers_panel.get_by_role("button", name="Pobierz CV")).to_be_visible()
    expect(offers_panel.get_by_role("button", name="Wyślij do Google Docs")).to_be_visible()
    expect(offers_panel.get_by_role("button", name="Generuj ponownie")).to_be_visible()
    expect(offers_panel.get_by_role("button", name="Generuj CV")).to_have_count(0)


def test_offers_tab_source_filter_hides_unselected_portals(
    page: Page,
    streamlit_url: str,
    e2e_workspace: Path,
    clean_boards: Storage,
) -> None:
    _preseed_offers(
        clean_boards,
        [
            _build_offer(
                BoardSource.JUSTJOIN,
                "jjit-1",
                title="JJIT Python Role",
                company="JJITCo",
                skills=["Python", "FastAPI"],
                published_at=_recent(),
            ),
            _build_offer(
                BoardSource.NOFLUFF,
                "nfj-1",
                title="NFJ Python Role",
                company="NFJCo",
                skills=["Python", "FastAPI"],
                published_at=_recent(),
            ),
        ],
    )

    goto_app(page, streamlit_url)
    set_profile_in_session(page)
    open_tab(page, "Oferty")
    offers_panel = page.get_by_role("tabpanel", name="Oferty")

    jjit_heading = offers_panel.get_by_role("heading").filter(has_text="JJIT Python Role")
    nfj_heading = offers_panel.get_by_role("heading").filter(has_text="NFJ Python Role")

    expect(jjit_heading).to_have_count(1, timeout=15_000)
    expect(nfj_heading).to_have_count(1)

    _set_offers_checkbox(offers_panel, "No Fluff Jobs", checked=False)

    expect(nfj_heading).to_have_count(0, timeout=15_000)
    expect(jjit_heading).to_have_count(1, timeout=15_000)


def test_offers_tab_hides_old_and_non_keyword_offers(
    page: Page,
    streamlit_url: str,
    e2e_workspace: Path,
    clean_boards: Storage,
) -> None:
    """Only today/yesterday offers whose title/skills hit the keywords are listed."""
    _preseed_offers(
        clean_boards,
        [
            _build_offer(
                BoardSource.JUSTJOIN,
                "fresh-python",
                title="Senior Python Engineer",
                company="GammaTech",
                skills=["Python", "FastAPI"],
                published_at=_recent(),
            ),
            _build_offer(
                BoardSource.NOFLUFF,
                "stale-python",
                title="Legacy Python Role",
                company="OldCo",
                skills=["Python", "FastAPI"],
                published_at=_recent(days_ago=5),
            ),
            _build_offer(
                BoardSource.PRACUJ,
                "fresh-go",
                title="Go Platform Engineer",
                company="GopherLabs",
                skills=["Go", "Kubernetes"],
                published_at=_recent(),
            ),
        ],
    )

    goto_app(page, streamlit_url)
    set_profile_in_session(page)
    open_tab(page, "Oferty")
    offers_panel = page.get_by_role("tabpanel", name="Oferty")

    expect(offers_panel.get_by_role("heading", name="Senior Python Engineer")).to_be_visible(
        timeout=15_000
    )
    expect(offers_panel.get_by_text("Legacy Python Role", exact=False)).to_have_count(0)
    expect(offers_panel.get_by_text("OldCo", exact=False)).to_have_count(0)
    expect(offers_panel.get_by_text("Go Platform Engineer", exact=False)).to_have_count(0)
    expect(offers_panel.get_by_text("GopherLabs", exact=False)).to_have_count(0)


def test_offers_tab_keyword_field_filters_visible_list(
    page: Page,
    streamlit_url: str,
    e2e_workspace: Path,
    clean_boards: Storage,
) -> None:
    _preseed_offers(
        clean_boards,
        [
            _build_offer(
                BoardSource.JUSTJOIN,
                "python-role",
                title="Senior Python Engineer",
                company="GammaTech",
                skills=["Python", "FastAPI"],
                published_at=_recent(),
            ),
        ],
    )

    goto_app(page, streamlit_url)
    set_profile_in_session(page)
    open_tab(page, "Oferty")
    offers_panel = page.get_by_role("tabpanel", name="Oferty")

    expect(offers_panel.get_by_role("heading", name="Senior Python Engineer")).to_be_visible(
        timeout=15_000
    )

    _open_filters_expander(offers_panel)
    keywords = offers_panel.get_by_role(
        "textbox", name="Słowa kluczowe (oddzielone przecinkami)"
    )
    expect(keywords).to_be_visible()
    keywords.fill("Erlang")
    keywords.press("Tab")

    expect(offers_panel.get_by_role("heading", name="Senior Python Engineer")).to_have_count(
        0, timeout=15_000
    )
    expect(
        offers_panel.get_by_text("pasujących do słów kluczowych", exact=False)
    ).to_be_visible(timeout=15_000)
