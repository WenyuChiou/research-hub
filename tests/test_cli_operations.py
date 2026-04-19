from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_hub.cli import build_parser, main
from research_hub.clusters import ClusterRegistry


class _TopicCfg:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.raw = root / "raw"
        self.hub = root / "hub"
        self.research_hub_dir = root / ".research_hub"
        self.clusters_file = self.research_hub_dir / "clusters.yaml"
        self.raw.mkdir(parents=True, exist_ok=True)
        self.hub.mkdir(parents=True, exist_ok=True)
        self.research_hub_dir.mkdir(parents=True, exist_ok=True)


def _setup_topic_cfg(tmp_path: Path) -> _TopicCfg:
    cfg = _TopicCfg(tmp_path / "vault")
    ClusterRegistry(cfg.clusters_file).create(query="agents", name="Agents", slug="agents")
    return cfg


@pytest.mark.parametrize(
    "argv",
    [
        ["remove", "--help"],
        ["mark", "--help"],
        ["move", "--help"],
        ["find", "--help"],
        ["dashboard", "--help"],
        ["quote", "--help"],
        ["references", "--help"],
        ["cited-by", "--help"],
        ["clusters", "rename", "--help"],
        ["clusters", "merge", "--help"],
    ],
)
def test_cli_help_commands(argv, capsys):
    parser = build_parser()

    with pytest.raises(SystemExit) as exc:
        parser.parse_args(argv)

    assert exc.value.code == 0
    assert "usage:" in capsys.readouterr().out


def test_cite_parser_supports_inline_markdown_and_style():
    args = build_parser().parse_args(["cite", "10.1000/example", "--inline", "--style", "chicago"])
    assert args.inline is True
    assert args.markdown is False
    assert args.style == "chicago"


def test_quote_parser_supports_list_and_remove_shapes():
    parser = build_parser()
    list_args = parser.parse_args(["quote", "list", "--cluster", "agents"])
    remove_args = parser.parse_args(["quote", "remove", "paper-one", "--at", "2026-04-12T12:00:00Z"])
    add_args = parser.parse_args(["quote", "paper-one", "--page", "12", "--text", "hello"])
    assert list_args.quote_target == ["list"]
    assert remove_args.quote_target == ["remove", "paper-one"]
    assert add_args.quote_target == ["paper-one"]


def test_cli_topic_scaffold_creates_file(tmp_path, monkeypatch, capsys):
    cfg = _setup_topic_cfg(tmp_path)
    monkeypatch.setattr("research_hub.cli.get_config", lambda: cfg)

    assert main(["topic", "scaffold", "--cluster", "agents", "--force"]) == 0

    out = capsys.readouterr().out
    assert "wrote" in out
    assert (cfg.hub / "agents" / "00_overview.md").exists()


def test_cli_topic_digest_prints_to_stdout_when_no_out(tmp_path, monkeypatch, capsys):
    cfg = _setup_topic_cfg(tmp_path)
    monkeypatch.setattr("research_hub.cli.get_config", lambda: cfg)
    note_dir = cfg.raw / "agents"
    note_dir.mkdir(parents=True, exist_ok=True)
    (note_dir / "paper-one.md").write_text(
        '---\ntitle: "Paper One"\nauthors: "Doe, Jane"\nyear: "2025"\ndoi: "10.1/one"\n---\n\n## Abstract\nDigest me.\n',
        encoding="utf-8",
    )

    assert main(["topic", "digest", "--cluster", "agents"]) == 0

    out = capsys.readouterr().out
    assert "# Agents" in out
    assert "### Paper One" in out
    assert "> Digest me." in out


def test_cli_topic_show_returns_1_when_missing_overview(tmp_path, monkeypatch, capsys):
    cfg = _setup_topic_cfg(tmp_path)
    (cfg.hub / "agents" / "00_overview.md").unlink()
    monkeypatch.setattr("research_hub.cli.get_config", lambda: cfg)

    assert main(["topic", "show", "--cluster", "agents"]) == 1

    err = capsys.readouterr().err
    assert "no overview" in err


def test_cli_topic_build_generates_notes(tmp_path, monkeypatch):
    cfg = _setup_topic_cfg(tmp_path)
    monkeypatch.setattr("research_hub.cli.get_config", lambda: cfg)
    note_dir = cfg.raw / "agents"
    note_dir.mkdir(parents=True, exist_ok=True)
    (note_dir / "paper-one.md").write_text(
        '---\n'
        'title: "Paper One"\n'
        'authors: "Doe, Jane"\n'
        'year: "2025"\n'
        'doi: "10.1/one"\n'
        "---\n\n"
        "## Abstract\n"
        "Paper one abstract.\n",
        encoding="utf-8",
    )
    (note_dir / "paper-two.md").write_text(
        '---\n'
        'title: "Paper Two"\n'
        'authors: "Roe, Alex"\n'
        'year: "2024"\n'
        'doi: "10.1/two"\n'
        "---\n\n"
        "## Abstract\n"
        "Paper two abstract.\n",
        encoding="utf-8",
    )

    proposed = tmp_path / "proposed.json"
    proposed.write_text(
        json.dumps(
            {
                "subtopics": [
                    {"slug": "benchmarks", "title": "Benchmarks", "description": "d"},
                    {"slug": "agent-interfaces", "title": "Agent Interfaces", "description": "d"},
                ]
            }
        ),
        encoding="utf-8",
    )
    assignments = tmp_path / "assignments.json"
    assignments.write_text(
        json.dumps(
            {
                "assignments": {
                    "paper-one": ["benchmarks"],
                    "paper-two": ["agent-interfaces"],
                }
            }
        ),
        encoding="utf-8",
    )

    assert main(["topic", "propose", "--cluster", "agents"]) == 0
    assert main(["topic", "assign", "emit", "--cluster", "agents", "--subtopics", str(proposed)]) == 0
    assert main(["topic", "assign", "apply", "--cluster", "agents", "--assignments", str(assignments)]) == 0
    assert main(["topic", "build", "--cluster", "agents"]) == 0

    topics_dir = cfg.raw / "agents" / "topics"
    assert (topics_dir / "01_agent-interfaces.md").exists()
    assert (topics_dir / "02_benchmarks.md").exists()
