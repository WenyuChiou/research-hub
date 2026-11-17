"""Offline rubric contracts, not model execution or scientific-quality scoring."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "skills/research-hub/evals/evals.json"
MIRROR = ROOT / "src/research_hub/skills_data/research-hub/evals/evals.json"


class Stage1EvalContract(unittest.TestCase):
    def setUp(self):
        self.rows = json.loads(SOURCE.read_text(encoding="utf-8"))["evals"]

    def row(self, prompt):
        matches = [row for row in self.rows if row["prompt"] == prompt]
        self.assertEqual(len(matches), 1, "Expected one rubric case for this prompt")
        return matches[0]["expected_behavior"]

    def test_notebook_is_not_blanket_provider_authorization(self):
        behavior = self.rows[0]["expected_behavior"]
        for required in ("Clarify only the unresolved notebook destination", "Do not infer Zotero, Obsidian or NotebookLM", "within existing authorization", "not a quota", "actual reading depth"):
            self.assertIn(required, behavior)
        self.assertNotIn('Drive `research-hub auto', behavior)

    def test_native_route_without_setup_or_storage(self):
        behavior = self.row("Find about 12 papers on human-agent decision behavior, abstracts first and two core papers closely. No storage; Research Hub is not installed.")
        for required in ("available native", "Do not require Hub installation", "Do not repeat supplied count/depth", "closest", "contrary", "versions", "reading", "no destination writes"):
            self.assertIn(required, behavior)

    def test_failed_search_is_not_zero_yield_or_completion(self):
        behavior = self.row("Continue this literature review: one search timed out, another paper has only an abstract, and the closest study has conflicting preprint and journal claims.")
        for required in ("not zero results", "abstract-only", "exact version", "unresolved", "partial", "Do not manufacture", "not proof of novelty"):
            self.assertIn(required, behavior)

    def test_unrelated_existing_cases_are_retained(self):
        self.assertEqual(len(self.rows), 6)
        self.assertIn("only run `--apply` after the user confirms", self.rows[3]["expected_behavior"])
        self.assertEqual(self.rows[1]["prompt"], "Ingest the PDFs in ./papers into a cluster called my-review.")
        self.assertEqual(self.rows[2]["prompt"], "Show me the dashboard.")

    def test_packaged_rubric_matches_source(self):
        self.assertEqual(SOURCE.read_bytes(), MIRROR.read_bytes())


if __name__ == "__main__":
    unittest.main()
