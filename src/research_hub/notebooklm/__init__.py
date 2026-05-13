"""NotebookLM integration backed by notebooklm-py."""

from research_hub.notebooklm.auth import (
    ImportResult,
    check_session_health,
    default_session_dir,
    default_state_file,
    import_session,
    login_interactive,
    login_interactive_cdp,
    login_nlm,
)
from research_hub.notebooklm.bundle import BundleReport, bundle_cluster
from research_hub.notebooklm.client import (
    BriefingArtifact,
    NotebookHandle,
    NotebookLMClient,
    NotebookLMError,
    UploadResult,
)
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
    "ImportResult",
    "NotebookHandle",
    "NotebookLMClient",
    "NotebookLMError",
    "UploadReport",
    "UploadResult",
    "bundle_cluster",
    "check_session_health",
    "default_session_dir",
    "default_state_file",
    "download_briefing_for_cluster",
    "generate_artifact",
    "import_session",
    "login_interactive",
    "login_interactive_cdp",
    "login_nlm",
    "read_latest_briefing",
    "upload_cluster",
]
