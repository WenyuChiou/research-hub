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
# A. rotate_and_persist_session
# ---------------------------------------------------------------------------


class TestRotateAndPersistSession:
    """Tests for keepalive.rotate_and_persist_session."""

    def _make_fake_jar(self) -> MagicMock:
        jar = MagicMock()
        jar.items = MagicMock(return_value=[])
        return jar

    def test_healthy_path_calls_rotate_save_perms(self, tmp_path: Path, monkeypatch):
        """A1: healthy → _rotate_cookies + save_cookies_to_storage called once + perms."""
        sf = _write_state(tmp_path)
        fake_jar = self._make_fake_jar()
        rotate_calls: list = []
        save_calls: list = []
        perm_calls: list = []

        import httpx

        async def fake_rotate(client, storage_path=None):
            rotate_calls.append(storage_path)
            # Simulate: no changes to client.cookies needed

        def fake_build(path=None):
            # Return a real httpx.Cookies (empty) so AsyncClient accepts it
            return httpx.Cookies()

        def fake_save(cookie_jar, path=None):
            save_calls.append((cookie_jar, path))

        def fake_perms(target):
            perm_calls.append(target)

        import notebooklm.auth as upstream_auth
        monkeypatch.setattr(upstream_auth, "_rotate_cookies", fake_rotate)
        monkeypatch.setattr(upstream_auth, "build_httpx_cookies_from_storage", fake_build)
        monkeypatch.setattr(upstream_auth, "save_cookies_to_storage", fake_save)

        import research_hub.notebooklm.auth as rh_auth
        monkeypatch.setattr(rh_auth, "_tighten_state_file_perms", fake_perms)

        from research_hub.notebooklm.keepalive import rotate_and_persist_session

        result = rotate_and_persist_session(sf)

        assert result is True
        assert len(rotate_calls) == 1, "Expected exactly one _rotate_cookies call"
        assert len(save_calls) == 1, "Expected exactly one save_cookies_to_storage call"
        assert len(perm_calls) == 1, "Expected exactly one _tighten_state_file_perms call"
        assert perm_calls[0] == sf

    @pytest.mark.parametrize("failure_mode", [
        "missing_attr",
        "rotate_raises",
        "save_raises",
    ])
    def test_never_raises_on_failure(
        self, tmp_path: Path, monkeypatch, failure_mode: str
    ):
        """A2/A3/A4: any internal failure → returns False, never raises."""
        sf = _write_state(tmp_path)
        fake_jar = self._make_fake_jar()

        import notebooklm.auth as upstream_auth

        if failure_mode == "missing_attr":
            # Remove the attribute so AttributeError fires
            monkeypatch.setattr(
                upstream_auth,
                "build_httpx_cookies_from_storage",
                None,
            )
        elif failure_mode == "rotate_raises":
            monkeypatch.setattr(
                upstream_auth,
                "build_httpx_cookies_from_storage",
                lambda path=None: fake_jar,
            )

            async def _raising_rotate(client, storage_path=None):
                raise RuntimeError("simulated rotate failure")

            monkeypatch.setattr(upstream_auth, "_rotate_cookies", _raising_rotate)
        elif failure_mode == "save_raises":
            monkeypatch.setattr(
                upstream_auth,
                "build_httpx_cookies_from_storage",
                lambda path=None: fake_jar,
            )

            async def _noop_rotate(client, storage_path=None):
                pass

            monkeypatch.setattr(upstream_auth, "_rotate_cookies", _noop_rotate)
            monkeypatch.setattr(
                upstream_auth,
                "save_cookies_to_storage",
                lambda jar, path=None: (_ for _ in ()).throw(IOError("disk full")),
            )

        from research_hub.notebooklm import keepalive as ka_mod
        # Reload to pick up patched upstream
        import importlib
        importlib.reload(ka_mod)

        # Must not raise
        try:
            result = ka_mod.rotate_and_persist_session(sf)
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"rotate_and_persist_session raised {type(exc).__name__}: {exc}")

        assert result is False, f"Expected False for failure_mode={failure_mode}, got {result}"


# ---------------------------------------------------------------------------
# B. keepalive_once
# ---------------------------------------------------------------------------


