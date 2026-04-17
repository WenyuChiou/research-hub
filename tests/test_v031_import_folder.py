from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from research_hub.clusters import ClusterRegistry
from tests._mcp_helpers import _get_mcp_tool, _list_mcp_tool_names


def _make_cfg(tmp_path: Path):
    root = tmp_path / "vault"
    raw = root / "raw"
    research_hub_dir = root / ".research_hub"
    raw.mkdir(parents=True)
    research_hub_dir.mkdir(parents=True)
    return SimpleNamespace(
        root=root,
        raw=raw,
        research_hub_dir=research_hub_dir,
        clusters_file=research_hub_dir / "clusters.yaml",
    )


def test_import_folder_walks_md_and_txt(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "note1.md").write_text("# First Note\n\nSome content.", encoding="utf-8")
    (src / "note2.txt").write_text("Plain text content here.", encoding="utf-8")

    cfg = _make_cfg(tmp_path)

    from research_hub.importer import import_folder

    report = import_folder(cfg, src, cluster_slug="demo-cluster", extensions=("md", "txt"))

    assert report.imported_count == 2
    assert report.failed_count == 0
    written = sorted((cfg.raw / "demo-cluster").glob("*.md"))
    assert len(written) == 2


def test_import_folder_dedupes_by_content_hash(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "note.md").write_text("# Same\n\nSame content.", encoding="utf-8")

    cfg = _make_cfg(tmp_path)

    from research_hub.importer import import_folder

    first = import_folder(cfg, src, cluster_slug="dedup-test", extensions=("md",))
    second = import_folder(cfg, src, cluster_slug="dedup-test", extensions=("md",))

    assert first.imported_count == 1
    assert second.imported_count == 0
    assert second.skipped_count == 1
    assert second.entries[0].status == "skipped_duplicate"


def test_import_folder_writes_document_frontmatter(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "doc.md").write_text("# A Document\n\nBody here.", encoding="utf-8")

    cfg = _make_cfg(tmp_path)

    from research_hub.importer import import_folder

    report = import_folder(cfg, src, cluster_slug="fm-test", extensions=("md",))

    note = report.entries[0].note_path
    assert note is not None
    text = note.read_text(encoding="utf-8")
    assert "source_kind: markdown" in text
    assert "topic_cluster: fm-test" in text
    assert "ingestion_source: import-folder" in text
    assert "title: A Document" in text


def test_import_folder_dry_run_writes_nothing(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "doc.md").write_text("# Doc", encoding="utf-8")

    cfg = _make_cfg(tmp_path)

    from research_hub.importer import import_folder

    report = import_folder(cfg, src, cluster_slug="dry", extensions=("md",), dry_run=True)

    assert report.imported_count == 1
    assert report.entries[0].note_path is None
    assert not (cfg.raw / "dry").exists()


def test_import_folder_skips_unsupported_extensions(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "image.png").write_bytes(b"fakepng")

    cfg = _make_cfg(tmp_path)

    from research_hub.importer import import_folder

    report = import_folder(cfg, src, cluster_slug="skip-test")

    assert report.imported_count == 0
    assert report.entries[0].status == "skipped_unsupported"


def test_import_folder_handles_unicode_filename(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "測試文件.md").write_text("# Chinese Filename\n\nContent.", encoding="utf-8")

    cfg = _make_cfg(tmp_path)

    from research_hub.importer import import_folder

    report = import_folder(cfg, src, cluster_slug="unicode-test", extensions=("md",))

    assert report.imported_count == 1
    assert report.entries[0].slug == "chinese-filename"


def test_import_folder_creates_cluster_if_missing(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "x.md").write_text("# X", encoding="utf-8")

    cfg = _make_cfg(tmp_path)
    registry = ClusterRegistry(cfg.clusters_file)
    assert registry.get("brand-new") is None

    from research_hub.importer import import_folder

    report = import_folder(cfg, src, cluster_slug="brand-new", extensions=("md",))
    reloaded = ClusterRegistry(cfg.clusters_file)

    assert report.imported_count == 1
    assert reloaded.get("brand-new") is not None


def test_import_folder_validates_cluster_slug(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "x.md").write_text("# X", encoding="utf-8")

    cfg = _make_cfg(tmp_path)

    from research_hub.importer import import_folder
    from research_hub.security import ValidationError

    with pytest.raises(ValidationError):
        import_folder(cfg, src, cluster_slug="../../etc", extensions=("md",))


def test_cli_import_folder_parser_and_dispatch(tmp_path, monkeypatch, capsys):
    from research_hub.cli import build_parser, main

    args = build_parser().parse_args(["import-folder", "docs", "--cluster", "agents"])
    assert args.command == "import-folder"
    assert args.folder == "docs"
    assert args.cluster == "agents"

    monkeypatch.setattr("research_hub.cli.get_config", lambda: None, raising=False)
    monkeypatch.setattr("research_hub.cli._import_folder_command", lambda args: print("Import summary") or 0)

    rc = main(["import-folder", "docs", "--cluster", "agents"])

    assert rc == 0
    assert "Import summary" in capsys.readouterr().out


def test_mcp_import_folder_tool_registered_and_returns_summary(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    entries = [SimpleNamespace(path=Path("a.md"), status="imported", slug="a", error="")]
    monkeypatch.setattr("research_hub.config.require_config", lambda: cfg)
    monkeypatch.setattr(
        "research_hub.importer.import_folder",
        lambda *a, **k: SimpleNamespace(
            imported_count=1,
            skipped_count=0,
            failed_count=0,
            entries=entries,
        ),
    )

    from research_hub.mcp_server import mcp

    assert "import_folder_tool" in _list_mcp_tool_names(mcp)
    result = _get_mcp_tool(mcp, "import_folder_tool").fn(str(tmp_path / "src"), "agents", True)

    assert result["cluster"] == "agents"
    assert result["imported"] == 1
    assert result["entries"][0]["slug"] == "a"
