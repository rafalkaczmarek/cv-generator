"""List editors for profile experiences and education."""

from __future__ import annotations

import json
import uuid
from datetime import date
from typing import Any

import streamlit as st
from pydantic import ValidationError

from cv_generator.models import Education, Experience, Profile
from cv_generator.ui.state import (
    delete_buffer_entry,
    ensure_entry_id,
    strip_entry_id,
    with_entry_ids,
)


def experiences_editor(profile: Profile | None) -> list[Experience]:
    st.subheader("Doświadczenie zawodowe")
    current: list[dict[str, Any]] = (
        [json.loads(e.model_dump_json()) for e in profile.experiences] if profile else []
    )
    if "experiences_buffer" not in st.session_state:
        st.session_state.experiences_buffer = with_entry_ids(current)

    if st.button("Dodaj doświadczenie", key="add_exp"):
        st.session_state.experiences_buffer.append(
            {
                "_id": str(uuid.uuid4()),
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
    keep_buffer: list[dict[str, Any]] = []
    active_ids = {e.get("_id") for e in st.session_state.experiences_buffer}
    for idx, exp in enumerate(list(st.session_state.experiences_buffer)):
        entry_id = ensure_entry_id(exp)
        if entry_id not in active_ids:
            continue
        with st.expander(
            f"#{idx + 1} {exp.get('title') or 'nowa pozycja'} @ {exp.get('company') or '...'}",
            expanded=False,
        ):
            c1, c2 = st.columns(2)
            with c1:
                exp["company"] = st.text_input(
                    "Firma", value=exp.get("company", ""), key=f"exp_company_{entry_id}"
                )
                exp["title"] = st.text_input(
                    "Stanowisko", value=exp.get("title", ""), key=f"exp_title_{entry_id}"
                )
                exp["location"] = st.text_input(
                    "Lokalizacja", value=exp.get("location") or "", key=f"exp_loc_{entry_id}"
                )
            with c2:
                start_raw = exp.get("start_date") or str(date.today())
                end_raw = exp.get("end_date")
                start_value = (
                    date.fromisoformat(start_raw) if isinstance(start_raw, str) else start_raw
                )
                exp["start_date"] = str(
                    st.date_input(
                        "Data rozpoczęcia",
                        value=start_value,
                        key=f"exp_start_{entry_id}",
                    )
                )
                exp["is_current"] = st.checkbox(
                    "Obecnie", value=bool(exp.get("is_current")), key=f"exp_curr_{entry_id}"
                )
                if not exp["is_current"]:
                    end_value = (
                        date.fromisoformat(end_raw)
                        if isinstance(end_raw, str) and end_raw
                        else date.today()
                    )
                    exp["end_date"] = str(
                        st.date_input(
                            "Data zakończenia", value=end_value, key=f"exp_end_{entry_id}"
                        )
                    )
                else:
                    exp["end_date"] = None

            exp["summary"] = st.text_area(
                "Krótki opis roli (opcjonalnie)",
                value=exp.get("summary") or "",
                key=f"exp_sum_{entry_id}",
                height=80,
            )
            bullets_str = st.text_area(
                "Bullet points (jeden na linię)",
                value="\n".join(exp.get("bullets") or []),
                key=f"exp_bullets_{entry_id}",
                height=120,
            )
            exp["bullets"] = [b.strip() for b in bullets_str.splitlines() if b.strip()]

            techs_str = st.text_input(
                "Technologie (po przecinku)",
                value=", ".join(exp.get("technologies") or []),
                key=f"exp_techs_{entry_id}",
            )
            exp["technologies"] = [t.strip() for t in techs_str.split(",") if t.strip()]

            st.button(
                "Usuń tę pozycję",
                key=f"exp_del_{entry_id}",
                on_click=delete_buffer_entry,
                args=("experiences_buffer", entry_id),
            )

            try:
                validated = Experience.model_validate(strip_entry_id(exp))
                keep.append(validated)
                keep_buffer.append({**json.loads(validated.model_dump_json()), "_id": entry_id})
            except ValidationError as ve:
                st.error(f"Pozycja #{idx + 1} ma błędne dane: {ve}")

    st.session_state.experiences_buffer = keep_buffer
    return keep


def education_editor(profile: Profile | None) -> list[Education]:
    st.subheader("Wykształcenie")
    current: list[dict[str, Any]] = (
        [json.loads(e.model_dump_json()) for e in profile.education] if profile else []
    )
    if "edu_buffer" not in st.session_state:
        st.session_state.edu_buffer = with_entry_ids(current)

    if st.button("Dodaj wykształcenie", key="add_edu"):
        st.session_state.edu_buffer.append(
            {
                "_id": str(uuid.uuid4()),
                "institution": "",
                "degree": "",
                "field_of_study": "",
                "start_date": None,
                "end_date": None,
            }
        )

    keep: list[Education] = []
    keep_buffer: list[dict[str, Any]] = []
    active_ids = {e.get("_id") for e in st.session_state.edu_buffer}
    for idx, edu in enumerate(list(st.session_state.edu_buffer)):
        entry_id = ensure_entry_id(edu)
        if entry_id not in active_ids:
            continue
        with st.expander(f"#{idx + 1} {edu.get('institution') or 'nowa pozycja'}", expanded=False):
            edu["institution"] = st.text_input(
                "Uczelnia / szkoła",
                value=edu.get("institution", ""),
                key=f"edu_inst_{entry_id}",
            )
            c1, c2 = st.columns(2)
            with c1:
                edu["degree"] = st.text_input(
                    "Stopień / tytuł", value=edu.get("degree") or "", key=f"edu_deg_{entry_id}"
                )
            with c2:
                edu["field_of_study"] = st.text_input(
                    "Kierunek", value=edu.get("field_of_study") or "", key=f"edu_field_{entry_id}"
                )

            edu["description"] = st.text_area(
                "Opis (opcjonalnie)",
                value=edu.get("description") or "",
                key=f"edu_desc_{entry_id}",
                height=60,
            )

            st.button(
                "Usuń tę pozycję",
                key=f"edu_del_{entry_id}",
                on_click=delete_buffer_entry,
                args=("edu_buffer", entry_id),
            )
            try:
                validated = Education.model_validate(strip_entry_id(edu))
                keep.append(validated)
                keep_buffer.append({**json.loads(validated.model_dump_json()), "_id": entry_id})
            except ValidationError as ve:
                st.error(f"Wykształcenie #{idx + 1} ma błędne dane: {ve}")

    st.session_state.edu_buffer = keep_buffer
    return keep
