"""Security regression coverage for cluster slugs and auto-pipeline paths.

Every filesystem exercise uses pytest's isolated temporary directory. The tests
never load the operator's vault, call a real search backend, or invoke an LLM.
"""

from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from research_hub import auto, clusters, mcp_server, operations
from research_hub.clusters import Cluster, ClusterRegistry, cluster_slugify, slugify
from research_hub.obsidian_bases import base_path_for_cluster
from research_hub.security import ValidationError, safe_join


BAD_SLUGS = ("../outside", "a/b", "a\\b", "C:\\outside", "..", "bad\x00slug")


@pytest.fixture
def temp_dir():
    """Use an isolated stdlib temp directory (independent of pytest tmpdir hooks)."""
    # Keep it under this authorized workspace: the host's default Windows
    # temp path is not writable in every sandbox profile.
    with tempfile.TemporaryDirectory(
        prefix=".slug-test-", dir=Path(__file__).resolve().parent
    ) as directory:
        yield Path(directory)


def _cfg(root: Path) -> SimpleNamespace:
    return SimpleNamespace(
        root=root,
        raw=root / "raw",
        clusters_file=root / ".research_hub" / "clusters.yaml",
        llm_cli_adapters={},
    )


def _mock_symlink_lstat(monkeypatch, target: Path) -> None:
    """Mark one existing fixture path as a symlink without OS privileges."""
    real_lstat = Path.lstat

    def fake_lstat(path):
        if path == target:
            return SimpleNamespace(st_mode=stat.S_IFLNK, st_reparse_tag=0)
        return real_lstat(path)

    monkeypatch.setattr(Path, "lstat", fake_lstat)


def _active_cluster():
    return SimpleNamespace(status="active", zotero_collection_key="already-bound")


@pytest.mark.parametrize(
    "mode,reparse_tag",
    [(stat.S_IFLNK, 0), (stat.S_IFDIR, 0xA0000003)],
)
def test_safe_join_strict_rejects_symlink_and_junction_components(
    temp_dir, monkeypatch, mode, reparse_tag
):
    root = temp_dir / "vault"
    root.mkdir()
    alias = root / "cluster-alias"
    real_lstat = Path.lstat

    def fake_lstat(path):
        if path == alias:
            return SimpleNamespace(st_mode=mode, st_reparse_tag=reparse_tag)
        return real_lstat(path)

    monkeypatch.setattr(Path, "lstat", fake_lstat)
    with pytest.raises(ValidationError, match="symlink or reparse point"):
        safe_join(root, "cluster-alias", reject_symlinks=True)


def test_safe_join_strict_allows_unrelated_windows_reparse_tag(temp_dir, monkeypatch):
    root = temp_dir / "vault"
    root.mkdir()
    cloud_placeholder = root / "cloud-placeholder"
    real_lstat = Path.lstat

    def fake_lstat(path):
        if path == cloud_placeholder:
            return SimpleNamespace(st_mode=stat.S_IFREG, st_reparse_tag=0x9000001A)
        return real_lstat(path)

    monkeypatch.setattr(Path, "lstat", fake_lstat)
    assert safe_join(
        root, "cloud-placeholder", reject_symlinks=True
    ) == root.resolve() / "cloud-placeholder"


def test_move_paper_rejects_symlinked_source_note_before_frontmatter_write(
    temp_dir, monkeypatch
):
    raw = temp_dir / "raw"
    source_dir = raw / "source"
    archive_dir = raw / "archive"
    source_dir.mkdir(parents=True)
    archive_dir.mkdir()
    sentinel = archive_dir / "paper.md"
    original = "---\ntopic_cluster: archive\n---\nprivate note\n"
    sentinel.write_text(original, encoding="utf-8")
    source_link = source_dir / "paper.md"
    try:
        source_link.symlink_to(sentinel)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"file symlinks unavailable: {exc}")

    monkeypatch.setattr(operations, "get_config", lambda: SimpleNamespace(raw=raw))
    with pytest.raises(ValidationError, match="symlink or reparse point"):
        operations.move_paper(
            "paper", "target", source_path=source_link, raw_root=raw
        )

    assert source_link.is_symlink()
    assert sentinel.read_text(encoding="utf-8") == original
    assert not (raw / "target").exists()


def test_delete_rejects_symlinked_note_without_registry_mutation(
    temp_dir, monkeypatch
):
    raw = temp_dir / "raw"
    cluster_dir = raw / "safe-topic"
    archive_dir = raw / "archive"
    cluster_dir.mkdir(parents=True)
    archive_dir.mkdir()
    sentinel = archive_dir / "paper.md"
    original = "---\ntopic_cluster: archive\n---\nprivate note\n"
    sentinel.write_text(original, encoding="utf-8")
    try:
        (cluster_dir / "paper.md").symlink_to(sentinel)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"file symlinks unavailable: {exc}")

    cfg = SimpleNamespace(raw=raw)
    monkeypatch.setattr(clusters, "get_config", lambda: cfg)
    registry = ClusterRegistry(temp_dir / "clusters.yaml")
    cluster = Cluster(slug="safe-topic", name="Safe topic")
    registry.clusters[cluster.slug] = cluster
    saves = []
    monkeypatch.setattr(registry, "save", lambda: saves.append("save"))

    with pytest.raises(ValidationError, match="symlink or reparse point"):
        registry.delete("safe-topic")

    assert registry.clusters == {cluster.slug: cluster}
    assert saves == []
    assert sentinel.read_text(encoding="utf-8") == original


