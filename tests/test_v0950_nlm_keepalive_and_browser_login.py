"""v0.95.0 / v1.0.0 — Idle keepalive + non-interactive browser-cookie login.

Tests are fully mocked — no real Google / browser / rookiepy / schtasks
execution happens at any point.

Coverage plan:
  A. rotate_and_persist_session
       A1. healthy path calls _rotate_cookies + save_cookies_to_storage + perms
       A2. missing upstream attr → returns False, never raises
       A3. _rotate_cookies raises → returns False, never raises
       A4. save_cookies_to_storage raises → returns False, never raises

  B. keepalive_once
       B1. session healthy → rotate called, returns 0
       B2. session not-ok → WARN printed, returns non-zero, NO rotate

  C. CLI notebooklm keepalive
       C1. default (no flags) → keepalive_once called
       C2. --loop --interval → N iterations with patched sleep
       C3. --install-windows-task WITHOUT --yes → argv printed, subprocess NOT called
       C4. --install-windows-task WITH --yes → subprocess.run called with schtasks argv
       C5. --uninstall-windows-task WITH --yes → schtasks /Delete argv passed to subprocess
       C6. non-Windows → no-op message, rc 1
       C7. console-script present → /TR uses script path, no wrapper written, no /RL
       C8. source-checkout → dry-run shows wrapper contents w/ PYTHONPATH=src + cd /d
       C9. source-checkout apply → wrapper file written + subprocess called w/ .cmd /TR
       C10. uninstall apply (source-checkout) → wrapper deleted + schtasks /Delete called

  D. login_from_browser (function)
       D1. rc==0 → upstream argv has --browser-cookies, perms tightened
       D2. specific browser → browser name appended after --browser-cookies
       D3. browser=None → no extra arg after --browser-cookies (auto)
       D4. rc!=0 → perms NOT tightened, rc propagated

  E. CLI notebooklm login --from-browser
       E1. bare --from-browser → args.from_browser=='auto', login_from_browser(browser=None)
       E2. --from-browser chrome → login_from_browser(browser='chrome')
       E3. rc propagated from login_from_browser
       E4. --from-browser takes precedence over default interactive login
       E5. --import-from takes precedence over --from-browser
       E6. rookiepy-missing (rc!=0) → actionable message printed
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_cfg(tmp_path: Path) -> MagicMock:
    cfg = MagicMock()
    cfg.research_hub_dir = tmp_path / ".research_hub"
    cfg.research_hub_dir.mkdir(parents=True, exist_ok=True)
    return cfg


def _write_state(tmp_path: Path) -> Path:
    sf = tmp_path / ".research_hub" / "nlm_sessions" / "state.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    sf.write_text("{}", encoding="utf-8")
    return sf


# ---------------------------------------------------------------------------
# A. refresh_and_persist_session + rotate_and_persist_session (back-compat shim)
# ---------------------------------------------------------------------------


class TestRefreshAndPersistSession:
    """Tests for the new ``refresh_and_persist_session`` (and the bool
    shim ``rotate_and_persist_session``). The old test class mocked the
    SDK's private ``_rotate_cookies`` poke; the new contract uses the
    SDK's PUBLIC ``fetch_tokens_with_domains`` which actually fetches
    CSRF + session_id (observable proof the session is alive)."""

    def test_healthy_returns_ok_with_metadata(self, tmp_path: Path, monkeypatch):
        """Happy path: SDK token fetch succeeds → RefreshResult(ok=True)
        with before/after metadata captured from the state file."""
        sf = _write_state(tmp_path)
        # Seed state.json with two freshness cookies so before-metadata is non-trivial.
        import json
        sf.write_text(json.dumps({"cookies": [
            {"name": "__Secure-1PSIDTS", "expires": 1700000000.0},
            {"name": "__Secure-3PSIDTS", "expires": 1700000000.0},
        ]}), encoding="utf-8")

        called: list = []

        async def fake_fetch(path=None, profile=None):
            called.append(("fetch", str(path)))
            # Simulate cookie rotation: bump expiries on disk so the
            # before/after diff has something to detect.
            data = json.loads(sf.read_text(encoding="utf-8"))
            for c in data["cookies"]:
                c["expires"] = 1700009999.0
            sf.write_text(json.dumps(data), encoding="utf-8")
            return ("csrf-tok", "sess-id")

        import notebooklm.auth as upstream_auth
        monkeypatch.setattr(upstream_auth, "fetch_tokens_with_domains", fake_fetch)
        import research_hub.notebooklm.auth as rh_auth
        monkeypatch.setattr(rh_auth, "_tighten_state_file_perms", lambda _p: None)

        from research_hub.notebooklm.keepalive import refresh_and_persist_session
        result = refresh_and_persist_session(sf)

        assert result.ok is True, f"expected ok=True; got reason={result.reason!r}"
        assert result.reason == "ok"
        assert called == [("fetch", str(sf))], "fetch_tokens_with_domains must run exactly once"
        # before vs after expiry strings must differ — proves the freshness
        # cookies actually moved forward, the original silent-fail bug.
        assert result.before_metadata["__Secure-1PSIDTS"] != result.after_metadata["__Secure-1PSIDTS"]
        assert "__Secure-1PSIDTS" in result.changed

    def test_sdk_failure_returns_not_ok_never_raises(self, tmp_path: Path, monkeypatch):
        """SDK raises (network down, auth expired, etc.) → RefreshResult(ok=False)
        with the exception type/message in `reason`. Must NEVER raise."""
        sf = _write_state(tmp_path)
        import notebooklm.auth as upstream_auth

        async def boom(path=None, profile=None):
            raise RuntimeError("auth expired (simulated)")

        monkeypatch.setattr(upstream_auth, "fetch_tokens_with_domains", boom)

        from research_hub.notebooklm.keepalive import refresh_and_persist_session
        result = refresh_and_persist_session(sf)

        assert result.ok is False
        assert "RuntimeError" in result.reason
        assert "auth expired" in result.reason

    def test_back_compat_shim_returns_bool(self, tmp_path: Path, monkeypatch):
        """`rotate_and_persist_session` is retained as a thin shim that
        collapses RefreshResult down to bool for older callers."""
        sf = _write_state(tmp_path)
        import notebooklm.auth as upstream_auth

        async def ok_fetch(path=None, profile=None):
            return ("csrf", "sid")

        monkeypatch.setattr(upstream_auth, "fetch_tokens_with_domains", ok_fetch)
        import research_hub.notebooklm.auth as rh_auth
        monkeypatch.setattr(rh_auth, "_tighten_state_file_perms", lambda _p: None)

        from research_hub.notebooklm.keepalive import rotate_and_persist_session
        assert rotate_and_persist_session(sf) is True

    def test_back_compat_shim_returns_false_on_failure(self, tmp_path: Path, monkeypatch):
        """Bool shim: SDK failure path → returns False (no exception)."""
        sf = _write_state(tmp_path)
        import notebooklm.auth as upstream_auth

        async def boom(path=None, profile=None):
            raise OSError("network unreachable")

        monkeypatch.setattr(upstream_auth, "fetch_tokens_with_domains", boom)

        from research_hub.notebooklm.keepalive import rotate_and_persist_session
        assert rotate_and_persist_session(sf) is False


# ---------------------------------------------------------------------------
# B. keepalive_once  (refresh-first contract — no pre-health gate)
# ---------------------------------------------------------------------------


class TestKeepaliveOnce:
    """Tests for ``keepalive_once``. Codex review of the old design flagged
    the pre-health gate as a blocker: if the gate failed, the only refresh
    attempt was skipped, so a transient health-check error guaranteed a
    stale session forever. The new contract calls refresh FIRST."""

    def test_refresh_success_returns_zero(self, tmp_path: Path, monkeypatch):
        """B1: successful refresh → rc 0, OK message includes changed cookies."""
        cfg = _make_cfg(tmp_path)
        sf = _write_state(tmp_path)

        from research_hub.notebooklm import keepalive as ka_mod
        from research_hub.notebooklm.keepalive import RefreshResult

        def fake_refresh(_path):
            return RefreshResult(
                ok=True,
                reason="ok",
                before_metadata={"__Secure-1PSIDTS": "expiry=100"},
                after_metadata={"__Secure-1PSIDTS": "expiry=200"},
                changed=["__Secure-1PSIDTS"],
            )

        monkeypatch.setattr(ka_mod, "refresh_and_persist_session", fake_refresh)
        import research_hub.notebooklm.auth as rh_auth
        monkeypatch.setattr(rh_auth, "default_state_file", lambda _root: sf)

        rc = ka_mod.keepalive_once(cfg)
        assert rc == 0

    def test_refresh_failure_returns_one_with_actionable_hint(
        self, tmp_path: Path, monkeypatch, capsys
    ):
        """B2: refresh failure → rc 1, WARN message names login --auto-detect."""
        cfg = _make_cfg(tmp_path)
        sf = _write_state(tmp_path)

        from research_hub.notebooklm import keepalive as ka_mod
        from research_hub.notebooklm.keepalive import RefreshResult

        def fake_refresh(_path):
            return RefreshResult(ok=False, reason="HTTPError: 401 Unauthorized")

        monkeypatch.setattr(ka_mod, "refresh_and_persist_session", fake_refresh)
        import research_hub.notebooklm.auth as rh_auth
        monkeypatch.setattr(rh_auth, "default_state_file", lambda _root: sf)

        rc = ka_mod.keepalive_once(cfg)
        assert rc == 1
        err = capsys.readouterr().err
        assert "refresh failed" in err
        assert "login --auto-detect" in err

    def test_refresh_is_called_before_any_health_gate(
        self, tmp_path: Path, monkeypatch
    ):
        """B3: regression for Codex critique — old code ran
        ``check_session_health`` FIRST and skipped refresh when it failed.
        New code MUST call refresh first; a (now nonexistent) pre-health
        gate must not be reintroduced."""
        cfg = _make_cfg(tmp_path)
        sf = _write_state(tmp_path)

        order: list = []
        from research_hub.notebooklm import keepalive as ka_mod
        from research_hub.notebooklm.keepalive import RefreshResult

        def fake_refresh(_path):
            order.append("refresh")
            return RefreshResult(ok=True, reason="ok")

        monkeypatch.setattr(ka_mod, "refresh_and_persist_session", fake_refresh)
        import research_hub.notebooklm.auth as rh_auth

        # Poison check_session_health so any reintroduced pre-gate would
        # short-circuit refresh.
        def poisoned_check(*_a, **_k):
            order.append("health-pregate")
            return {"ok": False, "reason": "should not be called pre-refresh"}

        monkeypatch.setattr(rh_auth, "check_session_health", poisoned_check, raising=False)
        monkeypatch.setattr(rh_auth, "default_state_file", lambda _root: sf)

        rc = ka_mod.keepalive_once(cfg)
        assert rc == 0
        assert order == ["refresh"], (
            f"refresh must be the first (and only) call; got {order!r}. "
            "A pre-health gate would short-circuit refresh on transient errors."
        )


# ---------------------------------------------------------------------------
# C. CLI notebooklm keepalive
# ---------------------------------------------------------------------------


class TestCLIKeepalive:
    """Tests for `research-hub notebooklm keepalive` CLI dispatch."""

    def _run(self, argv: list[str], monkeypatch, tmp_path: Path) -> tuple[int, str, str]:
        """Run cli.main with patched get_config; return (rc, stdout, stderr)."""
        cfg = _make_cfg(tmp_path)
        monkeypatch.setattr("research_hub.cli.get_config", lambda: cfg)

        import io
        import contextlib
        from research_hub import cli

        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = cli.main(argv)
        return rc, out.getvalue(), err.getvalue()

    def test_default_calls_keepalive_once(self, tmp_path: Path, monkeypatch):
        """C1: bare `notebooklm keepalive` → keepalive_once called."""
        cfg = _make_cfg(tmp_path)
        monkeypatch.setattr("research_hub.cli.get_config", lambda: cfg)
        once_calls: list = []

        import research_hub.notebooklm.keepalive as ka_mod
        monkeypatch.setattr(
            ka_mod,
            "keepalive_once",
            lambda c: (once_calls.append(c), 0)[1],
        )

        from research_hub import cli
        rc = cli.main(["notebooklm", "keepalive"])

        assert rc == 0
        assert len(once_calls) == 1

    def test_loop_calls_keepalive_n_times_with_sleep(
        self, tmp_path: Path, monkeypatch
    ):
        """C2: --loop --interval 7200 → N iterations with sleep between them."""
        cfg = _make_cfg(tmp_path)
        monkeypatch.setattr("research_hub.cli.get_config", lambda: cfg)

        call_count = 0
        sleep_calls: list[float] = []

        import research_hub.notebooklm.keepalive as ka_mod

        # We'll stop after 3 iterations by raising KeyboardInterrupt on 3rd sleep
        def fake_sleep(sec: float):
            sleep_calls.append(sec)
            if len(sleep_calls) >= 3:
                raise KeyboardInterrupt

        monkeypatch.setattr(ka_mod, "keepalive_once", lambda c: (
            setattr(sys, "_test_ka_count", getattr(sys, "_test_ka_count", 0) + 1), 0
        )[1])

        original_loop = ka_mod._keepalive_loop

        def patched_loop(c, interval_sec, sleep_fn=None):
            return original_loop(c, interval_sec, sleep_fn=fake_sleep)

        monkeypatch.setattr(ka_mod, "_keepalive_loop", patched_loop)

        from research_hub import cli
        rc = cli.main(["notebooklm", "keepalive", "--loop", "--interval", "7200"])

        assert rc == 0
        assert len(sleep_calls) >= 3
        assert all(s >= 600 for s in sleep_calls), "Floor must be 600 (10 min)"

    def test_loop_floor_clamps_to_600_seconds(
        self, tmp_path: Path, monkeypatch
    ):
        """C2b: regression for the new 600 s floor. Passing
        --interval 60 (the SDK's own floor) must be clamped to 600 by
        _keepalive_loop's `max(600, interval_sec)`. The old code clamped
        to 3600; the new code MUST clamp to 600. A regression that
        accidentally restored the old floor would let this assertion
        observe a 3600 sleep, failing the test."""
        cfg = _make_cfg(tmp_path)
        monkeypatch.setattr("research_hub.cli.get_config", lambda: cfg)

        sleep_calls: list[float] = []
        import research_hub.notebooklm.keepalive as ka_mod

        def fake_sleep(sec: float):
            sleep_calls.append(sec)
            raise KeyboardInterrupt

        monkeypatch.setattr(ka_mod, "keepalive_once", lambda c: 0)
        original_loop = ka_mod._keepalive_loop
        monkeypatch.setattr(
            ka_mod,
            "_keepalive_loop",
            lambda c, interval_sec, sleep_fn=None: original_loop(
                c, interval_sec, sleep_fn=fake_sleep
            ),
        )

        from research_hub import cli
        rc = cli.main(["notebooklm", "keepalive", "--loop", "--interval", "60"])

        assert rc == 0
        assert sleep_calls == [600], (
            f"--interval 60 must be clamped to the 600 s floor; got {sleep_calls!r}"
        )

    def test_install_windows_task_without_yes_is_dry_run(
        self, tmp_path: Path, monkeypatch, capsys
    ):
        """C3: --install-windows-task WITHOUT --yes → prints argv, subprocess NOT called.

        Updated: run_install_windows_task now requires cfg; /RL HIGHEST must NOT appear.
        """
        import platform
        monkeypatch.setattr(platform, "system", lambda: "Windows")
        cfg = _make_cfg(tmp_path)

        # Monkeypatch shutil.which so behaviour is deterministic (source-checkout path).
        import research_hub.notebooklm.keepalive as ka_mod
        monkeypatch.setattr(ka_mod.shutil, "which", lambda name: None)

        with patch("subprocess.run") as mock_run:
            rc = ka_mod.run_install_windows_task(15, dry_run=True, uninstall=False, cfg=cfg)

        assert rc == 0
        mock_run.assert_not_called()
        # Dry-run must NOT write the wrapper file either.
        wrapper = cfg.research_hub_dir / "nlm_keepalive.cmd"
        assert not wrapper.exists(), "Wrapper must NOT be created during dry-run"

    def test_install_windows_task_with_yes_calls_subprocess(
        self, tmp_path: Path, monkeypatch
    ):
        """C4: --install-windows-task WITH --yes → subprocess.run called with schtasks argv.

        Updated: cfg passed; /RL HIGHEST must NOT be in argv (removed — needless elevation).
        """
        import platform
        monkeypatch.setattr(platform, "system", lambda: "Windows")
        cfg = _make_cfg(tmp_path)

        import research_hub.notebooklm.keepalive as ka_mod
        # Force source-checkout path for deterministic wrapper path.
        monkeypatch.setattr(ka_mod.shutil, "which", lambda name: None)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            rc = ka_mod.run_install_windows_task(15, dry_run=False, uninstall=False, cfg=cfg)

        assert rc == 0
        mock_run.assert_called_once()
        argv_passed = mock_run.call_args[0][0]
        assert "schtasks" in argv_passed[0]
        assert "/Create" in argv_passed
        assert "ResearchHubNLMKeepalive" in " ".join(argv_passed)
        # Minute-cadence contract (regression guard — the old code used
        # /SC HOURLY which gave only ~3 retries per PSIDTS expiry window).
        assert "/SC" in argv_passed
        sc_idx = argv_passed.index("/SC")
        assert argv_passed[sc_idx + 1] == "MINUTE", (
            f"/SC must be MINUTE, got {argv_passed[sc_idx + 1]!r}"
        )
        assert "/MO" in argv_passed
        mo_idx = argv_passed.index("/MO")
        assert argv_passed[mo_idx + 1] == "15", (
            f"/MO must be the passed interval_minutes (15), got {argv_passed[mo_idx + 1]!r}"
        )
        # /RL HIGHEST is removed (P2 fix — needless elevation, breaks non-admin).
        assert "/RL" not in argv_passed, "argv must NOT contain /RL (elevation removed)"
        assert "HIGHEST" not in argv_passed, "argv must NOT contain HIGHEST"

    def test_uninstall_windows_task_with_yes(self, tmp_path: Path, monkeypatch):
        """C5: --uninstall-windows-task WITH --yes → schtasks /Delete argv passed.

        Updated: cfg passed; /RL HIGHEST must NOT appear in uninstall argv.
        """
        import platform
        monkeypatch.setattr(platform, "system", lambda: "Windows")
        cfg = _make_cfg(tmp_path)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            import research_hub.notebooklm.keepalive as ka_mod
            rc = ka_mod.run_install_windows_task(15, dry_run=False, uninstall=True, cfg=cfg)

        assert rc == 0
        mock_run.assert_called_once()
        argv_passed = mock_run.call_args[0][0]
        assert "/Delete" in argv_passed
        assert "ResearchHubNLMKeepalive" in " ".join(argv_passed)
        # /RL is not in uninstall argv either.
        assert "/RL" not in argv_passed, "argv must NOT contain /RL"

    def test_non_windows_no_op_message(self, monkeypatch, capsys):
        """C6: non-Windows → no-op message, returns 1."""
        import platform
        monkeypatch.setattr(platform, "system", lambda: "Linux")

        with patch("subprocess.run") as mock_run:
            import research_hub.notebooklm.keepalive as ka_mod
            rc = ka_mod.run_install_windows_task(15, dry_run=False, uninstall=False, cfg=None)

        assert rc == 1
        mock_run.assert_not_called()
        captured = capsys.readouterr()
        assert "Windows-only" in captured.err or "non-Windows" in captured.err

    def test_cli_install_windows_task_without_yes_dry_run(
        self, tmp_path: Path, monkeypatch, capsys
    ):
        """C3 via CLI: notebooklm keepalive --install-windows-task (no --yes) → dry-run."""
        cfg = _make_cfg(tmp_path)
        monkeypatch.setattr("research_hub.cli.get_config", lambda: cfg)

        import platform
        monkeypatch.setattr(platform, "system", lambda: "Windows")

        import research_hub.notebooklm.keepalive as ka_mod
        monkeypatch.setattr(ka_mod.shutil, "which", lambda name: None)

        with patch("subprocess.run") as mock_run:
            from research_hub import cli
            rc = cli.main(["notebooklm", "keepalive", "--install-windows-task"])

        assert rc == 0
        mock_run.assert_not_called()

    # ------------------------------------------------------------------
    # C7–C10: P3 — _resolve_task_command + wrapper correctness
    # ------------------------------------------------------------------

    def test_console_script_present_uses_script_no_wrapper(
        self, tmp_path: Path, monkeypatch, capsys
    ):
        """C7: console-script present → /TR uses script path, no wrapper, no /RL HIGHEST.

        monkeypatch shutil.which to return a fake path; assert:
        - task command contains that path
        - no nlm_keepalive.cmd wrapper written
        - /RL not in argv
        - dry-run output mentions the console-script path
        """
        import platform
        monkeypatch.setattr(platform, "system", lambda: "Windows")
        cfg = _make_cfg(tmp_path)

        fake_script = "/usr/local/bin/research-hub"
        import research_hub.notebooklm.keepalive as ka_mod
        # console-script found → no wrapper path
        monkeypatch.setattr(ka_mod.shutil, "which", lambda name: fake_script if name == "research-hub" else None)

        with patch("subprocess.run") as mock_run:
            rc = ka_mod.run_install_windows_task(15, dry_run=True, uninstall=False, cfg=cfg)

        assert rc == 0
        mock_run.assert_not_called()

        # Wrapper file must NOT exist (console-script path taken).
        wrapper = cfg.research_hub_dir / "nlm_keepalive.cmd"
        assert not wrapper.exists(), "No wrapper should be created when console-script is found"

        captured = capsys.readouterr()
        # Dry-run output mentions the script path, not a .cmd wrapper.
        assert fake_script in captured.err, (
            f"Expected console-script path in dry-run output; got: {captured.err!r}"
        )
        # The /TR argv must reference the script, not a .cmd.
        assert "nlm_keepalive.cmd" not in captured.err, (
            "Output must not mention nlm_keepalive.cmd when console-script is present"
        )

    def test_source_checkout_dry_run_shows_wrapper_contents(
        self, tmp_path: Path, monkeypatch, capsys
    ):
        """C8: source-checkout (which→None) → dry-run shows wrapper contents.

        Assert:
        - dry-run output contains 'cd /d', 'PYTHONPATH=src', '-m research_hub notebooklm keepalive'
        - /TR in printed argv points at the .cmd path
        - no /RL HIGHEST in printed argv
        - wrapper file is NOT created (dry-run only)
        """
        import platform
        monkeypatch.setattr(platform, "system", lambda: "Windows")
        cfg = _make_cfg(tmp_path)

        import research_hub.notebooklm.keepalive as ka_mod
        # Simulate source-checkout: console-script not found.
        monkeypatch.setattr(ka_mod.shutil, "which", lambda name: None)

        with patch("subprocess.run") as mock_run:
            rc = ka_mod.run_install_windows_task(15, dry_run=True, uninstall=False, cfg=cfg)

        assert rc == 0
        mock_run.assert_not_called()

        wrapper = cfg.research_hub_dir / "nlm_keepalive.cmd"
        assert not wrapper.exists(), "Wrapper must NOT be written during dry-run"

        captured = capsys.readouterr()
        combined = captured.out + captured.err

        # Wrapper contents must appear in dry-run output.
        assert "cd /d" in combined, f"Expected 'cd /d' in dry-run output; got:\n{combined}"
        assert "PYTHONPATH=src" in combined, (
            f"Expected 'PYTHONPATH=src' in dry-run output; got:\n{combined}"
        )
        assert "-m research_hub notebooklm keepalive" in combined, (
            f"Expected '-m research_hub notebooklm keepalive' in dry-run output; got:\n{combined}"
        )

        # /TR in the printed schtasks argv must point at the .cmd path.
        assert "nlm_keepalive.cmd" in combined, (
            f"Expected nlm_keepalive.cmd in dry-run output (the /TR target); got:\n{combined}"
        )

        # /RL must not appear.
        assert "/RL" not in combined, f"/RL must not appear in dry-run output; got:\n{combined}"
        assert "HIGHEST" not in combined, (
            f"HIGHEST must not appear in dry-run output; got:\n{combined}"
        )

    def test_source_checkout_apply_writes_wrapper_and_calls_schtasks(
        self, tmp_path: Path, monkeypatch
    ):
        """C9: source-checkout apply (--yes) → wrapper file written + subprocess with .cmd.

        Assert:
        - nlm_keepalive.cmd is written with correct contents
        - subprocess.run called with argv that has /TR pointing at the .cmd
        - /RL HIGHEST not in argv
        """
        import platform
        monkeypatch.setattr(platform, "system", lambda: "Windows")
        cfg = _make_cfg(tmp_path)

        import research_hub.notebooklm.keepalive as ka_mod
        monkeypatch.setattr(ka_mod.shutil, "which", lambda name: None)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            rc = ka_mod.run_install_windows_task(15, dry_run=False, uninstall=False, cfg=cfg)

        assert rc == 0

        wrapper = cfg.research_hub_dir / "nlm_keepalive.cmd"
        assert wrapper.exists(), "Wrapper .cmd must be written on apply"

        contents = wrapper.read_text(encoding="utf-8")
        assert "cd /d" in contents, f"Wrapper must contain 'cd /d'; got:\n{contents}"
        assert "PYTHONPATH=src" in contents, (
            f"Wrapper must set PYTHONPATH=src; got:\n{contents}"
        )
        assert "-m research_hub notebooklm keepalive" in contents, (
            f"Wrapper must invoke -m research_hub notebooklm keepalive; got:\n{contents}"
        )

        mock_run.assert_called_once()
        argv_passed = mock_run.call_args[0][0]
        assert "/Create" in argv_passed, "schtasks /Create must be called"
        assert "nlm_keepalive.cmd" in " ".join(argv_passed), (
            "/TR must reference the .cmd wrapper"
        )
        # /RL HIGHEST removed (P2 fix).
        assert "/RL" not in argv_passed, "argv must NOT contain /RL"
        assert "HIGHEST" not in argv_passed, "argv must NOT contain HIGHEST"

    def test_source_checkout_uninstall_apply_deletes_wrapper_and_calls_schtasks(
        self, tmp_path: Path, monkeypatch
    ):
        """C10: uninstall apply (source-checkout) → wrapper deleted + schtasks /Delete called."""
        import platform
        monkeypatch.setattr(platform, "system", lambda: "Windows")
        cfg = _make_cfg(tmp_path)

        # Pre-create a wrapper so we can assert it gets deleted.
        wrapper = cfg.research_hub_dir / "nlm_keepalive.cmd"
        wrapper.write_text("@echo off\n", encoding="utf-8")
        assert wrapper.exists()

        import research_hub.notebooklm.keepalive as ka_mod

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            rc = ka_mod.run_install_windows_task(15, dry_run=False, uninstall=True, cfg=cfg)

        assert rc == 0
        mock_run.assert_called_once()
        argv_passed = mock_run.call_args[0][0]
        assert "/Delete" in argv_passed
        assert "ResearchHubNLMKeepalive" in " ".join(argv_passed)
        # Wrapper must be deleted.
        assert not wrapper.exists(), "Wrapper .cmd must be deleted by uninstall --yes"


# ---------------------------------------------------------------------------
# D. login_from_browser (function)
# ---------------------------------------------------------------------------


class TestLoginFromBrowser:
    """Tests for auth.login_from_browser."""

    def test_rc0_argv_contains_browser_cookies_and_perms_tightened(
        self, tmp_path: Path, monkeypatch
    ):
        """D1: rc==0 → upstream argv has --browser-cookies, perms tightened."""
        sf = tmp_path / "state.json"
        perm_calls: list = []

        import research_hub.notebooklm.auth as rh_auth
        monkeypatch.setattr(rh_auth, "_tighten_state_file_perms", lambda p: perm_calls.append(p))

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            rc = rh_auth.login_from_browser(sf, browser=None)

        assert rc == 0
        assert len(perm_calls) == 1
        called_argv = mock_run.call_args[0][0]
        assert "--browser-cookies" in called_argv
        assert "--storage" in called_argv
        assert str(sf) in called_argv

    def test_specific_browser_appended(self, tmp_path: Path, monkeypatch):
        """D2: specific browser → browser name appended after --browser-cookies."""
        sf = tmp_path / "state.json"

        import research_hub.notebooklm.auth as rh_auth
        monkeypatch.setattr(rh_auth, "_tighten_state_file_perms", lambda p: None)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            rh_auth.login_from_browser(sf, browser="chrome")

        argv = mock_run.call_args[0][0]
        bc_idx = argv.index("--browser-cookies")
        assert argv[bc_idx + 1] == "chrome", (
            f"Expected 'chrome' after --browser-cookies, got: {argv[bc_idx + 1]!r}"
        )

    def test_no_browser_no_extra_arg(self, tmp_path: Path, monkeypatch):
        """D3: browser=None → nothing appended after --browser-cookies (auto)."""
        sf = tmp_path / "state.json"

        import research_hub.notebooklm.auth as rh_auth
        monkeypatch.setattr(rh_auth, "_tighten_state_file_perms", lambda p: None)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            rh_auth.login_from_browser(sf, browser=None)

        argv = mock_run.call_args[0][0]
        bc_idx = argv.index("--browser-cookies")
        # Nothing comes after --browser-cookies (it's the last arg)
        assert bc_idx == len(argv) - 1, (
            f"Expected --browser-cookies to be last arg; argv={argv}"
        )

    def test_rc_nonzero_perms_not_tightened(self, tmp_path: Path, monkeypatch):
        """D4: rc!=0 → perms NOT tightened, rc propagated."""
        sf = tmp_path / "state.json"
        perm_calls: list = []

        import research_hub.notebooklm.auth as rh_auth
        monkeypatch.setattr(rh_auth, "_tighten_state_file_perms", lambda p: perm_calls.append(p))

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=42)
            rc = rh_auth.login_from_browser(sf, browser=None)

        assert rc == 42
        assert len(perm_calls) == 0, "Perms must NOT be tightened on failure"


# ---------------------------------------------------------------------------
# E. CLI notebooklm login --from-browser
# ---------------------------------------------------------------------------


class TestCLIFromBrowser:
    """Tests for the --from-browser flag on `notebooklm login`."""

    def _make_login_mock(self, monkeypatch, tmp_path: Path, *, return_rc: int = 0):
        cfg = _make_cfg(tmp_path)
        monkeypatch.setattr("research_hub.cli.get_config", lambda: cfg)

        calls: list[dict] = []

        import research_hub.notebooklm.auth as rh_auth

        def fake_login_from_browser(state_file, *, browser=None):
            calls.append({"state_file": state_file, "browser": browser})
            return return_rc

        monkeypatch.setattr(rh_auth, "login_from_browser", fake_login_from_browser)
        return cfg, calls

    def test_bare_from_browser_passes_browser_none(self, tmp_path: Path, monkeypatch):
        """E1: bare --from-browser → login_from_browser(browser=None)."""
        cfg, calls = self._make_login_mock(monkeypatch, tmp_path)

        from research_hub import cli
        rc = cli.main(["notebooklm", "login", "--from-browser"])

        assert rc == 0
        assert len(calls) == 1
        assert calls[0]["browser"] is None

    def test_from_browser_with_name(self, tmp_path: Path, monkeypatch):
        """E2: --from-browser chrome → login_from_browser(browser='chrome')."""
        cfg, calls = self._make_login_mock(monkeypatch, tmp_path)

        from research_hub import cli
        rc = cli.main(["notebooklm", "login", "--from-browser", "chrome"])

        assert rc == 0
        assert len(calls) == 1
        assert calls[0]["browser"] == "chrome"

    def test_rc_propagated(self, tmp_path: Path, monkeypatch):
        """E3: rc propagated from login_from_browser."""
        _, calls = self._make_login_mock(monkeypatch, tmp_path, return_rc=1)

        from research_hub import cli
        rc = cli.main(["notebooklm", "login", "--from-browser"])

        assert rc == 1

    def test_from_browser_takes_precedence_over_interactive_default(
        self, tmp_path: Path, monkeypatch
    ):
        """E4: --from-browser takes precedence over default interactive path."""
        cfg = _make_cfg(tmp_path)
        monkeypatch.setattr("research_hub.cli.get_config", lambda: cfg)

        import research_hub.notebooklm.auth as rh_auth
        from_browser_calls: list = []
        login_nlm_calls: list = []

        monkeypatch.setattr(
            rh_auth,
            "login_from_browser",
            lambda sf, browser=None: (from_browser_calls.append(browser), 0)[1],
        )
        monkeypatch.setattr(
            rh_auth,
            "login_nlm",
            lambda *a, **kw: (login_nlm_calls.append(True), 0)[1],
        )

        from research_hub import cli
        rc = cli.main(["notebooklm", "login", "--from-browser"])

        assert from_browser_calls, "--from-browser must have been called"
        assert not login_nlm_calls, "login_nlm must NOT be called when --from-browser is set"

    def test_import_from_takes_precedence_over_from_browser(
        self, tmp_path: Path, monkeypatch
    ):
        """E5: --import-from takes precedence over --from-browser."""
        cfg = _make_cfg(tmp_path)
        monkeypatch.setattr("research_hub.cli.get_config", lambda: cfg)

        import research_hub.notebooklm.auth as rh_auth
        from_browser_calls: list = []

        monkeypatch.setattr(
            rh_auth,
            "login_from_browser",
            lambda sf, browser=None: (from_browser_calls.append(browser), 0)[1],
        )

        # --import-from points at a fake vault; just make import_session succeed
        src_vault = tmp_path / "other_vault"
        (src_vault / ".research_hub" / "nlm_sessions").mkdir(parents=True, exist_ok=True)
        src_state = src_vault / ".research_hub" / "nlm_sessions" / "state.json"
        src_state.write_text("{}", encoding="utf-8")

        import_calls: list = []

        def fake_import_session(*args, **kwargs):
            import_calls.append(True)
            from research_hub.notebooklm.auth import ImportResult
            return ImportResult(ok=True, files_copied=1, bytes_copied=10)

        monkeypatch.setattr(rh_auth, "import_session", fake_import_session)

        from research_hub import cli
        rc = cli.main([
            "notebooklm", "login",
            "--import-from", str(src_vault),
            "--from-browser",
        ])

        assert rc == 0
        assert import_calls, "--import-from handler must have run"
        assert not from_browser_calls, "--from-browser must NOT run when --import-from is set"

    def test_rookiepy_missing_rc_nonzero_prints_hint(
        self, tmp_path: Path, monkeypatch, capsys
    ):
        """E6: rookiepy-missing (rc!=0) → actionable message printed."""
        cfg = _make_cfg(tmp_path)
        monkeypatch.setattr("research_hub.cli.get_config", lambda: cfg)

        import research_hub.notebooklm.auth as rh_auth
        monkeypatch.setattr(
            rh_auth,
            "login_from_browser",
            lambda sf, browser=None: 1,
        )

        import io
        import contextlib
        from research_hub import cli

        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = cli.main(["notebooklm", "login", "--from-browser"])

        assert rc == 1
        combined = out.getvalue() + err.getvalue()
        assert "browser-auth" in combined or "rookiepy" in combined or "pip install" in combined, (
            f"Expected actionable pip install hint; got: {combined!r}"
        )

    def test_parser_accepts_all_browser_choices(self, tmp_path: Path, monkeypatch):
        """E1-variant: parser accepts all documented browser choices without error."""
        cfg = _make_cfg(tmp_path)
        monkeypatch.setattr("research_hub.cli.get_config", lambda: cfg)

        import research_hub.notebooklm.auth as rh_auth
        monkeypatch.setattr(rh_auth, "login_from_browser", lambda sf, browser=None: 0)

        from research_hub import cli

        valid_browsers = [
            "auto", "chrome", "firefox", "edge", "brave", "arc",
            "chromium", "safari", "vivaldi", "zen", "librewolf",
            "opera", "opera-gx",
        ]
        for browser in valid_browsers:
            rc = cli.main(["notebooklm", "login", "--from-browser", browser])
            assert rc == 0, f"Parser rejected valid browser choice: {browser!r}"
