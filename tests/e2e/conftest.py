"""Fixtures for Playwright E2E tests against a local Streamlit server."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Generator
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import Page

from cv_generator.config import PROJECT_ROOT

APP_PATH = PROJECT_ROOT / "src" / "cv_generator" / "ui" / "app.py"
DEFAULT_TEMPLATE = PROJECT_ROOT / "templates" / "cv_template.docx"


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_server(url: str, *, timeout_seconds: float = 45.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            response = httpx.get(url, timeout=2.0)
            if response.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.25)
    raise RuntimeError(f"Streamlit server did not become ready at {url}")


@pytest.fixture(autouse=True)
def _playwright_timeouts(page: Page) -> None:
    page.set_default_timeout(30_000)
    page.set_default_navigation_timeout(30_000)


@pytest.fixture(scope="session")
def browser_type_launch_args() -> dict[str, bool]:
    return {"headless": True}


@pytest.fixture(scope="session")
def browser_context_args() -> dict[str, dict[str, int]]:
    return {"viewport": {"width": 1280, "height": 900}}


@pytest.fixture(scope="session")
def e2e_workspace(tmp_path_factory: pytest.TempPathFactory) -> Path:
    base = tmp_path_factory.mktemp("e2e")
    for name in ("data", "output", "templates"):
        (base / name).mkdir()
    shutil.copy2(DEFAULT_TEMPLATE, base / "templates" / "cv_template.docx")
    return base


@pytest.fixture(scope="session")
def streamlit_url(e2e_workspace: Path) -> Generator[str, None, None]:
    port = _find_free_port()
    url = f"http://127.0.0.1:{port}"

    env = os.environ.copy()
    env.update(
        {
            "APP_DATA_DIR": str(e2e_workspace / "data"),
            "APP_OUTPUT_DIR": str(e2e_workspace / "output"),
            "APP_TEMPLATES_DIR": str(e2e_workspace / "templates"),
            "LLM_PROVIDER": "stub",
            "CV_GENERATOR_IGNORE_ENV_FILE": "1",
            "STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false",
        }
    )

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(APP_PATH),
            "--server.headless",
            "true",
            "--server.port",
            str(port),
            "--server.address",
            "127.0.0.1",
            "--browser.gatherUsageStats",
            "false",
            "--server.fileWatcherType",
            "none",
        ],
        env=env,
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        _wait_for_server(url)
        yield url
    except Exception as exc:
        raise RuntimeError(
            f"Streamlit server did not become ready at {url} (exit={proc.poll()})"
        ) from exc
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