def test_cascade_delete_rejects_in_vault_raw_alias_before_report(
    temp_dir, monkeypatch
):
    raw = temp_dir / "raw"
    hub = temp_dir / "hub"
    (raw / "archive").mkdir(parents=True)
    hub.mkdir()
    sentinel = raw / "archive" / "preserve.md"
    sentinel.write_text("untouched", encoding="utf-8")
    try:
        (raw / "safe-topic").symlink_to(raw / "archive", target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"directory symlinks unavailable: {exc}")

    monkeypatch.setattr(
        clusters,
        "compute_cluster_cascade_report",
        lambda *a, **k: pytest.fail("cascade report read was reached"),
    )
    cfg = SimpleNamespace(raw=raw, hub=hub)
    with pytest.raises(ValidationError, match="symlink or reparse point"):
        clusters.cascade_delete_cluster(cfg, "safe-topic", apply=False)

    assert sentinel.read_text(encoding="utf-8") == "untouched"


def test_split_rejects_symlinked_note_before_query_match_or_registry_change(
    temp_dir, monkeypatch
):
    raw_override = temp_dir / "override-raw"
    source_note = _write_split_source(raw_override)
    original = source_note.read_text(encoding="utf-8")
    cfg = _split_cfg(temp_dir)
    monkeypatch.setattr(clusters, "get_config", lambda: cfg)
    registry = ClusterRegistry(cfg.clusters_file)
    _seed_split_registry(registry)
    before = dict(registry.clusters)
    saves = []
    registry.save = lambda: saves.append("save")
    _mock_symlink_lstat(monkeypatch, source_note)
    monkeypatch.setattr(
        clusters, "note_matches_query", lambda *a, **k: pytest.fail("note was read")
    )

    with pytest.raises(ValidationError, match="symlink or reparse point"):
        registry.split("source", "topic target", "New target", vault_raw=raw_override)

    assert registry.clusters == before
    assert saves == []
    assert source_note.read_text(encoding="utf-8") == original


def test_cascade_report_rejects_symlinked_note_before_stat(temp_dir, monkeypatch):
    raw = temp_dir / "raw"
    note = raw / "safe-topic" / "paper.md"
    note.parent.mkdir(parents=True)
    note.write_text("report sentinel", encoding="utf-8")
    _mock_symlink_lstat(monkeypatch, note)
    cfg = SimpleNamespace(raw=raw, hub=temp_dir / "hub")

    with pytest.raises(ValidationError, match="symlink or reparse point"):
        clusters.compute_cluster_cascade_report(cfg, "safe-topic")

    assert note.read_text(encoding="utf-8") == "report sentinel"


def test_cascade_report_rejects_symlinked_memory_file_before_read(
    temp_dir, monkeypatch
):
    raw = temp_dir / "raw"
    (raw / "safe-topic").mkdir(parents=True)
    memory_file = temp_dir / "hub" / "safe-topic" / "memory.json"
    memory_file.parent.mkdir(parents=True)
    memory_file.write_text('{"sentinel": ["preserve"]}', encoding="utf-8")
    _mock_symlink_lstat(monkeypatch, memory_file)
    cfg = SimpleNamespace(raw=raw, hub=temp_dir / "hub")

    with pytest.raises(ValidationError, match="symlink or reparse point"):
        clusters.compute_cluster_cascade_report(cfg, "safe-topic")

    assert memory_file.read_text(encoding="utf-8") == '{"sentinel": ["preserve"]}'


def test_coverage_skips_symlinked_note_before_stat_or_read(
    temp_dir, monkeypatch, caplog
):
    raw = temp_dir / "raw"
    note = raw / "safe-topic" / "paper.md"
    note.parent.mkdir(parents=True)
    note.write_text(
        "---\nsummarize_status: pending\n---\nprivate fixture note\n",
        encoding="utf-8",
    )
    clusters_file = temp_dir / "clusters.yaml"
    registry = ClusterRegistry(clusters_file)
    registry.clusters["safe-topic"] = Cluster(slug="safe-topic", name="Safe topic")
    registry.save()
    _mock_symlink_lstat(monkeypatch, note)
    real_read_text = Path.read_text

    def guarded_read_text(path, *args, **kwargs):
        if path == note:
            pytest.fail("symlinked note was read")
        return real_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read_text)

    rows = clusters.compute_coverage(
        SimpleNamespace(raw=raw, clusters_file=clusters_file)
    )

    assert len(rows) == 1
    assert rows[0].paper_count == 0
    assert rows[0].pending_summary == 0
    assert "symlink or reparse point" in caplog.text


def _registered_auto_tool():
    """Read the FastMCP-registered function without starting an event loop."""
    provider = getattr(mcp_server.mcp, "_local_provider", None)
    components = getattr(provider, "_components", {})
    for component in components.values():
        if getattr(component, "name", None) == "auto_research_topic":
            return component
    # FastMCP 2.x used this synchronous registry; keep the regression test
    # compatible with the project's declared ``fastmcp>=2.0`` range.
    manager = getattr(mcp_server.mcp, "_tool_manager", None)
    tools = getattr(manager, "_tools", {})
    if isinstance(tools, dict):
        return tools.get("auto_research_topic")
    return None


def test_registered_mcp_tool_rejects_bad_explicit_slugs_before_pipeline(monkeypatch):
    tool = _registered_auto_tool()
    assert tool is not None

    def should_not_run(*args, **kwargs):
        pytest.fail("invalid MCP slug reached auto_pipeline")

    monkeypatch.setattr(auto, "auto_pipeline", should_not_run)
    for slug in (*BAD_SLUGS, 0, False, [], {}):
        result = tool.fn(topic="security test", cluster_slug=slug)
        assert result["ok"] is False
        assert result["error"]


