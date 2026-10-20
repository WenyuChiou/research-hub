from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from research_hub.authenticity import list_quarantine_report


def _config(root: Path) -> SimpleNamespace:
    research_hub_dir = root / ".research_hub"
    research_hub_dir.mkdir(parents=True, exist_ok=True)
    return SimpleNamespace(research_hub_dir=research_hub_dir)


def test_missing_quarantine_directory_under_existing_root_is_known_empty(tmp_path):
    result = list_quarantine_report(_config(tmp_path))

    assert result.status == "empty"
    assert result.rows == []
    assert result.issue_count == 0


def test_missing_research_hub_root_is_unavailable(tmp_path):
    cfg = SimpleNamespace(research_hub_dir=tmp_path / ".research_hub")

    result = list_quarantine_report(cfg)

    assert result.status == "unavailable"
    assert result.rows == []
    assert result.issue_count is None


def test_malformed_and_unreadable_records_produce_partial_result(tmp_path, monkeypatch):
    cfg = _config(tmp_path)
    cluster_dir = cfg.research_hub_dir / "quarantine" / "agents"
    cluster_dir.mkdir(parents=True)
    (cluster_dir / "valid.json").write_text(
        json.dumps({"slug": "valid-paper", "reason": "held"}), encoding="utf-8"
    )
    (cluster_dir / "malformed.json").write_text("{not json", encoding="utf-8")
    unreadable_path = cluster_dir / "unreadable.json"
    unreadable_path.write_text(json.dumps({"slug": "unreadable-paper"}), encoding="utf-8")
    original_read_text = Path.read_text

    def read_text(path, *args, **kwargs):
        if path == unreadable_path:
            raise PermissionError("fixture unreadable record")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_text)

    result = list_quarantine_report(cfg)

    assert result.status == "partial"
    assert result.issue_count == 2
    assert [row["slug"] for row in result.rows] == ["valid-paper"]


def test_quarantine_directory_enumeration_failure_is_unavailable(tmp_path, monkeypatch):
    cfg = _config(tmp_path)
    quarantine_dir = cfg.research_hub_dir / "quarantine"
    quarantine_dir.mkdir()
    original_iterdir = Path.iterdir

    def iterdir(path):
        if path == quarantine_dir:
            raise PermissionError("fixture listing failure")
        return original_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", iterdir)

    result = list_quarantine_report(cfg)

    assert result.status == "unavailable"
    assert result.rows == []
    assert result.issue_count is None
