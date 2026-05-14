"""v0.89.0 - structured bootstrap probe report for autonomous agents."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BootstrapReport:
    version: str = ""
    vault_path: str = ""
    vault_exists: bool = False
    persona: str = ""
    env_vars_present: dict[str, bool] = field(default_factory=dict)
    env_vars_missing: list[str] = field(default_factory=list)
    nlm_auth_status: str = "missing"
    zotero_reachable: bool = False
    zotero_error: str = ""
    llm_cli_detected: str = ""
    skills_installed: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return not self.env_vars_missing and self.zotero_reachable

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "vault_path": self.vault_path,
            "vault_exists": self.vault_exists,
            "persona": self.persona,
            "env_vars_present": dict(self.env_vars_present),
            "env_vars_missing": list(self.env_vars_missing),
            "nlm_auth_status": self.nlm_auth_status,
            "zotero_reachable": self.zotero_reachable,
            "zotero_error": self.zotero_error,
            "llm_cli_detected": self.llm_cli_detected,
            "skills_installed": list(self.skills_installed),
            "issues": list(self.issues),
            "ready": self.ready,
        }
