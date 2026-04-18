"""Protocol view over the existing NotebookLM module.

The notebooklm package has its own report objects. This adapter maps them
to the connector Protocol's report types without modifying NotebookLM.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from research_hub.connectors import (
    ConnectorBriefReport,
    ConnectorBundleReport,
    ConnectorUploadReport,
)


class NotebookLMConnector:
    name = "notebooklm"

    def bundle(self, cluster: Any, cfg: Any) -> ConnectorBundleReport:
        from research_hub.notebooklm.bundle import bundle_cluster

        report = bundle_cluster(cluster, cfg)
        pdf_count = getattr(report, "pdf_count", 0) or 0
        url_count = getattr(report, "url_count", 0) or 0
        bundle_dir = getattr(report, "bundle_dir", None)
        return ConnectorBundleReport(
            cluster_slug=getattr(cluster, "slug", ""),
            bundle_dir=Path(bundle_dir) if bundle_dir else None,
            source_count=pdf_count + url_count,
            pdf_count=pdf_count,
            url_count=url_count,
        )

    def upload(self, cluster: Any, cfg: Any) -> ConnectorUploadReport:
        from research_hub.notebooklm.upload import upload_cluster

        result = upload_cluster(cluster, cfg)
        uploaded = getattr(result, "uploaded", []) or []
        return ConnectorUploadReport(
            cluster_slug=getattr(cluster, "slug", ""),
            notebook_id=(
                getattr(result, "notebook_id", "")
                or getattr(cluster, "notebooklm_notebook_id", "")
                or ""
            ),
            notebook_url=getattr(result, "notebook_url", "") or "",
            uploaded_count=len(uploaded),
            skipped_count=getattr(result, "skipped_already_uploaded", 0) or 0,
        )

    def generate(
        self,
        cluster: Any,
        cfg: Any,
        *,
        artifact_type: str = "brief",
    ) -> dict[str, Any]:
        from research_hub.notebooklm.upload import generate_artifact

        try:
            url = generate_artifact(cluster, cfg, kind=artifact_type)
        except TypeError:
            url = generate_artifact(cluster, cfg, artifact_type=artifact_type)
        return {
            "ok": True,
            "cluster": getattr(cluster, "slug", ""),
            "artifact_type": artifact_type,
            "url": url or "",
        }

    def download(self, cluster: Any, cfg: Any) -> ConnectorBriefReport:
        from research_hub.notebooklm.upload import download_briefing_for_cluster

        result = download_briefing_for_cluster(cluster, cfg)
        artifact_path = getattr(result, "artifact_path", None)
        preview = ""
        if artifact_path:
            try:
                preview = Path(artifact_path).read_text(encoding="utf-8")[:500]
            except OSError:
                preview = ""
        return ConnectorBriefReport(
            cluster_slug=getattr(cluster, "slug", ""),
            artifact_path=Path(artifact_path) if artifact_path else None,
            char_count=getattr(result, "char_count", 0) or 0,
            preview=preview,
        )

    def check_auth(self, cfg: Any) -> bool:
        try:
            session_dir = cfg.research_hub_dir / "nlm_sessions" / "default"
        except Exception:
            return False
        return session_dir.exists()
