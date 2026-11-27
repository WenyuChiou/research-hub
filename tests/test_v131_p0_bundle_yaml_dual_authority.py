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
    assert _reading_scope({"reading_scope": "abstract", "reading_level": "full-text"}) == "abstract"
    assert _reading_scope({"reading_scope": "full-text", "reading_level": "abstract-only"}) == "abstract-only"
    assert _reading_scope({"reading_scope": "note-metadata", "reading_level": "selected-sections"}) == "note-metadata"
    assert _reading_scope({"reading_scope": "not-read", "reading_level": "abstract-snippet"}) == "not-read"
    assert _reading_scope({"reading_scope": "selected-sections", "reading_level": "excerpt"}) == "selected-sections"
    assert _reading_scope({"reading_scope": "unknown", "reading_level": "abstract"}) == "abstract"
    assert _reading_scope({"reading_scope": "full-text", "reading_level": "unknown"}) == "full-text"
    assert _reading_scope({}) == "unknown"


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
        assert imported_n2["data"]["batch_id"].startswith("obsidian-import:")
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
    imported = [i for i in res["items"] if i["action"] == "import"]
    assert len(imported) == 1
    assert imported[0]["note_path"] == "raw/beta/n3.md"
