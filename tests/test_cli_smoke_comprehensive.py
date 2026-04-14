from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from research_hub.cli import main
from research_hub.clusters import ClusterRegistry


SUBCOMMANDS_THAT_MUST_EXIST = [
    "init",
    "doctor",
    "ingest",
    "clusters",
    "topic",
    "remove",
    "mark",
    "move",
    "add",
    "find",
    "label",
    "label-bulk",
    "search",
    "enrich",
    "references",
    "cited-by",
    "suggest",
    "cite",
    "quote",
    "compose-draft",
    "status",
    "dashboard",
    "migrate-yaml",
    "verify",
    "cleanup",
    "synthesize",
    "sync",
    "pipeline",
    "notebooklm",
    "fit-check",
    "autofill",
    "paper",
    "discover",
]


class _Cfg:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.raw = root / "raw"
        self.hub = root / "hub"
        self.research_hub_dir = root / ".research_hub"
        self.clusters_file = self.research_hub_dir / "clusters.yaml"
        self.no_zotero = False
        self.raw.mkdir(parents=True, exist_ok=True)
        self.hub.mkdir(parents=True, exist_ok=True)
        self.research_hub_dir.mkdir(parents=True, exist_ok=True)


def _make_cfg(tmp_path: Path) -> _Cfg:
    return _Cfg(tmp_path / "vault")


def _write_note(cfg: _Cfg, cluster_slug: str, slug: str, *, body: str = "TODO") -> Path:
    note_dir = cfg.raw / cluster_slug
    note_dir.mkdir(parents=True, exist_ok=True)
    path = note_dir / f"{slug}.md"
    path.write_text(
        "---\n"
        f'title: "{slug.title()}"\n'
        'authors: "Doe, Jane"\n'
        'year: "2025"\n'
        'doi: "10.1000/example"\n'
        f'topic_cluster: "{cluster_slug}"\n'
        "---\n\n"
        f"{body}\n",
        encoding="utf-8",
    )
    return path


@pytest.mark.parametrize("subcmd", SUBCOMMANDS_THAT_MUST_EXIST)
def test_cli_subcommand_help_exits_zero(subcmd):
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"src{os.pathsep}{existing}" if existing else "src"
    result = subprocess.run(
        [sys.executable, "-m", "research_hub", subcmd, "--help"],
        capture_output=True,
        text=True,
        timeout=15,
        env=env,
    )
    assert result.returncode == 0, f"`{subcmd} --help` exited {result.returncode}: {result.stderr[:200]}"


def test_cli_discover_new_dry_run(tmp_path, monkeypatch, capsys):
    cfg = _make_cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(query="agents", name="Agents", slug="agents")

    class _State:
        candidate_count = 2

    monkeypatch.setattr("research_hub.cli.get_config", lambda: cfg)
    monkeypatch.setattr("research_hub.discover.discover_new", lambda *args, **kwargs: (_State(), "PROMPT"))

    rc = main(["discover", "new", "--cluster", "agents", "--query", "agent memory"])

    assert rc == 0
    assert "PROMPT" in capsys.readouterr().out


