"""Multi-scenario end-to-end pipeline tests across 20 realistic papers.

Exercises the full Research Hub lifecycle offline & deterministically:
1. 20-paper multi-category / multi-label / mixed-scope ingest (dry-run -> apply -> dedup)
2. Obsidian vault -> scripts/library_snapshot.py -> live WorkspaceServer HTTP API + curation
3. 20-paper NotebookLM bundle (8 full-text PDFs + 9 abstract-only + 3 URL/metadata) & dry-run upload
4. Multi-persona Zotero & NotebookLM integration probes (offline, encrypted creds, 200 vs 403, expired)
5. AI Agent Handoff hook lifecycle (create tracked handoff task -> export packet -> import result -> review gate)
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from research_hub import pipeline
from research_hub.clusters import ClusterRegistry
from research_hub.dedup import DedupIndex, build_from_obsidian
from research_hub.notebooklm.auth import default_state_file
from research_hub.notebooklm.bundle import bundle_cluster
from research_hub.notebooklm.upload import upload_cluster
from research_hub.security.secret_box import is_encrypted
from research_hub.workspace.core import Workspace
from research_hub.workspace.server import WorkspaceServer
from tests._pipeline_fixtures import PDF_BLOB, paper_input


COHORT_SPECS: list[dict] = [
    # 8 full-text papers across 4 categories
    {"slug": "park-2023-generative-agents", "title": "Generative Agents: Interactive Simulacra of Human Behavior", "authors": ["Joon Sung Park", "Joseph C. O'Brien", "Michael S. Bernstein"], "year": 2023, "venue": "UIST 2023", "doi": "10.1145/3586183.3606763", "category": "llm-agents", "reading_scope": "full-text", "tags": ["multi-agent", "memory", "simulation"], "screening": "include"},
    {"slug": "yao-2023-react", "title": "ReAct: Synergizing Reasoning and Acting in Language Models", "authors": ["Shunyu Yao", "Jeffrey Zhao", "Dian Yu"], "year": 2023, "venue": "ICLR 2023", "doi": "10.48550/arxiv.2210.03629", "arxiv_id": "2210.03629", "category": "llm-agents", "reading_scope": "full-text", "tags": ["multi-agent", "reasoning", "benchmark"], "screening": "include"},
    {"slug": "horton-2023-homo-silicus", "title": "Large Language Models as Simulated Economic Agents: What Can We Learn from Homo Silicus?", "authors": ["John J. Horton"], "year": 2023, "venue": "NBER Working Paper", "doi": "10.3386/w31122", "category": "human-simulation", "reading_scope": "full-text", "tags": ["economics", "simulation", "policy"], "screening": "include"},
    {"slug": "argyle-2023-out-of-one-many", "title": "Out of One, Many: Using Language Models to Simulate Human Samples", "authors": ["Lisa P. Argyle", "Ethan C. Busby", "Nancy Fulda"], "year": 2023, "venue": "Political Analysis", "doi": "10.1017/pan.2023.2", "category": "human-simulation", "reading_scope": "full-text", "tags": ["silicon-sampling", "bias", "validation"], "screening": "include"},
    {"slug": "gao-2024-llm-abm-survey", "title": "Large Language Models Empowered Agent-Based Modeling and Simulation: A Survey", "authors": ["Chen Gao", "Xiaochong Lan", "Nian Li"], "year": 2024, "venue": "Humanities and Social Sciences Communications", "doi": "10.1057/s41599-024-03611-3", "category": "llm-agents", "reading_scope": "full-text", "tags": ["multi-agent", "survey", "validation"], "screening": "include"},
    {"slug": "li-2024-econagent", "title": "EconAgent: Large Language Model-Empowered Agents for Simulating Macroeconomic Activities", "authors": ["Nian Li", "Chen Gao", "Mingyu Li"], "year": 2024, "venue": "ACL 2024", "doi": "10.18653/v1/2024.acl-long.829", "category": "human-simulation", "reading_scope": "full-text", "tags": ["economics", "multi-agent", "policy"], "screening": "include"},
    {"slug": "santurkar-2023-opinions", "title": "Whose Opinions Do Language Models Reflect?", "authors": ["Shibani Santurkar", "Esin Durmus", "Faisal Ladhak"], "year": 2023, "venue": "ICML 2023", "doi": "10.48550/arxiv.2303.17548", "arxiv_id": "2303.17548", "category": "evaluation-methods", "reading_scope": "full-text", "tags": ["bias", "benchmark", "validation"], "screening": "include"},
    {"slug": "du-2024-water-abm-llm", "title": "Coupling Large Language Models with Hydrological Agent-Based Water Allocation", "authors": ["Hao Du", "Lin Wei", "Sarah Chen"], "year": 2024, "venue": "Water Resources Research", "doi": "10.1029/2024wr037001", "category": "water-abm", "reading_scope": "full-text", "tags": ["hydrology", "multi-agent", "policy"], "screening": "include"},
    # 7 abstract-only papers
    {"slug": "aher-2023-turing-experiments", "title": "Using Large Language Models to Simulate Multiple Humans and Replicate Human Subject Studies", "authors": ["Gati Aher", "Rosa I. Arriaga", "Adam Tauman Kalai"], "year": 2023, "venue": "ICML 2023", "doi": "10.48550/arxiv.2208.10264", "arxiv_id": "2208.10264", "category": "human-simulation", "reading_scope": "abstract", "tags": ["simulation", "validation", "bias"], "screening": "include"},
    {"slug": "wu-2023-autogen", "title": "AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation", "authors": ["Qingyun Wu", "Gagan Bansal", "Jieyu Zhang"], "year": 2023, "venue": "arXiv", "doi": "10.48550/arxiv.2308.08155", "arxiv_id": "2308.08155", "category": "llm-agents", "reading_scope": "abstract", "tags": ["multi-agent", "tooling"], "screening": "include"},
    {"slug": "wang-2024-agent-survey", "title": "A Survey on Large Language Model Based Autonomous Agents", "authors": ["Lei Wang", "Chen Ma", "Xueyang Feng"], "year": 2024, "venue": "Frontiers of Computer Science", "doi": "10.1007/s11704-024-40231-1", "category": "llm-agents", "reading_scope": "abstract", "tags": ["survey", "memory", "multi-agent"], "screening": None},
    {"slug": "bisbee-2024-synthetic-replacements", "title": "Synthetic Replacements for Human Survey Data? The Perils of Large Language Models", "authors": ["James Bisbee", "Joshua D. Clinton", "Cassy Dorff"], "year": 2024, "venue": "Political Analysis", "doi": "10.1017/pan.2024.5", "category": "evaluation-methods", "reading_scope": "abstract", "tags": ["bias", "validation", "silicon-sampling"], "screening": "include"},
    {"slug": "dillion-2023-moral-judgments", "title": "Can AI Language Models Replace Human Participants?", "authors": ["Danica Dillion", "Nikhil Tandon", "Yuling Gu"], "year": 2023, "venue": "Trends in Cognitive Sciences", "doi": "10.1016/j.tics.2023.04.008", "category": "human-simulation", "reading_scope": "abstract", "tags": ["validation", "bias"], "screening": None},
    {"slug": "castilla-2024-basin-cooperation", "title": "Behavioral Heterogeneity in Transboundary River Basin Agent-Based Models", "authors": ["Elena Castilla", "Marco Rossi"], "year": 2024, "venue": "Environmental Modelling & Software", "doi": "10.1016/j.envsoft.2024.105912", "category": "water-abm", "reading_scope": "abstract", "tags": ["hydrology", "policy", "economics"], "screening": "include"},
    {"slug": "kim-2024-irrigation-agents", "title": "Adaptive Farmer Irrigation Decisions Under Drought Using Cognitive Agent Models", "authors": ["Minjun Kim", "Hana Park"], "year": 2024, "venue": "Journal of Hydrology", "doi": "10.1016/j.jhydrol.2024.131044", "category": "water-abm", "reading_scope": "abstract", "tags": ["hydrology", "simulation"], "screening": None},
    # 3 abstract-snippet papers
    {"slug": "zheng-2023-llm-judge", "title": "Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena", "authors": ["Lianmin Zheng", "Wei-Lin Chiang", "Ying Sheng"], "year": 2023, "venue": "NeurIPS 2023", "doi": "10.48550/arxiv.2306.05685", "arxiv_id": "2306.05685", "category": "evaluation-methods", "reading_scope": "abstract-snippet", "tags": ["benchmark", "validation"], "screening": None},
    {"slug": "shinn-2023-reflexion", "title": "Reflexion: Language Agents with Verbal Reinforcement Learning", "authors": ["Noah Shinn", "Federico Cassano", "Ashwin Gopinath"], "year": 2023, "venue": "NeurIPS 2023", "doi": "10.48550/arxiv.2303.11366", "arxiv_id": "2303.11366", "category": "llm-agents", "reading_scope": "abstract-snippet", "tags": ["memory", "reasoning"], "screening": "exclude"},
    {"slug": "hu-2024-persona-drift", "title": "Measuring Persona Drift and Demographic Stereotyping in Simulated Panels", "authors": ["Tiancheng Hu", "Nigel Collier"], "year": 2024, "venue": "EMNLP 2024", "doi": "10.18653/v1/2024.emnlp-main.412", "category": "evaluation-methods", "reading_scope": "abstract-snippet", "tags": ["bias", "silicon-sampling", "benchmark"], "screening": None},
    # 2 metadata-only papers (no abstract text)
    {"slug": "torres-2025-reservoir-rules", "title": "Multi-Reservoir Operating Rules Derived from Language-Guided Policy Search", "authors": ["Carlos Torres", "Ana Gomez"], "year": 2025, "venue": "Water Resources Management", "doi": "10.1007/s11269-025-04110-2", "category": "water-abm", "reading_scope": "metadata", "tags": ["hydrology", "policy"], "screening": None},
    {"slug": "chen-2025-agent-audit", "title": "Auditing Reproducibility of Multi-Agent Simulation Benchmarks", "authors": ["Mei Chen", "David Patel"], "year": 2025, "venue": "Nature Machine Intelligence", "doi": "10.1038/s42256-025-00988-1", "category": "evaluation-methods", "reading_scope": "metadata", "tags": ["benchmark", "validation"], "screening": "exclude"},
]


class _FakeZoteroClient:
    def __init__(self) -> None:
        self.created: list[dict] = []
        self.dois_seen: set[str] = set()

    def item_template(self, kind: str) -> dict:
        return {"itemType": kind}

    def create_items(self, items: list[dict]) -> dict:
        base = len(self.created)
        self.created.extend(items)
        for item in items:
            doi = str(item.get("DOI") or "").strip().lower()
            if doi:
                self.dois_seen.add(doi)
        return {
            "successful": {
                str(i): {"key": f"ZOT{base + i:04d}"} for i in range(len(items))
            }
        }


def _make_cfg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "vault"
    raw = root / "raw"
    hub = root / "hub"
    logs = root / "logs"
    pdfs = root / "pdfs"
    research_hub_dir = root / ".research_hub"
    for path in (raw, hub, logs, pdfs, research_hub_dir):
        path.mkdir(parents=True, exist_ok=True)
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "knowledge_base": {
                    "root": str(root),
                    "raw": str(raw),
                    "hub": str(hub),
                    "logs": str(logs),
                },
                "clusters_file": str(research_hub_dir / "clusters.yaml"),
                "zotero": {
                    "library_id": "998877",
                    "library_type": "user",
                    "default_collection": "DEFAULT",
                    "collections": {"DEFAULT": {"name": "Default"}},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("RESEARCH_HUB_CONFIG", str(config_path))
    monkeypatch.setenv("RESEARCH_HUB_ROOT", str(root))
    monkeypatch.delenv("RESEARCH_HUB_NO_ZOTERO", raising=False)

    import research_hub.config as cfg_mod

    monkeypatch.setattr(cfg_mod, "_config", None)
    monkeypatch.setattr(cfg_mod, "_config_path", None)
    cfg = cfg_mod.get_config()
    (cfg.research_hub_dir / "dedup_index.json").write_text("{}", encoding="utf-8")
    (cfg.research_hub_dir / "manifest.jsonl").write_text("", encoding="utf-8")
    (cfg.research_hub_dir / "nlm_cache.json").write_text("{}", encoding="utf-8")
    return cfg, config_path


def _build_20_paper_inputs() -> list[dict]:
    items = []
    for idx, spec in enumerate(COHORT_SPECS):
        has_abstract = spec["reading_scope"] != "metadata"
        abstract_text = (
            f"Detailed empirical abstract for {spec['title']} ({spec['year']}). "
            f"Investigates {', '.join(spec['tags'])} within {spec['category']} "
            f"using structured evaluation protocols across multiple scenarios (#{idx + 1})."
            if has_abstract
            else ""
        )
        p = paper_input(
            spec["title"],
            spec["slug"],
            spec["doi"],
            arxiv_id=spec.get("arxiv_id", ""),
        )
        p.update(
            {
                "authors": spec["authors"],
                "year": spec["year"],
                "journal": spec["venue"],
                "tags": list(spec["tags"]),
                "abstract": abstract_text if has_abstract else "TBD",
                "summary": abstract_text or "Metadata-only bibliographic record awaiting full-text acquisition.",
                "relevance": f"Relevant to {spec['category']} ({spec['reading_scope']}).",
                "reading_level": spec["reading_scope"],
                "url": f"https://doi.org/{spec['doi']}",
            }
        )
        items.append(p)
    return items


def _http_json(url: str, *, method: str = "GET", payload: dict | None = None, csrf: str | None = None, origin: str | None = None) -> tuple[int, dict]:
    headers = {"Accept": "application/json"}
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode("utf-8")
    if csrf is not None:
        headers["X-CSRF-Token"] = csrf
    if origin is not None:
        headers["Origin"] = origin
    req = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(req, timeout=8) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def _fetch_csrf(base: str) -> str:
    with urlopen(f"{base}/app/", timeout=8) as resp:
        html = resp.read().decode("utf-8")
    match = re.search(r'<meta name="research-hub-csrf-token" content="([^"]+)"', html)
    assert match, "Missing CSRF meta tag"
    return match.group(1)


def _build_obsidian_dedup_index(raw_dir: Path) -> DedupIndex:
    index = DedupIndex()
    for hit in build_from_obsidian(raw_dir):
        index.add(hit)
    return index


def _ingest_20_papers(cfg, monkeypatch: pytest.MonkeyPatch, fake_zotero: _FakeZoteroClient, cluster_slug: str = "multi-agent-20"):
    registry = ClusterRegistry(cfg.clusters_file)
    cluster = registry.create(
        query="LLM agents, human simulation, and water ABM",
        name="Multi-Agent & Water ABM (20 Papers)",
        slug=cluster_slug,
        zotero_collection_key="COLL20",
    )
    papers = _build_20_paper_inputs()
    (cfg.root / "papers_input.json").write_text(
        json.dumps({"papers": papers}, ensure_ascii=False), encoding="utf-8"
    )
    monkeypatch.setattr(pipeline, "get_config", lambda: cfg)
    monkeypatch.setattr(pipeline, "get_client", lambda: fake_zotero)
    monkeypatch.setattr(pipeline, "check_duplicate", lambda _zot, doi, _title: bool(doi and doi.lower() in fake_zotero.dois_seen))
    monkeypatch.setattr(pipeline, "add_note", lambda *a, **k: True)
    monkeypatch.setattr(pipeline.time, "sleep", lambda _s: None)
    return cluster


def test_scenario_1_20_paper_ingest_dry_run_apply_and_dedup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """20 papers: dry-run writes nothing, apply writes all 20 to Obsidian & Zotero with tags, re-run deduplicates."""
    cfg, _ = _make_cfg(tmp_path, monkeypatch)
    fake_zotero = _FakeZoteroClient()
    cluster = _ingest_20_papers(cfg, monkeypatch, fake_zotero)
    monkeypatch.setattr(
        pipeline,
        "_load_or_build_dedup",
        lambda *_a, **_k: _build_obsidian_dedup_index(cfg.raw),
    )

    # 1. Dry-run must write zero notes and zero Zotero items
    rc_dry = pipeline.run_pipeline(
        cluster_slug=cluster.slug,
        query="LLM agents, human simulation, and water ABM",
        dry_run=True,
        verify=False,
    )
    assert rc_dry == 0
    assert list((cfg.raw / cluster.slug).glob("*.md")) == []
    assert len(fake_zotero.created) == 0

    # 2. Live apply writes all 20 papers to Obsidian & Zotero
    rc_apply = pipeline.run_pipeline(
        cluster_slug=cluster.slug,
        query="LLM agents, human simulation, and water ABM",
        dry_run=False,
        verify=False,
    )
    assert rc_apply == 0
    notes = sorted((cfg.raw / cluster.slug).glob("*.md"))
    assert len(notes) == 20
    assert len(fake_zotero.created) == 20

    # Verify tags & cluster metadata made it into Zotero items and Obsidian notes
    first_zot_tags = {t["tag"] for t in fake_zotero.created[0].get("tags", [])}
    assert "research-hub" in first_zot_tags
    assert f"cluster/{cluster.slug}" in first_zot_tags
    assert "multi-agent" in first_zot_tags

    sample_note_text = (cfg.raw / cluster.slug / "park-2023-generative-agents.md").read_text(encoding="utf-8")
    assert 'doi: "10.1145/3586183.3606763"' in sample_note_text
    assert cluster.slug in sample_note_text

    # 3. Re-running ingest against the same 20 papers deduplicates cleanly (0 new Zotero creates)
    rc_second = pipeline.run_pipeline(
        cluster_slug=cluster.slug,
        query="LLM agents, human simulation, and water ABM",
        dry_run=False,
        verify=False,
    )
    assert rc_second == 0
    assert len(fake_zotero.created) == 20
    assert len(list((cfg.raw / cluster.slug).glob("*.md"))) == 20


def test_scenario_2_20_paper_obsidian_snapshot_and_workspace_http_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """20 papers flow through Obsidian vault -> library_snapshot.py -> live WorkspaceServer with tags & curation."""
    cfg, config_path = _make_cfg(tmp_path, monkeypatch)
    fake_zotero = _FakeZoteroClient()
    cluster = _ingest_20_papers(cfg, monkeypatch, fake_zotero)
    monkeypatch.setattr(
        pipeline,
        "_load_or_build_dedup",
        lambda *_a, **_k: _build_obsidian_dedup_index(cfg.raw),
    )
    assert pipeline.run_pipeline(cluster_slug=cluster.slug, query="LLM agents, human simulation, and water ABM", verify=False) == 0

    # Generate read-only UI snapshot via the real CLI script
    (cfg.root / ".obsidian").mkdir(exist_ok=True)
    snapshot_path = tmp_path / "library-snapshot-20.json"
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "library_snapshot.py"
    proc = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--vault",
            str(cfg.root),
            "--collection",
            cluster.slug,
            "--output",
            str(snapshot_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"library_snapshot.py failed: {proc.stderr}"
    snapshot_data = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert snapshot_data["read_only"] is True
    assert snapshot_data["body_read"] is False
    assert len(snapshot_data["notes"]) == 20

    # Populate a Workspace with all 20 papers (sources + curations + screenings)
    ws_root = tmp_path / "workspace"
    ws = Workspace(ws_root)
    project = ws.create_project(
        id="cohort-20",
        title="20-Paper Multi-Agent & Water ABM Review",
        archetype="review",
        goal="Synthesize LLM-agent simulation validity across economics and water ABM.",
    )
    source_ids: list[str] = []
    for spec in COHORT_SPECS:
        src = ws.add_record(
            project["id"],
            kind="source",
            data={
                "title": spec["title"],
                "locator": f"https://doi.org/{spec['doi']}",
                "doi": spec["doi"],
                "authors": spec["authors"],
                "year": spec["year"],
                "venue": spec["venue"],
                "category": spec["category"],
                "tags": spec["tags"],
                "reading_scope": spec["reading_scope"],
                "summary": (
                    f"Abstract summary for {spec['title']}."
                    if spec["reading_scope"] != "metadata"
                    else ""
                ),
            },
        )
        source_ids.append(src["id"])
        if spec["screening"]:
            ws.add_record(
                project["id"],
                kind="screening",
                data={
                    "source_id": src["id"],
                    "decision": spec["screening"],
                    "rationale": f"Screened as {spec['screening']} ({spec['reading_scope']}).",
                },
            )

    # Curate tags on paper #1 via append-only source_curation
    ws.add_record(
        project["id"],
        kind="source_curation",
        data={
            "source_id": source_ids[0],
            "tags": ["multi-agent", "memory", "simulation", "landmark"],
        },
    )

    server = WorkspaceServer(
        ws.root,
        port=0,
        obsidian_vault=cfg.root,
        library_snapshot=snapshot_path,
        integrations_config=config_path,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        csrf = _fetch_csrf(base)

        code, proj = _http_json(f"{base}/api/v1/projects/cohort-20")
        assert code == 200 and proj["ok"] is True
        sources = [r for r in proj["records"] if r["kind"] == "source"]
        curations = [r for r in proj["records"] if r["kind"] == "source_curation"]
        screenings = [r for r in proj["records"] if r["kind"] == "screening"]
        assert len(sources) == 20
        assert len(curations) == 1
        assert "landmark" in curations[0]["data"]["tags"]
        assert len(screenings) == 14

        # Verify read-only Obsidian snapshot API serves all 20 notes with matching DOIs
        code, snap = _http_json(f"{base}/api/v1/library/snapshot")
        assert code == 200
        assert len(snap["notes"]) == 20
        workspace_dois = {r["data"]["doi"].lower() for r in sources}
        snapshot_dois = {n["data"]["doi"].lower() for n in snap["notes"]}
        assert workspace_dois == snapshot_dois

        # Validate authorized Obsidian vault vs rejected workspace-internal path
        code, ok_val = _http_json(
            f"{base}/api/v1/integrations/obsidian/validate",
            method="POST",
            payload={"vault_path": str(cfg.root)},
            csrf=csrf,
            origin=base,
        )
        assert code == 200 and ok_val["ok"] is True and ok_val["status"] == "valid"

        code, denied_val = _http_json(
            f"{base}/api/v1/integrations/obsidian/validate",
            method="POST",
            payload={"vault_path": str(ws_root)},
            csrf=csrf,
            origin=base,
        )
        assert code == 403 and denied_val["code"] == "vault_scope_denied"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_scenario_3_20_paper_notebooklm_bundle_and_dry_run_upload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """20 papers in NotebookLM pipeline: 8 PDFs + abstract-only text sources + URL fallbacks + upload dry-run."""
    cfg, _ = _make_cfg(tmp_path, monkeypatch)
    fake_zotero = _FakeZoteroClient()
    cluster = _ingest_20_papers(cfg, monkeypatch, fake_zotero)
    monkeypatch.setattr(
        pipeline,
        "_load_or_build_dedup",
        lambda *_a, **_k: _build_obsidian_dedup_index(cfg.raw),
    )
    assert pipeline.run_pipeline(cluster_slug=cluster.slug, query="LLM agents, human simulation, and water ABM", verify=False) == 0

    # Place real PDF blobs for the 8 full-text papers only; leave the other 12 without PDFs
    pdfs_dir = cfg.root / "pdfs"
    for spec in COHORT_SPECS:
        if spec["reading_scope"] == "full-text":
            safe_name = re.sub(r"[^a-z0-9._-]", "_", spec["doi"].lower()) + ".pdf"
            (pdfs_dir / safe_name).write_bytes(PDF_BLOB)

    # Also simulate 3 abstract-only notes whose publisher URL is absent so the abstract-text rung is verified too
    for slug in ("bisbee-2024-synthetic-replacements", "dillion-2023-moral-judgments", "kim-2024-irrigation-agents"):
        note_path = cfg.raw / cluster.slug / f"{slug}.md"
        note_body = note_path.read_text(encoding="utf-8")
        note_body = re.sub(r'^doi:.*$', 'doi: ""', note_body, flags=re.MULTILINE)
        note_body = re.sub(r'^url:.*$', 'url: ""', note_body, flags=re.MULTILINE)
        note_path.write_text(note_body, encoding="utf-8")

    report = bundle_cluster(cluster, cfg, download_pdfs=False)
    assert len(report.entries) == 20
    assert report.pdf_count == 8
    assert report.text_count == 3
    assert report.url_count == 9
    assert report.skip_count == 0
    assert (report.bundle_dir / "manifest.json").exists()
    assert (report.bundle_dir / "README.md").exists()
    assert (report.bundle_dir / "sources.txt").exists()

    manifest = json.loads((report.bundle_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["pdf_count"] == 8
    assert manifest["text_count"] == 3
    assert manifest["url_count"] == 9

    # Dry-run NotebookLM upload validates the 20-source plan with zero live network/auth side effects
    upload_report = upload_cluster(cluster, cfg, dry_run=True)
    assert upload_report.dry_run is True
    assert upload_report.fail_count == 0


def test_scenario_4_multi_persona_zotero_and_notebooklm_integration_probes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Simulates offline user, valid/403 Zotero API key states, encrypted secret box, and NLM session states."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))
    for var in ("ZOTERO_API_KEY", "ZOTERO_LIBRARY_ID", "ZOTERO_LIBRARY_TYPE", "SEMANTIC_SCHOLAR_API_KEY", "UNPAYWALL_EMAIL"):
        monkeypatch.delenv(var, raising=False)

    cfg, config_path = _make_cfg(tmp_path, monkeypatch)
    clean_cfg = json.loads(config_path.read_text(encoding="utf-8"))
    clean_cfg["zotero"] = {}
    config_path.write_text(json.dumps(clean_cfg), encoding="utf-8")

    # Local mock Zotero Web API server (200 for valid key, 403 for invalid key)
    class _MockZoteroHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            api_key = self.headers.get("Zotero-API-Key", "")
            if api_key == "VALID_TEST_ZOTERO_KEY_2026":
                payload = json.dumps([{"key": "ITEM1"}]).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(payload)
            else:
                self.send_response(403)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"Forbidden")

        def log_message(self, *_args):
            pass

    mock_zot = ThreadingHTTPServer(("127.0.0.1", 0), _MockZoteroHandler)
    mock_zot_thread = threading.Thread(target=mock_zot.serve_forever, daemon=True)
    mock_zot_thread.start()
    try:
        mock_zot_base = f"http://127.0.0.1:{mock_zot.server_port}"

        import research_hub.workspace.integrations as integ_mod

        monkeypatch.setattr(integ_mod, "urlopen", lambda *_a, **_k: (_ for _ in ()).throw(OSError("No local Zotero desktop")))

        class _MockPyzoteroClient:
            def __init__(self, lib_id: str, lib_type: str, api_key: str):
                self.lib_id = lib_id
                self.lib_type = lib_type
                self.api_key = api_key

            def top(self, limit: int = 1):
                req = Request(
                    f"{mock_zot_base}/users/{self.lib_id}/items/top?limit={limit}",
                    headers={"Zotero-API-Key": self.api_key},
                )
                with urlopen(req, timeout=5) as resp:
                    return json.loads(resp.read().decode("utf-8"))

        monkeypatch.setitem(
            sys.modules,
            "pyzotero",
            SimpleNamespace(zotero=SimpleNamespace(Zotero=_MockPyzoteroClient)),
        )
        monkeypatch.setitem(
            sys.modules,
            "pyzotero.zotero",
            SimpleNamespace(Zotero=_MockPyzoteroClient),
        )

        def _offline_nlm_health(state_file: Path, auto_refresh: bool = True) -> dict:
            del auto_refresh
            if not state_file.exists():
                return {"ok": False, "reason": "missing"}
            payload = json.loads(state_file.read_text(encoding="utf-8"))
            cookies = payload.get("cookies") or []
            now_ts = time.time()
            valid = any(c.get("name") == "SID" and float(c.get("expires", 0)) > now_ts for c in cookies)
            return {"ok": valid, "refreshed": False}

        monkeypatch.setattr("research_hub.notebooklm.auth.ensure_session_health", _offline_nlm_health)

        ws = Workspace(tmp_path / "ws")
        server = WorkspaceServer(ws.root, port=0, integrations_config=config_path)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            csrf = _fetch_csrf(base)

            # Persona A: Offline zero-account user
            code, zot_missing = _http_json(f"{base}/api/v1/integrations/zotero/check", method="POST", payload={}, csrf=csrf, origin=base)
            assert code == 200 and zot_missing["probe"]["status"] == "missing_credentials"

            code, nlm_missing = _http_json(f"{base}/api/v1/integrations/notebooklm/check", method="POST", payload={}, csrf=csrf, origin=base)
            assert code == 200 and nlm_missing["probe"]["status"] == "missing"

            # Persona B: Save valid Zotero credentials -> encrypted on disk, never echoed, live probe -> connected_web
            code, saved = _http_json(
                f"{base}/api/v1/integrations/credentials",
                method="POST",
                payload={
                    "zotero_library_id": "554433",
                    "zotero_library_type": "user",
                    "zotero_api_key": "VALID_TEST_ZOTERO_KEY_2026",
                },
                csrf=csrf,
                origin=base,
            )
            assert code == 200 and saved["ok"] is True
            assert "VALID_TEST_ZOTERO_KEY_2026" not in json.dumps(saved)
            raw_disk_cfg = config_path.read_text(encoding="utf-8")
            assert "VALID_TEST_ZOTERO_KEY_2026" not in raw_disk_cfg
            stored_key = json.loads(raw_disk_cfg)["zotero"]["api_key"]
            assert is_encrypted(stored_key)

            code, zot_ok = _http_json(f"{base}/api/v1/integrations/zotero/check", method="POST", payload={}, csrf=csrf, origin=base)
            assert code == 200 and zot_ok["probe"]["status"] == "connected_web"

            # Invalid API key -> auth_failed (403)
            code, _ = _http_json(
                f"{base}/api/v1/integrations/credentials",
                method="POST",
                payload={"zotero_api_key": "INVALID_KEY_403"},
                csrf=csrf,
                origin=base,
            )
            assert code == 200
            code, zot_bad = _http_json(f"{base}/api/v1/integrations/zotero/check", method="POST", payload={}, csrf=csrf, origin=base)
            assert code == 200 and zot_bad["probe"]["status"] == "auth_failed"

            # Persona C: NotebookLM session state checks (valid future cookie vs expired cookie)
            nlm_state = default_state_file(cfg.research_hub_dir)
            nlm_state.parent.mkdir(parents=True, exist_ok=True)
            future_exp = time.time() + 86400 * 7
            nlm_state.write_text(
                json.dumps(
                    {
                        "cookies": [
                            {"name": "SID", "value": "fake-sid", "domain": ".google.com", "expires": future_exp},
                            {"name": "HSID", "value": "fake-hsid", "domain": ".google.com", "expires": future_exp},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            code, nlm_auth = _http_json(f"{base}/api/v1/integrations/notebooklm/check", method="POST", payload={}, csrf=csrf, origin=base)
            assert code == 200 and nlm_auth["probe"]["status"] == "authenticated"

            past_exp = time.time() - 3600
            nlm_state.write_text(
                json.dumps(
                    {
                        "cookies": [
                            {"name": "SID", "value": "expired-sid", "domain": ".google.com", "expires": past_exp},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            code, nlm_exp = _http_json(f"{base}/api/v1/integrations/notebooklm/check", method="POST", payload={}, csrf=csrf, origin=base)
            assert code == 200 and nlm_exp["probe"]["status"] == "expired"
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
    finally:
        mock_zot.shutdown()
        mock_zot.server_close()
        mock_zot_thread.join(timeout=5)


def test_scenario_5_ai_agent_handoff_hook_task_lifecycle_for_20_papers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """End-to-end AI Agent Handoff button flow: scoped selected_source_ids -> packet -> import result -> review gate."""
    # Even if RESEARCH_HUB_WRITING_ADAPTER is configured, scoped selected_source_ids handoffs MUST NOT bind whole-project manuscript_state.
    monkeypatch.setenv("RESEARCH_HUB_WRITING_ADAPTER", str(tmp_path / "nonexistent-adapter"))
    ws = Workspace(tmp_path / "ws")
    project = ws.create_project(
        id="handoff-20",
        title="20-Paper AI Agent Handoff Test",
        archetype="review",
        goal="Verify AI agent handoff task creation, source scoping, and human review boundary.",
    )
    source_ids: list[str] = []
    for spec in COHORT_SPECS:
        rec = ws.add_record(
            project["id"],
            kind="source",
            data={
                "title": spec["title"],
                "locator": f"https://doi.org/{spec['doi']}",
                "doi": spec["doi"],
                "category": spec["category"],
                "tags": spec["tags"],
                "reading_scope": spec["reading_scope"],
            },
        )
        source_ids.append(rec["id"])
    # Also register an unrelated private manuscript file to prove selected_source_ids never even reads/hashes it
    private_draft = ws.root / "private_manuscript.md"
    private_draft.write_text("# Private Draft\nDo not leak into single-paper handoff.\n", encoding="utf-8")
    ws.register_artifact(project["id"], path="private_manuscript.md", role="main_manuscript")

    from research_hub.workspace import _source_storage as storage_mod

    orig_current_hash = storage_mod.current_hash
    hashed_paths: list[str] = []

    def _spy_current_hash(workspace, item):
        hashed_paths.append(str(item.get("path") or ""))
        return orig_current_hash(workspace, item)

    monkeypatch.setattr(storage_mod, "current_hash", _spy_current_hash)

    server = WorkspaceServer(ws.root, port=0, human=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        csrf = _fetch_csrf(base)

        # Reject unknown source IDs in selected_source_ids
        code, bad_scope = _http_json(
            f"{base}/api/v1/projects/handoff-20/tasks",
            method="POST",
            payload={
                "operation": "synthesize",
                "mode": "handoff",
                "instructions": "Invalid scope test",
                "selected_source_ids": ["nonexistent-source-id"],
            },
            csrf=csrf,
            origin=base,
        )
        assert code == 400 and bad_scope["ok"] is False

        # Scoped 2-paper handoff must capture ONLY those 2 sources and ZERO unrelated private artifacts
        chosen_ids = source_ids[:2]
        handoff_instructions = (
            "# Research Hub AI Agent Handoff\n"
            "- Project: 20-Paper AI Agent Handoff Test (`handoff-20`)\n"
            "- Target sources: 2 (2 full-text declared, 0 abstract/metadata)\n"
            "## Task: Convert & Sync to Zotero + Obsidian\n"
            "1. Run `research-hub ingest --input papers.json --cluster handoff-20 --dry-run`.\n"
            "2. Wait for explicit human approval before writing."
        )
        code, created = _http_json(
            f"{base}/api/v1/projects/handoff-20/tasks",
            method="POST",
            payload={
                "operation": "synthesize",
                "mode": "handoff",
                "instructions": handoff_instructions,
                "selected_source_ids": chosen_ids,
            },
            csrf=csrf,
            origin=base,
        )
        assert code == 200 and created["ok"] is True
        task = created["task"]
        task_id = task["id"]
        assert task["mode"] == "handoff"
        assert task["operation"] == "synthesize"
        assert task["status"] == "awaiting_agent"
        assert task["request"]["selected_source_ids"] == chosen_ids
        assert [r["id"] for r in task["request"]["records"]] == chosen_ids
        assert task["request"]["artifacts"] == []
        assert "manuscript_state" not in task["request"]
        assert task["request"]["adapter_sha256"] is None
        assert "private_manuscript.md" not in hashed_paths

        # Export handoff packet — verify only the 2 selected sources are exported, never the other 18 or private draft
        code, packet = _http_json(
            f"{base}/api/v1/tasks/{task_id}/handoff",
            method="POST",
            payload={},
            csrf=csrf,
            origin=base,
        )
        assert code == 200 and packet["ok"] is True
        assert packet["packet"]["task_id"] == task_id
        assert [r["id"] for r in packet["packet"]["records"]] == chosen_ids
        assert packet["packet"]["artifacts"] == []

        # Import AI agent's dry-run report back into Research Hub — must wait for human review, never auto-accept!
        code, imported = _http_json(
            f"{base}/api/v1/tasks/{task_id}/result",
            method="POST",
            payload={
                "status": "completed",
                "prose": "Dry-run prepared for 2 selected papers. Awaiting human approval before Zotero/Obsidian writes.",
                "artifacts": [],
                "input_hash": task["action_hash"],
            },
            csrf=csrf,
            origin=base,
        )
        assert code == 200 and imported["ok"] is True
        assert imported["task"]["status"] == "awaiting_human"
        assert imported["task"]["result"]["semantic_acceptance"] == "pending"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


MULTI_TOPIC_COHORTS: dict[str, dict] = {
    "llm-social-sim": {
        "title": "LLM Multi-Agent & Behavioral Simulation",
        "query": "LLM multi-agent social simulation behavioral fidelity",
        "zotero_key": "COLL_LLM",
        "papers": [
            {"slug": "park-2023-agents", "title": "Generative Agents: Interactive Simulacra", "authors": ["Joon Sung Park"], "year": 2023, "venue": "UIST", "doi": "10.1145/3586183.3606763", "category": "llm-agents", "scope": "full-text", "tags": ["multi-agent", "simulation"]},
            {"slug": "argyle-2023-silicon", "title": "Out of One, Many: Silicon Sampling", "authors": ["Lisa P. Argyle"], "year": 2023, "venue": "Political Analysis", "doi": "10.1017/pan.2023.2", "category": "human-simulation", "scope": "full-text", "tags": ["silicon-sampling", "validation"]},
            {"slug": "bisbee-2024-perils", "title": "Synthetic Replacements for Human Survey Data", "authors": ["James Bisbee"], "year": 2024, "venue": "Political Analysis", "doi": "10.1017/pan.2024.5", "category": "evaluation-methods", "scope": "abstract", "tags": ["bias", "validation"]},
            {"slug": "li-2024-econagent", "title": "EconAgent: Macroeconomic Activities Simulation", "authors": ["Nian Li"], "year": 2024, "venue": "ACL", "doi": "10.18653/v1/2024.acl-long.829", "category": "human-simulation", "scope": "abstract", "tags": ["economics", "multi-agent"]},
        ],
    },
    "hydro-climate-abm": {
        "title": "Basin Hydrology & Climate Adaptation ABM",
        "query": "river basin hydrology drought adaptation agent-based modeling",
        "zotero_key": "COLL_HYDRO",
        "papers": [
            {"slug": "du-2024-hydro-llm", "title": "Coupling LLMs with Hydrological Water Allocation", "authors": ["Hao Du", "Lin Wei"], "year": 2024, "venue": "Water Resources Research", "doi": "10.1029/2024wr037001", "category": "water-abm", "scope": "full-text", "tags": ["hydrology", "drought"]},
            {"slug": "castilla-2024-basin", "title": "Behavioral Heterogeneity in Transboundary River Basins", "authors": ["Elena Castilla"], "year": 2024, "venue": "Env Modelling & Software", "doi": "10.1016/j.envsoft.2024.105912", "category": "water-abm", "scope": "full-text", "tags": ["hydrology", "policy"]},
            {"slug": "kim-2024-irrigation", "title": "Adaptive Farmer Irrigation Under Drought", "authors": ["Minjun Kim"], "year": 2024, "venue": "Journal of Hydrology", "doi": "10.1016/j.jhydrol.2024.131044", "category": "climate-adaptation", "scope": "abstract", "tags": ["irrigation", "drought"]},
            {"slug": "torres-2025-reservoir", "title": "Multi-Reservoir Operating Rules Under Climate Shift", "authors": ["Carlos Torres"], "year": 2025, "venue": "Water Resources Management", "doi": "10.1007/s11269-025-04110-2", "category": "reservoir-ops", "scope": "metadata", "tags": ["reservoir", "policy"]},
        ],
    },
    "clinical-ai-trials": {
        "title": "Clinical AI Decision Support & Medical Trials",
        "query": "clinical AI decision support randomized controlled trials",
        "zotero_key": "COLL_CLINICAL",
        "papers": [
            {"slug": "vance-2025-sepsis-rct", "title": "Randomized Trial of Bedside Clinical AI Sepsis Alerts", "authors": ["Elena Vance", "Marcus Chen"], "year": 2025, "venue": "Nature Medicine", "doi": "10.1038/s41591-025-00111-2", "category": "clinical-trials", "scope": "full-text", "tags": ["rct", "sepsis", "validation"]},
            {"slug": "patel-2024-radiology-cds", "title": "Diagnostic Calibration in Chest Radiography AI", "authors": ["Priya Patel"], "year": 2024, "venue": "The Lancet Digital Health", "doi": "10.1016/s2589-7500(24)00045-8", "category": "diagnostic-ai", "scope": "full-text", "tags": ["radiology", "calibration"]},
            {"slug": "gomez-2024-ehr-triage", "title": "Prospective Evaluation of Emergency Triage LLMs", "authors": ["Sofia Gomez"], "year": 2024, "venue": "JAMA Network Open", "doi": "10.1001/jamanetworkopen.2024.11892", "category": "clinical-triage", "scope": "abstract", "tags": ["ehr", "triage"]},
            {"slug": "okafor-2025-fda-audit", "title": "Post-Market Surveillance of Cleared Medical AI Devices", "authors": ["Chidi Okafor"], "year": 2025, "venue": "NEJM AI", "doi": "10.1056/aics20250042", "category": "regulatory-audit", "scope": "metadata", "tags": ["fda", "safety"]},
        ],
    },
}


def test_scenario_6_multi_topic_three_domain_e2e_crud_obsidian_bases_and_isolation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """3 distinct academic topics: ingest + Obsidian .base views + multi-collection snapshot + HTTP CRUD + isolation."""
    from research_hub.obsidian_bases import write_cluster_base

    cfg, config_path = _make_cfg(tmp_path, monkeypatch)
    fake_zotero = _FakeZoteroClient()
    registry = ClusterRegistry(cfg.clusters_file)

    monkeypatch.setattr(pipeline, "get_config", lambda: cfg)
    monkeypatch.setattr(pipeline, "get_client", lambda: fake_zotero)
    monkeypatch.setattr(
        pipeline,
        "check_duplicate",
        lambda _zot, doi, _title: bool(doi and doi.lower() in fake_zotero.dois_seen),
    )
    monkeypatch.setattr(pipeline, "add_note", lambda *a, **k: True)
    monkeypatch.setattr(pipeline.time, "sleep", lambda _s: None)
    monkeypatch.setattr(
        pipeline,
        "_load_or_build_dedup",
        lambda *_a, **_k: _build_obsidian_dedup_index(cfg.raw),
    )

    for slug, topic in MULTI_TOPIC_COHORTS.items():
        registry.create(
            query=topic["query"],
            name=topic["title"],
            slug=slug,
            zotero_collection_key=topic["zotero_key"],
        )
        topic_inputs = []
        for p_spec in topic["papers"]:
            item = paper_input(p_spec["title"], p_spec["slug"], p_spec["doi"])
            item.update(
                {
                    "authors": p_spec["authors"],
                    "year": p_spec["year"],
                    "journal": p_spec["venue"],
                    "tags": list(p_spec["tags"]),
                    "abstract": (
                        f"Empirical study on {p_spec['title']}."
                        if p_spec["scope"] != "metadata"
                        else "TBD"
                    ),
                    "summary": f"Summary for {p_spec['title']}.",
                    "reading_level": p_spec["scope"],
                    "url": f"https://doi.org/{p_spec['doi']}",
                }
            )
            topic_inputs.append(item)
        (cfg.root / "papers_input.json").write_text(
            json.dumps({"papers": topic_inputs}, ensure_ascii=False), encoding="utf-8"
        )
        assert pipeline.run_pipeline(cluster_slug=slug, query=topic["query"], verify=False) == 0
        base_file, _ = write_cluster_base(hub_root=cfg.hub, cluster_slug=slug, cluster_name=topic["title"], force=True)
        assert base_file.is_file()
        assert "views:" in base_file.read_text(encoding="utf-8")

    assert len(fake_zotero.created) == 12
    for slug in MULTI_TOPIC_COHORTS:
        assert len(list((cfg.raw / slug).glob("*.md"))) == 4

    # Multi-collection Obsidian snapshot across all 3 topics (12 notes total)
    (cfg.root / ".obsidian").mkdir(exist_ok=True)
    snapshot_path = tmp_path / "library-snapshot-multi.json"
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "library_snapshot.py"
    collection_flags = [arg for slug in MULTI_TOPIC_COHORTS for arg in ("--collection", slug)]
    proc = subprocess.run(
        [sys.executable, str(script_path), "--vault", str(cfg.root), *collection_flags, "--output", str(snapshot_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    snap_json = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert len(snap_json["collections"]) == 3
    assert len(snap_json["notes"]) == 12
    snap_collection_ids = {n["data"]["collection_id"] for n in snap_json["notes"]}
    assert snap_collection_ids == set(MULTI_TOPIC_COHORTS.keys())

    # Create 3 isolated projects on WorkspaceServer and test CRUD + isolation
    ws = Workspace(tmp_path / "ws-multi")
    first_source_by_topic: dict[str, str] = {}
    for slug, topic in MULTI_TOPIC_COHORTS.items():
        ws.create_project(id=slug, title=topic["title"], archetype="review", goal=topic["query"])
        for p_spec in topic["papers"]:
            rec = ws.add_record(
                slug,
                kind="source",
                data={
                    "title": p_spec["title"],
                    "locator": f"https://doi.org/{p_spec['doi']}",
                    "doi": p_spec["doi"],
                    "authors": p_spec["authors"],
                    "year": p_spec["year"],
                    "venue": p_spec["venue"],
                    "category": p_spec["category"],
                    "tags": p_spec["tags"],
                    "reading_scope": p_spec["scope"],
                },
            )
            first_source_by_topic.setdefault(slug, rec["id"])

    server = WorkspaceServer(
        ws.root,
        port=0,
        obsidian_vault=cfg.root,
        library_snapshot=snapshot_path,
        integrations_config=config_path,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        csrf = _fetch_csrf(base)

        # Verify workspace capability exposes vault basename only (never full filesystem path)
        code, ws_info = _http_json(f"{base}/api/v1/workspace")
        assert code == 200
        local_cap = ws_info["capabilities"]["local_integrations"]
        assert local_cap["obsidian_vault_configured"] is True
        assert local_cap["obsidian_vault_name"] == "vault"
        assert str(cfg.root) not in json.dumps(local_cap)

        # 1. Add a 5th source to clinical-ai-trials via HTTP
        code, added = _http_json(
            f"{base}/api/v1/projects/clinical-ai-trials/records",
            method="POST",
            payload={
                "kind": "source",
                "data": {
                    "title": "Multi-Center Cardiology AI Alert Trial",
                    "locator": "https://doi.org/10.1056/nejmoa2025991",
                    "doi": "10.1056/nejmoa2025991",
                    "authors": ["Hannah Lin", "David Cho"],
                    "year": "2025",
                    "venue": "NEJM",
                    "category": "clinical-trials",
                    "tags": ["cardiology", "rct"],
                    "reading_scope": "full-text",
                },
            },
            csrf=csrf,
            origin=base,
        )
        assert code == 200 and added["ok"] is True
        added_id = added["record"]["id"]

        # 2. Edit DOI/tags, Archive, and Restore via source_curation
        for patch in (
            {"source_id": added_id, "doi": "10.1056/nejmoa2025999", "tags": ["cardiology", "rct", "fda"], "archived": True},
            {"source_id": added_id, "archived": False},
        ):
            code, cur_resp = _http_json(
                f"{base}/api/v1/projects/clinical-ai-trials/records",
                method="POST",
                payload={"kind": "source_curation", "data": patch},
                csrf=csrf,
                origin=base,
            )
            assert code == 200 and cur_resp["ok"] is True

        # 3. Bind an Evidence claim in clinical-ai-trials
        code, claim_resp = _http_json(
            f"{base}/api/v1/projects/clinical-ai-trials/records",
            method="POST",
            payload={
                "kind": "claim",
                "data": {
                    "text": "Bedside sepsis and cardiology AI alerts reduce time-to-intervention.",
                    "source_ids": [first_source_by_topic["clinical-ai-trials"], added_id],
                    "uncertainty": "Requires external hospital validation.",
                },
            },
            csrf=csrf,
            origin=base,
        )
        assert code == 200 and claim_resp["ok"] is True

        # 4. Cross-project isolation: curating a clinical source inside hydro-climate-abm MUST fail with 400
        code, cross_err = _http_json(
            f"{base}/api/v1/projects/hydro-climate-abm/records",
            method="POST",
            payload={"kind": "source_curation", "data": {"source_id": added_id, "category": "tampered"}},
            csrf=csrf,
            origin=base,
        )
        assert code == 400 and cross_err["ok"] is False

        # Verify llm-social-sim and hydro-climate-abm still have exactly 4 sources each, while clinical-ai-trials has 5
        for slug, expected_count in (("llm-social-sim", 4), ("hydro-climate-abm", 4), ("clinical-ai-trials", 5)):
            code, detail = _http_json(f"{base}/api/v1/projects/{slug}")
            assert code == 200
            topic_sources = [r for r in detail["records"] if r["kind"] == "source"]
            assert len(topic_sources) == expected_count
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

