"""NullConnector: no-op implementation for the connector registry.

Useful when:
- tests need a Connector without external dependencies
- callers want a dry-run style flow
- new connector authors want a minimal example
"""

from __future__ import annotations

from typing import Any

from research_hub.connectors import (
    ConnectorBriefReport,
    ConnectorBundleReport,
    ConnectorUploadReport,
)


class NullConnector:
    name = "null"

    def bundle(self, cluster: Any, cfg: Any) -> ConnectorBundleReport:
        slug = getattr(cluster, "slug", "unknown")
        return ConnectorBundleReport(cluster_slug=slug, bundle_dir=None, source_count=0)

    def upload(self, cluster: Any, cfg: Any) -> ConnectorUploadReport:
        slug = getattr(cluster, "slug", "unknown")
        return ConnectorUploadReport(
            cluster_slug=slug,
            notebook_id=f"null-notebook-{slug}",
            notebook_url=f"null://{slug}",
            uploaded_count=0,
            skipped_count=0,
        )

    def generate(self, cluster: Any, cfg: Any, *, artifact_type: str = "brief") -> dict[str, Any]:
        slug = getattr(cluster, "slug", "unknown")
        return {
            "ok": True,
            "cluster": slug,
            "artifact_type": artifact_type,
            "note": "null connector; no real generation",
        }

    def download(self, cluster: Any, cfg: Any) -> ConnectorBriefReport:
        slug = getattr(cluster, "slug", "unknown")
        return ConnectorBriefReport(
            cluster_slug=slug,
            artifact_path=None,
            char_count=0,
            preview="(null connector; no real briefing)",
        )

    def check_auth(self, cfg: Any) -> bool:
        return True
