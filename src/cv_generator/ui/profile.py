"""Profile tab: form, LinkedIn import, save/load."""

from __future__ import annotations

from typing import Any

import streamlit as st
from pydantic import ValidationError

from cv_generator.models import Certification, Education, Experience, Profile
from cv_generator.services.linkedin_import import (
    LinkedInImportError,
    profile_from_linkedin_csv,
    profile_from_linkedin_zip,
)
from cv_generator.services.linkedin_url_import import (
    LinkedInUrlImportError,
    profile_from_linkedin_url,
)
from cv_generator.services.profile_merge import (
    Choice,
    FieldConflict,
    apply_conflict_resolutions,
    highlight_text_diff,
    merge_profiles_with_conflicts,
)
from cv_generator.ui.profile_editors import (
    certifications_editor,
    education_editor,
    experiences_editor,
)
from cv_generator.ui.state import ss_get, storage, strip_entry_id


def sync_profile_form_state(profile: Profile | None) -> None:
    """Ustawia wartości widgetów formularza — przy `key` Streamlit ignoruje `value`."""
    st.session_state.prof_full_name = profile.full_name if profile else ""
    st.session_state.prof_headline = profile.headline or "" if profile else ""
    st.session_state.prof_email = str(profile.email) if profile and profile.email else ""
    st.session_state.prof_phone = profile.phone or "" if profile else ""
    st.session_state.prof_location = profile.location or "" if profile else ""
    st.session_state.prof_linkedin = (
        str(profile.linkedin_url) if profile and profile.linkedin_url else ""
    )
    st.session_state.prof_github = str(profile.github_url) if profile and profile.github_url else ""
    st.session_state.prof_website = (
        str(profile.website_url) if profile and profile.website_url else ""
    )
    st.session_state.prof_summary = profile.summary or "" if profile else ""
    st.session_state.prof_skills = ", ".join(profile.skills) if profile else ""
    st.session_state.prof_languages = ", ".join(profile.languages) if profile else ""


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


def profile_from_session_state() -> Profile | None:
    """Best-effort snapshot of the form before an import overwrites widget state."""
    if "prof_full_name" not in st.session_state:
        return ss_get("profile")

    experiences: list[Experience] = []
    for raw in st.session_state.get("experiences_buffer", []):
        try:
            experiences.append(Experience.model_validate(strip_entry_id(raw)))
        except ValidationError:
            continue

    education: list[Education] = []
    for raw in st.session_state.get("edu_buffer", []):
        try:
            education.append(Education.model_validate(strip_entry_id(raw)))
        except ValidationError:
            continue

    certifications: list[Certification] = []
    for raw in st.session_state.get("cert_buffer", []):
        try:
            certifications.append(Certification.model_validate(strip_entry_id(raw)))
        except ValidationError:
            continue

    full_name = st.session_state.get("prof_full_name", "").strip()
    if not full_name and not experiences and not education:
        return ss_get("profile")

    try:
        return Profile(
            full_name=full_name or "—",
            headline=st.session_state.get("prof_headline") or None,
            summary=st.session_state.get("prof_summary") or None,
            email=st.session_state.get("prof_email") or None,
            phone=st.session_state.get("prof_phone") or None,
            location=st.session_state.get("prof_location") or None,
            linkedin_url=st.session_state.get("prof_linkedin") or None,
            github_url=st.session_state.get("prof_github") or None,
            website_url=st.session_state.get("prof_website") or None,
            skills=st.session_state.get("prof_skills", ""),
            languages=st.session_state.get("prof_languages", ""),
            experiences=experiences,
            education=education,
            certifications=certifications,
        )
    except ValidationError:
        return ss_get("profile")


def _set_profile_in_session(profile: Profile) -> None:
    st.session_state.profile = profile
    for k in ("experiences_buffer", "edu_buffer", "cert_buffer"):
        st.session_state.pop(k, None)
    sync_profile_form_state(profile)


