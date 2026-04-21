"""Bundled zero-account sample vault for dashboard preview."""

from __future__ import annotations

import os
import shutil
import tempfile
import webbrowser
import uuid
from importlib import resources
from pathlib import Path


SAMPLE_BANNER = (
    "SAMPLE PREVIEW - this vault is read-only and temporary. "
    "Run `research-hub init` to make your own."
)


def sample_vault_source() -> Path:
    """Return the packaged sample vault directory."""
    return Path(str(resources.files("research_hub.samples").joinpath("sample_vault")))


def copy_sample_vault(destination: Path | None = None) -> Path:
    """Copy the bundled sample vault to a temporary location."""
    source = sample_vault_source()
    generated_destination = destination is None
    if destination is None:
        destination = Path(tempfile.mkdtemp(prefix="research-hub-sample-"))
    destination = destination.resolve()
    if destination.exists() and not generated_destination:
        shutil.rmtree(destination)
    try:
        shutil.copytree(source, destination, dirs_exist_ok=generated_destination)
    except (PermissionError, shutil.Error):
        if not generated_destination:
            raise
        fallback_parent = Path.cwd() / ".research_hub_samples"
        fallback_parent.mkdir(parents=True, exist_ok=True)
        destination = fallback_parent / f"research-hub-sample-{uuid.uuid4().hex[:8]}"
        destination.mkdir(parents=True, exist_ok=False)
        shutil.copytree(source, destination, dirs_exist_ok=True)
    return destination


def _inject_sample_banner(html: str) -> str:
    banner = (
        '<div role="note" style="padding:10px 18px;background:#fff7cc;'
        'border-bottom:1px solid #d8b74a;color:#2f2a12;font:14px system-ui, sans-serif;">'
        'SAMPLE PREVIEW - this vault is read-only and temporary. '
        'Run <code>research-hub init</code> to make your own.'
        "</div>"
    )
    return html.replace("<body>", f"<body>\n  {banner}", 1)


def generate_sample_dashboard(*, open_browser: bool = False, rich_bibtex: bool = False) -> Path:
    """Render the normal dashboard against a copied sample vault."""
    import json

    import research_hub.config as config_mod
    from research_hub.dashboard import generate_dashboard
    from research_hub.security import atomic_write_text

    sample_root = copy_sample_vault()
    config_path = sample_root / ".research_hub" / "sample_config.json"
    config_path.write_text(
        json.dumps(
            {
                "knowledge_base": {"root": str(sample_root)},
                "clusters_file": str(sample_root / ".research_hub" / "clusters.yaml"),
                "persona": "researcher",
                "no_zotero": True,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    old_env = {
        "RESEARCH_HUB_CONFIG": os.environ.get("RESEARCH_HUB_CONFIG"),
        "RESEARCH_HUB_ALLOW_EXTERNAL_ROOT": os.environ.get("RESEARCH_HUB_ALLOW_EXTERNAL_ROOT"),
    }
    old_cache = (config_mod._config, config_mod._config_path)
    try:
        os.environ["RESEARCH_HUB_CONFIG"] = str(config_path)
        os.environ["RESEARCH_HUB_ALLOW_EXTERNAL_ROOT"] = "1"
        config_mod._config = None
        config_mod._config_path = None
        out_path = generate_dashboard(open_browser=False, rich_bibtex=rich_bibtex)
        html = _inject_sample_banner(out_path.read_text(encoding="utf-8"))
        atomic_write_text(out_path, html, encoding="utf-8")
    finally:
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        config_mod._config, config_mod._config_path = old_cache

    if open_browser:
        webbrowser.open(out_path.as_uri())
    return out_path
