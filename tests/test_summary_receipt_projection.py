"""Confirmed writes survive unavailable receipt projection; all I/O is synthetic."""
import contextlib
import io
import json
import sqlite3
import tempfile
from collections import Counter
from pathlib import Path
from threading import Lock
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from research_hub import summarize
from research_hub.summary_journal import JournalError, SummaryJournal


ENTRY = {
    "paper_slug": "paper",
    "key_findings": ["Synthetic finding"],
    "methodology": "Synthetic method",
    "relevance": "Synthetic relevance",
}


class FakeZotero:
    library_id = "123"
    library_type = "user"

    def __init__(self):
        self.reads = 0
        self.writes = 0

    def children(self, key):
        self.reads += 1
        return []

    def everything(self, children):
        return children

    def item_template(self, kind):
        return {"itemType": kind}

    def create_items(self, items):
        self.writes += 1
        return {"successful": {"0": {"key": "SYNTHNOTE"}}}


@pytest.fixture
def synthetic():
    # pytest's tmpdir plugin is deliberately disabled by this repository.
    temp_parent = Path.cwd() / ".pytest-work"
    temp_parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=temp_parent) as directory:
        root = Path(directory)
        cfg = SimpleNamespace(
            root=root, raw=root / "raw", research_hub_dir=root / ".research_hub",
            zotero_library_id="123", zotero_library_type="user",
        )
        note = cfg.raw / "cluster" / "paper.md"
        note.parent.mkdir(parents=True)
        note.write_text(
            "---\ntitle: Synthetic\nzotero-key: PARENT01\n---\n\n"
            "## Abstract\n\nSelected synthetic abstract.\n\n"
            "## Key Findings\n\n> [!success]\n> [TODO]\n^findings\n\n"
            "## Personal notes\n\nSynthetic preserved text.\n",
            encoding="utf-8",
        )
        yield SimpleNamespace(cfg=cfg, root=root, note=note, original=note.read_bytes())


def apply(fixture, zot, **kwargs):
    return summarize.apply_summaries(fixture.cfg, "cluster", [ENTRY], zot=zot, **kwargs)


@pytest.mark.parametrize("failure", [
    JournalError("synthetic receipt guard failure", "unsafe_path"),
    OSError("synthetic receipt read failure"),
    sqlite3.OperationalError("synthetic receipt database failure"),
])
def test_post_ack_projection_failure_preserves_confirmed_writes(synthetic, failure):
    zot = FakeZotero()
    with patch("research_hub.summary_apply_journal._receipt", side_effect=failure), patch.object(
        SummaryJournal, "recover", autospec=True, side_effect=SummaryJournal.recover,
    ) as recover:
        result = apply(synthetic, zot, provenance="legacy_cli_explicit_apply")
    assert result.errors == []
    assert result.applied == ["paper"]
    assert (result.obsidian_writes, result.zotero_writes) == (1, 1)
    assert zot.writes == 1
    assert synthetic.note.read_bytes() != synthetic.original
    recover.assert_not_called()
    receipt = result.to_dict()["receipts"][0]
    body = SummaryJournal(synthetic.root).get(receipt["operation_id"])
    assert {sink["state"] for sink in body["sinks"].values()} == {"confirmed"}
    assert receipt["status"] == "receipt_unavailable"
    assert receipt["write_outcome"] == "confirmed"
    assert set(receipt["confirmed_sinks"]) == {"local", "zotero"}
    assert receipt["current_attempt_dispatched"] is True
    assert "observations" not in receipt  # Missing projection is not invented.
    assert "authorization" not in receipt
    assert any("receipt projection unavailable" in item for item in result.warnings)
    line = next(summarize.receipt_lines(result.receipts))
    assert "receipt_unavailable" in line
    assert "local=confirmed" in line and "zotero=confirmed" in line


