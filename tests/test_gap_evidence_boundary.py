"""Exercise the local-note -> prompt -> CLI/writer boundary, without model APIs.

These tests establish preservation and qualification, not scientific truth or
whether a real model follows a prompt. Deliberately unsafe model text must never
be promoted into a writer-verified finding or an overview assertion.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import yaml

from research_hub.gap_analysis import (
    apply_gap_results, build_cluster_digest, cross_cluster_gap,
    emit_cross_cluster_gap_prompt, emit_gap_prompt,
)


@pytest.fixture
def cfg(tmp_path):
    return SimpleNamespace(raw=tmp_path / "raw", hub=tmp_path / "hub", root=tmp_path,
                           clusters_file=tmp_path / "clusters.yaml",
                           research_hub_dir=tmp_path / ".research_hub")


def write_note(cfg, slug="topic", name="paper", *, abstract="Observed association.",
               findings="", **metadata):
    path = cfg.raw / slug / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    fm = {"title": name, "year": 2026, "abstract": abstract, **metadata}
    path.write_text("---\n" + yaml.safe_dump(fm, allow_unicode=True, sort_keys=False)
                    + "---\n\n## Key Findings\n\n" + findings + "\n", encoding="utf-8")
    return path


def overview(cfg, slug="topic"):
    path = cfg.hub / slug / "00_overview.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# Topic\n\nExisting human note.\n", encoding="utf-8")
    return path


def context(path):
    return json.loads(path.with_name(path.stem + "-context.json").read_text(encoding="utf-8"))


def test_truncated_abstract_is_unknown_coverage_even_when_model_overclaims(cfg):
    long_abstract = "A short cross-sectional screening statement. " * 20 + "Longitudinal follow-up exists."
    note = write_note(cfg, abstract=long_abstract)
    before = note.read_bytes()
    digest = build_cluster_digest(cfg, "topic")
    paper = digest.papers[0]
    assert paper.text_limits["summary"] == {
        "characters_available": len(long_abstract), "characters_shown": 500, "truncated": True,
    }
    assert "Longitudinal follow-up exists" not in paper.summary
    assert paper.evidence_level == "abstract"
    assert paper.note_sha256 == hashlib.sha256(before).hexdigest()
    prompt = emit_gap_prompt(digest)
    assert '"truncated": true' in prompt
    assert "exactly 3-5" not in prompt
    model = "### Methodological Gaps\n- Nobody has done longitudinal research.\n"
    target_overview = overview(cfg)
    result = apply_gap_results(cfg, "topic", model, digest=digest)
    evidence = context(result.research_gaps_path)
    assert evidence["assessment"] == "unassessed"
    assert evidence["search_scope"].endswith("coverage unknown")
    assert evidence["digests"][0]["papers"][0]["text_limits"]["summary"]["truncated"]
    report = result.research_gaps_path.read_text(encoding="utf-8")
    assert report.index("scientific assessment unassessed") < report.index("Nobody has done")
    assert "Nobody has done" not in target_overview.read_text(encoding="utf-8")
    assert note.read_bytes() == before


def test_original_scope_is_preserved_without_inventing_a_region(cfg):
    scope = {"objective": "compare mechanisms", "original_constraints": {"period": "2000-2026"},
             "suggestions": ["Taiwan could be an illustrative case"], "geography": "unrestricted"}
    write_note(cfg, provenance={"research": scope})
    digest = build_cluster_digest(cfg, "topic")
    assert digest.papers[0].provenance == {"research": scope}
    prompt = emit_gap_prompt(digest)
    assert "do not turn a cluster label or suggested filter into a user constraint" in prompt
    result = apply_gap_results(cfg, "topic", "No justified directions.", digest=digest)
    preserved = context(result.research_gaps_path)["digests"][0]["papers"][0]["provenance"]
    assert preserved["research"] == scope
    assert preserved["research"]["geography"] == "unrestricted"


def test_recent_low_citation_closest_work_is_retained_not_discarded(cfg):
    closest = {"source_id": "S-new", "year": 2026, "citation_count": 1,
               "role": "closest-prior-work", "question": "same intervention",
               "method": "longitudinal", "outcome": "same endpoint", "locator": "Results p. 5",
               "source_version": "publisher-2026", "claim_status": "contradicts novelty"}
    write_note(cfg, name="new closest work", source_records=[closest])
    digest = build_cluster_digest(cfg, "topic")
    prompt = emit_gap_prompt(digest)
    assert closest == digest.papers[0].source_records[0]
    assert '"citation_count": 1' in prompt and "can defeat novelty" in prompt
    result = apply_gap_results(cfg, "topic", "### Unsupported Novelty Claims\nSame intervention already studied.", digest=digest)
    assert context(result.research_gaps_path)["digests"][0]["papers"][0]["source_records"] == [closest]


@pytest.mark.parametrize("failure", ["paywall", "truncated", "version-conflict", "HTTP 429", "timeout", "parse failure"])
def test_access_and_search_failures_stay_observed_unknowns_not_zero(cfg, failure):
    observed = {"source_id": "S1", "status": failure, "result_count": None,
                "versions": ["arxiv-v1", "publisher-correction"], "tool_ref": "synthetic:attempt"}
    write_note(cfg, source_records=[observed], publication_version="unknown")
    digest = build_cluster_digest(cfg, "topic")
    result = apply_gap_results(cfg, "topic", "Zero prior work; this is novel.", digest=digest)
    stored = context(result.research_gaps_path)
    assert stored["assessment"] == "unassessed"
    assert stored["scientific_validation"] == "not-performed"
    assert stored["digests"][0]["papers"][0]["source_records"] == [observed]
    assert stored["digests"][0]["papers"][0]["publication_version"] == "unknown"
    assert "unknown, never zero results" in emit_gap_prompt(digest)


def test_narrow_candidate_preserves_locators_counterconditions_and_kill_test(cfg):
    records = [
        {"source_id": "S1", "source_version": "publisher-2026", "locator": "Methods p. 4",
         "role": "closest-prior-work", "remaining_difference": "validation for sparse observations"},
        {"source_id": "S2", "source_version": "arxiv-v2", "locator": "Limitations §5",
         "role": "contrary", "conditions": "fails when reporting is sparse"},
    ]
    write_note(cfg, source_records=records, provenance={"research": {"contrary_path": "sparse validation failures"}})
    digest = build_cluster_digest(cfg, "topic")
    candidate = ("### Methodological Gaps — Provisional Candidates\n"
                 "Evidence-supported narrow candidate: sparse-observation validation.\n"
                 "Closest work S1, publisher-2026, Methods p. 4 already estimates the same endpoint.\n"
                 "Remaining difference: validation for sparse observations.\n"
                 "Counterevidence S2, arxiv-v2, Limitations §5: fails when reporting is sparse.\n"
                 "Contrary search path: sparse validation failures.\n"
                 "Kill test: reject if the held-out sparse-case error exceeds the closest baseline.\n")
    target_overview = overview(cfg)
    result = apply_gap_results(cfg, "topic", candidate, digest=digest)
    assert result.research_gaps_path.with_name("research-gaps-model-output.txt").read_text(encoding="utf-8") == candidate
    evidence = context(result.research_gaps_path)
    assert evidence["digests"][0]["papers"][0]["source_records"] == records
    assert evidence["assessment"] == "unassessed"  # preservation does not validate source support
    assert "Kill test:" in result.research_gaps_path.read_text(encoding="utf-8")
    assert "sparse-case" not in target_overview.read_text(encoding="utf-8")  # no model claim promoted by teaser


def test_cli_uses_same_consumed_snapshot_and_keeps_zero_directions(cfg):
    from research_hub.cli_paper import _cmd_paper_gaps
    note = write_note(cfg, abstract="Observed mechanism only.")
    target_overview = overview(cfg)
    consumed = note.read_bytes()
    response = "### Actionable Research Directions\nZero justified directions; scope uncertain.\n"
    prompts = []

    def fake_model(cli_name, prompt, **kwargs):
        prompts.append(prompt)
        note.write_text(note.read_text(encoding="utf-8").replace("Observed mechanism only.", "Changed after prompt."), encoding="utf-8")
        return response

    with patch("research_hub.llm_cli.detect_llm_cli", return_value="fixture"), \
         patch("research_hub.llm_cli.invoke_llm_cli", side_effect=fake_model):
        _cmd_paper_gaps(cfg, SimpleNamespace(cluster="topic", compare_cluster=None, no_llm=False, llm_cli=None))
    report = cfg.hub / "topic" / "research-gaps.md"
    stored = context(report)
    assert stored["digests"][0]["papers"][0]["note_sha256"] == hashlib.sha256(consumed).hexdigest()
    assert report.with_name("research-gaps-model-output.txt").read_text(encoding="utf-8") == response
    assert "Zero justified directions" in report.read_text(encoding="utf-8")
    assert "zero justified directions is valid" in target_overview.read_text(encoding="utf-8")
    assert "Changed after prompt" not in prompts[0]


def test_cross_cli_qualifies_both_overviews_and_preserves_failure_records(cfg):
    from research_hub.cli_paper import _cmd_paper_gaps
    write_note(cfg, "a", source_records=[{"status": "paywall", "result_count": None}])
    write_note(cfg, "b", name="closest", source_records=[{"role": "closest-prior-work", "locator": "p. 5"}])
    a, b = overview(cfg, "a"), overview(cfg, "b")
    raw = "### Intersection Gaps\nNobody has combined these methods; definitely worth doing.\n"
    with patch("research_hub.llm_cli.detect_llm_cli", return_value="fixture"), \
         patch("research_hub.llm_cli.invoke_llm_cli", return_value=raw):
        _cmd_paper_gaps(cfg, SimpleNamespace(cluster="a", compare_cluster="b", no_llm=False, llm_cli=None))
    path = cfg.hub / "_cross-cluster" / "a-x-b-gaps.md"
    assert context(path)["assessment"] == "unassessed"
    assert len(context(path)["digests"]) == 2
    for target in (a, b):
        assert "scientific assessment unassessed" in target.read_text(encoding="utf-8")
        assert "definitely worth" not in target.read_text(encoding="utf-8")
    assert path.with_name("a-x-b-gaps-model-output.txt").read_text(encoding="utf-8") == raw


def test_cross_prompt_does_not_force_bridges_or_imply_literature_absence(cfg):
    write_note(cfg, "a")
    write_note(cfg, "b", name="method comparator")
    da, db = build_cluster_digest(cfg, "a"), build_cluster_digest(cfg, "b")
    prompt = emit_cross_cluster_gap_prompt(da, db)
    assert "exactly 3-5" not in prompt and "zero or more" in prompt
    assert "neither is the whole literature" in prompt
    result = cross_cluster_gap(cfg, "a", "b", "No supported bridges.", digests=(da, db))
    assert context(result.gap_path)["assessment"] == "unassessed"


@pytest.mark.parametrize("cross", [False, True])
def test_owned_legacy_sections_are_qualified_idempotently_without_editing_content(cfg, cross):
    write_note(cfg)
    target = overview(cfg)
    human_suffix = "\n## Personal notes\n\nMy own conclusion must not be changed.  \n"
    if cross:
        generated = "## Cross-Cluster Analysis\n\n- [[_cross-cluster/topic-x-other-gaps|topic × other gaps]]\n"
        apply = lambda: cross_cluster_gap(cfg, "topic", "other", "New model text")
    else:
        generated = "## Research Gaps\n\n*Full analysis: [[research-gaps]]*\n\nOld generated teaser: Nobody has studied this.\n"
        apply = lambda: apply_gap_results(cfg, "topic", "New model text")
    original = "# Topic\n\nHuman introduction.  \n\n" + generated + human_suffix
    target.write_bytes(original.encode("utf-8"))
    apply()
    changed = target.read_text(encoding="utf-8")
    assert "scientific assessment unassessed" in changed
    assert generated.split("\n", 1)[1] in changed
    assert changed.startswith("# Topic\n\nHuman introduction.  \n\n")
    assert changed.endswith(human_suffix)
    apply()
    assert target.read_text(encoding="utf-8") == changed


@pytest.mark.parametrize("cross", [False, True])
def test_ambiguous_user_overview_sections_are_untouched(cfg, cross):
    write_note(cfg)
    target = overview(cfg)
    heading = "## Cross-Cluster Analysis" if cross else "## Research Gaps"
    original = "# Topic\n\n" + heading + "\n\nMy own research argument.  \n\n## Next\nPrivate reminder.\n"
    target.write_bytes(original.encode("utf-8"))
    if cross:
        cross_cluster_gap(cfg, "topic", "other", "New model text")
    else:
        apply_gap_results(cfg, "topic", "New model text")
    assert target.read_bytes() == original.encode()


def test_metadata_dates_do_not_break_provenance_snapshot(cfg):
    import datetime
    record = {"source_id": "S1", "accessed": datetime.date(2026, 10, 2), "locator": "Methods p. 3"}
    write_note(cfg, source_records=[record])
    digest = build_cluster_digest(cfg, "topic")
    assert "2026-10-02" in emit_gap_prompt(digest)
    result = apply_gap_results(cfg, "topic", "Unresolved.", digest=digest)
    assert context(result.research_gaps_path)["digests"][0]["papers"][0]["source_records"][0]["accessed"] == "2026-10-02"


def test_lf_crlf_notes_have_parsing_parity_and_distinct_raw_hashes(cfg):
    records = [{"source_id": "S1", "source_version": "publisher-2026", "locator": "Methods p. 4"}]
    provenance = {"research": {"geography": "unrestricted", "original_constraints": {"period": "2000-2026"}}}
    lf = write_note(cfg, name="lf", abstract="Complete abstract.", source_records=records,
                    provenance=provenance, publication_version="publisher-2026", doi="10.1000/example")
    lf.write_bytes(lf.read_bytes().replace(b"\r\n", b"\n"))  # explicit LF fixture on every OS
    crlf = lf.with_name("crlf.md")
    crlf.write_bytes(lf.read_bytes().replace(b"\n", b"\r\n"))
    digest = build_cluster_digest(cfg, "topic")
    by_name = {Path(p.note_locator).stem: p for p in digest.papers}
    a, b = by_name["lf"], by_name["crlf"]
    for field in ("title", "doi", "year", "summary", "publication_version", "source_records", "provenance", "text_limits"):
        assert getattr(a, field) == getattr(b, field)
    assert b.source_records == records and b.provenance == provenance
    assert a.note_sha256 == hashlib.sha256(lf.read_bytes()).hexdigest()
    assert b.note_sha256 == hashlib.sha256(crlf.read_bytes()).hexdigest()
    assert a.note_sha256 != b.note_sha256


@pytest.mark.parametrize("outside", [False, True])
def test_note_locator_identifies_actual_configured_raw_directory(cfg, outside):
    cfg.raw = cfg.root / "custom" / "paper-notes"
    if outside:
        cfg.root = cfg.root / "vault"
    note = write_note(cfg)
    digest = build_cluster_digest(cfg, "topic")
    expected = note.absolute().as_posix() if outside else "custom/paper-notes/topic/paper.md"
    assert digest.papers[0].note_locator == expected
    result = apply_gap_results(cfg, "topic", "Unresolved.", digest=digest)
    assert context(result.research_gaps_path)["digests"][0]["papers"][0]["note_locator"] == expected


@pytest.mark.parametrize("existing_section", [False, True])
@pytest.mark.parametrize("cross", [False, True])
def test_overview_crlf_and_eof_whitespace_are_preserved_byte_for_byte(cfg, existing_section, cross):
    write_note(cfg)
    target = overview(cfg)
    prefix = b"# Topic\r\n\r\nHuman introduction.  \t\r\n"
    suffix = b"\r\n## Personal notes\r\nHuman interpretation.  \t\r\n\r\n \t"
    if existing_section:
        if cross:
            generated = b"\r\n## Cross-Cluster Analysis\r\n\r\n- [[_cross-cluster/topic-x-other-gaps|topic \xc3\x97 other gaps]]\r\n"
        else:
            generated = b"\r\n## Research Gaps\r\n\r\n*Full analysis: [[research-gaps]]*\r\nOld teaser.  \t\r\n"
    else:
        generated = b""
    original = prefix + generated + suffix
    target.write_bytes(original)
    apply = (lambda: cross_cluster_gap(cfg, "topic", "other", "Unverified model text.")) if cross else (lambda: apply_gap_results(cfg, "topic", "Unverified model text."))
    apply()
    updated = target.read_bytes()
    if existing_section:
        assert updated.startswith(prefix)
        assert updated.endswith(suffix)
        assert generated.split(b"\r\n", 2)[-1] in updated
    else:
        assert updated.startswith(original)  # retain even the old EOF whitespace
    assert b"\n" not in updated.replace(b"\r\n", b"")
    assert b"scientific assessment unassessed" in updated
    apply()
    assert target.read_bytes() == updated


def test_unreadable_note_stays_unknown_and_cli_does_not_invoke_model(cfg, monkeypatch, capsys):
    from research_hub.cli_paper import _cmd_paper_gaps
    note = write_note(cfg)
    real_read = Path.read_bytes
    def fail_note(path):
        if path == note:
            raise OSError("synthetic unreadable note")
        return real_read(path)
    monkeypatch.setattr(Path, "read_bytes", fail_note)
    digest = build_cluster_digest(cfg, "topic")
    assert digest.paper_count == 1 and digest.papers == [] and digest.read_errors == ["paper.md"]
    with patch("research_hub.llm_cli.invoke_llm_cli", side_effect=AssertionError("must not invoke")):
        _cmd_paper_gaps(cfg, SimpleNamespace(cluster="topic", compare_cluster=None, no_llm=False, llm_cli=None))
    assert "Evidence unavailable" in capsys.readouterr().err


def test_new_fixture_text_io_is_explicitly_utf8():
    """Guard the fixture encoding contract; live Windows CI exercises it too."""
    import ast
    root = Path(__file__).resolve().parent
    for name in ("test_gap_evidence_boundary.py", "test_gap_preliminary_directions.py",
                 "test_handoff_gap_to_topic_design_helper.py"):
        tree = ast.parse((root / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {"read_text", "write_text"}:
                encoding = next((kw.value for kw in node.keywords if kw.arg == "encoding"), None)
                assert isinstance(encoding, ast.Constant) and encoding.value == "utf-8", (name, node.lineno)
