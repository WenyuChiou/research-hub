"""Ad-hoc Q&A against a cluster's NotebookLM notebook."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from research_hub.notebooklm.auth import default_state_file
from research_hub.notebooklm.client import NotebookLMClient, _parse_notebook_id


@dataclass
class AskCitation:
    """Structured citation linking answer text to a source paper."""

    source_id: str
    citation_number: int = 0
    cited_text: str = ""
    start_char: int = 0
    end_char: int = 0


@dataclass
class AskResult:
    ok: bool
    answer: str = ""
    error: str = ""
    references: list[AskCitation] = field(default_factory=list)
    artifact_path: Path | None = None
    latency_seconds: float = 0.0


def _open_debug_log(research_hub_dir: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = research_hub_dir / f"nlm-debug-{timestamp}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _log_jsonl(path: Path, event: dict) -> None:
    payload = dict(event)
    payload["ts"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    try:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass


def ask_cluster_notebook(
    cluster,
    cfg,
    *,
    question: str,
    headless: bool = True,
    timeout_sec: int = 120,
) -> AskResult:
    """Ask a question against the cluster's NotebookLM notebook."""
    started = time.time()
    debug_log = _open_debug_log(cfg.research_hub_dir)
    _log_jsonl(
        debug_log,
        {
            "kind": "ask_start",
            "cluster_slug": getattr(cluster, "slug", ""),
            "question": question,
            "headless": headless,
            "timeout_sec": timeout_sec,
        },
    )
    if not question.strip():
        _log_jsonl(debug_log, {"kind": "ask_error", "error": "Question must be non-empty."})
        return AskResult(ok=False, error="Question must be non-empty.")

    notebook_url = getattr(cluster, "notebooklm_notebook_url", "") or ""
    notebook_id = getattr(cluster, "notebooklm_notebook_id", "") or _parse_notebook_id(notebook_url)
    if not notebook_id:
        error = f"Cluster '{cluster.slug}' has no notebooklm_notebook_url."
        _log_jsonl(debug_log, {"kind": "ask_error", "error": error})
        return AskResult(ok=False, error=error)

    state_file = default_state_file(cfg.research_hub_dir)
    if not state_file.exists():
        error = "No NLM session. Run `research-hub notebooklm login --auto-detect` first."
        _log_jsonl(debug_log, {"kind": "ask_error", "error": error})
        return AskResult(ok=False, error=error)

    client = None
    try:
        client = NotebookLMClient(state_file, headless=headless, timeout_sec=timeout_sec)
        result = client.ask(notebook_id, question=question)
    except Exception as exc:
        latency = time.time() - started
        _log_jsonl(debug_log, {"kind": "ask_error", "error": str(exc), "latency_seconds": latency})
        return AskResult(ok=False, error=str(exc), latency_seconds=latency)
    finally:
        if client is not None:
            client.close()

    latency = time.time() - started
    if not result.get("ok"):
        error = result.get("error", "unknown error")
        _log_jsonl(debug_log, {"kind": "ask_error", "error": error, "latency_seconds": latency})
        return AskResult(ok=False, error=error, latency_seconds=latency)

    references = [
        AskCitation(
            source_id=item.get("source_id", ""),
            citation_number=item.get("citation_number", 0),
            cited_text=item.get("cited_text", ""),
            start_char=item.get("start_char", 0),
            end_char=item.get("end_char", 0),
        )
        for item in result.get("references", [])
    ]
    answer = result.get("answer", "")
    artifact_path = _write_ask_artifact(
        cluster,
        cfg,
        question=question,
        answer=answer,
        notebook_url=notebook_url or f"https://notebooklm.google.com/notebook/{notebook_id}",
        latency_seconds=latency,
        references=references,
    )
    _log_jsonl(
        debug_log,
        {
            "kind": "ask_ok",
            "answer_len": len(answer),
            "ref_count": len(references),
            "artifact_path": str(artifact_path),
            "latency_seconds": latency,
        },
    )
    return AskResult(
        ok=True,
        answer=answer,
        references=references,
        artifact_path=artifact_path,
        latency_seconds=latency,
    )


def _write_ask_artifact(
    cluster,
    cfg,
    *,
    question: str,
    answer: str,
    notebook_url: str,
    latency_seconds: float,
    references: list[AskCitation],
) -> Path:
    safe_slug = Path(cluster.slug).name
    artifacts_dir = cfg.research_hub_dir / "artifacts" / safe_slug
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    artifact_path = artifacts_dir / f"ask-{timestamp}.md"
    body = (
        f"# Ad-hoc question - {cluster.slug}\n\n"
        f"- Asked: {timestamp}\n"
        f"- Notebook: {notebook_url}\n"
        f"- Latency: {latency_seconds:.1f}s\n\n"
        f"## Question\n\n{question}\n\n"
        f"## Answer\n\n{answer}\n"
    )
    if references:
        body += "\n## References\n\n"
        for ref in references:
            body += f"- [{ref.citation_number}] {ref.source_id}: {ref.cited_text}\n"
    artifact_path.write_text(body, encoding="utf-8")
    return artifact_path
