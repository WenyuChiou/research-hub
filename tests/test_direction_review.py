"""Adversarial offline acceptance tests; supplied assessments are not science proofs."""

from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import shutil

import pytest
import yaml

from research_hub.direction_review import (
    DirectionReviewError,
    candidate_sha256,
    check_direction_review,
    dumps_direction_json,
    validate_direction_review,
)


FIXTURES = Path(__file__).parent / "fixtures" / "direction_review"
DOSSIER_NAME = "topic_dossier.v1.gaps.yml"
REVIEW_NAME = "topic_dossier.v1.direction-review.json"
KINDS = {"data", "tool", "model", "license", "cost", "premise", "validation-path"}


def independent_hash(candidate):
    raw = json.dumps(candidate, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture
def record(tmp_path):
    root = tmp_path / "sources-root"
    shutil.copytree(FIXTURES, root)
    dossier = yaml.safe_load((root / DOSSIER_NAME).read_text(encoding="utf-8"))
    review = json.loads((root / REVIEW_NAME).read_text(encoding="utf-8"))
    return dossier, review, root


def run(record):
    return validate_direction_review(*record)


def total(result, unit="person-weeks"):
    return next(row for row in result["resource_estimates"]["totals"] if row["unit"] == unit)


def only_g1(review):
    """Explicit caller scope, not a checker-generated candidate selection."""
    review["candidate_refs"] = review["candidate_refs"][:1]
    review["checks"] = [row for row in review["checks"]
                        if row["candidate_ref"]["candidate_id"] == "G1"]
    review["resources"]["requirements"] = review["resources"]["requirements"][:1]
    review["resources"]["components"] = review["resources"]["components"][:1]


def assert_boundary(result):
    assert result["semantic_assessment"] == "not-performed"
    assert result["human_selection"] == "outside-checker"
    assert result["execution_authorized"] is False
    assert result["resource_estimates"]["runtime_budget_verification"] == "not-performed"
    assert "selected_id" not in result
    assert "selected_candidate_id" not in result
    assert "feasible" not in result
    assert "pass" not in result


def test_fixture_hashes_and_locators_are_real_independent_inputs(record):
    dossier, review, root = record
    for candidate, ref in zip(dossier["gaps"], review["candidate_refs"]):
        assert ref["candidate_sha256"] == independent_hash(candidate)
    for evidence in review["evidence"]:
        raw = (root / evidence["path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == evidence["sha256"]
        assert evidence["locator"].startswith("lines ")
        first, last = map(int, evidence["locator"].removeprefix("lines ").split("-"))
        assert 1 <= first <= last <= len(raw.splitlines())
        assert evidence["publication_version"].startswith("fixture-")


def test_all_seven_kinds_multiple_data_checks_and_unknowns_remain_supplied(record):
    result = run(record)
    assert result["record_status"] == "valid"
    assert result["binding_status"] == "current"
    assert result["prerequisites"] == record[1]["checks"]
    for candidate_id in ("G1", "G2"):
        rows = [row for row in result["prerequisites"]
                if row["candidate_ref"]["candidate_id"] == candidate_id]
        assert {row["kind"] for row in rows} == KINDS
    data = [row for row in result["prerequisites"]
            if row["candidate_ref"]["candidate_id"] == "G2" and row["kind"] == "data"]
    assert {row["status"] for row in data} == {"supported", "contradicted"}
    assert any(row["kind"] == "license" and row["status"] == "unknown"
               for row in result["prerequisites"])
    assert_boundary(result)


def test_new_method_effect_may_remain_unmeasured_without_invalidating_record(record):
    result = run(record)
    premise = next(row for row in result["prerequisites"] if row["check_id"] == "G1-premise")
    assert result["record_status"] == "valid"
    assert premise["status"] == "unknown"
    assert premise["next_check"]
    assert_boundary(result)


def test_hash_is_full_candidate_canonical_utf8_and_order_independent():
    candidate = {"id": "G1", "candidate_version": 1, "statement": "年度水量", "extra": [1, None, True]}
    assert candidate_sha256(candidate) == independent_hash(candidate)
    assert candidate_sha256(dict(reversed(list(candidate.items())))) == independent_hash(candidate)
    altered = deepcopy(candidate)
    altered["extra"].append("not ignored")
    assert candidate_sha256(altered) != independent_hash(candidate)


@pytest.mark.parametrize("mutation,code", [
    (lambda d, r: r["checks"].pop(0), "missing-prerequisite-category"),
    (lambda d, r: r["checks"].append(deepcopy(r["checks"][0])), "duplicate-or-invalid-check-id"),
    (lambda d, r: r["checks"][0].update(status="pass"), "check-status-invalid"),
    (lambda d, r: r["checks"][0].update(kind="dataset"), "check-kind-invalid"),
    (lambda d, r: r["checks"][0].update(statement="  "), "check-description-required"),
    (lambda d, r: r["checks"][2].update(reason=""), "check-description-required"),
    (lambda d, r: r["checks"][3].update(next_check=None), "unknown-requires-next-check"),
    (lambda d, r: r["checks"][3].update(next_check="  "), "next-check-invalid"),
    (lambda d, r: r["checks"][0].update(evidence_refs=["absent"]), "evidence-ref-missing"),
    (lambda d, r: r["checks"][0].update(evidence_refs=["data", "data"]), "evidence-refs-invalid"),
    (lambda d, r: r["evidence"].append(deepcopy(r["evidence"][0])), "duplicate-or-invalid-evidence-id"),
    (lambda d, r: r["candidate_refs"].append(deepcopy(r["candidate_refs"][0])), "duplicate-candidate-ref"),
    (lambda d, r: d["gaps"].append(deepcopy(d["gaps"][0])), "duplicate-dossier-candidate"),
    (lambda d, r: r.update(format="research-direction-review/999"), "unsupported-review-format"),
    (lambda d, r: r.update(selected_id="G1"), "review-shape"),
    (lambda d, r: r["candidate_refs"][0].update(candidate_version=True), "candidate-version-invalid"),
    (lambda d, r: r["candidate_refs"][0].update(candidate_sha256="bad"), "candidate-hash-invalid"),
    (lambda d, r: r["checks"][0]["candidate_ref"].update(candidate_version=2), "candidate-ref-not-in-review"),
])
def test_invalid_record_shapes_have_explicit_codes(record, mutation, code):
    mutation(record[0], record[1])
    with pytest.raises(DirectionReviewError) as error:
        run(record)
    assert error.value.code == code


@pytest.mark.parametrize("status", ["supported", "contradicted"])
def test_established_assessments_need_evidence(record, status):
    record[1]["checks"][0].update(status=status, evidence_refs=[])
    with pytest.raises(DirectionReviewError, match="evidence-refs-invalid"):
        run(record)


@pytest.mark.parametrize("field", ["path", "sha256", "locator", "evidence_level", "publication_version"])
def test_required_evidence_metadata_cannot_be_omitted(record, field):
    del record[1]["evidence"][0][field]
    with pytest.raises(DirectionReviewError, match="evidence-shape"):
        run(record)


@pytest.mark.parametrize("field", ["path", "locator", "evidence_level", "publication_version"])
def test_empty_evidence_descriptions_are_not_a_binding(record, field):
    record[1]["evidence"][0][field] = "  "
    with pytest.raises(DirectionReviewError, match="evidence-description-required"):
        run(record)


def test_unknown_publication_version_and_note_level_remain_explicit(record):
    record[1]["evidence"][1]["publication_version"] = "unknown"
    result = run(record)
    binding = next(row for row in result["evidence_bindings"] if row["evidence_id"] == "method")
    assert binding["publication_version"] == "unknown"
    assert binding["publication_version_status"] == "unknown"
    assert binding["evidence_level"] == "synthetic-note-summary"
    assert binding["locator"] == "lines 3-5"
    assert binding["locator_verification"] == "not-performed"
    assert result["semantic_assessment"] == "not-performed"


def test_theory_can_explain_no_data_or_model_or_resource_requirement(record):
    _, review, _ = record
    only_g1(review)
    for check in review["checks"]:
        check.update(status="not-applicable", evidence_refs=[], next_check=None,
                     reason="Purely formal derivation; this empirical prerequisite is not required.")
    review["resources"] = {"requirements": [{"candidate_ref": deepcopy(review["candidate_refs"][0]),
                                                "units": []}], "components": [], "capacities": []}
    result = run(record)
    assert result["record_status"] == "valid"
    assert result["resource_estimates"]["status"] == "not-applicable"
    assert_boundary(result)


@pytest.mark.parametrize("change", ["version", "text", "extra-field"])
def test_changed_candidate_never_inherits_old_assessment_binding(record, change):
    candidate = record[0]["gaps"][0]
    if change == "version":
        candidate["candidate_version"] = 2
    elif change == "text":
        candidate["statement"] = "Now compare monthly changes."
    else:
        candidate["unanticipated_new_requirement"] = "Prospective observations"
    result = run(record)
    assert result["binding_status"] == "not-current"
    assert result["candidate_bindings"] == [{"candidate_id": "G1", "status": "stale-candidate"},
                                             {"candidate_id": "G2", "status": "current"}]
    assert result["prerequisites"] == record[1]["checks"]
    assert result["resource_estimates"]["status"] == "unknown"
    assert all(row["status"] == "unknown" for row in result["resource_estimates"]["totals"])
    assert_boundary(result)


def test_review_can_be_explicitly_reaffirmed_for_new_candidate_version(record):
    dossier, review, _ = record
    only_g1(review)
    candidate = dossier["gaps"][0]
    candidate.update(candidate_version=2, statement="Bounded annual comparison of totals.")
    replacement = {"candidate_id": "G1", "candidate_version": 2,
                   "candidate_sha256": independent_hash(candidate)}
    review["candidate_refs"] = [replacement]
    for row in review["checks"] + review["resources"]["requirements"]:
        row["candidate_ref"] = deepcopy(replacement)
    review["resources"]["components"][0]["candidate_refs"] = [deepcopy(replacement)]
    result = run(record)
    assert result["binding_status"] == "current"
    assert_boundary(result)


def test_other_candidate_changes_do_not_invalidate_scoped_g1(record):
    dossier, review, root = record
    only_g1(review)
    first = run(record)
    dossier["gaps"][1]["statement"] = "A wholly different G2 question."
    assert run(record) == first
    # Raw input receipt still changes even though G1's identity remains stable.
    (root / DOSSIER_NAME).write_text(yaml.safe_dump(dossier), encoding="utf-8")
    (root / REVIEW_NAME).write_text(json.dumps(review), encoding="utf-8")
    changed = check_direction_review(root / DOSSIER_NAME, root / REVIEW_NAME, root)
    assert changed["binding_status"] == "current"
    assert changed["input_receipts"]["dossier_sha256"] != hashlib.sha256((FIXTURES / DOSSIER_NAME).read_bytes()).hexdigest()


def test_same_content_recheck_is_deterministic_and_does_not_mutate_inputs(record):
    before = deepcopy(record[:2])
    first = run(record)
    assert run(record) == first
    assert record[:2] == before
    first["prerequisites"][0]["evidence_refs"].append("tamper-result-only")
    first["resource_estimates"]["components"][0]["evidence_refs"].append("tamper-result-only")
    first["resource_estimates"]["capacities"][0]["amount"] = 999
    assert record[:2] == before


@pytest.mark.parametrize("version", [None, 0, -1, True, "1"])
def test_missing_or_invalid_legacy_candidate_version_never_defaults_to_one(record, version):
    candidate = record[0]["gaps"][0]
    if version is None:
        del candidate["candidate_version"]
    else:
        candidate["candidate_version"] = version
    result = run(record)
    assert result["candidate_bindings"][0]["status"] == "missing-candidate-version"
    assert result["binding_status"] == "not-current"


def test_actual_legacy_dossier_remains_unchanged_and_is_explicitly_unversioned(record):
    legacy_path = FIXTURES.parent / "topic_dossier_sample.gaps.yml"
    raw = legacy_path.read_bytes()
    dossier = yaml.safe_load(raw)
    result = validate_direction_review(dossier, record[1], record[2])
    assert {row["status"] for row in result["candidate_bindings"]} == {"missing-candidate-version"}
    assert legacy_path.read_bytes() == raw


def test_missing_current_candidate_has_separate_binding_reason(record):
    record[0]["gaps"].pop(0)
    result = run(record)
    assert result["candidate_bindings"][0]["status"] == "missing-candidate"
    assert result["binding_status"] == "not-current"


@pytest.mark.parametrize("path", ["../outside.txt", "/etc/passwd", "C:/outside.txt", "C:\\outside.txt",
                                  "sources/../sources/data-dictionary.txt", "sources//data-dictionary.txt",
                                  "./sources/data-dictionary.txt", "https://example.invalid/a", "sources/a:stream"])
def test_evidence_paths_cannot_escape_or_use_alternate_path_syntax(record, path):
    record[1]["evidence"][0]["path"] = path
    result = run(record)
    assert result["evidence_bindings"][0]["status"] == "invalid-path"
    assert result["binding_status"] == "not-current"
    assert result["prerequisites"][0]["status"] == "supported"  # supplied, not promoted


@pytest.mark.parametrize("path,status", [("sources/absent.txt", "unavailable"), ("sources", "not-file")])
def test_missing_or_directory_source_is_not_current(record, path, status):
    record[1]["evidence"][0]["path"] = path
    result = run(record)
    assert result["evidence_bindings"][0]["status"] == status
    assert result["binding_status"] == "not-current"


def test_changed_raw_bytes_are_not_silently_rehashed_into_approval(record):
    _, review, root = record
    evidence = review["evidence"][0]
    old_hash = evidence["sha256"]
    path = root / evidence["path"]
    path.write_bytes(path.read_bytes() + b"\nchanged after review\n")
    result = run(record)
    binding = result["evidence_bindings"][0]
    assert binding["status"] == "changed"
    assert binding["expected_sha256"] == old_hash
    assert binding["actual_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert review["evidence"][0]["sha256"] == old_hash
    assert result["binding_status"] == "not-current"
    assert result["prerequisites"][0]["status"] == "supported"
    assert result["resource_estimates"]["status"] == "unknown"
    assert all(row["status"] == "unknown" for row in result["resource_estimates"]["totals"])
    assert_boundary(result)


def make_link(link, target, *, directory=False):
    try:
        link.symlink_to(target, target_is_directory=directory)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"Symlinks unavailable on this filesystem: {exc}")


@pytest.mark.parametrize("directory", [False, True])
def test_source_symlink_and_symlinked_parent_are_rejected(record, directory):
    _, review, root = record
    if directory:
        make_link(root / "linked", root / "sources", directory=True)
        review["evidence"][0]["path"] = "linked/data-dictionary.txt"
    else:
        make_link(root / "linked.txt", root / "sources/data-dictionary.txt")
        review["evidence"][0]["path"] = "linked.txt"
    result = run(record)
    assert result["evidence_bindings"][0]["status"] == "linked-path"
    assert result["binding_status"] == "not-current"


@pytest.mark.parametrize("ancestor", [False, True])
def test_linked_source_root_or_ancestor_is_rejected(record, tmp_path, ancestor):
    dossier, review, root = record
    if ancestor:
        make_link(tmp_path / "linked-parent", root.parent, directory=True)
        linked_root = tmp_path / "linked-parent" / root.name
    else:
        linked_root = tmp_path / "linked-root"
        make_link(linked_root, root, directory=True)
    with pytest.raises(DirectionReviewError, match="source-root-linked"):
        validate_direction_review(dossier, review, linked_root)


def test_unreadable_source_does_not_crash_or_expose_contents(record, monkeypatch):
    original = Path.open
    target = record[2] / record[1]["evidence"][0]["path"]
    def deny_one(path, *args, **kwargs):
        if path == target:
            raise PermissionError("private underlying detail")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", deny_one)
    result = run(record)
    assert result["evidence_bindings"][0]["status"] == "unreadable"
    assert "private underlying detail" not in json.dumps(result)


def test_raw_binary_evidence_is_hashed_without_decoding_or_normalizing(record):
    _, review, root = record
    path = root / review["evidence"][0]["path"]
    raw = b"\xff\x00\r\nopaque synthetic source\r\n"
    path.write_bytes(raw)
    review["evidence"][0]["sha256"] = hashlib.sha256(raw).hexdigest()
    result = run(record)
    assert result["evidence_bindings"][0]["status"] == "current"
    assert_boundary(result)


def test_seven_plus_eight_exceeds_ten_even_if_each_separately_fits(record):
    result = run(record)
    assert total(result) == {"unit": "person-weeks", "demand": 15, "capacity": 10,
                             "status": "exceeds-estimate", "missing_candidate_ids": [],
                             "unresolved_component_ids": []}
    assert result["resource_estimates"]["status"] == "exceeds-estimate"
    assert_boundary(result)


def test_shared_three_plus_four_plus_five_is_twelve_only_with_explicit_scope(record):
    review = record[1]
    first, second = review["resources"]["components"]
    first["amount"], second["amount"] = 4, 5
    shared = deepcopy(first)
    shared.update(component_id="shared-cleaning", candidate_refs=deepcopy(review["candidate_refs"]), amount=3,
                  sharing_basis="estimates.txt line 6: the same cleaned annual table serves both questions.")
    review["resources"]["components"].append(shared)
    result = run(record)
    assert total(result)["demand"] == 12
    assert total(result)["status"] == "exceeds-estimate"
    shared["sharing_basis"] = None
    unresolved = total(run(record))
    assert unresolved["demand"] is None
    assert unresolved["status"] == "unknown"
    assert unresolved["unresolved_component_ids"] == ["shared-cleaning"]


def test_similar_component_descriptions_do_not_implicitly_deduplicate(record):
    components = record[1]["resources"]["components"]
    for component in components:
        component.update(estimate_basis="The identically named cleaning activity.", amount=7)
    assert total(run(record))["demand"] == 14


@pytest.mark.parametrize("missing", ["candidate-component", "capacity", "estimate", "capacity-amount",
                                      "requirement", "required-units"])
def test_missing_planning_information_is_unknown_never_zero_filled(record, missing):
    resources = record[1]["resources"]
    if missing == "candidate-component":
        resources["components"].pop()
    elif missing == "capacity":
        resources["capacities"] = []
    elif missing == "estimate":
        resources["components"][1]["amount"] = None
    elif missing == "capacity-amount":
        resources["capacities"][0]["amount"] = None
    elif missing == "requirement":
        resources["requirements"].pop()
    else:
        resources["requirements"][1]["units"] = None
    result = run(record)
    row = total(result)
    assert row["status"] == "unknown"
    assert result["resource_estimates"]["status"] == "unknown"
    if missing not in {"capacity", "capacity-amount"}:
        assert row["demand"] is None
    if missing == "candidate-component":
        assert row["missing_candidate_ids"] == ["G2"]
    if missing in {"requirement", "required-units"}:
        assert result["resource_estimates"]["unknown_requirement_candidate_ids"] == ["G2"]


def test_omitted_entire_resource_dimension_does_not_allow_cheap_partial_within(record):
    resources = record[1]["resources"]
    resources["requirements"][0]["units"].append("USD")
    result = run(record)
    assert total(result, "USD")["demand"] is None
    assert total(result, "USD")["status"] == "unknown"
    assert total(result, "USD")["missing_candidate_ids"] == ["G1"]


def test_usd_gpu_hours_and_person_weeks_remain_separate_dimensions(record):
    review = record[1]
    resources = review["resources"]
    only_g1(review)
    for unit, amount, capacity in [("USD", 20, 25), ("GPU-hours", 4, 3)]:
        resources["requirements"][0]["units"].append(unit)
        component = deepcopy(resources["components"][0])
        component.update(component_id=unit, unit=unit, amount=amount)
        resources["components"].append(component)
        resources["capacities"].append({"unit": unit, "amount": capacity,
                                         "decision_ref": "Synthetic estimates.txt line 7."})
    result = run(record)
    assert {row["unit"] for row in result["resource_estimates"]["totals"]} == {"person-weeks", "USD", "GPU-hours"}
    assert total(result, "USD")["demand"] == 20
    assert total(result, "USD")["status"] == "within-estimate"
    assert total(result, "GPU-hours")["demand"] == 4
    assert total(result, "GPU-hours")["status"] == "exceeds-estimate"
    assert total(result)["demand"] == 7
    assert "total" not in result["resource_estimates"]


def test_only_explicit_candidate_subset_is_summed_and_never_selected(record):
    only_g1(record[1])
    result = run(record)
    assert total(result)["demand"] == 7
    assert total(result)["status"] == "within-estimate"
    assert result["candidate_bindings"] == [{"candidate_id": "G1", "status": "current"}]
    assert record[0]["gaps"][0]["verdict"] == "go"
    assert_boundary(result)


@pytest.mark.parametrize("quantity", [-1, True, False, float("nan"), float("inf"), -float("inf"), "7"])
@pytest.mark.parametrize("target", ["components", "capacities"])
def test_invalid_quantities_are_not_treated_as_numbers(record, target, quantity):
    record[1]["resources"][target][0]["amount"] = quantity
    with pytest.raises(DirectionReviewError):
        run(record)


@pytest.mark.parametrize("mutation,code", [
    (lambda r: r["components"].append(deepcopy(r["components"][0])), "duplicate-or-invalid-component-id"),
    (lambda r: r["components"][0].update(evidence_refs=[]), "evidence-refs-invalid"),
    (lambda r: r["components"][0].update(estimate_basis=""), "resource-estimate-invalid"),
    (lambda r: r["components"][0].update(candidate_refs=[]), "component-scope-invalid"),
    (lambda r: r["components"][0]["candidate_refs"][0].update(candidate_version=2), "candidate-ref-not-in-review"),
    (lambda r: r["components"][0].update(unit="USD"), "component-unit-not-declared"),
    (lambda r: r["capacities"][0].update(decision_ref=""), "capacity-decision-ref-required"),
    (lambda r: r["capacities"].append(deepcopy(r["capacities"][0])), "capacity-invalid"),
    (lambda r: r["requirements"].append(deepcopy(r["requirements"][0])), "duplicate-resource-requirement"),
    (lambda r: r["requirements"][0].update(units=[]), "applicable-cost-requires-units"),
])
def test_resource_contract_rejects_unbound_or_ambiguous_records(record, mutation, code):
    mutation(record[1]["resources"])
    with pytest.raises(DirectionReviewError) as error:
        run(record)
    assert error.value.code == code


def test_input_receipts_bind_exact_bytes_and_file_api_does_not_write(record):
    _, _, root = record
    before = {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}
    result = check_direction_review(root / DOSSIER_NAME, root / REVIEW_NAME, root)
    assert result["input_receipts"] == {"dossier_sha256": hashlib.sha256(before[Path(DOSSIER_NAME)]).hexdigest(),
                                       "review_sha256": hashlib.sha256(before[Path(REVIEW_NAME)]).hexdigest()}
    assert before == {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}
    assert_boundary(result)


@pytest.mark.parametrize("name,raw,code", [
    (DOSSIER_NAME, b"gaps: [", "input-malformed"),
    (REVIEW_NAME, b'{"format":', "input-malformed"),
    (DOSSIER_NAME, b"gaps: []\ngaps: []\n", "duplicate-object-key"),
    (DOSSIER_NAME, b"gaps:\n- id: G1\n  id: G2\n", "duplicate-object-key"),
    (REVIEW_NAME, b'{"format":"a","format":"b"}', "duplicate-object-key"),
    (REVIEW_NAME, b'{"nested":{"x":1,"x":2}}', "duplicate-object-key"),
    (DOSSIER_NAME, b"gaps: !!python/object/apply:os.system ['echo unsafe']", "input-malformed"),
    (DOSSIER_NAME, b"1: non-string key\ngaps: []", "non-string-object-key"),
    (REVIEW_NAME, b"\xff", "input-unreadable"),
])
def test_malformed_and_duplicate_key_input_is_bounded(record, name, raw, code):
    root = record[2]
    (root / name).write_bytes(raw)
    with pytest.raises(DirectionReviewError) as error:
        check_direction_review(root / DOSSIER_NAME, root / REVIEW_NAME, root)
    assert error.value.code == code
    assert str(error.value) == code


def test_recursive_candidate_yaml_is_bounded_without_recursion_traceback(record):
    root = record[2]
    (root / DOSSIER_NAME).write_text("gaps:\n- &g\n  id: G1\n  candidate_version: 1\n  self: *g\n", encoding="utf-8")
    with pytest.raises(DirectionReviewError, match="yaml-alias-not-supported"):
        check_direction_review(root / DOSSIER_NAME, root / REVIEW_NAME, root)


def test_resource_output_retains_inspectable_supplied_provenance(record):
    result = run(record)
    for field in ("requirements", "components", "capacities"):
        assert result["resource_estimates"][field] == record[1]["resources"][field]


@pytest.mark.parametrize("field", ["candidate_sha256", "sha256"])
@pytest.mark.parametrize("digest", ["", "g" * 64, "A" * 64, "0" * 63, None])
def test_bad_digest_shapes_do_not_become_bindings(record, field, digest):
    if field == "candidate_sha256":
        record[1]["candidate_refs"][0][field] = digest
    else:
        record[1]["evidence"][0][field] = digest
    with pytest.raises(DirectionReviewError, match="hash-invalid"):
        run(record)


@pytest.mark.parametrize("kind,code", [("absent", "source-root-unavailable"),
                                      ("file", "source-root-not-directory")])
def test_explicit_source_root_must_exist_as_directory(record, kind, code):
    dossier, review, root = record
    wrong = root / ("missing-directory" if kind == "absent" else DOSSIER_NAME)
    with pytest.raises(DirectionReviewError, match=code):
        validate_direction_review(dossier, review, wrong)


def test_input_and_source_size_limits_are_bounded(record, monkeypatch):
    import research_hub.direction_review as checker
    root = record[2]
    monkeypatch.setattr(checker, "MAX_INPUT_BYTES", 8)
    with pytest.raises(DirectionReviewError, match="input-too-large"):
        check_direction_review(root / DOSSIER_NAME, root / REVIEW_NAME, root)
    monkeypatch.setattr(checker, "MAX_SOURCE_BYTES", 8)
    result = run(record)
    assert {row["status"] for row in result["evidence_bindings"]} == {"source-too-large"}
    assert result["binding_status"] == "not-current"


def test_finite_components_cannot_overflow_total_into_infinity(record):
    for component in record[1]["resources"]["components"]:
        component["amount"] = 1e308
    with pytest.raises(DirectionReviewError, match="resource-total-overflow"):
        run(record)


@pytest.mark.parametrize("amounts,capacity,expected,status", [
    ([0.1, 0.2], 0.3, Decimal("0.3"), "within-estimate"),
    ([10000000000000000.0, 1], 10000000000000000, 10000000000000001, "exceeds-estimate"),
    ([10 ** 40, 1], 10 ** 40, 10 ** 40 + 1, "exceeds-estimate"),
    ([Decimal("0.10000000000000000001"), Decimal("0.2")], Decimal("0.3"),
     Decimal("0.30000000000000000001"), "exceeds-estimate"),
])
def test_decimal_boundaries_do_not_invent_or_erase_resource_overruns(record, amounts, capacity, expected, status):
    resources = record[1]["resources"]
    for row, amount in zip(resources["components"], amounts):
        row["amount"] = amount
    resources["capacities"][0]["amount"] = capacity
    result = run(record)
    assert total(result)["demand"] == expected
    assert total(result)["status"] == status
    # The actual wire representation is exact JSON, not a quoted number or
    # Decimal-to-float conversion that loses a small excess again.
    wire = dumps_direction_json(result)
    parsed = json.loads(wire, parse_float=Decimal)
    assert total(parsed)["demand"] == expected
    assert not isinstance(total(parsed)["demand"], str)
    assert_boundary(result)


def test_file_reader_preserves_decimal_tokens_before_arithmetic(record):
    dossier, review, root = record
    review["resources"]["components"][0]["amount"] = Decimal("0.10000000000000000001")
    review["resources"]["components"][1]["amount"] = Decimal("0.2")
    review["resources"]["capacities"][0]["amount"] = Decimal("0.3")
    (root / REVIEW_NAME).write_text(dumps_direction_json(review), encoding="utf-8")
    result = check_direction_review(root / DOSSIER_NAME, root / REVIEW_NAME, root)
    assert total(result)["demand"] == Decimal("0.30000000000000000001")
    assert total(result)["status"] == "exceeds-estimate"
    assert result["resource_estimates"]["components"][0]["amount"] == Decimal("0.10000000000000000001")


@pytest.mark.parametrize("value", [Decimal("1e-4097"), Decimal("1e4097")])
def test_decimal_exponents_are_bounded_before_aggregate_work(record, value):
    record[1]["resources"]["components"][0]["amount"] = value
    with pytest.raises(DirectionReviewError, match="numeric-precision-limit"):
        run(record)


def test_small_yaml_alias_is_rejected_without_expansion(record):
    _, _, root = record
    # Two small aliases suffice to exercise the boundary; no oversized payload.
    (root / DOSSIER_NAME).write_text("seed: &seed [1, 2]\nother: [*seed, *seed]\ngaps: []\n", encoding="utf-8")
    with pytest.raises(DirectionReviewError, match="yaml-alias-not-supported"):
        check_direction_review(root / DOSSIER_NAME, root / REVIEW_NAME, root)


def test_direct_api_expanded_node_work_is_bounded(monkeypatch):
    import research_hub.direction_review as module
    monkeypatch.setattr(module, "MAX_JSON_NODES", 10)
    leaf = {"value": [1, 2]}
    with pytest.raises(DirectionReviewError, match="input-node-limit"):
        candidate_sha256({"id": "G1", "shared": [leaf, leaf, leaf]})


@pytest.mark.parametrize("field", ["reason", "locator", "key", "candidate-id"])
def test_non_scalar_unicode_cannot_enter_report_fields_or_keys(record, field):
    dossier, review, _ = record
    surrogate = chr(0xD800)
    if field == "reason":
        review["checks"][0]["reason"] = surrogate
    elif field == "locator":
        review["evidence"][0]["locator"] = surrogate
    elif field == "key":
        review[surrogate] = "bad key"
    else:
        dossier["gaps"][0]["id"] = surrogate
    with pytest.raises(DirectionReviewError, match="non-scalar-unicode"):
        run(record)


@pytest.mark.parametrize("number", [0, 10 ** 40, -0.0, 0.1, 1.25, 1e20, 1e-10])
def test_normal_candidate_hashes_remain_compatible_with_original_json_canonicalization(number):
    candidate = {"id": "G1", "candidate_version": 1, "number": number,
                 "statement": "年度資料 🌸", "nested": {"flag": True, "missing": None}}
    assert candidate_sha256(candidate) == independent_hash(candidate)


def test_valid_unicode_scalar_text_round_trips_without_normalization(record):
    value = "中文 🌸 e\u0301 é"
    record[1]["checks"][0]["reason"] = value
    result = json.loads(dumps_direction_json(run(record)))
    assert result["prerequisites"][0]["reason"] == value
