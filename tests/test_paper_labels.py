from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest


def _cfg(tmp_path: Path) -> SimpleNamespace:
    root = tmp_path / "vault"
    raw = root / "raw"
    hub = root / "hub"
    research_hub_dir = root / ".research_hub"
    raw.mkdir(parents=True)
    hub.mkdir(parents=True)
    research_hub_dir.mkdir(parents=True)
    return SimpleNamespace(
        root=root,
        raw=raw,
        hub=hub,
        research_hub_dir=research_hub_dir,
        clusters_file=research_hub_dir / "clusters.yaml",
    )


def _write_note(cfg, cluster: str, slug: str, frontmatter: str, body: str = "Body\n") -> Path:
    note_dir = cfg.raw / cluster
    note_dir.mkdir(parents=True, exist_ok=True)
    path = note_dir / f"{slug}.md"
    path.write_text(f"---\n{frontmatter}\n---\n{body}", encoding="utf-8")
    return path


def _base_frontmatter(slug: str, cluster: str = "agents") -> str:
    return (
        f'title: "{slug}"\n'
        'doi: "10.1/test"\n'
        f'topic_cluster: "{cluster}"\n'
        'status: "unread"\n'
    )


def test_read_labels_returns_none_for_missing_slug(tmp_path):
    from research_hub.paper import read_labels

    assert read_labels(_cfg(tmp_path), "missing") is None


def test_read_labels_parses_inline_yaml_list(tmp_path):
    from research_hub.paper import read_labels

    cfg = _cfg(tmp_path)
    _write_note(cfg, "agents", "paper", _base_frontmatter("paper") + 'labels: ["seed", "benchmark"]')

    state = read_labels(cfg, "paper")

    assert state is not None
    assert state.labels == ["seed", "benchmark"]


def test_read_labels_parses_block_yaml_list(tmp_path):
    from research_hub.paper import read_labels

    cfg = _cfg(tmp_path)
    _write_note(cfg, "agents", "paper", _base_frontmatter("paper") + "labels:\n  - seed\n  - core")

    state = read_labels(cfg, "paper")

    assert state is not None
    assert state.labels == ["seed", "core"]


def test_read_labels_missing_labels_field_returns_empty(tmp_path):
    from research_hub.paper import read_labels

    cfg = _cfg(tmp_path)
    _write_note(cfg, "agents", "paper", _base_frontmatter("paper"))

    state = read_labels(cfg, "paper")

    assert state is not None
    assert state.labels == []


def test_set_labels_replaces_existing_list(tmp_path):
    from research_hub.paper import set_labels

    cfg = _cfg(tmp_path)
    _write_note(cfg, "agents", "paper", _base_frontmatter("paper") + "labels:\n  - seed\n  - survey")

    state = set_labels(cfg, "paper", labels=["core", "method"])

    assert state.labels == ["core", "method"]


def test_set_labels_add_appends_without_duplicates(tmp_path):
    from research_hub.paper import set_labels

    cfg = _cfg(tmp_path)
    _write_note(cfg, "agents", "paper", _base_frontmatter("paper") + "labels: [seed]")

    state = set_labels(cfg, "paper", add=["seed", "benchmark"])

    assert state.labels == ["seed", "benchmark"]


def test_set_labels_remove_preserves_others(tmp_path):
    from research_hub.paper import set_labels

    cfg = _cfg(tmp_path)
    _write_note(cfg, "agents", "paper", _base_frontmatter("paper") + "labels: [seed, deprecated, benchmark]")

    state = set_labels(cfg, "paper", remove=["deprecated"])

    assert state.labels == ["seed", "benchmark"]


def test_set_labels_updates_labeled_at_timestamp(tmp_path):
    from research_hub.paper import set_labels

    cfg = _cfg(tmp_path)
    _write_note(cfg, "agents", "paper", _base_frontmatter("paper"))

    state = set_labels(cfg, "paper", add=["seed"])

    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", state.labeled_at)