def test_confirmed_replay_with_unavailable_projection_keeps_identity_without_io(synthetic):
    first_zot = FakeZotero()
    first = apply(synthetic, first_zot, provenance="legacy_cli_explicit_apply")
    operation_id = first.receipts[0]["operation_id"]
    after = synthetic.note.read_bytes()
    zot = FakeZotero()
    with patch("research_hub.summary_apply_journal._receipt", side_effect=OSError("synthetic projection failure")), patch.object(
        summarize, "_write_note_text", side_effect=AssertionError("no repeated local write"),
    ), patch.object(SummaryJournal, "recover", side_effect=AssertionError("confirmed operation needs no recovery")):
        result = apply(synthetic, zot, provenance="legacy_mcp_apply_invocation")
    assert result.errors == []
    assert result.applied == [] and len(result.skipped) == 1
    assert (result.obsidian_writes, result.zotero_writes) == (0, 0)
    assert (zot.reads, zot.writes) == (0, 0)
    assert synthetic.note.read_bytes() == after
    receipt = result.receipts[0]
    assert receipt["operation_id"] == operation_id
    assert receipt["write_outcome"] == "confirmed"
    assert receipt["current_attempt_dispatched"] is False
    assert result.warnings
    # Reading the full receipt later retains the original invocation authority.
    final = apply(synthetic, zot, provenance="legacy_mcp_apply_invocation")
    assert final.receipts[0]["operation_id"] == operation_id
    assert final.receipts[0]["authorization"]["kind"] == "legacy_cli_explicit_apply"
    assert len(SummaryJournal(synthetic.root).list()) == 1
    assert (zot.reads, zot.writes) == (0, 0)


def test_local_only_projection_failure_counts_only_the_confirmed_local_sink(synthetic):
    zot = FakeZotero()
    with patch("research_hub.summary_apply_journal._receipt", side_effect=OSError("synthetic projection failure")):
        result = apply(synthetic, zot, write_zotero=False)
    assert result.errors == [] and result.applied == ["paper"]
    assert (result.obsidian_writes, result.zotero_writes) == (1, 0)
    assert result.receipts[0]["confirmed_sinks"] == ["local"]
    assert (zot.reads, zot.writes) == (0, 0)


def test_remote_only_projection_failure_counts_only_remote_and_does_not_replay(synthetic):
    zot = FakeZotero()
    with patch("research_hub.summary_apply_journal._receipt", side_effect=OSError("synthetic projection failure")):
        first = apply(synthetic, zot, write_obsidian=False)
        replay = apply(synthetic, zot, write_obsidian=False)
    assert first.errors == [] and first.applied == ["paper"]
    assert (first.obsidian_writes, first.zotero_writes) == (0, 1)
    assert first.receipts[0]["confirmed_sinks"] == ["zotero"]
    assert first.receipts[0]["current_attempt_dispatched"] is True
    assert synthetic.note.read_bytes() == synthetic.original
    assert replay.errors == [] and replay.applied == [] and len(replay.skipped) == 1
    assert (replay.obsidian_writes, replay.zotero_writes) == (0, 0)
    assert replay.receipts[0]["operation_id"] == first.receipts[0]["operation_id"]
    assert replay.receipts[0]["current_attempt_dispatched"] is False
    assert zot.writes == 1 and zot.reads == 1
    assert set(SummaryJournal(synthetic.root).get(first.receipts[0]["operation_id"])["sinks"]) == {"zotero"}


def test_existing_ownership_warning_survives_projection_warning(synthetic):
    class WithUnmarkedNote(FakeZotero):
        def children(self, key):
            self.reads += 1
            return [{"data": {"key": "UNMARKED", "itemType": "note", "parentItem": key,
                              "version": 1, "tags": [], "note": "Synthetic legacy note"}}]

    zot = WithUnmarkedNote()
    with patch("research_hub.summary_apply_journal._receipt", side_effect=OSError("synthetic projection failure")):
        result = apply(synthetic, zot)
    assert result.errors == [] and result.applied == ["paper"]
    assert (result.obsidian_writes, result.zotero_writes) == (1, 1)
    assert zot.writes == 1
    assert len(result.warnings) == 1
    assert "preserved 1 unmarked note(s)" in result.warnings[0]
    assert "legacy duplicate may remain" in result.warnings[0]
    assert "receipt projection unavailable" in result.warnings[0]
    assert result.receipts[0]["write_outcome"] == "confirmed"


