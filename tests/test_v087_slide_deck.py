"""v0.87 Q3 — slide-deck artifact download parity.

Slide decks are the user's primary download artifact beyond the brief
(answer to V087_PLAN.md Q3: "一般都是簡報"). Verifies that:

- CLI parser exposes `--type slide-deck` for both generate and download
- CLI parser exposes `--slide-format {pdf,pptx}` for download
- `NotebookLMClient.trigger_slide_deck` routes to upstream
  `artifacts.generate_slide_deck`
- `NotebookLMClient.download_slide_deck` routes to upstream
  `artifacts.download_slide_deck` with the right output args
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from research_hub.notebooklm.client import NotebookHandle, NotebookLMClient


def _build_client_with_capture() -> tuple[NotebookLMClient, MagicMock]:
    upstream = MagicMock()
    upstream.artifacts.generate_slide_deck = AsyncMock(
        return_value=SimpleNamespace(task_id="t1", id="t1", status="DONE")
    )
    upstream.artifacts.download_slide_deck = AsyncMock(return_value="/tmp/slide.pdf")
    upstream.artifacts.wait_for_completion = AsyncMock(
        return_value=SimpleNamespace(status="DONE", artifact_id="a1")
    )

    @asynccontextmanager
    async def _ctx():
        yield upstream

    client = NotebookLMClient.__new__(NotebookLMClient)
    client._client = upstream
    client._timeout = 60
    client._loop = asyncio.new_event_loop()
    client._active_notebook_id = "NB42"

    def _run(coro):
        return client._loop.run_until_complete(coro)

    client._run = _run  # type: ignore[attr-defined]
    return client, upstream


def test_trigger_slide_deck_calls_upstream_generate_slide_deck() -> None:
    client, upstream = _build_client_with_capture()
    try:
        client.trigger_slide_deck(notebook_id="NB42")
    except Exception:
        # adapter return chain not the subject of this assertion
        pass

    assert upstream.artifacts.generate_slide_deck.await_count == 1
    call = upstream.artifacts.generate_slide_deck.await_args
    assert call.args[0] == "NB42"


def test_download_slide_deck_passes_output_path_and_format(tmp_path: Path) -> None:
    client, upstream = _build_client_with_capture()
    out = tmp_path / "slide-deck-test.pdf"
    handle = NotebookHandle(notebook_id="NB42", url="https://nlm/notebook/NB42")

    result = client.download_slide_deck(handle, output_path=out, output_format="pdf")

    assert result == out
    call = upstream.artifacts.download_slide_deck.await_args
    assert call.args[0] == "NB42"
    assert call.kwargs["output_path"] == str(out)
    assert call.kwargs["output_format"] == "pdf"


def test_download_slide_deck_supports_pptx_format(tmp_path: Path) -> None:
    client, upstream = _build_client_with_capture()
    out = tmp_path / "slide-deck-test.pptx"
    handle = NotebookHandle(notebook_id="NB42", url="https://nlm/notebook/NB42")

    client.download_slide_deck(handle, output_path=out, output_format="pptx")

    call = upstream.artifacts.download_slide_deck.await_args
    assert call.kwargs["output_format"] == "pptx"


def test_cli_download_accepts_slide_deck_type() -> None:
    """The argparse choices must include slide-deck for the download subcommand."""
    from research_hub.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(
        ["notebooklm", "download", "--cluster", "demo", "--type", "slide-deck"]
    )
    assert args.type == "slide-deck"
    assert args.slide_format == "pdf"  # default


def test_cli_download_accepts_pptx_slide_format() -> None:
    from research_hub.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(
        ["notebooklm", "download", "--cluster", "demo", "--type", "slide-deck",
         "--slide-format", "pptx"]
    )
    assert args.slide_format == "pptx"


def test_cli_generate_accepts_slide_deck_type() -> None:
    from research_hub.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(
        ["notebooklm", "generate", "--cluster", "demo", "--type", "slide-deck"]
    )
    assert args.type == "slide-deck"


def test_cli_download_rejects_unknown_type() -> None:
    """audio/video/mind-map remain unsupported in v0.87.0 download path."""
    from research_hub.cli import build_parser

    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(
            ["notebooklm", "download", "--cluster", "demo", "--type", "audio"]
        )
