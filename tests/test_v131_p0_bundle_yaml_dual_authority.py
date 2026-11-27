"""v1.3.1 P0 fixes: non-destructive YAML frontmatter, bundle PDF matching/disambiguation,
reading_scope fail-closed, excluded filtering, and Obsidian Vault-to-Workspace import bridge.
"""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
import yaml

from research_hub.clusters import Cluster
from research_hub.notebooklm.bundle import (
    _find_pdf_for_doi,
    _match_pdf_for_note,
)
from research_hub.paper import (
    _parse_frontmatter,
    _read_paper_frontmatter,
    _rewrite_paper_frontmatter,
)
from research_hub.workspace.core import Workspace, WorkspaceError
from research_hub.workspace.server import WorkspaceServer
import research_hub.workspace.sync_hooks as sync_hooks_mod
from research_hub.workspace.sync_hooks import _reading_scope


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fetch_csrf(base: str) -> str:
    with urlopen(f"{base}/app/", timeout=5) as resp:
        html = resp.read().decode("utf-8")
    match = re.search(r'<meta name="research-hub-csrf-token" content="([^"]+)"', html)
    assert match, "CSRF meta tag not found in /app/"
    return match.group(1)


def _post_json(
    url: str,
    payload: dict,
    *,
    csrf: str | None = None,
    origin: str | None = None,
) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json"}
    if csrf is not None:
        headers["X-CSRF-Token"] = csrf
    if origin is not None:
        headers["Origin"] = origin
    req = Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# 1. paper.py: Non-destructive YAML frontmatter parsing & surgical patching
# ---------------------------------------------------------------------------


def test_parse_frontmatter_handles_multiline_nested_and_commas():
    text = (
        "---\n"
        'title: "Bounded Rationality"\n'
        "authors:\n"
        '  - "Simon, Herbert A."\n'
        '  - "March, James G."\n'
        "abstract: |\n"
        "  First paragraph line.\n"
        "  Second paragraph line.\n"
        "summary: >\n"
        "  Folded summary\n"
        "  across two lines.\n"
        "provenance:\n"
        "  fit_score: 5\n"
        "  source: crossref\n"
        "---\n"
        "# Body\n"
    )
    parsed = _parse_frontmatter(text)
    assert _read_paper_frontmatter(text) == parsed
    assert parsed["authors"] == ["Simon, Herbert A.", "March, James G."]
    assert "First paragraph line.\nSecond paragraph line." in parsed["abstract"]
    assert "Folded summary across two lines." in parsed["summary"]
    assert parsed["provenance"] == {"fit_score": 5, "source": "crossref"}


def test_parse_frontmatter_falls_back_to_legacy_on_yaml_error():
    bad_yaml_text = (
        "---\n"
        "title: Unquoted Title: With Colon\n"
        "labels: [seed, core]\n"
        "---\n"
        "Body\n"
    )
    parsed = _parse_frontmatter(bad_yaml_text)
    assert parsed["title"] == "Unquoted Title: With Colon"
    assert parsed["labels"] == ["seed", "core"]


def test_rewrite_paper_frontmatter_preserves_comments_multiline_nested_order_and_deletes_none(
    tmp_path: Path,
):
    note = tmp_path / "simon1955.md"
    raw_frontmatter = (
        "# Top-level curator note\n"
        'title: "A Behavioral Model of Rational Choice" # inline keep\n'
        "authors:\n"
        '  - "Simon, Herbert A."\n'
        "abstract: |\n"
        "  Line one of abstract.\n"
        "  Line two of abstract.\n"
        "provenance:\n"
        "  discovered_by: search\n"
        "  fit_score: 5\n"
        "stale_flag: true\n"
        "# Comment between keys\n"
        'status: "unread"\n'
        'tail_note: "keep-at-end"'
    )
    body = "# Heading\n\nBody remains untouched.\n"
    original = f"---\n{raw_frontmatter}\n---\n{body}"
    note.write_bytes(original.encode("utf-8"))

    _rewrite_paper_frontmatter(
        note,
        {
            "status": "read",
            "stale_flag": None,
            "absent_key": None,
            "labels": ["seed", "core"],
        },
    )

    updated_bytes = note.read_bytes()
    assert b"\r\n" not in updated_bytes
    updated = updated_bytes.decode("utf-8")

    # Untouched fields, comments, multiline blocks, and nested dicts stay intact byte-for-byte
    assert "# Top-level curator note\n" in updated
    assert 'title: "A Behavioral Model of Rational Choice" # inline keep\n' in updated
    assert 'authors:\n  - "Simon, Herbert A."\n' in updated
    assert "abstract: |\n  Line one of abstract.\n  Line two of abstract.\n" in updated
    assert "provenance:\n  discovered_by: search\n  fit_score: 5\n" in updated
    assert "# Comment between keys\n" in updated
    assert 'tail_note: "keep-at-end"\n' in updated
    assert updated.endswith(f"\n---\n{body}")

    # Deleted key gone cleanly; updated and added keys present and valid YAML
    assert "stale_flag" not in updated
    assert "absent_key" not in updated
    assert 'status: "read"' in updated
    assert "labels:\n  - seed\n  - core" in updated

    # Key order preserved (title before authors before abstract before provenance before status before tail_note before labels)
    for earlier, later in (
        ("title:", "authors:"),
        ("authors:", "abstract:"),
        ("abstract:", "provenance:"),
        ("provenance:", "status:"),
        ("status:", "tail_note:"),
        ("tail_note:", "labels:"),
    ):
        assert updated.index(earlier) < updated.index(later)

    reloaded = yaml.safe_load(updated.split("\n---\n", 1)[0][4:])
    assert reloaded["status"] == "read"
    assert reloaded["labels"] == ["seed", "core"]
    assert "stale_flag" not in reloaded
    assert reloaded["provenance"] == {"discovered_by": "search", "fit_score": 5}


# ---------------------------------------------------------------------------
# 2. notebooklm/bundle.py: Strict PDF matching & basename collision handling
# ---------------------------------------------------------------------------