def apply_imported_profile(
    profile: Profile,
    *,
    source: str,
    merge: bool = True,
) -> None:
    conflicts: list[FieldConflict] = []
    if merge:
        result = merge_profiles_with_conflicts(profile_from_session_state(), profile)
        profile = result.profile
        conflicts = result.conflicts
    _set_profile_in_session(profile)

    if conflicts:
        st.session_state.profile_import_conflicts = [
            {
                "field": c.field,
                "label": c.label,
                "current": c.current,
                "incoming": c.incoming,
            }
            for c in conflicts
        ]
        st.session_state.profile_import_source = source
        st.warning(
            f"Uzupełniono brakujące pola z ({source}). "
            f"Wykryto {len(conflicts)} konflikt(ów) — wybierz, którą wartość zachować."
        )
    else:
        st.session_state.pop("profile_import_conflicts", None)
        st.session_state.pop("profile_import_source", None)
        verb = "Uzupełniono" if merge else "Zaimportowano"
        st.success(
            f"{verb} dane ({source}): {profile.full_name} "
            f"({len(profile.experiences)} doświadczeń, "
            f"{len(profile.education)} wpisów wykształcenia, "
            f"{len(profile.skills)} umiejętności). "
            "Sprawdź i uzupełnij pola, a następnie zapisz profil."
        )
    st.rerun()


def render_import_conflicts() -> None:
    raw_conflicts = st.session_state.get("profile_import_conflicts")
    if not raw_conflicts:
        return

    conflicts = [
        FieldConflict(
            field=item["field"],
            label=item["label"],
            current=item["current"],
            incoming=item["incoming"],
        )
        for item in raw_conflicts
    ]
    source = st.session_state.get("profile_import_source", "import")

    with st.expander(
        f"Konflikty importu ({len(conflicts)}) — wybierz wartości",
        expanded=True,
    ):
        st.caption(
            f"Poniższe pola mają różne wartości w formularzu i w danych z ({source}). "
            "Różnice są podświetlone; wybierz wersję, którą chcesz zachować."
        )
        choices: dict[str, Choice] = {}
        for conflict in conflicts:
            st.markdown(f"**{conflict.label}**")
            left_html, right_html = highlight_text_diff(conflict.current, conflict.incoming)
            col_a, col_b = st.columns(2)
            with col_a:
                st.caption("Aktualne w formularzu")
                st.markdown(
                    f'<div style="padding:0.5rem;border:1px solid #ddd;'
                    f'border-radius:4px;white-space:pre-wrap">{left_html}</div>',
                    unsafe_allow_html=True,
                )
            with col_b:
                st.caption(f"Z ({source})")
                st.markdown(
                    f'<div style="padding:0.5rem;border:1px solid #ddd;'
                    f'border-radius:4px;white-space:pre-wrap">{right_html}</div>',
                    unsafe_allow_html=True,
                )
            choice = st.radio(
                f"Wybór dla: {conflict.label}",
                options=["current", "incoming"],
                format_func=lambda v, label=conflict.label: (
                    f"Zachowaj aktualne — {label}"
                    if v == "current"
                    else f"Użyj z ({source}) — {label}"
                ),
                key=f"conflict_choice_{conflict.field}",
                horizontal=True,
                label_visibility="collapsed",
            )
            choices[conflict.field] = choice  # type: ignore[assignment]
            st.divider()

        c1, c2 = st.columns(2)
        with c1:
            if st.button("Zastosuj wybrane wartości", type="primary", key="apply_conflicts"):
                profile = ss_get("profile") or profile_from_session_state()
                if profile is None:
                    st.error("Brak profilu do aktualizacji.")
                else:
                    resolved = apply_conflict_resolutions(profile, conflicts, choices)
                    _set_profile_in_session(resolved)
                    st.session_state.pop("profile_import_conflicts", None)
                    st.session_state.pop("profile_import_source", None)
                    for conflict in conflicts:
                        st.session_state.pop(f"conflict_choice_{conflict.field}", None)
                    st.success("Zastosowano wybrane wartości konfliktów.")
                    st.rerun()
        with c2:
            if st.button("Pomiń konflikty (zostaw aktualne)", key="skip_conflicts"):
                st.session_state.pop("profile_import_conflicts", None)
                st.session_state.pop("profile_import_source", None)
                for conflict in conflicts:
                    st.session_state.pop(f"conflict_choice_{conflict.field}", None)
                st.info("Pozostawiono aktualne wartości w konfliktujących polach.")
                st.rerun()


