# Connector Design

## Why Connectors Exist

v0.35 introduces a lightweight connector seam around external services.
This closes Codex critique #5 without refactoring the existing NotebookLM
implementation.

Today, NotebookLM is still the only real external-service integration in
the codebase. It remains in `src/research_hub/notebooklm/` unchanged.
The new connector package gives the project a documented protocol and a
registry so future integrations can plug in without first rewriting the
NotebookLM stack.

## Protocol Surface

The connector surface lives in `src/research_hub/connectors/__init__.py`.
It defines:

- `Connector`: runtime-checkable Protocol for bundle, upload, generate,
  download, and auth checks.
- `ConnectorBundleReport`: normalized bundle result.
- `ConnectorUploadReport`: normalized upload result.
- `ConnectorBriefReport`: normalized downloaded-artifact result.

The Protocol is intentionally small. It matches the workflow shape the
project already uses:

1. bundle cluster sources
2. upload sources to an external service
3. generate an artifact such as a briefing
4. download the resulting artifact

## NotebookLM As A Connector

NotebookLM is the reference implementation, but it is exposed through a
thin adapter instead of changing the current module layout.

`src/research_hub/connectors/_notebooklm_adapter.py` maps the existing
NotebookLM reports and function signatures onto the normalized connector
reports. This keeps backward compatibility intact:

- existing imports from `research_hub.notebooklm` still work
- existing workflows keep importing NotebookLM directly
- cluster YAML fields stay unchanged
- no CLI or MCP surface changes are introduced in v0.35

This is architecture-only work. The seam is available now; migrations to
consume it can happen later.

## Registry

The connector registry is import-time and process-local.

- `register_connector(connector)` adds or replaces an entry by name
- `get_connector(name)` returns a registered connector
- `list_connectors()` returns the sorted built-in and custom names

Built-ins auto-register on import:

- `notebooklm`
- `null`

## NullConnector

`NullConnector` is the minimal connector implementation.

Use it when:

- tests need a real Protocol object without external services
- future dry-run flows want a no-op connector
- a new connector author wants a small example to copy

The null connector is also the proof that the registry pattern works
without involving NotebookLM internals.

## Adding A New Connector

Future connectors such as Notion or Logseq should follow this pattern:

1. Create a module under `src/research_hub/connectors/`
2. Implement the `Connector` Protocol
3. Return the normalized report dataclasses
4. Register the connector with `register_connector(...)`

Minimal sketch:

```python
from research_hub.connectors import (
    ConnectorBriefReport,
    ConnectorBundleReport,
    ConnectorUploadReport,
    register_connector,
)


class NotionConnector:
    name = "notion"

    def bundle(self, cluster, cfg):
        return ConnectorBundleReport(cluster_slug=cluster.slug, bundle_dir=None)

    def upload(self, cluster, cfg):
        return ConnectorUploadReport(cluster_slug=cluster.slug)

    def generate(self, cluster, cfg, *, artifact_type="brief"):
        return {"ok": True, "artifact_type": artifact_type}

    def download(self, cluster, cfg):
        return ConnectorBriefReport(cluster_slug=cluster.slug)

    def check_auth(self, cfg):
        return True


register_connector(NotionConnector())
```

## Backward Compatibility

v0.35 does not change:

- `src/research_hub/notebooklm/*`
- existing import sites in core modules
- CLI commands
- MCP tools
- cluster YAML schema

That keeps the change low-risk while documenting the long-term extension
point.

## Testing Guidance

Use `NullConnector` when a test needs a connector-shaped object without
NotebookLM setup, browser automation, or saved sessions.

Use `NotebookLMConnector` when testing protocol conformance or adapter
delegation behavior.
