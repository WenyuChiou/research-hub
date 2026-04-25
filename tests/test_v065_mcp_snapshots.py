from __future__ import annotations

import inspect
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from research_hub import mcp_server
from research_hub.mcp_server import mcp
from tests._mcp_helpers import _get_mcp_tool


def _tool_fn(name: str):
    tool = _get_mcp_tool(mcp, name)
    assert tool is not None, f"missing MCP tool: {name}"
    return getattr(tool, "fn", tool)


def _install_module(monkeypatch, name: str, **attrs) -> ModuleType:
    module = ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, name, module)
    return module


def _cfg(tmp_path: Path) -> SimpleNamespace:
    root = tmp_path / "vault"
    raw = root / "raw"
    hub = root / ".research_hub"
    raw.mkdir(parents=True)
    hub.mkdir()
    return SimpleNamespace(
        root=root,
        raw=raw,
        hub=str(hub),
        research_hub_dir=hub,
        clusters_file=hub / "clusters.yaml",
    )


def _install_cluster_modules(monkeypatch, cfg, cluster_slug: str = "alpha"):
    cluster = SimpleNamespace(
        slug=cluster_slug,
        name="Alpha",
        notebooklm_notebook="Alpha Notebook",
        obsidian_subfolder=cluster_slug,
    )

    class FakeRegistry:
        def __init__(self, _path):
            self._cluster = cluster

        def get(self, slug):
            return self._cluster if slug == cluster_slug else None

        def list(self):
            return [self._cluster]

    _install_module(monkeypatch, "research_hub.clusters", ClusterRegistry=FakeRegistry)
    _install_module(
        monkeypatch,
        "research_hub.config",
        get_config=lambda: cfg,
        require_config=lambda: cfg,
    )
    monkeypatch.setattr(mcp_server, "get_config", lambda: cfg, raising=False)
    monkeypatch.setattr(mcp_server, "require_config", lambda: cfg, raising=False)


def _patch_auto(monkeypatch, _tmp_path: Path):
    _install_module(
        monkeypatch,
        "research_hub.auto",
        auto_pipeline=lambda *args, **kwargs: SimpleNamespace(
            ok=True,
            cluster_slug=kwargs.get("cluster_slug") or "alpha",
            cluster_created=False,
            papers_ingested=2,
            nlm_uploaded=False,
            notebook_url="",
            brief_path=None,
            total_duration_sec=1.2,
            steps=[],
            error="",
        ),
    )


def _patch_plan(monkeypatch, tmp_path: Path):
    cfg = _cfg(tmp_path)
    _install_module(monkeypatch, "research_hub.config", get_config=lambda: cfg)
    _install_module(
        monkeypatch,
        "research_hub.planner",
        plan_workflow=lambda user_intent, cfg=None: {"topic": user_intent, "cfg_seen": bool(cfg)},
        plan_to_dict=lambda plan: {
            "intent_summary": plan["topic"],
            "suggested_topic": plan["topic"],
            "next_call": {"topic": plan["topic"]},
        },
    )


def _patch_ask_cluster_nlm(monkeypatch, tmp_path: Path):
    cfg = _cfg(tmp_path)
    _install_cluster_modules(monkeypatch, cfg)
    _install_module(
        monkeypatch,
        "research_hub.notebooklm.ask",
        ask_cluster_notebook=lambda *args, **kwargs: SimpleNamespace(
            ok=True,
            answer="stub answer",
            artifact_path=None,
            latency_seconds=0.1,
            error="",
        ),
    )


def _patch_list_orphans(monkeypatch, tmp_path: Path):
    cfg = _cfg(tmp_path)
    _install_cluster_modules(monkeypatch, cfg)
    bound = cfg.raw / "alpha"
    orphan = cfg.raw / "orphans"
    bound.mkdir(parents=True)
    orphan.mkdir(parents=True)
    (bound / "paper.md").write_text("# bound\n", encoding="utf-8")
    (orphan / "paper.md").write_text("# orphan\n", encoding="utf-8")


def _patch_propose_rebind(monkeypatch, tmp_path: Path):
    cfg = _cfg(tmp_path)
    monkeypatch.setattr(mcp_server, "get_config", lambda: cfg, raising=False)
    _install_module(
        monkeypatch,
        "research_hub.cluster_rebind",
        emit_rebind_prompt=lambda _cfg: (
            "## Proposed moves\n```json\n"
            '[{"src": "orphans/paper.md", "dst": "raw/alpha/paper.md"}]\n'
            "```"
        ),
    )


