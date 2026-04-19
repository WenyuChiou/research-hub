"""v0.37 memory CLI subcommand tests."""

from __future__ import annotations

import json

import pytest

from tests._persona_factory import make_persona_vault


def test_memory_emit_cli_outputs_prompt(tmp_path, capsys, monkeypatch):
    from research_hub.cli import main

    cfg, _ = make_persona_vault(tmp_path, persona="A")
    monkeypatch.setattr("research_hub.cli.get_config", lambda: cfg)
    main(["memory", "emit", "--cluster", "persona-a-test"])
    out = capsys.readouterr().out
    assert "Cluster memory extraction" in out
    assert "persona-a-test" in out


def test_memory_apply_cli_writes_registry(tmp_path, capsys, monkeypatch):
    from research_hub.cli import main
    from research_hub.crystal import _read_cluster_papers

    cfg, _ = make_persona_vault(tmp_path, persona="A")
    monkeypatch.setattr("research_hub.cli.get_config", lambda: cfg)
    paper_slug = _read_cluster_papers(cfg, "persona-a-test")[0]["slug"]
    payload = {
        "entities": [{"slug": "openai", "name": "OpenAI", "type": "org", "papers": [paper_slug]}],
        "claims": [{"slug": "rlhf", "text": "RLHF.", "confidence": "high", "papers": [paper_slug]}],
        "methods": [{"slug": "rlhf-method", "name": "RLHF", "family": "rl", "papers": [paper_slug]}],
    }
    scored = tmp_path / "memory.json"
    scored.write_text(json.dumps(payload), encoding="utf-8")
    main(["memory", "apply", "--cluster", "persona-a-test", "--scored", str(scored)])
    out = capsys.readouterr().out
    assert "entities=1" in out
    assert "claims=1" in out
    assert "methods=1" in out


def test_memory_list_cli_entities(tmp_path, capsys, monkeypatch):
    from research_hub.cli import main
    from research_hub.crystal import _read_cluster_papers
    from research_hub.memory import apply_memory

    cfg, _ = make_persona_vault(tmp_path, persona="A")
    monkeypatch.setattr("research_hub.cli.get_config", lambda: cfg)
    paper_slug = _read_cluster_papers(cfg, "persona-a-test")[0]["slug"]
    apply_memory(
        cfg,
        "persona-a-test",
        {
            "entities": [{"slug": "openai", "name": "OpenAI", "type": "org", "papers": [paper_slug]}],
        },
    )
    main(["memory", "list", "--cluster", "persona-a-test", "--kind", "entities"])
    out = capsys.readouterr().out
    assert "openai" in out
    assert "OpenAI" in out


def test_memory_read_cli_returns_full_registry(tmp_path, capsys, monkeypatch):
    from research_hub.cli import main
    from research_hub.crystal import _read_cluster_papers
    from research_hub.memory import apply_memory

    cfg, _ = make_persona_vault(tmp_path, persona="A")
    monkeypatch.setattr("research_hub.cli.get_config", lambda: cfg)
    paper_slug = _read_cluster_papers(cfg, "persona-a-test")[0]["slug"]
    apply_memory(
        cfg,
        "persona-a-test",
        {
            "entities": [{"slug": "x", "name": "X", "type": "org", "papers": [paper_slug]}],
        },
    )
    main(["memory", "read", "--cluster", "persona-a-test"])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["cluster_slug"] == "persona-a-test"
    assert len(data["entities"]) == 1


def test_memory_read_cli_missing_returns_nonzero(tmp_path, capsys, monkeypatch):
    from research_hub.cli import main

    cfg, _ = make_persona_vault(tmp_path, persona="A")
    (cfg.hub / "persona-a-test" / "memory.json").unlink()
    monkeypatch.setattr("research_hub.cli.get_config", lambda: cfg)
    rc = main(["memory", "read", "--cluster", "persona-a-test"])
    err = capsys.readouterr().err
    assert rc == 1
    assert "No memory found" in err


def test_memory_emit_unknown_cluster_raises(tmp_path, monkeypatch):
    from research_hub.cli import main

    cfg, _ = make_persona_vault(tmp_path, persona="A")
    monkeypatch.setattr("research_hub.cli.get_config", lambda: cfg)
    with pytest.raises((ValueError, SystemExit)):
        main(["memory", "emit", "--cluster", "nonexistent"])
