"""v0.40 onboarding hardening tests."""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests._mcp_helpers import _get_mcp_tool
from tests._persona_factory import make_persona_vault


def test_readme_persona_table_includes_correct_extra():
    readme = Path("README.md").read_text(encoding="utf-8")
    expected = {
        "Researcher": "playwright,secrets",
        "Humanities": "playwright,secrets",
        "Analyst": "import,secrets",
        "Internal KM": "import,secrets",
    }
    for persona, extra in expected.items():
        assert re.search(
            rf"{re.escape(persona)}.*\[{re.escape(extra)}\]",
            readme,
            re.IGNORECASE | re.DOTALL,
        )


def test_onboarding_doc_does_not_reference_removed_field_flag():
    doc = Path("docs/onboarding.md").read_text(encoding="utf-8")
    assert "--field" not in doc


def test_onboarding_doc_mentions_all_4_personas():
    doc = Path("docs/onboarding.md").read_text(encoding="utf-8").lower()
    for persona in ("researcher", "humanities", "analyst", "internal"):
        assert persona in doc


def test_init_wizard_retries_zotero_credentials_on_validation_failure(tmp_path, monkeypatch, capsys):
    from research_hub import init_wizard

    config_dir = tmp_path / "config"
    prompts: list[str] = []
    answers = iter(
        [
            "y",  # Q0: do you use Zotero?
            "1",  # persona menu in Zotero branch -> researcher
            str(tmp_path / "vault"),
            "bad-key",
            "111",
            "r",
            "good-key",
            "222",
            "n",
        ]
    )
    statuses = iter([403, 200])

    monkeypatch.setattr(init_wizard.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(
        init_wizard.platformdirs,
        "user_config_dir",
        lambda *args, **kwargs: str(config_dir),
    )
    monkeypatch.setattr("builtins.input", lambda prompt="": prompts.append(prompt) or next(answers))
    monkeypatch.setattr("requests.head", lambda *args, **kwargs: SimpleNamespace(status_code=next(statuses)))
    monkeypatch.setattr(
        "research_hub.notebooklm.cdp_launcher.find_chrome_binary",
        lambda: "C:/Chrome/chrome.exe",
    )

    assert init_wizard.run_init() == 0

    output = capsys.readouterr().out
    assert "returned 403" in output
    assert "Zotero credentials: OK" in output
    assert "    [r]etry / [c]ontinue offline / [a]bort? " in prompts
    assert "    Re-enter Zotero API key: " in prompts
    assert "    Re-enter Zotero library ID: " in prompts


def test_init_wizard_aborts_when_user_aborts_after_network_failure(tmp_path, monkeypatch, capsys):
    from research_hub import init_wizard

    config_dir = tmp_path / "config"
    answers = iter(
        [
            "y",  # Q0: do you use Zotero?
            "1",  # persona menu in Zotero branch -> researcher
            str(tmp_path / "vault"),
            "key",
            "111",
            "a",
        ]
    )

    monkeypatch.setattr(init_wizard.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(
        init_wizard.platformdirs,
        "user_config_dir",
        lambda *args, **kwargs: str(config_dir),
    )
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    monkeypatch.setattr(
        "requests.head",
        lambda *args, **kwargs: (_ for _ in ()).throw(ConnectionError("boom")),
    )
    monkeypatch.setattr(
        "research_hub.notebooklm.cdp_launcher.find_chrome_binary",
        lambda: "C:/Chrome/chrome.exe",
    )

    assert init_wizard.run_init() == 1
    assert "could not reach api.zotero.org" in capsys.readouterr().out
    assert not (config_dir / "config.json").exists()


def test_import_folder_fails_fast_when_pdfplumber_missing(tmp_path, monkeypatch, capsys):
    target = tmp_path / "docs"
    target.mkdir()
    (target / "doc.pdf").write_bytes(b"%PDF-1.0")

    import sys

    monkeypatch.setitem(sys.modules, "pdfplumber", None)
    monkeypatch.setattr("research_hub.cli._import_folder_command", lambda args: pytest.fail("import should not run"))

    from research_hub.cli import main

    rc = main(["import-folder", str(target), "--cluster", "test"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "pdfplumber" in err
    assert "[import]" in err


def test_import_folder_passes_precheck_when_only_md_files(tmp_path, monkeypatch):
    target = tmp_path / "docs"
    target.mkdir()
    (target / "note.md").write_text("# Note", encoding="utf-8")

    import sys

    called: list[str] = []
    monkeypatch.setitem(sys.modules, "pdfplumber", None)
    monkeypatch.setattr("research_hub.cli._import_folder_command", lambda args: called.append(args.folder) or 0)

    from research_hub.cli import main

    assert main(["import-folder", str(target), "--cluster", "test"]) == 0
    assert called == [str(target)]


def test_mcp_ask_cluster_returns_structured_error_on_unknown_cluster(tmp_path, monkeypatch):
    from research_hub import mcp_server

    cfg, _ = make_persona_vault(tmp_path, persona="A")
    monkeypatch.setattr("research_hub.mcp_server.get_config", lambda: cfg)
    result = _get_mcp_tool(mcp_server.mcp, "ask_cluster").fn(
        cluster_slug="nonexistent-cluster-xyz",
        question="what is this?",
    )
    assert result["ok"] is False
    assert "hint" in result


def test_mcp_summarize_rebind_status_handles_empty_vault(tmp_path, monkeypatch):
    from research_hub import mcp_server

    cfg, _ = make_persona_vault(tmp_path, persona="A")
    monkeypatch.setattr("research_hub.mcp_server.get_config", lambda: cfg)
    result = _get_mcp_tool(mcp_server.mcp, "summarize_rebind_status").fn()
    assert "total_orphans" in result or result.get("ok") is False


def test_mcp_server_imports_for_all_4_personas(tmp_path, monkeypatch):
    from research_hub import mcp_server

    assert mcp_server.mcp is not None
    for persona in ("A", "B", "C", "H"):
        persona_root = tmp_path / persona.lower()
        cfg, _ = make_persona_vault(persona_root, persona=persona)
        monkeypatch.setattr("research_hub.mcp_server.get_config", lambda cfg=cfg: cfg)
        list_orphans = _get_mcp_tool(mcp_server.mcp, "list_orphan_papers").fn()
        assert "count" in list_orphans
