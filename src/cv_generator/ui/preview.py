"""Preview and human-in-the-loop edit tab."""

from __future__ import annotations

import streamlit as st

from cv_generator.agents.validator import validate
from cv_generator.models import JobOffer, Profile, TailoredCV, TailoredExperience
from cv_generator.ui.state import ss_get


def reevaluate_match_score(
    *,
    profile: Profile | None,
    job: JobOffer | None,
    cv: TailoredCV,
) -> tuple[TailoredCV | None, str | None]:
    """Recalculate match score for an edited CV. Returns ``(cv, error)``."""
    if profile is None:
        return None, "Brak profilu w sesji — nie można przeliczyć score."
    if job is None:
        return None, "Brak oferty w sesji — nie można przeliczyć score."
    _, _, updated = validate(profile=profile, job=job, cv=cv)
    return updated, None


def render_preview_tab() -> None:
    st.header("Podgląd i edycja CV")
    cv_en: TailoredCV | None = ss_get("tailored")
    cv_pl: TailoredCV | None = ss_get("tailored_pl")
    if not cv_en:
        st.info("Najpierw uruchom generowanie w zakładce 'Generuj'.")
        return

    if cv_pl:
        choice = st.radio(
            "Wersja językowa",
            options=["en", "pl"],
            format_func=lambda code: "English" if code == "en" else "Polski",
            horizontal=True,
            key="preview_language",
        )
        cv = cv_pl if choice == "pl" else cv_en
        session_key = "tailored_pl" if choice == "pl" else "tailored"
    else:
        cv = cv_en
        session_key = "tailored"

    cv.headline = st.text_input("Headline", value=cv.headline, key=f"prv_headline_{session_key}")
    cv.summary = st.text_area(
        "Podsumowanie", value=cv.summary, height=120, key=f"prv_summary_{session_key}"
    )

    st.subheader("Doświadczenie (możesz edytować bullety przed eksportem)")
    updated_experiences: list[TailoredExperience] = []
    for idx, exp in enumerate(cv.experiences):
        with st.expander(exp.heading, expanded=False):
            exp.title = st.text_input(
                "Tytuł", value=exp.title, key=f"prv_title_{session_key}_{idx}"
            )
            exp.company = st.text_input(
                "Firma", value=exp.company, key=f"prv_company_{session_key}_{idx}"
            )
            exp.date_range = st.text_input(
                "Okres", value=exp.date_range, key=f"prv_dates_{session_key}_{idx}"
            )
            bullets_str = st.text_area(
                "Bullety",
                value="\n".join(exp.bullets),
                height=140,
                key=f"prv_bullets_{session_key}_{idx}",
            )
            exp.bullets = [b.strip() for b in bullets_str.splitlines() if b.strip()]
        updated_experiences.append(exp)
    cv.experiences = updated_experiences

    cv.skills = [
        s.strip()
        for s in st.text_area(
            "Umiejętności (po przecinku)",
            value=", ".join(cv.skills),
            key=f"prv_skills_{session_key}",
        ).split(",")
        if s.strip()
    ]
    cv.courses = [
        s.strip()
        for s in st.text_area(
            "Kursy (po przecinku)",
            value=", ".join(cv.courses),
            key=f"prv_courses_{session_key}",
        ).split(",")
        if s.strip()
    ]

    st.metric("Match score", f"{cv.match_score}/100")
    if st.button("Reevaluate", key=f"prv_reevaluate_{session_key}"):
        updated, error = reevaluate_match_score(
            profile=ss_get("profile"),
            job=ss_get("job_offer"),
            cv=cv,
        )
        if error:
            st.error(error)
        else:
            assert updated is not None
            st.session_state[session_key] = updated
            st.rerun()

    if cv.matched_keywords:
        st.success("Dopasowane: " + ", ".join(cv.matched_keywords))
    if cv.missing_keywords:
        st.warning("Brakuje: " + ", ".join(cv.missing_keywords))

    st.session_state[session_key] = cv
