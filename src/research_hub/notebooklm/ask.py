"""Ad-hoc Q&A against a cluster's NotebookLM notebook.

Adapted from PleasePrompto/notebooklm-skill (MIT):
https://github.com/PleasePrompto/notebooklm-skill

Patterns reused with attribution:
  - selector chains for query input and responses
  - 3-read stability polling for streaming answer text
  - thinking-message detection
  - human-like typing delays
"""

from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from research_hub.notebooklm.browser import (
    default_session_dir,
    default_state_file,
    launch_nlm_context,
)

QUERY_INPUT_SELECTORS = (
    'chat-panel textarea',
    'textarea[formcontrolname="query"]',
    'textarea[aria-label="Query box"]',
    'textarea[placeholder*="Start typing"]',
    'textarea[placeholder*="Ask"]',
    'textarea[aria-label*="問題"]',
    'textarea[aria-label*="查詢"]',
    'textarea[aria-label*="問いかけ"]',
    'textarea[aria-label*="询问"]',
    'textarea[aria-label*="질문"]',
    'div[contenteditable="true"][role="textbox"]',
    'textarea:not([formcontrolname="discoverSourcesQuery"])',
)

RESPONSE_SELECTORS = (
    "chat-message .message-content",
    "div.chat-message-text",
    "message-content",
    'message[role="assistant"] .markdown',
    '[role="log"] [role="listitem"]:last-child',
)

THINKING_MESSAGE_SELECTORS = (
    "div.thinking-message",
    '[aria-label*="Thinking"]',
    '[aria-label*="思考中"]',
    '[aria-label*="생각"]',
    ".loading-indicator",
)


def _dismiss_overlay(page) -> None:
    """Dismiss any overlay backdrop that would intercept clicks.

    NotebookLM occasionally pops an onboarding / add-source dialog when
    a notebook URL is opened fresh. The backdrop
    ``.cdk-overlay-backdrop-showing`` blocks pointer events. Press
    Escape up to three times — each press dismisses one dialog layer.
    """
    for _ in range(3):
        backdrop = page.locator(".cdk-overlay-backdrop-showing").first
        try:
            if backdrop.count() == 0:
                return
        except Exception:
            return
        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
        except Exception:
            return


@dataclass
class AskResult:
    ok: bool
    answer: str = ""
    artifact_path: Path | None = None
    latency_seconds: float = 0.0
    error: str = ""


