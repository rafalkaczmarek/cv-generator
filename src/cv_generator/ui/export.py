"""Export and generation history tab."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from cv_generator.config import get_settings
from cv_generator.models import JobOffer, Profile, TailoredCV
from cv_generator.services.docx_generator import list_templates, render_cv
from cv_generator.ui.state import ss_get, storage


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

            for label, path in paths:
                st.success(f"Zapisano ({label}): {path}")
                with open(path, "rb") as fh:
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
        except Exception as exc:  # pragma: no cover - filesystem/template errors
            st.error(f"Nie udało się zapisać DOCX: {exc}")

    _render_google_docs_export(cv, offer)

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


def _render_google_docs_export(
    cv: TailoredCV | None,
    offer: JobOffer | None,
) -> None:
    settings = get_settings()
    with st.expander("Google Docs (opcjonalne)"):
        if not settings.google_drive_template_id:
            st.caption(
                "Ustaw `GOOGLE_DRIVE_TEMPLATE_ID` w `.env` i zainstaluj "
                "`pip install -e .[google]`, aby eksportować do Drive."
            )
            return
        if not cv:
            st.caption("Najpierw wygeneruj CV.")
            return
        if st.button("Eksportuj do Google Docs"):
            try:
                from cv_generator.services.google_docs import (
                    GoogleDocsUnavailable,
                    export_cv_to_drive,
                )

                doc_name = f"CV — {cv.full_name}"
                if offer and offer.company:
                    doc_name = f"CV — {cv.full_name} — {offer.company}"
                result = export_cv_to_drive(cv, document_name=doc_name)
                link = result.get("web_view_link") or ""
                st.success("Utworzono dokument w Google Docs.")
                if link:
                    st.markdown(f"[Otwórz w Google Docs]({link})")
            except GoogleDocsUnavailable as exc:
                st.error(str(exc))
            except Exception as exc:  # pragma: no cover - OAuth / API errors
                st.error(f"Nie udało się wyeksportować do Google Docs: {exc}")
