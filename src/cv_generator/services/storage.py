"""SQLite-based local persistence for profiles, job offers and generated CVs.

Storage is intentionally tiny — JSON blobs of the Pydantic models indexed by
name/slug/offer_key. Enough for a local single-user app.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from cv_generator.config import get_settings
from cv_generator.models import BoardOffer, BoardSource, JobOffer, Profile, TailoredCV

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

CREATE TABLE IF NOT EXISTS board_offers (
    offer_key TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    data TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    published_at TEXT,
    last_seen_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_board_offers_source ON board_offers(source);
CREATE INDEX IF NOT EXISTS idx_board_offers_published ON board_offers(published_at);

CREATE TABLE IF NOT EXISTS offer_matches (
    profile_name TEXT NOT NULL,
    offer_key TEXT NOT NULL,
    match_score INTEGER NOT NULL,
    matched_json TEXT NOT NULL,
    missing_json TEXT NOT NULL,
    scored_at TEXT NOT NULL,
    PRIMARY KEY (profile_name, offer_key)
);
"""


class Storage:
    def __init__(self, db_path: Path | None = None) -> None:
        settings = get_settings()
        self.db_path = db_path or (settings.app_data_dir / "cv_generator.sqlite")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            self._migrate(conn)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        """Additive-only migrations for older databases."""
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(generated_cvs)")}
        if "offer_key" not in cols:
            conn.execute("ALTER TABLE generated_cvs ADD COLUMN offer_key TEXT")

    # Profiles -----------------------------------------------------------

    def save_profile(self, profile: Profile, name: str | None = None) -> str:
        key = name or profile.full_name
        payload = profile.model_dump_json()
        now = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO profiles(name, data, updated_at) VALUES(?, ?, ?) "
                "ON CONFLICT(name) DO UPDATE SET"
                " data=excluded.data, updated_at=excluded.updated_at",
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
        now = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO job_offers(slug, data, updated_at) VALUES(?, ?, ?) "
                "ON CONFLICT(slug) DO UPDATE SET"
                " data=excluded.data, updated_at=excluded.updated_at",
                (slug, payload, now),
            )
        return slug

    def load_job_offer(self, slug: str) -> JobOffer | None:
        with self._connect() as conn:
            row = conn.execute("SELECT data FROM job_offers WHERE slug=?", (slug,)).fetchone()
        return JobOffer.model_validate_json(row["data"]) if row else None

    # Board offers -------------------------------------------------------

    def upsert_board_offers(self, offers: list[BoardOffer]) -> int:
        if not offers:
            return 0
        now = datetime.now(UTC).isoformat()
        rows = [
            (
                o.offer_key,
                o.source.value,
                o.external_id,
                o.model_dump_json(),
                1 if o.is_active else 0,
                o.published_at.isoformat() if o.published_at else None,
                (o.last_seen_at or datetime.now(UTC)).isoformat(),
                now,
            )
            for o in offers
        ]
        with self._connect() as conn:
            conn.executemany(
                "INSERT INTO board_offers"
                "(offer_key, source, external_id, data, is_active, published_at,"
                " last_seen_at, updated_at) "
                "VALUES(?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(offer_key) DO UPDATE SET "
                "  data=excluded.data,"
                "  is_active=excluded.is_active,"
                "  published_at=COALESCE(excluded.published_at, board_offers.published_at),"
                "  last_seen_at=excluded.last_seen_at,"
                "  updated_at=excluded.updated_at",
                rows,
            )
        return len(rows)

    def mark_missing_inactive(
        self, source: BoardSource, seen_offer_keys: list[str]
    ) -> int:
        """Mark board offers for ``source`` that were NOT seen as inactive."""
        with self._connect() as conn:
            if seen_offer_keys:
                placeholders = ",".join("?" * len(seen_offer_keys))
                cursor = conn.execute(
                    f"UPDATE board_offers SET is_active=0 "
                    f"WHERE source=? AND offer_key NOT IN ({placeholders})",
                    (source.value, *seen_offer_keys),
                )
            else:
                cursor = conn.execute(
                    "UPDATE board_offers SET is_active=0 WHERE source=?",
                    (source.value,),
                )
            return cursor.rowcount

    def load_board_offer(self, offer_key: str) -> BoardOffer | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT data, is_active FROM board_offers WHERE offer_key=?",
                (offer_key,),
            ).fetchone()
        return _hydrate_board_offer(row) if row else None

    def list_board_offers(
        self,
        *,
        sources: list[BoardSource] | None = None,
        include_inactive: bool = True,
    ) -> list[BoardOffer]:
        query = "SELECT data, is_active FROM board_offers"
        conditions: list[str] = []
        params: list[object] = []
        if sources:
            placeholders = ",".join("?" * len(sources))
            conditions.append(f"source IN ({placeholders})")
            params.extend(s.value for s in sources)
        if not include_inactive:
            conditions.append("is_active=1")
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY COALESCE(published_at, updated_at) DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [_hydrate_board_offer(r) for r in rows]

    # Offer matches ------------------------------------------------------

    def save_match(
        self,
        *,
        profile_name: str,
        offer_key: str,
        match_score: int,
        matched: list[str],
        missing: list[str],
    ) -> None:
        now = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO offer_matches"
                "(profile_name, offer_key, match_score, matched_json, missing_json, scored_at) "
                "VALUES(?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(profile_name, offer_key) DO UPDATE SET "
                "  match_score=excluded.match_score,"
                "  matched_json=excluded.matched_json,"
                "  missing_json=excluded.missing_json,"
                "  scored_at=excluded.scored_at",
                (
                    profile_name,
                    offer_key,
                    int(match_score),
                    json.dumps(matched, ensure_ascii=False),
                    json.dumps(missing, ensure_ascii=False),
                    now,
                ),
            )

    def get_match(self, *, profile_name: str, offer_key: str) -> dict[str, object] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT match_score, matched_json, missing_json, scored_at "
                "FROM offer_matches WHERE profile_name=? AND offer_key=?",
                (profile_name, offer_key),
            ).fetchone()
        if not row:
            return None
        return {
            "match_score": int(row["match_score"]),
            "matched": json.loads(row["matched_json"]),
            "missing": json.loads(row["missing_json"]),
            "scored_at": row["scored_at"],
        }

    def list_matches(self, profile_name: str) -> dict[str, dict[str, object]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT offer_key, match_score, matched_json, missing_json, scored_at "
                "FROM offer_matches WHERE profile_name=?",
                (profile_name,),
            ).fetchall()
        return {
            r["offer_key"]: {
                "match_score": int(r["match_score"]),
                "matched": json.loads(r["matched_json"]),
                "missing": json.loads(r["missing_json"]),
                "scored_at": r["scored_at"],
            }
            for r in rows
        }

    # Generated CVs ------------------------------------------------------

    def record_generated_cv(
        self,
        *,
        profile_name: str,
        job_slug: str,
        file_path: Path,
        cv: TailoredCV,
        offer_key: str | None = None,
    ) -> int:
        now = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO generated_cvs(profile_name, job_slug, file_path, "
                "match_score, data, created_at, offer_key) VALUES(?, ?, ?, ?, ?, ?, ?)",
                (
                    profile_name,
                    job_slug,
                    str(file_path),
                    cv.match_score,
                    cv.model_dump_json(),
                    now,
                    offer_key,
                ),
            )
            return int(cursor.lastrowid or 0)

    def list_generated_cvs(self, limit: int = 50) -> list[dict[str, object]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, profile_name, job_slug, file_path, match_score, created_at,"
                " offer_key "
                "FROM generated_cvs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def find_cv_for_offer(
        self, *, profile_name: str, offer_key: str
    ) -> dict[str, object] | None:
        """Return the most recent generated CV for a (profile, board offer) pair."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, profile_name, job_slug, file_path, match_score, created_at,"
                " offer_key, data "
                "FROM generated_cvs "
                "WHERE profile_name=? AND offer_key=? "
                "ORDER BY created_at DESC LIMIT 1",
                (profile_name, offer_key),
            ).fetchone()
        return dict(row) if row else None


__all__ = ["Storage"]


def _hydrate_board_offer(row: sqlite3.Row) -> BoardOffer:
    """Rebuild a ``BoardOffer`` from a row, respecting the DB ``is_active`` column.

    The JSON blob was serialized at upsert time (always ``is_active=True``);
    the authoritative flag lives in its own column and is updated in place by
    :meth:`Storage.mark_missing_inactive`.
    """
    offer = BoardOffer.model_validate_json(row["data"])
    return offer.model_copy(update={"is_active": bool(row["is_active"])})


def _serialize_for_export(cv: TailoredCV) -> str:
    """Helper for ad-hoc dumps (kept for symmetry with future Drive export)."""
    return json.dumps(cv.model_dump(), ensure_ascii=False, indent=2)
