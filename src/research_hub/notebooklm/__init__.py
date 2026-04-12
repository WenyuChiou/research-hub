"""NotebookLM integration (v0.4.x)."""

from research_hub.notebooklm.bundle import BundleReport, bundle_cluster
from research_hub.notebooklm.client import (
    BriefingArtifact,
    NotebookHandle,
    NotebookLMClient,
    NotebookLMError,
    UploadResult,
)
from research_hub.notebooklm.session import PlaywrightSession, SessionConfig, login_interactive
from research_hub.notebooklm.upload import (
    DownloadReport,
    UploadReport,
    download_briefing_for_cluster,
    generate_artifact,
    read_latest_briefing,
    upload_cluster,
)

__all__ = [
    "BriefingArtifact",
    "BundleReport",
    "DownloadReport",
    "NotebookHandle",
    "NotebookLMClient",
    "NotebookLMError",
    "PlaywrightSession",
    "SessionConfig",
    "UploadReport",
    "UploadResult",
    "bundle_cluster",
    "download_briefing_for_cluster",
    "generate_artifact",
    "login_interactive",
    "read_latest_briefing",
    "upload_cluster",
]
