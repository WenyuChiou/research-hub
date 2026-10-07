"""One transport-neutral API for the researcher workspace."""

from __future__ import annotations

import json
from pathlib import Path
import uuid
import sqlite3

from .core import Workspace, WorkspaceError, encoded, now
from .tasks import TaskService


PROTECTION_SCOPE = (
    "Workspace tasks are proposal-only and retain inputs, results and human decisions. "
    "Codex produces no-tool prose; original documents remain in your editor. "
    "Legacy dashboard/MCP direct-write tools are outside this workspace approval boundary. "
    "Local approval is an operator-session assertion, not identity authentication on a shared computer."
)


class WorkspaceService:
    def __init__(self, root):
        self.workspace = Workspace(root)
        self.tasks = TaskService(self.workspace)

    def capabilities(self, *, human: bool = False) -> dict:
        from .executor import codex_capability
        from .writing import writing_capability
        return {"ok": True, "projects": self.workspace.list_projects(),
                "capabilities": {"codex": codex_capability(), "writing": writing_capability(),
                    "approval": {"status": "available" if human else "unavailable", "message": "Local operator review session enabled" if human else "Use an interactive terminal: research-hub task decide <task-id> --root <workspace> --outcome accept --actor <name> --rationale <reason>"}},
                "protection_scope": PROTECTION_SCOPE}

    def search(self, project_id, *, query: str, limit: int = 5) -> dict:
        self.workspace.project(project_id)
        if not isinstance(query, str) or not query.strip() or len(query) > 2000 or type(limit) is not int or not 1 <= limit <= 20:
            raise WorkspaceError("Search requires a query and limit between 1 and 20")
        from research_hub.search.crossref import CrossrefBackend
        import requests
        warnings = []
        class ObservedCrossref(CrossrefBackend):
            def _request(self, *args, **kwargs):
                response = super()._request(*args, **kwargs)
                if response is None:
                    warnings.append("Crossref unavailable; no successful search is claimed.")
                elif response.status_code != 200:
                    warnings.append(f"Crossref returned HTTP {response.status_code}; results may be unavailable.")
                else:
                    try:
                        response.json()
                    except ValueError:
                        warnings.append("Crossref returned invalid metadata JSON.")
                return response
        try:
            papers = ObservedCrossref(timeout=15).search(query, limit=limit)
            results = [{"source_id": p.doi or str(index), "title": p.title,
                        "locator": "https://doi.org/" + p.doi if p.doi else p.url,
                        "doi": p.doi, "identity_status": "unverified"} for index, p in enumerate(papers) if p]
        except (requests.RequestException, ValueError, TypeError, AttributeError) as exc:
            warnings.append(f"Search failed: {type(exc).__name__}")
            results = []
        record = {"query": query, "provider": "crossref", "limit": limit, "retrieved_at": now(),
                  "status": "degraded" if warnings else "completed", "results": results, "warnings": warnings}
        with self.workspace.db(write=True) as db:
            db.execute("INSERT INTO records VALUES (?,?,?,?)", (uuid.uuid4().hex, project_id, "search", encoded(record)))
        return {"ok": not warnings, "results": results, "warnings": warnings,
                **({"error": "Search provider is degraded", "code": "provider_unavailable"} if warnings else {})}

    def dispatch(self, resource: str, operation: str, data: dict | None = None, *, proof=None, background=False) -> dict:
        """Explicit operations only. No dynamic command/function names from clients."""
        values = dict(data or {})
        if resource == "project":
            if operation == "demo":
                if values:
                    raise WorkspaceError("Demo takes only an explicit empty workspace root")
                from .demo import create_demo
                return create_demo(self.workspace.root)
            if operation == "list":
                return {"ok": True, "projects": self.workspace.list_projects()}
            if operation == "create":
                return {"ok": True, "project": self.workspace.create_project(**values)}
            project_id = values.pop("project_id")
            if operation == "show":
                return self.workspace.snapshot(project_id)
            if operation == "register":
                return {"ok": True, "artifact": self.workspace.register_artifact(project_id, **values)}
            if operation == "record":
                return {"ok": True, "record": self.workspace.add_record(project_id, **values)}
            if operation == "search":
                return self.search(project_id, **values)
        elif resource == "task":
            if operation == "create":
                project_id = values.pop("project_id")
                return {"ok": True, "task": self.tasks.create(project_id, **values)}
            if operation == "list":
                return {"ok": True, "tasks": self.tasks.list(values["project_id"])}
            task_id = values.pop("task_id")
            if operation == "show":
                return {"ok": True, "task": self.tasks.get(task_id)}
            if operation == "handoff":
                return self.tasks.handoff(task_id)
            if operation == "run":
                return {"ok": True, "task": (self.tasks.launch if background else self.tasks.start)(task_id)}
            if operation == "import":
                return {"ok": True, "task": self.tasks.import_result(task_id, **values)}
            if operation == "decide":
                return {"ok": True, "task": self.tasks.decide(task_id, proof=proof, **values)}
            if operation == "cancel":
                return {"ok": True, "task": self.tasks.cancel(task_id)}
            if operation == "recover":
                return {"ok": True, "task": self.tasks.recover(task_id)}
        elif resource == "manuscript":
            project_id = values.pop("project_id")
            from .writing import WritingAdapter
            if operation == "bind":
                path = WritingAdapter().bind(self.workspace, project_id)
                return {"ok": True, "path": str(path), "state": json.loads(path.read_text(encoding="utf-8"))}
            if operation == "audit":
                return WritingAdapter().audit(self.workspace, project_id, **values)
            if operation == "state":
                return {"ok": True, "state": self.workspace.snapshot(project_id)["manuscript"]}
            if operation == "impact":
                return manuscript_impact(self.workspace, project_id)
        elif resource == "action":
            from .actions import ActionService
            actions = ActionService(self.workspace)
            if operation == "prepare":
                return {"ok": True, "action": actions.prepare_delivery(**values)}
            action_id = values.pop("action_id")
            if operation == "show":
                return {"ok": True, "action": actions.get(action_id)}
            if operation == "decide":
                return {"ok": True, "action": actions.decide(action_id, proof=proof, **values)}
            if operation == "execute":
                return {"ok": True, "action": actions.execute(action_id)}
            if operation == "reconcile":
                return {"ok": True, "action": actions.reconcile(action_id)}
        raise WorkspaceError("Unknown workspace operation", "not_found")


