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
    st.caption("CV jest domyślnie generowane po angielsku.")

    also_polish = st.checkbox(
        "Wygeneruj też wersję polską",
        value=False,
        help="Uruchamia dodatkowy przebieg pipeline'u i zapisuje osobne CV po polsku.",
    )

    if st.button("Uruchom pipeline agentów", type="primary"):
        with st.spinner("Agenci analizują profil i ofertę, dopasowują treść CV..."):
            try:
                cv_en = generate_cv(profile, offer, language="en")
                st.session_state.tailored = cv_en
                st.session_state.preview_language = "en"
                st.session_state.pop("tailored_pl", None)

                if also_polish:
                    cv_pl = generate_cv(profile, offer, language="pl")
                    st.session_state.tailored_pl = cv_pl
                    st.success(
                        f"Gotowe (EN + PL). Match score EN: {cv_en.match_score}/100, "
                        f"PL: {cv_pl.match_score}/100"
                    )
                else:
                    st.success(f"Gotowe. Match score: {cv_en.match_score}/100")
            except Exception as exc:  # pragma: no cover - LLM errors
                st.error(format_llm_error(exc))
