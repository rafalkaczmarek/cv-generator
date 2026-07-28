"""Tests for the CLI entrypoint."""

from __future__ import annotations

import sys

import pytest

from cv_generator import cli, test_cli

_UNIT_ARGS = ["-o", "addopts=", "-m", "not e2e", "--ignore=tests/e2e"]
_COV_ARGS = ["--cov=cv_generator", "--cov-report=term-missing"]
_E2E_ARGS = ["tests/e2e", "-m", "e2e", "-v", "-o", "addopts="]


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


@pytest.mark.parametrize(
    ("entrypoint", "expected_args"),
    [
        (test_cli.test_unit, _UNIT_ARGS),
        (test_cli.test_unit_cov, [*_UNIT_ARGS, *_COV_ARGS]),
        (test_cli.test_e2e, _E2E_ARGS),
        (
            test_cli.test_e2e_cov,
            [*_E2E_ARGS, *_COV_ARGS, "--cov-append"],
        ),
    ],
)
def test_test_cli_entrypoints(
    monkeypatch: pytest.MonkeyPatch,
    entrypoint,
    expected_args: list[str],
) -> None:
    captured: list[list[str]] = []

    def fake_main(args: list[str]) -> int:
        captured.append(args)
        return 0

    monkeypatch.setattr(test_cli.pytest, "main", fake_main)
    monkeypatch.setattr(test_cli, "_ensure_playwright_chromium", lambda: None)

    with pytest.raises(SystemExit) as exc_info:
        entrypoint()
    assert exc_info.value.code == 0
    assert captured == [expected_args]
