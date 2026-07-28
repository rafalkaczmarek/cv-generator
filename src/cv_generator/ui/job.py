"""Job offer tab."""

from __future__ import annotations

import streamlit as st

from cv_generator.agents.job_analyzer import JobFetchError, analyze_job
from cv_generator.models import JobOffer
from cv_generator.ui.llm import format_llm_error
from cv_generator.ui.state import ss_get, storage


def render_job_tab() -> None:
    st.header("Oferta pracy")
    url = st.text_input("URL oferty (opcjonalnie)", key="job_url")
    raw_text = st.text_area("Wklejona treść oferty (opcjonalnie)", height=240, key="job_raw_text")

    if st.button("Analizuj ofertę", type="primary"):
        if not url and not raw_text.strip():
            st.warning("Podaj URL lub wklej treść oferty.")
        else:
            with st.spinner("Analizuję ofertę przez LLM..."):
                try:
                    offer = analyze_job(url=url or None, raw_text=raw_text or None)
                    st.session_state.job_offer = offer
                    storage().save_job_offer(offer)
                    st.success(f"Oferta przeanalizowana: {offer.title} @ {offer.company}")
                except (JobFetchError, ValueError) as exc:
                    st.error(f"Nie udało się pobrać oferty: {exc}")
                except Exception as exc:  # pragma: no cover - LLM/network errors
                    st.error(format_llm_error(exc))

    offer: JobOffer | None = ss_get("job_offer")
    if offer:
        st.subheader("Wykryte wymagania")
        st.write("**Tytuł:**", offer.title)
        st.write("**Firma:**", offer.company)
        st.write("**Lokalizacja:**", offer.location)

        with st.expander("Wymagania", expanded=True):
            for r in offer.requirements:
                st.markdown(f"- {r}")
        with st.expander("Mile widziane"):
            for r in offer.nice_to_have:
                st.markdown(f"- {r}")
        with st.expander("Obowiązki"):
            for r in offer.responsibilities:
                st.markdown(f"- {r}")
        with st.expander("Słowa kluczowe ATS"):
            st.write(", ".join(offer.keywords))
