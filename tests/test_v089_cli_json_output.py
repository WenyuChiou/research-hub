from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from research_hub import cli
from research_hub.auto import AutoReport, AutoStepResult
from research_hub.crystal import CrystalApplyResult
from research_hub.doctor import CheckResult
from research_hub.fit_check import FitCheckReport, FitCheckResult
from research_hub.importer import ImportEntry, ImportReport
from research_hub.notebooklm.upload import DownloadReport
from research_hub.summarize import SummaryReport
from research_hub.vault.frontmatter_dedupe import DedupeResult
from research_hub.vault.hub_backlink_migrate import HubMigrationResult
from research_hub.vault.tag_migrate import TagMigrationResult


def _write_json(path: Path, payload) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    root = tmp_path / "vault"
    raw = root / "raw"
    hub = root / "hub"
    research_hub_dir = root / ".research_hub"
    logs = research_hub_dir / "logs"
    for path in (raw / "alpha", raw / "beta", hub, logs):
        path.mkdir(parents=True, exist_ok=True)

    clusters_file = research_hub_dir / "clusters.yaml"
    _write_json(
        clusters_file,
        {
            "clusters": {
                "alpha": {
                    "name": "Alpha",
                    "first_query": "alpha topic",
                    "obsidian_subfolder": "alpha",
                    "zotero_collection_key": "ZA1",
                },
                "beta": {
                    "name": "Beta",
                    "first_query": "beta topic",
                    "obsidian_subfolder": "beta",
                    "zotero_collection_key": "ZB1",
                },
            }
        },
    )
    _write_json(research_hub_dir / "dedup_index.json", {})
    cfg_obj = SimpleNamespace(
        root=root,
        raw=raw,
        hub=hub,
        logs=logs,
        research_hub_dir=research_hub_dir,
        clusters_file=clusters_file,
    )
    shared_get_config = lambda: cfg_obj
    # Satisfy require_config()'s early-exit check: it calls _resolve_config_path()
    # before get_config(), and raises SystemExit if neither a config file nor
    # RESEARCH_HUB_ROOT is found.  Setting the env var to the tmp vault dir makes
    # require_config() pass through to get_config() without reading a real config file.
    monkeypatch.setenv("RESEARCH_HUB_ROOT", str(root))
    monkeypatch.setattr(cli, "get_config", shared_get_config, raising=False)
    # Patch in config.py's own namespace so require_config() → get_config() returns
    # cfg_obj on all call sites (cli.py + any module that imports get_config directly).
    monkeypatch.setattr("research_hub.config.get_config", shared_get_config)
    return cfg_obj


def _case_auto(cfg, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "research_hub.auto.auto_pipeline",
        lambda **_kwargs: AutoReport(
            cluster_slug="alpha",
            cluster_created=True,
            steps=[AutoStepResult(name="search", ok=True, detail="stub")],
            papers_ingested=3,
        ),
    )
    return ["auto", "agent systems", "--no-show", "--json"], "auto"


def _case_doctor(cfg, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "research_hub.doctor.run_doctor",
        lambda *, strict=False: [CheckResult("config", "OK", f"strict={strict}")],
    )
    return ["doctor", "--json"], "doctor"


def _case_crystal_emit(cfg, tmp_path: Path, monkeypatch):
    monkeypatch.setattr("research_hub.crystal.emit_crystal_prompt", lambda *_a, **_k: "CRYSTAL PROMPT")
    return ["crystal", "emit", "--cluster", "alpha", "--json"], "crystal emit"


def _case_crystal_apply(cfg, tmp_path: Path, monkeypatch):
    scored = _write_json(tmp_path / "scored.json", {"generator": "test", "crystals": []})
    monkeypatch.setattr(
        "research_hub.crystal.apply_crystals",
        lambda *_a, **_k: CrystalApplyResult(cluster_slug="alpha", written=["what-is-this-field"]),
    )
    return ["crystal", "apply", "--cluster", "alpha", "--scored", str(scored), "--json"], "crystal apply"


