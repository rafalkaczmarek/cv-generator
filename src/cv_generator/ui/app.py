"""Streamlit UI for the CV generator.

Tabs:
1. Profil — formularz danych kandydata (z możliwością zapisu/wczytania)
2. Oferty — polskie portale IT: lista pasujących ofert z dopasowaniem do profilu
3. Oferta — URL lub wklejony tekst pojedynczej oferty, analiza przez LLM
4. Generuj — uruchomienie pipeline'u LangGraph
5. Podgląd i edycja — human-in-the-loop, ostatnia korekta przed eksportem
6. Eksport — zapis do DOCX i historia poprzednich generacji
"""

from __future__ import annotations

import streamlit as st

from cv_generator.config import get_settings
from cv_generator.logging_setup import configure_logging
from cv_generator.ui.export import render_export_tab
from cv_generator.ui.generate import render_generate_tab
from cv_generator.ui.job import render_job_tab
from cv_generator.ui.llm import render_llm_sidebar
from cv_generator.ui.offers import render_offers_tab
from cv_generator.ui.preview import render_preview_tab
from cv_generator.ui.profile import render_profile_tab

configure_logging(get_settings())

st.set_page_config(page_title="CV Generator", page_icon=":briefcase:", layout="wide")


def main() -> None:
    render_llm_sidebar()
    st.title("CV Generator")
    st.caption("AI-powered, dopasowane do konkretnej oferty pracy.")

    tabs = st.tabs(["Profil", "Oferty", "Oferta", "Generuj", "Podgląd", "Eksport"])
    with tabs[0]:
        render_profile_tab()
    with tabs[1]:
        render_offers_tab()
    with tabs[2]:
        render_job_tab()
    with tabs[3]:
        render_generate_tab()
    with tabs[4]:
        render_preview_tab()
    with tabs[5]:
        render_export_tab()


main()
