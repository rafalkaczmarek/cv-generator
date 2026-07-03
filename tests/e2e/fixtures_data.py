"""Static files and builders for Playwright E2E tests."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

PROFILE_CSV = FIXTURES_DIR / "Profile.csv"
POSITIONS_CSV = FIXTURES_DIR / "Positions.csv"


def build_linkedin_zip(path: Path) -> Path:
    """Write a minimal LinkedIn export archive for file-upload tests."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.write(PROFILE_CSV, arcname="Profile.csv")
        archive.write(POSITIONS_CSV, arcname="Positions.csv")
        archive.writestr(
            "Skills.csv",
            "Name\r\nPython\r\nFastAPI\r\nDocker\r\n",
        )
    path.write_bytes(buffer.getvalue())
    return path
