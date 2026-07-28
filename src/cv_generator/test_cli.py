"""Console entrypoints for running the test suite."""

from __future__ import annotations

import subprocess
import sys

import pytest

# Clear ini addopts (`-o addopts=`) so CLI args are not merged with pyproject.toml.
_UNIT_ARGS = ["-o", "addopts=", "-m", "not e2e", "--ignore=tests/e2e"]
_COV_ARGS = ["--cov=cv_generator", "--cov-report=term-missing"]
_E2E_COV_ARGS = [*_COV_ARGS, "--cov-append"]
_E2E_ARGS = ["tests/e2e", "-m", "e2e", "-v", "-o", "addopts="]


def _exit_pytest(args: list[str]) -> None:
    # Copy so callers can safely reuse module-level arg lists.
    raise SystemExit(pytest.main(list(args)))


def _ensure_playwright_chromium() -> None:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            browser.close()
    except PlaywrightError as exc:
        if "Executable doesn't exist" not in str(exc):
            raise
        subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])


def test_unit() -> None:
    """Run unit tests (excludes e2e)."""
    _exit_pytest(_UNIT_ARGS)


def test_unit_cov() -> None:
    """Run unit tests with code coverage."""
    _exit_pytest([*_UNIT_ARGS, *_COV_ARGS])


def test_e2e() -> None:
    """Run Playwright end-to-end tests."""
    _ensure_playwright_chromium()
    _exit_pytest(_E2E_ARGS)


def test_e2e_cov() -> None:
    """Run end-to-end tests with code coverage."""
    _ensure_playwright_chromium()
    _exit_pytest([*_E2E_ARGS, *_E2E_COV_ARGS])
