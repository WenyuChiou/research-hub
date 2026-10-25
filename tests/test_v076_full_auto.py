from __future__ import annotations

from types import SimpleNamespace
from research_hub.summarize import SummaryApplyResult

from research_hub.auto import auto_pipeline


def _make_cfg(tmp_path, slug: str = "test-topic"):
    raw = tmp_path / "raw"
    cluster_dir = raw / slug
    cluster_dir.mkdir(parents=True)
    (cluster_dir / "paper.md").write_text("paper", encoding="utf-8")
    research_hub_dir = tmp_path / ".research_hub"
    research_hub_dir.mkdir()
    return SimpleNamespace(
        root=tmp_path,
        raw=raw,
        research_hub_dir=research_hub_dir,
        clusters_file=research_hub_dir / "clusters.yaml",
    )


def _patch_auto_success(monkeypatch, tmp_path, slug: str = "test-topic"):
    from research_hub import auto as auto_mod

    cfg = _make_cfg(tmp_path, slug=slug)
    monkeypatch.setattr(auto_mod, "get_config", lambda: cfg)

    class _Registry:
        def __init__(self, *args, **kwargs):
            del args, kwargs

        def get(self, asked_slug):
            return SimpleNamespace(slug=asked_slug, name=asked_slug, zotero_collection_key="EXISTING")

        def create(self, **kwargs):
            return SimpleNamespace(
                slug=kwargs["slug"],
                name=kwargs.get("name", kwargs["slug"]),
                zotero_collection_key="EXISTING",
            )

    monkeypatch.setattr(auto_mod, "ClusterRegistry", _Registry)
    monkeypatch.setattr(auto_mod, "_run_search", lambda topic, **kwargs: [{"title": topic, "doi": "10.1/a"}])
    monkeypatch.setattr(auto_mod, "run_pipeline", lambda **kwargs: 0)
    return cfg


def test_auto_cli_full_auto_enables_flags(monkeypatch):
    from research_hub import cli

    captured = {}
    monkeypatch.setattr(cli, "_auto", lambda **kwargs: captured.update(kwargs) or 0)

    assert cli.main(["auto", "topic", "--full-auto"]) == 0
    assert captured["with_pdfs"] is True
    assert captured["with_summary"] is True
    assert captured["do_crystals"] is True


def test_auto_pipeline_runs_summary_when_enabled(monkeypatch, tmp_path):
    """v0.88.6: --with-summary drives BOTH layers — summarize_cluster
    fills ## Summary callout, paper_summarize.summarize_pending fills
    Key Findings / Methodology / Relevance. Both must be invoked."""
    _patch_auto_success(monkeypatch, tmp_path)

    called = {}

    def fake_summarize(cfg, cluster_slug, *, llm_cli=None, apply=False, **kwargs):
        called["cfg"] = cfg
        called["cluster_slug"] = cluster_slug
        called["llm_cli"] = llm_cli
        called["apply"] = apply
        return SimpleNamespace(
            ok=True,
            cli_used=llm_cli,
            apply_result=SummaryApplyResult("test-cluster", applied=["paper"], errors=[]),
        )

    def fake_summarize_pending(cfg, *, cluster_slug_filter=None, backend="claude", **kwargs):
        called["paper_summarize_cluster"] = cluster_slug_filter
        called["paper_summarize_backend"] = backend
        # v0.88.8 regression guard: SummarizeResult uses `.action` not
        # `.status`. The earlier v0.88.6 test set `status="done"` on the
        # SimpleNamespace which masked the production attribute typo —
        # both the test fake and the production code agreed on the wrong
        # name, so layer-2 silently logged "0 done" in real runs.
        return [SimpleNamespace(action="done"), SimpleNamespace(action="done")]

    monkeypatch.setattr("research_hub.auto.detect_llm_cli", lambda: "codex")
    monkeypatch.setattr("research_hub.summarize.summarize_cluster", fake_summarize)
    monkeypatch.setattr(
        "research_hub.paper_summarize.summarize_pending", fake_summarize_pending
    )

    report = auto_pipeline(
        "test topic",
        do_nlm=False,
        do_fit_check=False,
        do_cluster_overview=False,
        with_summary=True,
        append=True,
        print_progress=False,
    )

    assert report.ok
    # Layer 1 wiring
    assert called["cluster_slug"] == "test-topic"
    assert called["llm_cli"] == "codex"
    assert called["apply"] is True
    # Layer 2 (v0.88.6) — paper_summarize.summarize_pending must also fire
    assert called["paper_summarize_cluster"] == "test-topic"
    assert called["paper_summarize_backend"] == "codex"

    summary_step = next(step for step in report.steps if step.name == "summary")
    assert summary_step.ok is True
    # Reports both layers in detail
    assert "layer-1" in summary_step.detail
    assert "layer-2" in summary_step.detail
    assert "1 ok" in summary_step.detail  # layer-1
    assert "2 done" in summary_step.detail  # layer-2


