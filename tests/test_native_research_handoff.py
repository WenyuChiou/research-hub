"""Native research handoffs use explicit files and retain evidence on replay."""

from __future__ import annotations

import copy
import json

import pytest
import yaml

from research_hub.ingest_provenance import merge_note_evidence
from tests.test_pipeline import _configure, _paper
from tests.test_pipeline_v03 import _create_cluster


def _metadata(text):
    return yaml.safe_load(text.split("---", 2)[1])


@pytest.fixture
def handoff_env(tmp_path, monkeypatch):
    from research_hub import cli, pipeline

    cfg = _configure(monkeypatch, tmp_path, default_collection="ABCD1234")
    _create_cluster(cfg, "native-review")
    monkeypatch.setattr(cli, "get_config", lambda: cfg)
    monkeypatch.setattr(pipeline, "get_config", lambda: cfg)
    monkeypatch.setattr(pipeline.time, "sleep", lambda seconds: None)
    # This is an integration test of the storage seam, not a claim that a
    # synthetic DOI or agent-provided assertion passed identity verification.
    monkeypatch.setattr("research_hub.authenticity.verify_authenticity", lambda papers, *a, **kw: (papers, []))
    created, notes = [], []

    class FixtureZotero:
        def item_template(self, item_type):
            return {"itemType": item_type}

        def create_items(self, items):
            created.extend(copy.deepcopy(items))
            return {"successful": {str(i): {"key": f"TEST{i}"} for i in range(len(items))}}

    monkeypatch.setattr(pipeline, "get_client", lambda: FixtureZotero())
    monkeypatch.setattr(pipeline, "check_duplicate", lambda *a, **kw: False)
    monkeypatch.setattr(pipeline, "add_note", lambda zot, key, content: notes.append(content))
    return cfg, created, notes


@pytest.mark.parametrize("command", ["ingest", "run"])
def test_cli_routes_explicit_input(command, handoff_env, monkeypatch, tmp_path):
    from research_hub import cli

    received = []
    monkeypatch.setattr(cli, "run_pipeline", lambda **kw: received.append(kw) or 0)
    path = tmp_path / "native handoff.json"
    assert cli.main([command, "--input", str(path), "--dry-run"]) == 0
    assert received[0]["papers_json"] == str(path)


def test_cli_input_bom_inbatch_and_incremental_replay(handoff_env, tmp_path, capsys):
    from research_hub import cli

    cfg, created, notes = handoff_env
    default = cfg.root / "papers_input.json"
    default.write_text("[]", encoding="utf-8")
    path = tmp_path / "handoff.json"
    first = _paper("Synthetic Native Research Evidence", "native-evidence", "10.1000/native")
    first["provenance"] = {
        "producer": "host-native",
        "research": {"queries": ['native, \"evidence\"'], "basis": "full_text"},
        "doi_recheck_pending": True,
    }
    first["source_records"] = [{"source_id": "S1", "url": "https://example.test/article", "locator": "p. 4"}]
    second = copy.deepcopy(first)
    second["doi"] = "10.1000/native-preprint"
    second["source_records"] = [{"source_id": "S2", "url": "https://example.test/preprint", "locator": "<section>"}]
    # This alias was seen on the collapsed candidate, so it must not create
    # another item when its title has changed.
    third = copy.deepcopy(second)
    third["title"] = "Alternate Title For The Same Native Evidence"
    third["source_records"] = [{"source_id": "S3", "url": "https://example.test/mirror"}]
    path.write_text(json.dumps({"papers": [first, second, third]}), encoding="utf-8-sig")
    args = ["ingest", "--input", str(path), "--cluster", "native-review", "--query", 'native, "evidence"', "--no-verify", "--json"]
    assert cli.main(args) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["report"]["input_path"] == str(path)
    assert len(created) == len(notes) == 1
    note = cfg.raw / "native-review" / "native-evidence.md"
    text = note.read_text(encoding="utf-8")
    metadata = _metadata(text)
    assert [record["source_id"] for record in metadata["source_records"]] == ["S1", "S2", "S3"]
    for field, value in first["provenance"].items():
        assert metadata["provenance"][field] == value
    assert "&lt;section&gt;" in notes[0]
    assert "S1" in notes[0] and "S3" in notes[0]
    assert default.read_text(encoding="utf-8") == "[]"

    annotation = "\n## My reading notes\nA private synthetic annotation.\n"
    text = text.replace("status: unread", "status: deep-read") + annotation
    note.write_text(text, encoding="utf-8")
    body = text.split("---", 2)[2]
    update = copy.deepcopy(first)
    update["summary"] = "A replacement summary that must not overwrite my note."
    update["source_records"] = [{"source_id": "S4", "url": "https://example.test/correction"}]
    update["provenance"]["research"]["queries"] = ["citation follow-up"]
    path.write_text(json.dumps([update]), encoding="utf-8")
    args[args.index("--query") + 1] = 'follow-up, "citation"'
    assert cli.main(args) == 0
    capsys.readouterr()
    after = note.read_text(encoding="utf-8")
    metadata = _metadata(after)
    assert metadata["status"] == "deep-read"
    assert metadata["cluster_queries"] == ['native, "evidence"', 'follow-up, "citation"']
    assert metadata["provenance"]["research"]["queries"] == ['native, "evidence"', "citation follow-up"]
    assert [record["source_id"] for record in metadata["source_records"]] == ["S1", "S2", "S3", "S4"]
    assert after.split("---", 2)[2] == body
    assert cli.main(args) == 0
    capsys.readouterr()
    assert note.read_text(encoding="utf-8") == after
    assert len(created) == len(notes) == 1
    assert len(list((cfg.raw / "native-review").glob("*.md"))) == 1


