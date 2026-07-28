"""Preview and human-in-the-loop edit tab."""

from __future__ import annotations

import streamlit as st

from cv_generator.models import TailoredCV, TailoredExperience
from cv_generator.ui.state import ss_get


def render_preview_tab() -> None:
    st.header("Podgląd i edycja CV")
    cv: TailoredCV | None = ss_get("tailored")
    if not cv:
        st.info("Najpierw uruchom generowanie w zakładce 'Generuj'.")
        return

    cv.headline = st.text_input("Headline", value=cv.headline, key="prv_headline")
    cv.summary = st.text_area("Podsumowanie", value=cv.summary, height=120, key="prv_summary")

    st.subheader("Doświadczenie (możesz edytować bullety przed eksportem)")
    updated_experiences: list[TailoredExperience] = []
    for idx, exp in enumerate(cv.experiences):
        with st.expander(f"{exp.title} — {exp.company}", expanded=False):
            exp.title = st.text_input("Tytuł", value=exp.title, key=f"prv_title_{idx}")
            exp.company = st.text_input("Firma", value=exp.company, key=f"prv_company_{idx}")
            exp.date_range = st.text_input("Okres", value=exp.date_range, key=f"prv_dates_{idx}")
            bullets_str = st.text_area(
                "Bullety", value="\n".join(exp.bullets), height=140, key=f"prv_bullets_{idx}"
            )
            exp.bullets = [b.strip() for b in bullets_str.splitlines() if b.strip()]
        updated_experiences.append(exp)
    cv.experiences = updated_experiences

    cv.skills = [
        s.strip()
        for s in st.text_area(
            "Umiejętności (po przecinku)", value=", ".join(cv.skills), key="prv_skills"
        ).split(",")
        if s.strip()
    ]

    st.metric("Match score", f"{cv.match_score}/100")
    if cv.matched_keywords:
        st.success("Dopasowane: " + ", ".join(cv.matched_keywords))
    if cv.missing_keywords:
        st.warning("Brakuje: " + ", ".join(cv.missing_keywords))

    st.session_state.tailored = cv
