"""Synthetic-only ownership regressions; no credentials or live Zotero calls."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from research_hub.summarize import _write_zotero_child_note, apply_summaries

TAG = "research-hub:summary:v1"


def note(key, *, owned=False, parent="PARENT01", version=7):
    return {"key": key, "version": version, "data": {
        "key": key, "version": version, "itemType": "note",
        "parentItem": parent, "note": f"<p>Original {key} — handwritten 中文</p>",
        "tags": [{"tag": TAG}] if owned else [],
    }}


class FakeZotero:
    library_id = "SYNTHETIC"
    library_type = "user"
    def __init__(self, notes=(), *, later=()):
        self.notes = deepcopy(list(notes))
        self.later = deepcopy(list(later))
        self.updated = []
        self.created = []
        self.fail_update = None
        self.fail_create = None

    def children(self, parent):
        assert parent == "PARENT01"
        return deepcopy(self.notes)

    def everything(self, children):
        return children + deepcopy(self.later)

    def item_template(self, kind):
        return {"itemType": kind, "tags": []}

    def update_item(self, data):
        self.updated.append(deepcopy(data))
        if self.fail_update:
            raise self.fail_update
        return True

    def create_items(self, items):
        self.created.extend(deepcopy(items))
        if self.fail_create:
            raise self.fail_create
        return {"successful": {"0": {"key": "NEWNOTE1"}}}


def test_handwritten_first_note_is_not_selected_over_owned_second():
    zot = FakeZotero([note("HUMAN001"), note("HUB00001", owned=True)])
    before = deepcopy(zot.notes)
    _write_zotero_child_note(zot, "PARENT01", "<p>New summary</p>")
    assert [item["key"] for item in zot.updated] == ["HUB00001"]
    assert zot.updated[0]["version"] == 7
    assert zot.notes == before
    assert not zot.created


@pytest.mark.parametrize("html", ["<p>My own note</p>", "<h1>Summary</h1><p>Legacy Hub note</p>"])
def test_unmarked_notes_are_preserved_and_reported_when_creating_owned_note(html):
    old = note("UNMARKED")
    old["data"]["note"] = html
    zot = FakeZotero([old])
    warning = _write_zotero_child_note(zot, "PARENT01", "new")
    assert not zot.updated
    assert len(zot.created) == 1 and zot.created[0]["tags"] == [{"tag": TAG}]
    assert "preserved 1 unmarked" in warning
    assert "possible legacy" in warning
    assert zot.notes == [old]


def test_multiple_managed_notes_fail_closed_including_later_page():
    zot = FakeZotero([note("HUB00001", owned=True)], later=[note("HUB00002", owned=True)])
    with pytest.raises(RuntimeError, match="multiple"):
        _write_zotero_child_note(zot, "PARENT01", "new")
    assert not zot.updated and not zot.created


def test_empty_parent_creates_explicitly_owned_note():
    zot = FakeZotero()
    _write_zotero_child_note(zot, "PARENT01", "new")
    assert zot.created[0]["tags"] == [{"tag": TAG}]
    assert zot.created[0]["parentItem"] == "PARENT01"
    assert not zot.updated


@pytest.mark.parametrize("field,value", [("parentItem", "OTHER001"), ("key", ""), ("version", None), ("version", True)])
def test_invalid_owned_identity_or_version_never_writes(field, value):
    owned = note("HUB00001", owned=True)
    owned["data"][field] = value
    zot = FakeZotero([owned])
    with pytest.raises(RuntimeError):
        _write_zotero_child_note(zot, "PARENT01", "new")
    assert not zot.updated and not zot.created


def test_owned_update_failure_is_not_retried_or_replaced_by_create():
    zot = FakeZotero([note("HUB00001", owned=True)])
    zot.fail_update = RuntimeError("synthetic version conflict")
    with pytest.raises(RuntimeError, match="version conflict"):
        _write_zotero_child_note(zot, "PARENT01", "new")
    assert len(zot.updated) == 1
    assert not zot.created


def test_ownership_refusal_rolls_back_local_note_with_unchanged_result_fields(tmp_path):
    raw = tmp_path / "raw" / "cluster"
    raw.mkdir(parents=True)
    path = raw / "paper.md"
    original = '---\ntitle: Synthetic\nzotero-key: PARENT01\n---\n\n## Key Findings\n\n> [!success]\n> [TODO]\n^findings\n\n## Personal notes\n\nKeep 中文 and $x=1$.\n'
    path.write_text(original, encoding="utf-8")
    zot = FakeZotero([note("HUB00001", owned=True), note("HUB00002", owned=True)])
    result = apply_summaries(SimpleNamespace(raw=raw.parent), "cluster", [{
        "paper_slug": "paper", "key_findings": ["New finding"],
        "methodology": "Synthetic method", "relevance": "Synthetic relevance",
    }], zot=zot)
    assert result.applied == []
    assert result.obsidian_writes == result.zotero_writes == 0
    assert len(result.errors) == 1 and "multiple" in result.errors[0]
    assert path.read_text(encoding="utf-8") == original
    assert not zot.updated and not zot.created
    assert set(result.to_dict()) == {"cluster_slug", "applied", "skipped", "errors", "obsidian_writes", "zotero_writes", "receipts"}
    assert result.receipts[0]["sinks"]["local"]["state"] == "compensated"
    assert result.receipts[0]["sinks"]["zotero"]["state"] == "rejected"


def test_repeat_apply_updates_owned_note_without_extra_create():
    class StatefulZotero(FakeZotero):
        def children(self, parent):
            result = super().children(parent)
            return result + [{"data": {**item, "key": "NEWNOTE1", "version": 8}}
                             for item in self.created]

    zot = StatefulZotero([note("HUMAN001")])
    assert "preserved 1 unmarked" in _write_zotero_child_note(zot, "PARENT01", "first")
    assert _write_zotero_child_note(zot, "PARENT01", "second") == ""
    assert len(zot.created) == len(zot.updated) == 1
    assert zot.updated[0]["key"] == "NEWNOTE1"
    assert zot.updated[0]["note"] == "second"
    assert zot.notes[0]["data"]["note"] == "<p>Original HUMAN001 — handwritten 中文</p>"


def test_unmarked_note_on_later_page_is_preserved_and_counted():
    zot = FakeZotero(later=[note("HUMAN001")])
    warning = _write_zotero_child_note(zot, "PARENT01", "new")
    assert "preserved 1 unmarked" in warning
    assert len(zot.created) == 1 and not zot.updated


@pytest.mark.parametrize("response", [None, {}, {"successful": {}}, {"successful": {"0": {}}},
                                      {"successful": {"0": {"key": True}}}])
def test_missing_create_confirmation_is_unknown_and_not_retried(response):
    zot = FakeZotero([note("HUMAN001")])
    attempts = []

    def create(items):
        attempts.append(deepcopy(items))
        return response

    zot.create_items = create
    with pytest.raises(RuntimeError, match="inspect Zotero before retrying"):
        _write_zotero_child_note(zot, "PARENT01", "new")
    assert len(attempts) == 1 and not zot.updated


def test_uncertain_create_rolls_back_local_note_and_reports_unknown(tmp_path):
    raw = tmp_path / "raw" / "cluster"
    raw.mkdir(parents=True)
    path = raw / "paper.md"
    original = '---\ntitle: Synthetic\nzotero-key: PARENT01\n---\n\n## Key Findings\n\n> [!success]\n> [TODO]\n^findings\n'
    path.write_text(original, encoding="utf-8")
    zot = FakeZotero([note("HUMAN001")])
    zot.fail_create = TimeoutError("synthetic lost reply after possible remote commit")
    result = apply_summaries(SimpleNamespace(raw=raw.parent), "cluster", [{
        "paper_slug": "paper", "key_findings": ["New finding"],
        "methodology": "Synthetic method", "relevance": "Synthetic relevance",
    }], zot=zot)
    assert result.applied == [] and result.zotero_writes == result.obsidian_writes == 0
    assert "outcome unknown" in result.errors[0] and "no automatic retry" in result.errors[0]
    assert "write failed" not in result.errors[0]
    assert len(zot.created) == 1 and not zot.updated
    assert path.read_text(encoding="utf-8") == original


def test_version_conflict_rolls_back_local_note_without_retry(tmp_path):
    from pyzotero.zotero_errors import PreConditionFailedError

    raw = tmp_path / "raw" / "cluster"
    raw.mkdir(parents=True)
    path = raw / "paper.md"
    original = '---\ntitle: Synthetic\nzotero-key: PARENT01\n---\n\n## Key Findings\n\n> [!success]\n> [TODO]\n^findings\n'
    path.write_text(original, encoding="utf-8")
    zot = FakeZotero([note("HUB00001", owned=True)])
    zot.fail_update = PreConditionFailedError("synthetic version conflict")
    result = apply_summaries(SimpleNamespace(raw=raw.parent), "cluster", [{
        "paper_slug": "paper", "key_findings": ["New finding"],
        "methodology": "Synthetic method", "relevance": "Synthetic relevance",
    }], zot=zot)
    assert not result.applied and result.zotero_writes == result.obsidian_writes == 0
    assert "version conflict" in result.errors[0]
    assert len(zot.updated) == 1 and not zot.created
    assert path.read_text(encoding="utf-8") == original


def test_generic_add_note_is_unowned_but_pipeline_summary_is_owned():
    from research_hub import pipeline
    from research_hub.zotero.client import add_note

    zot = FakeZotero()
    assert add_note(zot, "PARENT01", "Human-requested generic note")
    assert zot.created[0]["tags"] == []
    assert pipeline.add_note(zot, "PARENT01", pipeline._build_note_html({"summary": "synthetic"}))
    assert zot.created[1]["tags"] == [{"tag": TAG}]


def test_shared_client_pagination_and_write_are_one_transaction():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event, Lock

    first_read = Event()
    second_attempted = Event()
    state_lock = Lock()
    events = []

    class SharedClient(FakeZotero):
        def children(self, parent):
            with state_lock:
                events.append((parent, "children"))
            if parent == "FIRST001":
                first_read.set()
                assert second_attempted.wait(2)
            self.current_parent = parent
            return []

        def everything(self, children):
            with state_lock:
                events.append((self.current_parent, "everything"))
            return [note("NOTE" + self.current_parent, owned=True, parent=self.current_parent)]

        def update_item(self, data):
            with state_lock:
                events.append((data["parentItem"], "update"))
            return True

    zot = SharedClient()

    def second():
        assert first_read.wait(2)
        second_attempted.set()
        return _write_zotero_child_note(zot, "SECOND02", "second")

    with ThreadPoolExecutor(max_workers=2) as workers:
        first = workers.submit(_write_zotero_child_note, zot, "FIRST001", "first")
        second_result = workers.submit(second)
        first.result(timeout=3)
        second_result.result(timeout=3)
    assert events == [("FIRST001", "children"), ("FIRST001", "everything"), ("FIRST001", "update"),
                      ("SECOND02", "children"), ("SECOND02", "everything"), ("SECOND02", "update")]


def test_optional_warnings_reach_cli_json_and_mcp_without_changing_success(monkeypatch, capsys):
    from research_hub import cli_summarize, mcp_server, summarize
    from tests._mcp_helpers import _get_mcp_tool

    result = summarize.SummaryApplyResult("cluster", applied=["paper"], obsidian_writes=1,
                                        zotero_writes=1, warnings=["paper: preserved 1 unmarked note"])
    report = summarize.SummaryReport("cluster", cli_used="synthetic", apply_result=result)
    monkeypatch.setattr(summarize, "summarize_cluster", lambda *a, **kw: report)
    args = SimpleNamespace(cluster="cluster", llm_cli="synthetic", apply=True,
                           no_zotero=False, no_obsidian=False)
    assert cli_summarize._cmd_summarize(args, object()) == 0
    assert "WARN paper: preserved 1 unmarked note" in capsys.readouterr().err
    assert cli_summarize._cmd_summarize(args, object(), emit_json=True) == 0
    assert '"warnings"' in capsys.readouterr().out
    monkeypatch.setattr("research_hub.config.get_config", lambda: object())
    monkeypatch.setattr(summarize, "apply_summaries", lambda *a, **kw: result)
    tool = _get_mcp_tool(mcp_server.mcp, "apply_cluster_summaries", module=mcp_server)
    received = tool.fn("cluster", {"summaries": []})
    assert received["warnings"] == result.warnings
    assert received["applied"] == ["paper"] and received["errors"] == []
    assert "warnings" not in summarize.SummaryApplyResult("cluster").to_dict()


@pytest.mark.parametrize("tags", [[{"tag": "research-hub:summary:v2"}], "invalid", ["invalid"]])
def test_unknown_ownership_version_or_invalid_tags_fail_closed(tags):
    owned = note("HUB00001", owned=True)
    owned["data"]["tags"] = tags
    zot = FakeZotero([owned])
    with pytest.raises(RuntimeError):
        _write_zotero_child_note(zot, "PARENT01", "new")
    assert not zot.updated and not zot.created


def test_duplicate_payload_is_not_an_automatic_retry_of_uncertain_create(tmp_path):
    raw = tmp_path / "raw" / "cluster"
    raw.mkdir(parents=True)
    for slug in ("paper", "alias"):
        (raw / f"{slug}.md").write_text('---\ntitle: Synthetic\nzotero-key: PARENT01\n---\n', encoding="utf-8")
    zot = FakeZotero()
    zot.fail_create = TimeoutError("synthetic lost reply")
    entry = {"paper_slug": "paper", "key_findings": ["Synthetic"], "methodology": "x", "relevance": "y"}
    result = apply_summaries(SimpleNamespace(raw=raw.parent), "cluster", [entry, entry, {**entry, "paper_slug": "alias"}],
                             zot=zot, write_obsidian=False)
    assert len(zot.created) == 1 and not zot.updated
    assert len(result.errors) == 1 and "outcome unknown" in result.errors[0]
    assert len(result.skipped) == 2 and all("not retried" in item for item in result.skipped)
    assert not result.applied


@pytest.mark.parametrize("unknown", [False, True])
def test_auto_propagates_receipt_and_never_retries_unknown_create(monkeypatch, unknown):
    import time
    from research_hub import auto, summarize

    calls = []
    message = "zotero write outcome unknown: inspect Zotero before retrying"
    result = summarize.SummaryApplyResult("cluster", warnings=["preserved 1 unmarked note"],
                                        errors=[message] if unknown else [])
    reply = summarize.SummaryReport("cluster", ok=not unknown, error=message if unknown else "",
                                    apply_result=result)
    monkeypatch.setattr(summarize, "summarize_cluster", lambda *a, **kw: calls.append(kw) or reply)
    monkeypatch.setattr("research_hub.paper_summarize.summarize_pending", lambda *a, **kw: [])
    report = auto.AutoReport("cluster", False)
    auto._run_summary_step(object(), "cluster", "synthetic", report, time.time(), False)
    assert len(calls) == 1
    assert any("WARN preserved 1 unmarked note" in step.detail for step in report.steps)
    assert report.steps[-1].ok is not unknown
    if unknown:
        assert any(message in step.detail for step in report.steps)


@pytest.mark.parametrize("unknown", [False, True])
def test_enrich_propagates_receipt_and_unknown_without_retry(tmp_path, monkeypatch, capsys, unknown):
    from research_hub import summarize
    from research_hub.zotero.enrich import EnrichPlan, apply_enrichment
    from tests.test_v080_resummarize import _cfg, _bind_cluster, _write_note

    cfg = _cfg(tmp_path)
    _bind_cluster(cfg, "cluster")
    _write_note(cfg.raw / "cluster" / "paper.md", title="Synthetic", zotero_key="PARENT01",
                abstract="(no abstract)", summary="[TODO] Synthetic")
    calls = []
    message = "zotero write outcome unknown: inspect Zotero before retrying"
    result = summarize.SummaryApplyResult("cluster", warnings=["preserved 1 unmarked note"],
                                        errors=[message] if unknown else [])
    reply = summarize.SummaryReport("cluster", ok=not unknown, error=message if unknown else "",
                                    apply_result=result)
    monkeypatch.setattr(summarize, "summarize_cluster", lambda *a, **kw: calls.append(kw) or reply)

    class EnrichZotero:
        def item(self, key):
            return {"data": {"key": key, "abstractNote": ""}}
        def update_item(self, data):
            return True

    apply_enrichment(EnrichZotero(), [EnrichPlan(item_key="PARENT01", title="Synthetic", doi="",
                     fields_to_fill={"abstractNote": "Synthetic recovered abstract"}, abstract_source="synthetic")],
                     cfg=cfg, cluster_slug="cluster", rate_limit_rps=999, chain_resummarize=True)
    output = capsys.readouterr().out
    assert len(calls) == 1
    assert "preserved 1 unmarked note" in output
    if unknown:
        assert message in output


def test_shared_template_does_not_leak_summary_ownership_to_generic_notes():
    from research_hub.zotero.client import add_note, add_summary_note

    zot = FakeZotero()
    template = {"itemType": "note", "tags": []}
    zot.item_template = lambda kind: template
    assert add_summary_note(zot, "PARENT01", "generated")
    assert add_note(zot, "PARENT01", "personal")
    assert zot.created[0]["tags"] == [{"tag": TAG}]
    assert zot.created[1]["tags"] == []
    assert template == {"itemType": "note", "tags": []}
