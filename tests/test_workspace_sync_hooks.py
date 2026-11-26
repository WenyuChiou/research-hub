"""Backend security, confinement, and sync-hook tests for WorkspaceSyncHooks."""

from __future__ import annotations

import json
from pathlib import Path
import re
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
import yaml

from research_hub.workspace.core import Workspace
from research_hub.workspace.server import WorkspaceServer
import research_hub.workspace.sync_hooks as sync_hooks_mod


@pytest.fixture(autouse=True)
def _isolate_home_and_env(tmp_path: Path, monkeypatch):
    fake_home = tmp_path / "isolated_home"
    fake_home.mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))
    for var in (
        "ZOTERO_API_KEY",
        "ZOTERO_LIBRARY_ID",
        "ZOTERO_LIBRARY_TYPE",
        "SEMANTIC_SCHOLAR_API_KEY",
        "UNPAYWALL_EMAIL",
        "RESEARCH_HUB_CONFIG",
    ):
        monkeypatch.delenv(var, raising=False)


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


def _seed_workspace(ws_root: Path) -> tuple[Workspace, dict[str, str]]:
    ws = Workspace(ws_root)
    ws.create_project(id="proj-alpha", title="Agentic Hydrology Review", archetype="review")
    ws.create_project(id="proj-beta", title="Other Project", archetype="empirical")

    s1 = ws.add_record(
        "proj-alpha",
        kind="source",
        data={
            "title": "Full-Text Hydrological Agent Simulation",
            "locator": "https://doi.org/10.1029/2025WR000001",
            "doi": "https://doi.org/10.1029/2025WR000001",
            "authors": ["Lin, Mei-Hua", "Chen, Wei"],
            "year": "2025",
            "venue": "Water Resources Research",
            "category": "simulation",
            "reading_scope": "full-text",
            "tags": ["hydrology", "multi-agent"],
            "summary": "Full-text basin flood adaptation simulation study.",
        },
    )
    s2 = ws.add_record(
        "proj-alpha",
        kind="source",
        data={
            "title": "Abstract-Only LLM Benchmark Survey",
            "locator": "https://arxiv.org/abs/2409.12345",
            "doi": "10.48550/arXiv.2409.12345",
            "authors": "Patel, Aria",
            "year": "2024",
            "reading_scope": "abstract",
            "tags": ["benchmark"],
            "summary": "Survey of evaluation harnesses from abstract metadata.",
        },
    )
    s3_archived = ws.add_record(
        "proj-alpha",
        kind="source",
        data={
            "title": "Archived Legacy Paper",
            "locator": "https://example.org/legacy",
            "year": "2019",
        },
    )
    ws.add_record(
        "proj-alpha",
        kind="source_curation",
        data={
            "source_id": s3_archived["id"],
            "archived": True,
        },
    )
    ws.add_record(
        "proj-alpha",
        kind="screening",
        data={
            "source_id": s1["id"],
            "decision": "include",
            "rationale": "Core full-text watershed simulation benchmark.",
        },
    )
    other_src = ws.add_record(
        "proj-beta",
        kind="source",
        data={
            "title": "Cross-Project Secret Paper",
            "locator": "https://example.org/other",
        },
    )
    return ws, {
        "s1": s1["id"],
        "s2": s2["id"],
        "s3_archived": s3_archived["id"],
        "other_project_source": other_src["id"],
    }


