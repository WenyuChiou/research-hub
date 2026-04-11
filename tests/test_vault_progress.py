"""Tests for vault progress reporting."""

from __future__ import annotations

from pathlib import Path

from research_hub.clusters import ClusterRegistry
from research_hub.vault.progress import count_status_by_cluster, print_status_table


def _write_note(path: Path, frontmatter: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(frontmatter + "\nBody\n", encoding="utf-8")


def _write_clusters(path: Path) -> ClusterRegistry:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "clusters:\n"
        "  alpha:\n"
        "    name: Alpha Cluster\n"
        "    first_query: alpha\n"
        "  beta:\n"
        "    name: Beta Cluster\n"
        "    first_query: beta\n",
        encoding="utf-8",
    )
    return ClusterRegistry(path)


def test_count_status_by_cluster_empty_vault(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    assert count_status_by_cluster(raw_dir) == {}


def test_count_status_by_cluster_groups_by_cluster(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    _write_note(
        raw_dir / "a.md",
        '---\ntitle: "A"\ntopic_cluster: "alpha"\nstatus: unread\n---',
    )
    _write_note(
        raw_dir / "b.md",
        '---\ntitle: "B"\ntopic_cluster: "alpha"\nstatus: skim\n---',
    )
    _write_note(
        raw_dir / "c.md",
        '---\ntitle: "C"\ntopic_cluster: "beta"\nstatus: cited\n---',
    )

    result = count_status_by_cluster(raw_dir)

    assert result["alpha"]["unread"] == 1
    assert result["alpha"]["skim"] == 1
    assert result["beta"]["cited"] == 1


def test_count_status_by_cluster_counts_unassigned(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    _write_note(raw_dir / "legacy.md", '---\ntitle: "Legacy"\nstatus: unread\n---')

    result = count_status_by_cluster(raw_dir)

    assert result["__unassigned__"]["unread"] == 1


def test_count_status_by_cluster_defaults_unread(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    _write_note(raw_dir / "legacy.md", '---\ntitle: "Legacy"\ntopic_cluster: "alpha"\n---')

    result = count_status_by_cluster(raw_dir)

    assert result["alpha"]["unread"] == 1


def test_print_status_table_sorts_by_unread_desc(tmp_path: Path, capsys):
    raw_dir = tmp_path / "raw"
    registry = _write_clusters(tmp_path / ".research_hub" / "clusters.yaml")
    _write_note(
        raw_dir / "a.md",
        '---\ntitle: "A"\ntopic_cluster: "alpha"\nstatus: unread\n---',
    )
    _write_note(
        raw_dir / "b.md",
        '---\ntitle: "B"\ntopic_cluster: "alpha"\nstatus: unread\n---',
    )
    _write_note(
        raw_dir / "c.md",
        '---\ntitle: "C"\ntopic_cluster: "beta"\nstatus: unread\n---',
    )

    print_status_table(raw_dir, registry)
    output = capsys.readouterr().out.strip().splitlines()

    alpha_index = next(index for index, line in enumerate(output) if line.strip().startswith("alpha"))
    beta_index = next(index for index, line in enumerate(output) if line.strip().startswith("beta"))
    assert alpha_index < beta_index


def test_print_status_table_single_cluster_mode(tmp_path: Path, capsys):
    raw_dir = tmp_path / "raw"
    registry = _write_clusters(tmp_path / ".research_hub" / "clusters.yaml")
    _write_note(
        raw_dir / "a.md",
        '---\ntitle: "Alpha Paper"\ntopic_cluster: "alpha"\nstatus: unread\n---',
    )
    _write_note(
        raw_dir / "b.md",
        '---\ntitle: "Beta Paper"\ntopic_cluster: "beta"\nstatus: skim\n---',
    )

    print_status_table(raw_dir, registry, one_cluster="alpha")
    output = capsys.readouterr().out

    assert "Alpha Paper" in output
    assert "Beta Paper" not in output
    assert "Unread (1)" in output
