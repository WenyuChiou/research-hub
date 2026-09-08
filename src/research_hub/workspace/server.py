"""Loopback-only researcher UI. Does not inherit legacy dashboard CORS."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import mimetypes
from pathlib import Path
import secrets
from urllib.parse import unquote, urlsplit
import webbrowser

from .core import WorkspaceError, encoded, safe_path
from .service import WorkspaceService, call_workspace
from .tasks import _LOCAL_HUMAN


class WorkspaceServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, root, *, port=8765, human=False):
        self.service = WorkspaceService(root)
        self.csrf = secrets.token_urlsafe(32)
        self.human = secrets.token_urlsafe(32) if human else None
        self.static = Path(__file__).resolve().parents[1] / "workspace_static"
        super().__init__(("127.0.0.1", port), WorkspaceHandler)


class WorkspaceHandler(BaseHTTPRequestHandler):
    server: WorkspaceServer

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, format, *args):
        # Paths may contain private project/task identifiers. No access log.
        return

    def _reply(self, status, body, content_type="application/json; charset=utf-8"):
        if not isinstance(body, bytes):
            body = encoded(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(body)

    def _trusted_origin(self):
        expected = f"127.0.0.1:{self.server.server_port}"
        if self.headers.get("Host") != expected:
            return False
        origin = self.headers.get("Origin")
        if origin and origin != f"http://{expected}":
            return False
        return self.headers.get("Sec-Fetch-Site") not in {"cross-site", "same-site"}

    def do_GET(self):
        if not self._trusted_origin():
            return self._reply(403, {"ok": False, "error": "Untrusted origin", "code": "forbidden"})
        path = unquote(urlsplit(self.path).path)
        try:
            if path == "/api/v1/workspace":
                return self._reply(200, self.server.service.capabilities(human=bool(self.server.human)))
            segments = path.strip("/").split("/")
            if len(segments) == 4 and segments[:2] == ["api", "v1"]:
                resource = {"projects": "project", "tasks": "task", "actions": "action"}.get(segments[2])
                if resource:
                    return self._result(call_workspace(self.server.service.workspace.root, resource, "show", {f"{resource}_id": segments[3]}))
            if path in {"/", "/app", "/app/"}:
                target = safe_path(self.server.static, "index.html", exists=True)
                html = target.read_text(encoding="utf-8")
                meta = f'<meta name="research-hub-csrf-token" content="{self.server.csrf}">'
                if self.server.human:
                    meta += f'<meta name="research-hub-human-token" content="{self.server.human}">'
                return self._reply(200, html.replace("</head>", meta + "</head>").encode("utf-8"), "text/html; charset=utf-8")
            if path.startswith("/app/assets/"):
                target = safe_path(self.server.static, path[len("/app/"):], exists=True)
                return self._reply(200, target.read_bytes(), mimetypes.guess_type(target.name)[0] or "application/octet-stream")
            return self._reply(404, {"ok": False, "error": "Not found", "code": "not_found"})
        except (OSError, ValueError) as exc:
            self._reply(400, {"ok": False, "error": str(exc), "code": "invalid_request"})

    def _result(self, result):
        self._reply(200 if result.get("ok") else (403 if result.get("code") == "human_required" else 400), result)

    def do_POST(self):
        if not self._trusted_origin() or not hmac.compare_digest(self.headers.get("X-CSRF-Token", ""), self.server.csrf):
            return self._reply(403, {"ok": False, "error": "Untrusted request", "code": "forbidden"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 2_100_000 or self.headers.get_content_type() != "application/json":
                raise WorkspaceError("A bounded application/json body is required")
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise WorkspaceError("Request must be an object")
            parts = unquote(urlsplit(self.path).path).strip("/").split("/")
            resource = operation = None
            proof = None
            if parts == ["api", "v1", "projects"]:
                resource, operation = "project", "create"
            elif parts == ["api", "v1", "workspace", "demo"]:
                resource, operation = "project", "demo"
            elif len(parts) == 5 and parts[:2] == ["api", "v1"]:
                if parts[2] == "projects":
                    data["project_id"] = parts[3]
                    operation = {"artifacts": "register", "records": "record", "search": "search", "tasks": "create", "bind": "bind", "audit": "audit", "impact": "impact", "delivery": "prepare"}.get(parts[4])
                    resource = "task" if parts[4] == "tasks" else "action" if parts[4] == "delivery" else "manuscript" if parts[4] in {"bind", "audit", "impact"} else "project"
                elif parts[2] == "tasks":
                    resource = "task"
                    data["task_id"] = parts[3]
                    operation = {"run": "run", "handoff": "handoff", "result": "import", "decision": "decide", "cancel": "cancel", "recover": "recover"}.get(parts[4])
                    if operation == "decide" and self.server.human and hmac.compare_digest(self.headers.get("X-Human-Token", ""), self.server.human):
                        proof = _LOCAL_HUMAN
                elif parts[2] == "actions":
                    resource = "action"
                    data["action_id"] = parts[3]
                    operation = {"decision": "decide", "execute": "execute", "reconcile": "reconcile"}.get(parts[4])
                    if operation == "decide" and self.server.human and hmac.compare_digest(self.headers.get("X-Human-Token", ""), self.server.human):
                        proof = _LOCAL_HUMAN
            if not operation:
                raise WorkspaceError("Unknown workspace route", "not_found")
            self._result(call_workspace(self.server.service.workspace.root, resource, operation, data, proof=proof, background=True))
        except (ValueError, OSError) as exc:
            self._reply(400, {"ok": False, "error": str(exc), "code": "invalid_request"})


def serve_workspace(root, *, port=8765, open_browser=True, human=False):
    server = WorkspaceServer(root, port=port, human=human)
    url = f"http://127.0.0.1:{server.server_port}/app/"
    print(f"Research workspace: {url}")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    finally:
        server.server_close()
