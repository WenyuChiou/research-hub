"""Explicitly configured public skill bundle; no copied scientific rules."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import stat

from research_hub.locks import file_lock
from .core import WorkspaceError, atomic_json, file_hash, safe_path


PREFIX = "skills/academic-writing-skills/"
MANUSCRIPT_ROLES = {"main_manuscript", "supplement", "reviewer_response"}
SCRIPTS = {
    "state": "audit_manuscript_state.py", "consistency": "audit_text_consistency.py",
    "prose": "audit_prose_patterns.py", "candidate": "audit_candidate_text.py",
    "docx": "audit_docx_structure.py", "regression": "run_regression_tests.py",
}


def check_alignment(workspace, project_id: str, state: dict) -> None:
    """Refuse stale binding without rewriting public manuscript authority."""
    if (not isinstance(state, dict) or not isinstance(state.get("project"), dict)
            or state["project"].get("id") != project_id):
        raise WorkspaceError("Manuscript state belongs to another project", "stale_alignment")
    artifacts = state.get("artifacts")
    contract = state.get("contract")
    if (not isinstance(artifacts, list) or not isinstance(contract, dict)
            or not isinstance(contract.get("questions"), list)
            or any(not isinstance(a, dict) or any(not isinstance(a.get(k), str) for k in ("id", "path", "role", "status")) for a in artifacts)
            or any(not isinstance(q, dict) or any(not isinstance(q.get(k), str) for k in ("id", "text")) for q in contract["questions"])):
        raise WorkspaceError("Malformed manuscript alignment; original state preserved", "stale_alignment")
    expected = {(a["id"], a["path"], a["role"]) for a in workspace.artifacts(project_id) if a["role"] in MANUSCRIPT_ROLES}
    actual = {(a.get("id"), a.get("path"), a.get("role")) for a in state.get("artifacts", []) if a.get("status") == "ACTIVE"}
    sources = state.get("authority_sources", [])
    if not isinstance(sources, list) or any(not isinstance(s, dict) or not isinstance(s.get("id"), str) for s in sources):
        raise WorkspaceError("Malformed manuscript authority sources", "stale_alignment")
    sources_by_id = {s["id"]: s for s in sources}
    for artifact in workspace.artifacts(project_id):
        if artifact["role"] not in MANUSCRIPT_ROLES:
            source = sources_by_id.get(artifact["id"], {})
            if (source.get("path_or_reference") != artifact["path"] or not isinstance(source.get("scope"), list)
                    or artifact["role"] not in source["scope"]):
                raise WorkspaceError("Manuscript research authority alignment is stale; review existing state explicitly", "stale_alignment")
    questions = {(r["id"], r["data"]["text"]) for r in workspace.records(project_id) if r["kind"] == "question"}
    bound_questions = {(q.get("id"), q.get("text")) for q in state.get("contract", {}).get("questions", [])}
    if expected != actual or not questions.issubset(bound_questions):
        raise WorkspaceError("Manuscript alignment is stale. Review manuscript_state.json against project show, explicitly update intended artifact IDs/paths and questions, then bind again. Existing authority was preserved.", "stale_alignment")


class WritingAdapter:
    def __init__(self, root=None):
        configured = str(root or os.environ.get("RESEARCH_HUB_WRITING_ADAPTER", "")).strip()
        if not configured:
            raise WorkspaceError("Configure a trusted public writing bundle with RESEARCH_HUB_WRITING_ADAPTER", "adapter_unavailable")
        original = Path(configured).expanduser().absolute()
        if original.is_symlink() or (original.exists() and getattr(original.lstat(), "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
            raise WorkspaceError("Writing bundle root must not be a symlink", "unsafe_path")
        self.root = original.resolve()
        manifest_path = safe_path(self.root, "adapter.json", exists=True)
        self.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (not isinstance(self.manifest, dict) or self.manifest.get("schema_version") != 1
                or self.manifest.get("id") != "academic-writing-skills"
                or not isinstance(self.manifest.get("adapter_version"), str)
                or not isinstance(self.manifest.get("operations"), dict)
                or any(not isinstance(value, dict) for value in self.manifest["operations"].values())
                or not isinstance(self.manifest.get("entrypoints"), dict)):
            raise WorkspaceError("Unsupported writing adapter contract", "adapter_invalid")
        files = self.manifest.get("files")
        if not isinstance(files, dict) or not files:
            raise WorkspaceError("Writing adapter has no verified files", "adapter_invalid")
        for relative, expected in files.items():
            if not isinstance(relative, str) or Path(relative).is_absolute() or "\\" in relative:
                raise WorkspaceError("Adapter paths must be relative portable paths", "adapter_invalid")
            if file_hash(safe_path(self.root, relative, exists=True)) != expected:
                raise WorkspaceError(f"Writing bundle changed: {relative}", "adapter_changed")
        for name, script in SCRIPTS.items():
            expected = PREFIX + "scripts/" + script
            if self.manifest.get("operations", {}).get(name, {}).get("script") != expected or expected not in files:
                raise WorkspaceError("Writing adapter operation does not match the supported public contract", "adapter_invalid")
        self.template_path = PREFIX + "assets/manuscript_state_template.json"
        if self.manifest.get("entrypoints", {}).get("state_template") != self.template_path or self.template_path not in files:
            raise WorkspaceError("Missing public manuscript state template", "adapter_invalid")
        self.sha256 = file_hash(manifest_path)
        for script in (self.root / PREFIX / "scripts").rglob("*.py"):
            relative = script.relative_to(self.root).as_posix()
            if relative not in files:
                raise WorkspaceError("Unverified Python file in writing script directory", "adapter_invalid")

    def instructions(self, skill: str) -> dict[str, str]:
        if skill not in {"academic-writing-skills", "paper-review"}:
            raise WorkspaceError("Unsupported writing skill")
        paths = [f"skills/{skill}/SKILL.md"]
        generic = ("universal-integrity.md", "state-and-authority.md", "lifecycle-and-routing.md",
                   "prose-and-citation-editing.md", "reviewer-red-team-and-release.md", "reviewer-response-workflow.md")
        if skill == "paper-review":
            generic = ("round-calibration.md", "display-notation-provenance.md", "overlay-contract.md")
        paths.extend(f"skills/{skill}/references/{name}" for name in generic)
        result = {}
        for path in paths:
            if path not in self.manifest["files"]:
                raise WorkspaceError("Writing bundle lacks required instructions", "adapter_invalid")
            result[path] = safe_path(self.root, path, exists=True).read_text(encoding="utf-8")
        return result

    def bind(self, workspace, project_id: str) -> Path:
        project = workspace.project(project_id)
        path = safe_path(workspace.root, workspace.project_dir(project_id) / "manuscript_state.json")
        with file_lock(path):
            if path.exists():
                check_alignment(workspace, project_id, json.loads(path.read_text(encoding="utf-8")))
                return path
            state = json.loads(safe_path(self.root, self.template_path, exists=True).read_text(encoding="utf-8"))
            artifacts = workspace.artifacts(project_id)
            state["project"].update(id=project_id, title=project["title"], archetype=project["archetype"])
            # Manuscript artifacts are documents to edit/audit. Code, data and
            # figures remain authority sources and frozen task inputs, not prose.
            state["artifacts"] = [{"id": a["id"], "path": a["path"], "role": a["role"], "status": "ACTIVE", "required_for_release": a["role"] in {"main_manuscript", "supplement"}} for a in artifacts if a["role"] in MANUSCRIPT_ROLES]
            state["authority_sources"] = [{"id": a["id"], "kind": "research_artifact", "path_or_reference": a["path"], "scope": [a["role"]], "status": "UNVERIFIED", "last_verified": ""} for a in artifacts if a["role"] in {"analysis", "evidence", "figure", "table"}]
            questions = [r for r in workspace.records(project_id) if r["kind"] == "question"]
            state["contract"]["questions"] = [{"id": r["id"], "text": r["data"]["text"], "lock": "SEMANTIC"} for r in questions]
            state["contract"]["task"] = project["goal"]
            state["alignment"] = [{"question_id": r["id"], "method": "", "evidence": "", "result": "", "interpretation": "", "limitation": "", "contribution": "", "status": "PLANNED"} for r in questions]
            state["release"]["candidate_artifact_ids"] = [a["id"] for a in artifacts if a["role"] == "main_manuscript"]
            atomic_json(path, state, replace=False)
        return path

    def audit(self, workspace, project_id: str, operation: str = "state", candidate: str | None = None) -> dict:
        if operation not in SCRIPTS:
            raise WorkspaceError("Unsupported writing check")
        # Recheck bytes immediately before execution. Trust comes from explicit
        # operator configuration, not self-asserted hashes in an arbitrary URL.
        verified = WritingAdapter(self.root)
        state = self.bind(workspace, project_id)
        document = json.loads(state.read_text(encoding="utf-8"))
        checked = {a["path"]: a["sha256"] for a in workspace.artifacts(project_id)}
        if any(not a["current"] for a in workspace.artifacts(project_id)):
            raise WorkspaceError("Registered input changed before manuscript check", "stale_input")
        state_hash = file_hash(state)
        if candidate:
            checked[candidate] = file_hash(safe_path(workspace.root, candidate, exists=True))
        for artifact in document.get("artifacts", []):
            safe_path(workspace.root, artifact["path"])
        script = safe_path(self.root, PREFIX + "scripts/" + SCRIPTS[operation], exists=True)
        # Isolated mode omits even the script directory. Restore ONLY the
        # verified public helper directory so sibling audit imports work.
        bootstrap = "import runpy,sys; sys.path.insert(0,sys.argv[1]); sys.argv=sys.argv[2:]; runpy.run_path(sys.argv[0],run_name='__main__')"
        args = [sys.executable, "-I", "-c", bootstrap, str(script.parent), str(script)]
        if operation in {"state", "consistency", "prose"}:
            args += [str(state), "--project-root", str(workspace.root), "--json"]
        elif operation == "candidate":
            if not candidate:
                raise WorkspaceError("Candidate check requires an exact file")
            args += [str(state), str(safe_path(workspace.root, candidate, exists=True)), "--json"]
        elif operation == "docx":
            paths = [str(safe_path(workspace.root, a["path"], exists=True)) for a in workspace.artifacts(project_id) if a["path"].lower().endswith(".docx")]
            if not paths:
                raise WorkspaceError("No registered DOCX artifact")
            args += [*paths, "--json"]
        try:
            result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", timeout=90, cwd=workspace.root, shell=False)
        except subprocess.TimeoutExpired as exc:
            raise WorkspaceError("Writing check timed out; no PASS recorded", "timeout") from exc
        try:
            report = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise WorkspaceError("Writing check returned invalid JSON; no PASS recorded", "invalid_output") from exc
        if not isinstance(report, (dict, list)):
            raise WorkspaceError("Writing check returned an invalid report", "invalid_output")
        if file_hash(state) != state_hash or any(file_hash(safe_path(workspace.root, path, exists=True)) != checksum for path, checksum in checked.items()):
            raise WorkspaceError("Input changed during manuscript check; report is stale", "stale_input")
        return {"ok": result.returncode == 0, "operation": operation, "report": report,
                "exit_code": result.returncode, "adapter_sha256": verified.sha256,
                "checked_artifacts": checked, "manuscript_state_sha256": state_hash,
                "semantic_acceptance": "not_performed"}


def writing_capability() -> dict:
    try:
        adapter = WritingAdapter()
        return {"status": "available", "message": f"Verified writing adapter {adapter.manifest['adapter_version']}", "sha256": adapter.sha256}
    except (WorkspaceError, OSError, ValueError, TypeError) as exc:
        return {"status": "unavailable", "message": str(exc)}