def test_sync_hook_routes_require_enabled_integrations_and_csrf(tmp_path: Path):
    ws, _ = _seed_workspace(tmp_path / "ws")
    server = WorkspaceServer(ws.root, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        csrf = _fetch_csrf(base)

        for route, payload in (
            ("/api/v1/projects/proj-alpha/integrations/notebooklm/bundle", {}),
            ("/api/v1/projects/proj-alpha/integrations/zotero/sync", {"dry_run": True}),
            ("/api/v1/projects/proj-alpha/integrations/obsidian/pack", {}),
        ):
            # Missing CSRF -> 403 forbidden
            code, body = _post_json(f"{base}{route}", payload, origin=base)
            assert code == 403 and body["code"] == "forbidden"

            # Untrusted Origin -> 403 forbidden
            code, body = _post_json(
                f"{base}{route}",
                payload,
                csrf=csrf,
                origin="https://evil.example",
            )
            assert code == 403 and body["code"] == "forbidden"

            # Valid CSRF when integrations disabled -> 403 integrations_unavailable
            code, body = _post_json(f"{base}{route}", payload, csrf=csrf, origin=base)
            assert code == 403 and body["code"] == "integrations_unavailable"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_cross_project_and_unknown_selected_source_ids_rejected_with_400(tmp_path: Path):
    ws, ids = _seed_workspace(tmp_path / "ws")
    cfg_path = tmp_path / "cfg" / "config.json"
    cfg_path.parent.mkdir(parents=True)
    cfg_path.write_text("{}", encoding="utf-8")

    server = WorkspaceServer(ws.root, port=0, integrations_config=cfg_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        csrf = _fetch_csrf(base)

        for route in (
            "/api/v1/projects/proj-alpha/integrations/notebooklm/bundle",
            "/api/v1/projects/proj-alpha/integrations/zotero/sync",
            "/api/v1/projects/proj-alpha/integrations/obsidian/pack",
        ):
            code, body = _post_json(
                f"{base}{route}",
                {"selected_source_ids": [ids["s1"], ids["other_project_source"]]},
                csrf=csrf,
                origin=base,
            )
            assert code == 400
            assert body["ok"] is False
            assert body["code"] == "invalid_source"

            code_unknown, body_unknown = _post_json(
                f"{base}{route}",
                {"selected_source_ids": ["nonexistent-id"]},
                csrf=csrf,
                origin=base,
            )
            assert code_unknown == 400
            assert body_unknown["ok"] is False
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_notebooklm_bundle_and_obsidian_pack_stay_inside_workspace_never_touching_vault(
    tmp_path: Path,
    monkeypatch,
):
    vault = tmp_path / "readonly-vault"
    (vault / ".obsidian").mkdir(parents=True)
    (vault / "raw" / "proj-alpha").mkdir(parents=True)
    (vault / ".research_hub").mkdir()
    (vault / ".research_hub" / "clusters.yaml").write_text(
        "schema_version: '1.0'\nclusters:\n  proj-alpha:\n    name: Alpha\n    status: active\n    obsidian_subfolder: proj-alpha\n",
        encoding="utf-8",
    )
    (vault / "raw" / "proj-alpha" / "existing.md").write_text("UNTOUCHED", encoding="utf-8")
    vault_snapshot_before = {
        str(p.relative_to(vault)): (p.stat().st_mtime_ns, p.stat().st_size if p.is_file() else -1)
        for p in vault.rglob("*")
    }

    ws, ids = _seed_workspace(tmp_path / "ws")
    cfg_path = tmp_path / "cfg" / "config.json"
    cfg_path.parent.mkdir(parents=True)
    cfg_path.write_text(json.dumps({"knowledge_base": {"root": str(vault)}}), encoding="utf-8")

    import research_hub.notebooklm.auth as nlm_auth

    monkeypatch.setattr(
        nlm_auth,
        "ensure_session_health",
        lambda sf, auto_refresh=True: {"ok": False, "refreshed": False},
    )

    server = WorkspaceServer(ws.root, port=0, obsidian_vault=vault, integrations_config=cfg_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        csrf = _fetch_csrf(base)

        # 1. NotebookLM bundle (archived s3 skipped automatically)
        code, nlm = _post_json(
            f"{base}/api/v1/projects/proj-alpha/integrations/notebooklm/bundle",
            {},
            csrf=csrf,
            origin=base,
        )
        assert code == 200 and nlm["ok"] is True
        assert nlm["export_dir"] == ".research/exports/notebooklm-proj-alpha"
        assert nlm["pack_file"] == ".research/exports/notebooklm-proj-alpha/00-notebooklm-source-pack.md"
        assert nlm["source_count"] == 2
        assert nlm["full_text_count"] == 1
        assert nlm["abstract_or_metadata_count"] == 1
        assert nlm["nlm_status"] == "missing"
        assert nlm["notebook_url"] == "https://notebooklm.google.com/"
        assert str(ws.root) not in json.dumps(nlm)
        assert str(vault) not in json.dumps(nlm)

        nlm_dir = ws.root / ".research" / "exports" / "notebooklm-proj-alpha"
        manifest = json.loads((nlm_dir / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["project_title"] == "Agentic Hydrology Review"
        assert manifest["source_count"] == 2
        assert manifest["full_text_count"] == 1
        assert manifest["abstract_only_count"] == 1
        pack_md = (nlm_dir / "00-notebooklm-source-pack.md").read_text(encoding="utf-8")
        assert "Full-Text Declared Sources (1)" in pack_md
        assert "Abstract-Only & Metadata Sources (1)" in pack_md
        assert "Archived Legacy Paper" not in pack_md
        individual_files = sorted((nlm_dir / "sources").glob("*.md"))
        assert len(individual_files) == 2

        # 2. Obsidian pack (writes strictly to workspace .research/exports/, zero writes to vault)
        code_obs, obs = _post_json(
            f"{base}/api/v1/projects/proj-alpha/integrations/obsidian/pack",
            {},
            csrf=csrf,
            origin=base,
        )
        assert code_obs == 200 and obs["ok"] is True
        assert obs["export_dir"] == ".research/exports/obsidian-proj-alpha"
        assert obs["base_file"] == ".research/exports/obsidian-proj-alpha/proj-alpha.base"
        assert obs["note_count"] == 2
        assert obs["obsidian_vault_name"] == "readonly-vault"
        assert str(ws.root) not in json.dumps(obs)
        assert str(vault) not in json.dumps(obs)

        obs_dir = ws.root / ".research" / "exports" / "obsidian-proj-alpha"
        base_parsed = yaml.safe_load((obs_dir / "proj-alpha.base").read_text(encoding="utf-8"))
        assert len(base_parsed["views"]) == 3
        notes = sorted(obs_dir.glob("*.md"))
        assert len(notes) == 2
        first_note = notes[0].read_text(encoding="utf-8")
        assert 'topic_cluster: "proj-alpha"' in first_note
        assert 'reading_scope: "full-text"' in first_note
        assert 'screening: "include"' in first_note
        assert 'doi: "10.1029/2025WR000001"' in first_note

        # Re-packing with 1 selected source removes stale 2nd note
        code_sub, obs_sub = _post_json(
            f"{base}/api/v1/projects/proj-alpha/integrations/obsidian/pack",
            {"selected_source_ids": [ids["s1"]]},
            csrf=csrf,
            origin=base,
        )
        assert code_sub == 200 and obs_sub["note_count"] == 1
        assert len(list(obs_dir.glob("*.md"))) == 1

        # Verify --obsidian-vault is 100% untouched!
        vault_snapshot_after = {
            str(p.relative_to(vault)): (p.stat().st_mtime_ns, p.stat().st_size if p.is_file() else -1)
            for p in vault.rglob("*")
        }
        assert vault_snapshot_before == vault_snapshot_after
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_zotero_sync_missing_credentials_and_dry_run_to_live_write(tmp_path: Path, monkeypatch):
    ws, ids = _seed_workspace(tmp_path / "ws")
    cfg_path = tmp_path / "cfg" / "config.json"
    cfg_path.parent.mkdir(parents=True)
    cfg_path.write_text("{}", encoding="utf-8")

    server = WorkspaceServer(ws.root, port=0, integrations_config=cfg_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        csrf = _fetch_csrf(base)

        # 1. Missing credentials returns clean guidance status without failing
        code_missing, missing_res = _post_json(
            f"{base}/api/v1/projects/proj-alpha/integrations/zotero/sync",
            {},
            csrf=csrf,
            origin=base,
        )
        assert code_missing == 200
        assert missing_res["ok"] is True
        assert missing_res["status"] == "missing_credentials"
        assert missing_res["dry_run"] is True
        assert missing_res["candidate_count"] == 2
        assert missing_res["would_create"] == 0

        # 2. Save Zotero credentials and mock Zotero client
        raw_secret = "zot-sync-secret-key-777"
        save_code, _ = _post_json(
            f"{base}/api/v1/integrations/credentials",
            {
                "zotero_library_id": "88888",
                "zotero_library_type": "user",
                "zotero_api_key": raw_secret,
            },
            csrf=csrf,
            origin=base,
        )
        assert save_code == 200

        created_batches: list[list[dict]] = []

        class _FakeZoteroClient:
            def __init__(self, lib_id: str, lib_type: str, api_key: str):
                assert lib_id == "88888"
                assert lib_type == "user"
                assert api_key == raw_secret

            def items(self, q: str = "", limit: int = 5):
                # Simulate s2 already existing in Zotero by DOI
                if "2409.12345" in q or "Abstract-Only LLM Benchmark" in q:
                    return [
                        {
                            "key": "EXISTING9",
                            "data": {
                                "title": "Abstract-Only LLM Benchmark Survey",
                                "DOI": "10.48550/arXiv.2409.12345",
                            },
                        }
                    ]
                return []

            def create_items(self, items_list: list[dict]):
                created_batches.append(items_list)
                return {
                    "successful": {
                        str(idx): {"key": f"ZOTKEY{idx + 1}"}
                        for idx in range(len(items_list))
                    },
                    "failed": {},
                }

        monkeypatch.setattr(sync_hooks_mod, "_get_zotero_client", _FakeZoteroClient)

        # 3. Dry-run=True (default): zero writes, detects 1 new + 1 duplicate
        code_dry, dry_res = _post_json(
            f"{base}/api/v1/projects/proj-alpha/integrations/zotero/sync",
            {"dry_run": True},
            csrf=csrf,
            origin=base,
        )
        assert code_dry == 200
        assert dry_res["ok"] is True
        assert dry_res["status"] == "ready"
        assert dry_res["dry_run"] is True
        assert dry_res["candidate_count"] == 2
        assert dry_res["would_create"] == 1
        assert dry_res["duplicates"] == 1
        assert created_batches == []
        actions_by_id = {entry["id"]: entry["action"] for entry in dry_res["items"]}
        assert actions_by_id == {ids["s1"]: "create", ids["s2"]: "skip_duplicate"}
        assert raw_secret not in json.dumps(dry_res)

        # 4. Dry-run=False: creates only non-duplicate journalArticle with cluster & source tags
        code_sync, sync_res = _post_json(
            f"{base}/api/v1/projects/proj-alpha/integrations/zotero/sync",
            {"dry_run": False},
            csrf=csrf,
            origin=base,
        )
        assert code_sync == 200
        assert sync_res["ok"] is True
        assert sync_res["status"] == "synced"
        assert sync_res["dry_run"] is False
        assert sync_res["created_count"] == 1
        assert sync_res["skipped_duplicates"] == 1
        assert sync_res["created_keys"] == ["ZOTKEY1"]
        assert raw_secret not in json.dumps(sync_res)

        assert len(created_batches) == 1 and len(created_batches[0]) == 1
        created_item = created_batches[0][0]
        assert created_item["itemType"] == "journalArticle"
        assert created_item["DOI"] == "10.1029/2025WR000001"
        tag_names = [t["tag"] for t in created_item["tags"]]
        assert "research-hub" in tag_names
        assert "cluster/proj-alpha" in tag_names
        assert "hydrology" in tag_names
        assert "multi-agent" in tag_names
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