def test_summary_step_counts_real_summarize_result_objects(monkeypatch, tmp_path):
    """v0.88.8 regression guard: layer-2 attribute is `.action`, not
    `.status`. The v0.88.6 ship used `.status` which silently logged
    "0 done" even when paper-summarize completed every note. Use the
    REAL `SummarizeResult` dataclass (not SimpleNamespace duck-typing)
    so any future rename of the field would fail this test."""
    _patch_auto_success(monkeypatch, tmp_path)

    from research_hub.paper_summarize import SummarizeResult

    monkeypatch.setattr("research_hub.auto.detect_llm_cli", lambda: "codex")
    monkeypatch.setattr(
        "research_hub.summarize.summarize_cluster",
        lambda *_a, **_k: SimpleNamespace(
            ok=True,
            cli_used="codex",
            apply_result=SummaryApplyResult("test-cluster", applied=["paper"], errors=[]),
        ),
    )
    monkeypatch.setattr(
        "research_hub.paper_summarize.summarize_pending",
        lambda *_a, **_k: [
            SummarizeResult(tmp_path / "p1.md", "done", backend="codex"),
            SummarizeResult(tmp_path / "p2.md", "done", backend="codex"),
            SummarizeResult(tmp_path / "p3.md", "failed_no_abstract", backend="codex"),
        ],
    )

    report = auto_pipeline(
        "test topic",
        do_nlm=False,
        do_fit_check=False,
        do_cluster_overview=False,
        with_summary=True,
        append=True,
        print_progress=False,
    )

    summary_step = next(step for step in report.steps if step.name == "summary")
    # 2 done + 1 failed_no_abstract should both surface in the log line.
    assert "2 done" in summary_step.detail
    assert "1 failed_no_abstract" in summary_step.detail


def test_auto_pipeline_skips_summary_when_no_llm_cli(monkeypatch, tmp_path):
    _patch_auto_success(monkeypatch, tmp_path)
    monkeypatch.setattr("research_hub.auto.detect_llm_cli", lambda: None)
    monkeypatch.setattr(
        "research_hub.summarize.summarize_cluster",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not be called")),
    )

    report = auto_pipeline(
        "test topic",
        do_nlm=False,
        do_fit_check=False,
        do_cluster_overview=False,
        with_summary=True,
        append=True,
        print_progress=False,
    )

    assert report.ok
    summary_step = next(step for step in report.steps if step.name == "summary")
    assert summary_step.ok is True
    assert "skipped" in summary_step.detail


def test_auto_pipeline_dry_run_mentions_summary(monkeypatch, tmp_path, capsys):
    _patch_auto_success(monkeypatch, tmp_path)
    monkeypatch.setattr("research_hub.auto.detect_llm_cli", lambda: "codex")

    auto_pipeline(
        "test topic",
        dry_run=True,
        do_nlm=False,
        do_fit_check=False,
        do_cluster_overview=False,
        with_summary=True,
        append=True,
        print_progress=True,
    )

    out = capsys.readouterr().out
    assert "summarize per-paper notes via LLM CLI (codex)" in out