def test_mixed_concurrent_batch_keeps_confirmed_counts_and_uncertain_identity(synthetic):
    from research_hub import summary_apply_journal

    second_note = synthetic.note.with_name("other.md")
    second_note.write_bytes(synthetic.original.replace(b"PARENT01", b"PARENT02"))
    other_entry = {**ENTRY, "paper_slug": "other", "methodology": "Other synthetic method"}
    payload = [ENTRY, other_entry]

    class MixedZotero(FakeZotero):
        def __init__(self):
            super().__init__()
            self.by_parent = Counter()
            self.lock = Lock()

        def create_items(self, items):
            parent = items[0]["parentItem"]
            with self.lock:
                self.by_parent[parent] += 1
                self.writes += 1
            if parent == "PARENT02":
                raise TimeoutError("synthetic lost remote response")
            return {"successful": {"0": {"key": "SYNTHNOTE"}}}

    real_receipt = summary_apply_journal._receipt

    def project(journal, operation_id):
        body = journal.get(operation_id)
        if "PARENT01" in body["targets"]["zotero"]:
            assert {sink["state"] for sink in body["sinks"].values()} == {"confirmed"}
            raise OSError("synthetic confirmed receipt projection failure")
        return real_receipt(journal, operation_id)

    zot = MixedZotero()
    with patch.object(summary_apply_journal, "_receipt", side_effect=project):
        result = summarize.apply_summaries(synthetic.cfg, "cluster", payload, zot=zot)
    assert result.applied == ["paper"]
    assert len(result.errors) == 1 and result.errors[0].startswith("other:")
    assert "outcome unknown" in result.errors[0]
    assert (result.obsidian_writes, result.zotero_writes) == (1, 1)
    assert zot.by_parent == Counter({"PARENT01": 1, "PARENT02": 1})
    assert synthetic.note.read_bytes() != synthetic.original
    assert second_note.read_bytes() == synthetic.original.replace(b"PARENT01", b"PARENT02")
    assert len(result.warnings) == 1 and result.warnings[0].startswith("paper:")
    assert "receipt projection unavailable" in result.warnings[0]
    assert len(result.receipts) == 2
    confirmed = next(receipt for receipt in result.receipts if receipt.get("write_outcome") == "confirmed")
    uncertain = next(receipt for receipt in result.receipts if receipt.get("write_outcome") != "confirmed")
    assert confirmed["status"] == "receipt_unavailable"
    assert uncertain["sinks"]["zotero"]["state"] == "unknown"
    replay_zot = MixedZotero()
    replay = summarize.apply_summaries(synthetic.cfg, "cluster", payload, zot=replay_zot)
    assert replay.applied == [] and len(replay.skipped) == 1 and len(replay.errors) == 1
    assert (replay.obsidian_writes, replay.zotero_writes) == (0, 0)
    assert replay_zot.by_parent == Counter()
    assert {receipt["operation_id"] for receipt in replay.receipts} == {
        confirmed["operation_id"], uncertain["operation_id"],
    }


@pytest.mark.parametrize("failed_sink", ["zotero", "local"])
def test_incomplete_durable_ack_is_still_uncertain_and_cannot_replay(synthetic, failed_sink):
    acknowledge = SummaryJournal.acknowledge

    def fail(journal, operation_id, sink, token, outcome):
        if sink == failed_sink:
            raise sqlite3.OperationalError("synthetic acknowledgement persistence failure")
        return acknowledge(journal, operation_id, sink, token, outcome)

    zot = FakeZotero()
    with patch.object(SummaryJournal, "acknowledge", fail), patch(
        "research_hub.summary_apply_journal._receipt",
        side_effect=JournalError("synthetic receipt unavailable", "unsafe_path"),
    ):
        result = apply(synthetic, zot)
    assert result.errors and "reconciliation" in result.errors[0]
    assert result.applied == []
    assert (result.obsidian_writes, result.zotero_writes) == (0, 0)
    assert zot.writes == 1
    receipt = result.receipts[0]
    assert receipt.get("write_outcome") != "confirmed"
    assert "confirmed_sinks" not in receipt
    operation_id = receipt["operation_id"]
    if failed_sink == "local":
        assert SummaryJournal(synthetic.root).get(operation_id)["sinks"]["zotero"]["state"] == "confirmed"
    retry_zot = FakeZotero()
    retry = apply(synthetic, retry_zot)
    assert retry.errors and retry.receipts[0]["operation_id"] == operation_id
    assert (retry_zot.reads, retry_zot.writes) == (0, 0)


