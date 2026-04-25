"""v0.66.1: doctor detects orphan Chrome processes holding the NLM session
profile, which can spontaneously open accounts.google.com/notebooklm/...
URLs that look like research-hub bugs but are not."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock

import pytest

from research_hub.doctor import check_nlm_chrome_orphans


class _FakeProc:
    def __init__(self, stdout: str = "", returncode: int = 0):
        self.stdout = stdout
        self.returncode = returncode


def test_no_orphan_chrome_returns_ok(monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: _FakeProc(stdout="random other process line\n"),
    )
    result = check_nlm_chrome_orphans()
    assert result.status == "OK"
    assert "No orphan" in result.message


def test_orphan_chrome_returns_info_with_count_and_hint(monkeypatch):
    fake_output = (
        "Node,CommandLine,ProcessId\n"
        "MACHINE,chrome.exe --user-data-dir=/c/Users/X/.research_hub/nlm_sessions/default,12345\n"
        "MACHINE,chrome.exe --user-data-dir=/c/Users/X/.research_hub/nlm_sessions/default,12346\n"
    )
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **kw: _FakeProc(stdout=fake_output)
    )
    result = check_nlm_chrome_orphans()
    assert result.status == "INFO"
    assert "2 Chrome process" in result.message
    assert "kill these processes" in result.message
    assert "research-hub itself" in result.message  # disambiguates blame


def test_subprocess_unavailable_returns_info_not_fail(monkeypatch):
    def _raise(*_a, **_kw):
        raise FileNotFoundError("wmic not on PATH")

    monkeypatch.setattr(subprocess, "run", _raise)
    result = check_nlm_chrome_orphans()
    assert result.status == "INFO"
    assert "Process listing unavailable" in result.message


def test_subprocess_timeout_returns_info_not_crash(monkeypatch):
    def _raise(*_a, **_kw):
        raise subprocess.TimeoutExpired(cmd="ps", timeout=8)

    monkeypatch.setattr(subprocess, "run", _raise)
    result = check_nlm_chrome_orphans()
    assert result.status == "INFO"
    assert "Process listing unavailable" in result.message
