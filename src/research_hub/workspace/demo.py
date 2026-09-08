"""Offline example projects created only in an explicit new or empty directory."""

from __future__ import annotations

import json
from pathlib import Path
import stat

from .core import Workspace, WorkspaceError, atomic_json, safe_path
from .sample_data import summation


_WARNINGS = [
    "DEMO projects contain editable examples, not accepted research or submission-ready manuscripts.",
    "Source identity and claim support remain unverified; screening decisions are examples.",
    "The optional writing adapter is not bound. No manuscript checks, agent tasks, or human approvals were created.",
]

_SOURCES = [
    {
        "title": "What Every Computer Scientist Should Know About Floating-Point Arithmetic",
        "authors": ["David Goldberg"],
        "year": 1991,
        "doi": "10.1145/103162.103163",
        "locator": "https://docs.oracle.com/cd/E19957-01/806-3568/ncg_goldberg.html",
    },
    {
        "title": "Accurate Sum and Dot Product",
        "authors": ["Takeshi Ogita", "Siegfried M. Rump", "Shin'ichi Oishi"],
        "year": 2005,
        "doi": "10.1137/030601818",
        "locator": "https://www.tuhh.de/ti3/paper/rump/OgRuOi05.pdf",
    },
]


def _checked_root(root: str | Path) -> Path:
    if not isinstance(root, (str, Path)) or not str(root).strip():
        raise WorkspaceError("Choose an explicit new or empty demo directory")
    supplied = Path(root).expanduser()
    if ".." in supplied.parts or str(supplied).startswith(("\\\\", "//")):
        raise WorkspaceError("Demo root must be a local path without parent traversal", "unsafe_path")
    absolute = supplied.absolute()
    for component in absolute.parts[1:]:
        reserved = component.split(".")[0].upper() in {
            "CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$",
            *(f"COM{number}" for number in range(1, 10)),
            *(f"LPT{number}" for number in range(1, 10)),
        }
        if ":" in component or component.endswith((".", " ")) or reserved:
            raise WorkspaceError("Ambiguous demo path component", "unsafe_path")
    for candidate in reversed((absolute, *absolute.parents)):
        try:
            info = candidate.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise WorkspaceError("Cannot inspect the demo directory safely", "unsafe_path") from exc
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise WorkspaceError("Demo paths cannot contain symlinks or reparse points", "unsafe_path")
        if not stat.S_ISDIR(info.st_mode):
            raise WorkspaceError("Demo root and its ancestors must be directories", "unsafe_path")
    if absolute.exists() and any(absolute.iterdir()):
        raise WorkspaceError("Demo root must be new or empty; existing files were preserved", "conflict")
    if not absolute.parent.is_dir():
        raise WorkspaceError("Create the demo directory's parent first", "missing_parent")
    return absolute.resolve()


def _write(root: Path, relative: str, text: str) -> Path:
    path = safe_path(root, relative)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)
    return path


def _json(value) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n"


def _outline(workspace: Workspace, project: str, section: str, function: str,
             claim: str, evidence: str, bridge: str) -> None:
    workspace.add_record(project, kind="outline", data={
        "section": section, "function": function, "claim": claim,
        "evidence": evidence, "bridge": bridge, "example": True,
    })


