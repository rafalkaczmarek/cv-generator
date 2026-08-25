"""Static files and builders for Playwright E2E tests."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

PROFILE_CSV = FIXTURES_DIR / "Profile.csv"
POSITIONS_CSV = FIXTURES_DIR / "Positions.csv"
EDUCATION_CSV = FIXTURES_DIR / "Education.csv"
EDUCATION_BLANK_SCHOOL_CSV = FIXTURES_DIR / "Education_blank_school.csv"
# Deliberately not chronological — import must sort by Start Date, newest first.
PROJECTS_CSV = FIXTURES_DIR / "Projects.csv"

E2E_EDUCATION_INSTITUTION = "Politechnika Warszawska"
E2E_EDUCATION_DEGREE = "mgr inż."
E2E_EDUCATION_FIELD = "Informatyka"
E2E_EDUCATION_LINE = (
    f"{E2E_EDUCATION_DEGREE}, {E2E_EDUCATION_FIELD} — "
    f"{E2E_EDUCATION_INSTITUTION} (2013 - 2018)"
)
E2E_BLANK_SCHOOL_DEGREE = "Inżynier (Inż.)"


def build_linkedin_zip(path: Path) -> Path:
    """Write a minimal LinkedIn export archive for file-upload tests."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.write(PROFILE_CSV, arcname="Profile.csv")
        archive.write(POSITIONS_CSV, arcname="Positions.csv")
        archive.write(PROJECTS_CSV, arcname="Projects.csv")
        archive.write(EDUCATION_CSV, arcname="Education.csv")
        archive.writestr(
            "Skills.csv",
            "Name\r\nPython\r\nFastAPI\r\nDocker\r\n",
        )
    path.write_bytes(buffer.getvalue())
    return path