def test_match_pdf_enforces_token_boundary_and_rejects_short_or_ambiguous_tail(tmp_path: Path):
    pdfs = tmp_path / "pdfs"
    pdfs.mkdir()

    # Substring trap: tail "1234" must NOT match "12345.pdf" or "x1234y.pdf"
    p_longer = pdfs / "10.1000_12345.pdf"
    p_embedded = pdfs / "paper_x1234y.pdf"
    p_longer.write_bytes(b"%PDF")
    p_embedded.write_bytes(b"%PDF")
    assert _find_pdf_for_doi(pdfs, "10.1000/1234") is None

    # Short tail (<4 chars) must NOT match via tail fallback
    p_short = pdfs / "abc.pdf"
    p_short.write_bytes(b"%PDF")
    assert _find_pdf_for_doi(pdfs, "10.1000/abc") is None

    # Full normalized DOI match works even if tail < 4
    p_full_hyphen = pdfs / "10.1000-abc.pdf"
    p_full_hyphen.write_bytes(b"%PDF")
    assert _find_pdf_for_doi(pdfs, "10.1000/abc") == p_full_hyphen

    # Ambiguous tail (>=2 PDFs matching tail token boundary) returns None
    p_amb1 = pdfs / "study_s41599_v1.pdf"
    p_amb2 = pdfs / "study_s41599_v2.pdf"
    p_amb1.write_bytes(b"%PDF")
    p_amb2.write_bytes(b"%PDF")
    assert _find_pdf_for_doi(pdfs, "10.1057/s41599") is None

    # Exact note_path.stem match works even when tail is ambiguous/absent
    note_path = tmp_path / "raw" / "alpha" / "my_custom_stem.md"
    p_stem = pdfs / "my_custom_stem.pdf"
    p_stem.write_bytes(b"%PDF")
    assert _match_pdf_for_note(pdfs, note_path, "10.1057/s41599") == p_stem