def test_explicit_missing_input_never_falls_back(handoff_env, tmp_path, capsys):
    from research_hub import cli

    cfg, created, _ = handoff_env
    (cfg.root / "papers_input.json").write_text("[]", encoding="utf-8")
    missing = tmp_path / "missing.json"
    assert cli.main(["ingest", "--input", str(missing), "--dry-run", "--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["error"]["context"]["input_path"] == str(missing)
    assert not created


@pytest.mark.parametrize("payload", [[42], [{"provenance": "not an object"}], [{"source_records": ["not an object"]}]])
@pytest.mark.parametrize("no_zotero", [False, True])
def test_bad_evidence_rejected_before_external_writes(payload, no_zotero, handoff_env, tmp_path, monkeypatch):
    from research_hub import pipeline

    cfg, created, _ = handoff_env
    if no_zotero:
        monkeypatch.setenv("RESEARCH_HUB_NO_ZOTERO", "1")
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert pipeline.run_pipeline(papers_json=path) == 1
    assert not created
    assert not list(cfg.raw.rglob("*.md"))


def test_preview_does_not_write_canonical_manifest(handoff_env, tmp_path):
    from research_hub import pipeline

    cfg, created, _ = handoff_env
    path = tmp_path / "preview.json"
    path.write_text(json.dumps([_paper("Preview Evidence", "preview", "10.1000/preview")]), encoding="utf-8")
    assert pipeline.run_pipeline(papers_json=path, dry_run=True, cluster_slug="native-review") == 0
    assert not (cfg.research_hub_dir / "manifest.jsonl").exists()
    assert not created
    assert not list(cfg.raw.rglob("*.md"))


@pytest.mark.parametrize("command", ["ingest", "run"])
def test_preview_preserves_state_and_never_auto_labels(command, handoff_env, tmp_path, monkeypatch, capsys):
    from research_hub import cli, pipeline

    cfg, created, _ = handoff_env
    path = tmp_path / "preview.json"
    path.write_text(json.dumps([_paper("Preview Evidence", "preview", "10.1000/preview")]), encoding="utf-8")
    for target in (cfg.logs / "pipeline_log.txt", cfg.logs / "pipeline_output.json", cfg.research_hub_dir / "manifest.jsonl"):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('{"previous_run": true}', encoding="utf-8")
    before = {str(p): p.read_bytes() for p in cfg.root.rglob("*") if p.is_file()}
    monkeypatch.setattr(pipeline, "get_client", lambda: pytest.fail("Preview must not access Zotero"))
    monkeypatch.setattr("research_hub.paper.apply_fit_check_to_labels", lambda *a, **kw: pytest.fail("Preview must not apply labels"))
    args = [command, "--input", str(path), "--cluster", "native-review", "--dry-run"]
    if command == "ingest":
        args.extend(["--fit-check", "--json"])
    assert cli.main(args) == 0
    output = capsys.readouterr()
    if command == "ingest":
        report = json.loads(output.out)["report"]
        assert report["pipeline_output"] is None
        assert report["fit_check_auto_labels"] is None
    assert {str(p): p.read_bytes() for p in cfg.root.rglob("*") if p.is_file()} == before
    assert not created


def test_failed_or_noop_ingest_does_not_report_previous_output(handoff_env, tmp_path, monkeypatch, capsys):
    from research_hub import cli

    cfg, _, _ = handoff_env
    (cfg.logs / "pipeline_output.json").write_text('{"previous_run": true}', encoding="utf-8")
    for result in (0, 1):
        monkeypatch.setattr(cli, "run_pipeline", lambda **kw: result)
        assert cli.main(["ingest", "--json"]) == result
        assert json.loads(capsys.readouterr().out)["report"]["pipeline_output"] is None


@pytest.mark.parametrize("field,value", [
    ("slug", "../../outside"), ("slug", "nested/paper"), ("slug", "nested\\paper"),
    ("slug", 12), ("sub_category", "../../outside"), ("sub_category", "/outside"),
    ("sub_category", "nested\\folder"), ("sub_category", 12),
])
def test_unsafe_handoff_paths_fail_before_client_access(field, value, handoff_env, tmp_path, monkeypatch):
    from research_hub import pipeline

    cfg, created, _ = handoff_env
    paper = _paper("Unsafe Path Evidence", "safe-slug", "10.1000/path")
    paper[field] = value
    path = tmp_path / "unsafe.json"
    path.write_text(json.dumps([paper]), encoding="utf-8")
    monkeypatch.setattr(pipeline, "get_client", lambda: pytest.fail("Unsafe input must fail before client access"))
    assert pipeline.run_pipeline(papers_json=path) == 1
    assert not created
    assert not list(cfg.raw.rglob("*.md"))


def test_handoff_rejects_symlink_escape_before_writes(handoff_env, tmp_path, monkeypatch):
    from research_hub import pipeline

    cfg, created, _ = handoff_env
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "paper.md"
    target.write_text("Preserve this unrelated file", encoding="utf-8")
    folder = cfg.raw / "survey"
    folder.mkdir(parents=True, exist_ok=True)
    try:
        (folder / "safe-slug.md").symlink_to(target)
    except OSError:
        pytest.skip("Symlink creation is unavailable on this platform")
    path = tmp_path / "unsafe.json"
    path.write_text(json.dumps([_paper("Unsafe Path Evidence", "safe-slug", "10.1000/path")]), encoding="utf-8")
    monkeypatch.setattr(pipeline, "get_client", lambda: pytest.fail("Symlink escape must fail before client access"))
    assert pipeline.run_pipeline(papers_json=path) == 1
    assert target.read_text(encoding="utf-8") == "Preserve this unrelated file"
    assert not created


def test_metadata_merge_keeps_yaml_comments_and_body(tmp_path):
    from research_hub.pipeline import append_cluster_query_to_existing

    note = tmp_path / "annotated.md"
    note.write_text(
        '---\n# My frontmatter comment\nstatus: cited\ncustom: keep\n'
        'cluster_queries:\n  - "initial, query"\n'
        'provenance:\n  producer: native\n  research:\n    queries: [initial]\n'
        'source_records:\n  - source_id: S1\n    locator: page 1\n'
        '---\n## Reading notes\nKeep this exact body.\n', encoding="utf-8",
    )
    incoming = {"provenance": {"producer": "other-host", "research": {"queries": ["second"]}}, "source_records": [{"source_id": "S2", "locator": "page 2"}]}
    assert merge_note_evidence(note, incoming)
    assert append_cluster_query_to_existing(note, 'second, "query"')
    after = note.read_text(encoding="utf-8")
    metadata = _metadata(after)
    assert metadata["provenance"]["producer"] == "native"
    assert metadata["status"] == "cited"
    assert metadata["custom"] == "keep"
    assert metadata["cluster_queries"] == ["initial, query", 'second, "query"']
    assert "# My frontmatter comment" in after
    assert after.endswith("## Reading notes\nKeep this exact body.\n")
    assert not merge_note_evidence(note, incoming)
    assert not append_cluster_query_to_existing(note, 'second, "query"')
    assert note.read_text(encoding="utf-8") == after


@pytest.mark.parametrize("metadata", [
    "cluster_queries: custom-scalar\nprovenance: {}",
    "cluster_queries: [initial]\nprovenance: custom-scalar",
    "cluster_queries: [initial]\nsource_records: custom-scalar",
    "cluster_queries: [initial]\nprovenance: {}\nprovenance: {}",
    "cluster_queries: [initial]\nprovenance: [",
    "cluster_queries: &q [initial]\ncustom: *q\nprovenance: {}",
    "common: &q [initial]\ncluster_queries: *q\nprovenance: {}",
    "common: &p {producer: original}\nprovenance: *p\ncluster_queries: [initial]",
    "provenance: &p {producer: original}\ncustom: *p\ncluster_queries: [initial]",
])
def test_existing_note_merge_failure_never_creates_duplicate_or_overwrites(metadata, handoff_env, tmp_path, capsys):
    from research_hub import cli

    cfg, created, _ = handoff_env
    path = tmp_path / "handoff.json"
    paper = _paper("Annotated Native Research Evidence", "annotated", "10.1000/annotated")
    paper["provenance"] = {"research": {"queries": ["follow-up"]}}
    paper["source_records"] = [{"source_id": "S2", "url": "https://example.test/article"}]
    path.write_text(json.dumps([paper]), encoding="utf-8")
    args = ["ingest", "--input", str(path), "--cluster", "native-review", "--query", "follow-up", "--no-verify", "--json"]
    assert cli.main(args) == 0
    capsys.readouterr()
    note = cfg.raw / "native-review" / "annotated.md"
    original = '---\ntitle: "Annotated Native Research Evidence"\ndoi: "10.1000/annotated"\nzotero-key: "TEST0"\nstatus: deep-read\n' + metadata + '\n---\n## My reading notes\nPreserve this exact annotation.\n'
    note.write_text(original, encoding="utf-8")
    assert cli.main(args) == 1
    error = json.loads(capsys.readouterr().out)["error"]
    assert "not replaced" in error["message"]
    assert note.read_text(encoding="utf-8") == original
    assert len(created) == 1


def test_unrelated_yaml_anchor_is_preserved(tmp_path):
    note = tmp_path / "anchored.md"
    original = '---\ncustom: &p {label: retained}\nother: *p\nprovenance: {producer: native}\n---\nKeep this body.\n'
    note.write_text(original, encoding="utf-8")
    assert merge_note_evidence(note, {"source_records": [{"source_id": "S1"}]})
    updated = note.read_text(encoding="utf-8")
    assert "custom: &p {label: retained}\nother: *p" in updated
    assert _metadata(updated)["custom"] == _metadata(updated)["other"]
    assert updated.endswith("Keep this body.\n")


def test_block_metadata_preserves_following_field_comment(tmp_path):
    note = tmp_path / "commented.md"
    note.write_text('---\nprovenance:\n  producer: native\n# My comment for status\nstatus: cited\n---\nKeep this body.\n', encoding="utf-8")
    assert merge_note_evidence(note, {"provenance": {"research": {"queries": ["new"]}}})
    updated = note.read_text(encoding="utf-8")
    assert "# My comment for status\nstatus: cited" in updated
    assert _metadata(updated)["status"] == "cited"


@pytest.mark.parametrize("generated_field", ["folder", "filename"])
def test_generated_paths_are_checked_before_zotero(generated_field, handoff_env, tmp_path, monkeypatch):
    from research_hub import pipeline

    cfg, created, _ = handoff_env
    paper = _paper("Generated Path Evidence", "unused", "10.1000/generated")
    paper.pop("slug")
    paper.pop("sub_category")
    derived = copy.deepcopy(paper)
    pipeline._auto_generate_missing_fields(derived, None)
    cfg.raw.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    folder = cfg.raw / derived["sub_category"]
    try:
        if generated_field == "folder":
            folder.symlink_to(outside, target_is_directory=True)
        else:
            folder.mkdir()
            (folder / (derived["slug"] + ".md")).symlink_to(outside / "target.md")
    except OSError:
        pytest.skip("Symlink creation is unavailable on this platform")
    path = tmp_path / "generated.json"
    path.write_text(json.dumps([paper]), encoding="utf-8")
    monkeypatch.setattr(pipeline, "get_client", lambda: pytest.fail("Generated unsafe path must fail before client access"))
    assert pipeline.run_pipeline(papers_json=path) == 1
    assert not created
    assert not list(outside.iterdir())


def test_native_string_authors_are_valid_for_real_ingest(handoff_env, tmp_path, capsys):
    from research_hub import cli

    cfg, created, _ = handoff_env
    paper = _paper("String Author Evidence", "string-authors", "10.1000/string-authors")
    paper["authors"] = ["Alex Example"]
    paper.pop("authors_str")
    path = tmp_path / "string-authors.json"
    path.write_text(json.dumps([paper]), encoding="utf-8")
    assert cli.main(["ingest", "--input", str(path), "--cluster", "native-review", "--no-verify", "--json"]) == 0
    capsys.readouterr()
    assert created[0]["creators"] == [{"creatorType": "author", "name": "Alex Example"}]
    metadata = _metadata((cfg.raw / "native-review" / "string-authors.md").read_text(encoding="utf-8"))
    assert "Alex Example" in metadata["authors"]


def test_native_metadata_html_entities_are_decoded_once(handoff_env, tmp_path, capsys):
    from research_hub import cli

    _, created, _ = handoff_env
    paper = _paper("Nested &amp;lt; Evidence", "nested-entity", "10.1000/entity")
    path = tmp_path / "entities.json"
    path.write_text(json.dumps([paper]), encoding="utf-8")
    assert cli.main(["ingest", "--input", str(path), "--cluster", "native-review", "--no-verify", "--json"]) == 0
    capsys.readouterr()
    assert created[0]["title"] == "Nested &lt; Evidence"


@pytest.mark.parametrize("newline", ["\n", "\r\n"], ids=["lf", "crlf"])
@pytest.mark.parametrize("incoming_cluster", ["native-review", "cross-review"])
def test_duplicate_replay_preserves_primary_cluster_links(
    incoming_cluster, newline, handoff_env, tmp_path, monkeypatch
):
    """A new query is evidence, not a request to move an existing paper."""
    from research_hub import pipeline
    from research_hub.clusters import ClusterRegistry
    from research_hub.dedup import DedupHit, DedupIndex
    from research_hub.vault.link_updater import update_cluster_links

    cfg, created, child_notes = handoff_env
    ClusterRegistry(cfg.clusters_file).create(
        query="cross query", name="Cross Review", slug="cross-review",
        zotero_collection_key="CROSS123",
    )
    paper = _paper("Synthetic Primary Cluster Evidence", "paper-p", "10.1000/primary")
    manual_body = "\n# My paper\n\nManual reading annotation: keep exactly.\n\n"
    for slug, cluster in (("paper-p", "native-review"), ("paper-q", "native-review"), ("paper-r", "cross-review")):
        path = cfg.raw / cluster / f"{slug}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f'---\ntitle: "Synthetic Evidence {slug}"\n'
            f'topic_cluster: "{cluster}"\n'
            'tags: [evidence]\nstatus: cited\nverified: true\n'
            f'doi: "{paper["doi"] if slug == "paper-p" else "10.1000/" + slug}"\n'
            f'zotero_key: {"ORIGINAL1" if slug == "paper-p" else slug.upper()}\n'
            'cluster_queries: [original query]\n---\n' + manual_body,
            encoding="utf-8",
        )
    note = cfg.raw / "native-review" / "paper-p.md"
    update_cluster_links(note, cfg.raw, "native-review")
    assert "[[paper-q]]" in note.read_text(encoding="utf-8")
    body_before = note.read_text(encoding="utf-8").split("---", 2)[2]
    other_before = (cfg.raw / "cross-review" / "paper-r.md").read_bytes()
    dedup = DedupIndex()
    dedup.add(DedupHit(source="obsidian", doi=paper["doi"], title=paper["title"],
                       zotero_key="ORIGINAL1", obsidian_path=str(note)))
    monkeypatch.setattr(pipeline, "_load_or_build_dedup", lambda *a, **kw: dedup)
    routes = []
    monkeypatch.setattr(pipeline, "_ensure_batch_subcollection",
                        lambda zot, **kw: routes.append(kw["cluster_coll"]) or "BATCH123")
    paper["source_records"] = [{"source_id": "S-cross", "url": "https://example.test/cross"}]
    paper["provenance"] = {"research": {"queries": ["cross query"]}}
    source = tmp_path / "cross-handoff.json"
    source.write_text(json.dumps([paper]), encoding="utf-8")
    kwargs = dict(papers_json=source, cluster_slug=incoming_cluster,
                  query="cross query", batch_label="synthetic", verify=False)
    assert pipeline.run_pipeline(**kwargs) == 0
    # Exercise on-disk LF and CRLF independently of the host platform.
    note.write_bytes(note.read_text(encoding="utf-8").replace("\n", newline).encode("utf-8"))
    after_bytes = note.read_bytes()
    after = note.read_text(encoding="utf-8")
    metadata = _metadata(after)
    assert metadata["topic_cluster"] == "native-review"
    assert metadata["status"] == "cited"
    assert metadata["verified"] is True
    assert metadata["zotero_key"] == "ORIGINAL1"
    assert metadata["cluster_queries"] == ["original query", "cross query"]
    assert metadata["source_records"] == paper["source_records"]
    assert metadata["provenance"] == paper["provenance"]
    assert "[[paper-q]]" in after
    assert "[[paper-r]]" not in after
    assert after.split("---", 2)[2] == body_before
    assert pipeline.run_pipeline(**kwargs) == 0
    assert note.read_bytes() == after_bytes
    assert (cfg.raw / "cross-review" / "paper-r.md").read_bytes() == other_before
    assert len(list(cfg.raw.rglob("*.md"))) == 3
    assert not created and not child_notes
    if incoming_cluster == "cross-review":
        # Observe existing destination collection routing, not new membership.
        assert routes == ["CROSS123", "CROSS123"]


@pytest.mark.parametrize("newline", ["\n", "\r\n"], ids=["lf", "crlf"])
@pytest.mark.parametrize("primary", ["absent", "absent-known-query", "empty", "unavailable"])
def test_duplicate_replay_primary_cluster_fallback(
    primary, newline, handoff_env, tmp_path, monkeypatch
):
    """Keep merge's missing-field default; don't rewrite links without metadata."""
    from research_hub import pipeline
    from research_hub.dedup import DedupHit, DedupIndex

    cfg, created, child_notes = handoff_env
    paper = _paper("Synthetic Fallback Evidence", "fallback", "10.1000/fallback")
    directory = cfg.raw / "native-review"
    directory.mkdir(parents=True, exist_ok=True)
    note = directory / "fallback.md"
    cluster_line = {"absent": "", "absent-known-query": "cluster_queries: [new query]\n", "empty": 'topic_cluster: ""\n',
                    "unavailable": 'topic_cluster: "native-review"\n'}[primary]
    body = "\n# Manual annotation\nKeep me.\n\n## Related Papers in This Cluster\n\n- [[original-sibling]]\n"
    note.write_text('---\ntitle: "Synthetic Fallback Evidence"\n' + cluster_line +
                    'status: cited\nzotero_key: ORIGINAL1\n---\n' + body, encoding="utf-8")
    body = note.read_text(encoding="utf-8").split("---", 2)[2]
    sibling = directory / "new-sibling.md"
    sibling.write_text('---\ntitle: "New Sibling"\ntopic_cluster: "native-review"\n---\n', encoding="utf-8")
    dedup = DedupIndex()
    dedup.add(DedupHit(source="obsidian", doi=paper["doi"], title=paper["title"],
                       zotero_key="ORIGINAL1", obsidian_path=str(note)))
    monkeypatch.setattr(pipeline, "_load_or_build_dedup", lambda *a, **kw: dedup)
    if primary == "unavailable":
        # Exercise the conservative guard if the link metadata parser cannot
        # read the note; evidence merging still uses real YAML parsing.
        monkeypatch.setattr(pipeline, "parse_frontmatter", lambda path: None)
    source = tmp_path / "fallback.json"
    source.write_text(json.dumps([paper]), encoding="utf-8")
    kwargs = dict(papers_json=source, cluster_slug="native-review", query="new query", verify=False)
    assert pipeline.run_pipeline(**kwargs) == 0
    # Exercise on-disk LF and CRLF independently of the host platform.
    note.write_bytes(note.read_text(encoding="utf-8").replace("\n", newline).encode("utf-8"))
    after_bytes = note.read_bytes()
    after = note.read_text(encoding="utf-8")
    metadata = _metadata(after)
    assert metadata["status"] == "cited"
    assert metadata["zotero_key"] == "ORIGINAL1"
    assert metadata["cluster_queries"] == ["new query"]
    if primary == "absent":
        assert metadata["topic_cluster"] == "native-review"
        assert "[[new-sibling]]" in after
    else:
        if primary == "absent-known-query":
            assert "topic_cluster" not in metadata
        else:
            assert metadata["topic_cluster"] == ("" if primary == "empty" else "native-review")
        assert after.split("---", 2)[2] == body
    assert pipeline.run_pipeline(**kwargs) == 0
    assert note.read_bytes() == after_bytes
    assert not created and not child_notes
