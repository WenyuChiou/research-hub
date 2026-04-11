"""NotebookLM integration (v0.4.x)."""

from research_hub.notebooklm.bundle import BundleReport, bundle_cluster
from research_hub.notebooklm.client import NotebookHandle, NotebookLMClient, NotebookLMError, UploadResult
from research_hub.notebooklm.session import PlaywrightSession, SessionConfig, login_interactive
from research_hub.notebooklm.upload import UploadReport, generate_artifact, upload_cluster

__all__ = [
    "BundleReport",
    "NotebookHandle",
    "NotebookLMClient",
    "NotebookLMError",
    "PlaywrightSession",
    "SessionConfig",
    "UploadReport",
    "UploadResult",
    "bundle_cluster",
    "generate_artifact",
    "login_interactive",
    "upload_cluster",
]