class TestKeepaliveOnce:
    """Tests for keepalive.keepalive_once."""

    def test_healthy_session_rotates_returns_0(self, tmp_path: Path, monkeypatch):
        """B1: session ok → rotate called, returns 0."""
        cfg = _make_cfg(tmp_path)
        sf = _write_state(tmp_path)
        rotate_calls: list = []

        import research_hub.notebooklm.auth as rh_auth
        monkeypatch.setattr(
            rh_auth,
            "check_session_health",
            lambda path: {"ok": True, "reason": "ok"},
        )
        monkeypatch.setattr(
            rh_auth,
            "default_state_file",
            lambda research_hub_dir: sf,
        )

        import research_hub.notebooklm.keepalive as ka_mod
        monkeypatch.setattr(
            ka_mod,
            "rotate_and_persist_session",
            lambda state_file: (rotate_calls.append(state_file), True)[1],
        )

        rc = ka_mod.keepalive_once(cfg)

        assert rc == 0
        assert len(rotate_calls) == 1

    def test_dead_session_warns_returns_nonzero_no_rotate(
        self, tmp_path: Path, monkeypatch, capsys
    ):
        """B2: session not-ok → WARN printed to stderr, returns non-zero, no rotate."""
        cfg = _make_cfg(tmp_path)
        sf = _write_state(tmp_path)
        rotate_calls: list = []

        import research_hub.notebooklm.auth as rh_auth
        monkeypatch.setattr(
            rh_auth,
            "check_session_health",
            lambda path: {"ok": False, "reason": "auth invalid"},
        )
        monkeypatch.setattr(
            rh_auth,
            "default_state_file",
            lambda research_hub_dir: sf,
        )

        import research_hub.notebooklm.keepalive as ka_mod
        monkeypatch.setattr(
            ka_mod,
            "rotate_and_persist_session",
            lambda state_file: (rotate_calls.append(state_file), True)[1],
        )

        rc = ka_mod.keepalive_once(cfg)

        assert rc != 0
        assert len(rotate_calls) == 0, "rotate must NOT be called when session is dead"
        captured = capsys.readouterr()
        assert "revoked" in captured.err or "WARN" in captured.err, (
            f"Expected WARN in stderr; got: {captured.err!r}"
        )
        assert "notebooklm login" in captured.err

    def test_post_rotation_probe_failure_warns_returns_nonzero(
        self, tmp_path: Path, monkeypatch, capsys
    ):
        """B3: rotation success but post-probe not-ok returns non-zero and warns."""
        cfg = _make_cfg(tmp_path)
        sf = _write_state(tmp_path)
        health_results = [
            {"ok": True, "reason": "ok"},
            {"ok": False, "reason": "auth invalid"},
        ]
        rotate_calls: list = []

        import research_hub.notebooklm.auth as rh_auth
        monkeypatch.setattr(
            rh_auth,
            "check_session_health",
            lambda path: health_results.pop(0),
        )
        monkeypatch.setattr(
            rh_auth,
            "default_state_file",
            lambda research_hub_dir: sf,
        )

        import research_hub.notebooklm.keepalive as ka_mod
        monkeypatch.setattr(
            ka_mod,
            "rotate_and_persist_session",
            lambda state_file: (rotate_calls.append(state_file), True)[1],
        )

        rc = ka_mod.keepalive_once(cfg)

        assert rc != 0
        assert rotate_calls == [sf]
        captured = capsys.readouterr()
        assert "cookies rotated" in captured.err
        assert "notebooklm login" in captured.err


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
        assert all(s >= 3600 for s in sleep_calls), "Floor must be 3600"

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
            rc = ka_mod.run_install_windows_task(6, dry_run=True, uninstall=False, cfg=cfg)

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
            rc = ka_mod.run_install_windows_task(6, dry_run=False, uninstall=False, cfg=cfg)

        assert rc == 0
        mock_run.assert_called_once()
        argv_passed = mock_run.call_args[0][0]
        assert "schtasks" in argv_passed[0]
        assert "/Create" in argv_passed
        assert "ResearchHubNLMKeepalive" in " ".join(argv_passed)
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
            rc = ka_mod.run_install_windows_task(6, dry_run=False, uninstall=True, cfg=cfg)

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
            rc = ka_mod.run_install_windows_task(6, dry_run=False, uninstall=False, cfg=None)

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
            rc = ka_mod.run_install_windows_task(6, dry_run=True, uninstall=False, cfg=cfg)

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
            rc = ka_mod.run_install_windows_task(6, dry_run=True, uninstall=False, cfg=cfg)

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
            rc = ka_mod.run_install_windows_task(6, dry_run=False, uninstall=False, cfg=cfg)

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
            rc = ka_mod.run_install_windows_task(6, dry_run=False, uninstall=True, cfg=cfg)

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
