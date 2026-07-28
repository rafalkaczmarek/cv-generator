"""Export and generation history tab."""

from __future__ import annotations

import streamlit as st

from cv_generator.models import JobOffer, Profile, TailoredCV
from cv_generator.services.docx_generator import render_cv
from cv_generator.ui.state import ss_get, storage


def render_export_tab() -> None:
    st.header("Eksport i historia")
    cv: TailoredCV | None = ss_get("tailored")
    offer: JobOffer | None = ss_get("job_offer")
    profile: Profile | None = ss_get("profile")

    if cv and st.button("Zapisz jako DOCX", type="primary"):
        try:
            filename = None
            if offer:
                stamp_slug = offer.slug()
                filename = f"cv_{stamp_slug}.docx"
            path = render_cv(cv, filename=filename)
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
