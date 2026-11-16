"""Offline observation consistency checks, not execution or scientific verification."""
import copy
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from tests.test_native_reader import fixture, reader


class NativeObservationConsistencyTests(unittest.TestCase):
    def value(self):
        return fixture()[0]

    def accepted(self, value):
        before = copy.deepcopy(value)
        result = reader.observations_view(value)
        self.assertEqual(set(result), {s["id"] for s in value["sources"]})
        self.assertEqual(value, before, "validation must not rewrite observations")

    def rejected(self, value, reason):
        before = copy.deepcopy(value)
        with self.assertRaisesRegex(reader.ReaderError, reason):
            reader.observations_view(value)
        self.assertEqual(value, before, "rejection must preserve caller records")

    def test_unobserved_attempts_never_claim_results(self):
        for status in ("planned", "declared", "unavailable"):
            for changes in ({"outcome": "success"}, {"result_count": 0}):
                with self.subTest(status=status, changes=changes):
                    value = self.value()
                    value["attempts"][0].update(status=status, outcome="unknown",
                                               result_count=None, tool=None, receipt=None)
                    value["attempts"][0].update(changes)
                    self.rejected(value, "Unobserved attempts")

    def test_unobserved_unknown_attempts_remain_useful(self):
        for status in ("planned", "declared", "unavailable"):
            value = self.value()
            value["attempts"][0].update(status=status, outcome="unknown",
                                       result_count=None, tool=None, receipt=None)
            self.accepted(value)

    def test_observed_requires_named_tool_and_nonempty_receipt(self):
        for changes, reason in (
            ({"tool": None}, "Observed attempts"),
            ({"receipt": None}, "Observed attempts"),
            ({"receipt": {"reference": None, "material": None}}, "Empty receipt"),
        ):
            with self.subTest(changes=changes):
                value = self.value()
                value["attempts"][0].update(changes)
                self.rejected(value, reason)

    def test_material_only_receipt_is_not_opened_or_authenticated(self):
        value = self.value()
        value["attempts"][0]["receipt"] = {
            "reference": None, "material": {"path": "not-present.txt", "sha256": "a" * 64}}
        self.accepted(value)

    def test_failed_and_unknown_counts_cannot_be_zero_or_positive(self):
        for outcome in ("timeout", "denied", "error", "unknown"):
            for count in (0, 1):
                with self.subTest(outcome=outcome, count=count):
                    value = self.value()
                    value["attempts"][0].update(kind="search", outcome=outcome,
                                               result_count=count)
                    self.rejected(value, "failed result count")

    def test_failures_with_unknown_counts_remain_in_partial_result(self):
        for outcome in ("timeout", "denied", "error", "unknown"):
            value = self.value()
            value["attempts"][0].update(kind="search", outcome=outcome, result_count=None)
            self.accepted(value)

    def test_empty_is_an_observed_search_with_zero_results(self):
        for kind, count in (("read", None), ("read", 0), ("search", None), ("search", 1)):
            with self.subTest(kind=kind, count=count):
                value = self.value()
                value["attempts"][0].update(kind=kind, outcome="empty", result_count=count)
                self.rejected(value, "Empty search")
        value = self.value()
        value["attempts"][0].update(kind="search", outcome="empty", result_count=0)
        self.accepted(value)

    def test_reads_have_no_search_result_count(self):
        for outcome in ("success", "partial"):
            for count in (0, 1):
                with self.subTest(outcome=outcome, count=count):
                    value = self.value()
                    value["attempts"][0].update(outcome=outcome, result_count=count)
                    self.rejected(value, "Read observations")
            value = self.value()
            value["attempts"][0].update(outcome=outcome, result_count=None)
            self.accepted(value)

    def test_attempts_and_sources_need_at_least_one_known_need(self):
        for field in ("attempts", "sources"):
            value = self.value()
            value[field][0]["need_ids"] = []
            self.rejected(value, "need references")

    def test_unresolved_and_unassessed_needs_cannot_disappear(self):
        for status in ("unresolved", "not-assessed"):
            for completion in ("partial", "continue", "bounded-complete"):
                with self.subTest(status=status, completion=completion):
                    value = self.value()
                    value["needs"][0]["status"] = status
                    value["completion"].update(status=completion, residual_need_ids=[])
                    self.rejected(value, "Unresolved needs")

    def test_bounded_complete_cannot_retain_residual_needs(self):
        value = self.value()
        value["needs"][0]["status"] = "covered"
        value["completion"]["status"] = "bounded-complete"
        self.rejected(value, "bounded-complete")

    def test_covered_needs_require_linked_observed_success_or_empty(self):
        for changes in (
            {"status": "planned", "outcome": "unknown", "tool": None, "receipt": None},
            {"outcome": "partial"},
            {"outcome": "timeout"},
            {"outcome": "unknown"},
        ):
            with self.subTest(changes=changes):
                value = self.value()
                value["needs"][0]["status"] = "covered"
                value["completion"].update(status="bounded-complete", residual_need_ids=[])
                value["attempts"][0].update(changes)
                self.rejected(value, "Covered needs")

    def test_success_on_a_different_need_does_not_cover_this_one(self):
        value = self.value()
        value["needs"].append({"id": "N2", "text": "Other need", "families": ["other"],
                               "status": "covered"})
        self.rejected(value, "Covered needs")

    def test_success_then_failure_does_not_erase_valid_covered_observation(self):
        value = self.value()
        value["needs"][0]["status"] = "covered"
        value["completion"].update(status="bounded-complete", residual_need_ids=[])
        failed = copy.deepcopy(value["attempts"][0])
        failed.update(id="A2", outcome="timeout")
        value["attempts"].append(failed)
        self.accepted(value)

    def test_empty_search_does_not_gain_scientific_acceptance(self):
        value = self.value()
        value["needs"][0]["status"] = "covered"
        value["attempts"][0].update(kind="search", outcome="empty", result_count=0)
        value["completion"].update(status="bounded-complete", residual_need_ids=[])
        self.accepted(value)
        self.assertNotIn("human_acceptance", value)
        self.assertNotIn("semantic_support", value)

    def test_supplied_source_does_not_require_fabricated_search_history(self):
        value = self.value()
        value["attempts"] = []
        for source in value["sources"]:
            source["attempt_ids"] = []
        self.accepted(value)
        self.assertIsNone(value["sources"][2]["version"])
        self.assertIsNone(value["sources"][2]["material"])

    def test_invalid_input_fails_before_cli_generates_or_check_only_writes(self):
        with tempfile.TemporaryDirectory(prefix="reader-observation-") as temp:
            root = Path(temp).resolve()
            path = root / "observations.json"
            value = self.value()
            value["attempts"][0].update(kind="search", outcome="timeout", result_count=0)
            raw = reader.canonical(value)
            path.write_bytes(raw)
            for mode in ("check", "generate"):
                output = root / mode
                flags = ["--check-only"] if mode == "check" else ["--output-dir", str(output)]
                stdout, stderr = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    result = reader.main(["--observations", str(path), *flags])
                self.assertEqual(result, 1)
                self.assertEqual(stdout.getvalue(), "")
                self.assertEqual(json.loads(stderr.getvalue())["status"], "failed")
                self.assertFalse(output.exists())
                self.assertEqual(path.read_bytes(), raw)


if __name__ == "__main__":
    unittest.main()
