from __future__ import annotations

import sys
from types import SimpleNamespace


def _run_auto(*, monkeypatch, is_tty: bool, show: bool):
    from research_hub import cli

    calls: list[bool] = []
    monkeypatch.setattr("research_hub.auto.auto_pipeline", lambda *args, **kwargs: SimpleNamespace(ok=True, error=""))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: is_tty)
    monkeypatch.setattr(
        "research_hub.dashboard.generate_dashboard",
        lambda **kwargs: calls.append(kwargs.get("open_browser", False)),
    )

    rc = cli._auto(
        topic="agent-based modeling",
        cluster_slug=None,
        cluster_name=None,
        max_papers=3,
        field=None,
        do_nlm=False,
        do_crystals=False,
        llm_cli=None,
        dry_run=False,
        show=show,
    )
    return rc, calls


def test_auto_show_default_on_opens_dashboard_when_tty(monkeypatch):
    rc, calls = _run_auto(monkeypatch=monkeypatch, is_tty=True, show=True)
    assert rc == 0
    assert calls == [True]


def test_auto_no_show_flag_suppresses_dashboard(monkeypatch):
    rc, calls = _run_auto(monkeypatch=monkeypatch, is_tty=True, show=False)
    assert rc == 0
    assert calls == []


def test_auto_skips_dashboard_when_not_tty(monkeypatch):
    rc, calls = _run_auto(monkeypatch=monkeypatch, is_tty=False, show=True)
    assert rc == 0
    assert calls == []
