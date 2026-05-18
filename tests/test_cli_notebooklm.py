"""Tests for NotebookLM CLI parser and dispatch."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Regression tests for the __main__ guard bug:
# `python -m research_hub.cli notebooklm login` silently returned exit 0
# without invoking login_nlm because cli.py had no if __name__=="__main__"
# block — the module body ran but main() was never called.
# ---------------------------------------------------------------------------


def test_cli_module_has_main_guard():
    """cli.py must have an if __name__ == '__main__' guard so that
    `python -m research_hub.cli` actually calls main() and does not
    silently exit 0 having done nothing."""
    import ast
    import inspect
    from research_hub import cli

    source = inspect.getsource(cli)
    tree = ast.parse(source)
    # Look for a top-level If node whose test compares __name__ to __main__
    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            test = node.test
            # Match: __name__ == "__main__"
            if (
                isinstance(test, ast.Compare)
                and isinstance(test.left, ast.Name)
                and test.left.id == "__name__"
                and len(test.comparators) == 1
                and isinstance(test.comparators[0], ast.Constant)
                and test.comparators[0].value == "__main__"
            ):
                found = True
                break
    assert found, (
        "cli.py is missing `if __name__ == '__main__': raise SystemExit(main())`. "
        "Without it, `python -m research_hub.cli notebooklm login` silently exits 0 "
        "without invoking main() or login_nlm."
    )


def _make_cfg_mock(tmp_path):
    """Return a mock HubConfig with research_hub_dir pointing at tmp_path."""
    cfg = MagicMock()
    cfg.research_hub_dir = tmp_path / ".research_hub"
    cfg.research_hub_dir.mkdir(parents=True, exist_ok=True)
    return cfg


def test_notebooklm_login_calls_login_nlm(monkeypatch, tmp_path):
    """CLI `notebooklm login` (no extra flags) must call login_nlm.
    Regression: the missing __main__ guard caused it to silently exit 0
    without ever reaching this code path when run via python -m."""
    from research_hub import cli
    from research_hub.notebooklm import auth as auth_mod

    cfg = _make_cfg_mock(tmp_path)
    monkeypatch.setattr("research_hub.cli.get_config", lambda: cfg)

    login_calls = []

    def fake_login_nlm(user_data_dir, *, state_file=None, timeout_sec=300, **kwargs):
        login_calls.append({
            "user_data_dir": user_data_dir,
            "state_file": state_file,
            "timeout_sec": timeout_sec,
        })
        return 0  # simulate successful login

    monkeypatch.setattr(auth_mod, "login_nlm", fake_login_nlm)

    rc = cli.main(["notebooklm", "login"])

    assert rc == 0
    assert len(login_calls) == 1, (
        f"Expected login_nlm to be called exactly once, got {len(login_calls)} calls. "
        "If 0 calls: the __main__ guard bug has re-appeared or the dispatch is short-circuiting."
    )
    # state_file must be a Path (not None) so the session is persisted
    assert login_calls[0]["state_file"] is not None, "login_nlm must receive a state_file path"
    # timeout_sec must be the default (300) when not overridden
    assert login_calls[0]["timeout_sec"] == 300


def test_notebooklm_login_propagates_nonzero_exit(monkeypatch, tmp_path):
    """When login_nlm returns non-zero (upstream subprocess failed),
    the CLI must propagate that exit code — NOT silently return 0.
    Regression: the __main__ guard bug caused exit 0 in all cases."""
    from research_hub import cli
    from research_hub.notebooklm import auth as auth_mod

    cfg = _make_cfg_mock(tmp_path)
    monkeypatch.setattr("research_hub.cli.get_config", lambda: cfg)

    # Simulate upstream login subprocess failure (e.g. EOFError / no TTY)
    monkeypatch.setattr(auth_mod, "login_nlm", lambda *a, **kw: 1)

    rc = cli.main(["notebooklm", "login"])

    assert rc == 1, (
        f"Expected CLI exit code 1 when login_nlm returns 1, got {rc}. "
        "The CLI must NOT swallow non-zero subprocess exit codes."
    )


def test_notebooklm_login_does_not_silently_succeed_without_invoking_subprocess(
    monkeypatch, tmp_path
):
    """Guard against a regression where the login block is skipped entirely
    (e.g. due to a missing __main__ guard or early return) and the CLI
    exits 0 without having done anything."""
    from research_hub import cli
    from research_hub.notebooklm import auth as auth_mod

    cfg = _make_cfg_mock(tmp_path)
    monkeypatch.setattr("research_hub.cli.get_config", lambda: cfg)

    invoked = []

    def tracking_login_nlm(user_data_dir, **kwargs):
        invoked.append(True)
        return 0

    monkeypatch.setattr(auth_mod, "login_nlm", tracking_login_nlm)

    rc = cli.main(["notebooklm", "login"])

    assert invoked, (
        "login_nlm was never called. The CLI returned exit 0 without invoking the "
        "upstream login subprocess — this is the silent-no-op regression."
    )


def test_notebooklm_login_help_hides_dead_flags_keeps_real_paths(capsys):
    from research_hub.cli import build_parser

    with pytest.raises(SystemExit) as exc_info:
        build_parser().parse_args(["notebooklm", "login", "--help"])

    assert exc_info.value.code == 0
    help_text = capsys.readouterr().out
    for removed in ("--cdp", "--from-chrome-profile", "--keep-open", "--timeout"):
        assert removed not in help_text
    assert "--import-from" in help_text
    assert "--from-browser" in help_text


def test_notebooklm_login_rejects_removed_cdp_flag():
    from research_hub.cli import build_parser

    with pytest.raises(SystemExit):
        build_parser().parse_args(["notebooklm", "login", "--cdp"])


def test_build_parser_accepts_notebooklm_upload_and_generate_flags():
    from research_hub.cli import build_parser

    upload_args = build_parser().parse_args(["notebooklm", "upload", "--cluster", "alpha", "--dry-run", "--visible"])
    assert upload_args.command == "notebooklm"
    assert upload_args.notebooklm_command == "upload"
    assert upload_args.cluster == "alpha"
    assert upload_args.dry_run is True
    assert upload_args.headless is False
    assert upload_args.over_cap_strategy == "fail"

    generate_args = build_parser().parse_args(["notebooklm", "generate", "--cluster", "alpha", "--type", "all", "--visible"])
    assert generate_args.notebooklm_command == "generate"
    assert generate_args.type == "all"
    assert generate_args.headless is False

    ask_args = build_parser().parse_args(["notebooklm", "ask", "--cluster", "alpha", "--question", "Hello?"])
    assert ask_args.notebooklm_command == "ask"
    assert ask_args.question == "Hello?"
    assert ask_args.headless is True


def test_main_routes_notebooklm_upload_and_generate(monkeypatch, mock_require_config):
    from research_hub import cli

    calls = []

    monkeypatch.setattr(
        cli,
        "_nlm_upload",
        lambda cluster, dry_run, headless, create_if_missing, **kwargs: calls.append(
            ("upload", cluster, dry_run, headless, create_if_missing, kwargs)
        ) or 0,
    )
    monkeypatch.setattr(cli, "_nlm_generate", lambda cluster, artifact_type, headless: calls.append(("generate", cluster, artifact_type, headless)) or 0)
    monkeypatch.setattr(cli, "_nlm_ask", lambda cluster, *, question, headless, timeout_sec: calls.append(("ask", cluster, question, headless, timeout_sec)) or 0)

    assert cli.main(["notebooklm", "upload", "--cluster", "alpha", "--dry-run"]) == 0
    assert cli.main(["notebooklm", "generate", "--cluster", "alpha", "--type", "mind-map"]) == 0
    assert cli.main(["notebooklm", "ask", "--cluster", "alpha", "--question", "What?"]) == 0
    assert calls == [
        ("upload", "alpha", True, False, True, {"over_cap_strategy": "fail", "shard_size": 50, "include_suspect_urls": False}),
        ("generate", "alpha", "mind-map", False),
        ("ask", "alpha", "What?", True, 120),
    ]
