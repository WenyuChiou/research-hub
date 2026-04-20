"""v0.46 — research-hub tidy tests."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def _fake_cfg(tmp_path):
    cfg = MagicMock(
        research_hub_dir=tmp_path / ".research_hub",
        hub=tmp_path / "hub",
        raw=tmp_path / "raw",
        clusters_file=tmp_path / "clusters.yaml",
    )
    cfg.research_hub_dir.mkdir()
    (tmp_path / "raw").mkdir()
    return cfg


def _stub_all(monkeypatch, tmp_path):
    cfg = _fake_cfg(tmp_path)
    monkeypatch.setattr("research_hub.config.get_config", lambda: cfg)
    # v0.49.2: matches the real API (run_doctor takes no args; autofix is separate).
    monkeypatch.setattr(
        "research_hub.doctor.run_doctor",
        lambda: [MagicMock(status="OK"), MagicMock(status="INFO")],
    )
    monkeypatch.setattr(
        "research_hub.vault_autofix.run_autofix",
        lambda c: {"topic_cluster": 0, "ingested_at": 0, "doi_derived": 0, "skipped_no_cluster": 0},
    )
    fake_idx = MagicMock(doi_to_hits={"a": [], "b": []}, title_to_hits={"X": [], "Y": [], "Z": []})
    fake_idx.rebuild_from_obsidian = MagicMock(return_value=None)
    fake_idx.save = MagicMock(return_value=None)
    monkeypatch.setattr("research_hub.dedup.DedupIndex.load", classmethod(lambda cls, p: fake_idx))
    monkeypatch.setattr(
        "research_hub.clusters.ClusterRegistry",
        lambda *a, **kw: MagicMock(list=lambda: []),
    )
    monkeypatch.setattr(
        "research_hub.obsidian_bases.write_cluster_base",
        lambda **kw: (None, True),
    )
    fake_report = MagicMock(
        total_bytes=1234, bundles=[], debug_logs=[], artifacts=[]
    )
    monkeypatch.setattr(
        "research_hub.cleanup.collect_garbage", lambda cfg, **kw: fake_report
    )
    monkeypatch.setattr("research_hub.cleanup.format_bytes", lambda n: "1.2 KB")
    return cfg


def test_tidy_signatures_match_real_api():
    """v0.49.2 regression: tidy.py must call doctor/dedup with their real signatures.

    The original v0.46 release passed `run_doctor(autofix=True)` and
    `build_from_obsidian(cfg)` even though both signatures rejected those
    arguments. Mocked tests didn't catch it because the mocks accepted
    anything. This test introspects the real signatures so the tidy module
    has to keep matching them.
    """
    import inspect

    from research_hub.doctor import run_doctor
    from research_hub.dedup import DedupIndex
    from research_hub.vault_autofix import run_autofix

    # run_doctor should be no-arg
    assert inspect.signature(run_doctor).parameters == {}, (
        "run_doctor() must remain no-arg; tidy uses it that way"
    )
    # run_autofix should accept a cfg
    assert "cfg" in inspect.signature(run_autofix).parameters

    # DedupIndex must expose .load, .rebuild_from_obsidian, .save and the
    # doi_to_hits / title_to_hits dicts that tidy iterates.
    assert hasattr(DedupIndex, "load")
    assert hasattr(DedupIndex, "rebuild_from_obsidian")
    assert hasattr(DedupIndex, "save")
    fields = {f.name for f in DedupIndex.__dataclass_fields__.values()}
    assert {"doi_to_hits", "title_to_hits"} <= fields


def test_tidy_invokes_all_four_substeps(monkeypatch, tmp_path):
    from research_hub.tidy import run_tidy

    _stub_all(monkeypatch, tmp_path)
    report = run_tidy(print_progress=False)
    step_names = [s.name for s in report.steps]
    assert step_names == ["doctor", "dedup", "bases", "cleanup"]
    assert all(s.ok for s in report.steps)


def test_tidy_doctor_failure_is_non_fatal(monkeypatch, tmp_path):
    from research_hub.tidy import run_tidy

    _stub_all(monkeypatch, tmp_path)

    def _doctor_boom(autofix=False):
        raise RuntimeError("doctor exploded")

    monkeypatch.setattr("research_hub.doctor.run_doctor", _doctor_boom)
    report = run_tidy(print_progress=False)
    doctor_step = next(s for s in report.steps if s.name == "doctor")
    assert not doctor_step.ok
    other_steps = [s for s in report.steps if s.name != "doctor"]
    assert all(s.ok for s in other_steps)
    assert len(report.steps) == 4


def test_tidy_apply_cleanup_passes_through(monkeypatch, tmp_path):
    from research_hub.tidy import run_tidy

    _stub_all(monkeypatch, tmp_path)
    captured = {}

    def _gc(cfg, **kwargs):
        captured.update(kwargs)
        return MagicMock(total_bytes=0, bundles=[], debug_logs=[], artifacts=[])

    monkeypatch.setattr("research_hub.cleanup.collect_garbage", _gc)
    run_tidy(apply_cleanup=True, print_progress=False)
    assert captured["apply"] is True


def test_cli_tidy_dispatch(monkeypatch):
    from research_hub import cli as cli_module
    from research_hub.tidy import TidyReport, TidyStep

    called = {"applied": None}

    def _fake_tidy(*, apply_cleanup, print_progress):
        called["applied"] = apply_cleanup
        return TidyReport(
            steps=[TidyStep(name="doctor", ok=True)], total_duration_sec=1.0
        )

    monkeypatch.setattr("research_hub.tidy.run_tidy", _fake_tidy)
    rc = cli_module.main(["tidy", "--apply-cleanup"])
    assert rc == 0
    assert called["applied"] is True
