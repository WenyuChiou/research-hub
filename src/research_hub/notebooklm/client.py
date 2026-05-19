"""Thin sync adapter over notebooklm-py's async NotebookLMClient."""

from __future__ import annotations

import asyncio
import inspect
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from notebooklm import (
    NotebookLMClient as _UpstreamClient,
    NotebookLMError as _UpstreamError,
    ReportFormat,
)
from research_hub.errors import ResearchHubError


CLUSTER_SYNTHESIS_PROMPT = """\
Synthesize across ALL sources in this notebook. For each major theme \
that recurs in multiple sources, write a section that:
- names the theme
- lists which sources contribute and what each says
- notes points of agreement and disagreement

Cover every source at least once. Do NOT default-focus on one paper. \
End with an "Open questions across the cluster" section that surfaces \
gaps, contradictions, and follow-up directions raised by more than one \
source.
"""


class NotebookLMError(ResearchHubError):
    """research-hub-specific error class wrapping NotebookLM failures."""

    error_code = "notebooklm_error"

    def __init__(
        self,
        message: str,
        *,
        selector: str | None = None,
        page_url: str | None = None,
    ) -> None:
        super().__init__(
            message,
            context={"selector": selector, "page_url": page_url},
        )
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
        keepalive_sec: int | None = None,
    ) -> None:
        del headless
        self._state_file = Path(state_file)
        self._timeout = float(timeout_sec)
        # keepalive_sec: None = disabled (fast single-RPC paths like health probe);
        # positive integer = enable background cookie-rotation loop via upstream.
        # Values below the upstream floor of 60 s are clamped up by upstream.
        self._keepalive_sec = keepalive_sec
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
        # Pass keepalive through to the upstream client so the background
        # cookie-rotation loop (which elicits __Secure-1PSIDTS refresh) runs
        # for long sessions.  keepalive=None (the default) keeps the loop OFF
        # for trivial one-RPC calls (health probe, notebooks.list, etc.) so
        # check_session_health / doctor stays fast.  The upstream floor is
        # 60 s; values below it are clamped up automatically.
        kwargs: dict = {
            "path": str(self._state_file),
            "timeout": self._timeout,
        }
        if self._keepalive_sec is not None:
            kwargs["keepalive"] = float(self._keepalive_sec)
        client = await self._maybe_await(
            _UpstreamClient.from_storage(**kwargs)
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
        text: str = "",
        title: str = "",
    ) -> UploadResult:
        async def _go():
            if file_path is not None:
                # v0.88.10: notebooklm-py 0.4.x renamed the file kwarg from
                # `path=` to `file_path=` (see notebooklm._sources.SourcesAPI
                # .add_file signature: (notebook_id, file_path, mime_type, ...)).
                # The previous `path=` call raised TypeError on every PDF
                # upload — Stage B saw 0/5 PDF uploads succeed because of
                # this single bug, masked by 3-retry indiscriminate backoff
                # in upload.py::_attempt_upload.
                return await self._client.sources.add_file(notebook_id, file_path=str(file_path))
            if text:
                # F8 content ladder: when no PDF/OA is available, the
                # abstract (already in the vault) is uploaded as a
                # copied-text source — real content NotebookLM can use,
                # vs a paywall URL it can't.
                return await self._client.sources.add_text(
                    notebook_id, title=title or "Untitled", content=text
                )
            return await self._client.sources.add_url(notebook_id, url=url)

        if file_path is not None:
            source_kind, path_or_url = "pdf", str(file_path)
        elif text:
            source_kind, path_or_url = "text", (title or text[:60])
        else:
            source_kind, path_or_url = "url", url
        try:
            source = self._run(_go())
            source_title = getattr(source, "title", "") or (
                file_path.name if file_path is not None
                else title if text          # F8: keep caller's paper title
                else url
            )
            return UploadResult(
                source_kind=source_kind,
                path_or_url=path_or_url,
                success=True,
                title=source_title,
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

    def upload_text(self, text: str, *, title: str = "") -> UploadResult:
        notebook_id = getattr(self, "_active_notebook_id", "")
        if not notebook_id:
            raise NotebookLMError("upload_text requires an active notebook_id")
        return self.upload_source(notebook_id, text=text, title=title)

    def set_active_notebook(self, notebook_id: str) -> None:
        self._active_notebook_id = notebook_id

    def list_sources(self, notebook_id: str) -> list[Any]:
        """Return sources in a notebook through the upstream sources API."""

        async def _go():
            return await self._client.sources.list(notebook_id)

        try:
            return list(self._run(_go()))
        except _UpstreamError as exc:
            raise NotebookLMError(f"failed to list sources: {exc}") from exc
        except Exception as exc:
            raise NotebookLMError(f"failed to list sources: {exc}") from exc

    def source_fulltext(self, notebook_id: str, source_id: str) -> Any:
        """Return indexed fulltext for one source if the SDK exposes it."""

        async def _go():
            sources_api = self._client.sources
            getter = getattr(sources_api, "get_fulltext", None) or getattr(sources_api, "fulltext", None)
            if getter is None:
                raise NotebookLMError("NotebookLM sources API does not expose fulltext")
            try:
                return await getter(notebook_id, source_id)
            except TypeError:
                return await getter(source_id)

        try:
            return self._run(_go())
        except _UpstreamError as exc:
            raise NotebookLMError(f"failed to fetch source fulltext: {exc}") from exc
        except Exception as exc:
            raise NotebookLMError(f"failed to fetch source fulltext: {exc}") from exc

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

    def download_slide_deck(
        self,
        handle: NotebookHandle,
        *,
        output_path: Path,
        output_format: str = "pdf",
    ) -> Path:
        """Download the latest slide deck for a notebook (PDF or PPTX).

        Returns the saved path. Raises NotebookLMError on RPC failure.
        """
        async def _go():
            await self._client.artifacts.download_slide_deck(
                handle.notebook_id,
                output_path=str(output_path),
                output_format=output_format,
            )
            return output_path

        try:
            return self._run(_go())
        except _UpstreamError as exc:
            raise NotebookLMError(f"failed to download slide deck: {exc}") from exc
        except Exception as exc:
            raise NotebookLMError(f"failed to download slide deck: {exc}") from exc

    def trigger_briefing(self, notebook_id: str | None = None) -> str:
        return self._trigger_generation("brief", notebook_id)

    def trigger_audio_overview(self, notebook_id: str | None = None) -> str:
        return self._trigger_generation("audio", notebook_id)

    def trigger_mind_map(self, notebook_id: str | None = None) -> str:
        return self._trigger_generation("mind_map", notebook_id)

    def trigger_video_overview(self, notebook_id: str | None = None) -> str:
        return self._trigger_generation("video", notebook_id)

    def trigger_slide_deck(self, notebook_id: str | None = None) -> str:
        return self._trigger_generation("slide_deck", notebook_id)

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
                # v0.87 N2: default brief = cluster synthesis, not single-source
                # briefing doc. The NLM auto-briefing pattern focuses on whichever
                # source it judges most prominent, which produces a 1-of-N brief
                # for multi-paper clusters. CUSTOM + a synthesis prompt forces
                # cross-paper coverage. (Locked decision in V087_PLAN.md §N2.)
                status = await self._client.artifacts.generate_report(
                    notebook_id,
                    report_format=ReportFormat.CUSTOM,
                    custom_prompt=CLUSTER_SYNTHESIS_PROMPT,
                )
            elif kind == "audio":
                status = await self._client.artifacts.generate_audio(notebook_id)
            elif kind == "mind_map":
                status = await self._client.artifacts.generate_mind_map(notebook_id)
            elif kind == "video":
                status = await self._client.artifacts.generate_video(notebook_id)
            elif kind == "slide_deck":
                status = await self._client.artifacts.generate_slide_deck(notebook_id)
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

    async def _save_state(self) -> None:
        """v0.88.7: persist rotated Google cookies back to state.json.

        Google rotates short-lived auth tokens (SIDCC / SIDTS / OSID /
        CSRF) during each session. Without this, the local state.json
        captured at ``notebooklm login`` time stays frozen — subsequent
        research-hub runs load increasingly-stale cookies, and Google
        eventually rejects them with "Authentication expired or
        invalid" (which presents to the user as "the login keeps
        getting wiped"). Calling notebooklm-py's
        ``save_cookies_to_storage`` after each successful client
        lifetime persists the freshly-rotated jar, with the upstream
        helper's OS-level file lock to keep concurrent CLI runs safe.

        Best-effort: state-save failure must never poison the
        operation that actually succeeded.
        """
        try:
            from notebooklm.auth import save_cookies_to_storage
        except Exception:
            return
        auth = getattr(self._client, "auth", None)
        if auth is None:
            return
        cookie_jar = getattr(auth, "cookie_jar", None)
        storage_path = getattr(auth, "storage_path", None)
        if cookie_jar is None or not storage_path:
            return
        try:
            from pathlib import Path as _Path
            storage_path_obj = _Path(str(storage_path))
            save_cookies_to_storage(cookie_jar, storage_path_obj)
            # G3 P1 #2: rotating cookie persistence also writes state.json
            # — re-tighten to 0600 each time so cookie rotation doesn't
            # silently relax perms back to 0644 on some platforms.
            from research_hub.notebooklm.auth import _tighten_state_file_perms
            _tighten_state_file_perms(storage_path_obj)
        except Exception as exc:
            # v0.90.0 G1#2 fix: still best-effort (don't poison successful
            # operation), but surface the failure so the next session's
            # auth-expired error has a breadcrumb to root cause. Pre-fix
            # silently swallowed all save errors.
            print(
                f"  [nlm] WARN cookie persistence to {storage_path} failed: "
                f"{type(exc).__name__}: {exc}",
                file=sys.stderr,
            )

    def refresh_and_save(self) -> None:
        """v0.88.7: force a token refresh + state.json write mid-session.

        Optional opportunistic hook for long-running flows (e.g. bulk
        upload of 30+ sources) where you want the cookie jar persisted
        before the next leg, not only at close().
        """
        async def _go():
            refresh = getattr(self._client, "refresh_auth", None)
            if refresh is not None:
                try:
                    await self._maybe_await(refresh())
                except Exception:
                    pass
            await self._save_state()

        try:
            self._run(_go())
        except Exception:
            pass

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True

        async def _go():
            # v1.0.0 Fix-3: upstream ClientCore.close() / __aexit__ always
            # persists the live cookie jar via its own _save_lock-serialized
            # save_cookies() call (try/finally in ClientCore.close ensures
            # it runs on ALL exit paths, including exceptions).  The old
            # research-hub _save_state() was redundant AND racy — it called
            # save_cookies_to_storage() directly, bypassing the upstream
            # threading.Lock, so it could race against an in-flight keepalive
            # save and let an older snapshot overwrite freshly rotated tokens.
            # Removing it here means exactly ONE lock-serialized save per
            # close(), which is always the freshest jar.
            exit_method = getattr(self._client, "__aexit__", None)
            if exit_method is not None:
                await self._maybe_await(exit_method(None, None, None))
            # Preserve G3 P1 #2: upstream's on-close save_cookies() writes
            # state.json (Google auth cookies) but does NOT restrict perms.
            # The removed _save_state() used to re-harden after each cookie
            # write; re-tighten here AFTER the authoritative upstream write
            # so cookie rotation can't silently relax state.json to 0644 on
            # some platforms. Best-effort: never poison a successful op.
            try:
                from research_hub.notebooklm.auth import _tighten_state_file_perms

                _tighten_state_file_perms(self._state_file)
            except Exception:
                pass

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
