"""Loopback-only researcher UI. Does not inherit legacy dashboard CORS."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import mimetypes
from pathlib import Path
import secrets
import sys
import time
from urllib.parse import unquote, urlsplit
import webbrowser

from .core import WorkspaceError, encoded, safe_path
from .integrations import LocalIntegrationsManager
from .service import WorkspaceService, call_workspace
from .tasks import _LOCAL_HUMAN
from .obsidian_validation import ObsidianValidation
from .library_snapshot import LibrarySnapshot, read_vault_snapshot
from .sync_hooks import WorkspaceSyncHooks
from .agent_chat import WorkspaceAgentBridge


class WorkspaceServer(ThreadingHTTPServer):
    daemon_threads = True
    _service_type = WorkspaceService

    def __init__(self, root, *, port=8765, human=False, obsidian_vault=None, library_snapshot=None, integrations_config=None):
        self.library_snapshot = LibrarySnapshot(library_snapshot)
        self.integrations = LocalIntegrationsManager(integrations_config)
        effective_vault = obsidian_vault
        if effective_vault is None and integrations_config is not None:
            candidate_vault = self.integrations.default_vault_root()
            if candidate_vault is not None:
                try:
                    probe = ObsidianValidation(candidate_vault)
                    probe.assert_storage_outside(root)
                    effective_vault = candidate_vault
                except ValueError:
                    effective_vault = None
        self.obsidian_validation = ObsidianValidation(effective_vault)
        self.obsidian_validation.assert_storage_outside(root)
        self.service = self._service_type(root)
        self.service.workspace.initialize_preparations()
        self.sync_hooks = WorkspaceSyncHooks(
            self.service.workspace,
            self.integrations,
            obsidian_validation=self.obsidian_validation,
        )
        self.agent_bridge = WorkspaceAgentBridge(
            self.service.workspace,
            sync_hooks=self.sync_hooks,
        )
        self.csrf = secrets.token_urlsafe(32)
        self.human = secrets.token_urlsafe(32) if human else None
        self.static = Path(__file__).resolve().parents[1] / "workspace_static"
        super().__init__(("127.0.0.1", port), WorkspaceHandler)

    def _call(self, resource, operation, data=None, *, proof=None, background=False):
        # Keep the constructor-selected service; no request selects a backend.
        return call_workspace(self.service.workspace.root, resource, operation, data,
                              proof=proof, background=background, _service=self.service)


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
                result = self.server.service.capabilities(human=bool(self.server.human))
                obs_val = getattr(self.server, "obsidian_validation", None)
                lib_snap = getattr(self.server, "library_snapshot", None)
                if obs_val is not None:
                    result["capabilities"]["obsidian_validation"] = obs_val.capability()
                result["capabilities"]["obsidian_snapshot_available"] = bool(
                    (lib_snap is not None and getattr(lib_snap, "path", None) is not None)
                    or (obs_val is not None and getattr(obs_val, "scope", None) is not None)
                )
                integrations = getattr(self.server, "integrations", None)
                if integrations is not None and integrations.enabled:
                    result["capabilities"]["local_integrations"] = integrations.capability()
                return self._reply(200, result)
            if path == "/api/v1/integrations/status":
                integrations = getattr(self.server, "integrations", None)
                if integrations is None:
                    return self._reply(403, {"ok": False, "code": "integrations_unavailable", "error": "Local integrations are unavailable in this server mode."})
                result = integrations.status()
                return self._reply(200 if result.get("ok") else 403, result)
            if path == "/api/v1/library/snapshot":
                if urlsplit(self.path).query:
                    return self._reply(400, {"ok": False, "code": "invalid_request", "error": "Snapshot requests accept no path parameters."})
                if self.server.library_snapshot.path is not None:
                    result = self.server.library_snapshot.read()
                elif self.server.obsidian_validation.scope is not None:
                    result = read_vault_snapshot(self.server.obsidian_validation.scope)
                else:
                    result = self.server.library_snapshot.read()
                return self._reply(404 if result.get("ok") is False else 200, result)
            segments = path.strip("/").split("/")
            if (len(segments) == 7 and segments[:3] == ["api", "v1", "projects"]
                    and segments[4] == "integrations" and segments[5] == "agent" and segments[6] == "status"):
                return self._reply(200, self.server.agent_bridge.status())
            if (len(segments) == 6 and segments[:3] == ["api", "v1", "projects"]
                    and segments[4] == "native-summary" and segments[5] == "markdown"):
                from urllib.parse import parse_qs
                query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                if set(query) != {"source_record_id"} or len(query["source_record_id"]) != 1 or not query["source_record_id"][0]:
                    raise WorkspaceError("Select exactly one project source", "invalid_request")
                return self._result(self.server._call("project", "native-summary-export",
                    {"project_id": segments[3], "source_record_id": query["source_record_id"][0]}))
            if (len(segments) == 5 and segments[:3] == ["api", "v1", "projects"]
                    and segments[4] == "native-summary"):
                from urllib.parse import parse_qs
                query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                if set(query) != {"source_record_id"} or len(query["source_record_id"]) != 1 or not query["source_record_id"][0]:
                    raise WorkspaceError("Select exactly one project source", "invalid_request")
                return self._result(self.server._call("project", "native-summary-read",
                    {"project_id": segments[3], "source_record_id": query["source_record_id"][0]}))

            if (len(segments) == 5 and segments[:3] == ["api", "v1", "projects"]
                    and segments[4] == "working-summary"):
                from urllib.parse import parse_qs
                query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                if set(query) not in ({"source_record_id", "artifact_id"}, {"source_record_id", "task_id"}) or any(len(v) != 1 or not v[0] for v in query.values()):
                    raise WorkspaceError("Select one source and generated draft", "invalid_request")
                return self._result(self.server._call("project", "working-summary-context",
                    {"project_id": segments[3], **{k: v[0] for k, v in query.items()}}))
            if (len(segments) == 6 and segments[:3] == ["api", "v1", "projects"]
                    and segments[4] == "source-text"):
                return self._result(self.server._call("project", "source_text_lookup",
                    {"project_id": segments[3], "key": segments[5],
                     "workspace_instance_id": self.headers.get("X-Workspace-Instance")}))
            if (len(segments) == 6 and segments[:3] == ["api", "v1", "projects"]
                    and segments[4] == "preparations"):
                return self._result(self.server._call("task", "reconcile_preparation",
                    {"project_id": segments[3], "key": segments[5],
                     "workspace_instance_id": self.headers.get("X-Workspace-Instance")}))
            if (len(segments) == 7 and segments[:3] == ["api", "v1", "projects"]
                    and segments[4] == "artifacts" and segments[6] == "discovery"):
                return self._result(self.server._call("project", "discovery-view",
                    {"project_id": segments[3], "artifact_id": segments[5]}))
            if (len(segments) == 7 and segments[:3] == ["api", "v1", "projects"]
                    and segments[4] == "artifacts" and segments[6] == "text"):
                return self._result(self.server._call("project", "preview_text",
                                                  {"project_id": segments[3], "artifact_id": segments[5]}))
            if len(segments) == 4 and segments[:2] == ["api", "v1"]:
                resource = {"projects": "project", "tasks": "task", "actions": "action"}.get(segments[2])
                if resource:
                    return self._result(self.server._call(resource, "show", {f"{resource}_id": segments[3]}))
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

    def _discard_rejected_body(self):
        """Best-effort bounded drain after denial; never parse or authorize data.

        Closing HTTP/1.0 with unread request bytes can race response delivery.
        This mitigates only small, unambiguously framed bodies, not every reset.
        The read-wait budget is 250ms, not a hard scheduler/wall-clock bound.
        It occupies an existing handler thread and is not general DoS protection.
        """
        self.close_connection = True
        lengths = self.headers.get_all("Content-Length", [])
        if self.headers.get_all("Transfer-Encoding") is not None or len(lengths) != 1:
            return
        value = lengths[0]
        if not 1 <= len(value) <= 5 or not value.isascii() or not value.isdecimal():
            return
        remaining = int(value)
        if not 0 < remaining <= 65_536:
            return
        previous = None
        restore = False
        try:
            previous = self.connection.gettimeout()
            restore = True
            deadline = time.monotonic() + 0.25
            while remaining:
                budget = deadline - time.monotonic()
                if budget <= 0:
                    break
                self.connection.settimeout(min(previous, budget) if previous is not None else budget)
                chunk = self.rfile.read1(min(8192, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
        except OSError:
            pass  # Failed draining must not replace the denial or dispatch work.
        finally:
            if restore:
                try:
                    self.connection.settimeout(previous)
                except OSError:
                    pass

    def do_POST(self):
        if not self._trusted_origin() or not hmac.compare_digest(self.headers.get("X-CSRF-Token", ""), self.server.csrf):
            self._discard_rejected_body()
            return self._reply(403, {"ok": False, "error": "Untrusted request", "code": "forbidden"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 2_100_000 or self.headers.get_content_type() != "application/json":
                raise WorkspaceError("A bounded application/json body is required")
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise WorkspaceError("Request must be an object")
            parts = unquote(urlsplit(self.path).path).strip("/").split("/")
            if parts == ["api", "v1", "integrations", "obsidian", "validate"]:
                if set(data) != {"vault_path"}:
                    raise WorkspaceError("Only vault_path is accepted", "invalid_request")
                result = self.server.obsidian_validation.validate(data["vault_path"])
                status = 200 if result["ok"] else 403 if result["code"] == "vault_scope_denied" else 409
                return self._reply(status, result)
            if parts == ["api", "v1", "integrations", "credentials"]:
                integrations = getattr(self.server, "integrations", None)
                if integrations is None:
                    return self._reply(403, {"ok": False, "error": "Local integrations are unavailable in this server mode", "code": "integrations_unavailable"})
                try:
                    raw_vault = data.get("obsidian_vault_path")
                    if isinstance(raw_vault, str) and raw_vault.strip():
                        try:
                            probe = ObsidianValidation(raw_vault.strip())
                            probe.assert_storage_outside(self.server.service.workspace.root)
                        except ValueError as exc:
                            raise WorkspaceError(str(exc), "invalid_request") from exc
                    result = integrations.save_credentials(data)
                    if result.get("obsidian_touched"):
                        refreshed_vault = integrations.default_vault_root()
                        try:
                            new_validation = ObsidianValidation(refreshed_vault)
                            new_validation.assert_storage_outside(self.server.service.workspace.root)
                        except ValueError:
                            new_validation = ObsidianValidation(None)
                        self.server.obsidian_validation = new_validation
                        if getattr(self.server, "sync_hooks", None) is not None:
                            self.server.sync_hooks.obsidian_validation = new_validation
                        result["obsidian_validation"] = new_validation.capability()
                        result["obsidian_snapshot_available"] = bool(
                            self.server.library_snapshot.path is not None
                            or new_validation.scope is not None
                        )
                    return self._reply(200, result)
                except WorkspaceError as exc:
                    status = 403 if exc.code == "integrations_unavailable" else 400
                    return self._reply(status, {"ok": False, "error": str(exc), "code": exc.code})
            if parts == ["api", "v1", "integrations", "zotero", "check"]:
                if data:
                    raise WorkspaceError("Check accepts an empty JSON object", "invalid_request")
                integrations = getattr(self.server, "integrations", None)
                if integrations is None:
                    return self._reply(403, {"ok": False, "error": "Local integrations are unavailable in this server mode", "code": "integrations_unavailable"})
                try:
                    return self._reply(200, integrations.check_zotero())
                except WorkspaceError as exc:
                    status = 403 if exc.code == "integrations_unavailable" else 400
                    return self._reply(status, {"ok": False, "error": str(exc), "code": exc.code})
            if parts == ["api", "v1", "integrations", "notebooklm", "check"]:
                if data:
                    raise WorkspaceError("Check accepts an empty JSON object", "invalid_request")
                integrations = getattr(self.server, "integrations", None)
                if integrations is None:
                    return self._reply(403, {"ok": False, "error": "Local integrations are unavailable in this server mode", "code": "integrations_unavailable"})
                try:
                    return self._reply(200, integrations.check_notebooklm())
                except WorkspaceError as exc:
                    status = 403 if exc.code == "integrations_unavailable" else 400
                    return self._reply(status, {"ok": False, "error": str(exc), "code": exc.code})
            if parts == ["api", "v1", "integrations", "notebooklm", "login"]:
                integrations = getattr(self.server, "integrations", None)
                if integrations is None:
                    return self._reply(403, {"ok": False, "error": "Local integrations are unavailable in this server mode", "code": "integrations_unavailable"})
                try:
                    result = integrations.start_notebooklm_login(data)
                    return self._reply(200 if result.get("ok") else 400, result)
                except WorkspaceError as exc:
                    status = 403 if exc.code == "integrations_unavailable" else 409 if exc.code == "login_in_progress" else 400
                    return self._reply(status, {"ok": False, "error": str(exc), "code": exc.code})
            if len(parts) == 7 and parts[:3] == ["api", "v1", "projects"] and parts[4] == "integrations":
                if parts[5] == "agent" and parts[6] in {"chat", "apply"}:
                    agent_fn = (
                        self.server.agent_bridge.chat
                        if parts[6] == "chat"
                        else self.server.agent_bridge.apply
                    )
                    try:
                        return self._reply(200, agent_fn(parts[3], data))
                    except WorkspaceError as exc:
                        status = (
                            404 if exc.code == "not_found"
                            else 403 if exc.code == "integrations_unavailable"
                            else 409 if exc.code == "stale_preview"
                            else 400
                        )
                        return self._reply(status, {"ok": False, "error": str(exc), "code": exc.code})
                sync_hooks = getattr(self.server, "sync_hooks", None)
                integrations = getattr(self.server, "integrations", None)
                if sync_hooks is None or integrations is None or not integrations.enabled:
                    return self._reply(403, {"ok": False, "error": "Local integrations are unavailable in this server mode", "code": "integrations_unavailable"})
                hook_route = (parts[5], parts[6])
                hook_fn = {
                    ("notebooklm", "bundle"): sync_hooks.bundle_notebooklm,
                    ("notebooklm", "upload"): sync_hooks.upload_notebooklm,
                    ("zotero", "sync"): sync_hooks.sync_zotero,
                    ("obsidian", "pack"): sync_hooks.pack_obsidian,
                }.get(hook_route)
                if hook_fn is not None:
                    try:
                        return self._reply(200, hook_fn(parts[3], data))
                    except WorkspaceError as exc:
                        status = 403 if exc.code == "integrations_unavailable" else 400
                        return self._reply(status, {"ok": False, "error": str(exc), "code": exc.code})
            resource = operation = None
            proof = None
            if parts == ["api", "v1", "projects"]:
                resource, operation = "project", "create"
            elif parts == ["api", "v1", "workspace", "demo"]:
                resource, operation = "project", "demo"
            elif len(parts) == 5 and parts[:2] == ["api", "v1"]:
                if parts[2] == "projects":
                    data["project_id"] = parts[3]
                    operation = {"artifacts": "register", "records": "record", "search": "search", "tasks": "create", "bind": "bind", "audit": "audit", "impact": "impact", "delivery": "prepare", "source-text": "source_text", "working-summary": "working-summary-save"}.get(parts[4])
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
            self._result(self.server._call(resource, operation, data, proof=proof, background=True))
        except (ValueError, OSError) as exc:
            self._reply(400, {"ok": False, "error": str(exc), "code": "invalid_request"})


def serve_workspace(root, *, port=8765, open_browser=True, human=False, obsidian_vault=None, library_snapshot=None, integrations_config=None):
    server_kwargs = {
        "port": port,
        "human": human,
        "obsidian_vault": obsidian_vault,
        "library_snapshot": library_snapshot,
    }
    if integrations_config is not None:
        server_kwargs["integrations_config"] = integrations_config
    server = WorkspaceServer(root, **server_kwargs)
    try:
        url = f"http://127.0.0.1:{server.server_port}/app/"
        print(f"Research workspace: {url}", flush=True)
        if open_browser:
            try:
                opened = webbrowser.open(url)
            except (webbrowser.Error, OSError):
                opened = False
            if not opened:
                print("Could not open a browser automatically. Open the workspace URL above in your browser.", file=sys.stderr)
        server.serve_forever()
    finally:
        server.server_close()