def test_set_labels_with_fit_score_and_reason(tmp_path):
    from research_hub.paper import set_labels

    cfg = _cfg(tmp_path)
    _write_note(cfg, "agents", "paper", _base_frontmatter("paper"))

    state = set_labels(cfg, "paper", add=["deprecated"], fit_score=1, fit_reason="off topic")

    assert state.fit_score == 1
    assert state.fit_reason == "off topic"


def test_set_labels_preserves_existing_frontmatter_keys(tmp_path):
    from research_hub.paper import set_labels

    cfg = _cfg(tmp_path)
    path = _write_note(
        cfg,
        "agents",
        "paper",
        _base_frontmatter("paper") + 'custom_field: "keep-me"',
    )

    set_labels(cfg, "paper", add=["seed"])

    assert 'custom_field: "keep-me"' in path.read_text(encoding="utf-8")


def test_set_labels_creates_labels_field_when_missing(tmp_path):
    from research_hub.paper import set_labels

    cfg = _cfg(tmp_path)
    path = _write_note(cfg, "agents", "paper", _base_frontmatter("paper"))

    set_labels(cfg, "paper", add=["seed"])

    assert "labels:" in path.read_text(encoding="utf-8")


def test_set_labels_raises_value_error_on_empty_slug(tmp_path):
    from research_hub.paper import set_labels

    with pytest.raises(ValueError):
        set_labels(_cfg(tmp_path), "   ", add=["seed"])


def test_list_papers_no_filter_returns_all_with_labels(tmp_path):
    from research_hub.paper import list_papers_by_label

    cfg = _cfg(tmp_path)
    _write_note(cfg, "agents", "one", _base_frontmatter("one") + "labels: [seed]")
    _write_note(cfg, "agents", "two", _base_frontmatter("two") + "labels: [core]")

    states = list_papers_by_label(cfg, "agents")

    assert [state.slug for state in states] == ["one", "two"]


def test_list_papers_by_label_filters_to_seed(tmp_path):
    from research_hub.paper import list_papers_by_label

    cfg = _cfg(tmp_path)
    _write_note(cfg, "agents", "one", _base_frontmatter("one") + "labels: [seed]")
    _write_note(cfg, "agents", "two", _base_frontmatter("two") + "labels: [core]")

    states = list_papers_by_label(cfg, "agents", label="seed")

    assert [state.slug for state in states] == ["one"]


def test_list_papers_label_not_excludes_deprecated(tmp_path):
    from research_hub.paper import list_papers_by_label

    cfg = _cfg(tmp_path)
    _write_note(cfg, "agents", "one", _base_frontmatter("one") + "labels: [seed]")
    _write_note(cfg, "agents", "two", _base_frontmatter("two") + "labels: [deprecated]")

    states = list_papers_by_label(cfg, "agents", label_not="deprecated")

    assert [state.slug for state in states] == ["one"]


def test_list_papers_skips_overview_and_index(tmp_path):
    from research_hub.paper import list_papers_by_label

    cfg = _cfg(tmp_path)
    _write_note(cfg, "agents", "paper", _base_frontmatter("paper"))
    _write_note(cfg, "agents", "00_overview", _base_frontmatter("overview"))
    _write_note(cfg, "agents", "index", _base_frontmatter("index"))

    states = list_papers_by_label(cfg, "agents")

    assert [state.slug for state in states] == ["paper"]


def test_list_papers_only_scans_target_cluster(tmp_path):
    from research_hub.paper import list_papers_by_label

    cfg = _cfg(tmp_path)
    _write_note(cfg, "agents", "paper", _base_frontmatter("paper", "agents"))
    _write_note(cfg, "other", "paper2", _base_frontmatter("paper2", "other"))

    states = list_papers_by_label(cfg, "agents")

    assert [state.slug for state in states] == ["paper"]


def test_list_papers_empty_cluster_returns_empty_list(tmp_path):
    from research_hub.paper import list_papers_by_label

    assert list_papers_by_label(_cfg(tmp_path), "missing") == []