def _empirical(workspace: Workspace, measured: dict) -> dict:
    project = workspace.create_project(
        id="summation-demo", title="DEMO: three floating-point summation cases",
        archetype="empirical", goal="Inspect three measured cancellation cases and edit a bounded manuscript scaffold.",
    )
    project_id = project["id"]
    source = Path(summation.__file__).read_text(encoding="utf-8")
    _write(workspace.root, "summation-demo/summation.py", source)
    _write(workspace.root, "summation-demo/analysis.json", _json(measured))
    table = "\n".join(
        f"| {case['case_id']} | {case['exact_integer_sum']} | {case['results']['naive_loop']} | "
        f"{case['results']['math_fsum']} | {case['results']['builtin_sum']} |"
        for case in measured["cases"]
    )
    _write(workspace.root, "summation-demo/manuscript.md", f"""# DEMO: floating-point summation manuscript scaffold

Editable example with measured local output. No scientific review or acceptance has occurred.

## Question

How do an explicit naive float loop, math.fsum, and built-in sum compare on these three ordered inputs?
[Add the intended audience and why this bounded question matters.]

## Methods

The accompanying summation.py evaluates exactly the inputs in analysis.json.
From the workspace directory, run `python summation-demo/summation.py` to print a fresh result without modifying files.
The JSON records the actual Python version and platform; compare runtime fields before interpreting a rerun.
[Explain the three input orders and the exact integer reference.]

## Measured results

| Case | Exact integer sum | Naive loop | math.fsum | Built-in sum |
| --- | ---: | ---: | ---: | ---: |
{table}

[Describe these observations and cite analysis.json.]

## Discussion and limits

Only three illustrative cases were measured. No timings were collected.
These outputs do not establish universal accuracy or performance claims.
[Explain the scope of each observation after checking the method and runtime.]

## Next edit

[Write a short conclusion that stays within the measured evidence.]
""")
    for name, role in (("summation.py", "analysis"), ("analysis.json", "analysis"), ("manuscript.md", "main_manuscript")):
        workspace.register_artifact(project_id, path=f"{project_id}/{name}", role=role)
    question = "How do the three summation methods compare on the three listed cancellation cases in this runtime?"
    workspace.add_record(project_id, kind="question", data={"text": question, "example": True})
    workspace.add_record(project_id, kind="analysis", data={
        "question": question,
        "method": "Run summation-demo/summation.py: explicit += loop, math.fsum(values), and sum(values).",
        "result": _json(measured["cases"]).strip(),
        "limitation": measured["limitation"],
        "artifact": "summation-demo/analysis.json", "example": True,
    })
    _outline(workspace, project_id, "Methods", "Make the calculation reproducible",
             "[Explain the ordered inputs and methods.]", "summation-demo/summation.py",
             "Use the recorded runtime to frame the results.")
    _outline(workspace, project_id, "Results", "Report the three measured comparisons",
             "[Describe the observed values without extending their scope.]", "summation-demo/analysis.json",
             "Connect each observation to its limitation.")
    _outline(workspace, project_id, "Discussion", "Bound interpretation",
             "[Explain what these three examples can establish.]", "Three cases in the recorded runtime; no timing data",
             "Conclude only from the measured examples.")
    return project


