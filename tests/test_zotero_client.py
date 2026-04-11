"""Tests for research_hub.zotero.client helpers."""

from __future__ import annotations

import json
import urllib.error
from pathlib import Path


def _write_hub_config(tmp_path: Path, *, library_id: str | None = None) -> Path:
    config_path = tmp_path / "config.json"
    payload = {"knowledge_base": {"root": str(tmp_path / "kb")}}
    if library_id is not None:
        payload["zotero"] = {"library_id": library_id}
    config_path.write_text(json.dumps(payload), encoding="utf-8")
    return config_path


def test_check_local_api_returns_false_without_library_id(tmp_path, monkeypatch):
    from research_hub import config as hub_config
    from research_hub.zotero.client import check_local_api

    hub_config._config = None
    monkeypatch.setattr(hub_config, "CONFIG_PATH", _write_hub_config(tmp_path))

    assert check_local_api() is False

    hub_config._config = None


def test_check_local_api_probes_configured_library_id(tmp_path, monkeypatch):
    from research_hub import config as hub_config
    from research_hub.zotero.client import check_local_api

    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_urlopen(request, timeout=0):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        return Response()

    hub_config._config = None
    monkeypatch.setattr(hub_config, "CONFIG_PATH", _write_hub_config(tmp_path, library_id="99999"))
    monkeypatch.setattr("research_hub.zotero.client.urllib.request.urlopen", fake_urlopen)

    assert check_local_api() is True
    assert "/users/99999/" in captured["url"]

    hub_config._config = None


def test_check_local_api_returns_false_on_network_error(tmp_path, monkeypatch):
    from research_hub import config as hub_config
    from research_hub.zotero.client import check_local_api

    hub_config._config = None
    monkeypatch.setattr(hub_config, "CONFIG_PATH", _write_hub_config(tmp_path, library_id="99999"))
    monkeypatch.setattr(
        "research_hub.zotero.client.urllib.request.urlopen",
        lambda request, timeout=0: (_ for _ in ()).throw(urllib.error.URLError("unreachable")),
    )

    assert check_local_api() is False

    hub_config._config = None


def test_load_credentials_env_vars_win_over_config(tmp_path, monkeypatch):
    from research_hub.zotero.client import _load_credentials
    import research_hub.zotero.client as zotero_client

    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "zotero_api_key": "config-key",
                "zotero_library_id": "config-lib",
                "zotero_library_type": "group",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(zotero_client, "_CONFIG_PATH", config_path)
    monkeypatch.setenv("ZOTERO_API_KEY", "env-key")
    monkeypatch.setenv("ZOTERO_LIBRARY_ID", "env-lib")
    monkeypatch.setenv("ZOTERO_LIBRARY_TYPE", "user")

    assert _load_credentials() == ("env-key", "env-lib", "user")


def test_load_credentials_from_env_file(tmp_path, monkeypatch):
    from research_hub.zotero.client import _load_credentials

    home = tmp_path / "home"
    env_file = home / ".claude" / ".env"
    env_file.parent.mkdir(parents=True, exist_ok=True)
    env_file.write_text(
        'ZOTERO_API_KEY="file-key"\nZOTERO_LIBRARY_ID=file-lib\nZOTERO_LIBRARY_TYPE=group\n',
        encoding="utf-8",
    )

    monkeypatch.delenv("ZOTERO_API_KEY", raising=False)
    monkeypatch.delenv("ZOTERO_LIBRARY_ID", raising=False)
    monkeypatch.delenv("ZOTERO_LIBRARY_TYPE", raising=False)
    monkeypatch.setattr("research_hub.zotero.client.Path.home", lambda: home)

    assert _load_credentials() == ("file-key", "file-lib", "group")
