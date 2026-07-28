"""Session state helpers shared across Streamlit tabs."""

from __future__ import annotations

import uuid
from typing import Any

import streamlit as st

from cv_generator.services.storage import Storage


def storage() -> Storage:
    if "storage" not in st.session_state:
        st.session_state.storage = Storage()
    return st.session_state.storage


def ss_get(key: str, default: Any = None) -> Any:
    return st.session_state.get(key, default)


def ensure_entry_id(entry: dict[str, Any]) -> str:
    entry_id = entry.get("_id")
    if not entry_id:
        entry_id = str(uuid.uuid4())
        entry["_id"] = entry_id
    return entry_id


def strip_entry_id(entry: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in entry.items() if k != "_id"}


def with_entry_ids(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for item in items:
        ensure_entry_id(item)
    return items


def delete_buffer_entry(buffer_key: str, entry_id: str) -> None:
    st.session_state[buffer_key] = [
        entry for entry in st.session_state[buffer_key] if entry.get("_id") != entry_id
    ]
