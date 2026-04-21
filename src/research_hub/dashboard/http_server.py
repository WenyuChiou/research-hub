"""Localhost-only HTTP server for live dashboard interaction."""

from __future__ import annotations

import json
import logging
import secrets
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from queue import Empty
from urllib.parse import urlparse

from research_hub.api.jobs import JobQueue
from research_hub.api import v1 as api_v1

from research_hub.dashboard.data import collect_dashboard_data
from research_hub.dashboard.events import EventBroadcaster, VaultWatcher
from research_hub.dashboard.executor import execute_action
from research_hub.dashboard.render import render_dashboard_from_config

logger = logging.getLogger(__name__)


def _clean_for_json(obj):
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, dict):
        return {key: _clean_for_json(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [_clean_for_json(value) for value in obj]
    if isinstance(obj, tuple):
        return [_clean_for_json(value) for value in obj]
    return obj


def _serialize_dashboard_data(cfg) -> dict:
    data = collect_dashboard_data(cfg)
    return _clean_for_json(asdict(data))


def _resolve_version() -> str:
    # Prefer the in-source __version__ so editable / dev installs report the
    # right version. Fall back to the installed-package metadata only if the
    # in-source attribute is missing (extremely unusual).
    try:
        from research_hub import __version__ as _v
        if _v:
            return str(_v)
    except Exception:
        pass
    try:
        from importlib.metadata import version as _v
        return _v("research-hub-pipeline")
    except Exception:
        return "unknown"


class DashboardHandler(BaseHTTPRequestHandler):
    cfg = None
    broadcaster: EventBroadcaster
    csrf_token = ""
    version = _resolve_version()
    api_token: str | None = None
    job_queue = JobQueue()

    def log_message(self, format: str, *args) -> None:
        logger.info("%s - %s", self.address_string(), format % args)

    def _write_json(self, status: int, payload: dict, *, extra_headers: dict[str, str] | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _write_html(self, status: int, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _serve_artifact(self, raw_target: str) -> None:
        """Serve an artifact file from inside the vault root, with safety check.

        v0.53.2: replaces the dashboard's old `file:///C:/...` href which
        modern browsers refuse to follow from an http:// page (mixed
        protocol, blocked silently). Now the dashboard links to
        `/artifact?path=<rel>` and the server reads the file safely.

        Path is treated as either an absolute path inside cfg.root or a
        relative path resolved against cfg.root. Anything resolving
        OUTSIDE cfg.root is rejected with 403 to prevent path traversal.
        """
        if not raw_target:
            self._write_json(400, {"error": "missing path"})
            return
        try:
            from urllib.parse import unquote
            target = Path(unquote(raw_target))
            if not target.is_absolute():
                target = (Path(self.cfg.root) / target).resolve()
            else:
                target = target.resolve()
            vault_root = Path(self.cfg.root).resolve()
            try:
                target.relative_to(vault_root)
            except ValueError:
                self._write_json(403, {"error": "path is outside the vault"})
                return
            if not target.exists() or not target.is_file():
                self._write_json(404, {"error": "file not found"})
                return
            if target.suffix.lower() in {".txt", ".md", ".json", ".log", ".yaml", ".yml"}:
                ctype = "text/plain; charset=utf-8"
            elif target.suffix.lower() == ".html":
                ctype = "text/html; charset=utf-8"
            elif target.suffix.lower() == ".pdf":
                ctype = "application/pdf"
            else:
                ctype = "application/octet-stream"
            data = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
        except Exception as exc:
            self._write_json(500, {"error": f"could not serve artifact: {exc}"})

    def _handle_artifact_delete(self) -> None:
        """v0.57: delete a single artifact file from inside the vault.

        Same path-traversal protection as `_serve_artifact`. CSRF + origin
        checks performed inline since this is a mutating operation.
        """
        from urllib.parse import parse_qs, unquote

        # Origin + CSRF (mirrors /api/exec)
        origin = self.headers.get("Origin", "")
        host_header = self.headers.get("Host", "")
        allowed_origins = {
            f"http://{host_header}",
            f"http://127.0.0.1:{self.server.server_port}",
        }
        if origin and origin not in allowed_origins:
            self._write_json(403, {"ok": False, "error": "origin not allowed"})
            return
        sent = self.headers.get("X-CSRF-Token", "")
        if self.csrf_token and (not sent or not secrets.compare_digest(sent, self.csrf_token)):
            self._write_json(403, {"ok": False, "error": "csrf token mismatch"})
            return

        qs = parse_qs(urlparse(self.path).query)
        raw_target = (qs.get("path") or [""])[0]
        if not raw_target:
            self._write_json(400, {"ok": False, "error": "missing path"})
            return
        try:
            target = Path(unquote(raw_target))
            if not target.is_absolute():
                target = (Path(self.cfg.root) / target).resolve()
            else:
                target = target.resolve()
            vault_root = Path(self.cfg.root).resolve()
            try:
                target.relative_to(vault_root)
            except ValueError:
                self._write_json(403, {"ok": False, "error": "path is outside the vault"})
                return
            if not target.exists():
                self._write_json(404, {"ok": False, "error": "file not found"})
                return
            if target.is_dir():
                self._write_json(400, {"ok": False, "error": "refuses to delete directories"})
                return
            target.unlink()
            # Notify dashboards in other tabs that vault state changed.
            try:
                self.broadcaster.broadcast({"type": "vault_changed", "reason": "artifact-deleted"})
            except Exception:
                pass
            self._write_json(200, {"ok": True, "deleted": str(target.relative_to(vault_root))})
        except Exception as exc:
            self._write_json(500, {"ok": False, "error": f"could not delete artifact: {exc}"})

    def _api_v1_headers(self, extra_headers: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Authorization, Content-Type",
        }
        if extra_headers:
            headers.update(extra_headers)
        return headers

    def _write_api_v1_json(
        self,
        status: int,
        payload: dict,
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self._write_json(status, payload, extra_headers=self._api_v1_headers(extra_headers))

    def _write_api_v1_error(self, status: int, code: str, message: str) -> None:
        self._write_api_v1_json(status, {"ok": False, "error": message, "code": code})

    def _check_api_v1_auth(self, path: str) -> bool:
        token = self.api_token
        if not token or path == "/api/v1/health":
            return True
        sent = self.headers.get("Authorization", "")
        expected = f"Bearer {token}"
        if sent and secrets.compare_digest(sent, expected):
            return True
        self._write_api_v1_error(401, "unauthorized", "Missing or invalid bearer token.")
        return False

    def _read_json_body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError as exc:
            raise api_v1.ApiError(400, "bad_request", "Invalid Content-Length header.") from exc
        if length <= 0 or length > 64 * 1024:
            raise api_v1.ApiError(400, "bad_request", "Request body must be non-empty and under 64 KiB.")
        try:
            body = self.rfile.read(length).decode("utf-8")
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise api_v1.ApiError(400, "bad_request", "Malformed JSON request body.") from exc
        except UnicodeDecodeError as exc:
            raise api_v1.ApiError(400, "bad_request", "Request body must be UTF-8 JSON.") from exc
        if not isinstance(payload, dict):
            raise api_v1.ApiError(400, "bad_request", "Request body must be a JSON object.")
        return payload

    def _dispatch_api_v1(self, method: str, path: str) -> None:
        if not self._check_api_v1_auth(path):
            return
        try:
            payload = None
            if method == "POST":
                payload = self._read_json_body()
            result = self._route_api_v1(method, path, payload)
        except api_v1.ApiError as exc:
            self._write_api_v1_error(exc.status, exc.code, exc.message)
            return
        except Exception:
            logger.exception("api v1 dispatch failed")
            self._write_api_v1_error(500, "internal_error", "The server failed to process the request.")
            return

        body, status, extra_headers = result
        self._write_api_v1_json(status, body, extra_headers=extra_headers)

    def _route_api_v1(self, method: str, path: str, payload: dict | None) -> tuple[dict, int, dict[str, str] | None]:
        request = {
            "cfg": self.cfg,
            "json": payload,
            "job_queue": self.job_queue,
            "method": method,
            "path": path,
            "path_params": {},
        }
        segments = [segment for segment in path.split("/") if segment]
        if len(segments) < 3 or segments[0] != "api" or segments[1] != "v1":
            raise api_v1.ApiError(404, "not_found", "Requested resource was not found.")
        tail = segments[2:]

        if method == "GET":
            if tail == ["health"]:
                return api_v1.get_health(request), 200, None
            if tail == ["clusters"]:
                return api_v1.get_clusters(request), 200, None
            if len(tail) == 2 and tail[0] == "clusters":
                request["path_params"] = {"slug": tail[1]}
                return api_v1.get_cluster(request), 200, None
            if len(tail) == 3 and tail[0] == "clusters" and tail[2] == "crystals":
                request["path_params"] = {"slug": tail[1]}
                return api_v1.get_cluster_crystals(request), 200, None
            if len(tail) == 4 and tail[0] == "clusters" and tail[2] == "crystals":
                request["path_params"] = {"slug": tail[1], "crystal_slug": tail[3]}
                return api_v1.get_cluster_crystal(request), 200, None
            if len(tail) == 4 and tail[0] == "clusters" and tail[2] == "memory":
                request["path_params"] = {"slug": tail[1], "kind": tail[3]}
                return api_v1.get_cluster_memory(request), 200, None
            if len(tail) == 2 and tail[0] == "jobs":
                request["path_params"] = {"job_id": tail[1]}
                return api_v1.get_job(request), 200, None

        if method == "POST":
            if tail == ["search"]:
                return api_v1.post_search(request), 200, None
            if tail == ["websearch"]:
                return api_v1.post_websearch(request), 200, None
            if tail == ["plan"]:
                return api_v1.post_plan(request), 200, None
            if tail == ["ask"]:
                return api_v1.post_ask(request), 200, None
            if tail == ["auto"]:
                result = api_v1.post_auto(request)
                if isinstance(result, tuple) and len(result) == 3:
                    return result
                return result, 202, None

        raise api_v1.ApiError(404, "not_found", "Requested resource was not found.")

    def do_OPTIONS(self) -> None:
        path = urlparse(self.path).path
        if path.startswith("/api/v1/"):
            self.send_response(204)
            for key, value in self._api_v1_headers().items():
                self.send_header(key, value)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path.startswith("/api/v1/"):
            self._dispatch_api_v1("GET", path)
            return
        if path in {"/", "/index.html"}:
            try:
                self._write_html(
                    200,
                    render_dashboard_from_config(self.cfg, csrf_token=self.csrf_token),
                )
            except Exception as exc:
                logger.exception("dashboard render failed")
                self._write_json(500, {"error": str(exc)})
            return

        if path == "/healthz":
            self._write_json(200, {"ok": True, "version": self.version, "mode": "live"})
            return

        if path == "/artifact":
            # v0.53.2: serve files inside the vault over HTTP so the dashboard
            # can link to them. Browsers block file:// hrefs from http://
            # pages (mixed-protocol security), which made "open .txt" appear
            # blank. Path is taken from query string; we resolve + verify it
            # stays inside cfg.root before serving.
            from urllib.parse import parse_qs
            qs = parse_qs(urlparse(self.path).query)
            raw_target = (qs.get("path") or [""])[0]
            try:
                self._serve_artifact(raw_target)
            except Exception as exc:
                logger.exception("artifact serve failed")
                self._write_json(500, {"error": str(exc)})
            return

        if path == "/api/state":
            try:
                self._write_json(200, _serialize_dashboard_data(self.cfg))
            except Exception as exc:
                logger.exception("state collection failed")
                self._write_json(500, {"error": str(exc)})
            return

        if path == "/api/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            queue = self.broadcaster.subscribe()
            try:
                hello = json.dumps({"csrf_token": self.csrf_token}, ensure_ascii=False).encode("utf-8")
                self.wfile.write(b"event: hello\n")
                self.wfile.write(b"data: ")
                self.wfile.write(hello)
                self.wfile.write(b"\n\n")
                self.wfile.flush()
                while True:
                    try:
                        event = queue.get(timeout=30)
                    except Empty:
                        self.wfile.write(b": heartbeat\n\n")
                        self.wfile.flush()
                        continue
                    event_name = ""
                    payload_obj = event
                    if isinstance(event, dict):
                        event_name = str(event.get("event", "") or "").strip()
                        if event_name:
                            payload_obj = {key: value for key, value in event.items() if key != "event"}
                    if event_name:
                        self.wfile.write(f"event: {event_name}\n".encode("utf-8"))
                    payload = f"data: {json.dumps(payload_obj, ensure_ascii=False)}\n\n".encode("utf-8")
                    self.wfile.write(payload)
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                self.broadcaster.unsubscribe(queue)
            return

        self._write_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path.startswith("/api/v1/"):
            self._dispatch_api_v1("POST", path)
            return
        if path == "/artifact-delete":
            # v0.57: per-artifact delete from the dashboard's NotebookLM
            # artifacts table. Same CSRF + origin protection as /api/exec
            # since this also mutates vault state.
            self._handle_artifact_delete()
            return
        if path != "/api/exec":
            self._write_json(404, {"error": "not found"})
            return

        origin = self.headers.get("Origin", "")
        host_header = self.headers.get("Host", "")
        allowed_origins = {
            f"http://{host_header}",
            f"http://127.0.0.1:{self.server.server_port}",
        }
        if origin and origin not in allowed_origins:
            self._write_json(403, {"error": "origin not allowed"})
            return

        sent = self.headers.get("X-CSRF-Token", "")
        if self.csrf_token and (not sent or not secrets.compare_digest(sent, self.csrf_token)):
            self._write_json(403, {"error": "csrf token mismatch"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            length = 0
        if length <= 0 or length > 64 * 1024:
            self._write_json(400, {"error": "invalid content length"})
            return

        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            self._write_json(400, {"error": "invalid json"})
            return

        action = str(payload.get("action", "")).strip()
        slug = payload.get("slug")
        fields = payload.get("fields") or {}
        timeout = payload.get("timeout", None)
        if timeout is None:
            timeout_seconds = 300
        else:
            try:
                timeout_seconds = int(timeout)
            except (TypeError, ValueError):
                self._write_json(400, {"error": "timeout must be an integer"})
                return
            if timeout_seconds <= 0:
                self._write_json(400, {"error": "timeout must be > 0"})
                return

        try:
            try:
                result = execute_action(action, slug, fields, timeout=timeout_seconds)
            except TypeError as exc:
                if "unexpected keyword argument 'timeout'" not in str(exc):
                    raise
                result = execute_action(action, slug, fields)
        except ValueError as exc:
            self._write_json(400, {"error": str(exc)})
            return
        except Exception as exc:
            logger.exception("execute failed")
            self._write_json(500, {"error": str(exc)})
            return

        if result.ok:
            self.broadcaster.broadcast(
                {
                    "type": "vault_changed",
                    "reason": "exec",
                    "action": result.action,
                }
            )
            self.broadcaster.broadcast(
                {
                    "event": "state-change",
                    "action": result.action,
                    "reason": "exec",
                }
            )

        response = result.to_dict()
        if not result.ok and result.returncode == -1 and "timeout" in result.stderr.lower():
            response["error"] = "timeout"
        elif not result.ok and result.stderr:
            response["error"] = result.stderr

        self._write_json(200, response)


def serve_dashboard(
    cfg,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    allow_external: bool = False,
    open_browser: bool = True,
    api_token: str | None = None,
) -> None:
    if host != "127.0.0.1" and not allow_external:
        raise ValueError(f"host={host!r} refused: pass --allow-external to bind non-loopback")
    if not api_token and host != "127.0.0.1":
        raise ValueError("host must remain 127.0.0.1 when no API token is configured")

    broadcaster = EventBroadcaster(maxsize=100, drop_oldest_on_full=True)
    watcher = VaultWatcher(cfg, broadcaster)
    watcher.start()

    DashboardHandler.cfg = cfg
    DashboardHandler.broadcaster = broadcaster
    DashboardHandler.csrf_token = secrets.token_urlsafe(32)
    DashboardHandler.api_token = api_token
    DashboardHandler.job_queue = JobQueue()

    server = ThreadingHTTPServer((host, port), DashboardHandler)
    logger.info("dashboard server listening on http://%s:%d/", host, port)

    if open_browser:
        import webbrowser

        webbrowser.open(f"http://{host}:{port}/")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("shutting down dashboard server")
    finally:
        watcher.stop()
        server.server_close()