def test_bundle_cluster_disambiguates_colliding_pdf_basenames(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = tmp_path / "vault"
    raw = root / "raw" / "alpha"
    pdfs = root / "pdfs"
    (pdfs / "a").mkdir(parents=True)
    (pdfs / "b").mkdir(parents=True)
    (pdfs / "c").mkdir(parents=True)
    raw.mkdir(parents=True)
    (root / ".research_hub").mkdir()

    # Two distinct PDFs sharing basename "paper.pdf", plus a 3rd where note_c_paper.pdf is ALSO pre-occupied
    pdf_a = pdfs / "a" / "paper.pdf"
    pdf_b = pdfs / "b" / "paper.pdf"
    pdf_c = pdfs / "c" / "paper.pdf"
    pdf_a.write_bytes(b"PDF-A")
    pdf_b.write_bytes(b"PDF-B")
    pdf_c.write_bytes(b"PDF-C")

    # Pre-create note_4_paper.pdf so note_4's disambiguated name collides and triggers -{n}
    (raw / "note_1.md").write_text("---\ntitle: N1\ndoi: 10.1/1\ntopic_cluster: alpha\n---\n", encoding="utf-8")
    (raw / "note_2.md").write_text("---\ntitle: N2\ndoi: 10.1/2\ntopic_cluster: alpha\n---\n", encoding="utf-8")
    (raw / "note_3.md").write_text("---\ntitle: N3\ndoi: 10.1/3\ntopic_cluster: alpha\n---\n", encoding="utf-8")
    (raw / "note_4.md").write_text("---\ntitle: N4\ndoi: 10.1/4\ntopic_cluster: alpha\n---\n", encoding="utf-8")
    pdf_pre = pdfs / "note_4_paper.pdf"
    pdf_pre.write_bytes(b"PDF-PRE")

    doi_map = {
        "10.1/1": pdf_a,
        "10.1/2": pdf_b,
        "10.1/3": pdf_pre,
        "10.1/4": pdf_c,
    }
    cfg = SimpleNamespace(root=root, raw=root / "raw", research_hub_dir=root / ".research_hub")
    cluster = Cluster(slug="alpha", name="Alpha", obsidian_subfolder="alpha")

    import research_hub.notebooklm.bundle as bundle_mod

    monkeypatch.setattr(bundle_mod, "_find_pdf_for_doi", lambda pdir, doi, **kw: doi_map.get(doi))
    report = bundle_mod.bundle_cluster(cluster, cfg)

    assert report.pdf_count == 4
    dest_paths = [Path(e.pdf_path) for e in report.entries]
    dest_names = [p.name for p in dest_paths]
    assert dest_names == ["paper.pdf", "note_2_paper.pdf", "note_4_paper.pdf", "note_4_paper-2.pdf"]
    assert [p.read_bytes() for p in dest_paths] == [b"PDF-A", b"PDF-B", b"PDF-PRE", b"PDF-C"]


# ---------------------------------------------------------------------------
# 3. sync_hooks.py: _reading_scope fail-closed & screening==exclude filtering
# ---------------------------------------------------------------------------


def test_reading_scope_prefers_reading_scope_and_fails_closed_on_disagreement():
    from research_hub.workspace.core import resolve_reading_scope
    from research_hub.workspace.native_summary import _scope

    assert _reading_scope({"reading_scope": "abstract", "reading_level": "full-text"}) == "abstract"
    assert _reading_scope({"reading_scope": "full-text", "reading_level": "abstract-only"}) == "abstract-only"
    assert _reading_scope({"reading_scope": "note-metadata", "reading_level": "selected-sections"}) == "note-metadata"
    assert _reading_scope({"reading_scope": "not-read", "reading_level": "abstract-snippet"}) == "not-read"
    assert _reading_scope({"reading_scope": "selected-sections", "reading_level": "excerpt"}) == "selected-sections"
    assert _reading_scope({"reading_scope": "selected-sections", "reading_level": "metadata-only"}) == "metadata-only"
    assert _reading_scope({"reading_scope": "full-text", "reading_level": "custom-unrecognized"}) == "custom-unrecognized"
    # Absent (None / "") falls back to the other field
    assert _reading_scope({"reading_scope": None, "reading_level": "abstract"}) == "abstract"
    assert _reading_scope({"reading_scope": "", "reading_level": "abstract"}) == "abstract"
    assert _reading_scope({"reading_scope": "full-text", "reading_level": None}) == "full-text"
    assert _reading_scope({"reading_scope": "full-text", "reading_level": ""}) == "full-text"
    # Explicit "unknown" ranks 0 and fails closed over wider claims
    assert _reading_scope({"reading_scope": "unknown", "reading_level": "abstract"}) == "unknown"
    assert _reading_scope({"reading_scope": "full-text", "reading_level": "unknown"}) == "unknown"
    assert _reading_scope({}) == "unknown"

    # native_summary._scope shares canonical resolve_reading_scope
    sample = {"reading_scope": "full-text", "reading_level": "abstract-only"}
    assert _scope({"data": sample}) == resolve_reading_scope(sample) == "abstract-only"
    assert _scope({"data": {"reading_scope": "full-text", "reading_level": "unknown"}}) == "unknown"


def test_notebooklm_bundle_excludes_screened_out_and_keeps_disagreed_out_of_fulltext(tmp_path: Path):
    ws = Workspace(tmp_path / "ws")
    ws.create_project(id="proj-scope", title="Scope Test", archetype="review")
    s_keep_full = ws.add_record(
        "proj-scope",
        kind="source",
        data={"title": "True Full Text", "locator": "https://example.org/1", "reading_scope": "full-text"},
    )
    s_trap_mismatch = ws.add_record(
        "proj-scope",
        kind="source",
        data={
            "title": "Abstract Mismatch",
            "locator": "https://example.org/2",
            "reading_scope": "abstract-only",
            "reading_level": "full-text",
        },
    )
    s_excluded = ws.add_record(
        "proj-scope",
        kind="source",
        data={"title": "Excluded Paper", "locator": "https://example.org/3", "reading_scope": "full-text"},
    )
    ws.add_record(
        "proj-scope",
        kind="screening",
        data={"source_id": s_excluded["id"], "decision": "exclude", "rationale": "Out of scope"},
    )

    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text("{}", encoding="utf-8")
    from research_hub.workspace.integrations import LocalIntegrationsManager
    from research_hub.workspace.sync_hooks import WorkspaceSyncHooks

    hooks = WorkspaceSyncHooks(ws, LocalIntegrationsManager(cfg_path))
    res = hooks.bundle_notebooklm("proj-scope", {})
    assert res["source_count"] == 2
    assert res["full_text_count"] == 1
    assert res["abstract_or_metadata_count"] == 1

    manifest = json.loads((ws.root / res["manifest_file"]).read_text(encoding="utf-8"))
    by_id = {m["source_id"]: m for m in manifest["sources"]}
    assert s_excluded["id"] not in by_id
    assert by_id[s_keep_full["id"]]["reading_scope"] == "full-text"
    assert by_id[s_trap_mismatch["id"]]["reading_scope"] == "abstract-only"


# ---------------------------------------------------------------------------
# 4. Decision #2: Obsidian Vault-to-Workspace Import Bridge
# ---------------------------------------------------------------------------


def _build_vault(vault: Path) -> dict[str, str]:
    (vault / ".obsidian").mkdir(parents=True)
    (vault / ".research_hub").mkdir()
    (vault / ".research_hub" / "clusters.yaml").write_text(
        "schema_version: '1.0'\n"
        "clusters:\n"
        "  alpha:\n"
        "    name: Alpha\n"
        "    status: active\n"
        "    obsidian_subfolder: alpha\n"
        "  beta:\n"
        "    name: Beta\n"
        "    status: active\n"
        "    obsidian_subfolder: beta\n",
        encoding="utf-8",
    )
    (vault / "raw" / "alpha").mkdir(parents=True)
    (vault / "raw" / "beta").mkdir(parents=True)

    (vault / "raw" / "alpha" / "n1.md").write_text(
        "---\n"
        'title: "Agentic Flood Simulation"\n'
        'doi: "10.1029/2025WR000001"\n'
        'year: "2025"\n'
        'authors: ["Lin, Mei-Hua", "Chen, Wei"]\n'
        'abstract: "Simulating flood response."\n'
        'category: "simulation"\n'
        'tags: ["hydrology", "abm"]\n'
        'zotero_key: "ZOTKEY01"\n'
        "---\nBody 1\n",
        encoding="utf-8",
    )
    (vault / "raw" / "alpha" / "n2.md").write_text(
        "---\n"
        'title: "Classic Decision Theory"\n'
        'year: "1955"\n'
        'authors: ["Simon, Herbert A."]\n'
        'category: "classic"\n'
        "---\nBody 2\n",
        encoding="utf-8",
    )
    (vault / "raw" / "beta" / "n3.md").write_text(
        "---\n"
        'title: "Beta Benchmark"\n'
        'doi: "10.1000/beta-2024"\n'
        'year: "2024"\n'
        'url: "https://example.org/beta"\n'
        "---\nBody 3\n",
        encoding="utf-8",
    )
    from research_hub.workspace.library_snapshot import read_vault_snapshot

    snap = read_vault_snapshot(vault)
    return {n["data"]["note_path"]: n["id"] for n in snap["notes"]}


def test_obsidian_import_bridge_dry_run_dedup_apply_and_errors(tmp_path: Path):
    vault = tmp_path / "vault"
    note_ids_by_path = _build_vault(vault)
    vault_snapshot_before = {
        str(p.relative_to(vault)): (p.stat().st_mtime_ns, p.stat().st_size if p.is_file() else -1)
        for p in vault.rglob("*")
    }

    ws = Workspace(tmp_path / "ws")
    ws.create_project(id="proj-bridge", title="Bridge Project", archetype="review")
    # Pre-seed a source matching n1 by normalized DOI (with https://doi.org/ prefix)
    ws.add_record(
        "proj-bridge",
        kind="source",
        data={
            "title": "Pre-existing Agentic Flood",
            "locator": "https://doi.org/10.1029/2025WR000001",
            "doi": "https://doi.org/10.1029/2025wr000001",
        },
    )

    cfg_path = tmp_path / "cfg" / "config.json"
    cfg_path.parent.mkdir(parents=True)
    cfg_path.write_text("{}", encoding="utf-8")

    # 1. Server without obsidian_vault returns 400 obsidian_not_configured
    srv_no_vault = WorkspaceServer(ws.root, port=0, integrations_config=cfg_path)
    t_nv = threading.Thread(target=srv_no_vault.serve_forever, daemon=True)
    t_nv.start()
    try:
        base_nv = f"http://127.0.0.1:{srv_no_vault.server_port}"
        csrf_nv = _fetch_csrf(base_nv)
        code, body = _post_json(
            f"{base_nv}/api/v1/projects/proj-bridge/integrations/obsidian/import",
            {"dry_run": True},
            csrf=csrf_nv,
            origin=base_nv,
        )
        assert code == 400 and body["code"] == "obsidian_not_configured"
    finally:
        srv_no_vault.shutdown()
        srv_no_vault.server_close()
        t_nv.join(timeout=5)

    # 2. Server with obsidian_vault
    server = WorkspaceServer(ws.root, port=0, obsidian_vault=vault, integrations_config=cfg_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        csrf = _fetch_csrf(base)
        route = f"{base}/api/v1/projects/proj-bridge/integrations/obsidian/import"

        # Unsupported key -> 400 invalid_request
        code_bad, body_bad = _post_json(route, {"unknown_key": 1}, csrf=csrf, origin=base)
        assert code_bad == 400 and body_bad["code"] == "invalid_request"

        # Missing note_id -> 400 invalid_source
        code_miss, body_miss = _post_json(
            route, {"note_ids": ["obsidian:000000000000000000000000"]}, csrf=csrf, origin=base
        )
        assert code_miss == 400 and body_miss["code"] == "invalid_source"

        # Dry-run for collection alpha: n1 skipped (DOI dup), n2 would_import (DOI-less classic)
        code_dry, dry_res = _post_json(
            route, {"collection_id": "alpha", "dry_run": True}, csrf=csrf, origin=base
        )
        assert code_dry == 200 and dry_res["ok"] is True
        assert dry_res["dry_run"] is True
        assert dry_res["would_import"] == 1
        assert dry_res["skipped_existing"] == 1
        assert [i["action"] for i in dry_res["items"]] == ["skip_existing", "import"]
        assert len([r for r in ws.records("proj-bridge") if r["kind"] == "source"]) == 1

        # Apply import for all collections (n1 skipped, n2 + n3 created)
        code_apply, apply_res = _post_json(route, {"dry_run": False}, csrf=csrf, origin=base)
        assert code_apply == 200 and apply_res["ok"] is True
        assert apply_res["dry_run"] is False
        assert apply_res["imported_count"] == 2
        assert apply_res["skipped_existing"] == 1
        assert len(apply_res["created_ids"]) == 2

        sources = [r for r in ws.records("proj-bridge") if r["kind"] == "source"]
        assert len(sources) == 3
        imported_n2 = next(r for r in sources if r["data"].get("origin_note_path") == "raw/alpha/n2.md")
        assert imported_n2["data"]["upstream_id"] == note_ids_by_path["raw/alpha/n2.md"]
        assert imported_n2["data"]["batch_id"].startswith("obsidian-vault:")
        assert dry_res["truncated"] is False
        assert apply_res["truncated"] is False
        assert imported_n2["data"]["reading_scope"] == "note-metadata"
        assert imported_n2["data"]["reading_level"] == "note-metadata"
        assert imported_n2["data"]["identity_status"] == "unverified"
        assert imported_n2["data"]["human_acceptance"] == "pending"
        assert imported_n2["data"]["authors"] == ["Simon, Herbert A."]
        assert imported_n2["data"]["locator"] == "obsidian:raw/alpha/n2.md"

        imported_n3 = next(r for r in sources if r["data"].get("origin_note_path") == "raw/beta/n3.md")
        assert imported_n3["data"]["locator"] == "https://example.org/beta"
        assert imported_n3["data"]["doi"] == "10.1000/beta-2024"

        # Re-running import deduplicates by origin_note_path / (title, year) / doi
        code_re, re_res = _post_json(route, {"dry_run": False}, csrf=csrf, origin=base)
        assert code_re == 200 and re_res["imported_count"] == 0 and re_res["skipped_existing"] == 3

        # Verify vault was never modified
        vault_snapshot_after = {
            str(p.relative_to(vault)): (p.stat().st_mtime_ns, p.stat().st_size if p.is_file() else -1)
            for p in vault.rglob("*")
        }
        assert vault_snapshot_before == vault_snapshot_after
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_obsidian_import_dedups_by_zotero_key_and_title_year(tmp_path: Path):
    vault = tmp_path / "vault"
    _build_vault(vault)

    ws = Workspace(tmp_path / "ws")
    ws.create_project(id="proj-dedup", title="Dedup Test", archetype="review")
    ws.add_record(
        "proj-dedup",
        kind="source",
        data={
            "title": "Different Title Same Zotero",
            "locator": "https://example.org/zot",
            "zotero_key": "zotkey01",
        },
    )
    ws.add_record(
        "proj-dedup",
        kind="source",
        data={
            "title": "  classic decision theory ",
            "locator": "https://example.org/classic",
            "year": "1955",
        },
    )

    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text("{}", encoding="utf-8")
    from research_hub.workspace.integrations import LocalIntegrationsManager
    from research_hub.workspace.obsidian_validation import ObsidianValidation
    from research_hub.workspace.sync_hooks import WorkspaceSyncHooks

    hooks = WorkspaceSyncHooks(
        ws,
        LocalIntegrationsManager(cfg_path),
        obsidian_validation=ObsidianValidation(vault),
    )
    res = hooks.import_obsidian_notes("proj-dedup", {"dry_run": True})
    assert res["would_import"] == 1
    assert res["skipped_existing"] == 2
    assert res["truncated"] is False
    imported = [i for i in res["items"] if i["action"] == "import"]
    assert len(imported) == 1
    assert imported[0]["note_path"] == "raw/beta/n3.md"


# ---------------------------------------------------------------------------
# 5. Astra gate §4-§6 regression tests
# ---------------------------------------------------------------------------


def test_yaml_list_quoting_verification_empty_block_comments_and_literal_plus(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from research_hub.paper import _NoTimestampSafeLoader, _split_frontmatter
    import research_hub.paper as paper_mod

    # Safe list quoting preserves strings with colons, YAML booleans, hashes, and ints
    note = tmp_path / "list_types.md"
    note.write_text("---\ntitle: \"Test\"\n---\nBody\n", encoding="utf-8")
    mixed_labels = ["A: B", "yes", "x # y", "true", "null", "seed", 42]
    _rewrite_paper_frontmatter(note, {"labels": mixed_labels})
    raw_fm = _split_frontmatter(note.read_text(encoding="utf-8"))[1]
    reloaded = yaml.load(raw_fm, Loader=_NoTimestampSafeLoader)
    assert reloaded["labels"] == mixed_labels
    assert [type(x) for x in reloaded["labels"]] == [type(x) for x in mixed_labels]

    # Round-trip verification aborts without writing when rendered YAML corrupts types
    before_bytes = note.read_bytes()
    monkeypatch.setattr(paper_mod, "_render_patch_field", lambda k, v, nl: f"{k}:{nl}  - yes")
    with pytest.raises(ValueError):
        _rewrite_paper_frontmatter(note, {"labels": ["yes"]})
    assert note.read_bytes() == before_bytes
    monkeypatch.undo()

    # Preserve |+ trailing blank lines when appending a new key under both LF and CRLF
    for nl in ("\n", "\r\n"):
        nl_tag = "crlf" if nl == "\r\n" else "lf"
        note_plus = tmp_path / f"literal_plus_{nl_tag}.md"
        note_plus.write_bytes(
            f"---{nl}notes: |+{nl}  Line 1{nl}{nl}{nl}---{nl}Body{nl}".encode("utf-8")
        )
        raw_before = note_plus.read_bytes().decode("utf-8")
        full_fm_before = raw_before.split(f"---{nl}", 1)[1].split(f"---{nl}", 1)[0]
        assert yaml.safe_load(full_fm_before)["notes"] == "Line 1\n\n\n"
        _rewrite_paper_frontmatter(note_plus, {"labels": ["seed"]})
        raw_after_bytes = note_plus.read_bytes()
        if nl == "\n":
            assert b"\r\n" not in raw_after_bytes
        else:
            assert b"\r\n" in raw_after_bytes
        raw_after = raw_after_bytes.decode("utf-8")
        full_fm_after = raw_after.split(f"---{nl}", 1)[1].split(f"---{nl}", 1)[0]
        reloaded_plus = yaml.safe_load(full_fm_after)
        assert reloaded_plus["notes"] == "Line 1\n\n\n"
        assert reloaded_plus["labels"] == ["seed"]

    # Adjacent ---\n---\nBody stops at first --- without scanning into Markdown horizontal rules
    note_empty = tmp_path / "empty_fm.md"
    note_empty.write_text("---\n---\nBody\n---\nLater rule\n", encoding="utf-8")
    _rewrite_paper_frontmatter(note_empty, {"labels": ["seed"]})
    updated_empty = note_empty.read_text(encoding="utf-8")
    assert updated_empty == "---\nlabels:\n  - seed\n---\nBody\n---\nLater rule\n"

    # Comment-only frontmatter preserves comment non-destructively
    note_comment = tmp_path / "comment_only.md"
    note_comment.write_text("---\n# curator note\n---\nBody\n", encoding="utf-8")
    _rewrite_paper_frontmatter(note_comment, {"labels": ["seed"]})
    updated_comment = note_comment.read_text(encoding="utf-8")
    assert "# curator note\n" in updated_comment
    assert "labels:\n  - seed\n" in updated_comment

    # Non-mapping YAML sequence and malformed YAML with interior comments/nested blocks fail closed without touching disk
    note_seq = tmp_path / "sequence_fm.md"
    note_seq.write_bytes(b"---\n- curator-a\n- curator-b\n---\nBody\n")
    seq_before = note_seq.read_bytes()
    with pytest.raises(ValueError, match="valid YAML mapping"):
        _rewrite_paper_frontmatter(note_seq, {"labels": ["seed"]})
    assert note_seq.read_bytes() == seq_before

    note_broken = tmp_path / "broken_yaml.md"
    note_broken.write_bytes(
        b"---\n# leading curator note\nprovenance:\n  fit_score: 5\n# interior comment\ntitle: Unquoted: Colon\n---\nBody\n"
    )
    broken_before = note_broken.read_bytes()
    with pytest.raises(ValueError, match="valid YAML mapping"):
        _rewrite_paper_frontmatter(note_broken, {"labels": ["seed"]})
    assert note_broken.read_bytes() == broken_before


def test_bundle_pdf_rejects_conflicting_doi_dot_suffix_escapes_and_records_source(tmp_path: Path):
    import research_hub.notebooklm.bundle as bundle_mod

    root = tmp_path / "vault"
    pdfs = root / "pdfs"
    raw = root / "raw" / "alpha"
    pdfs.mkdir(parents=True)
    raw.mkdir(parents=True)
    (root / ".research_hub").mkdir()

    # Conflicting DOI, .2 extension suffix, and short numeric tail must all be rejected
    (pdfs / "10.9999_1234.pdf").write_bytes(b"%PDF-wrong-prefix")
    (pdfs / "10.1234_1234.2.pdf").write_bytes(b"%PDF-dot-two")
    (pdfs / "unrelated_1234.pdf").write_bytes(b"%PDF-short-num")
    assert _find_pdf_for_doi(pdfs, "10.1234/1234") is None

    # Symlink escape outside pdfs_dir must be skipped
    outside_pdf = tmp_path / "outside.pdf"
    outside_pdf.write_bytes(b"%PDF-outside")
    escape_link = pdfs / "10.1234_escape.pdf"
    try:
        escape_link.symlink_to(outside_pdf)
    except OSError:
        pass
    else:
        assert _find_pdf_for_doi(pdfs, "10.1234/escape") is None

    # Ambiguous stem or author_year returns None
    (pdfs / "a").mkdir()
    (pdfs / "b").mkdir()
    (pdfs / "a" / "shared_stem.pdf").write_bytes(b"%PDF-1")
    (pdfs / "b" / "shared_stem.pdf").write_bytes(b"%PDF-2")
    assert _match_pdf_for_note(pdfs, raw / "shared_stem.md", "") is None

    # pdf_source distinguishes local-doi vs local-slug (stem and author/year)
    (raw / "doi_note.md").write_text("---\ntitle: D\ndoi: 10.1000/abc\ntopic_cluster: alpha\n---\n", encoding="utf-8")
    (pdfs / "10.1000_abc.pdf").write_bytes(b"%PDF-doi")
    (raw / "stem_note.md").write_text("---\ntitle: S\ndoi: 10.1000/unmatched\ntopic_cluster: alpha\n---\n", encoding="utf-8")
    (pdfs / "stem_note.pdf").write_bytes(b"%PDF-stem")
    (raw / "author_note.md").write_text(
        "---\ntitle: A\nauthors: \"Ben-Zion, Y.\"\nyear: 2025\ntopic_cluster: alpha\n---\n",
        encoding="utf-8",
    )
    (pdfs / "Ben-Zion_2025.pdf").write_bytes(b"%PDF-auth")

    cfg = SimpleNamespace(root=root, raw=root / "raw", research_hub_dir=root / ".research_hub")
    cluster = Cluster(slug="alpha", name="Alpha", obsidian_subfolder="alpha")
    r1 = bundle_mod.bundle_cluster(cluster, cfg)
    r2 = bundle_mod.bundle_cluster(cluster, cfg)
    assert r1.bundle_dir != r2.bundle_dir
    assert r1.bundle_dir.exists() and r2.bundle_dir.exists()

    by_title = {e.title: e for e in r1.entries}
    assert by_title["D"].pdf_source == "local-doi"
    assert by_title["S"].pdf_source == "local-slug"
    assert by_title["A"].pdf_source == "local-slug"


def test_bundle_cluster_case_insensitive_pdf_collision_no_clobber(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    import research_hub.notebooklm.bundle as bundle_mod

    root = tmp_path / "vault"
    raw = root / "raw" / "alpha"
    pdfs = root / "pdfs"
    (pdfs / "d1").mkdir(parents=True)
    (pdfs / "d2").mkdir(parents=True)
    raw.mkdir(parents=True)
    (root / ".research_hub").mkdir()

    pdf_upper = pdfs / "d1" / "Paper.pdf"
    pdf_lower = pdfs / "d2" / "paper.pdf"
    pdf_upper.write_bytes(b"UPPER")
    pdf_lower.write_bytes(b"LOWER")

    (raw / "n1.md").write_text("---\ntitle: N1\ndoi: 10.1/1\ntopic_cluster: alpha\n---\n", encoding="utf-8")
    (raw / "n2.md").write_text("---\ntitle: N2\ndoi: 10.1/2\ntopic_cluster: alpha\n---\n", encoding="utf-8")
    doi_map = {"10.1/1": pdf_upper, "10.1/2": pdf_lower}
    monkeypatch.setattr(bundle_mod, "_find_pdf_for_doi", lambda pdir, doi, **kw: doi_map.get(doi))

    cfg = SimpleNamespace(root=root, raw=root / "raw", research_hub_dir=root / ".research_hub")
    cluster = Cluster(slug="alpha", name="Alpha", obsidian_subfolder="alpha")
    report = bundle_mod.bundle_cluster(cluster, cfg)
    names = [Path(e.pdf_path).name for e in report.entries]
    assert names == ["Paper.pdf", "n2_paper.pdf"]
    assert [Path(e.pdf_path).read_bytes() for e in report.entries] == [b"UPPER", b"LOWER"]


def test_screening_inline_and_selected_source_ids_exclusion(tmp_path: Path):
    from research_hub.workspace.integrations import LocalIntegrationsManager
    from research_hub.workspace.sync_hooks import WorkspaceSyncHooks

    ws = Workspace(tmp_path / "ws")
    ws.create_project(id="proj-scr", title="Screening", archetype="review")
    s_keep = ws.add_record(
        "proj-scr", kind="source", data={"title": "Keep", "locator": "https://example.org/k"}
    )
    s_inline_ex = ws.add_record(
        "proj-scr",
        kind="source",
        data={"title": "Inline Ex", "locator": "https://example.org/ie", "screening": "exclude"},
    )
    s_rec_ex = ws.add_record(
        "proj-scr", kind="source", data={"title": "Rec Ex", "locator": "https://example.org/re"}
    )
    ws.add_record(
        "proj-scr",
        kind="screening",
        data={"source_id": s_rec_ex["id"], "decision": "exclude", "rationale": "Rejected"},
    )

    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text("{}", encoding="utf-8")
    hooks = WorkspaceSyncHooks(ws, LocalIntegrationsManager(cfg_path))

    res = hooks.bundle_notebooklm("proj-scr", {})
    assert res["source_count"] == 1
    manifest = json.loads((ws.root / res["manifest_file"]).read_text(encoding="utf-8"))
    assert [m["source_id"] for m in manifest["sources"]] == [s_keep["id"]]

    for bad_id in (s_inline_ex["id"], s_rec_ex["id"]):
        with pytest.raises(WorkspaceError) as exc_info:
            hooks.bundle_notebooklm("proj-scr", {"selected_source_ids": [bad_id]})
        assert exc_info.value.code == "invalid_source"


def test_library_snapshot_filters_without_opening_unrelated_and_parses_classic_authors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    import research_hub.workspace.library_snapshot as ls_mod

    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    (vault / ".research_hub").mkdir()
    (vault / ".research_hub" / "clusters.yaml").write_text(
        "schema_version: '1.0'\nclusters:\n"
        "  alpha:\n    name: Alpha\n    status: active\n    obsidian_subfolder: alpha\n"
        "  beta:\n    name: Beta\n    status: active\n    obsidian_subfolder: beta\n",
        encoding="utf-8",
    )
    (vault / "raw" / "alpha").mkdir(parents=True)
    (vault / "raw" / "beta").mkdir(parents=True)
    (vault / "raw" / "alpha" / "classic.md").write_text(
        '---\ntitle: "Wealth of Nations"\nyear: 1776\nauthors: "Smith, Adam; Doe, Jane"\n---\nBody\n',
        encoding="utf-8",
    )
    (vault / "raw" / "alpha" / "other.md").write_text('---\ntitle: "Other"\n---\nBody\n', encoding="utf-8")
    (vault / "raw" / "beta" / "secret.md").write_text('---\ntitle: "Secret"\n---\nBody\n', encoding="utf-8")

    opened_paths: list[str] = []
    orig_extract = ls_mod._extract_frontmatter_incremental

    def spy_extract(path: Path):
        opened_paths.append(path.name)
        return orig_extract(path)

    monkeypatch.setattr(ls_mod, "_extract_frontmatter_incremental", spy_extract)

    full = ls_mod.read_vault_snapshot(vault)
    classic_id = next(n["id"] for n in full["notes"] if n["data"]["note_path"] == "raw/alpha/classic.md")

    opened_paths.clear()
    scoped = ls_mod.read_vault_snapshot(vault, collection_id="alpha", note_ids=[classic_id])
    assert opened_paths == ["classic.md"]
    assert len(scoped["notes"]) == 1
    ndata = scoped["notes"][0]["data"]
    assert ndata["year"] == "1776"
    assert ndata["authors"] == ["Smith, Adam", "Doe, Jane"]


def test_obsidian_import_conflict_aware_title_year_and_concurrency_lock(tmp_path: Path):
    from research_hub.workspace.integrations import LocalIntegrationsManager
    from research_hub.workspace.obsidian_validation import ObsidianValidation
    from research_hub.workspace.sync_hooks import WorkspaceSyncHooks

    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    (vault / ".research_hub").mkdir()
    (vault / ".research_hub" / "clusters.yaml").write_text(
        "schema_version: '1.0'\nclusters:\n  alpha:\n    name: Alpha\n    status: active\n    obsidian_subfolder: alpha\n",
        encoding="utf-8",
    )
    (vault / "raw" / "alpha").mkdir(parents=True)
    (vault / "raw" / "alpha" / "atlas_b.md").write_text(
        '---\ntitle: "Atlas"\nyear: "2020"\ndoi: "10.1000/b"\n---\nBody\n',
        encoding="utf-8",
    )
    (vault / "raw" / "alpha" / "atlas_z2.md").write_text(
        '---\ntitle: "Atlas II"\nyear: "2020"\nzotero_key: "Z2"\n---\nBody\n',
        encoding="utf-8",
    )

    ws = Workspace(tmp_path / "ws")
    ws.create_project(id="proj-c", title="Conflict Test", archetype="review")
    ws.add_record(
        "proj-c",
        kind="source",
        data={"title": "Atlas", "locator": "https://doi.org/10.1000/a", "doi": "10.1000/a", "year": "2020"},
    )
    ws.add_record(
        "proj-c",
        kind="source",
        data={"title": "Atlas II", "locator": "https://example.org/z1", "year": "2020", "zotero_key": "Z1"},
    )

    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text("{}", encoding="utf-8")
    hooks = WorkspaceSyncHooks(
        ws,
        LocalIntegrationsManager(cfg_path),
        obsidian_validation=ObsidianValidation(vault),
    )

    res1 = hooks.import_obsidian_notes("proj-c", {"dry_run": False})
    assert res1["imported_count"] == 2
    assert res1["skipped_existing"] == 0

    # Concurrent / overlapping imports serialize under _export_lock without duplicate rows
    results: list[dict] = []
    errors: list[Exception] = []
    barrier = threading.Barrier(2)

    ws2 = Workspace(tmp_path / "ws2")
    ws2.create_project(id="proj-par", title="Parallel", archetype="review")
    hooks2 = WorkspaceSyncHooks(
        ws2,
        LocalIntegrationsManager(cfg_path),
        obsidian_validation=ObsidianValidation(vault),
    )

    def worker():
        try:
            barrier.wait(timeout=5)
            results.append(hooks2.import_obsidian_notes("proj-par", {"dry_run": False}))
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert not errors
    assert sum(r["imported_count"] for r in results) == 2
    assert len([r for r in ws2.records("proj-par") if r["kind"] == "source"]) == 2


def test_v133_bundle_multi_slash_doi_root_tie_and_download_containment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    import research_hub.notebooklm.bundle as bundle_mod

    root = tmp_path / "vault"
    pdfs = root / "pdfs"
    raw = root / "raw" / "alpha"
    (pdfs / "subcollection").mkdir(parents=True)
    (pdfs / "nested").mkdir(parents=True)
    raw.mkdir(parents=True)
    (root / ".research_hub").mkdir()

    # Multi-slash DOI 10.1234/series/chapter matches subcollection/10.1234_series_chapter.pdf
    multi_slash_pdf = pdfs / "subcollection" / "10.1234_series_chapter.pdf"
    multi_slash_pdf.write_bytes(b"%PDF-multi-slash")
    assert _match_pdf_for_note(pdfs, raw / "other_name.md", "10.1234/series/chapter") == multi_slash_pdf

    # Root canonical filename + nested canonical filename must tie-break to None
    (pdfs / "10.1234_tie.pdf").write_bytes(b"%PDF-root")
    (pdfs / "nested" / "10.1234_tie.pdf").write_bytes(b"%PDF-nested")
    assert _match_pdf_for_note(pdfs, raw / "tie_note.md", "10.1234/tie") is None

    # download_pdfs=True rejects an out-of-root path returned by fetch_paper_pdf
    outside_pdf = tmp_path / "outside_secret.pdf"
    outside_pdf.write_bytes(b"%PDF-secret")
    (raw / "dl_escape.md").write_text(
        '---\ntitle: "Escape"\ndoi: "10.1234/dl-escape"\nurl: "https://example.org/esc"\ntopic_cluster: alpha\n---\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "research_hub.notebooklm.pdf_fetcher.fetch_paper_pdf",
        lambda *a, **k: SimpleNamespace(ok=True, path=outside_pdf, source="local-doi", error=""),
    )
    cfg = SimpleNamespace(root=root, raw=root / "raw", research_hub_dir=root / ".research_hub")
    cluster = Cluster(slug="alpha", name="Alpha", obsidian_subfolder="alpha")
    report = bundle_mod.bundle_cluster(cluster, cfg, download_pdfs=True)
    assert report.pdf_count == 0
    assert report.entries[0].action == "url"


def test_v133_snapshot_empty_frontmatter_scope_tie_and_import_edge_cases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from research_hub.workspace import library_snapshot as ls_mod
    from research_hub.workspace.core import resolve_reading_scope
    from research_hub.workspace.integrations import LocalIntegrationsManager
    from research_hub.workspace.obsidian_validation import ObsidianValidation
    from research_hub.workspace.sync_hooks import WorkspaceSyncHooks

    # 1. Empty frontmatter block must not scan body prose
    empty_note = tmp_path / "empty_body_trap.md"
    empty_note.write_text("---\n---\ntitle: Heading in the body\nyear: 1776\n---\nAfter\n", encoding="utf-8")
    loaded, _, _ = ls_mod._extract_frontmatter_incremental(empty_note)
    assert loaded == {}

    # 2. Swapping fulltext / full-text between reading_scope and reading_level never flips classification
    assert resolve_reading_scope({"reading_scope": "fulltext", "reading_level": "full-text"}) == "full-text"
    assert resolve_reading_scope({"reading_scope": "full-text", "reading_level": "fulltext"}) == "full-text"
    assert resolve_reading_scope({"reading_scope": "excerpt", "reading_level": "selected-sections"}) == "selected-sections"
    assert resolve_reading_scope({"reading_scope": "selected-sections", "reading_level": "excerpt"}) == "selected-sections"

    ws_scope = Workspace(tmp_path / "ws_scope")
    ws_scope.create_project(id="proj-alias", title="Alias Symmetry", archetype="review")
    ws_scope.add_record(
        "proj-alias",
        kind="source",
        data={
            "title": "Alias Paper",
            "locator": "https://example.org/alias",
            "reading_scope": "fulltext",
            "reading_level": "full-text",
        },
    )
    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text("{}", encoding="utf-8")
    hooks_scope = WorkspaceSyncHooks(ws_scope, LocalIntegrationsManager(cfg_path))
    pack_res = hooks_scope.bundle_notebooklm("proj-alias", {})
    assert pack_res["full_text_count"] == 1
    assert pack_res["abstract_or_metadata_count"] == 0

    # 3. Vault A and Vault B with identical relative raw/alpha/n1.md path but different DOI/title both import
    vault_a = tmp_path / "vault_a"
    vault_b = tmp_path / "vault_b"
    for v, title, doi in (
        (vault_a, "Vault A Paper", "10.1000/vault-a"),
        (vault_b, "Vault B Paper", "10.1000/vault-b"),
    ):
        (v / ".obsidian").mkdir(parents=True)
        (v / ".research_hub").mkdir()
        (v / ".research_hub" / "clusters.yaml").write_text(
            "schema_version: '1.0'\nclusters:\n  alpha:\n    name: Alpha\n    status: active\n    obsidian_subfolder: alpha\n",
            encoding="utf-8",
        )
        (v / "raw" / "alpha").mkdir(parents=True)
        (v / "raw" / "alpha" / "n1.md").write_text(
            f'---\ntitle: "{title}"\ndoi: "{doi}"\nyear: 2024\n---\nBody\n',
            encoding="utf-8",
        )
    (vault_a / "raw" / "alpha" / "n2.md").write_text(
        '---\ntitle: "Vault A Second"\ndoi: "10.1000/vault-a2"\nyear: 2024\n---\nBody\n',
        encoding="utf-8",
    )

    ws_multi = Workspace(tmp_path / "ws_multi")
    ws_multi.create_project(id="proj-mv", title="Multi Vault", archetype="review")
    hooks_a = WorkspaceSyncHooks(
        ws_multi, LocalIntegrationsManager(cfg_path), obsidian_validation=ObsidianValidation(vault_a)
    )
    hooks_b = WorkspaceSyncHooks(
        ws_multi, LocalIntegrationsManager(cfg_path), obsidian_validation=ObsidianValidation(vault_b)
    )
    res_a = hooks_a.import_obsidian_notes("proj-mv", {"dry_run": False})
    assert res_a["imported_count"] == 2
    res_b = hooks_b.import_obsidian_notes("proj-mv", {"dry_run": False})
    assert res_b["imported_count"] == 1
    assert res_b["skipped_existing"] == 0
    sources_mv = [r for r in ws_multi.records("proj-mv") if r["kind"] == "source"]
    assert len({r["data"]["origin_vault_id"] for r in sources_mv}) == 2

    # 4. Nonexistent collection_id fails with invalid_source
    with pytest.raises(WorkspaceError) as exc_col:
        hooks_a.import_obsidian_notes("proj-mv", {"collection_id": "nonexistent", "dry_run": True})
    assert exc_col.value.code == "invalid_source"

    # 5. Missing note_id on a truncated snapshot raises snapshot_truncated
    monkeypatch.setattr(
        ls_mod,
        "read_vault_snapshot",
        lambda *a, **k: {
            "schema_version": 1,
            "read_only": True,
            "body_read": False,
            "captured_at": "2026-11-27T00:00:00Z",
            "vault_label": "v",
            "collections": [{"id": "alpha", "name": "Alpha", "note_count": 0}],
            "notes": [],
            "truncated": True,
        },
    )
    with pytest.raises(WorkspaceError) as exc_trunc:
        hooks_a.import_obsidian_notes(
            "proj-mv", {"note_ids": ["obsidian:000000000000000000000000"], "dry_run": True}
        )
    assert exc_trunc.value.code == "snapshot_truncated"
    monkeypatch.undo()

    # 6. Explicit note_ids bypasses MAX_VAULT_NOTES early stop in read_vault_snapshot
    monkeypatch.setattr(ls_mod, "MAX_VAULT_NOTES", 1)
    full_a = ls_mod.read_vault_snapshot(vault_a)
    assert full_a.get("truncated") is True and len(full_a["notes"]) == 1
    n2_id = f"obsidian:{__import__('hashlib').sha256(b'raw/alpha/n2.md').hexdigest()[:24]}"
    explicit_snap = ls_mod.read_vault_snapshot(vault_a, collection_id="alpha", note_ids=[n2_id])
    assert [n["id"] for n in explicit_snap["notes"]] == [n2_id]
