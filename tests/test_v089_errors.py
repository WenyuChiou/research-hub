from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from research_hub.auto import _invoke_llm_cli
from research_hub.errors import (
    MissingCredential,
    MissingExternalTool,
    ResearchHubError,
    RequiresAuthRefresh,
    UpstreamRateLimited,
    UpstreamUnavailable,
)


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (
            ResearchHubError(
                "base failure",
                context={"kind": "base"},
                next_steps=["inspect"],
            ),
            {
                "error_code": "research_hub_error",
                "message": "base failure",
                "context": {"kind": "base"},
                "next_steps": ["inspect"],
            },
        ),
        (
            MissingCredential(
                "Zotero API key",
                env_var="ZOTERO_API_KEY",
                fallback_paths_tried=["$ZOTERO_API_KEY", "config.json"],
            ),
            {
                "error_code": "missing_credential",
                "message": "Missing credential: Zotero API key. Set $ZOTERO_API_KEY.",
                "context": {
                    "name": "Zotero API key",
                    "env_var": "ZOTERO_API_KEY",
                    "fallback_paths_tried": ["$ZOTERO_API_KEY", "config.json"],
                },
                "next_steps": ["export ZOTERO_API_KEY=<value>"],
            },
        ),
        (
            RequiresAuthRefresh(
                "NotebookLM",
                fix_command="python -m research_hub notebooklm login --auto-detect",
            ),
            {
                "error_code": "requires_auth_refresh",
                "message": "NotebookLM session expired. Run: python -m research_hub notebooklm login --auto-detect",
                "context": {"service": "NotebookLM"},
                "next_steps": ["python -m research_hub notebooklm login --auto-detect"],
            },
        ),
        (
            MissingExternalTool(
                "codex",
                install_hint="npm i -g @anthropic-ai/codex",
            ),
            {
                "error_code": "missing_external_tool",
                "message": "'codex' not on PATH. npm i -g @anthropic-ai/codex",
                "context": {"tool": "codex"},
                "next_steps": ["npm i -g @anthropic-ai/codex"],
            },
        ),
        (
            UpstreamRateLimited("Semantic Scholar", retry_after=2.5),
            {
                "error_code": "upstream_rate_limited",
                "message": "Semantic Scholar rate-limited (HTTP 429)",
                "context": {"service": "Semantic Scholar", "retry_after": 2.5},
                "next_steps": [],
            },
        ),
        (
            UpstreamUnavailable("NotebookLM", status_code=503),
            {
                "error_code": "upstream_unavailable",
                "message": "NotebookLM unreachable (status=503)",
                "context": {"service": "NotebookLM", "status_code": 503},
                "next_steps": [],
            },
        ),
    ],
)
def test_error_to_dict_round_trips(exc: ResearchHubError, expected: dict[str, object]):
    assert exc.error_code == expected["error_code"]
    assert exc.to_dict() == expected


def test_missing_credential_context_includes_env_var_and_fallbacks():
    exc = MissingCredential(
        "Zotero API key",
        env_var="ZOTERO_API_KEY",
        fallback_paths_tried=["$ZOTERO_API_KEY", "C:/config.json"],
    )

    assert exc.context["env_var"] == "ZOTERO_API_KEY"
    assert exc.context["fallback_paths_tried"] == ["$ZOTERO_API_KEY", "C:/config.json"]


def test_notebooklm_error_backwards_compat_import():
    from research_hub.notebooklm.client import NotebookLMError

    assert issubclass(NotebookLMError, ResearchHubError)


def test_rate_limit_error_backwards_compat_import():
    from research_hub.search.semantic_scholar import RateLimitError

    assert issubclass(RateLimitError, UpstreamRateLimited)


def test_invoke_llm_cli_missing_tool_raises_structured_error(monkeypatch):
    monkeypatch.setattr("research_hub.llm_cli.shutil.which", lambda _name: None)

    with pytest.raises(MissingExternalTool) as excinfo:
        _invoke_llm_cli("codex", "hello")

    assert excinfo.value.context["tool"] == "codex"
    assert excinfo.value.next_steps == ["npm i -g @openai/codex"]


def test_get_client_missing_api_key_raises_structured_error(monkeypatch):
    import importlib
    import research_hub.zotero.client as zotero_client

    zotero_client = importlib.reload(zotero_client)
    monkeypatch.setattr(zotero_client, "_load_credentials", lambda: (None, "123456", "user"))
    monkeypatch.setattr(
        zotero_client,
        "zotero_credential_fallback_paths",
        lambda: ["$ZOTERO_API_KEY", "config.json"],
    )

    with pytest.raises(MissingCredential) as excinfo:
        zotero_client.get_client()

    assert excinfo.value.context["env_var"] == "ZOTERO_API_KEY"
    assert excinfo.value.context["fallback_paths_tried"] == ["$ZOTERO_API_KEY", "config.json"]


def test_cli_json_mode_emits_structured_missing_credential(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]
    src_path = repo_root / "src"
    vault_root = tmp_path / "vault"
    research_hub_dir = vault_root / ".research_hub"
    raw_dir = vault_root / "raw"
    research_hub_dir.mkdir(parents=True)
    raw_dir.mkdir(parents=True)

    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "knowledge_base": {"root": str(vault_root)},
                "zotero": {"library_id": "123456"},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    dedup_index_path = research_hub_dir / "dedup_index.json"
    dedup_index_path.write_text(
        json.dumps(
            {
                "doi_to_hits": {
                    "10.1000/example": [
                        {
                            "source": "zotero",
                            "doi": "10.1000/example",
                            "title": "Example",
                            "zotero_key": "ABC123",
                            "obsidian_path": None,
                        }
                    ]
                },
                "title_to_hits": {},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    helper_script = tmp_path / "invoke_cli.py"
    helper_script.write_text(
        "\n".join(
            [
                "from __future__ import annotations",
                "import sys",
                f"sys.path.insert(0, {str(src_path)!r})",
                "from research_hub import cli",
                "import research_hub.zotero.client as zotero_client",
                "",
                "zotero_client._load_credentials = lambda: (None, '123456', 'user')",
                "raise SystemExit(cli.main(['dedup', 'compact', '--json']))",
                "",
            ]
        ),
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["RESEARCH_HUB_CONFIG"] = str(config_path)
    env["RESEARCH_HUB_ALLOW_EXTERNAL_ROOT"] = "1"
    env.pop("ZOTERO_API_KEY", None)

    proc = subprocess.run(
        [sys.executable, str(helper_script)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert proc.returncode == 1
    payload = json.loads(proc.stdout)
    assert payload["ok"] is False
    assert payload["error"]["error_code"] == "missing_credential"
    assert payload["error"]["context"]["env_var"] == "ZOTERO_API_KEY"