def _open_debug_log(research_hub_dir: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = research_hub_dir / ("nlm-debug-{0}.jsonl".format(timestamp))
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


def _human_type(page, selector: str, text: str) -> None:
    """Type ``text`` into ``selector`` with randomized per-char delays."""
    element = page.locator(selector).first
    element.click()
    for char in text:
        element.type(char, delay=random.randint(25, 75))
        if random.random() < 0.08:
            time.sleep(random.uniform(0.2, 0.6))


def _find_query_input(page):
    for selector in QUERY_INPUT_SELECTORS:
        loc = page.locator(selector).first
        try:
            loc.wait_for(state="visible", timeout=3_000)
            return selector
        except Exception:
            continue
    raise RuntimeError("Could not find NotebookLM query input. UI may have changed.")


def _read_response_text(page) -> str:
    for selector in RESPONSE_SELECTORS:
        loc = page.locator(selector).last
        try:
            if loc.count() == 0:
                continue
            return (loc.inner_text() or "").strip()
        except Exception:
            continue
    return ""


def _is_thinking(page) -> bool:
    for selector in THINKING_MESSAGE_SELECTORS:
        loc = page.locator(selector).first
        try:
            if loc.count() > 0:
                return True
        except Exception:
            continue
    return False


def _wait_for_stable_answer(
    page,
    *,
    timeout_sec: int = 120,
    stable_reads_required: int = 3,
    poll_interval_sec: float = 1.0,
) -> str:
    """Poll response selectors until text stabilizes across consecutive reads."""
    start = time.time()
    last_text = ""
    stable_count = 0
    while time.time() - start < timeout_sec:
        if _is_thinking(page):
            stable_count = 0
            last_text = ""
            time.sleep(poll_interval_sec)
            continue
        text = _read_response_text(page)
        if text and text == last_text:
            stable_count += 1
            if stable_count >= stable_reads_required:
                return text
        else:
            stable_count = 1
            last_text = text
        time.sleep(poll_interval_sec)
    return last_text


def ask_cluster_notebook(
    cluster,
    cfg,
    *,
    question: str,
    headless: bool = True,
    timeout_sec: int = 120,
) -> AskResult:
    """Ask a question against the cluster's NotebookLM notebook."""
    debug_log = _open_debug_log(cfg.research_hub_dir)
    _log_jsonl(
        debug_log,
        {
            "kind": "ask_start",
            "cluster_slug": getattr(cluster, "slug", ""),
            "headless": headless,
            "timeout_sec": timeout_sec,
            "question": question,
        },
    )
    if not question.strip():
        _log_jsonl(debug_log, {"kind": "ask_error", "error": "Question must be non-empty."})
        return AskResult(ok=False, error="Question must be non-empty.")

    notebook_url = getattr(cluster, "notebooklm_notebook_url", "") or ""
    if not notebook_url:
        error = (
            "Cluster '{0}' has no notebooklm_notebook_url. Run `research-hub notebooklm "
            "upload --cluster {0}` first."
        ).format(cluster.slug)
        _log_jsonl(debug_log, {"kind": "ask_error", "error": error})
        return AskResult(ok=False, error=error)

    session_dir = default_session_dir(cfg.research_hub_dir)
    state_file = default_state_file(cfg.research_hub_dir)

    start = time.time()
    try:
        with launch_nlm_context(
            user_data_dir=session_dir,
            headless=headless,
            state_file=state_file,
        ) as (_, page):
            _log_jsonl(debug_log, {"kind": "ask_navigate", "url": notebook_url})
            page.goto(notebook_url)
            try:
                page.wait_for_load_state("networkidle", timeout=10_000)
            except Exception:
                pass
            _dismiss_overlay(page)
            query_selector = _find_query_input(page)
            _log_jsonl(debug_log, {"kind": "ask_input_found", "selector": query_selector})
            _human_type(page, query_selector, question)
            page.keyboard.press("Enter")
            _log_jsonl(debug_log, {"kind": "ask_submitted"})
            answer = _wait_for_stable_answer(
                page,
                timeout_sec=timeout_sec,
                stable_reads_required=3,
            )
    except Exception as exc:
        latency = time.time() - start
        error = "Ask failed for cluster '{0}': {1}".format(cluster.slug, exc)
        _log_jsonl(debug_log, {"kind": "ask_error", "error": error, "latency_seconds": latency})
        return AskResult(ok=False, error=error, latency_seconds=latency)

    latency = time.time() - start
    if not answer:
        error = (
            "No answer received within {0}s (NotebookLM may still be generating)."
        ).format(timeout_sec)
        _log_jsonl(debug_log, {"kind": "ask_timeout", "error": error, "latency_seconds": latency})
        return AskResult(ok=False, error=error, latency_seconds=latency)

    safe_slug = Path(cluster.slug).name
    artifacts_dir = cfg.research_hub_dir / "artifacts" / safe_slug
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    artifact_path = artifacts_dir / ("ask-{0}.md".format(timestamp))
    body = (
        "# Ad-hoc question - {0}\n\n"
        "- Asked: {1}\n"
        "- Notebook: {2}\n"
        "- Latency: {3:.1f}s\n\n"
        "## Question\n\n{4}\n\n"
        "## Answer\n\n{5}\n"
    ).format(cluster.slug, timestamp, notebook_url, latency, question, answer)
    artifact_path.write_text(body, encoding="utf-8")
    _log_jsonl(
        debug_log,
        {
            "kind": "ask_ok",
            "artifact_path": str(artifact_path),
            "latency_seconds": latency,
        },
    )
    return AskResult(
        ok=True,
        answer=answer,
        artifact_path=artifact_path,
        latency_seconds=latency,
    )
