from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace


def _cfg(tmp_path: Path) -> SimpleNamespace:
    root = tmp_path / "vault"
    raw = root / "raw"
    raw.mkdir(parents=True)
    return SimpleNamespace(raw=raw)


def test_auto_errors_on_nonempty_cluster_without_force_or_append(tmp_path, monkeypatch, capsys):
    from research_hub.cli import _auto

    cfg = _cfg(tmp_path)
    cluster = cfg.raw / "agents"
    cluster.mkdir()
    (cluster / "paper.md").write_text("x", encoding="utf-8")
    monkeypatch.setattr("research_hub.cli.get_config", lambda: cfg)
    monkeypatch.setattr("research_hub.auto.auto_pipeline", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not run")))

    rc = _auto(topic="x", cluster_slug="agents", cluster_name=None, max_papers=1, field=None, do_nlm=False, do_crystals=False, llm_cli=None, dry_run=False)
    assert rc == 2
    assert "already has 1 paper(s)" in capsys.readouterr().out


def test_auto_proceeds_with_append_flag(tmp_path, monkeypatch):
    from research_hub.cli import _auto

    cfg = _cfg(tmp_path)
    cluster = cfg.raw / "agents"
    cluster.mkdir()
    (cluster / "paper.md").write_text("x", encoding="utf-8")
    monkeypatch.setattr("research_hub.cli.get_config", lambda: cfg)
    monkeypatch.setattr(
        "research_hub.auto.auto_pipeline",
        lambda *args, **kwargs: SimpleNamespace(ok=True, error=""),
    )
    assert _auto(topic="x", cluster_slug="agents", cluster_name=None, max_papers=1, field=None, do_nlm=False, do_crystals=False, llm_cli=None, dry_run=False, append=True) == 0


def test_auto_proceeds_with_force_flag(tmp_path, monkeypatch):
    from research_hub.cli import _auto

    cfg = _cfg(tmp_path)
    cluster = cfg.raw / "agents"
    cluster.mkdir()
    (cluster / "paper.md").write_text("x", encoding="utf-8")
    monkeypatch.setattr("research_hub.cli.get_config", lambda: cfg)
    monkeypatch.setattr(
        "research_hub.auto.auto_pipeline",
        lambda *args, **kwargs: SimpleNamespace(ok=True, error=""),
    )
    assert _auto(topic="x", cluster_slug="agents", cluster_name=None, max_papers=1, field=None, do_nlm=False, do_crystals=False, llm_cli=None, dry_run=False, force=True) == 0
