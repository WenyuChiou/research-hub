"""Tests for MCP server tool functions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import wraps
from http import HTTPStatus
from pathlib import Path

import requests

try:
    import responses
except ImportError:  # pragma: no cover
    class _Call:
        def __init__(self, method: str, url: str) -> None:
            self.request = type("RequestInfo", (), {"method": method, "url": url})()

    class _ShimResponse:
        def __init__(
            self,
            *,
            status: int,
            url: str,
            headers: dict[str, str] | None = None,
            json_data: dict | None = None,
        ) -> None:
            self.status_code = status
            self.url = url
            self.headers = headers or {}
            self._json_data = json_data or {}
            self.reason = HTTPStatus(status).phrase if status in HTTPStatus._value2member_map_ else ""

        def json(self):
            return self._json_data

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise requests.exceptions.HTTPError(f"{self.status_code} {self.reason}")

    class _ResponsesShim:
        HEAD = "HEAD"
        GET = "GET"

        def __init__(self) -> None:
            self.calls: list[_Call] = []
            self._registry: list[dict] = []
            self._original = None

        def add(self, method, url, *, status=200, headers=None, body=None, json=None):
            self._registry.append(
                {
                    "method": method.upper(),
                    "url": url,
                    "status": status,
                    "headers": headers or {},
                    "body": body,
                    "json": json,
                }
            )

        def activate(self, func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                self.calls = []
                self._original = requests.sessions.Session.request

                def fake_request(session, method, url, **request_kwargs):
                    prepared = requests.Request(
                        method=method.upper(),
                        url=url,
                        params=request_kwargs.get("params"),
                    ).prepare()
                    resolved_url = prepared.url
                    self.calls.append(_Call(method.upper(), resolved_url))
                    for index, entry in enumerate(self._registry):
                        if entry["method"] == method.upper() and (
                            entry["url"] == resolved_url or resolved_url.startswith(f"{entry['url']}?")
                        ):
                            self._registry.pop(index)
                            if isinstance(entry["body"], Exception):
                                raise entry["body"]
                            response = _ShimResponse(
                                status=entry["status"],
                                url=resolved_url,
                                headers=entry["headers"],
                                json_data=entry["json"],
                            )
                            if (
                                request_kwargs.get("allow_redirects")
                                and 300 <= response.status_code < 400
                                and response.headers.get("Location")
                            ):
                                redirected = fake_request(
                                    session,
                                    method,
                                    response.headers["Location"],
                                    **{k: v for k, v in request_kwargs.items() if k != "params"},
                                )
                                redirected.history = [response]
                                return redirected
                            return response
                    raise AssertionError(f"Unexpected HTTP call: {method} {resolved_url}")

                requests.sessions.Session.request = fake_request
                try:
                    return func(*args, **kwargs)
                finally:
                    requests.sessions.Session.request = self._original
                    self._registry = []

            return wrapper

    responses = _ResponsesShim()

from research_hub.clusters import ClusterRegistry
from research_hub.dedup import DedupHit, DedupIndex
from research_hub.doctor import CheckResult
from research_hub.mcp_server import (
    export_citation,
    get_config_info,
    list_clusters,
    run_doctor,
    search_papers,
    show_cluster,
    suggest_integration,
    verify_paper,
)


@dataclass
class StubConfig:
    root: Path
    raw: Path
    research_hub_dir: Path
    clusters_file: Path


def make_config(tmp_path: Path) -> StubConfig:
    root = tmp_path / "vault"
    raw = root / "raw"
    research_hub_dir = root / ".research_hub"
    raw.mkdir(parents=True)
    research_hub_dir.mkdir(parents=True)
    return StubConfig(
        root=root,
        raw=raw,
        research_hub_dir=research_hub_dir,
        clusters_file=research_hub_dir / "clusters.yaml",
    )


@responses.activate
def test_search_papers_returns_results(tmp_path, monkeypatch):
    cfg = make_config(tmp_path)
    index = DedupIndex()
    index.save(cfg.research_hub_dir / "dedup_index.json")
    monkeypatch.setattr("research_hub.config.get_config", lambda: cfg)
    responses.add(
        responses.GET,
        "https://api.semanticscholar.org/graph/v1/paper/search",
        json={
            "data": [
                {
                    "title": "Fresh Paper",
                    "year": 2024,
                    "authors": [{"name": "Jane Doe"}],
                    "externalIds": {"DOI": "10.1000/fresh"},
                    "venue": "Venue",
                    "citationCount": 11,
                    "url": "https://example.org/paper",
                    "openAccessPdf": {"url": "https://example.org/paper.pdf"},
                }
            ]
        },
        status=200,
    )

    result = search_papers("fresh query", limit=5)

    assert isinstance(result, list)
    assert result[0]["title"] == "Fresh Paper"
    assert result[0]["doi"] == "10.1000/fresh"
    assert result[0]["already_in_vault"] is False


@responses.activate
def test_verify_paper_doi(tmp_path, monkeypatch):
    cfg = make_config(tmp_path)
    monkeypatch.setattr("research_hub.config.get_config", lambda: cfg)
    responses.add(responses.HEAD, "https://doi.org/10.1000/example", status=200)

    result = verify_paper(doi="10.1000/example")

    assert result["ok"] is True
    assert result["source"] == "doi.org"


def test_suggest_integration_returns_clusters_and_related(tmp_path, monkeypatch):
    cfg = make_config(tmp_path)
    registry = ClusterRegistry(cfg.clusters_file)
    registry.create(query="flood risk llm agent", name="Flood Agents", slug="flood-agents")
    note_dir = cfg.raw / "flood-agents"
    note_dir.mkdir()
    note_path = note_dir / "doe-2024-related.md"
    note_path.write_text(
        """---