@pytest.mark.parametrize(
    "slug", [*BAD_SLUGS, "A" * 65, " leading", "trailing ", 0, False, [], {}]
)
def test_direct_pipeline_rejects_bad_slug_before_config_or_side_effects(monkeypatch, slug):
    def should_not_run(*args, **kwargs):
        pytest.fail("invalid slug crossed the early validation boundary")

    monkeypatch.setattr(auto, "get_config", should_not_run)
    monkeypatch.setattr(auto, "detect_llm_cli", should_not_run)
    monkeypatch.setattr(auto, "ClusterRegistry", should_not_run)

    report = auto.auto_pipeline("a safe topic", cluster_slug=slug, force=True)
    assert report.ok is False
    assert report.error


def test_registry_rejects_bad_slug_without_persisting_or_cleaning_existing_keys(temp_dir, monkeypatch):
    path = temp_dir / "clusters.yaml"
    registry = ClusterRegistry(path)
    legacy = Cluster(slug="../legacy-existing-entry", name="legacy")
    registry.clusters[legacy.slug] = legacy
    marker = "preserve this registry byte-for-byte\n"
    path.write_text(marker, encoding="utf-8")
    saves = []
    monkeypatch.setattr(registry, "save", lambda: saves.append("save"))

    for slug in (*BAD_SLUGS, 0, False, [], {}):
        with pytest.raises(ValidationError):
            registry.create(query="untrusted", slug=slug)

    assert saves == []
    assert registry.clusters == {legacy.slug: legacy}
    assert path.read_text(encoding="utf-8") == marker


@pytest.mark.parametrize("operation", ["merge", "split", "delete"])
def test_legacy_traversal_registry_entry_is_inert_and_preserved(
    temp_dir, monkeypatch, operation
):
    vault = temp_dir / "vault"
    raw = vault / "raw"
    raw.mkdir(parents=True)
    outside = vault / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel.md"
    sentinel.write_text("leave this note alone", encoding="utf-8")

    path = vault / ".research_hub" / "clusters.yaml"
    path.parent.mkdir(parents=True)
    marker = "schema_version: '1.0'\nclusters:\n  ../outside:\n    name: legacy\n"
    path.write_text(marker, encoding="utf-8")
    registry = ClusterRegistry(path)
    assert "../outside" in registry.clusters  # loading preserves legacy data

    saves = []
    monkeypatch.setattr(registry, "save", lambda: saves.append("save"))
    monkeypatch.setattr(clusters, "get_config", lambda: SimpleNamespace(raw=raw))

    with pytest.raises(ValidationError):
        if operation == "merge":
            registry.merge("../outside", "safe-target", vault_raw=raw)
        elif operation == "split":
            registry.split("../outside", "query", "new cluster", vault_raw=raw)
        else:
            registry.delete("../outside")

    assert sentinel.read_text(encoding="utf-8") == "leave this note alone"
    assert saves == []
    assert "../outside" in registry.clusters
    assert path.read_text(encoding="utf-8") == marker


def test_coverage_skips_invalid_legacy_slug_without_reading_outside_raw_root(
    temp_dir, caplog
):
    vault = temp_dir / "vault"
    raw = vault / "raw"
    raw.mkdir(parents=True)
    outside = vault / "outside"
    outside.mkdir()
    sentinel = outside / "outside-paper.md"
    sentinel.write_text(
        "---\ntitle: outside\nsummarize_status: pending\n---\nprivate note\n",
        encoding="utf-8",
    )

    path = vault / ".research_hub" / "clusters.yaml"
    path.parent.mkdir(parents=True)
    marker = "schema_version: '1.0'\nclusters:\n  ../outside:\n    name: legacy\n"
    path.write_text(marker, encoding="utf-8")
    cfg = SimpleNamespace(raw=raw, clusters_file=path)

    rows = clusters.compute_coverage(cfg)

    assert len(rows) == 1
    assert rows[0].slug == "../outside"
    assert rows[0].paper_count == 0
    assert rows[0].pending_summary == 0
    assert rows[0].coverage_score == 0
    assert "invalid slug" in caplog.text
    assert sentinel.read_text(encoding="utf-8").endswith("private note\n")
    assert path.read_text(encoding="utf-8") == marker


def test_registry_accepts_normalized_and_64_character_slugs(temp_dir, monkeypatch):
    monkeypatch.setattr(ClusterRegistry, "_auto_create_zotero_collection", lambda *a, **k: None)
    monkeypatch.setattr(ClusterRegistry, "_refresh_graph_if_possible", lambda *a, **k: None)
    from research_hub import topic

    monkeypatch.setattr(topic, "scaffold_cluster_hub", lambda *a, **k: None)
    root = temp_dir / "vault"
    path = root / ".research_hub" / "clusters.yaml"
    registry = ClusterRegistry(path)

    normalized = registry.create(query="normal", slug="Normal-Slug")
    maximum = registry.create(query="boundary", slug="a" * 64)

    assert normalized.slug == "normal-slug"
    assert maximum.slug == "a" * 64
    assert set(registry.clusters) == {"normal-slug", "a" * 64}