def _case_summarize(cfg, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "research_hub.summarize.summarize_cluster",
        lambda *_a, **_k: SummaryReport(cluster_slug="alpha", ok=True, cli_used="codex"),
    )
    return ["summarize", "--cluster", "alpha", "--json"], "summarize"


def _case_fit_emit(cfg, tmp_path: Path, monkeypatch):
    candidates = _write_json(tmp_path / "candidates.json", [{"title": "Paper"}])
    monkeypatch.setattr("research_hub.fit_check.emit_prompt", lambda *_a, **_k: "FIT PROMPT")
    return [
        "fit-check",
        "emit",
        "--cluster",
        "alpha",
        "--candidates",
        str(candidates),
        "--json",
    ], "fit-check emit"


def _case_fit_apply(cfg, tmp_path: Path, monkeypatch):
    candidates = _write_json(tmp_path / "candidates.json", [{"title": "Paper"}])
    scored = _write_json(tmp_path / "scored.json", {"scores": []})
    monkeypatch.setattr(
        "research_hub.fit_check.apply_scores",
        lambda *_a, **_k: FitCheckReport(
            cluster_slug="alpha",
            threshold=3,
            candidates_in=1,
            accepted=[FitCheckResult(doi="10.1/a", title="Paper", score=4, reason="on topic", kept=True)],
            rejected=[],
        ),
    )
    return [
        "fit-check",
        "apply",
        "--cluster",
        "alpha",
        "--candidates",
        str(candidates),
        "--scored",
        str(scored),
        "--json",
    ], "fit-check apply"


def _case_bases_emit(cfg, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "research_hub.obsidian_bases.write_cluster_base",
        lambda **_kwargs: (cfg.hub / "alpha" / "alpha.base", True),
    )
    return ["bases", "emit", "--cluster", "alpha", "--json"], "bases emit"


def _case_vault_rebuild(cfg, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "research_hub.vault.hub_overview.populate_all_overviews",
        lambda *_a, **_k: [("alpha", cfg.hub / "alpha" / "00_overview.md")],
    )
    return ["vault", "rebuild-overviews", "--cluster", "alpha", "--json"], "vault rebuild-overviews"


def _case_vault_tag_migrate(cfg, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "research_hub.vault.tag_migrate.migrate_all",
        lambda *_a, **_k: [
            TagMigrationResult(path=cfg.raw / "alpha" / "paper.md", action="added", topic_tag="topic:alpha")
        ],
    )
    return ["vault", "tag-migrate", "--cluster", "alpha", "--json"], "vault tag-migrate"


def _case_vault_hub_backlink(cfg, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "research_hub.vault.hub_backlink_migrate.migrate_all",
        lambda *_a, **_k: [HubMigrationResult(path=cfg.raw / "alpha" / "paper.md", action="added")],
    )
    return ["vault", "hub-backlink-migrate", "--cluster", "alpha", "--json"], "vault hub-backlink-migrate"


def _case_vault_summarize_status(cfg, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "research_hub.vault.summarize_migrate.migrate_existing_to_pending_status",
        lambda *_a, **_k: [(cfg.raw / "alpha" / "paper.md", "pending")],
    )
    return ["vault", "summarize-status-migrate", "--cluster", "alpha", "--json"], "vault summarize-status-migrate"


def _case_vault_cleanup_frontmatter(cfg, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "research_hub.vault.frontmatter_dedupe.migrate_all",
        lambda *_a, **_k: [
            DedupeResult(
                path=cfg.raw / "alpha" / "paper.md",
                action="deduped",
                fields_deduped=["tags"],
                before={"tags": 2},
                after={"tags": 1},
            )
        ],
    )
    return ["vault", "cleanup-frontmatter", "--cluster", "alpha", "--json"], "vault cleanup-frontmatter"


