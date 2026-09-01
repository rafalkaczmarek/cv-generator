"""Export and generation history tab."""

from __future__ import annotations

import logging
from pathlib import Path

import streamlit as st

from cv_generator.config import get_settings
from cv_generator.models import JobOffer, Profile, TailoredCV
from cv_generator.services.docx_generator import list_templates, render_cv
from cv_generator.ui.google_export import (
    document_name_for_cv,
    render_send_to_google_docs_button,
)
from cv_generator.ui.state import ss_get, storage

logger = logging.getLogger(__name__)

_LAST_EXPORT_KEY = "last_export_artifacts"


def _lang_suffix(cv: TailoredCV) -> str:
    return "pl" if str(cv.language or "en").lower().startswith("pl") else "en"


def _export_one(
    cv: TailoredCV,
    *,
    offer: JobOffer | None,
    profile: Profile | None,
    template_id: str | None,
) -> Path:
    filename = None
    if offer:
        filename = f"cv_{offer.slug()}_{_lang_suffix(cv)}.docx"
    path = render_cv(cv, template_id=template_id, filename=filename, language=cv.language)
    if profile and offer:
        storage().record_generated_cv(
            profile_name=profile.full_name,
            job_slug=offer.slug(),
            file_path=path,
            cv=cv,
        )
    return path


def _build_export_artifacts(
    paths: list[tuple[str, Path]],
    *,
    cv: TailoredCV,
    cv_pl: TailoredCV | None,
    offer: JobOffer | None,
) -> list[dict[str, str]]:
    company = offer.company if offer else None
    artifacts: list[dict[str, str]] = []
    for label, path in paths:
        source_cv = cv_pl if label == "Polski" and cv_pl else cv
        doc_name = document_name_for_cv(
            full_name=source_cv.full_name,
            company=company,
        )
        if label == "Polski":
            doc_name = f"{doc_name} (PL)"
        artifacts.append(
            {
                "label": label,
                "path": str(path),
                "document_name": doc_name,
            }
        )
    return artifacts


def _render_export_artifacts(artifacts: list[dict[str, str]]) -> None:
    for item in artifacts:
        path = Path(item["path"])
        label = item["label"]
        if not path.is_file():
            st.warning(f"Plik ({label}) nie istnieje już na dysku: {path.name}")
            continue
        st.success(f"Zapisano ({label}): {path}")
        cols = st.columns(2)
        with cols[0], open(path, "rb") as fh:
            st.download_button(
                f"Pobierz plik ({label})",
                data=fh.read(),
                file_name=path.name,
                mime=(
                    "application/vnd.openxmlformats-officedocument"
                    ".wordprocessingml.document"
                ),
                key=f"dl_{path.name}",
            )
        with cols[1]:
            render_send_to_google_docs_button(
                docx_path=path,
                document_name=item["document_name"],
                key=f"gdocs_{path.name}",
            )


def render_export_tab() -> None:
    st.header("Eksport i historia")
    cv: TailoredCV | None = ss_get("tailored")
    cv_pl: TailoredCV | None = ss_get("tailored_pl")
    offer: JobOffer | None = ss_get("job_offer")
    profile: Profile | None = ss_get("profile")

    templates = list_templates()
    template_labels = {
        t.id: f"{t.label} — {t.description}" if t.description else t.label for t in templates
    }
    selected_id = st.selectbox(
        "Szablon CV",
        options=[t.id for t in templates],
        format_func=lambda tid: template_labels.get(tid, tid),
        help=(
            "Wbudowane szablony Word albo własny plik `.docx` wrzucony do katalogu templates/. "
            "Wszystkie muszą używać placeholderów Jinja2 z kontekstem `cv.*`."
        ),
        disabled=not bool(templates),
    )

    if cv and st.button("Zapisz jako DOCX", type="primary"):
        try:
            paths: list[tuple[str, Path]] = []
            path_en = _export_one(
                cv, offer=offer, profile=profile, template_id=selected_id
            )
            paths.append(("English", path_en))
            if cv_pl:
                path_pl = _export_one(
                    cv_pl, offer=offer, profile=profile, template_id=selected_id
                )
                paths.append(("Polski", path_pl))
            st.session_state[_LAST_EXPORT_KEY] = _build_export_artifacts(
                paths, cv=cv, cv_pl=cv_pl, offer=offer
            )
        except Exception as exc:  # pragma: no cover - filesystem/template errors
            logger.exception("DOCX export failed")
            st.error(f"Nie udało się zapisać DOCX: {exc}")

    artifacts = ss_get(_LAST_EXPORT_KEY) or []
    if artifacts:
        _render_export_artifacts(artifacts)

    _render_google_docs_setup_help()
    _render_template_based_google_export(cv, offer)

    st.subheader("Historia wygenerowanych CV")
    rows = storage().list_generated_cvs()
    if not rows:
        st.caption("Brak wpisów.")
    else:
        for r in rows:
            st.write(
                f"`{r['created_at']}` — **{r['profile_name']}** → {r['job_slug']} "
                f"(score {r['match_score']}) — {r['file_path']}"
            )


def _render_google_docs_setup_help() -> None:
    settings = get_settings()
    with st.expander("Google Docs — konfiguracja"):
        st.markdown(
            "1. `pip install -e .[google]`\n"
            "2. Włącz Drive API (i opcjonalnie Docs API) w Google Cloud Console.\n"
            "3. Pobierz OAuth credentials → "
            f"`{settings.google_credentials_path}`.\n"
            "4. Po wygenerowaniu CV użyj **Wyślij do Google Docs** obok przycisku pobierania.\n"
            "5. Jeśli token wygasł (`invalid_grant`), usuń "
            f"`{settings.google_token_path}` i kliknij ponownie — otworzy się logowanie Google."
        )


def _render_template_based_google_export(
    cv: TailoredCV | None,
    offer: JobOffer | None,
) -> None:
    """Optional advanced flow: fill a Drive-native template via replaceAllText."""
    settings = get_settings()
    with st.expander("Google Docs — szablon Drive (opcjonalne)"):
        if not settings.google_drive_template_id:
            st.caption(
                "Ustaw `GOOGLE_DRIVE_TEMPLATE_ID` w `.env`, aby wypełniać szablon "
                "Google Docs z placeholderami `{{full_name}}`, `{{experiences}}`, …"
            )
            return
        if not cv:
            st.caption("Najpierw wygeneruj CV.")
            return
        if st.button("Wypełnij szablon Google Docs", key="gdocs_template_fill"):
            try:
                from cv_generator.services.google_docs import (
                    GoogleDocsUnavailable,
                    export_cv_to_drive,
                )

                doc_name = document_name_for_cv(
                    full_name=cv.full_name,
                    company=offer.company if offer else None,
                )
                result = export_cv_to_drive(cv, document_name=doc_name)
                link = result.get("web_view_link") or ""
                st.success("Utworzono dokument w Google Docs ze szablonu.")
                if link:
                    st.markdown(f"[Otwórz w Google Docs]({link})")
            except GoogleDocsUnavailable as exc:
                logger.warning("Google Docs extra unavailable: %s", exc)
                st.error(str(exc))
            except Exception as exc:  # pragma: no cover - OAuth / API errors
                logger.exception("Google Docs template export failed")
                st.error(f"Nie udało się wyeksportować do Google Docs: {exc}")