def call_workspace(root, resource, operation, data=None, *, proof=None, background=False) -> dict:
    try:
        if resource == "project" and operation == "demo":
            if data:
                raise WorkspaceError("Demo takes only an explicit empty workspace root")
            from .demo import create_demo
            return create_demo(root)
        return WorkspaceService(root).dispatch(resource, operation, data, proof=proof, background=background)
    except WorkspaceError as exc:
        return {"ok": False, "error": str(exc), "code": exc.code}
    except sqlite3.Error as exc:
        return {"ok": False, "error": f"Workspace ledger unavailable: {exc}", "code": "ledger_unavailable"}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {"ok": False, "error": str(exc), "code": "invalid_request"}


def manuscript_impact(workspace, project_id):
    """Conservative review impact, not a claim to understand changed science."""
    items = []
    for artifact in workspace.artifacts(project_id):
        if not artifact["current"]:
            sections = ["Methods", "Results", "Discussion", "Abstract", "Figures", "Tables", "Supplement", "Reviewer response"] if artifact["role"] in {"analysis", "evidence", "figure", "table"} else ["Manuscript", "Abstract", "Supplement", "Reviewer response"]
            items.append({"source": artifact["path"], "affected": sections, "reason": "Registered bytes changed or file is unavailable; human review required"})
    stale_tasks = []
    for task in TaskService(workspace).list(project_id):
        try:
            TaskService(workspace).check_inputs(task)
        except (WorkspaceError, OSError) as exc:
            stale_tasks.append({"task_id": task["id"], "status": task["status"], "reason": str(exc), "acceptance_current": False})
    return {"ok": True, "impacts": items, "stale_tasks": stale_tasks, "automatic_semantic_sync": False}