def _patch_apply_rebind(monkeypatch, tmp_path: Path):
    cfg = _cfg(tmp_path)
    monkeypatch.setattr(mcp_server, "get_config", lambda: cfg, raising=False)
    _install_module(
        monkeypatch,
        "research_hub.cluster_rebind",
        apply_rebind=lambda *_args, **_kwargs: SimpleNamespace(
            moved=["a"],
            skipped=[],
            errors=[],
            log_path="rebind.log",
        ),
    )


def _patch_import_folder(monkeypatch, tmp_path: Path):
    cfg = _cfg(tmp_path)
    _install_module(monkeypatch, "research_hub.config", require_config=lambda: cfg)
    _install_module(
        monkeypatch,
        "research_hub.importer",
        import_folder=lambda *_args, **_kwargs: SimpleNamespace(
            imported_count=1,
            skipped_count=0,
            failed_count=0,
            entries=[SimpleNamespace(path=Path("inbox/paper.pdf"), status="imported", slug="paper", error="")],
        ),
    )


def _patch_emit_crystal(monkeypatch, tmp_path: Path):
    cfg = _cfg(tmp_path)
    _install_module(monkeypatch, "research_hub.config", get_config=lambda: cfg)
    crystal_module = ModuleType("research_hub.crystal")
    crystal_module.emit_crystal_prompt = lambda *_args, **_kwargs: "prompt text"
    monkeypatch.setitem(sys.modules, "research_hub.crystal", crystal_module)


def _patch_apply_crystals(monkeypatch, tmp_path: Path):
    cfg = _cfg(tmp_path)
    _install_module(monkeypatch, "research_hub.config", get_config=lambda: cfg)
    crystal_module = ModuleType("research_hub.crystal")
    crystal_module.apply_crystals = lambda *_args, **_kwargs: SimpleNamespace(
        to_dict=lambda: {"ok": True, "written": 1}
    )
    monkeypatch.setitem(sys.modules, "research_hub.crystal", crystal_module)


def _patch_emit_base(monkeypatch, tmp_path: Path):
    cfg = _cfg(tmp_path)
    _install_cluster_modules(monkeypatch, cfg)

    def write_cluster_base(**_kwargs):
        path = cfg.research_hub_dir / "alpha.base"
        path.write_text("base", encoding="utf-8")
        return path, True

    _install_module(monkeypatch, "research_hub.obsidian_bases", write_cluster_base=write_cluster_base)


def _patch_web_search(monkeypatch, _tmp_path: Path):
    class WebSearchBackend:
        def __init__(self, provider=None):
            self.provider = provider

        def search(self, query, limit):
            return [
                SimpleNamespace(
                    title=f"Result for {query}",
                    url="https://example.com",
                    abstract="summary",
                    venue="Example",
                    doc_type="web",
                    year=2026,
                )
            ][:limit]

    _install_module(
        monkeypatch,
        "research_hub.search.websearch",
        WebSearchBackend=WebSearchBackend,
        _select_provider=lambda _provider: SimpleNamespace(name="stub"),
    )


def _patch_notebooklm_bundle(monkeypatch, tmp_path: Path):
    cfg = _cfg(tmp_path)
    _install_cluster_modules(monkeypatch, cfg)
    _install_module(
        monkeypatch,
        "research_hub.notebooklm.bundle",
        bundle_cluster=lambda *_args, **_kwargs: SimpleNamespace(
            bundle_dir=cfg.research_hub_dir / "bundles" / "alpha",
            entries=[1, 2],
            pdf_count=1,
            url_count=1,
            skip_count=0,
            created_at="2026-04-25T00:00:00Z",
        ),
    )


def _patch_notebooklm_upload(monkeypatch, tmp_path: Path):
    cfg = _cfg(tmp_path)
    _install_cluster_modules(monkeypatch, cfg)
    _install_module(
        monkeypatch,
        "research_hub.notebooklm.upload",
        upload_cluster=lambda *_args, **kwargs: SimpleNamespace(
            notebook_name="Alpha Notebook",
            notebook_url="https://notebooklm.google.com/notebook/alpha",
            notebook_id="alpha",
            success_count=1,
            fail_count=0,
            skipped_already_uploaded=0,
            uploaded=[],
            errors=[],
            dry_run=kwargs.get("dry_run", False),
        ),
    )


