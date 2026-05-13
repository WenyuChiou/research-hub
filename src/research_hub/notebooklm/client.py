"""Thin sync adapter over notebooklm-py's async NotebookLMClient."""

from __future__ import annotations

import asyncio
import inspect
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from notebooklm import (
    NotebookLMClient as _UpstreamClient,
    NotebookLMError as _UpstreamError,
    ReportFormat,
)


class NotebookLMError(Exception):
    """research-hub-specific error class wrapping NotebookLM failures."""

    def __init__(
        self,
        message: str,
        *,
        selector: str | None = None,
        page_url: str | None = None,
    ) -> None:
        super().__init__(message)
        self.selector = selector
        self.page_url = page_url


@dataclass
class UploadResult:
    """Single source upload result.

    Keeps the v0.85 field names used by CLI/tests while exposing ``ok`` as
    the v0.86 success alias.
    """

    source_kind: str = ""
    path_or_url: str = ""
    success: bool = False
    error: str = ""
    title: str = ""

    @property
    def ok(self) -> bool:
        return self.success


@dataclass(init=False)
class NotebookHandle:
    """research-hub handle for a NotebookLM notebook."""

    name: str
    url: str
    notebook_id: str

    def __init__(
        self,
        name: str | None = None,
        url: str = "",
        notebook_id: str = "",
        *,
        title: str | None = None,
    ) -> None:
        self.name = name if name is not None else (title or "")
        self.url = url
        self.notebook_id = notebook_id

    @property
    def title(self) -> str:
        return self.name

    @title.setter
    def title(self, value: str) -> None:
        self.name = value


@dataclass
class BriefingArtifact:
    """Generated briefing doc plus metadata."""

    notebook_name: str = ""
    notebook_url: str = ""
    notebook_id: str = ""
    text: str = ""
    titles: list[str] = field(default_factory=list)
    source_count: int = 0
    ok: bool = True
    error: str = ""