def test_force_deletes_only_temp_raw_markdown_inside_vault(temp_dir, monkeypatch):
    root = temp_dir / "vault"
    raw_dir = root / "raw" / "safe-topic"
    raw_dir.mkdir(parents=True)
    old_note = raw_dir / "old.md"
    other_file = raw_dir / "keep.json"
    old_note.write_text("old note", encoding="utf-8")
    other_file.write_text("keep", encoding="utf-8")
    outside_vault = temp_dir / "outside-vault"
    outside_vault.mkdir()
    sentinel = outside_vault / "sentinel.md"
    sentinel.write_text("untouched", encoding="utf-8")

    monkeypatch.setattr(auto, "get_config", lambda: _cfg(root))
    monkeypatch.setattr(auto, "detect_llm_cli", lambda **kwargs: None)
    monkeypatch.setattr(auto, "ClusterRegistry", lambda path: SimpleNamespace(get=lambda slug: _active_cluster()))
    monkeypatch.setattr(auto, "_run_search", lambda *args, **kwargs: [])

    report = auto.auto_pipeline(
        "safe topic", cluster_slug="safe-topic", force=True,
        do_fit_check=False, do_nlm=False, do_cluster_overview=False,
        print_progress=False,
    )

    assert report.ok is False  # the mocked search returns no papers
    assert not old_note.exists()
    assert other_file.read_text(encoding="utf-8") == "keep"
    assert sentinel.read_text(encoding="utf-8") == "untouched"


def test_run_output_is_confined_and_kept_for_failed_ingest(temp_dir, monkeypatch):
    root = temp_dir / "vault"
    cfg = _cfg(root)
    calls = []

    monkeypatch.setattr(auto, "get_config", lambda: cfg)
    monkeypatch.setattr(auto, "detect_llm_cli", lambda **kwargs: None)
    monkeypatch.setattr(auto, "ClusterRegistry", lambda path: SimpleNamespace(get=lambda slug: _active_cluster()))
    monkeypatch.setattr(auto, "_run_search", lambda *args, **kwargs: [{"title": "temp result"}])

    def fail_ingest(**kwargs):
        path = kwargs["papers_json"]
        calls.append((path, json.loads(path.read_text(encoding="utf-8"))))
        return 1

    monkeypatch.setattr(auto, "run_pipeline", fail_ingest)
    report = auto.auto_pipeline(
        "safe topic", cluster_slug="safe-topic", do_fit_check=False,
        do_nlm=False, do_cluster_overview=False, print_progress=False,
    )

    assert report.ok is False
    assert "pipeline returned exit code 1" in report.error
    assert len(calls) == 1
    papers_path, payload = calls[0]
    assert papers_path == root / ".runs" / f"safe-topic-{__import__('os').getpid()}" / "papers_input.json"
    papers_path.resolve().relative_to(root.resolve())
    assert payload == {"papers": [{"title": "temp result"}]}
    assert papers_path.exists()  # a failed ingest retains its per-run input


def test_run_output_is_written_to_validated_leaf_and_cleaned_on_success(temp_dir, monkeypatch):
    root = temp_dir / "vault"
    cfg = _cfg(root)
    calls = []

    monkeypatch.setattr(auto, "get_config", lambda: cfg)
    monkeypatch.setattr(auto, "detect_llm_cli", lambda **kwargs: None)
    monkeypatch.setattr(
        auto, "ClusterRegistry",
        lambda path: SimpleNamespace(get=lambda slug: _active_cluster()),
    )
    monkeypatch.setattr(auto, "_run_search", lambda *args, **kwargs: [{"title": "safe result"}])

    def successful_ingest(**kwargs):
        path = Path(kwargs["papers_json"])
        calls.append((path, json.loads(path.read_text(encoding="utf-8"))))
        path.resolve().relative_to(root.resolve())
        return 0

    monkeypatch.setattr(auto, "run_pipeline", successful_ingest)
    auto.auto_pipeline(
        "safe topic", cluster_slug="safe-topic", do_fit_check=False,
        do_nlm=False, do_cluster_overview=False, print_progress=False,
    )

    assert len(calls) == 1
    papers_path, payload = calls[0]
    assert papers_path == root / ".runs" / f"safe-topic-{os.getpid()}" / "papers_input.json"
    assert payload == {"papers": [{"title": "safe result"}]}
    assert not papers_path.exists()  # successful ingest removes its per-run directory


def test_run_output_leaf_symlink_escape_is_rejected_before_registry_or_search(
    temp_dir, monkeypatch
):
    root = temp_dir / "vault"
    run_dir = root / ".runs" / f"safe-topic-{os.getpid()}"
    run_dir.mkdir(parents=True)
    outside = temp_dir / "outside-vault"
    outside.mkdir()
    sentinel = outside / "sentinel.json"
    sentinel.write_text('{"sentinel":"untouched"}', encoding="utf-8")
    link = run_dir / "papers_input.json"
    try:
        link.symlink_to(sentinel)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"file symlinks unavailable: {exc}")

    def should_not_run(*args, **kwargs):
        pytest.fail("leaf symlink escape reached registry, search, or ingest")

    monkeypatch.setattr(auto, "get_config", lambda: _cfg(root))
    monkeypatch.setattr(auto, "ClusterRegistry", should_not_run)
    monkeypatch.setattr(auto, "_run_search", should_not_run)
    monkeypatch.setattr(auto, "run_pipeline", should_not_run)
    report = auto.auto_pipeline(
        "safe topic", cluster_slug="safe-topic", force=True,
        do_fit_check=False, do_nlm=False, print_progress=False,
    )

    assert report.ok is False
    assert "symlink or reparse point" in report.error or "escapes root" in report.error
    assert link.is_symlink()
    assert sentinel.read_text(encoding="utf-8") == '{"sentinel":"untouched"}'


