"""Pluggable external-service connectors.

A Connector encapsulates the bundle -> upload -> generate -> download
pattern that NotebookLM established. Future connectors just need to
satisfy the Protocol and register.

Existing NotebookLM code is not refactored. The
``research_hub.connectors._notebooklm_adapter`` module provides the
Protocol view over the current implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@dataclass
class ConnectorBundleReport:
    cluster_slug: str
    bundle_dir: Path | None
    source_count: int = 0
    pdf_count: int = 0
    url_count: int = 0


@dataclass
class ConnectorUploadReport:
    cluster_slug: str
    notebook_id: str = ""
    notebook_url: str = ""
    uploaded_count: int = 0
    skipped_count: int = 0


@dataclass
class ConnectorBriefReport:
    cluster_slug: str
    artifact_path: Path | None = None
    char_count: int = 0
    preview: str = ""


@runtime_checkable
class Connector(Protocol):
    """Protocol every external-service connector must satisfy."""

    name: str

    def bundle(self, cluster: Any, cfg: Any) -> ConnectorBundleReport: ...

    def upload(self, cluster: Any, cfg: Any) -> ConnectorUploadReport: ...

    def generate(
        self,
        cluster: Any,
        cfg: Any,
        *,
        artifact_type: str = "brief",
    ) -> dict[str, Any]: ...

    def download(self, cluster: Any, cfg: Any) -> ConnectorBriefReport: ...

    def check_auth(self, cfg: Any) -> bool: ...


_REGISTRY: dict[str, Connector] = {}


def register_connector(connector: Connector) -> None:
    """Register a Connector in the global registry."""

    if not isinstance(connector, Connector):
        raise TypeError(
            f"object {connector!r} (name={getattr(connector, 'name', '?')!r}) "
            "does not satisfy Connector Protocol; missing required methods"
        )
    name = connector.name
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"connector.name must be non-empty string, got {name!r}")
    _REGISTRY[name] = connector


def get_connector(name: str) -> Connector:
    if name not in _REGISTRY:
        available = sorted(_REGISTRY)
        raise KeyError(f"connector {name!r} not registered. Available: {available}")
    return _REGISTRY[name]


def list_connectors() -> list[str]:
    return sorted(_REGISTRY)


def _auto_register() -> None:
    """Auto-register built-in connectors at import time."""

    from research_hub.connectors._notebooklm_adapter import NotebookLMConnector
    from research_hub.connectors.null import NullConnector

    register_connector(NotebookLMConnector())
    register_connector(NullConnector())


_auto_register()


__all__ = [
    "Connector",
    "ConnectorBriefReport",
    "ConnectorBundleReport",
    "ConnectorUploadReport",
    "get_connector",
    "list_connectors",
    "register_connector",
]
