from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from research_hub.bootstrap_report import BootstrapReport
from research_hub.describe import ENV_VARS
from research_hub.setup_command import autonomous_exit_code, run_autonomous


def _set_env_vars(monkeypatch, *, missing: set[str] | None = None) -> None:
    missing = missing or set()
    for spec in ENV_VARS:
        name = spec["name"]
        monkeypatch.delenv(name, raising=False)
        if name in missing:
            continue
        if name == "ZOTERO_LIBRARY_ID":
            monkeypatch.setenv(name, "12345678")
        else:
            monkeypatch.setenv(name, f"test-{name.lower()}")


def test_run_autonomous_ready_when_required_env_and_zotero_probe_pass(tmp_path, monkeypatch):
    from research_hub import setup_command

    _set_env_vars(monkeypatch)
    monkeypatch.setattr(setup_command, "_probe_zotero_reachability", lambda _env: (True, ""))

    report = run_autonomous(vault=tmp_path, persona="agent")

    assert isinstance(report, BootstrapReport)
    assert report.persona == "agent"
    assert report.vault_exists is True
    assert report.env_vars_missing == []
    assert report.zotero_reachable is True
    assert report.ready is True
    assert autonomous_exit_code(report) == 0


def test_run_autonomous_reports_missing_required_env_without_zotero_probe(tmp_path, monkeypatch):
    from research_hub import setup_command

    _set_env_vars(monkeypatch, missing={"ZOTERO_API_KEY"})
    called = {"value": False}

    def _fake_probe(_env):
        called["value"] = True
        return True, ""

    monkeypatch.setattr(setup_command, "_probe_zotero_reachability", _fake_probe)

    report = run_autonomous(vault=tmp_path, persona="agent")

    assert "ZOTERO_API_KEY" in report.env_vars_missing
    assert report.zotero_reachable is False
    assert report.ready is False
    assert autonomous_exit_code(report) == 1
    assert called["value"] is False


def test_run_autonomous_nlm_auth_status_uses_state_file_presence_only(tmp_path, monkeypatch):
    from research_hub import setup_command

    _set_env_vars(monkeypatch)
    monkeypatch.setattr(setup_command, "_probe_zotero_reachability", lambda _env: (True, ""))
    monkeypatch.setattr(
        setup_command,
        "run_notebooklm_login",
        lambda: (_ for _ in ()).throw(AssertionError("NotebookLM login must not run")),
    )

    state_file = tmp_path / ".research_hub" / "nlm_sessions" / "state.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text('{"cookies": []}', encoding="utf-8")

    present = run_autonomous(vault=tmp_path, persona="agent")
    missing = run_autonomous(vault=tmp_path / "other", persona="agent")

    assert present.nlm_auth_status == "present"
    assert missing.nlm_auth_status == "missing"


def test_python_module_setup_autonomous_never_calls_input(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    src_path = repo_root / "src"
    patch_dir = tmp_path / "patch"
    patch_dir.mkdir(parents=True, exist_ok=True)
    (patch_dir / "sitecustomize.py").write_text(
        "import builtins\n"
        "def _boom(*_args, **_kwargs):\n"
        "    raise AssertionError('input() called')\n"
        "builtins.input = _boom\n",
        encoding="utf-8",
    )

    env = os.environ.copy()
    for spec in ENV_VARS:
        env.pop(spec["name"], None)
    env["PYTHONPATH"] = str(patch_dir) + os.pathsep + str(src_path) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["RESEARCH_HUB_ALLOW_EXTERNAL_ROOT"] = "1"

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "research_hub",
            "setup",
            "--autonomous",
            "--vault",
            str(tmp_path / "vault"),
            "--persona",
            "agent",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=5,
        check=False,
    )

    assert proc.returncode == 1
    assert "input() called" not in proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["persona"] == "agent"
    assert "ZOTERO_API_KEY" in payload["env_vars_missing"]