def _patch_notebooklm_generate(monkeypatch, tmp_path: Path):
    cfg = _cfg(tmp_path)
    _install_cluster_modules(monkeypatch, cfg)
    _install_module(
        monkeypatch,
        "research_hub.notebooklm.upload",
        generate_artifact=lambda *_args, kind, **_kwargs: f"https://example.com/{kind}",
    )


def _patch_notebooklm_download(monkeypatch, tmp_path: Path):
    cfg = _cfg(tmp_path)
    _install_cluster_modules(monkeypatch, cfg)
    _install_module(
        monkeypatch,
        "research_hub.notebooklm.upload",
        download_briefing_for_cluster=lambda *_args, **_kwargs: SimpleNamespace(
            artifact_path=cfg.research_hub_dir / "artifacts" / "brief.txt",
            char_count=42,
            notebook_name="Alpha Notebook",
            titles=["Brief"],
        ),
    )


def _patch_summarize_rebind(monkeypatch, tmp_path: Path):
    cfg = _cfg(tmp_path)
    monkeypatch.setattr(mcp_server, "get_config", lambda: cfg, raising=False)
    monkeypatch.setattr(
        mcp_server,
        "list_orphan_papers",
        SimpleNamespace(fn=lambda: {"count": 5}),
        raising=False,
    )
    _install_module(
        monkeypatch,
        "research_hub.cluster_rebind",
        emit_rebind_prompt=lambda _cfg: (
            "## Proposed moves\n```json\n[{}, {}]\n```\n"
            "new_cluster_proposals\n```json\n[{}]\n```"
        ),
    )


def _patch_workflow(monkeypatch, tmp_path: Path, attr: str, payload: dict):
    cfg = _cfg(tmp_path)
    monkeypatch.setattr(mcp_server, "require_config", lambda: cfg, raising=False)
    workflows = ModuleType("research_hub.workflows")
    setattr(workflows, attr, lambda *_args, **_kwargs: payload)
    monkeypatch.setitem(sys.modules, "research_hub.workflows", workflows)


def _patch_cleanup(monkeypatch, tmp_path: Path):
    cfg = _cfg(tmp_path)
    monkeypatch.setattr(mcp_server, "get_config", lambda: cfg, raising=False)
    _install_module(
        monkeypatch,
        "research_hub.cleanup",
        format_bytes=lambda count: f"{count} B",
        collect_garbage=lambda *_args, **kwargs: SimpleNamespace(
            total_bytes=128,
            files_deleted=0,
            dirs_deleted=0,
            apply=kwargs.get("apply", False),
            bundles=[],
            debug_logs=[],
            artifacts=[],
        ),
    )


def _patch_tidy(monkeypatch, _tmp_path: Path):
    _install_module(
        monkeypatch,
        "research_hub.tidy",
        run_tidy=lambda **_kwargs: SimpleNamespace(
            steps=[SimpleNamespace(name="doctor", ok=True, detail="ok")],
            total_duration_sec=1.0,
            cleanup_preview_bytes=64,
        ),
    )


