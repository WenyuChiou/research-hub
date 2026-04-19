"""v0.49 — Next Steps banner + LLM CLI detection + crystal step graceful fallback.

These tests pin behavior added so the lazy-mode `auto` flow ends with a
copy-paste-ready handoff and the optional `--with-crystals` step degrades
cleanly when no LLM CLI is on PATH.
"""
from __future__ import annotations

import json

import pytest


def test_detect_llm_cli_returns_first_match(monkeypatch):
    from research_hub import auto as auto_mod

    fake_path = {"claude": None, "codex": "/usr/local/bin/codex", "gemini": "/usr/local/bin/gemini"}
    monkeypatch.setattr(auto_mod.shutil, "which", lambda name: fake_path.get(name))

    assert auto_mod.detect_llm_cli() == "codex"


def test_detect_llm_cli_returns_none_when_nothing_on_path(monkeypatch):
    from research_hub import auto as auto_mod

    monkeypatch.setattr(auto_mod.shutil, "which", lambda name: None)
    assert auto_mod.detect_llm_cli() is None


def test_extract_first_json_handles_fenced_block():
    from research_hub.auto import _extract_first_json

    text = (
        "Here is your JSON:\n\n```json\n"
        '{"crystals": [{"slug": "x", "tldr": "ok"}]}\n'
        "```\nLet me know if you need anything else."
    )
    parsed = _extract_first_json(text)
    assert parsed is not None
    assert parsed["crystals"][0]["slug"] == "x"


def test_extract_first_json_handles_bare_object():
    from research_hub.auto import _extract_first_json

    parsed = _extract_first_json('  {"a": 1, "b": [2, 3]}  ')
    assert parsed == {"a": 1, "b": [2, 3]}


def test_extract_first_json_returns_none_on_garbage():
    from research_hub.auto import _extract_first_json

    assert _extract_first_json("no json here at all") is None
    assert _extract_first_json("") is None


def test_auto_pipeline_prints_next_steps(monkeypatch, capsys, tmp_path):
    """After a successful auto run, the Next Steps banner should appear."""
    from research_hub import auto as auto_mod

    # Stub all steps so we exercise only the banner code path
    cfg = type("Cfg", (), {})()
    cfg.clusters_file = tmp_path / "clusters.yaml"
    cfg.research_hub_dir = tmp_path / ".research_hub"
    cfg.root = tmp_path
    cfg.raw = tmp_path / "raw"
    cfg.raw.mkdir()
    (cfg.raw / "x").mkdir()
    (cfg.raw / "x" / "p1.md").write_text("paper", encoding="utf-8")

    monkeypatch.setattr(auto_mod, "get_config", lambda: cfg)

    class _Reg:
        def __init__(self, *a, **kw): pass
        def get(self, slug): return type("C", (), {"slug": slug, "name": slug})()
        def create(self, **kw): return type("C", (), {"slug": kw["slug"], "name": kw.get("name", "")})()

    monkeypatch.setattr(auto_mod, "ClusterRegistry", _Reg)
    monkeypatch.setattr(auto_mod, "_run_search", lambda topic, **kw: [{"slug": "p1"}])
    monkeypatch.setattr(auto_mod, "run_pipeline", lambda **kw: 0)

    report = auto_mod.auto_pipeline(
        "test topic",
        max_papers=1,
        do_nlm=False,
        do_crystals=False,
        print_progress=True,
    )
    out = capsys.readouterr().out
    assert report.ok
    assert "Next steps" in out
    assert "research-hub serve --dashboard" in out
    assert "research-hub crystal emit" in out
    assert "research-hub ask" in out


