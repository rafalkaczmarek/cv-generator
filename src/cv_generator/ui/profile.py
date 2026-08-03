"""Profile tab: form, save/load, and orchestration."""

from __future__ import annotations

from typing import Any

import streamlit as st
from pydantic import ValidationError

from cv_generator.models import Profile
from cv_generator.ui.profile_editors import (
    education_editor,
    experiences_editor,
)
from cv_generator.ui.profile_import import (
    render_import_conflicts,
    render_linkedin_import,
    render_linkedin_url_import,
    set_profile_in_session,
    sync_profile_form_state,
)
from cv_generator.ui.state import ss_get, storage


def profile_form_inputs(profile: Profile | None) -> dict[str, Any]:
    # Wartości widgetów z `key` muszą pochodzić wyłącznie z session_state
    # (patrz `sync_profile_form_state`) — nie podawać jednocześnie `value=`.
    if "prof_full_name" not in st.session_state:
        sync_profile_form_state(profile)

    col1, col2 = st.columns(2)
    with col1:
        full_name = st.text_input("Imię i nazwisko", key="prof_full_name")
        headline = st.text_input("Headline", key="prof_headline")
        email = st.text_input("Email", key="prof_email")
        phone = st.text_input("Telefon", key="prof_phone")
    with col2:
        location = st.text_input("Lokalizacja", key="prof_location")
        linkedin_url = st.text_input("LinkedIn URL", key="prof_linkedin")
        github_url = st.text_input("GitHub URL", key="prof_github")
        website_url = st.text_input("Strona WWW", key="prof_website")

    summary = st.text_area("Krótkie podsumowanie", height=120, key="prof_summary")
    skills = st.text_area(
        "Umiejętności (oddzielone przecinkami)", height=80, key="prof_skills"
    )
    languages = st.text_area(
        "Języki (oddzielone przecinkami, np. 'Polski - natywny, Angielski - C1')",
        height=60,
        key="prof_languages",
    )

    return {
        "full_name": full_name,
        "headline": headline or None,
        "email": email or None,
        "phone": phone or None,
        "location": location or None,
        "linkedin_url": linkedin_url or None,
        "github_url": github_url or None,
        "website_url": website_url or None,
        "summary": summary or None,
        "skills": skills,
        "languages": languages,
    }


def render_profile_tab() -> None:
    st.header("Profil kandydata")
    st.caption(
        "Dane profilu uzupełniasz ręcznie, importujesz z publicznego URL LinkedIn "
        "lub z oficjalnego eksportu LinkedIn (ZIP/CSV)."
    )

    render_linkedin_url_import()
    render_linkedin_import()
    render_import_conflicts()

    store = storage()
    existing = store.list_profiles()
    selected_name = st.selectbox(
        "Wczytaj zapisany profil",
        options=["(nowy profil)"] + existing,
        index=0,
        key="profile_picker",
    )

    if selected_name != "(nowy profil)" and st.button("Wczytaj"):
        loaded = store.load_profile(selected_name)
        if loaded:
            set_profile_in_session(loaded)
            st.success(f"Wczytano profil: {selected_name}")
            st.rerun()

    profile_state: Profile | None = ss_get("profile")
    fields = profile_form_inputs(profile_state)
    experiences = experiences_editor(profile_state)
    education = education_editor(profile_state)

    c1, c2 = st.columns([1, 1])
    with c1:
        if st.button("Zapisz profil w bazie lokalnej", type="primary"):
            try:
                profile = Profile(
                    **fields,
                    experiences=experiences,
                    education=education,
                )
            except ValidationError as ve:
                st.error(f"Profil ma błędy: {ve}")
            else:
                store.save_profile(profile)
                st.session_state.profile = profile
                st.success(f"Zapisano profil dla: {profile.full_name}")
    with c2:
        if st.button("Tylko ustaw w sesji (bez zapisu)"):
            try:
                st.session_state.profile = Profile(
                    **fields,
                    experiences=experiences,
                    education=education,
                )
                st.success("Profil ustawiony.")
            except ValidationError as ve:
                st.error(f"Profil ma błędy: {ve}")
