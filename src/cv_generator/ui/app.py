"""Streamlit UI for the CV generator.

Tabs:
1. Profil — formularz danych kandydata (z możliwością zapisu/wczytania)
2. Oferta — URL lub wklejony tekst oferty, analiza przez LLM
3. Generuj — uruchomienie pipeline'u LangGraph
4. Podgląd i edycja — human-in-the-loop, ostatnia korekta przed eksportem
5. Eksport — zapis do DOCX i historia poprzednich generacji
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import streamlit as st
from pydantic import ValidationError

from cv_generator.agents.job_analyzer import JobFetchError, analyze_job
from cv_generator.graph.pipeline import generate_cv
from cv_generator.models import (
    Certification,
    Education,
    Experience,
    JobOffer,
    Profile,
    TailoredCV,
    TailoredExperience,
)
from cv_generator.services.docx_generator import render_cv
from cv_generator.services.linkedin_import import (
    LinkedInImportError,
    profile_from_linkedin_csv,
    profile_from_linkedin_zip,
)
from cv_generator.services.storage import Storage

st.set_page_config(page_title="CV Generator", page_icon=":briefcase:", layout="wide")

# …/src/cv_generator/ui/app.py → parents[3] is the project root.
_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


def _llm_provider_label(settings: Any) -> str:
    if settings.llm_provider == "openai":
        return f"OpenAI ({settings.openai_model})"
    if settings.llm_provider == "github":
        return f"GitHub Models ({settings.github_model})"
    if settings.llm_provider == "anthropic":
        return f"Anthropic ({settings.anthropic_model})"
    return settings.llm_provider


def _format_llm_error(exc: Exception) -> str:
    from cv_generator.config import get_settings

    settings = get_settings()
    provider = _llm_provider_label(settings)
    message = str(exc)
    if "invalid_api_key" in message or "Incorrect API key" in message:
        return (
            f"Aktywny provider: **{provider}**.\n\n"
            "Wygląda na to, że zapytanie trafiło do OpenAI z placeholderem `sk-...`. "
            "Najczęstsze przyczyny:\n"
            "- w `.env` zostawiono `OPENAI_API_KEY=sk-...` przy `LLM_PROVIDER=github` "
            "(usuń tę linię lub zostaw pustą)\n"
            "- terminal/IDE wstrzykuje `OPENAI_API_KEY` do środowiska procesu\n\n"
            "Sprawdź plik `.env` w katalogu projektu:\n"
            "- **GitHub Models**: `LLM_PROVIDER=github` i `GITHUB_TOKEN` z `models:read`\n"
            "- **OpenAI**: `LLM_PROVIDER=openai` i prawdziwy `OPENAI_API_KEY`\n\n"
            f"Szczegóły: {message}"
        )
    if "no_access" in message and "model" in message.lower():
        return (
            "Brak dostępu do modelu na GitHub Models. Token musi mieć uprawnienie **models:read** "
            "(fine-grained PAT → Permissions → Models → Read). "
            "Możesz też sprawdzić dostęp w https://github.com/marketplace/models.\n\n"
            f"Szczegóły: {message}"
        )
    return message


def _render_llm_sidebar() -> None:
    import os

    from cv_generator.config import get_settings

    settings = get_settings()
    with st.sidebar:
        st.subheader("LLM")
        st.caption(_llm_provider_label(settings))
        st.caption(f"Konfiguracja: `{_ENV_FILE}`")
        env_provider = os.environ.get("LLM_PROVIDER")
        if env_provider and env_provider != settings.llm_provider:
            st.warning(
                f"Środowisko procesu ma `LLM_PROVIDER={env_provider}`, "
                f"ale używany jest `{settings.llm_provider}` z `.env`."
            )
        if settings.llm_provider != "openai" and os.environ.get("OPENAI_API_KEY"):
            st.warning("Wykryto OPENAI_API_KEY w środowisku procesu — może powodować błędy.")
        st.caption("Po zmianie `.env` odśwież stronę w przeglądarce.")


def _storage() -> Storage:
    if "storage" not in st.session_state:
        st.session_state.storage = Storage()
    return st.session_state.storage


def _ss_get(key: str, default: Any = None) -> Any:
    return st.session_state.get(key, default)


def _sync_profile_form_state(profile: Profile | None) -> None:
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


def _profile_form_inputs(profile: Profile | None) -> dict[str, Any]:
    col1, col2 = st.columns(2)
    with col1:
        full_name = st.text_input(
            "Imię i nazwisko", value=profile.full_name if profile else "", key="prof_full_name"
        )
        headline = st.text_input(
            "Headline", value=profile.headline or "" if profile else "", key="prof_headline"
        )
        email = st.text_input(
            "Email", value=str(profile.email) if profile and profile.email else "", key="prof_email"
        )
        phone = st.text_input(
            "Telefon", value=profile.phone or "" if profile else "", key="prof_phone"
        )
    with col2:
        location = st.text_input(
            "Lokalizacja", value=profile.location or "" if profile else "", key="prof_location"
        )
        linkedin_url = st.text_input(
            "LinkedIn URL",
            value=str(profile.linkedin_url) if profile and profile.linkedin_url else "",
            key="prof_linkedin",
        )
        github_url = st.text_input(
            "GitHub URL",
            value=str(profile.github_url) if profile and profile.github_url else "",
            key="prof_github",
        )
        website_url = st.text_input(
            "Strona WWW",
            value=str(profile.website_url) if profile and profile.website_url else "",
            key="prof_website",
        )

    summary = st.text_area(
        "Krótkie podsumowanie",
        value=profile.summary or "" if profile else "",
        height=120,
        key="prof_summary",
    )

    skills_default = ", ".join(profile.skills) if profile else ""
    skills = st.text_area(
        "Umiejętności (oddzielone przecinkami)", value=skills_default, height=80, key="prof_skills"
    )
    languages_default = ", ".join(profile.languages) if profile else ""
    languages = st.text_area(
        "Języki (oddzielone przecinkami, np. 'Polski - natywny, Angielski - C1')",
        value=languages_default,
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


def _experiences_editor(profile: Profile | None) -> list[Experience]:
    st.subheader("Doświadczenie zawodowe")
    current: list[dict[str, Any]] = (
        [json.loads(e.model_dump_json()) for e in profile.experiences] if profile else []
    )
    if "experiences_buffer" not in st.session_state:
        st.session_state.experiences_buffer = current

    if st.button("Dodaj doświadczenie", key="add_exp"):
        st.session_state.experiences_buffer.append(
            {
                "company": "",
                "title": "",
                "location": "",
                "start_date": str(date.today()),
                "end_date": None,
                "is_current": True,
                "summary": "",
                "bullets": [],
                "technologies": [],
            }
        )

    keep: list[Experience] = []
    for idx, exp in enumerate(list(st.session_state.experiences_buffer)):
        with st.expander(f"#{idx + 1} {exp.get('title') or 'nowa pozycja'} @ {exp.get('company') or '...'}", expanded=False):
            c1, c2 = st.columns(2)
            with c1:
                exp["company"] = st.text_input("Firma", value=exp.get("company", ""), key=f"exp_company_{idx}")
                exp["title"] = st.text_input("Stanowisko", value=exp.get("title", ""), key=f"exp_title_{idx}")
                exp["location"] = st.text_input(
                    "Lokalizacja", value=exp.get("location") or "", key=f"exp_loc_{idx}"
                )
            with c2:
                start_raw = exp.get("start_date") or str(date.today())
                end_raw = exp.get("end_date")
                start_value = date.fromisoformat(start_raw) if isinstance(start_raw, str) else start_raw
                exp["start_date"] = str(
                    st.date_input("Data rozpoczęcia", value=start_value, key=f"exp_start_{idx}")
                )
                exp["is_current"] = st.checkbox(
                    "Obecnie", value=bool(exp.get("is_current")), key=f"exp_curr_{idx}"
                )
                if not exp["is_current"]:
                    end_value = date.fromisoformat(end_raw) if isinstance(end_raw, str) and end_raw else date.today()
                    exp["end_date"] = str(
                        st.date_input("Data zakończenia", value=end_value, key=f"exp_end_{idx}")
                    )
                else:
                    exp["end_date"] = None

            exp["summary"] = st.text_area(
                "Krótki opis roli (opcjonalnie)",
                value=exp.get("summary") or "",
                key=f"exp_sum_{idx}",
                height=80,
            )
            bullets_str = st.text_area(
                "Bullet points (jeden na linię)",
                value="\n".join(exp.get("bullets") or []),
                key=f"exp_bullets_{idx}",
                height=120,
            )
            exp["bullets"] = [b.strip() for b in bullets_str.splitlines() if b.strip()]

            techs_str = st.text_input(
                "Technologie (po przecinku)",
                value=", ".join(exp.get("technologies") or []),
                key=f"exp_techs_{idx}",
            )
            exp["technologies"] = [t.strip() for t in techs_str.split(",") if t.strip()]

            if st.button("Usuń tę pozycję", key=f"exp_del_{idx}"):
                continue

            try:
                keep.append(Experience.model_validate(exp))
            except ValidationError as ve:
                st.error(f"Pozycja #{idx + 1} ma błędne dane: {ve}")

    st.session_state.experiences_buffer = [json.loads(e.model_dump_json()) for e in keep]
    return keep


def _education_editor(profile: Profile | None) -> list[Education]:
    st.subheader("Wykształcenie")
    current: list[dict[str, Any]] = (
        [json.loads(e.model_dump_json()) for e in profile.education] if profile else []
    )
    if "edu_buffer" not in st.session_state:
        st.session_state.edu_buffer = current

    if st.button("Dodaj wykształcenie", key="add_edu"):
        st.session_state.edu_buffer.append(
            {"institution": "", "degree": "", "field_of_study": "", "start_date": None, "end_date": None}
        )

    keep: list[Education] = []
    for idx, edu in enumerate(list(st.session_state.edu_buffer)):
        with st.expander(f"#{idx + 1} {edu.get('institution') or 'nowa pozycja'}", expanded=False):
            edu["institution"] = st.text_input(
                "Uczelnia / szkoła", value=edu.get("institution", ""), key=f"edu_inst_{idx}"
            )
            c1, c2 = st.columns(2)
            with c1:
                edu["degree"] = st.text_input(
                    "Stopień / tytuł", value=edu.get("degree") or "", key=f"edu_deg_{idx}"
                )
            with c2:
                edu["field_of_study"] = st.text_input(
                    "Kierunek", value=edu.get("field_of_study") or "", key=f"edu_field_{idx}"
                )

            edu["description"] = st.text_area(
                "Opis (opcjonalnie)",
                value=edu.get("description") or "",
                key=f"edu_desc_{idx}",
                height=60,
            )

            if st.button("Usuń tę pozycję", key=f"edu_del_{idx}"):
                continue
            try:
                keep.append(Education.model_validate(edu))
            except ValidationError as ve:
                st.error(f"Wykształcenie #{idx + 1} ma błędne dane: {ve}")

    st.session_state.edu_buffer = [json.loads(e.model_dump_json()) for e in keep]
    return keep


def _certifications_editor(profile: Profile | None) -> list[Certification]:
    st.subheader("Certyfikaty")
    current: list[dict[str, Any]] = (
        [json.loads(c.model_dump_json()) for c in profile.certifications] if profile else []
    )
    if "cert_buffer" not in st.session_state:
        st.session_state.cert_buffer = current

    if st.button("Dodaj certyfikat", key="add_cert"):
        st.session_state.cert_buffer.append({"name": "", "issuer": "", "issued": None, "url": None})

    keep: list[Certification] = []
    for idx, cert in enumerate(list(st.session_state.cert_buffer)):
        with st.expander(f"#{idx + 1} {cert.get('name') or 'nowy certyfikat'}", expanded=False):
            cert["name"] = st.text_input("Nazwa", value=cert.get("name", ""), key=f"cert_name_{idx}")
            cert["issuer"] = st.text_input(
                "Wystawca", value=cert.get("issuer") or "", key=f"cert_issuer_{idx}"
            )
            cert["url"] = st.text_input("Link", value=cert.get("url") or "", key=f"cert_url_{idx}") or None

            if st.button("Usuń", key=f"cert_del_{idx}"):
                continue
            try:
                keep.append(Certification.model_validate(cert))
            except ValidationError as ve:
                st.error(f"Certyfikat #{idx + 1} ma błędne dane: {ve}")

    st.session_state.cert_buffer = [json.loads(c.model_dump_json()) for c in keep]
    return keep


def _render_linkedin_import() -> None:
    with st.expander("Importuj z eksportu LinkedIn", expanded=False):
        st.caption(
            "Wejdź na LinkedIn → Ustawienia → Prywatność danych → "
            "*Pobierz kopię swoich danych* i wgraj otrzymane archiwum ZIP "
            "(albo pojedynczy plik CSV, np. `Positions.csv`). "
            "Dane uzupełnią formularz — przejrzyj je przed zapisem."
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
                st.session_state.profile = profile
                for k in ("experiences_buffer", "edu_buffer", "cert_buffer"):
                    st.session_state.pop(k, None)
                _sync_profile_form_state(profile)
                st.success(
                    f"Zaimportowano dane LinkedIn: {profile.full_name} "
                    f"({len(profile.experiences)} doświadczeń, "
                    f"{len(profile.education)} wpisów wykształcenia, "
                    f"{len(profile.skills)} umiejętności). "
                    "Sprawdź i uzupełnij pola, a następnie zapisz profil."
                )
                st.rerun()


def _render_profile_tab() -> None:
    st.header("Profil kandydata")
    st.caption(
        "URL profilu LinkedIn służy jako referencja w wygenerowanym CV. "
        "Dane uzupełniasz ręcznie lub importujesz z eksportu LinkedIn."
    )

    _render_linkedin_import()

    storage = _storage()
    existing = storage.list_profiles()
    selected_name = st.selectbox(
        "Wczytaj zapisany profil",
        options=["(nowy profil)"] + existing,
        index=0,
        key="profile_picker",
    )

    loaded: Profile | None = None
    if selected_name != "(nowy profil)" and st.button("Wczytaj"):
        loaded = storage.load_profile(selected_name)
        if loaded:
            st.session_state.profile = loaded
            for k in ("experiences_buffer", "edu_buffer", "cert_buffer"):
                st.session_state.pop(k, None)
            _sync_profile_form_state(loaded)
            st.success(f"Wczytano profil: {selected_name}")
            st.rerun()

    profile_state: Profile | None = _ss_get("profile")
    fields = _profile_form_inputs(profile_state)
    experiences = _experiences_editor(profile_state)
    education = _education_editor(profile_state)
    certifications = _certifications_editor(profile_state)

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
                storage.save_profile(profile)
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


def _render_job_tab() -> None:
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
                    _storage().save_job_offer(offer)
                    st.success(f"Oferta przeanalizowana: {offer.title} @ {offer.company}")
                except (JobFetchError, ValueError) as exc:
                    st.error(f"Nie udało się pobrać oferty: {exc}")
                except Exception as exc:  # pragma: no cover - LLM/network errors
                    st.error(_format_llm_error(exc))

    offer: JobOffer | None = _ss_get("job_offer")
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


def _render_generate_tab() -> None:
    st.header("Generowanie CV")
    profile = _ss_get("profile")
    offer = _ss_get("job_offer")

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
                st.error(_format_llm_error(exc))


def _render_preview_tab() -> None:
    st.header("Podgląd i edycja CV")
    cv: TailoredCV | None = _ss_get("tailored")
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


def _render_export_tab() -> None:
    st.header("Eksport i historia")
    cv: TailoredCV | None = _ss_get("tailored")
    offer: JobOffer | None = _ss_get("job_offer")
    profile: Profile | None = _ss_get("profile")

    if cv and st.button("Zapisz jako DOCX", type="primary"):
        try:
            filename = None
            if offer:
                stamp_slug = offer.slug()
                filename = f"cv_{stamp_slug}.docx"
            path = render_cv(cv, filename=filename)
            if profile and offer:
                _storage().record_generated_cv(
                    profile_name=profile.full_name,
                    job_slug=offer.slug(),
                    file_path=path,
                    cv=cv,
                )
            st.success(f"Zapisano: {path}")
            with open(path, "rb") as fh:
                st.download_button(
                    "Pobierz plik",
                    data=fh.read(),
                    file_name=path.name,
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
        except Exception as exc:  # pragma: no cover - filesystem/template errors
            st.error(f"Nie udało się zapisać DOCX: {exc}")

    st.subheader("Historia wygenerowanych CV")
    rows = _storage().list_generated_cvs()
    if not rows:
        st.caption("Brak wpisów.")
    else:
        for r in rows:
            st.write(
                f"`{r['created_at']}` — **{r['profile_name']}** → {r['job_slug']} "
                f"(score {r['match_score']}) — {r['file_path']}"
            )


def main() -> None:
    _render_llm_sidebar()
    st.title("CV Generator")
    st.caption("AI-powered, dopasowane do konkretnej oferty pracy.")

    tabs = st.tabs(["Profil", "Oferta", "Generuj", "Podgląd", "Eksport"])
    with tabs[0]:
        _render_profile_tab()
    with tabs[1]:
        _render_job_tab()
    with tabs[2]:
        _render_generate_tab()
    with tabs[3]:
        _render_preview_tab()
    with tabs[4]:
        _render_export_tab()


main()
