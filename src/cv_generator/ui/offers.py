"""'Oferty' tab — Polish IT board listings matched against the loaded profile."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import streamlit as st

from cv_generator.agents.job_analyzer import JobFetchError, analyze_job
from cv_generator.config import get_settings
from cv_generator.graph.pipeline import generate_cv
from cv_generator.models import BOARD_LABELS, BoardOffer, BoardSource, JobOffer, Profile
from cv_generator.services.boards import BoardFetchResult, BoardFetchService, BoardQuery
from cv_generator.services.docx_generator import render_cv
from cv_generator.services.offer_matcher import (
    MatchResult,
    score_offers,
    sort_results,
    top_profile_keywords,
)
from cv_generator.ui.google_export import (
    document_name_for_cv,
    render_send_to_google_docs_button,
)
from cv_generator.ui.llm import format_llm_error
from cv_generator.ui.state import ss_get, storage


def render_offers_tab() -> None:
    st.header("Oferty pracy (portale PL)")
    profile: Profile | None = ss_get("profile")
    if not profile:
        st.info(
            "Najpierw wczytaj lub zapisz profil w zakładce **Profil** — "
            "oferty są sortowane i oceniane względem Twoich umiejętności."
        )
        return

    settings = get_settings()

    with st.expander("Filtry i źródła", expanded=False):
        _render_query_form(profile)
        selected_sources = _render_source_filters()
        min_score = st.slider(
            "Minimalne dopasowanie (score %)",
            min_value=0,
            max_value=100,
            value=int(settings.min_board_match_score),
            step=5,
            help="Oferty poniżej progu (w tym z oceną 0%) są ukrywane.",
            key="offers_min_score",
        )
        show_inactive = st.checkbox(
            "Pokaż oferty nieaktywne (wyszarzone)",
            value=True,
            help="Oferty, których nie było w ostatnim odświeżeniu portalu.",
            key="offers_show_inactive",
        )

    col_a, col_b = st.columns([1, 3])
    with col_a:
        if st.button("Odśwież oferty", type="primary", key="offers_refresh"):
            _run_refresh(profile, selected_sources)
    with col_b:
        last_result: BoardFetchResult | None = ss_get("offers_last_refresh_result")
        if last_result:
            _render_refresh_summary(last_result)

    offers = storage().list_board_offers(
        sources=selected_sources or None,
        include_inactive=True,
    )
    if not offers:
        st.info(
            "Brak zapisanych ofert. Kliknij **Odśwież oferty**, aby pobrać "
            "aktualne listingi z wybranych portali."
        )
        return

    results = score_offers(profile, offers, min_score=min_score)
    if not show_inactive:
        results = [r for r in results if r.offer.is_active]
    results = sort_results(results)

    _persist_scores(profile.full_name, results)
    _render_summary(offers, results)
    _render_results(profile, results)


def _render_query_form(profile: Profile) -> None:
    default_keywords = ", ".join(top_profile_keywords(profile))
    st.text_input(
        "Słowa kluczowe (oddzielone przecinkami)",
        value=st.session_state.get("offers_keywords", default_keywords),
        key="offers_keywords",
        help="Domyślnie skills z profilu — zawęź lub rozszerz według uznania.",
    )
    col_city, col_remote = st.columns([2, 1])
    with col_city:
        st.text_input("Miasto (opcjonalnie)", value="", key="offers_city")
    with col_remote:
        st.checkbox("Tylko zdalne", value=False, key="offers_remote_only")


def _render_source_filters() -> list[BoardSource]:
    st.caption("Portale")
    selected: list[BoardSource] = []
    cols = st.columns(len(BoardSource))
    for col, source in zip(cols, BoardSource, strict=True):
        with col:
            state_key = f"offers_source_{source.value}"
            checked = st.checkbox(
                BOARD_LABELS[source],
                value=st.session_state.get(state_key, True),
                key=state_key,
            )
            if checked:
                selected.append(source)
    return selected


def _build_query() -> BoardQuery:
    settings = get_settings()
    keywords_raw = st.session_state.get("offers_keywords", "") or ""
    keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()]
    city = (st.session_state.get("offers_city") or "").strip() or None
    remote = bool(st.session_state.get("offers_remote_only", False))
    return BoardQuery(
        keywords=keywords,
        city=city,
        remote_only=remote,
        limit_per_board=settings.board_limit_per_source,
    )


def _run_refresh(profile: Profile, sources: list[BoardSource]) -> None:
    if not sources:
        st.warning("Zaznacz przynajmniej jeden portal.")
        return
    query = _build_query()
    service = BoardFetchService(storage=storage())
    with st.spinner("Pobieram oferty z portali (równolegle)..."):
        try:
            result = service.refresh(sources=sources, query=query)
        except Exception as exc:  # pragma: no cover - defensive UX guard
            st.error(f"Nie udało się odświeżyć: {exc}")
            return
    st.session_state.offers_last_refresh_result = result
    st.session_state.offers_last_refresh_at = datetime.now(UTC).isoformat()
    _ = profile
    st.rerun()


def _render_refresh_summary(result: BoardFetchResult) -> None:
    parts: list[str] = []
    for source in BoardSource:
        count = result.fetched.get(source)
        if count is None:
            continue
        parts.append(f"{BOARD_LABELS[source]}: {count}")
    if parts:
        st.caption("Ostatnie pobranie — " + " | ".join(parts))
    if result.errors:
        for source, message in result.errors.items():
            st.warning(f"{BOARD_LABELS[source]}: {message}")


def _render_summary(all_offers: list[BoardOffer], results: list[MatchResult]) -> None:
    total = len(all_offers)
    active = sum(1 for o in all_offers if o.is_active)
    shown = len(results)
    st.caption(
        f"Widocznych ofert: **{shown}** / w bazie: **{total}** "
        f"(aktywnych: {active}, nieaktywnych: {total - active})"
    )


def _render_results(profile: Profile, results: list[MatchResult]) -> None:
    if not results:
        st.info("Brak ofert spełniających kryteria.")
        return
    for result in results:
        _render_offer_card(profile, result)


def _render_offer_card(profile: Profile, result: MatchResult) -> None:
    offer = result.offer
    inactive = not offer.is_active
    status_badge = "wyszarzona" if inactive else "aktywna"
    prefix = "~~" if inactive else ""
    suffix = "~~" if inactive else ""

    with st.container(border=True):
        header_cols = st.columns([5, 1])
        with header_cols[0]:
            st.markdown(
                f"### {prefix}{offer.title}{suffix}\n"
                f"**{offer.company or '—'}** · {BOARD_LABELS[offer.source]} · "
                f"_{status_badge}_"
            )
        with header_cols[1]:
            st.metric("Score", f"{result.match_score}%")

        meta_bits: list[str] = []
        if offer.location:
            meta_bits.append(offer.location)
        if offer.seniority:
            meta_bits.append(offer.seniority)
        if offer.workplace_type:
            meta_bits.append(offer.workplace_type)
        if offer.salary_text:
            meta_bits.append(offer.salary_text)
        if offer.published_at:
            meta_bits.append(offer.published_at.strftime("%Y-%m-%d"))
        if meta_bits:
            st.caption(" · ".join(meta_bits))

        if offer.skills:
            matched_lower = {m.lower() for m in result.matched}
            tags: list[str] = []
            for skill in offer.skills[:12]:
                mark = "✅ " if skill.lower() in matched_lower else ""
                tags.append(f"{mark}{skill}")
            st.write(" ".join(f"`{t}`" for t in tags))

        st.markdown(f"[Otwórz ofertę na portalu]({offer.url})")

        _render_actions(profile, result)


def _render_actions(profile: Profile, result: MatchResult) -> None:
    offer = result.offer
    existing = storage().find_cv_for_offer(
        profile_name=profile.full_name, offer_key=offer.offer_key
    )

    action_cols = st.columns([1, 1, 1, 2])
    generate_key = f"offer_gen_{offer.offer_key}"
    with action_cols[0]:
        button_label = "Generuj CV" if not existing else "Generuj ponownie"
        clicked = st.button(
            button_label,
            key=generate_key,
            disabled=not offer.is_active and existing is None,
            help=(
                "Nieaktywna oferta — nie można wygenerować nowego CV."
                if not offer.is_active
                else None
            ),
        )
    with action_cols[1]:
        if existing:
            _render_download_button(existing)
        else:
            st.caption("Brak CV.")
    with action_cols[2]:
        if existing:
            _render_google_docs_button(existing, profile=profile, offer=offer)
    with action_cols[3]:
        if existing:
            created = existing.get("created_at", "")
            score = existing.get("match_score", "?")
            st.caption(f"Ostatnie CV: {created} · score {score}")

    if clicked:
        _generate_cv_for_offer(profile, result)


def _render_download_button(existing: dict[str, object]) -> None:
    file_path = Path(str(existing.get("file_path", "")))
    if not file_path.exists():
        st.caption("Plik CV został usunięty z dysku. Wygeneruj ponownie.")
        return
    with open(file_path, "rb") as fh:
        st.download_button(
            "Pobierz CV",
            data=fh.read(),
            file_name=file_path.name,
            mime=(
                "application/vnd.openxmlformats-officedocument"
                ".wordprocessingml.document"
            ),
            key=f"offer_dl_{existing.get('id')}",
        )


def _render_google_docs_button(
    existing: dict[str, object],
    *,
    profile: Profile,
    offer: BoardOffer,
) -> None:
    file_path = Path(str(existing.get("file_path", "")))
    if not file_path.exists():
        return
    render_send_to_google_docs_button(
        docx_path=file_path,
        document_name=document_name_for_cv(
            full_name=profile.full_name,
            company=offer.company,
        ),
        key=f"offer_gdocs_{existing.get('id')}",
    )


def _generate_cv_for_offer(profile: Profile, result: MatchResult) -> None:
    offer = result.offer
    with st.spinner(f"Generuję CV dla oferty: {offer.title}..."):
        try:
            job = _board_offer_to_job_offer(offer)
        except JobFetchError as exc:
            st.error(f"Nie udało się pobrać treści oferty: {exc}")
            return
        except Exception as exc:  # pragma: no cover - LLM error path
            st.error(format_llm_error(exc))
            return

        try:
            cv = generate_cv(profile, job)
        except Exception as exc:  # pragma: no cover - LLM error path
            st.error(format_llm_error(exc))
            return

        try:
            file_path = render_cv(
                cv,
                filename=f"cv_{offer.offer_key.replace(':', '_')}.docx",
                language=cv.language,
            )
        except Exception as exc:  # pragma: no cover - filesystem/template errors
            st.error(f"Nie udało się zapisać DOCX: {exc}")
            return

        storage().record_generated_cv(
            profile_name=profile.full_name,
            job_slug=job.slug(),
            file_path=file_path,
            cv=cv,
            offer_key=offer.offer_key,
        )
        st.session_state.tailored = cv
        st.session_state.job_offer = job
        st.session_state.preview_language = cv.language or "en"

    st.success(f"Wygenerowano CV (score {cv.match_score}/100). Plik: {file_path.name}")
    st.rerun()


def _board_offer_to_job_offer(offer: BoardOffer) -> JobOffer:
    """Build a full ``JobOffer`` from a ``BoardOffer`` using the LLM analyzer."""
    return analyze_job(url=str(offer.url), raw_text=None)


def _persist_scores(profile_name: str, results: list[MatchResult]) -> None:
    """Cache the latest scores so match history persists across reruns."""
    for result in results:
        storage().save_match(
            profile_name=profile_name,
            offer_key=result.offer.offer_key,
            match_score=result.match_score,
            matched=result.matched,
            missing=result.missing,
        )