def test_raw_symlink_escape_is_rejected_before_registry_or_search(temp_dir, monkeypatch):
    root = temp_dir / "vault"
    raw = root / "raw"
    raw.mkdir(parents=True)
    outside = temp_dir / "outside-vault"
    outside.mkdir()
    sentinel = outside / "sentinel.md"
    sentinel.write_text("untouched", encoding="utf-8")
    try:
        (raw / "safe-topic").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"directory symlinks unavailable: {exc}")

    def should_not_run(*args, **kwargs):
        pytest.fail("symlink escape was not rejected before side effects")

    monkeypatch.setattr(auto, "get_config", lambda: _cfg(root))
    monkeypatch.setattr(auto, "ClusterRegistry", should_not_run)
    monkeypatch.setattr(auto, "_run_search", should_not_run)
    report = auto.auto_pipeline(
        "safe topic", cluster_slug="safe-topic", force=True,
        do_fit_check=False, do_nlm=False, print_progress=False,
    )

    assert report.ok is False
    assert "symlink or reparse point" in report.error or "escapes root" in report.error
    assert sentinel.read_text(encoding="utf-8") == "untouched"


def test_run_root_symlink_escape_is_rejected_before_registry_or_search(temp_dir, monkeypatch):
    root = temp_dir / "vault"
    root.mkdir()
    outside = temp_dir / "outside-vault"
    outside.mkdir()
    sentinel = outside / "sentinel.json"
    sentinel.write_text("untouched", encoding="utf-8")
    try:
        (root / ".runs").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"directory symlinks unavailable: {exc}")

    def should_not_run(*args, **kwargs):
        pytest.fail("symlink escape was not rejected before side effects")

    monkeypatch.setattr(auto, "get_config", lambda: _cfg(root))
    monkeypatch.setattr(auto, "ClusterRegistry", should_not_run)
    monkeypatch.setattr(auto, "_run_search", should_not_run)
    report = auto.auto_pipeline(
        "safe topic", cluster_slug="safe-topic", force=True,
        do_fit_check=False, do_nlm=False, print_progress=False,
    )

    assert report.ok is False
    assert "symlink or reparse point" in report.error or "escapes root" in report.error
    assert sentinel.read_text(encoding="utf-8") == "untouched"


def test_run_root_in_vault_symlink_alias_is_rejected_before_registry_or_search(
    temp_dir, monkeypatch
):
    root = temp_dir / "vault"
    runs = root / ".runs"
    runs.mkdir(parents=True)
    aliased_run = runs / "other-run"
    aliased_run.mkdir()
    sentinel = aliased_run / "keep.json"
    sentinel.write_text('{"sentinel":"untouched"}', encoding="utf-8")
    run_link = runs / f"safe-topic-{os.getpid()}"
    try:
        run_link.symlink_to(aliased_run, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"directory symlinks unavailable: {exc}")

    def should_not_run(*args, **kwargs):
        pytest.fail("in-vault run alias reached registry, search, or ingest")

    monkeypatch.setattr(auto, "get_config", lambda: _cfg(root))
    monkeypatch.setattr(auto, "ClusterRegistry", should_not_run)
    monkeypatch.setattr(auto, "_run_search", should_not_run)
    monkeypatch.setattr(auto, "run_pipeline", should_not_run)
    report = auto.auto_pipeline(
        "safe topic", cluster_slug="safe-topic", do_fit_check=False,
        do_nlm=False, print_progress=False,
    )

    assert report.ok is False
    assert "symlink or reparse point" in report.error
    assert run_link.is_symlink()
    assert sentinel.read_text(encoding="utf-8") == '{"sentinel":"untouched"}'


def test_run_output_leaf_in_vault_symlink_alias_is_rejected(temp_dir, monkeypatch):
    root = temp_dir / "vault"
    run_dir = root / ".runs" / f"safe-topic-{os.getpid()}"
    run_dir.mkdir(parents=True)
    sentinel = root / ".runs" / "other-input.json"
    sentinel.write_text('{"sentinel":"untouched"}', encoding="utf-8")
    leaf = run_dir / "papers_input.json"
    try:
        leaf.symlink_to(sentinel)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"file symlinks unavailable: {exc}")

    def should_not_run(*args, **kwargs):
        pytest.fail("in-vault input alias reached registry, search, or ingest")

    monkeypatch.setattr(auto, "get_config", lambda: _cfg(root))
    monkeypatch.setattr(auto, "ClusterRegistry", should_not_run)
    monkeypatch.setattr(auto, "_run_search", should_not_run)
    monkeypatch.setattr(auto, "run_pipeline", should_not_run)
    report = auto.auto_pipeline(
        "safe topic", cluster_slug="safe-topic", do_fit_check=False,
        do_nlm=False, print_progress=False,
    )

    assert report.ok is False
    assert "symlink or reparse point" in report.error
    assert leaf.is_symlink()
    assert sentinel.read_text(encoding="utf-8") == '{"sentinel":"untouched"}'