def test_predispatch_failure_with_unavailable_projection_does_not_claim_success(synthetic):
    zot = FakeZotero()
    with patch.object(SummaryJournal, "_commit", side_effect=sqlite3.OperationalError("synthetic predispatch failure")), patch(
        "research_hub.summary_apply_journal._receipt", side_effect=JournalError("synthetic receipt unavailable", "unsafe_path"),
    ):
        result = apply(synthetic, zot)
    assert result.errors and result.applied == []
    assert (result.obsidian_writes, result.zotero_writes) == (0, 0)
    assert (zot.reads, zot.writes) == (0, 0)
    assert synthetic.note.read_bytes() == synthetic.original
    assert result.receipts[0].get("write_outcome") != "confirmed"
    assert result.receipts[0]["current_attempt_dispatched"] is False


def test_aggregation_preserves_explicit_confirmed_facts_alongside_an_error(synthetic):
    outcome = summarize._PerPaperOutcome(
        slug="paper", applied=True, obsidian_written=True, zotero_written=True,
        error="synthetic later reporting error", warning="synthetic reporting warning",
    )
    zot = FakeZotero()
    with patch.object(summarize, "_apply_one_entry", return_value=outcome):
        result = apply(synthetic, zot)
    assert result.errors
    assert result.applied == ["paper"]
    assert (result.obsidian_writes, result.zotero_writes) == (1, 1)
    assert result.warnings == ["paper: synthetic reporting warning"]
    assert (zot.reads, zot.writes) == (0, 0)


def test_actual_cli_reports_projection_warning_with_success_and_confirmed_counts(synthetic):
    from research_hub import cli, llm_cli
    from research_hub.zotero import client

    zot = FakeZotero()
    stdout, stderr = io.StringIO(), io.StringIO()
    with patch.object(cli, "get_config", return_value=synthetic.cfg), patch.object(
        client, "get_client", return_value=zot,
    ), patch.object(llm_cli, "invoke_llm_cli", return_value=json.dumps({"summaries": [ENTRY]})) as model, patch(
        "research_hub.summary_apply_journal._receipt", side_effect=OSError("synthetic projection failure"),
    ), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        rc = cli.main(["summarize", "--cluster", "cluster", "--llm-cli", "synthetic", "--apply"])
    assert rc == 0
    model.assert_called_once()  # Mocked only; receipt failure must not regenerate.
    assert zot.writes == 1
    assert "applied: 1" in stdout.getvalue()
    assert "obsidian writes: 1, zotero writes: 1" in stdout.getvalue()
    assert "receipt_unavailable" in stdout.getvalue()
    assert "receipt projection unavailable" in stderr.getvalue()


def test_actual_mcp_apply_serializes_confirmed_facts_without_promoting_authority(synthetic):
    from research_hub import config, mcp_server
    from research_hub.zotero import client

    zot = FakeZotero()
    with patch.object(config, "get_config", return_value=synthetic.cfg), patch.object(
        client, "get_client", return_value=zot,
    ), patch("research_hub.summary_apply_journal._receipt", side_effect=OSError("synthetic projection failure")):
        result = mcp_server.apply_cluster_summaries("cluster", {"summaries": [ENTRY]})
    assert result["errors"] == [] and result["applied"] == ["paper"]
    assert (result["obsidian_writes"], result["zotero_writes"]) == (1, 1)
    assert result["receipts"][0]["write_outcome"] == "confirmed"
    assert result["warnings"]
    assert zot.writes == 1
    body = SummaryJournal(synthetic.root).get(result["receipts"][0]["operation_id"])
    assert body["authorization"]["kind"] == "legacy_mcp_apply_invocation"


