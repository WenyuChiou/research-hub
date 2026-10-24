"""Temporary abstract UI fixtures; no runner or scientific acceptance.

Importable without Playwright so offline preflight can verify fixture contracts.
All paths belong to the caller's temporary workspace, never a private vault.
"""
from __future__ import annotations

import os

from research_hub.workspace.core import digest
from research_hub.workspace.tasks import TaskService, _LOCAL_HUMAN

ABSTRACT = "研究😀: No reduction was reported.\r\nOnly two synthetic samples."
SOURCE = "UNSELECTED_HEADER\r\n" + ABSTRACT + "\r\nUNSELECTED_TAIL"


def prepare_abstract_fixtures(workspace):
    if os.environ.get("RESEARCH_HUB_WRITING_ADAPTER", "").strip():
        raise RuntimeError("Abstract browser fixtures require no external writing adapter")
    project_id = "abstract-journey-fixture"
    workspace.create_project(
        id=project_id, title="Synthetic abstract journey",
        goal="Transport fixtures only; no model or scientific acceptance.",
    )
    path = workspace.root / "browser-abstract-source.txt"
    path.write_bytes(SOURCE.encode("utf-8"))
    artifact = workspace.register_artifact(project_id, path=path.name, role="evidence")
    record = workspace.add_record(project_id, kind="source", data={
        "title": "Synthetic selected source", "locator": "fixture:abstract-source",
    })
    other = workspace.add_record(project_id, kind="source", data={
        "title": "Synthetic unselected source", "locator": "fixture:unselected",
    })
    selection = {
        "artifact_id": artifact["id"], "source_record_id": record["id"],
        "start": SOURCE.index(ABSTRACT), "end": SOURCE.index(ABSTRACT) + len(ABSTRACT),
    }
    tasks = TaskService(workspace)
    accepted = {}
    for name in ("changed", "current"):
        task = tasks.create(project_id, operation="paper-abstract-draft",
                            mode="handoff", source_selection=selection)
        task = tasks.import_result(task["id"], input_hash=digest(task["request"]),
                                   draft_response={
            "summary": [{"text": "Synthetic transport statement; not a quality judgement.",
                         "quote": ABSTRACT}],
            "findings": [], "methodology": [], "limitations": [],
        })
        tasks.decide(task["id"], outcome="accept", actor="synthetic-browser-fixture",
                     rationale="Decision plumbing only, not scientific approval",
                     action_hash=task["action_hash"], proof=_LOCAL_HUMAN)
        task = tasks.get(task["id"])
        assert task["freshness"]["status"] == "current"
        # Mutate a generated candidate, never the registered source.
        candidate = next(a for a in task["result"]["artifacts"]
                         if a["path"].endswith("draft.md"))
        accepted[name] = {"id": task["id"], "path": workspace.root / candidate["path"]}
    return {"project_id": project_id, "source": record, "other_source": other,
            "artifact": artifact, "selection": selection, "source_path": path,
            "accepted": accepted}