title: "Flood Risk Agents for Response"
doi: "10.1000/related"
authors: ["Jane Doe"]
journal: "Risk Journal"
tags: [flood, agents]
topic_cluster: flood-agents
---
""",
        encoding="utf-8",
    )
    index = DedupIndex()
    index.add(
        DedupHit(
            source="obsidian",
            doi="10.1000/related",
            title="Flood Risk Agents for Response",
            obsidian_path=str(note_path),
        )
    )
    index.save(cfg.research_hub_dir / "dedup_index.json")
    monkeypatch.setattr("research_hub.config.get_config", lambda: cfg)

    result = suggest_integration("Flood risk agent coordination", top_clusters=2, top_related=2)

    assert result["paper"]["title"] == "Flood risk agent coordination"
    assert result["cluster_suggestions"]
    assert result["cluster_suggestions"][0]["cluster_slug"] == "flood-agents"
    assert result["related_papers"]


def test_list_clusters_empty_registry(tmp_path, monkeypatch):
    cfg = make_config(tmp_path)
    monkeypatch.setattr("research_hub.config.get_config", lambda: cfg)

    assert list_clusters() == []


def test_show_cluster_not_found(tmp_path, monkeypatch):
    cfg = make_config(tmp_path)
    monkeypatch.setattr("research_hub.config.get_config", lambda: cfg)

    assert show_cluster("missing") == {"error": "Cluster not found: missing"}


def test_export_citation_calls_cite(monkeypatch):
    calls = []

    def fake_cite(identifier, cluster, content_format, out_path):
        calls.append((identifier, cluster, content_format, out_path))
        print("citation output")
        return 0

    monkeypatch.setattr("research_hub.cli._cite", fake_cite)

    result = export_citation(identifier="10.1000/example", format="bibtex")

    assert result == "citation output\n"
    assert calls == [("10.1000/example", None, "bibtex", None)]


def test_run_doctor_returns_check_results(monkeypatch):
    monkeypatch.setattr(
        "research_hub.doctor.run_doctor",
        lambda: [CheckResult(name="config", status="OK", message="ready")],
    )

    assert run_doctor() == [{"name": "config", "status": "OK", "message": "ready", "remedy": ""}]


def test_get_config_info_returns_paths(tmp_path, monkeypatch):
    cfg = make_config(tmp_path)
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"knowledge_base": {"root": str(cfg.root)}}), encoding="utf-8")
    monkeypatch.setattr("research_hub.config.get_config", lambda: cfg)
    monkeypatch.setattr("research_hub.config._resolve_config_path", lambda: config_path)

    result = get_config_info()

    assert result["config_path"] == str(config_path)
    assert result["vault_root"] == str(cfg.root)
    assert result["raw_dir"] == str(cfg.raw)


def test_show_cluster_includes_sync_status(tmp_path, monkeypatch):
    cfg = make_config(tmp_path)
    registry = ClusterRegistry(cfg.clusters_file)
    registry.create(query="flood risk llm agent", name="Flood Agents", slug="flood-agents")
    monkeypatch.setattr("research_hub.config.get_config", lambda: cfg)

    result = show_cluster("flood-agents")

    assert result["slug"] == "flood-agents"
    assert "sync_status" in result
    assert result["sync_status"]["cluster_slug"] == "flood-agents"
