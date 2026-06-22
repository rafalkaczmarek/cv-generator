"""CLI entrypoint.

Currently a thin wrapper that launches the Streamlit UI. Implemented as a
console script so users can run `cv-generator` after `pip install`.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    app_path = Path(__file__).parent / "ui" / "app.py"
    cmd = [sys.executable, "-m", "streamlit", "run", str(app_path)]
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