def test_json_cli_exposes_confirmed_counts_and_projection_status(synthetic):
    from research_hub import cli_summarize, llm_cli
    from research_hub.zotero import client

    zot = FakeZotero()
    args = SimpleNamespace(cluster="cluster", llm_cli="synthetic", apply=True, no_zotero=False, no_obsidian=False)
    stdout = io.StringIO()
    with patch.object(client, "get_client", return_value=zot), patch.object(
        llm_cli, "invoke_llm_cli", return_value=json.dumps({"summaries": [ENTRY]}),
    ) as model, patch(
        "research_hub.summary_apply_journal._receipt", side_effect=OSError("synthetic projection failure"),
    ), contextlib.redirect_stdout(stdout):
        rc = cli_summarize._cmd_summarize(args, synthetic.cfg, emit_json=True)
    assert rc == 0
    model.assert_called_once()
    assert zot.writes == 1
    envelope = json.loads(stdout.getvalue())
    assert envelope["ok"] is True and envelope["command"] == "summarize"
    result = envelope["report"]["apply_result"]
    assert result["errors"] == [] and result["applied"] == ["paper"]
    assert (result["obsidian_writes"], result["zotero_writes"]) == (1, 1)
    assert result["receipts"][0]["status"] == "receipt_unavailable"
    assert result["receipts"][0]["write_outcome"] == "confirmed"
    assert result["warnings"]


def test_paper_resummarize_prints_projection_warning_on_confirmed_success(synthetic):
    from research_hub import cli_paper

    synthetic.cfg.clusters_file = synthetic.root / "clusters.yaml"
    cluster = SimpleNamespace(slug="cluster", obsidian_subfolder="cluster")
    result = summarize.SummaryApplyResult(
        "cluster", applied=["paper"], obsidian_writes=1, zotero_writes=1,
        warnings=["paper: receipt projection unavailable"],
        receipts=[{"operation_id": "synthetic-id", "version": 2,
                   "status": "receipt_unavailable", "write_outcome": "confirmed",
                   "confirmed_sinks": ["local", "zotero"]}],
    )
    report = summarize.SummaryReport("cluster", apply_result=result)
    stdout, stderr = io.StringIO(), io.StringIO()
    with patch.object(cli_paper, "get_config", return_value=synthetic.cfg), patch.object(
        cli_paper, "ClusterRegistry", return_value=SimpleNamespace(get=lambda slug: cluster),
    ), patch.object(cli_paper, "_summary_block_has_todo", return_value=True), patch.object(
        summarize, "summarize_cluster", return_value=report,
    ) as model_boundary, contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        rc = cli_paper._paper_resummarize("cluster", apply=True, llm_cli="synthetic")
    assert rc == 0
    model_boundary.assert_called_once()
    assert "receipt_unavailable" in stdout.getvalue()
    assert "obsidian writes: 1, zotero writes: 1" in stdout.getvalue()
    assert "receipt projection unavailable" in stderr.getvalue()


def test_auto_defers_secondary_writer_when_projection_is_unavailable(synthetic):
    from research_hub import auto, paper_summarize

    result = summarize.SummaryApplyResult(
        "cluster", applied=["paper"], obsidian_writes=1, zotero_writes=1,
        warnings=["paper: receipt projection unavailable"],
        receipts=[{"operation_id": "synthetic-id", "version": 2,
                   "status": "receipt_unavailable", "write_outcome": "confirmed",
                   "confirmed_sinks": ["local", "zotero"]}],
    )
    first_layer = summarize.SummaryReport("cluster", apply_result=result)
    auto_report = auto.AutoReport(cluster_slug="cluster", cluster_created=False)
    with patch.object(summarize, "summarize_cluster", return_value=first_layer) as first, patch.object(
        paper_summarize, "summarize_pending",
    ) as second:
        auto._run_summary_step(synthetic.cfg, "cluster", "synthetic", auto_report, 0, False)
    first.assert_called_once()
    second.assert_not_called()
    assert any("layer-1: 1 confirmed" in step.detail for step in auto_report.steps)
    assert any("layer-2 deferred: receipt projection unavailable" in step.detail for step in auto_report.steps)
