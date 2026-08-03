"""Export and generation history tab."""

from __future__ import annotations

import streamlit as st

from cv_generator.config import get_settings
from cv_generator.models import JobOffer, Profile, TailoredCV
from cv_generator.services.docx_generator import list_templates, render_cv
from cv_generator.ui.state import ss_get, storage


def render_export_tab() -> None:
    st.header("Eksport i historia")
    cv: TailoredCV | None = ss_get("tailored")
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
            filename = None
            if offer:
                stamp_slug = offer.slug()
                filename = f"cv_{stamp_slug}.docx"
            path = render_cv(cv, template_id=selected_id, filename=filename)
            if profile and offer:
                storage().record_generated_cv(
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
