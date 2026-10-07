"""Compare the same synthetic storage fixtures across two source revisions."""
from __future__ import annotations

import contextlib
import copy
import io
import json
import os
import tempfile
from pathlib import Path

import pytest
import yaml

from research_hub import cli, pipeline
from tests.test_pipeline import _configure, _paper
from tests.test_pipeline_v03 import _create_cluster


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def main():
    results = {"fixture": "synthetic native handoff; storage-only, identity verifier stubbed"}
    os.environ.pop("RESEARCH_HUB_NO_ZOTERO", None)
    with pytest.MonkeyPatch.context() as mp, tempfile.TemporaryDirectory(prefix="research-hub-value-", dir=Path.home()) as temp:
        cfg = _configure(mp, Path(temp), default_collection="ABCD1234")
        _create_cluster(cfg, "native-review")
        mp.setattr(pipeline, "get_config", lambda: cfg)
        mp.setattr(cli, "get_config", lambda: cfg)
        mp.setattr(pipeline.time, "sleep", lambda _: None)
        mp.setattr("research_hub.authenticity.verify_authenticity", lambda papers, *a, **kw: (papers, []))
        created, notes = [], []

        class FixtureZotero:
            def item_template(self, item_type):
                return {"itemType": item_type}

            def create_items(self, items):
                created.extend(copy.deepcopy(items))
                return {"successful": {str(i): {"key": f"TEST{i}"} for i in range(len(items))}}

        mp.setattr(pipeline, "get_client", lambda: FixtureZotero())
        mp.setattr(pipeline, "check_duplicate", lambda *a, **kw: False)
        mp.setattr(pipeline, "add_note", lambda zot, key, content: notes.append(content))
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            try:
                parsed = cli.build_parser().parse_args(["ingest", "--input", "handoff.json", "--dry-run"])
                results["explicit_input_flag"] = parsed.papers_json == "handoff.json"
            except SystemExit:
                results["explicit_input_flag"] = False

            first = _paper("Synthetic Native Research Evidence", "native-evidence", "10.1000/native")
            first["provenance"] = {"producer": "host-native", "research": {"queries": ["round one"]}}
            first["source_records"] = [{"source_id": "S1", "url": "https://example.test/article", "locator": "p. 4"}]
            second = copy.deepcopy(first)
            second["source_records"] = [{"source_id": "S2", "url": "https://example.test/mirror"}]
            path = Path(temp) / "handoff.json"
            path.write_text(json.dumps([first, second]), encoding="utf-8")

            before = snapshot(cfg.root)
            results["preview_rc"] = pipeline.run_pipeline(papers_json=path, dry_run=True, cluster_slug="native-review", query="initial, query")
            after = snapshot(cfg.root)
            results["preview_changed_files"] = sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))

            results["first_ingest_rc"] = pipeline.run_pipeline(papers_json=path, cluster_slug="native-review", query="initial, query", verify=False)
            note = cfg.raw / "native-review" / "native-evidence.md"
            text = note.read_text(encoding="utf-8")
            metadata = yaml.safe_load(text.split("---", 2)[1])
            results["inbatch_evidence_records"] = len(metadata.get("source_records") or [])
            results["initial_zotero_evidence_retained"] = bool(notes and "S1" in notes[0] and "S2" in notes[0])
            text = text.replace("status: unread", "status: deep-read") + "\n## Synthetic reading annotation\nKeep this exact body.\n"
            note.write_text(text, encoding="utf-8")
            original_body = text.split("---", 2)[2]
            update = copy.deepcopy(first)
            update["summary"] = "Do not overwrite existing reading notes"
            update["source_records"] = [{"source_id": "S3", "url": "https://example.test/correction"}]
            update["provenance"]["research"]["queries"] = ["round two"]
            path.write_text(json.dumps([update]), encoding="utf-8")
            pipeline.run_pipeline(papers_json=path, cluster_slug="native-review", query='follow-up, "citation"', verify=False)
            after = note.read_text(encoding="utf-8")
            try:
                metadata = yaml.safe_load(after.split("---", 2)[1])
                results["incremental_query_yaml_valid"] = True
                results["incremental_query_count"] = len(metadata.get("cluster_queries") or [])
                results["incremental_evidence_records"] = len(metadata.get("source_records") or [])
            except yaml.YAMLError:
                results["incremental_query_yaml_valid"] = False
                results["incremental_query_count"] = None
                results["incremental_evidence_records"] = None
            results["reading_state_and_body_preserved"] = "status: deep-read" in after and after.split("---", 2)[2] == original_body
            pipeline.run_pipeline(papers_json=path, cluster_slug="native-review", query='follow-up, "citation"', verify=False)
            results["exact_replay_note_unchanged"] = note.read_text(encoding="utf-8") == after
            results["zotero_items_created"] = len(created)
            unsafe = copy.deepcopy(first)
            unsafe["slug"] = "../../outside"
            path.write_text(json.dumps([unsafe]), encoding="utf-8")
            results["unsafe_path_preview_rc"] = pipeline.run_pipeline(papers_json=path, dry_run=True, cluster_slug="native-review")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
