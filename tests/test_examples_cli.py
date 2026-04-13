from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from research_hub.clusters import ClusterRegistry


@dataclass
class StubConfig:
    root: Path
    raw: Path
    research_hub_dir: Path
    clusters_file: Path


def make_config(tmp_path: Path) -> StubConfig:
    root = tmp_path / "vault"
    raw = root / "raw"
    research_hub_dir = root / ".research_hub"
    raw.mkdir(parents=True)
    research_hub_dir.mkdir(parents=True)
    return StubConfig(
        root=root,
        raw=raw,
        research_hub_dir=research_hub_dir,
        clusters_file=research_hub_dir / "clusters.yaml",
    )


def test_cli_examples_list_prints_4_lines(capsys):
    from research_hub import cli

    rc = cli.main(["examples", "list"])

    out = capsys.readouterr().out.strip().splitlines()
    assert rc == 0
    assert len(out) == 4


def test_cli_examples_show_unknown_returns_2(capsys):
    from research_hub import cli

    rc = cli.main(["examples", "show", "missing"])

    err = capsys.readouterr().err
    assert rc == 2
    assert "unknown example" in err


def test_cli_examples_copy_creates_cluster(tmp_path, monkeypatch, capsys):
    from research_hub import cli

    cfg = make_config(tmp_path)
    monkeypatch.setattr("research_hub.cli.get_config", lambda: cfg)

    rc = cli.main(["examples", "copy", "cs_swe", "--cluster", "test-swe"])

    out = capsys.readouterr().out
    assert rc == 0
    assert "copied cs_swe as cluster test-swe" in out
    assert ClusterRegistry(cfg.clusters_file).get("test-swe") is not None


def test_cli_init_field_non_interactive(monkeypatch, capsys):
    from research_hub import cli

    class Result:
        cluster_slug = "x"
        candidate_count = 3
        next_steps = ["1. step"]

    monkeypatch.setattr("research_hub.cli.get_config", lambda: object())
    monkeypatch.setattr("research_hub.onboarding.run_field_wizard", lambda *args, **kwargs: Result())

    rc = cli.main(
        [
            "init",
            "--field",
            "cs",
            "--cluster",
            "x",
            "--name",
            "X",
            "--query",
            "Y",
            "--non-interactive",
        ]
    )

    out = capsys.readouterr().out
    assert rc == 0
    assert "Created cluster x with 3 candidates" in out
