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

    monkeypatch.setattr(
        zotero_client,
        "_load_config",
        lambda: {
            "zotero_api_key": "config-key",
            "zotero_library_id": "config-lib",
            "zotero_library_type": "group",
        },
    )
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


def test_get_formatted_rejects_unknown_format():
    from research_hub.zotero.client import ZoteroDualClient

    dual = ZoteroDualClient.__new__(ZoteroDualClient)  # skip __init__

    import pytest

    with pytest.raises(ValueError, match="Unsupported content format"):
        dual.get_formatted("ABC123", content_format="yaml")


def test_get_formatted_joins_list_from_read():
    from research_hub.zotero.client import ZoteroDualClient

    dual = ZoteroDualClient.__new__(ZoteroDualClient)

    captured = {}

    def fake_read(method_name, *args, **kwargs):
        captured["method"] = method_name
        captured["args"] = args
        captured["kwargs"] = kwargs
        return ["@article{first}", "@article{second}"]

    dual._read = fake_read
    result = dual.get_formatted("ABC123", content_format="bibtex")

    assert captured["method"] == "item"
    assert captured["args"] == ("ABC123",)
    assert captured["kwargs"] == {"content": "bibtex"}
    assert "@article{first}" in result
    assert "@article{second}" in result


def _make_dual_for_update(fetched_data: dict) -> tuple:
    """Build a ZoteroDualClient (no __init__) with a mocked web for update_collection tests.

    ``fetched_data`` is placed under ``coll["data"]``.  Returns ``(dual, web_mock)``
    where ``web_mock.update_collection`` records its call argument.
    """
    from unittest.mock import MagicMock
    from research_hub.zotero.client import ZoteroDualClient

    dual = ZoteroDualClient.__new__(ZoteroDualClient)
    web = MagicMock(spec=["collection", "update_collection"])
    # collection() returns a full collection dict with a "data" sub-dict
    coll_payload = {
        "key": fetched_data["key"],
        "version": fetched_data.get("version", 5),
        "data": dict(fetched_data),
    }
    web.collection.return_value = coll_payload
    web.update_collection.return_value = {}
    dual.web = web
    dual._require_web = lambda: None  # no credentials check in unit tests
    return dual, web


def test_update_collection_name_only_preserves_parent_collection():
    """Changing only the name must not blank or drop parentCollection."""
    dual, web = _make_dual_for_update({
        "key": "K1",
        "version": 3,
        "name": "Old Name",
        "parentCollection": "PKEY",
    })

    dual.update_collection("K1", name="New Name")

    web.update_collection.assert_called_once()
    sent = web.update_collection.call_args[0][0]
    # The full collection dict was passed; data must be mutated in-place
    assert sent["data"]["name"] == "New Name"
    assert sent["data"]["parentCollection"] == "PKEY", (
        "parentCollection must be preserved when only name changes"
    )


def test_update_collection_parent_only_preserves_name():
    """Changing only the parent must not blank or drop the existing name."""
    dual, web = _make_dual_for_update({
        "key": "K2",
        "version": 7,
        "name": "Keep This Name",
        "parentCollection": False,
    })

    dual.update_collection("K2", parent_key="NEWPARENT")

    web.update_collection.assert_called_once()
    sent = web.update_collection.call_args[0][0]
    assert sent["data"]["name"] == "Keep This Name", (
        "name must be preserved when only parentCollection changes"
    )
    assert sent["data"]["parentCollection"] == "NEWPARENT"


def test_update_collection_both_name_and_parent():
    """Both name and parentCollection can be changed in one call."""
    dual, web = _make_dual_for_update({
        "key": "K3",
        "version": 2,
        "name": "Original",
        "parentCollection": "OLD_PARENT",
        "relations": {},
    })

    dual.update_collection("K3", name="Renamed", parent_key="NEW_PARENT")

    web.update_collection.assert_called_once()
    sent = web.update_collection.call_args[0][0]
    assert sent["data"]["name"] == "Renamed"
    assert sent["data"]["parentCollection"] == "NEW_PARENT"
    # Other fields on data (relations) must not be dropped
    assert sent["data"]["relations"] == {}


def test_update_collection_payload_derived_from_fetched_collection():
    """The dict passed to web.update_collection must include the fetched collection's
    data fields, not a hand-built minimal payload that could blank existing fields."""
    dual, web = _make_dual_for_update({
        "key": "K4",
        "version": 11,
        "name": "Existing",
        "parentCollection": "P",
        "extra_field": "preserved",
    })

    dual.update_collection("K4", parent_key="P2")

    sent = web.update_collection.call_args[0][0]
    # Must be the full collection object (has "data" sub-dict), not a flat payload
    assert "data" in sent, "payload must be the full collection dict with a 'data' key"
    assert sent["data"]["extra_field"] == "preserved", (
        "extra fields in data must survive the PATCH (not blanked)"
    )


def test_update_collection_fallback_on_missing_data():
    """If the fetched collection has no 'data' key, fall back to minimal payload (no crash)."""
    from unittest.mock import MagicMock
    from research_hub.zotero.client import ZoteroDualClient

    dual = ZoteroDualClient.__new__(ZoteroDualClient)
    web = MagicMock(spec=["collection", "update_collection"])
    # Unusual shape: no "data" key
    web.collection.return_value = {"key": "K5", "version": 99}
    web.update_collection.return_value = {}
    dual.web = web
    dual._require_web = lambda: None

    # Must not raise; should still call web.update_collection
    dual.update_collection("K5", name="X", parent_key="PX")

    web.update_collection.assert_called_once()


def test_read_zotero_key_from_frontmatter(tmp_path):
    from research_hub.cli import _read_zotero_key_from_frontmatter

    md = tmp_path / "paper.md"
    md.write_text(
        "---\n"
        'title: "Example"\n'
        "year: 2025\n"
        "zotero-key: ABCD1234\n"
        "---\n"
        "\n# body\n",
        encoding="utf-8",
    )
    assert _read_zotero_key_from_frontmatter(md) == "ABCD1234"

    empty = tmp_path / "empty.md"
    empty.write_text("no frontmatter here\n", encoding="utf-8")
    assert _read_zotero_key_from_frontmatter(empty) is None