def test_raw_cluster_in_vault_symlink_alias_is_rejected_before_force_deletion(
    temp_dir, monkeypatch
):
    root = temp_dir / "vault"
    raw = root / "raw"
    raw.mkdir(parents=True)
    aliased_cluster = raw / "archive"
    aliased_cluster.mkdir()
    sentinel = aliased_cluster / "preserve.md"
    sentinel.write_text("untouched", encoding="utf-8")
    cluster_link = raw / "safe-topic"
    try:
        cluster_link.symlink_to(aliased_cluster, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"directory symlinks unavailable: {exc}")

    def should_not_run(*args, **kwargs):
        pytest.fail("in-vault raw alias reached registry, search, or ingest")

    monkeypatch.setattr(auto, "get_config", lambda: _cfg(root))
    monkeypatch.setattr(auto, "ClusterRegistry", should_not_run)
    monkeypatch.setattr(auto, "_run_search", should_not_run)
    report = auto.auto_pipeline(
        "safe topic", cluster_slug="safe-topic", force=True,
        do_fit_check=False, do_nlm=False, print_progress=False,
    )

    assert report.ok is False
    assert "symlink or reparse point" in report.error
    assert cluster_link.is_symlink()
    assert sentinel.read_text(encoding="utf-8") == "untouched"


def test_base_path_validates_slug_and_constrains_symlinks(temp_dir):
    hub = temp_dir / "vault" / "hub"
    assert base_path_for_cluster(hub, "safe-topic") == hub / "safe-topic" / "safe-topic.base"
    with pytest.raises(ValidationError):
        base_path_for_cluster(hub, "../outside")

    hub.mkdir(parents=True)
    outside = temp_dir / "outside-vault"
    outside.mkdir()
    sentinel = outside / "outside.base"
    sentinel.write_text("untouched", encoding="utf-8")
    try:
        (hub / "safe-topic").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"directory symlinks unavailable: {exc}")
    with pytest.raises(ValidationError, match="symlink or reparse point|escapes root"):
        base_path_for_cluster(hub, "safe-topic")
    assert sentinel.read_text(encoding="utf-8") == "untouched"


def test_generated_and_64_character_slugs_are_accepted_before_pipeline(monkeypatch, temp_dir):
    root = temp_dir / "vault"
    monkeypatch.setattr(auto, "get_config", lambda: _cfg(root))
    monkeypatch.setattr(auto, "detect_llm_cli", lambda **kwargs: None)
    monkeypatch.setattr(auto, "ClusterRegistry", lambda path: SimpleNamespace(get=lambda slug: None))

    generated = auto.auto_pipeline(
        "Nonlinear dynamics reservoirs", dry_run=True, do_fit_check=False,
        do_nlm=False, do_cluster_overview=False, print_progress=False,
    )
    boundary = auto.auto_pipeline(
        "valid topic", cluster_slug="a" * 64, dry_run=True, do_fit_check=False,
        do_nlm=False, do_cluster_overview=False, print_progress=False,
    )
    assert generated.ok is True
    assert generated.cluster_slug == "nonlinear-dynamics-reservoirs"
    assert boundary.ok is True
    assert boundary.cluster_slug == "a" * 64


def test_dry_run_needs_only_registry_config_and_has_no_filesystem_side_effects(
    monkeypatch, temp_dir
):
    cfg = SimpleNamespace(clusters_file=temp_dir / "clusters.yaml")
    registry = SimpleNamespace(get=lambda _slug: None)
    monkeypatch.setattr(auto, "get_config", lambda: cfg)
    monkeypatch.setattr(auto, "ClusterRegistry", lambda _path: registry)
    monkeypatch.setattr(auto, "detect_llm_cli", lambda **kwargs: "claude")

    report = auto.auto_pipeline(
        "llm agents",
        dry_run=True,
        peer_reviewed=True,
        do_nlm=False,
        print_progress=False,
    )

    assert report.ok is True
    assert report.cluster_slug == "llm-agents"
    assert list(temp_dir.iterdir()) == []


def test_long_generated_slugs_are_bounded_and_collision_resistant(monkeypatch, temp_dir):
    topics = ["a" * 70 + "x", "a" * 70 + "y"]
    slugs = [cluster_slugify(topic) for topic in topics]
    assert all(len(slug) == 64 for slug in slugs)
    assert slugs[0] != slugs[1]
    assert slugs[0] == cluster_slugify(topics[0])

    root = temp_dir / "vault"
    monkeypatch.setattr(auto, "get_config", lambda: _cfg(root))
    monkeypatch.setattr(auto, "detect_llm_cli", lambda **kwargs: None)
    monkeypatch.setattr(
        auto, "ClusterRegistry", lambda path: SimpleNamespace(get=lambda slug: None)
    )
    reports = [
        auto.auto_pipeline(
            topic,
            dry_run=True,
            do_fit_check=False,
            do_nlm=False,
            do_cluster_overview=False,
            print_progress=False,
        )
        for topic in topics
    ]
    assert [report.cluster_slug for report in reports] == slugs
    assert all(report.ok for report in reports)


def test_long_generated_topic_preserves_legacy_registry_entry_without_duplicate(
    monkeypatch, temp_dir
):
    topic = "a" * 70 + "legacy"
    legacy_slug = slugify(topic)
    bounded_slug = cluster_slugify(topic)
    assert len(legacy_slug) > 64
    assert len(bounded_slug) == 64

    root = temp_dir / "vault"
    cfg = _cfg(root)
    registry = ClusterRegistry(cfg.clusters_file)
    legacy = Cluster(slug=legacy_slug, name="Legacy long slug", first_query=topic)
    registry.clusters[legacy_slug] = legacy
    saves = []
    registry.save = lambda: saves.append("save")
    before = dict(registry.clusters)

    with pytest.raises(ValidationError, match="Existing legacy cluster key"):
        registry.create(query=topic)

    monkeypatch.setattr(auto, "get_config", lambda: cfg)
    monkeypatch.setattr(auto, "ClusterRegistry", lambda _path: registry)
    monkeypatch.setattr(auto, "detect_llm_cli", lambda **kwargs: None)
    monkeypatch.setattr(
        auto, "_run_search", lambda *a, **k: pytest.fail("search ran")
    )
    report = auto.auto_pipeline(
        topic,
        dry_run=True,
        do_fit_check=False,
        do_nlm=False,
        do_cluster_overview=False,
        print_progress=False,
    )

    assert report.ok is False
    assert "Existing legacy cluster key" in report.error
    assert report.cluster_slug == bounded_slug
    assert registry.clusters == before
    assert saves == []