def _review(workspace: Workspace) -> dict:
    project = workspace.create_project(
        id="review-demo", title="DEMO: floating-point reading and review outline",
        archetype="review", goal="Practice source screening and outlining with two seed references; no completed review is claimed.",
    )
    project_id = project["id"]
    sources = []
    for metadata in _SOURCES:
        record = workspace.add_record(project_id, kind="source", data={
            **metadata, "identity_status": "unverified", "example": True,
            "note": "Seed bibliography supplied with the demo; no source was fetched or verified during creation.",
        })
        sources.append(record)
        workspace.add_record(project_id, kind="screening", data={
            "source_id": record["id"], "decision": "include", "example": True,
            "rationale": "Example inclusion for a two-source reading exercise. Reassess eligibility after reading the source.",
        })
    workspace.add_record(project_id, kind="question", data={
        "text": "Which assumptions and error bounds should a reader extract when comparing accounts of floating-point summation?",
        "example": True,
    })
    workspace.add_record(project_id, kind="claim", data={
        "text": "[Placeholder] Form a bounded comparison after reading both sources and recording supporting passages.",
        "source_ids": [source["id"] for source in sources], "verification_status": "unverified",
        "human_acceptance": "pending", "example": True,
    })
    _outline(workspace, project_id, "Scope and eligibility", "Define the reading exercise",
             "[Specify the question and eligibility criteria.]", "Two seed references; no search or completeness assessment",
             "Explain how evidence will be extracted.")
    _outline(workspace, project_id, "Evidence comparison", "Compare extracted evidence",
             "[Fill only after reading and checking source passages.]", "review-demo/references.json; support remains unverified",
             "Identify agreements, differences, and unresolved questions.")
    _outline(workspace, project_id, "Limitations", "Disclose the selection and evidence limits",
             "[Explain the limits of a two-source example.]", "Example screening records; no systematic search",
             "State what further reading would be needed.")
    _write(workspace.root, "review-demo/references.json", _json(sources))
    references = "\n".join(
        f"- {', '.join(source['authors'])} ({source['year']}). {source['title']}. "
        f"DOI: {source['doi']}. [Source link]({source['locator']})."
        for source in _SOURCES
    )
    _write(workspace.root, "review-demo/manuscript.md", f"""# DEMO: literature-review manuscript scaffold

Editable reading exercise. The two seed references and example inclusion decisions do not establish a complete or systematic review.
Source identity and claim support remain unverified in this workspace. No source text was downloaded.

## Scope and question

[Define a question about floating-point summation and state the intended scope.]

## Search and screening plan

[Record the planned search sources, dates, terms, and eligibility criteria.]
The supplied inclusion records are examples for two seed sources; reassess them after reading.

## Evidence comparison

[Extract assumptions, methods, error bounds, and supporting page or section locations.]
[Write claims only after checking the cited passages; identify disagreements and gaps.]

## Limitations and next steps

[Explain the selection limits, unresolved verification, and further reading needed.]

## Seed references

{references}
""")
    workspace.register_artifact(project_id, path="review-demo/references.json", role="evidence")
    workspace.register_artifact(project_id, path="review-demo/manuscript.md", role="main_manuscript")
    return project


def create_demo(root: str | Path) -> dict:
    """Create two offline examples or raise without removing partial output.

    The parent directory must already exist. Every demo file is new; an existing
    nonempty directory is refused. If an operation fails after creation starts,
    the exception identifies the preserved partial directory. Inspect that
    directory and use another new or empty root for the next attempt.
    """
    target = _checked_root(root)
    measured = summation.measure()
    try:
        target.mkdir(exist_ok=True)
        # Claim each output directory exclusively before the core writes state.
        safe_path(target, ".research").mkdir()
        if {path.name for path in target.iterdir()} != {".research"}:
            raise WorkspaceError("Demo directory changed during creation", "conflict")
        for project_id in ("summation-demo", "review-demo"):
            safe_path(target, project_id).mkdir()
        workspace = Workspace(target)
        projects = [_empirical(workspace, measured), _review(workspace)]
        for project in projects:
            if not all(item["current"] for item in workspace.artifacts(project["id"])):
                raise WorkspaceError("A demo artifact changed during creation", "conflict")
        _write(target, "README.md", """# Research workspace DEMO

This directory contains two editable examples: summation-demo (empirical) and review-demo (literature review).
Open each project's manuscript.md to start editing. analysis.json contains three real calculations with runtime metadata.
Run `python summation-demo/summation.py` from this directory to print a fresh calculation without changing existing files.

No network, accounts, LLM calls, or optional writing adapter are needed to create these projects.
The bibliography is supplied seed metadata. Source identity, claim support, screening suitability, and manuscript readiness require review.
No agent task, human approval, manuscript acceptance, or completed systematic review is supplied.

Creation only accepts a new or empty directory. A failed creation preserves partial files for inspection;
use another new or empty directory for another attempt. A complete creation contains demo.json.
""")
        result = {"ok": True, "root": str(target), "projects": projects, "warnings": list(_WARNINGS)}
        atomic_json(safe_path(target, "demo.json"), result, replace=False)
        return result
    except Exception as exc:
        raise WorkspaceError(
            f"Demo creation failed at {target}. Partial output was preserved; inspect it and choose a new or empty directory. "
            f"Cause: {type(exc).__name__}: {exc}",
            "demo_incomplete",
        ) from exc
