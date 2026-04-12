from __future__ import annotations

import json
from pathlib import Path

from research_hub.config import get_config
from research_hub.vault_search import search_vault


def _make_config(tmp_path: Path, monkeypatch):
    root = tmp_path / "vault"
    raw = root / "raw"
    raw.mkdir(parents=True)
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"knowledge_base": {"root": str(root), "raw": str(raw)}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("RESEARCH_HUB_CONFIG", str(config_path))
    return get_config()


def _write_note(path: Path, *, title: str, cluster: str, status: str, body: str = ""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        f'title: "{title}"\n'
        f'topic_cluster: "{cluster}"\n'
        f"status: {status}\n"
        "---\n"
        f"{body}\n",
        encoding="utf-8",
    )


def test_search_vault_title_search(tmp_path, monkeypatch):
    cfg = _make_config(tmp_path, monkeypatch)
    _write_note(cfg.raw / "alpha" / "paper-one.md", title="Flood Risk Agents", cluster="alpha", status="unread")

    result = search_vault("flood agents")

    assert [item["slug"] for item in result] == ["paper-one"]


def test_search_vault_full_text_search(tmp_path, monkeypatch):
    cfg = _make_config(tmp_path, monkeypatch)
    _write_note(
        cfg.raw / "alpha" / "paper-one.md",
        title="Other Title",
        cluster="alpha",
        status="unread",
        body="Contains important downstream evidence.",
    )

    result = search_vault("downstream evidence", full_text=True)

    assert [item["slug"] for item in result] == ["paper-one"]


def test_search_vault_cluster_filter(tmp_path, monkeypatch):
    cfg = _make_config(tmp_path, monkeypatch)
    _write_note(cfg.raw / "alpha" / "one.md", title="Flood Risk Agents", cluster="alpha", status="unread")
    _write_note(cfg.raw / "beta" / "two.md", title="Flood Risk Agents", cluster="beta", status="unread")

    result = search_vault("flood", cluster="beta")

    assert [item["cluster"] for item in result] == ["beta"]


def test_search_vault_status_filter(tmp_path, monkeypatch):
    cfg = _make_config(tmp_path, monkeypatch)
    _write_note(cfg.raw / "alpha" / "one.md", title="Flood Risk Agents", cluster="alpha", status="unread")
    _write_note(cfg.raw / "alpha" / "two.md", title="Flood Risk Analysis", cluster="alpha", status="cited")

    result = search_vault("flood", status="cited")

    assert [item["slug"] for item in result] == ["two"]


def test_search_vault_limit(tmp_path, monkeypatch):
    cfg = _make_config(tmp_path, monkeypatch)
    for idx in range(3):
        _write_note(
            cfg.raw / "alpha" / f"paper-{idx}.md",
            title=f"Flood Note {idx}",
            cluster="alpha",
            status="unread",
        )

    result = search_vault("flood", limit=2)

    assert len(result) == 2