def _seed_split_registry(
    registry, source_slug="source", tombstone_slug="topic-target", target_slug="real-target"
):
    registry.clusters[source_slug] = Cluster(
        slug=source_slug, name="Source", first_query="source"
    )
    registry.clusters[tombstone_slug] = Cluster(
        slug=tombstone_slug,
        name="Legacy tombstone",
        status="merged",
        merged_into=target_slug,
    )
    registry.clusters[target_slug] = Cluster(
        slug=target_slug, name="Existing target", first_query="real target"
    )


def _write_split_source(raw_root):
    source_note = raw_root / "source" / "topic-target-paper.md"
    source_note.parent.mkdir(parents=True, exist_ok=True)
    source_note.write_text(
        '---\ntitle: "Topic Target Paper"\ntopic_cluster: "source"\n---\n\n# Topic Target Paper\n',
        encoding="utf-8",
    )
    return source_note


def _split_cfg(temp_dir):
    return SimpleNamespace(
        raw=temp_dir / "config-raw",
        root=temp_dir / "config-root",
        hub=temp_dir / "config-hub",
        research_hub_dir=temp_dir / "config-root" / ".research_hub",
        clusters_file=temp_dir / "registry.yaml",
    )


def test_split_rejects_invalid_resolved_tombstone_target_without_mutation(
    temp_dir, monkeypatch
):
    raw_override = temp_dir / "override-raw"
    source_note = _write_split_source(raw_override)
    outside = temp_dir / "outside-vault"
    outside.mkdir()
    sentinel = outside / "sentinel.md"
    sentinel.write_text("untouched", encoding="utf-8")
    config_raw = temp_dir / "config-raw"
    cfg = _split_cfg(temp_dir)
    monkeypatch.setattr(clusters, "get_config", lambda: cfg)
    registry = ClusterRegistry(cfg.clusters_file)
    _seed_split_registry(registry, target_slug="../outside")
    before = dict(registry.clusters)
    saved = []
    registry.save = lambda: saved.append(True)
    monkeypatch.setattr(clusters, "move_paper", lambda *a, **k: pytest.fail("move ran"))

    with pytest.raises(ValidationError, match="target_slug"):
        registry.split("source", "topic target", "New target", vault_raw=raw_override)

    assert registry.clusters == before
    assert saved == []
    assert source_note.read_text(encoding="utf-8").startswith(
        '---\ntitle: "Topic Target Paper"'
    )
    assert sentinel.read_text(encoding="utf-8") == "untouched"
    assert not config_raw.exists()


def test_split_rejects_resolved_target_symlink_in_vault_raw_override(
    temp_dir, monkeypatch
):
    raw_override = temp_dir / "override-raw"
    source_note = _write_split_source(raw_override)
    outside = temp_dir / "outside-vault"
    outside.mkdir()
    sentinel = outside / "sentinel.md"
    sentinel.write_text("untouched", encoding="utf-8")
    try:
        (raw_override / "real-target").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"directory symlinks unavailable: {exc}")

    config_raw = temp_dir / "config-raw"
    cfg = _split_cfg(temp_dir)
    monkeypatch.setattr(clusters, "get_config", lambda: cfg)
    registry = ClusterRegistry(cfg.clusters_file)
    _seed_split_registry(registry)
    before = dict(registry.clusters)
    saved = []
    registry.save = lambda: saved.append(True)
    monkeypatch.setattr(clusters, "move_paper", lambda *a, **k: pytest.fail("move ran"))

    with pytest.raises(ValidationError, match="symlink or reparse point|escapes root"):
        registry.split("source", "topic target", "New target", vault_raw=raw_override)

    assert registry.clusters == before
    assert saved == []
    assert source_note.read_text(encoding="utf-8").startswith(
        '---\ntitle: "Topic Target Paper"'
    )
    assert sentinel.read_text(encoding="utf-8") == "untouched"
    assert not config_raw.exists()


def test_split_rejects_in_vault_resolved_target_alias_without_mutation(
    temp_dir, monkeypatch
):
    raw_override = temp_dir / "override-raw"
    source_note = _write_split_source(raw_override)
    aliased_target = raw_override / "archived-target"
    aliased_target.mkdir()
    sentinel = aliased_target / "preserve.md"
    sentinel.write_text("untouched", encoding="utf-8")
    try:
        (raw_override / "real-target").symlink_to(
            aliased_target, target_is_directory=True
        )
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"directory symlinks unavailable: {exc}")

    cfg = _split_cfg(temp_dir)
    monkeypatch.setattr(clusters, "get_config", lambda: cfg)
    registry = ClusterRegistry(cfg.clusters_file)
    _seed_split_registry(registry)
    before = dict(registry.clusters)
    saves = []
    registry.save = lambda: saves.append("save")
    monkeypatch.setattr(
        clusters, "move_paper", lambda *a, **k: pytest.fail("move ran")
    )

    with pytest.raises(ValidationError, match="symlink or reparse point"):
        registry.split("source", "topic target", "New target", vault_raw=raw_override)

    assert registry.clusters == before
    assert saves == []
    assert source_note.read_text(encoding="utf-8").startswith(
        '---\ntitle: "Topic Target Paper"'
    )
    assert sentinel.read_text(encoding="utf-8") == "untouched"
    assert not cfg.raw.exists()


