"""Loopback-only opt-in integration controls (encrypted API keys, live probes, NLM session setup).

Disabled by default on direct ``WorkspaceServer(root)`` construction so clean-baseline
and offline tests never touch HOME or network services. Enabled when launched via
``research-hub serve --workspace`` or when an explicit ``integrations_config`` path
is supplied. Secret values (API keys, emails, cookies) are never returned in HTTP
responses or DOM attributes.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat
import threading
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import platformdirs

from research_hub.config import (
    CONFIG_PATH,
    _resolve_config_path,
    invalidate_config_cache,
)
from research_hub.security import chmod_sensitive
from research_hub.security.secret_box import _HAS_CRYPTO, decrypt, encrypt, is_encrypted
from .core import WorkspaceError, atomic_json


_DIGITS_RE = re.compile(r"^[0-9]+$")
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_ALLOWED_CREDENTIAL_FIELDS = frozenset({
    "zotero_library_id",
    "zotero_library_type",
    "zotero_api_key",
    "clear_zotero_api_key",
    "unpaywall_email",
    "s2_api_key",
    "clear_s2_api_key",
})
_ALLOWED_LOGIN_FIELDS = frozenset({"mode", "browser", "state_path"})
_ALLOWED_BROWSERS = frozenset({"", "chrome", "edge", "firefox", "chromium"})
_MAX_KEY_CHARS = 512
_MAX_STATE_IMPORT_BYTES = 2 * 1024 * 1024


def resolve_default_config_path() -> Path:
    """Return the active config.json path or canonical user-config destination."""
    resolved = _resolve_config_path()
    if resolved is not None:
        return resolved
    env = os.environ.get("RESEARCH_HUB_CONFIG")
    if env and env.strip():
        return Path(env).expanduser()
    return Path(platformdirs.user_config_dir("research-hub", ensure_exists=False)) / "config.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _validate_secret_key(value: object, *, label: str) -> str:
    if not isinstance(value, str):
        raise WorkspaceError(f"{label} must be a string", "invalid_request")
    trimmed = value.strip()
    if not trimmed or len(trimmed) > _MAX_KEY_CHARS:
        raise WorkspaceError(f"{label} must be 1 to {_MAX_KEY_CHARS} characters", "invalid_request")
    if any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in trimmed):
        raise WorkspaceError(f"{label} cannot contain whitespace or control characters", "invalid_request")
    try:
        trimmed.encode("latin-1")
    except UnicodeEncodeError as exc:
        raise WorkspaceError(f"{label} must contain valid ASCII/latin-1 characters", "invalid_request") from exc
    return trimmed


class LocalIntegrationsManager:
    """Manage encrypted local credentials, read-only probes, and NLM login."""

    def __init__(self, config_target: str | Path | None = None) -> None:
        self._explicit_mode = config_target == "auto"
        if config_target is None:
            self._config_path: Path | None = None
        elif config_target == "auto":
            self._config_path = resolve_default_config_path()
        else:
            self._config_path = Path(config_target).expanduser()
        self._lock = threading.Lock()
        self._probes: dict[str, dict[str, Any] | None] = {
            "zotero": None,
            "notebooklm_auth": None,
        }
        self._login_job: dict[str, Any] = {
            "status": "idle",
            "mode": None,
            "message": "",
            "started_at": None,
            "finished_at": None,
        }

    @property
    def enabled(self) -> bool:
        return self._config_path is not None

    def _active_config_path(self) -> Path:
        if self._config_path is None:
            raise WorkspaceError("Local integrations are unavailable in this server mode", "integrations_unavailable")
        if self._explicit_mode:
            resolved = _resolve_config_path()
            if resolved is not None:
                return resolved
        return self._config_path

    def _read_config_dict(self) -> tuple[Path, dict[str, Any]]:
        path = self._active_config_path()
        if not path.exists():
            return path, {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise WorkspaceError(f"Could not read configuration file: {type(exc).__name__}", "config_unreadable") from exc
        if not isinstance(data, dict):
            raise WorkspaceError("Configuration root must be a JSON object", "invalid_config")
        return path, data

    def _vault_research_hub_dir(self, data: dict[str, Any]) -> Path:
        kb = data.get("knowledge_base")
        raw_root = kb.get("root") if isinstance(kb, dict) else None
        if isinstance(raw_root, str) and raw_root.strip():
            root = Path(raw_root).expanduser()
        elif os.environ.get("RESEARCH_HUB_ROOT", "").strip():
            root = Path(os.environ["RESEARCH_HUB_ROOT"]).expanduser()
        else:
            root = Path.home() / "knowledge-base"
        return root / ".research_hub"

    def default_vault_root(self) -> Path | None:
        """Return configured existing KB root if enabled cleanly, without failing startup."""
        if not self.enabled:
            return None
        try:
            _, data = self._read_config_dict()
            kb = data.get("knowledge_base")
            raw_root = kb.get("root") if isinstance(kb, dict) else None
            if isinstance(raw_root, str) and raw_root.strip():
                candidate = Path(raw_root).expanduser()
                if candidate.is_dir():
                    return candidate
        except WorkspaceError:
            pass
        return None

    def _nlm_state_file(self, data: dict[str, Any]) -> Path:
        from research_hub.notebooklm.auth import default_state_file

        return default_state_file(self._vault_research_hub_dir(data))

    def _decrypt_field(self, raw_val: object, config_dir: Path) -> str:
        if not isinstance(raw_val, str) or not raw_val.strip():
            return ""
        val = raw_val.strip()
        if not is_encrypted(val):
            return val
        try:
            return decrypt(val, config_dir)
        except RuntimeError:
            return ""

    def _resolve_zotero_effective(
        self, data: dict[str, Any], config_dir: Path | None
    ) -> dict[str, Any]:
        """Resolve Zotero credentials with the exact precedence of zotero.client._load_credentials."""
        zot = data.get("zotero") if isinstance(data.get("zotero"), dict) else {}
        raw_zot_key = str(zot.get("api_key") or data.get("zotero_api_key") or "").strip()

        api_key = str(os.environ.get("ZOTERO_API_KEY") or "").strip()
        lib_id = str(os.environ.get("ZOTERO_LIBRARY_ID") or "").strip()
        lib_type = str(os.environ.get("ZOTERO_LIBRARY_TYPE") or "user").strip() or "user"

        if not api_key or not lib_id:
            try:
                from research_hub.zotero.client import _read_env_file

                env_file = _read_env_file()
                if not api_key:
                    api_key = str(env_file.get("ZOTERO_API_KEY") or "").strip()
                if not lib_id:
                    lib_id = str(env_file.get("ZOTERO_LIBRARY_ID") or "").strip()
                lib_type = str(env_file.get("ZOTERO_LIBRARY_TYPE") or lib_type).strip() or lib_type
            except Exception:
                pass

        if not api_key or not lib_id:
            if not api_key:
                raw_flat = str(data.get("zotero_api_key") or "").strip()
                api_key = (self._decrypt_field(raw_flat, config_dir) if config_dir else raw_flat) or ""
            if not lib_id:
                lib_id = str(data.get("zotero_library_id") or "").strip()
            flat_type = str(data.get("zotero_library_type") or "").strip()
            if flat_type:
                lib_type = flat_type

            if not api_key:
                raw_nested = str(zot.get("api_key") or "").strip()
                api_key = (self._decrypt_field(raw_nested, config_dir) if config_dir else raw_nested) or ""
            if not lib_id:
                lib_id = str(zot.get("library_id") or "").strip()
            nested_type = str(zot.get("library_type") or "").strip()
            if nested_type:
                lib_type = nested_type

        if lib_type not in {"user", "group"}:
            lib_type = "user"

        return {
            "api_key": api_key,
            "library_id": lib_id,
            "library_type": lib_type,
            "raw_config_key": raw_zot_key,
        }

    def capability(self) -> dict[str, Any]:
        """Non-sensitive summary included in /api/v1/workspace."""
        if not self.enabled:
            return {"version": 1, "status": "unavailable"}
        try:
            path, data = self._read_config_dict()
        except WorkspaceError:
            return {"version": 1, "status": "available", "config_error": True}
        search_cfg = data.get("search") if isinstance(data.get("search"), dict) else {}
        resolved_zot = self._resolve_zotero_effective(data, path.parent)
        raw_zot_key = resolved_zot["raw_config_key"]
        raw_s2_key = str(search_cfg.get("semantic_scholar_api_key") or "").strip()
        unpaywall_raw = str(
            data.get("unpaywall_email")
            or (data.get("zotero") if isinstance(data.get("zotero"), dict) else {}).get("unpaywall_email")
            or ""
        ).strip()
        state_file = self._nlm_state_file(data)
        nlm_present = False
        try:
            nlm_present = state_file.is_file() and state_file.stat().st_size > 0
        except OSError:
            nlm_present = False

        env_s2_key = bool(os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "").strip())
        env_unpaywall = bool(os.environ.get("UNPAYWALL_EMAIL", "").strip())

        effective_lib_id = resolved_zot["library_id"]
        effective_zot_key = bool(resolved_zot["api_key"])

        return {
            "version": 1,
            "status": "available",
            "zotero_configured": bool(effective_lib_id and effective_zot_key),
            "zotero_api_key_present": effective_zot_key,
            "zotero_api_key_encrypted": bool(raw_zot_key and is_encrypted(raw_zot_key)),
            "zotero_library_id": effective_lib_id,
            "zotero_library_type": resolved_zot["library_type"],
            "unpaywall_email_present": bool(unpaywall_raw) or env_unpaywall,
            "s2_api_key_present": bool(raw_s2_key) or env_s2_key,
            "s2_api_key_encrypted": bool(raw_s2_key and is_encrypted(raw_s2_key)),
            "nlm_state_present": nlm_present,
        }

    def status(self) -> dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "code": "integrations_unavailable", "error": "Local integrations are unavailable in this server mode."}
        creds = self.capability()
        _, data = self._read_config_dict()
        state_file = self._nlm_state_file(data)
        cookie_summary: dict[str, str] = {}
        if state_file.exists():
            try:
                from research_hub.notebooklm.keepalive import _read_short_cookie_metadata

                raw_meta = _read_short_cookie_metadata(state_file)
                cookie_summary = {
                    k: ("absent" if v in {"absent", "unreadable"} else "present")
                    for k, v in raw_meta.items()
                }
            except Exception:
                cookie_summary = {}
        with self._lock:
            probes = {k: (dict(v) if isinstance(v, dict) else None) for k, v in self._probes.items()}
            login_job = dict(self._login_job)
        return {
            "ok": True,
            "credentials": creds,
            "nlm_cookies": cookie_summary,
            "probes": probes,
            "login_job": login_job,
        }

    def save_credentials(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.enabled:
            raise WorkspaceError("Local integrations are unavailable in this server mode", "integrations_unavailable")
        if not isinstance(payload, dict) or not payload or not set(payload).issubset(_ALLOWED_CREDENTIAL_FIELDS):
            raise WorkspaceError("Unsupported credential update fields", "invalid_request")

        with self._lock:
            path, data = self._read_config_dict()
            path.parent.mkdir(parents=True, exist_ok=True)
            chmod_sensitive(path.parent, mode=0o700)

            zot = data.get("zotero")
            if zot is None:
                zot = {}
            if not isinstance(zot, dict):
                raise WorkspaceError("Invalid zotero section in configuration", "invalid_config")
            zot = dict(zot)

            search_cfg = data.get("search")
            if search_cfg is None:
                search_cfg = {}
            if not isinstance(search_cfg, dict):
                raise WorkspaceError("Invalid search section in configuration", "invalid_config")
            search_cfg = dict(search_cfg)

            zotero_touched = False
            if "zotero_library_id" in payload:
                raw_id = payload["zotero_library_id"]
                if not isinstance(raw_id, str):
                    raise WorkspaceError("Zotero library ID must be a string", "invalid_request")
                trimmed = raw_id.strip()
                if not trimmed:
                    zot.pop("library_id", None)
                    data.pop("zotero_library_id", None)
                else:
                    if not _DIGITS_RE.match(trimmed) or not re.search(r"[1-9]", trimmed):
                        raise WorkspaceError("Enter a positive numeric Zotero library ID", "invalid_request")
                    zot["library_id"] = trimmed.lstrip("0")
                zotero_touched = True

            if "zotero_library_type" in payload:
                lib_type = payload["zotero_library_type"]
                if lib_type not in {"user", "group"}:
                    raise WorkspaceError("Zotero library type must be 'user' or 'group'", "invalid_request")
                zot["library_type"] = lib_type
                zotero_touched = True

            if payload.get("clear_zotero_api_key") is True:
                zot.pop("api_key", None)
                data.pop("zotero_api_key", None)
                zotero_touched = True
            elif "zotero_api_key" in payload:
                raw_key = payload["zotero_api_key"]
                if isinstance(raw_key, str) and raw_key.strip():
                    validated = _validate_secret_key(raw_key, label="Zotero API key")
                    if not _HAS_CRYPTO:
                        raise WorkspaceError(
                            "Encrypted secret storage requires the 'cryptography' package (pip install research-hub-pipeline[secrets]).",
                            "encryption_unavailable",
                        )
                    encrypted_zot = encrypt(validated, path.parent)
                    if not is_encrypted(encrypted_zot):
                        raise WorkspaceError("Failed to encrypt Zotero API key", "encryption_unavailable")
                    zot["api_key"] = encrypted_zot
                    data.pop("zotero_api_key", None)
                    zotero_touched = True

            if "unpaywall_email" in payload:
                raw_email = payload["unpaywall_email"]
                if not isinstance(raw_email, str):
                    raise WorkspaceError("Unpaywall email must be a string", "invalid_request")
                email = raw_email.strip()
                if not email:
                    data.pop("unpaywall_email", None)
                    zot.pop("unpaywall_email", None)
                else:
                    if len(email) > 320 or not _EMAIL_RE.match(email):
                        raise WorkspaceError("Enter a valid Unpaywall email address", "invalid_request")
                    data["unpaywall_email"] = email

            if payload.get("clear_s2_api_key") is True:
                search_cfg.pop("semantic_scholar_api_key", None)
            elif "s2_api_key" in payload:
                raw_s2 = payload["s2_api_key"]
                if isinstance(raw_s2, str) and raw_s2.strip():
                    validated_s2 = _validate_secret_key(raw_s2, label="Semantic Scholar API key")
                    if not _HAS_CRYPTO:
                        raise WorkspaceError(
                            "Encrypted secret storage requires the 'cryptography' package (pip install research-hub-pipeline[secrets]).",
                            "encryption_unavailable",
                        )
                    encrypted_s2 = encrypt(validated_s2, path.parent)
                    if not is_encrypted(encrypted_s2):
                        raise WorkspaceError("Failed to encrypt Semantic Scholar API key", "encryption_unavailable")
                    search_cfg["semantic_scholar_api_key"] = encrypted_s2

            if zot:
                data["zotero"] = zot
            else:
                data.pop("zotero", None)

            if search_cfg:
                data["search"] = search_cfg
            else:
                data.pop("search", None)

            atomic_json(path, data)
            chmod_sensitive(path, mode=0o600)
            invalidate_config_cache()
            if zotero_touched:
                self._probes["zotero"] = None
            return {"ok": True, "saved": True, "credentials": self.capability()}

    def check_zotero(self) -> dict[str, Any]:
        if not self.enabled:
            raise WorkspaceError("Local integrations are unavailable in this server mode", "integrations_unavailable")
        path, data = self._read_config_dict()
        resolved = self._resolve_zotero_effective(data, path.parent)
        lib_id = resolved["library_id"]
        lib_type = resolved["library_type"]
        api_key = resolved["api_key"]

        local_ok = False
        if lib_id:
            prefix = "groups" if lib_type == "group" else "users"
            req = Request(
                f"http://localhost:23119/api/{prefix}/{lib_id}/items?limit=1",
                headers={"Zotero-Allowed-Request": "true"},
            )
            try:
                with urlopen(req, timeout=2):
                    local_ok = True
            except (URLError, OSError, TimeoutError):
                local_ok = False

        web_status = "not_configured"
        if lib_id and api_key:
            try:
                from pyzotero import zotero

                client = zotero.Zotero(lib_id, lib_type, api_key)
                client.top(limit=1)
                web_status = "ok"
            except Exception as exc:
                msg = str(exc).lower()
                if "403" in msg or "401" in msg or "invalid key" in msg or "forbidden" in msg:
                    web_status = "auth_failed"
                else:
                    web_status = "unreachable"

        if web_status == "ok" and local_ok:
            overall = "connected_local_and_web"
        elif web_status == "ok":
            overall = "connected_web"
        elif local_ok:
            overall = "connected_local"
        elif web_status == "auth_failed":
            overall = "auth_failed"
        elif not lib_id or not api_key:
            overall = "missing_credentials"
        else:
            overall = "unreachable"

        probe = {
            "status": overall,
            "local_api": local_ok,
            "web_api": web_status,
            "observed_at": _utc_now(),
        }
        with self._lock:
            self._probes["zotero"] = dict(probe)
        return {"ok": True, "probe": probe}

    def check_notebooklm(self) -> dict[str, Any]:
        if not self.enabled:
            raise WorkspaceError("Local integrations are unavailable in this server mode", "integrations_unavailable")
        _, data = self._read_config_dict()
        state_file = self._nlm_state_file(data)
        from research_hub.notebooklm.auth import ensure_session_health

        health = ensure_session_health(state_file, auto_refresh=True)
        if health.get("ok"):
            status = "authenticated"
            code = "ok"
        elif not state_file.exists():
            status = "missing"
            code = "state_missing"
        else:
            status = "expired"
            code = "auth_invalid"
        probe = {
            "status": status,
            "code": code,
            "refreshed": bool(health.get("refreshed", False)),
            "state_present": state_file.exists(),
            "observed_at": _utc_now(),
        }
        with self._lock:
            self._probes["notebooklm_auth"] = dict(probe)
        return {"ok": True, "probe": probe}

    def _run_browser_window_login(self, session_dir: Path, state_file: Path) -> None:
        from research_hub.notebooklm.auth import check_session_health, login_nlm

        try:
            rc = login_nlm(
                session_dir,
                state_file=state_file,
                timeout_sec=300,
                wait_timeout=300,
                auto_detect=True,
            )
            health = check_session_health(state_file) if rc == 0 else {"ok": False}
            ok = rc == 0 and bool(health.get("ok"))
            finished = _utc_now()
            with self._lock:
                self._login_job = {
                    "status": "succeeded" if ok else "failed",
                    "mode": "browser_window",
                    "message": "authenticated" if ok else "login_not_completed",
                    "started_at": self._login_job.get("started_at"),
                    "finished_at": finished,
                }
                self._probes["notebooklm_auth"] = {
                    "status": "authenticated" if ok else ("expired" if state_file.exists() else "missing"),
                    "code": "ok" if ok else "login_not_completed",
                    "refreshed": False,
                    "state_present": state_file.exists(),
                    "observed_at": finished,
                }
        except Exception:
            finished = _utc_now()
            with self._lock:
                self._login_job = {
                    "status": "failed",
                    "mode": "browser_window",
                    "message": "login_failed",
                    "started_at": self._login_job.get("started_at"),
                    "finished_at": finished,
                }

    def start_notebooklm_login(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.enabled:
            raise WorkspaceError("Local integrations are unavailable in this server mode", "integrations_unavailable")
        if not isinstance(payload, dict) or not set(payload).issubset(_ALLOWED_LOGIN_FIELDS):
            raise WorkspaceError("Unsupported NotebookLM login fields", "invalid_request")
        mode = payload.get("mode")
        if mode not in {"browser_window", "browser_cookies", "import_state"}:
            raise WorkspaceError("Invalid NotebookLM login mode", "invalid_request")

        _, data = self._read_config_dict()
        rh_dir = self._vault_research_hub_dir(data)
        from research_hub.notebooklm.auth import (
            _tighten_state_file_perms,
            default_session_dir,
            default_state_file,
            ensure_session_health,
            login_from_browser,
        )

        state_file = default_state_file(rh_dir)
        session_dir = default_session_dir(rh_dir)

        if mode == "browser_window":
            with self._lock:
                if self._login_job.get("status") == "running":
                    raise WorkspaceError("NotebookLM browser login is already running", "login_in_progress")
                self._login_job = {
                    "status": "running",
                    "mode": "browser_window",
                    "message": "waiting_for_browser_signin",
                    "started_at": _utc_now(),
                    "finished_at": None,
                }
                login_snapshot = dict(self._login_job)
            worker = threading.Thread(
                target=self._run_browser_window_login,
                args=(session_dir, state_file),
                daemon=True,
            )
            worker.start()
            return {"ok": True, "login": login_snapshot}

        if mode == "browser_cookies":
            raw_browser = payload.get("browser") or ""
            if not isinstance(raw_browser, str) or raw_browser.strip().lower() not in _ALLOWED_BROWSERS:
                raise WorkspaceError("Unsupported browser selection", "invalid_request")
            browser = raw_browser.strip().lower() or None
            rc = login_from_browser(state_file, browser=browser)
            if rc != 0:
                return {
                    "ok": False,
                    "code": "browser_cookies_failed",
                    "error": "Could not import authenticated NotebookLM cookies from local browsers.",
                }
            health = ensure_session_health(state_file, auto_refresh=True)
            probe = {
                "status": "authenticated" if health.get("ok") else "expired",
                "code": "ok" if health.get("ok") else "auth_invalid",
                "refreshed": bool(health.get("refreshed", False)),
                "state_present": state_file.exists(),
                "observed_at": _utc_now(),
            }
            with self._lock:
                self._probes["notebooklm_auth"] = dict(probe)
            return {"ok": True, "probe": probe}

        # mode == "import_state"
        raw_path = payload.get("state_path")
        if not isinstance(raw_path, str) or not raw_path.strip() or len(raw_path) > 4096 or "\x00" in raw_path:
            raise WorkspaceError("Provide a valid local state.json path", "invalid_request")
        src = Path(raw_path.strip()).expanduser()
        if not src.is_absolute():
            raise WorkspaceError("State file path must be absolute", "invalid_request")
        try:
            info = src.lstat()
        except OSError as exc:
            raise WorkspaceError("Selected state file could not be read", "invalid_request") from exc
        if stat.S_ISLNK(info.st_mode) or (getattr(info, "st_file_attributes", 0) & 0x400) or not stat.S_ISREG(info.st_mode) or info.st_size > _MAX_STATE_IMPORT_BYTES:
            raise WorkspaceError("Selected file must be a regular JSON file under 2 MiB", "invalid_request")
        try:
            open_flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(src, open_flags)
            try:
                finfo = os.fstat(fd)
                if not stat.S_ISREG(finfo.st_mode) or finfo.st_size > _MAX_STATE_IMPORT_BYTES:
                    raise WorkspaceError("Selected file must be a regular JSON file under 2 MiB", "invalid_request")
                with os.fdopen(fd, "rb") as stream:
                    fd = -1
                    raw_bytes = stream.read(_MAX_STATE_IMPORT_BYTES + 1)
                if len(raw_bytes) > _MAX_STATE_IMPORT_BYTES:
                    raise WorkspaceError("Selected file must be under 2 MiB", "invalid_request")
            finally:
                if fd >= 0:
                    os.close(fd)
            parsed = json.loads(raw_bytes.decode("utf-8"))
        except WorkspaceError:
            raise
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WorkspaceError("Selected file is not valid UTF-8 JSON", "invalid_request") from exc
        if not isinstance(parsed, dict) or not isinstance(parsed.get("cookies"), list) or not parsed["cookies"]:
            raise WorkspaceError("State JSON must contain a non-empty cookies list", "invalid_request")

        state_file.parent.mkdir(parents=True, exist_ok=True)
        chmod_sensitive(state_file.parent, mode=0o700)
        tmp_state = state_file.parent / f".import-check-{os.getpid()}-{threading.get_ident()}.json"
        try:
            atomic_json(tmp_state, parsed)
            _tighten_state_file_perms(tmp_state)
            health = ensure_session_health(tmp_state, auto_refresh=True)
            if not health.get("ok"):
                return {
                    "ok": False,
                    "code": "auth_invalid",
                    "error": "Imported NotebookLM state is expired or invalid; existing session was kept unchanged.",
                }
            # Persist refreshed/validated bytes from the checked temporary copy without clobbering on invalid input.
            checked_payload = json.loads(tmp_state.read_text(encoding="utf-8"))
            atomic_json(state_file, checked_payload)
            _tighten_state_file_perms(state_file)
        finally:
            tmp_state.unlink(missing_ok=True)

        probe = {
            "status": "authenticated",
            "code": "ok",
            "refreshed": bool(health.get("refreshed", False)),
            "state_present": state_file.exists(),
            "observed_at": _utc_now(),
        }
        with self._lock:
            self._probes["notebooklm_auth"] = dict(probe)
        return {"ok": True, "probe": probe}
