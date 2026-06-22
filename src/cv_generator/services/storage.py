"""SQLite-based local persistence for profiles, job offers and generated CVs.

Storage is intentionally tiny — three tables holding JSON blobs of the
Pydantic models, indexed by name/slug. Enough for a local single-user app.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

from cv_generator.config import get_settings
from cv_generator.models import JobOffer, Profile, TailoredCV

_SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
    name TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS job_offers (
    slug TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS generated_cvs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_name TEXT NOT NULL,
    job_slug TEXT NOT NULL,
    file_path TEXT NOT NULL,
    match_score INTEGER NOT NULL,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


class Storage:
    def __init__(self, db_path: Path | None = None) -> None:
        settings = get_settings()
        self.db_path = db_path or (settings.app_data_dir / "cv_generator.sqlite")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # Profiles -----------------------------------------------------------

    def save_profile(self, profile: Profile, name: str | None = None) -> str:
        key = name or profile.full_name
        payload = profile.model_dump_json()
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO profiles(name, data, updated_at) VALUES(?, ?, ?) "
                "ON CONFLICT(name) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
                (key, payload, now),
            )
        return key

    def load_profile(self, name: str) -> Profile | None:
        with self._connect() as conn:
            row = conn.execute("SELECT data FROM profiles WHERE name=?", (name,)).fetchone()
        return Profile.model_validate_json(row["data"]) if row else None

    def list_profiles(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT name FROM profiles ORDER BY updated_at DESC").fetchall()
        return [r["name"] for r in rows]

    def delete_profile(self, name: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM profiles WHERE name=?", (name,))

    # Job offers ---------------------------------------------------------

    def save_job_offer(self, offer: JobOffer) -> str:
        slug = offer.slug()
        payload = offer.model_dump_json()
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO job_offers(slug, data, updated_at) VALUES(?, ?, ?) "
                "ON CONFLICT(slug) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
                (slug, payload, now),
            )
        return slug

    def load_job_offer(self, slug: str) -> JobOffer | None:
        with self._connect() as conn:
            row = conn.execute("SELECT data FROM job_offers WHERE slug=?", (slug,)).fetchone()
        return JobOffer.model_validate_json(row["data"]) if row else None

    # Generated CVs ------------------------------------------------------

    def record_generated_cv(
        self,
        *,
        profile_name: str,
        job_slug: str,
        file_path: Path,
        cv: TailoredCV,
    ) -> int:
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO generated_cvs(profile_name, job_slug, file_path, "
                "match_score, data, created_at) VALUES(?, ?, ?, ?, ?, ?)",
                (
                    profile_name,
                    job_slug,
                    str(file_path),
                    cv.match_score,
                    cv.model_dump_json(),
                    now,
                ),
            )
            return int(cursor.lastrowid or 0)

    def list_generated_cvs(self, limit: int = 50) -> list[dict[str, object]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, profile_name, job_slug, file_path, match_score, created_at "
                "FROM generated_cvs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]


__all__ = ["Storage"]


def _serialize_for_export(cv: TailoredCV) -> str:
    """Helper for ad-hoc dumps (kept for symmetry with future Drive export)."""
    return json.dumps(cv.model_dump(), ensure_ascii=False, indent=2)