def test_split_rejects_in_vault_source_alias_without_mutation(temp_dir, monkeypatch):
    raw_override = temp_dir / "override-raw"
    alias_target = raw_override / "archived-source"
    alias_target.mkdir(parents=True)
    source_note = alias_target / "topic-target-paper.md"
    source_note.write_text(
        '---\ntitle: "Topic Target Paper"\ntopic_cluster: "source"\n---\n',
        encoding="utf-8",
    )
    try:
        (raw_override / "source").symlink_to(alias_target, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"directory symlinks unavailable: {exc}")

    cfg = _split_cfg(temp_dir)
    monkeypatch.setattr(clusters, "get_config", lambda: cfg)
    registry = ClusterRegistry(cfg.clusters_file)
    _seed_split_registry(registry)
    before = dict(registry.clusters)
    saves = []
    registry.save = lambda: saves.append("save")

    with pytest.raises(ValidationError, match="symlink or reparse point"):
        registry.split("source", "topic target", "New target", vault_raw=raw_override)

    assert registry.clusters == before
    assert saves == []
    assert source_note.exists()
    assert source_note.read_text(encoding="utf-8").startswith(
        '---\ntitle: "Topic Target Paper"'
    )
    assert not cfg.raw.exists()


@pytest.mark.parametrize("alias_role", ["source", "target"])
def test_merge_rejects_in_vault_cluster_alias_without_mutation(
    temp_dir, monkeypatch, alias_role
):
    raw_override = temp_dir / "override-raw"
    raw_override.mkdir()
    source_dir = raw_override / "source"
    target_dir = raw_override / "target"
    alias_dir = raw_override / f"archived-{alias_role}"
    alias_dir.mkdir()
    sentinel = alias_dir / "keep.md"
    sentinel.write_text("untouched", encoding="utf-8")
    try:
        if alias_role == "source":
            source_dir.symlink_to(alias_dir, target_is_directory=True)
            target_dir.mkdir()
        else:
            source_dir.mkdir()
            (source_dir / "paper.md").write_text("paper", encoding="utf-8")
            target_dir.symlink_to(alias_dir, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"directory symlinks unavailable: {exc}")

    cfg = _split_cfg(temp_dir)
    monkeypatch.setattr(clusters, "get_config", lambda: cfg)
    registry = ClusterRegistry(cfg.clusters_file)
    registry.clusters["source"] = Cluster(slug="source", name="Source")
    registry.clusters["target"] = Cluster(slug="target", name="Target")
    before = dict(registry.clusters)
    saves = []
    registry.save = lambda: saves.append("save")
    monkeypatch.setattr(
        clusters, "move_paper", lambda *a, **k: pytest.fail("move ran")
    )

    with pytest.raises(ValidationError, match="symlink or reparse point"):
        registry.merge("source", "target", vault_raw=raw_override)

    assert registry.clusters == before
    assert saves == []
    assert sentinel.read_text(encoding="utf-8") == "untouched"
    if alias_role == "target":
        assert (source_dir / "paper.md").read_text(encoding="utf-8") == "paper"
    assert not cfg.raw.exists()


def test_split_follows_valid_merged_redirect_using_vault_raw_override(
    temp_dir, monkeypatch
):
    raw_override = temp_dir / "override-raw"
    source_note = _write_split_source(raw_override)
    target_dir = raw_override / "real-target"
    target_dir.mkdir(parents=True)
    config_raw = temp_dir / "config-raw"
    cfg = _split_cfg(temp_dir)
    monkeypatch.setattr(clusters, "get_config", lambda: cfg)
    monkeypatch.setattr(operations, "get_config", lambda: cfg)
    monkeypatch.setattr(
        ClusterRegistry, "_refresh_graph_if_possible", lambda *a, **k: None
    )
    monkeypatch.setattr(
        ClusterRegistry, "_rebuild_dedup_index_best_effort", lambda *a, **k: False
    )
    registry = ClusterRegistry(cfg.clusters_file)
    _seed_split_registry(registry)

    result = registry.split(
        "source", "topic target", "New target", vault_raw=raw_override
    )

    moved_note = target_dir / source_note.name
    assert result["new_cluster"] == "real-target"
    assert result["moved"] == 1
    assert not source_note.exists()
    assert moved_note.exists()
    assert "topic_cluster: real-target" in moved_note.read_text(encoding="utf-8")
    assert set(registry.clusters) == {"source", "topic-target", "real-target"}
    assert registry.clusters["real-target"].status == "active"
    assert not config_raw.exists()


def test_registry_bounds_long_autogenerated_slugs_in_temp_fixture(monkeypatch, temp_dir):
    monkeypatch.setattr(
        ClusterRegistry, "_auto_create_zotero_collection", lambda *a, **k: None
    )
    monkeypatch.setattr(ClusterRegistry, "_refresh_graph_if_possible", lambda *a, **k: None)
    from research_hub import topic

    monkeypatch.setattr(topic, "scaffold_cluster_hub", lambda *a, **k: None)
    query = "a" * 80
    registry = ClusterRegistry(temp_dir / "vault" / ".research_hub" / "clusters.yaml")
    created = registry.create(query=query)
    assert created.slug == cluster_slugify(query)
    assert len(created.slug) == 64
