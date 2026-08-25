"""LinkedIn import UI, conflict resolution, and profile form session sync."""

from __future__ import annotations

import streamlit as st
from pydantic import ValidationError

from cv_generator.models import Education, Experience, Profile
from cv_generator.services.linkedin_import import (
    LinkedInImportError,
    profile_from_linkedin_csv,
    profile_from_linkedin_zip,
)
from cv_generator.services.linkedin_url_import import (
    LinkedInUrlImportError,
    profile_from_linkedin_html,
    profile_from_linkedin_url,
)
from cv_generator.services.profile_merge import (
    Choice,
    FieldConflict,
    apply_conflict_resolutions,
    highlight_text_diff,
    merge_profiles_with_conflicts,
)
from cv_generator.ui.profile_editors import sync_education_buffer
from cv_generator.ui.state import ss_get, strip_entry_id


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
    st.session_state.prof_courses = ", ".join(profile.courses) if profile else ""
    st.session_state.prof_languages = ", ".join(profile.languages) if profile else ""


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
            courses=st.session_state.get("prof_courses", ""),
            languages=st.session_state.get("prof_languages", ""),
            experiences=experiences,
            education=education,
        )
    except ValidationError:
        return ss_get("profile")


def set_profile_in_session(profile: Profile) -> None:
    st.session_state.profile = profile
    st.session_state.pop("experiences_buffer", None)
    # Drop stale experience widget values so imported rows show up.
    for key in list(st.session_state.keys()):
        if key.startswith("exp_"):
            del st.session_state[key]
    sync_education_buffer(profile)
    sync_profile_form_state(profile)


def _education_import_summary(profile: Profile) -> str:
    if not profile.education:
        return "brak wpisów wykształcenia"
    parts: list[str] = []
    for edu in profile.education:
        title = ", ".join(
            p for p in ((edu.degree or "").strip(), (edu.field_of_study or "").strip()) if p
        )
        if title:
            parts.append(f"{edu.institution}: {title}")
        else:
            parts.append(f"{edu.institution}: (brak Degree Name / Field Of Study w pliku)")
    return "; ".join(parts)


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
    set_profile_in_session(profile)

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
            f"Wykryto {len(conflicts)} konflikt(ów) — wybierz, którą wartość zachować. "
            f"Wykształcenie: {_education_import_summary(profile)}."
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
            f"Wykształcenie: {_education_import_summary(profile)}. "
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
                    set_profile_in_session(resolved)
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
        st.info(
            "LinkedIn często blokuje automatyczne pobieranie (błąd 999). "
            "Wtedy zapisz stronę profilu w przeglądarce jako HTML i wgraj ją "
            "poniżej, albo użyj oficjalnego eksportu ZIP."
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

        st.markdown("**Alternatywa: wgraj HTML strony profilu**")
        st.caption(
            "W przeglądarce otwórz publiczny profil (oraz ewentualnie "
            "`…/details/projects/`), wybierz *Zapisz stronę jako…* / *Save as*, "
            "potem wgraj plik `.html`."
        )
        html_upload = st.file_uploader(
            "Plik HTML profilu LinkedIn",
            type=["html", "htm"],
            key="linkedin_html_upload",
        )
        if html_upload is not None and st.button(
            "Wczytaj dane z HTML", key="linkedin_html_import_btn"
        ):
            try:
                html_text = html_upload.getvalue().decode("utf-8", errors="replace")
                profile = profile_from_linkedin_html(
                    html_text,
                    source_url=url or None,
                )
            except LinkedInUrlImportError as exc:
                st.error(str(exc))
            except Exception as exc:  # pragma: no cover - defensive
                st.error(f"Nie udało się zaimportować HTML: {exc}")
            else:
                apply_imported_profile(profile, source="HTML LinkedIn")


def render_linkedin_import() -> None:
    with st.expander("Importuj z eksportu LinkedIn", expanded=False):
        st.caption(
            "Wejdź na LinkedIn → Ustawienia → Prywatność danych → "
            "*Pobierz kopię swoich danych* i wgraj otrzymane archiwum ZIP "
            "(albo pojedynczy plik CSV, np. `Positions.csv` / `Projects.csv`). "
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
