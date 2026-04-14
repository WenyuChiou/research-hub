from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import pytest

from research_hub.clusters import ClusterRegistry
from research_hub.dashboard import render_dashboard_from_config
from research_hub.dashboard.manage_commands import (
    build_compose_draft_command,
    build_manage_command,
    shell_quote,
)


class _Cfg:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.raw = root / "raw"
        self.hub = root / "hub"
        self.research_hub_dir = root / ".research_hub"
        self.clusters_file = self.research_hub_dir / "clusters.yaml"
        self.no_zotero = False
        self.raw.mkdir(parents=True, exist_ok=True)
        self.hub.mkdir(parents=True, exist_ok=True)
        self.research_hub_dir.mkdir(parents=True, exist_ok=True)


def _make_cfg(tmp_path: Path) -> _Cfg:
    return _Cfg(tmp_path / "vault")


def _write_note(
    cfg: _Cfg,
    cluster_slug: str,
    filename: str,
    *,
    title: str = "Paper One",
    doi: str = "10.1000/one",
    labels: str = "[seed]",
    tags: str = "[agents, memory]",
    zotero_key: str = "ABC123",
) -> Path:
    note_dir = cfg.raw / cluster_slug
    note_dir.mkdir(parents=True, exist_ok=True)
    path = note_dir / filename
    path.write_text(
        "---\n"
        f'title: "{title}"\n'
        'authors: "Doe, Jane"\n'
        'year: "2025"\n'
        f'doi: "{doi}"\n'
        f'tags: {tags}\n'
        f'labels: {labels}\n'
        f"zotero-key: {zotero_key}\n"
        'status: "reading"\n'
        'ingested_at: "2026-04-12T12:00:00Z"\n'
        'abstract: "Compact abstract."\n'
        f'topic_cluster: "{cluster_slug}"\n'
        "---\n"
        "Body\n",
        encoding="utf-8",
    )
    return path


def _render_dashboard_html(tmp_path: Path, monkeypatch, *, with_cluster: bool = True) -> str:
    cfg = _make_cfg(tmp_path)
    if with_cluster:
        ClusterRegistry(cfg.clusters_file).create(query="agents", name="Agents", slug="agents")
        _write_note(cfg, "agents", "paper-one.md")
        archive_dir = cfg.raw / "_archive" / "agents"
        archive_dir.mkdir(parents=True, exist_ok=True)
        (archive_dir / "old-paper.md").write_text(
            "---\n"
            'title: "Old Paper"\n'
            'labels: [deprecated]\n'
            'fit_reason: "off topic"\n'
            "---\nArchived\n",
            encoding="utf-8",
        )
    monkeypatch.setattr("research_hub.dashboard.data.run_doctor", lambda: [])
    monkeypatch.setattr("research_hub.dashboard.data.detect_drift", lambda cfg, dedup: [])
    return render_dashboard_from_config(cfg)


@pytest.mark.parametrize(
    ("action", "slug", "fields", "expected"),
    [
        ("rename", "foo", {"new_name": "Bar"}, "research-hub clusters rename foo --name Bar"),
        ("rename", "foo", {"new_name": "Foo Bar"}, 'research-hub clusters rename foo --name "Foo Bar"'),
        ("merge", "foo", {"target": "bar"}, "research-hub clusters merge foo --into bar"),
        (
            "split",
            "foo",
            {"query": "LLM", "new_name": "Sub"},
            "research-hub clusters split foo --query LLM --new-name Sub",
        ),
        ("bind-zotero", "foo", {"zotero": "ABC123"}, "research-hub clusters bind foo --zotero ABC123"),
        (
            "bind-nlm",
            "foo",
            {"notebooklm": "https://notebooklm.google.com/notebook/123"},
            'research-hub clusters bind foo --notebooklm "https://notebooklm.google.com/notebook/123"',
        ),
        ("delete", "foo", {}, "research-hub clusters delete foo --dry-run"),
    ],
)
def test_build_manage_command(action, slug, fields, expected):
    assert build_manage_command(action, slug, **fields) == expected


def test_build_manage_command_unknown_action_raises():
    with pytest.raises(ValueError):
        build_manage_command("nuke", "foo")


def test_build_manage_command_incomplete_fields_return_none():
    assert build_manage_command("rename", "foo", new_name="") is None
    assert build_manage_command("merge", "foo", target="foo") is None
    assert build_manage_command("split", "foo", query="", new_name="bar") is None
    assert build_manage_command("bind-zotero", "foo", zotero="") is None


def test_shell_quote_escapes_special_chars():
    assert shell_quote('foo"bar') == '"foo\\"bar"'
    assert shell_quote("foo bar") == '"foo bar"'
    assert shell_quote("simple") == "simple"
    assert shell_quote("") == '""'
    assert shell_quote(None) == '""'


def test_build_compose_draft_command_minimal():
    assert build_compose_draft_command("my-cluster") == "research-hub compose-draft --cluster my-cluster"


def test_build_compose_draft_command_full():
    out = build_compose_draft_command(
        "my-cluster",
        outline="Intro;Methods;Results",
        quote_slugs=["slug1", "slug2"],
        style="chicago",
    )
    assert '--cluster my-cluster' in out
    assert '--outline "Intro;Methods;Results"' in out
    assert '--quotes "slug1,slug2"' in out
    assert '--style chicago' in out


def test_copy_button_data_attributes_present_in_render(tmp_path, monkeypatch):
    html = _render_dashboard_html(tmp_path, monkeypatch)
    copy_payloads = re.findall(r'class="copy-cmd-btn"[^>]*data-text="([^"]+)"', html)
    cite_payloads = re.findall(r'class="cite-btn"[^>]*data-bibtex="([^"]+)"', html)
    assert copy_payloads
    assert all(item.strip() for item in copy_payloads)
    assert cite_payloads
    assert all(item.strip() for item in cite_payloads)


def test_obsidian_url_absolute_path_in_render(tmp_path, monkeypatch):
    html = _render_dashboard_html(tmp_path, monkeypatch)
    hrefs = re.findall(r'href="(obsidian://open\?path=[^"]+)"', html)
    assert hrefs
    for href in hrefs:
        parsed = urlparse(href)
        encoded_path = parse_qs(parsed.query).get("path", [""])[0]
        decoded = unquote(encoded_path)
        assert decoded
        assert Path(decoded).is_absolute(), decoded


def test_no_hash_anchor_navigation_in_render():
    script = (Path("src/research_hub/dashboard/script.js")).read_text(encoding="utf-8")
    filtered = "\n".join(line for line in script.splitlines() if not line.strip().startswith("//"))
    assert "window.location.hash =" not in filtered


def test_all_tabs_have_empty_state_rendering(tmp_path, monkeypatch):
    html = _render_dashboard_html(tmp_path, monkeypatch, with_cluster=False)
    for tab_id in (
        "tab-overview",
        "tab-library",
        "tab-briefings",
        "tab-writing",
        "tab-diagnostics",
        "tab-manage",
    ):
        assert f'id="{tab_id}"' in html
    assert "No clusters bound yet." in html
    assert 'No clusters yet. Run <code>research-hub clusters new --query "topic"</code>' in html
    assert "No briefings downloaded yet." in html