def render_linkedin_url_import() -> None:
    with st.expander("Importuj z URL profilu LinkedIn", expanded=False):
        st.caption(
            "Wklej publiczny adres profilu LinkedIn (`linkedin.com/in/...`). "
            "Aplikacja uzupełni brakujące pola formularza — istniejące dane "
            "nie zostaną nadpisane. Przy konfliktach pokażemy obie wersje "
            "do wyboru. Doświadczenie pobierane jest z podstrony "
            "projektów (`/details/projects/`), bo główny profil często maskuje "
            "historię zatrudnienia gwiazdkami."
        )
        url = st.text_input(
            "URL profilu LinkedIn",
            placeholder="https://www.linkedin.com/in/twoj-profil/",
            key="linkedin_url_input",
        )
        if url and st.button("Pobierz dane z URL", key="linkedin_url_import_btn"):
            try:
                profile = profile_from_linkedin_url(url)
            except LinkedInUrlImportError as exc:
                st.error(str(exc))
            except Exception as exc:  # pragma: no cover - defensive
                st.error(f"Nie udało się zaimportować danych: {exc}")
            else:
                apply_imported_profile(profile, source="URL LinkedIn")


def render_linkedin_import() -> None:
    with st.expander("Importuj z eksportu LinkedIn", expanded=False):
        st.caption(
            "Wejdź na LinkedIn → Ustawienia → Prywatność danych → "
            "*Pobierz kopię swoich danych* i wgraj otrzymane archiwum ZIP "
            "(albo pojedynczy plik CSV, np. `Positions.csv`). "
            "Brakujące pola zostaną uzupełnione; przy konfliktach wybierzesz "
            "wartość ręcznie."
        )
        upload = st.file_uploader(
            "Plik ZIP lub CSV z LinkedIn",
            type=["zip", "csv"],
            key="linkedin_upload",
        )
        if upload is not None and st.button("Wczytaj dane z LinkedIn", key="linkedin_import_btn"):
            try:
                data = upload.getvalue()
                if upload.name.lower().endswith(".zip"):
                    profile = profile_from_linkedin_zip(data)
                else:
                    profile = profile_from_linkedin_csv(upload.name, data)
            except LinkedInImportError as exc:
                st.error(str(exc))
            except Exception as exc:  # pragma: no cover - defensive
                st.error(f"Nie udało się zaimportować danych: {exc}")
            else:
                apply_imported_profile(profile, source="eksport LinkedIn")


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
            st.session_state.profile = loaded
            for k in ("experiences_buffer", "edu_buffer", "cert_buffer"):
                st.session_state.pop(k, None)
            sync_profile_form_state(loaded)
            st.success(f"Wczytano profil: {selected_name}")
            st.rerun()

    profile_state: Profile | None = ss_get("profile")
    fields = profile_form_inputs(profile_state)
    experiences = experiences_editor(profile_state)
    education = education_editor(profile_state)
    certifications = certifications_editor(profile_state)

    c1, c2 = st.columns([1, 1])
    with c1:
        if st.button("Zapisz profil w bazie lokalnej", type="primary"):
            try:
                profile = Profile(
                    **fields,
                    experiences=experiences,
                    education=education,
                    certifications=certifications,
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
                    certifications=certifications,
                )
                st.success("Profil ustawiony.")
            except ValidationError as ve:
                st.error(f"Profil ma błędy: {ve}")
