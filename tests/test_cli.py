"""Tests for the CLI entrypoint."""

from __future__ import annotations

import sys

from cv_generator import cli


def test_main_launches_streamlit(monkeypatch) -> None:
    captured: list[list[str]] = []

    def fake_call(cmd: list[str]) -> int:
        captured.append(cmd)
        return 0

    monkeypatch.setattr(cli.subprocess, "call", fake_call)

    assert cli.main() == 0
    assert captured
    assert captured[0][0] == sys.executable
    assert captured[0][1:4] == ["-m", "streamlit", "run"]
    assert captured[0][-1].endswith("ui\\app.py") or captured[0][-1].endswith("ui/app.py")
