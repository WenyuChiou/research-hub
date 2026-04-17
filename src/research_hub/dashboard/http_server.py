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

    def log_message(self, format: str, *args) -> None:
        logger.info("%s - %s", self.address_string(), format % args)

    def _write_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
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

    def do_GET(self) -> None:
        path = urlparse(self.path).path
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
                    payload = f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode("utf-8")
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
        if not sent or not secrets.compare_digest(sent, self.csrf_token):
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

        try:
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

        self._write_json(200 if result.ok else 500, result.to_dict())


def serve_dashboard(
    cfg,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    allow_external: bool = False,
    open_browser: bool = True,
) -> None:
    if host != "127.0.0.1" and not allow_external:
        raise ValueError(f"host={host!r} refused: pass --allow-external to bind non-loopback")

    broadcaster = EventBroadcaster()
    watcher = VaultWatcher(cfg, broadcaster)
    watcher.start()

    DashboardHandler.cfg = cfg
    DashboardHandler.broadcaster = broadcaster
    DashboardHandler.csrf_token = secrets.token_urlsafe(32)

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
