"""Pure endpoint handlers for the v1 REST API."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from research_hub.dashboard.data import collect_dashboard_data
from research_hub import mcp_server as _m


def _unwrap(t):
    """Return the plain callable from either a bare function or a fastmcp
    FunctionTool wrapper. v0.52.1: needed because fastmcp 2.x wraps newer
    @mcp.tool() definitions in a FunctionTool object that isn't directly
    callable; older tool definitions are plain functions. Both must be
    callable from the REST handlers."""
    return getattr(t, "fn", t)


ask_cluster = _unwrap(_m.ask_cluster)
auto_research_topic = _unwrap(_m.auto_research_topic)
list_claims = _unwrap(_m.list_claims)
list_clusters = _unwrap(_m.list_clusters)
list_crystals = _unwrap(_m.list_crystals)
list_entities = _unwrap(_m.list_entities)
list_methods = _unwrap(_m.list_methods)
plan_research_workflow = _unwrap(_m.plan_research_workflow)
read_crystal = _unwrap(_m.read_crystal)
search_papers = _unwrap(_m.search_papers)
show_cluster = _unwrap(_m.show_cluster)
web_search = _unwrap(_m.web_search)


API_VERSION = "0.52.0"


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def _clean(value: Any) -> Any:
    if is_dataclass(value):
        return _clean(asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(item) for item in value]
    return value


def _require_body(request: dict) -> dict:
    body = request.get("json")
    if not isinstance(body, dict):
        raise ApiError(400, "bad_request", "Request body must be a JSON object.")
    return body


def _require_string(body: dict, key: str) -> str:
    value = body.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ApiError(400, "bad_request", f"Missing required field: {key}.")
    return value.strip()


def _optional_int(body: dict, key: str, default: int) -> int:
    value = body.get(key, default)
    if not isinstance(value, int):
        raise ApiError(400, "bad_request", f"Field {key} must be an integer.")
    return value


def _optional_bool(body: dict, key: str, default: bool) -> bool:
    value = body.get(key, default)
    if not isinstance(value, bool):
        raise ApiError(400, "bad_request", f"Field {key} must be a boolean.")
    return value


def _optional_string(body: dict, key: str, default: str = "") -> str:
    value = body.get(key, default)
    if value is None:
        return default
    if not isinstance(value, str):
        raise ApiError(400, "bad_request", f"Field {key} must be a string.")
    return value.strip()


def _optional_string_list(body: dict, key: str) -> list[str] | None:
    value = body.get(key)
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ApiError(400, "bad_request", f"Field {key} must be a list of strings.")
    return [item.strip() for item in value if item.strip()]


def _raise_for_tool_error(result: Any, *, not_found_prefix: str | None = None) -> None:
    if not isinstance(result, dict):
        return
    if result.get("ok") is False:
        raise ApiError(400, "bad_request", "The request arguments were rejected.")
    message = result.get("error")
    if isinstance(message, str) and message:
        if not_found_prefix and message.startswith(not_found_prefix):
            raise ApiError(404, "not_found", message)
        raise ApiError(400, "bad_request", message)
    if result.get("status") == "not_found":
        raise ApiError(404, "not_found", "Requested resource was not found.")


def get_health(request: dict) -> dict:
    cfg = request["cfg"]
    vault_root = getattr(cfg, "root", None) or getattr(cfg, "raw", "")
    return {
        "ok": True,
        "version": API_VERSION,
        "vault_root": str(vault_root),
    }


def get_clusters(request: dict) -> dict:
    # v0.52.1: switched from collect_dashboard_data() (full dashboard build,
    # 5-10s on large vaults, caused HTTP timeouts) to the lightweight
    # list_clusters() MCP function (~1s) since the API just needs slug +
    # name + paper_count, not the full dashboard data structure.
    raw = list_clusters()
    if isinstance(raw, dict) and "error" in raw:
        # MCP returns {"error": "..."} on failure; surface it as 500
        raise ApiError(500, "internal_error", raw["error"])
    items = raw if isinstance(raw, list) else []
    clusters = []
    for c in items:
        clusters.append(
            {
                "slug": c.get("slug", ""),
                "name": c.get("name", c.get("slug", "")),
                "paper_count": int(c.get("paper_count", 0) or 0),
                "crystal_count": int(c.get("crystal_count", 0) or 0),
                "last_activity": c.get("last_activity", ""),
            }
        )
    return {"clusters": clusters}


def get_cluster(request: dict) -> dict:
    slug = request["path_params"]["slug"]
    result = show_cluster(slug)
    _raise_for_tool_error(result, not_found_prefix="Cluster not found:")
    return {"cluster": _clean(result)}


def get_cluster_crystals(request: dict) -> dict:
    slug = request["path_params"]["slug"]
    result = list_crystals(slug)
    _raise_for_tool_error(result, not_found_prefix="Cluster not found:")
    crystals = result.get("crystals", []) if isinstance(result, dict) else []
    return {
        "crystals": [
            {
                "slug": item.get("slug", ""),
                "tldr": item.get("tldr", ""),
            }
            for item in crystals
        ]
    }


def get_cluster_crystal(request: dict) -> dict:
    params = request["path_params"]
    result = read_crystal(params["slug"], params["crystal_slug"], level="full")
    _raise_for_tool_error(result, not_found_prefix="Cluster not found:")
    return {"crystal": _clean(result)}


def get_cluster_memory(request: dict) -> dict:
    params = request["path_params"]
    kind = params["kind"]
    handlers = {
        "entities": (list_entities, "entities"),
        "claims": (list_claims, "claims"),
        "methods": (list_methods, "methods"),
    }
    if kind not in handlers:
        raise ApiError(404, "not_found", "Requested resource was not found.")
    fn, field_name = handlers[kind]
    result = fn(params["slug"])
    _raise_for_tool_error(result, not_found_prefix="Cluster not found:")
    return {"items": _clean(result.get(field_name, []))}


def get_job(request: dict) -> dict:
    job = request["job_queue"].get(request["path_params"]["job_id"])
    if job is None:
        raise ApiError(404, "not_found", "Requested resource was not found.")
    return _clean(job)


def post_search(request: dict) -> dict:
    body = _require_body(request)
    query = _require_string(body, "query")
    limit = _optional_int(body, "limit", 10)
    backends = _optional_string_list(body, "backends")
    field = _optional_string(body, "field", "") or None
    results = search_papers(query=query, limit=limit, backends=backends, field=field)
    _raise_for_tool_error(results)
    return {"ok": True, "results": _clean(results)}


def post_websearch(request: dict) -> dict:
    body = _require_body(request)
    query = _require_string(body, "query")
    max_results = _optional_int(body, "max_results", 10)
    provider = _optional_string(body, "provider", "auto") or "auto"
    result = web_search(query=query, max_results=max_results, provider=provider)
    _raise_for_tool_error(result)
    return _clean(result)


def post_plan(request: dict) -> dict:
    body = _require_body(request)
    intent = _require_string(body, "intent")
    result = plan_research_workflow(intent)
    _raise_for_tool_error(result)
    return _clean(result)


def post_ask(request: dict) -> dict:
    body = _require_body(request)
    cluster = _require_string(body, "cluster")
    question = _require_string(body, "question")
    detail = _optional_string(body, "detail", "gist") or "gist"
    result = ask_cluster(cluster, question=question, detail=detail)
    _raise_for_tool_error(result, not_found_prefix="Cluster not found:")
    if isinstance(result, dict) and result.get("ok") is False:
        message = str(result.get("error", "") or "")
        if "unknown cluster" in message.lower() or "cluster not found" in message.lower():
            raise ApiError(404, "not_found", message)
        raise ApiError(400, "bad_request", message or "The request arguments were rejected.")
    return _clean(result)


def post_auto(request: dict) -> dict:
    body = _require_body(request)
    topic = _require_string(body, "topic")
    max_papers = _optional_int(body, "max_papers", 8)
    do_nlm = _optional_bool(body, "do_nlm", True)
    do_crystals = _optional_bool(body, "do_crystals", False)
    field = _optional_string(body, "field", "") or None

    def _run_auto() -> dict:
        result = auto_research_topic(
            topic=topic,
            max_papers=max_papers,
            do_nlm=do_nlm,
            do_crystals=do_crystals,
            field=field,
        )
        return _clean(result)

    job_id = request["job_queue"].enqueue(_run_auto)
    status_url = f"/api/v1/jobs/{job_id}"
    return {"job_id": job_id, "status_url": status_url}, 202, {"Location": status_url}
