"""Synthetic regression against the existing optional discovery validator/view.

This checks record handling only; caller-supplied events are not authenticated.
"""
import json
import unittest
from unittest.mock import patch

from research_hub.workspace import discovery
from research_hub.workspace.core import WorkspaceError


def profile(contrary_status, outcome, count, receipt):
    return {
        "format": "research-discovery-observations/1.0", "run_id": "fixture",
        "project_id": "p", "brief": "Synthetic research need",
        "capabilities": [{"name": "host", "kind": "search", "availability": "available", "observation": "fixture"}],
        "needs": [{"id": "n", "text": "Compare closest and boundary", "families": ["closest", "contrary"], "status": "unresolved"}],
        "attempts": [
            {"id": "closest", "need_ids": ["n"], "kind": "search", "tool": "host", "input": "closest synthetic query", "status": "observed", "outcome": "success", "result_count": 2, "receipt": {"reference": "fixture:closest", "material": None}},
            {"id": "contrary", "need_ids": ["n"], "kind": "search", "tool": "host", "input": "contrary synthetic query", "status": contrary_status, "outcome": outcome, "result_count": count, "receipt": receipt},
        ],
        "sources": [], "completion": {"status": "partial", "reason": "Boundary assessment unresolved", "residual_need_ids": ["n"]},
    }


def view(value):
    # Exercise the production shape validator, relationships and display projection.
    # The registered-file step is stubbed; no local storage or host call occurs.
    discovery._validator().validate(value)
    raw = json.dumps(value).encode("utf-8")
    item = {"id": "fixture", "sha256": "0" * 64}
    with patch.object(discovery, "_registered_profile", return_value=(item, raw, value)):
        return discovery.view_profile(None, "p", "fixture")


class MixedSearchTests(unittest.TestCase):
    def test_failure_and_unavailable_stay_distinct_from_empty(self):
        for status, outcome, receipt in [
            ("observed", "timeout", {"reference": "fixture:timeout", "material": None}),
            ("unavailable", "unknown", None),
        ]:
            with self.subTest(status=status):
                result = view(profile(status, outcome, None, receipt))
                attempts = result["discovery"]["attempts"]
                self.assertEqual(attempts[0]["outcome"], "success")
                self.assertEqual((attempts[1]["input"], attempts[1]["status"], attempts[1]["outcome"], attempts[1]["result_count"]),
                                 ("contrary synthetic query", status, outcome, None))
                self.assertEqual(result["discovery"]["completion"]["residual_need_ids"], ["n"])
                self.assertFalse(result["report"]["execution_verified"])
                self.assertEqual(result["report"]["semantic_assessment"], "not-performed")

    def test_observed_zero_retains_query_and_observation_basis(self):
        p = profile("observed", "empty", 0, {"reference": "fixture:empty", "material": None})
        result = view(p)
        attempt = result["discovery"]["attempts"][1]
        self.assertEqual((attempt["input"], attempt["status"], attempt["outcome"], attempt["result_count"]),
                         ("contrary synthetic query", "observed", "empty", 0))
        self.assertEqual(result["report"]["caller_observed_attempts"], 2)
        self.assertNotIn("receipt", attempt)  # view intentionally excludes caller references
        self.assertEqual(p["attempts"][1]["receipt"]["reference"], "fixture:empty")
        self.assertEqual(result["discovery"]["completion"]["status"], "partial")

    def test_zero_cannot_be_fabricated_from_failure_or_without_receipt(self):
        for status, outcome, count, receipt in [
            ("observed", "timeout", 0, {"reference": "fixture:timeout", "material": None}),
            ("unavailable", "unknown", 0, None),
            ("observed", "empty", 0, None),
        ]:
            with self.subTest(status=status, outcome=outcome):
                with self.assertRaises(WorkspaceError):
                    view(profile(status, outcome, count, receipt))


if __name__ == "__main__":
    unittest.main()