def _case_notebooklm_download(cfg, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(cli, "_preflight_nlm_session", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "research_hub.notebooklm.upload.download_briefing_for_cluster",
        lambda *_a, **_k: DownloadReport(
            cluster_slug="alpha",
            notebook_name="Alpha notebook",
            artifact_path=cfg.hub / "alpha" / "notebooklm-brief.md",
            char_count=1234,
            titles=["Brief title"],
        ),
    )
    return ["notebooklm", "download", "--cluster", "alpha", "--json"], "notebooklm download"


def _case_clusters_audit(cfg, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(cli, "_load_zotero_if_configured", lambda: object())
    monkeypatch.setattr(
        "research_hub.doctor.check_cluster_zotero_drift",
        lambda *_a, **_k: [CheckResult("cluster/zotero_drift", "OK", "clean")],
    )
    monkeypatch.setattr(
        "research_hub.doctor.check_cluster_test_pattern",
        lambda *_a, **_k: CheckResult("cluster/test_pattern", "OK", "clean"),
    )
    monkeypatch.setattr(
        "research_hub.doctor.check_cluster_collection_collision",
        lambda *_a, **_k: CheckResult("cluster/collision", "OK", "clean"),
    )
    monkeypatch.setattr(
        "research_hub.doctor.check_manifest_orphan_cluster",
        lambda *_a, **_k: CheckResult("manifest/orphan_cluster", "OK", "clean"),
    )
    monkeypatch.setattr(
        "research_hub.vault.sync.compute_sync_status",
        lambda *_a, **_k: SimpleNamespace(obsidian_count=2, zotero_count=2, in_both=2),
    )
    return ["clusters", "audit", "--cluster", "alpha", "--json"], "clusters audit"


def _case_dedup_compact(cfg, tmp_path: Path, monkeypatch):
    return ["dedup", "compact", "--json"], "dedup compact"


def _case_dashboard_markdown_summary(cfg, tmp_path: Path, monkeypatch):
    (cfg.raw / "alpha" / "paper.md").write_text(
        '---\ntitle: "Paper"\nstatus: unread\nsummarize_status: pending\n---\n# Paper\n',
        encoding="utf-8",
    )
    return ["dashboard", "--markdown-summary", "--json"], "dashboard"


def _case_paper_retype(cfg, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "research_hub.paper.retype_paper",
        lambda *_a, **_k: {
            "mode": "dry_run",
            "slug": "paper-one",
            "from_type": "journalArticle",
            "to_type": "report",
            "old_zotero_key": "ZA1",
            "new_zotero_key": "",
            "fields_copied": ["title"],
            "fields_dropped": [],
            "errors": [],
        },
    )
    return ["paper", "retype", "--slug", "paper-one", "--to-type", "report", "--json"], "paper retype"


def _case_paper_bulk_relabel(cfg, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "research_hub.paper.bulk_relabel",
        lambda *_a, **_k: {
            "mode": "dry_run",
            "from": "deprecated",
            "to": "archived",
            "cluster": "alpha",
            "changed": [{"slug": "paper-one", "cluster": "alpha"}],
            "zotero_updated": [],
            "zotero_errors": [],
        },
    )
    return [
        "paper",
        "bulk-relabel",
        "--from",
        "deprecated",
        "--to",
        "archived",
        "--cluster",
        "alpha",
        "--json",
    ], "paper bulk-relabel"


def _case_paper_bulk_move(cfg, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "research_hub.paper.bulk_move",
        lambda *_a, **_k: {
            "mode": "dry_run",
            "to_cluster": "beta",
            "would_move": [{"slug": "paper-one", "from_cluster": "alpha", "to_cluster": "beta"}],
            "moved": [],
            "missing": [],
            "skipped": [],
            "zotero_updated": [],
            "zotero_errors": [],
        },
    )
    return [
        "paper",
        "bulk-move",
        "--slugs",
        "paper-one",
        "--to-cluster",
        "beta",
        "--json",
    ], "paper bulk-move"


def _case_paper_bulk_delete(cfg, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "research_hub.paper.bulk_delete_by_tag",
        lambda *_a, **_k: {
            "mode": "dry_run",
            "tag": "deprecated",
            "would_delete": [{"slug": "paper-one", "cluster": "alpha"}],
            "deleted": [],
            "zotero_trashed": [],
            "zotero_errors": [],
        },
    )
    return ["paper", "bulk-delete", "--by-tag", "deprecated", "--json"], "paper bulk-delete"


def _case_ingest(cfg, tmp_path: Path, monkeypatch):
    def _fake_run_pipeline(**_kwargs):
        _write_json(
            cfg.logs / "pipeline_output.json",
            {"papers": [{"slug": "paper-one", "title": "Paper One"}], "obsidian_results": []},
        )
        return 0

    monkeypatch.setattr(cli, "run_pipeline", _fake_run_pipeline)
    return ["ingest", "--cluster", "alpha", "--json"], "ingest"


def _case_import_folder(cfg, tmp_path: Path, monkeypatch):
    source = tmp_path / "import-folder"
    source.mkdir(parents=True, exist_ok=True)
    (source / "paper.md").write_text("# Imported", encoding="utf-8")
    monkeypatch.setattr(
        "research_hub.importer.import_folder",
        lambda *_a, **_k: ImportReport(
            folder=source,
            cluster_slug="alpha",
            entries=[ImportEntry(path=source / "paper.md", slug="paper", status="imported")],
            dry_run=False,
        ),
    )
    return ["import-folder", str(source), "--cluster", "alpha", "--json"], "import-folder"


CASES = [
    pytest.param(_case_auto, id="auto"),
    pytest.param(_case_doctor, id="doctor"),
    pytest.param(_case_crystal_emit, id="crystal-emit"),
    pytest.param(_case_crystal_apply, id="crystal-apply"),
    pytest.param(_case_summarize, id="summarize"),
    pytest.param(_case_fit_emit, id="fit-check-emit"),
    pytest.param(_case_fit_apply, id="fit-check-apply"),
    pytest.param(_case_bases_emit, id="bases-emit"),
    pytest.param(_case_vault_rebuild, id="vault-rebuild-overviews"),
    pytest.param(_case_vault_tag_migrate, id="vault-tag-migrate"),
    pytest.param(_case_vault_hub_backlink, id="vault-hub-backlink-migrate"),
    pytest.param(_case_vault_summarize_status, id="vault-summarize-status-migrate"),
    pytest.param(_case_vault_cleanup_frontmatter, id="vault-cleanup-frontmatter"),
    pytest.param(_case_notebooklm_download, id="notebooklm-download"),
    pytest.param(_case_clusters_audit, id="clusters-audit"),
    pytest.param(_case_dedup_compact, id="dedup-compact"),
    pytest.param(_case_dashboard_markdown_summary, id="dashboard-markdown-summary"),
    pytest.param(_case_paper_retype, id="paper-retype"),
    pytest.param(_case_paper_bulk_relabel, id="paper-bulk-relabel"),
    pytest.param(_case_paper_bulk_move, id="paper-bulk-move"),
    pytest.param(_case_paper_bulk_delete, id="paper-bulk-delete"),
    pytest.param(_case_ingest, id="ingest"),
    pytest.param(_case_import_folder, id="import-folder"),
]


@pytest.mark.parametrize("case", CASES)
def test_cli_json_output_cases(case, cfg, tmp_path: Path, monkeypatch, capsys):
    argv, expected_command = case(cfg, tmp_path, monkeypatch)

    rc = cli.main(argv)

    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out)
    assert {"ok", "command", "version", "report"} <= set(payload)
    assert payload["ok"] is True
    assert payload["command"] == expected_command
    assert isinstance(payload["version"], str) and payload["version"]
    assert isinstance(payload["report"], dict)