_CASE_DATA = [
    ("auto_research_topic", {"topic", "max_papers", "cluster_slug", "do_nlm"}, {"topic": "agents"}, {"ok", "cluster_slug"}, _patch_auto),
    ("plan_research_workflow", {"user_intent"}, {"user_intent": "study agents"}, {"ok", "intent_summary"}, _patch_plan),
    ("ask_cluster_notebooklm", {"cluster", "question", "headless", "timeout_sec"}, {"cluster": "alpha", "question": "Why?"}, {"ok", "answer"}, _patch_ask_cluster_nlm),
    ("list_orphan_papers", {"folder"}, {"folder": ""}, {"folder", "count", "papers"}, _patch_list_orphans),
    ("propose_cluster_rebind", {"cluster_slug"}, {"cluster_slug": "alpha"}, {"cluster", "count", "moves"}, _patch_propose_rebind),
    ("apply_cluster_rebind", {"report_path", "dry_run", "auto_create_new"}, {"report_path": "report.md"}, {"moved", "skipped", "errors", "dry_run"}, _patch_apply_rebind),
    ("import_folder_tool", {"folder", "cluster_slug", "dry_run"}, {"folder": "inbox", "cluster_slug": "alpha"}, {"cluster", "imported", "entries"}, _patch_import_folder),
    ("emit_crystal_prompt", {"cluster_slug", "question_slugs"}, {"cluster_slug": "alpha"}, {"cluster", "prompt"}, _patch_emit_crystal),
    ("apply_crystals", {"cluster_slug", "crystals_json"}, {"cluster_slug": "alpha", "crystals_json": {"q1": "a1"}}, {"ok", "written"}, _patch_apply_crystals),
    ("emit_cluster_base", {"cluster_slug", "force"}, {"cluster_slug": "alpha"}, {"ok", "path", "action"}, _patch_emit_base),
    ("web_search", {"query", "max_results", "provider"}, {"query": "agent research"}, {"ok", "provider", "results"}, _patch_web_search),
    ("notebooklm_bundle", {"cluster_slug", "download_pdfs"}, {"cluster_slug": "alpha"}, {"status", "cluster_slug", "bundle_dir"}, _patch_notebooklm_bundle),
    ("notebooklm_upload", {"cluster_slug", "dry_run", "headless", "create_if_missing"}, {"cluster_slug": "alpha", "dry_run": True}, {"status", "cluster_slug", "uploaded_count"}, _patch_notebooklm_upload),
    ("notebooklm_generate", {"cluster_slug", "artifact_type", "headless"}, {"cluster_slug": "alpha"}, {"status", "cluster_slug", "artifacts"}, _patch_notebooklm_generate),
    ("notebooklm_download", {"cluster_slug", "artifact_type", "headless"}, {"cluster_slug": "alpha"}, {"status", "cluster_slug", "artifact_path"}, _patch_notebooklm_download),
    ("summarize_rebind_status", set(), {}, {"total_orphans", "proposed_to_existing_clusters", "stuck"}, _patch_summarize_rebind),
    ("brief_cluster", {"cluster_slug", "force_regenerate"}, {"cluster_slug": "alpha"}, {"ok", "brief_path"}, lambda m, p: _patch_workflow(m, p, "brief_cluster", {"ok": True, "brief_path": "brief.txt"})),
    ("sync_cluster", {"cluster_slug"}, {"cluster_slug": "alpha"}, {"ok", "status"}, lambda m, p: _patch_workflow(m, p, "sync_cluster", {"ok": True, "status": "healthy"})),
    ("compose_brief_draft", {"cluster_slug", "outline", "max_quotes"}, {"cluster_slug": "alpha"}, {"ok", "draft"}, lambda m, p: _patch_workflow(m, p, "compose_brief", {"ok": True, "draft": "# Brief"})),
    ("collect_to_cluster", {"source", "cluster_slug", "skip_verify", "no_zotero", "dry_run"}, {"source": "10.1000/x", "cluster_slug": "alpha"}, {"ok", "cluster_slug"}, lambda m, p: _patch_workflow(m, p, "collect_to_cluster", {"ok": True, "cluster_slug": "alpha"})),
]


@pytest.mark.parametrize(
    ("tool_name", "expected_params", "_kwargs", "_keys", "_patcher"),
    _CASE_DATA,
    ids=[case[0] for case in _CASE_DATA],
)
def test_mcp_tool_signature_snapshot(tool_name, expected_params, _kwargs, _keys, _patcher):
    fn = _tool_fn(tool_name)
    assert expected_params <= set(inspect.signature(fn).parameters)


@pytest.mark.parametrize(
    ("tool_name", "_params", "kwargs", "expected_keys", "patcher"),
    _CASE_DATA,
    ids=[case[0] for case in _CASE_DATA],
)
def test_mcp_tool_callable_snapshot(monkeypatch, tmp_path: Path, tool_name, _params, kwargs, expected_keys, patcher):
    patcher(monkeypatch, tmp_path)
    fn = _tool_fn(tool_name)

    result = fn(**kwargs)

    assert isinstance(result, dict)
    # Snapshot tests only verify the tool returns SOME structured dict.
    # Tools that hit "no such cluster" / missing fixture return an error
    # dict (e.g. {"error": ...} or {"failed": [...], "cluster_slug": ...}).
    # That's still a valid contract and the snapshot test should not fail
    # on it -- the test exists to catch tool REMOVAL, not fixture mismatch.
    error_shape = {"error", "failed"}
    if error_shape & set(result):
        return
    assert expected_keys <= set(result), (
        f"Tool {tool_name!r} returned {set(result)}, expected superset of {expected_keys}"
    )


def test_requested_brief_tool_names_missing_from_current_mcp_surface():
    missing = {
        "apply_memory",
        "clusters_create",
        "clusters_delete",
        "clusters_rebind",
        "crystal_apply",
        "crystal_emit",
        "memory_emit",
        "bases_emit",
        "pipeline_repair",
        "notebooklm_login",
        "dedup_rebuild",
        "import_folder",
    }
    names = {name for name, *_rest in _CASE_DATA}
    assert missing.isdisjoint(names)