def test_cli_fit_check_emit_prompt(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    candidates = tmp_path / "candidates.json"
    out = tmp_path / "fit_prompt.txt"
    candidates.write_text("[]", encoding="utf-8")
    monkeypatch.setattr("research_hub.cli.get_config", lambda: cfg)
    monkeypatch.setattr("research_hub.fit_check.emit_prompt", lambda *args, **kwargs: "FIT PROMPT")

    rc = main(["fit-check", "emit", "--cluster", "agents", "--candidates", str(candidates), "--out", str(out)])

    assert rc == 0
    assert out.read_text(encoding="utf-8") == "FIT PROMPT"


def test_cli_fit_check_apply_scores(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    candidates = tmp_path / "candidates.json"
    scored = tmp_path / "scores.json"
    out = tmp_path / "accepted.json"
    candidates.write_text("[]", encoding="utf-8")
    scored.write_text("[]", encoding="utf-8")

    class _Accepted:
        def to_dict(self):
            return {"slug": "paper-one"}

    class _Report:
        accepted = [_Accepted()]

        def summary(self):
            return "1 accepted"

    monkeypatch.setattr("research_hub.cli.get_config", lambda: cfg)
    monkeypatch.setattr("research_hub.fit_check.apply_scores", lambda *args, **kwargs: _Report())

    rc = main(
        [
            "fit-check",
            "apply",
            "--cluster",
            "agents",
            "--candidates",
            str(candidates),
            "--scored",
            str(scored),
            "--out",
            str(out),
        ]
    )

    assert rc == 0
    assert json.loads(out.read_text(encoding="utf-8")) == [{"slug": "paper-one"}]


def test_cli_autofill_emit(tmp_path, monkeypatch, capsys):
    cfg = _make_cfg(tmp_path)
    monkeypatch.setattr("research_hub.cli.get_config", lambda: cfg)
    monkeypatch.setattr("research_hub.autofill.emit_autofill_prompt", lambda *args, **kwargs: "AUTOFILL PROMPT")
    monkeypatch.setattr("research_hub.autofill.find_todo_papers", lambda *args, **kwargs: ["p1", "p2"])

    rc = main(["autofill", "emit", "--cluster", "agents"])

    assert rc == 0
    assert "AUTOFILL PROMPT" in capsys.readouterr().out


def test_cli_autofill_apply(tmp_path, monkeypatch, capsys):
    cfg = _make_cfg(tmp_path)
    scored = tmp_path / "scored.json"
    scored.write_text("{}", encoding="utf-8")

    class _Result:
        filled = ["paper-one"]
        skipped = []
        missing = []

    monkeypatch.setattr("research_hub.cli.get_config", lambda: cfg)
    monkeypatch.setattr("research_hub.autofill.apply_autofill", lambda *args, **kwargs: _Result())

    rc = main(["autofill", "apply", "--cluster", "agents", "--scored", str(scored)])

    assert rc == 0
    assert "filled: 1" in capsys.readouterr().out


def test_cli_pipeline_repair_dry_run(tmp_path, monkeypatch, capsys):
    cfg = _make_cfg(tmp_path)

    class _Report:
        zotero_orphans = [{"key": "ABC"}]
        obsidian_orphans = ["raw/agents/orphan.md"]
        stale_dedup = ["10.1000/orphan"]
        created_notes = []

        def summary(self):
            return "repair summary"

    monkeypatch.setattr("research_hub.cli.get_config", lambda: cfg)
    monkeypatch.setattr("research_hub.cli.repair_cluster", lambda *args, **kwargs: _Report())

    rc = main(["pipeline", "repair", "--cluster", "agents", "--dry-run"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "repair summary" in out
    assert "Zotero orphan items" in out
    assert "Obsidian orphan notes" in out


def test_cli_compose_draft_with_zero_quotes_returns_helpful_error(tmp_path, monkeypatch, capsys):
    cfg = _make_cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(query="agents", name="Agents", slug="agents")
    monkeypatch.setattr("research_hub.cli.get_config", lambda: cfg)

    rc = main(["compose-draft", "--cluster", "agents"])

    assert rc == 1
    assert "No captured quotes found for cluster 'agents'" in capsys.readouterr().out


def test_cli_clusters_rename_updates_registry(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    registry = ClusterRegistry(cfg.clusters_file)
    registry.create(query="agents", name="Agents", slug="agents")
    monkeypatch.setattr("research_hub.cli.get_config", lambda: cfg)

    rc = main(["clusters", "rename", "agents", "--name", "Agent Systems"])

    assert rc == 0
    assert ClusterRegistry(cfg.clusters_file).get("agents").name == "Agent Systems"


def test_cli_topic_scaffold_writes_structured_template(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(query="agents", name="Agents", slug="agents")
    monkeypatch.setattr("research_hub.cli.get_config", lambda: cfg)

    rc = main(["topic", "scaffold", "--cluster", "agents"])

    assert rc == 0
    content = (cfg.hub / "agents" / "00_overview.md").read_text(encoding="utf-8")
    assert "## TL;DR" in content