def test_auto_pipeline_crystal_step_falls_back_to_prompt_file(monkeypatch, tmp_path, capsys):
    """When --with-crystals is on but no LLM CLI is on PATH, save prompt + warn."""
    from research_hub import auto as auto_mod

    cfg = type("Cfg", (), {})()
    cfg.clusters_file = tmp_path / "clusters.yaml"
    cfg.research_hub_dir = tmp_path / ".research_hub"
    cfg.root = tmp_path
    cfg.raw = tmp_path / "raw"
    cfg.raw.mkdir()
    (cfg.raw / "x").mkdir()
    (cfg.raw / "x" / "p1.md").write_text("paper", encoding="utf-8")

    monkeypatch.setattr(auto_mod, "get_config", lambda: cfg)
    monkeypatch.setattr(auto_mod, "detect_llm_cli", lambda: None)
    monkeypatch.setattr(
        "research_hub.crystal.emit_crystal_prompt",
        lambda c, slug, **kw: "# fake prompt",
    )

    class _Reg:
        def __init__(self, *a, **kw): pass
        def get(self, slug): return type("C", (), {"slug": slug, "name": slug})()
        def create(self, **kw): return type("C", (), {"slug": kw["slug"], "name": kw.get("name", "")})()

    monkeypatch.setattr(auto_mod, "ClusterRegistry", _Reg)
    monkeypatch.setattr(auto_mod, "_run_search", lambda topic, **kw: [{"slug": "p1"}])
    monkeypatch.setattr(auto_mod, "run_pipeline", lambda **kw: 0)

    report = auto_mod.auto_pipeline(
        "test topic",
        max_papers=1,
        do_nlm=False,
        do_crystals=True,
        print_progress=False,
    )
    assert report.ok
    crystal_step = next(s for s in report.steps if s.name == "crystals")
    assert crystal_step.ok is False
    assert "no LLM CLI" in crystal_step.detail
    # prompt was saved for manual use
    prompt_path = cfg.research_hub_dir / "artifacts" / "test-topic" / "crystal-prompt.md"
    assert prompt_path.exists()
    assert prompt_path.read_text(encoding="utf-8") == "# fake prompt"


def test_auto_pipeline_crystal_step_invokes_detected_cli(monkeypatch, tmp_path):
    """With --with-crystals + a fake CLI, pipeline pipes prompt and applies response."""
    from research_hub import auto as auto_mod

    cfg = type("Cfg", (), {})()
    cfg.clusters_file = tmp_path / "clusters.yaml"
    cfg.research_hub_dir = tmp_path / ".research_hub"
    cfg.root = tmp_path
    cfg.raw = tmp_path / "raw"
    cfg.raw.mkdir()
    (cfg.raw / "x").mkdir()
    (cfg.raw / "x" / "p1.md").write_text("paper", encoding="utf-8")

    monkeypatch.setattr(auto_mod, "get_config", lambda: cfg)
    monkeypatch.setattr(auto_mod, "detect_llm_cli", lambda: "claude")
    monkeypatch.setattr(
        auto_mod, "_invoke_llm_cli",
        lambda cli, prompt, **kw: '{"crystals": [{"slug": "what-is-this-field", "tldr": "ok"}]}',
    )
    monkeypatch.setattr(
        "research_hub.crystal.emit_crystal_prompt",
        lambda c, slug, **kw: "# prompt",
    )

    applied = {}

    def _fake_apply(cfg, slug, parsed):
        applied["slug"] = slug
        applied["parsed"] = parsed
        return type("R", (), {"written_count": 1, "written": ["what-is-this-field"]})()

    monkeypatch.setattr("research_hub.crystal.apply_crystals", _fake_apply)

    class _Reg:
        def __init__(self, *a, **kw): pass
        def get(self, slug): return type("C", (), {"slug": slug, "name": slug})()
        def create(self, **kw): return type("C", (), {"slug": kw["slug"], "name": kw.get("name", "")})()

    monkeypatch.setattr(auto_mod, "ClusterRegistry", _Reg)
    monkeypatch.setattr(auto_mod, "_run_search", lambda topic, **kw: [{"slug": "p1"}])
    monkeypatch.setattr(auto_mod, "run_pipeline", lambda **kw: 0)

    report = auto_mod.auto_pipeline(
        "test topic",
        max_papers=1,
        do_nlm=False,
        do_crystals=True,
        print_progress=False,
    )
    crystal_step = next(s for s in report.steps if s.name == "crystals")
    assert crystal_step.ok is True
    assert "via claude" in crystal_step.detail
    assert applied["slug"] == "test-topic"
    assert applied["parsed"]["crystals"][0]["slug"] == "what-is-this-field"


def test_init_wizard_readiness_check_includes_obsidian_chrome_zotero(monkeypatch, tmp_path):
    """The first-run readiness probe should report on the four prerequisites."""
    from research_hub import init_wizard

    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / ".obsidian").mkdir()

    # Force patchright import to fail so we get a deterministic WARN
    import sys
    monkeypatch.setitem(sys.modules, "patchright.sync_api", None)
    monkeypatch.setattr(init_wizard.shutil, "which", lambda name: None)

    rows = init_wizard._check_first_run_readiness(vault, persona="researcher", has_zotero=True)
    subsystems = {sub for sub, _, _ in rows}
    assert subsystems == {"obsidian", "chrome", "zotero", "llm-cli"}

    obs_status = next(s for sub, s, _ in rows if sub == "obsidian")
    assert obs_status == "OK"  # .obsidian exists

    zot_status = next(s for sub, s, _ in rows if sub == "zotero")
    assert zot_status == "OK"  # has_zotero=True