def test_apply_fit_check_to_labels_no_sidecar_returns_empty(tmp_path):
    from research_hub.paper import apply_fit_check_to_labels

    assert apply_fit_check_to_labels(_cfg(tmp_path), "agents") == {"tagged": [], "already": [], "missing": []}


def test_apply_fit_check_to_labels_tags_deprecated(tmp_path):
    from research_hub.paper import apply_fit_check_to_labels, read_labels

    cfg = _cfg(tmp_path)
    _write_note(cfg, "agents", "paper", _base_frontmatter("paper") + 'doi: "10.1/a"')
    target = cfg.hub / "agents"
    target.mkdir(parents=True, exist_ok=True)
    (target / ".fit_check_rejected.json").write_text(
        json.dumps({"rejected": [{"doi": "10.1/a", "score": 1, "reason": "off topic"}]}),
        encoding="utf-8",
    )

    result = apply_fit_check_to_labels(cfg, "agents")
    state = read_labels(cfg, "paper")

    assert result["tagged"] == ["paper"]
    assert state is not None
    assert "deprecated" in state.labels
    assert state.fit_score == 1


def test_apply_fit_check_to_labels_skips_already_deprecated(tmp_path):
    from research_hub.paper import apply_fit_check_to_labels

    cfg = _cfg(tmp_path)
    _write_note(cfg, "agents", "paper", _base_frontmatter("paper") + 'doi: "10.1/a"\nlabels: [deprecated]')
    target = cfg.hub / "agents"
    target.mkdir(parents=True, exist_ok=True)
    (target / ".fit_check_rejected.json").write_text(
        json.dumps({"rejected": [{"doi": "10.1/a", "score": 1, "reason": "off topic"}]}),
        encoding="utf-8",
    )

    result = apply_fit_check_to_labels(cfg, "agents")

    assert result["already"] == ["paper"]


def test_apply_fit_check_to_labels_missing_papers_reported(tmp_path):
    from research_hub.paper import apply_fit_check_to_labels

    cfg = _cfg(tmp_path)
    target = cfg.hub / "agents"
    target.mkdir(parents=True, exist_ok=True)
    (target / ".fit_check_rejected.json").write_text(
        json.dumps({"rejected": [{"doi": "10.1/missing", "score": 1, "reason": "off topic"}]}),
        encoding="utf-8",
    )

    result = apply_fit_check_to_labels(cfg, "agents")

    assert result["missing"] == ["10.1/missing"]


def test_rewrite_preserves_closing_fence_newline(tmp_path):
    from research_hub.paper import _rewrite_paper_frontmatter

    cfg = _cfg(tmp_path)
    path = _write_note(cfg, "agents", "paper", _base_frontmatter("paper"), body="## Summary\nBody\n")

    _rewrite_paper_frontmatter(path, {"labels": ["seed"]})

    with path.open("r", encoding="utf-8", newline="") as handle:
        text = handle.read()
    assert re.search(r"\r?\n---\r?\n## Summary\r?\n", text)


def test_rewrite_preserves_unrelated_keys(tmp_path):
    from research_hub.paper import _rewrite_paper_frontmatter

    cfg = _cfg(tmp_path)
    path = _write_note(cfg, "agents", "paper", _base_frontmatter("paper") + 'note_type: "reference"')

    _rewrite_paper_frontmatter(path, {"labels": ["seed"]})

    assert 'note_type: "reference"' in path.read_text(encoding="utf-8")


def test_rewrite_handles_crlf_line_endings(tmp_path):
    from research_hub.paper import _rewrite_paper_frontmatter

    cfg = _cfg(tmp_path)
    path = cfg.raw / "agents" / "paper.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write("---\r\ntitle: \"paper\"\r\ntopic_cluster: \"agents\"\r\n---\r\nBody\r\n")

    _rewrite_paper_frontmatter(path, {"labels": ["seed"]})

    with path.open("r", encoding="utf-8", newline="") as handle:
        text = handle.read()
    assert "\r\n---\r\nBody" in text
    assert "labels:\r\n  - seed" in text