class NotebookLMClient:
    """Sync facade over notebooklm-py's async client."""

    def __init__(
        self,
        state_file: Path,
        *,
        headless: bool = True,
        timeout_sec: int = 120,
    ) -> None:
        del headless
        self._state_file = Path(state_file)
        self._timeout = float(timeout_sec)
        self._loop = asyncio.new_event_loop()
        self._closed = False
        try:
            self._client = self._run(self._open_client())
        except Exception as exc:
            self._loop.close()
            raise NotebookLMError(f"failed to load NLM session: {exc}") from exc

    def _run(self, awaitable):
        return self._loop.run_until_complete(awaitable)

    async def _maybe_await(self, value: Any) -> Any:
        if inspect.isawaitable(value):
            return await value
        return value

    async def _open_client(self):
        client = await self._maybe_await(
            _UpstreamClient.from_storage(
                path=str(self._state_file),
                timeout=self._timeout,
            )
        )
        enter = getattr(client, "__aenter__", None)
        if enter is not None:
            await self._maybe_await(enter())
        return client

    def _notebook_to_handle(self, notebook: Any) -> NotebookHandle:
        return NotebookHandle(
            name=getattr(notebook, "title", "") or getattr(notebook, "name", ""),
            notebook_id=getattr(notebook, "id", "") or getattr(notebook, "notebook_id", ""),
            url=getattr(notebook, "url", "") or _notebook_url(getattr(notebook, "id", "")),
        )

    def list_notebooks(self) -> list[NotebookHandle]:
        async def _go():
            return await self._client.notebooks.list()

        try:
            return [self._notebook_to_handle(item) for item in self._run(_go())]
        except Exception as exc:
            raise NotebookLMError(f"failed to list notebooks: {exc}") from exc

    def find_or_create_notebook(self, title: str) -> NotebookHandle:
        for notebook in self.list_notebooks():
            if notebook.name == title:
                return notebook
        return self.create_notebook(title)

    def open_or_create_notebook(self, name: str) -> NotebookHandle:
        return self.find_or_create_notebook(name)

    def open_notebook_by_name(self, name: str) -> NotebookHandle:
        for notebook in self.list_notebooks():
            if notebook.name == name:
                return notebook
        raise NotebookLMError(f"Notebook not found: {name}")

    def create_notebook(self, name: str) -> NotebookHandle:
        async def _go():
            return await self._client.notebooks.create(title=name)

        try:
            return self._notebook_to_handle(self._run(_go()))
        except Exception as exc:
            raise NotebookLMError(f"failed to create notebook '{name}': {exc}") from exc

    def upload_source(
        self,
        notebook_id: str,
        *,
        file_path: Path | None = None,
        url: str = "",
    ) -> UploadResult:
        async def _go():
            if file_path is not None:
                return await self._client.sources.add_file(notebook_id, path=str(file_path))
            return await self._client.sources.add_url(notebook_id, url=url)

        source_kind = "pdf" if file_path is not None else "url"
        path_or_url = str(file_path) if file_path is not None else url
        try:
            source = self._run(_go())
            title = getattr(source, "title", "") or (file_path.name if file_path else url)
            return UploadResult(
                source_kind=source_kind,
                path_or_url=path_or_url,
                success=True,
                title=title,
            )
        except _UpstreamError as exc:
            return UploadResult(source_kind=source_kind, path_or_url=path_or_url, error=str(exc))
        except Exception as exc:
            return UploadResult(source_kind=source_kind, path_or_url=path_or_url, error=str(exc))

    def upload_pdf(self, pdf_path: Path) -> UploadResult:
        notebook_id = getattr(self, "_active_notebook_id", "")
        if not notebook_id:
            raise NotebookLMError("upload_pdf requires an active notebook_id")
        return self.upload_source(notebook_id, file_path=pdf_path)

    def upload_url(self, url: str) -> UploadResult:
        notebook_id = getattr(self, "_active_notebook_id", "")
        if not notebook_id:
            raise NotebookLMError("upload_url requires an active notebook_id")
        return self.upload_source(notebook_id, url=url)

    def set_active_notebook(self, notebook_id: str) -> None:
        self._active_notebook_id = notebook_id

    def generate_briefing(self, notebook_id: str) -> BriefingArtifact:
        try:
            text = self._generate_and_download_report(notebook_id)
            return BriefingArtifact(notebook_id=notebook_id, text=text, ok=True)
        except Exception as exc:
            return BriefingArtifact(notebook_id=notebook_id, ok=False, error=str(exc))

    def download_briefing(self, handle: NotebookHandle) -> BriefingArtifact:
        try:
            text = self._download_report_text(handle.notebook_id)
            return BriefingArtifact(
                notebook_name=handle.name,
                notebook_url=handle.url,
                notebook_id=handle.notebook_id,
                text=text,
                titles=["Briefing Doc"] if text else [],
            )
        except Exception as exc:
            raise NotebookLMError(f"failed to download briefing: {exc}") from exc

    def trigger_briefing(self, notebook_id: str | None = None) -> str:
        return self._trigger_generation("brief", notebook_id)

    def trigger_audio_overview(self, notebook_id: str | None = None) -> str:
        return self._trigger_generation("audio", notebook_id)

    def trigger_mind_map(self, notebook_id: str | None = None) -> str:
        return self._trigger_generation("mind_map", notebook_id)

    def trigger_video_overview(self, notebook_id: str | None = None) -> str:
        return self._trigger_generation("video", notebook_id)

    def ask(
        self,
        notebook_id: str,
        *,
        question: str,
        source_ids: list[str] | None = None,
    ) -> dict:
        async def _go():
            return await self._client.chat.ask(
                notebook_id,
                question=question,
                source_ids=source_ids,
            )

        try:
            result = self._run(_go())
            return {
                "ok": True,
                "answer": result.answer,
                "references": [
                    {
                        "source_id": ref.source_id,
                        "citation_number": ref.citation_number or 0,
                        "cited_text": ref.cited_text or "",
                        "start_char": ref.start_char or 0,
                        "end_char": ref.end_char or 0,
                    }
                    for ref in (result.references or [])
                ],
            }
        except _UpstreamError as exc:
            return {"ok": False, "error": str(exc), "answer": "", "references": []}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "answer": "", "references": []}

    def _trigger_generation(
        self,
        kind: str,
        notebook_id: str | None = None,
        *,
        prefer_id: bool = False,
    ) -> str:
        notebook_id = notebook_id or getattr(self, "_active_notebook_id", "")
        if not notebook_id:
            raise NotebookLMError(f"{kind} generation requires a notebook_id")

        async def _go():
            if kind == "brief":
                status = await self._client.artifacts.generate_report(
                    notebook_id,
                    report_format=ReportFormat.BRIEFING_DOC,
                )
            elif kind == "audio":
                status = await self._client.artifacts.generate_audio(notebook_id)
            elif kind == "mind_map":
                status = await self._client.artifacts.generate_mind_map(notebook_id)
            elif kind == "video":
                status = await self._client.artifacts.generate_video(notebook_id)
            else:
                raise ValueError(f"Unknown generation kind: {kind}")
            task_id = getattr(status, "task_id", "") or getattr(status, "id", "")
            if task_id and hasattr(self._client.artifacts, "wait_for_completion"):
                status = await self._client.artifacts.wait_for_completion(
                    notebook_id,
                    task_id,
                    timeout=self._timeout,
                )
            return status

        try:
            status = self._run(_go())
        except _UpstreamError as exc:
            raise NotebookLMError(str(exc)) from exc
        artifact_id = getattr(status, "task_id", "") or getattr(status, "id", "")
        url = getattr(status, "url", "") or ""
        if not (artifact_id or url):
            raise NotebookLMError("Generation did not return an artifact id")
        return artifact_id if prefer_id else (url or artifact_id)

    def _generate_and_download_report(self, notebook_id: str) -> str:
        artifact_id = self._trigger_generation("brief", notebook_id, prefer_id=True)
        return self._download_report_text(notebook_id, artifact_id=artifact_id)

    def _download_report_text(self, notebook_id: str, artifact_id: str | None = None) -> str:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "briefing.md"

            async def _go():
                return await self._client.artifacts.download_report(
                    notebook_id,
                    str(out_path),
                    artifact_id=artifact_id,
                )

            self._run(_go())
            return out_path.read_text(encoding="utf-8")

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True

        async def _go():
            exit_method = getattr(self._client, "__aexit__", None)
            if exit_method is not None:
                await self._maybe_await(exit_method(None, None, None))

        try:
            self._run(_go())
        except Exception:
            pass
        finally:
            self._loop.close()


def _parse_notebook_id(url: str) -> str:
    """Extract the notebook identifier from a NotebookLM URL."""
    match = re.search(r"/notebook/([^/?#]+)", url)
    if match:
        return match.group(1)
    return url.rstrip("/").split("/")[-1] if url else ""


def _notebook_url(notebook_id: str) -> str:
    return f"https://notebooklm.google.com/notebook/{notebook_id}" if notebook_id else ""
