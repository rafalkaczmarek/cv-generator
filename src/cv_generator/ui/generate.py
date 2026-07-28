"""CV generation tab."""

from __future__ import annotations

import streamlit as st

from cv_generator.graph.pipeline import generate_cv
from cv_generator.ui.llm import format_llm_error
from cv_generator.ui.state import ss_get


def render_generate_tab() -> None:
    st.header("Generowanie CV")
    profile = ss_get("profile")
    offer = ss_get("job_offer")

    if not profile:
        st.info("Najpierw uzupełnij i zapisz profil w zakładce 'Profil'.")
        return
    if not offer:
        st.info("Najpierw przeanalizuj ofertę w zakładce 'Oferta'.")
        return

    st.write(f"Profil: **{profile.full_name}**")
    st.write(f"Oferta: **{offer.title}** @ **{offer.company}**")

    if st.button("Uruchom pipeline agentów", type="primary"):
        with st.spinner("Agenci analizują profil i oferta, dopasowują treść CV..."):
            try:
                cv = generate_cv(profile, offer)
                st.session_state.tailored = cv
                st.success(f"Gotowe. Match score: {cv.match_score}/100")
            except Exception as exc:  # pragma: no cover - LLM errors
                st.error(format_llm_error(exc))
