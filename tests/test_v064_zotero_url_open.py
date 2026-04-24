from __future__ import annotations

from pathlib import Path

from research_hub import init_wizard


def _patch_init_runtime(monkeypatch, tmp_path: Path) -> Path:
    config_dir = tmp_path / "config"
    monkeypatch.setattr(init_wizard.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(init_wizard.Path, "home", classmethod(lambda cls: tmp_path / "home"))
    monkeypatch.setattr(
        init_wizard.platformdirs,
        "user_config_dir",
        lambda *args, **kwargs: str(config_dir),
    )
    monkeypatch.setattr("requests.head", lambda *args, **kwargs: type("Resp", (), {"status_code": 200})())
    monkeypatch.setattr(
        init_wizard,
        "_check_first_run_readiness",
        lambda vault, *, persona, has_zotero: [("chrome", "OK", "ready")],
    )
    monkeypatch.setattr("research_hub.setup_command.run_notebooklm_login", lambda: None)
    return config_dir


def test_zotero_url_opens_when_interactive(monkeypatch, tmp_path):
    _patch_init_runtime(monkeypatch, tmp_path)
    answers = iter(["y", "1", str(tmp_path / "vault"), "z-key", "123"])
    opens: list[str] = []

    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    monkeypatch.setattr("webbrowser.open", lambda url: opens.append(url))

    assert init_wizard.run_init() == 0
    assert opens == ["https://www.zotero.org/settings/keys"]


def test_no_browser_flag_suppresses_open(monkeypatch, tmp_path):
    _patch_init_runtime(monkeypatch, tmp_path)
    answers = iter(["y", "1", str(tmp_path / "vault"), "z-key", "123"])
    opens: list[str] = []

    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    monkeypatch.setattr("webbrowser.open", lambda url: opens.append(url))

    assert init_wizard.run_init(no_browser=True) == 0
    assert opens == []


def test_webbrowser_failure_does_not_break_init(monkeypatch, tmp_path):
    _patch_init_runtime(monkeypatch, tmp_path)
    answers = iter(["y", "1", str(tmp_path / "vault"), "z-key", "123"])

    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    def _raise(_url):
        raise Exception("browser failed")

    monkeypatch.setattr("webbrowser.open", _raise)

    assert init_wizard.run_init() == 0
