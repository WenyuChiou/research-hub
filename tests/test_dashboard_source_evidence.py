"""Read-only native-source evidence must never masquerade as remote sync."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from research_hub.clusters import ClusterRegistry
from research_hub.dashboard.data import collect_dashboard_data
from research_hub.dashboard.sections import LibrarySection
from research_hub.dashboard.types import ClusterCard, DashboardData, PaperRow


@pytest.fixture
def native_source(tmp_path, monkeypatch):
    root = tmp_path / "vault"
    cfg = SimpleNamespace(root=root, raw=root / "raw", research_hub_dir=root / ".research_hub", no_zotero=True, persona="analyst")
    cfg.clusters_file = cfg.research_hub_dir / "clusters.yaml"
    cfg.hub = root / "hub"
    cfg.raw.mkdir(parents=True)
    cfg.research_hub_dir.mkdir()
    ClusterRegistry(cfg.clusters_file).create(query="evidence", name="Evidence", slug="evidence")
    note = cfg.raw / "evidence" / "paper.md"
    note.parent.mkdir()
    note.write_text('---\ntitle: "Synthetic source"\ndoi: "10.1000/example"\ntopic_cluster: "evidence"\nzotero-key: "ABC12345"\n---\nManual notes remain.\n', encoding="utf-8")
    monkeypatch.setattr("research_hub.dashboard.data.run_doctor", lambda: [])
    monkeypatch.setattr("research_hub.dashboard.data.detect_drift", lambda cfg, dedup: [])
    return cfg, note


def _collect(native_source, payload=None, *, raw=None):
    cfg, note = native_source
    cache = cfg.research_hub_dir / "nlm_cache.json"
    if raw is not None:
        cache.write_text(raw, encoding="utf-8")
    elif payload is not None:
        cache.write_text(json.dumps(payload), encoding="utf-8")
    before = {p: p.read_bytes() for p in (note, cache) if p.exists()}
    data = collect_dashboard_data(cfg)
    assert {p: p.read_bytes() for p in before} == before
    assert len(data.clusters) == 1
    assert len(data.clusters[0].papers) == 1
    return data, data.clusters[0].papers[0]


def test_library_exposes_native_identity_without_remote_success(native_source):
    data, paper = _collect(native_source)
    html = LibrarySection().render(data)
    assert 'class="source-evidence"' in html
    assert "ABC12345" in html  # Recorded even in analyst persona; not a live Zotero check.
    assert str(native_source[1]) in html
    assert "10.1000/example" in html
    assert "Remote sync: unknown" in html
    assert "No automatic upload, replacement or deletion" in html
    assert paper.nlm_source_evidence.state == "unknown"
    assert paper.nlm_source_evidence.reason == "cache_missing"


@pytest.mark.parametrize("raw", ['{broken', '[]', 'null', '"cache"'])
def test_invalid_cache_retains_library_and_explains_unknown(native_source, raw):
    data, paper = _collect(native_source, raw=raw)
    assert paper.nlm_source_evidence.reason == "cache_invalid"
    html = LibrarySection().render(data)
    assert "local cache format is invalid" in html
    assert "Remote sync: unknown" in html
    assert "Inspect the local cache file" in html


@pytest.mark.parametrize("cluster_cache", [[], None, {"uploaded_sources": "10.1000/example"}, {"uploaded_sources": [None]}, {"uploaded_sources": [{}]}])
def test_invalid_cluster_shapes_do_not_hide_the_paper(native_source, cluster_cache):
    _, paper = _collect(native_source, {"evidence": cluster_cache})
    assert paper.nlm_source_evidence.reason == "cache_invalid"


def test_exact_cached_identity_without_version_is_not_sync_success(native_source):
    data, paper = _collect(native_source, {"evidence": {"uploaded_sources": ["10.1000/example"]}})
    assert paper.nlm_source_evidence.state == "recorded"
    assert paper.nlm_source_evidence.reason == "version_unknown"
    assert paper.nlm_source_evidence.source_key == "10.1000/example"
    assert not paper.nlm_source_evidence.payload_sha256
    html = LibrarySection().render(data)
    assert "uploaded payload fingerprint is unavailable" in html
    assert "Remote sync: unknown" in html
    assert "Manually compare the source" in html
    assert "Historical payload SHA-256" not in html


def test_cached_fingerprint_is_historical_and_collapsed(native_source):
    digest = "a" * 64
    data, paper = _collect(native_source, {"evidence": {
        "uploaded_sources": ["10.1000/example"],
        "source_versions": {"10.1000/example": {"kind": "text", "sha256": digest}},
    }})
    assert paper.nlm_source_evidence.payload_sha256 == digest
    assert paper.nlm_source_evidence.payload_kind == "text"
    html = LibrarySection().render(data)
    assert "current content and remote state were not checked" in html
    assert "Historical fingerprint recorded; not current-version verification" in html
    assert '<details class="source-evidence-technical">' in html
    assert digest in html.split('<details class="source-evidence-technical">')[1].split('</details>')[0]
    assert 'class="source-evidence-technical" open' not in html
    assert "Remote sync: unknown" in html


@pytest.mark.parametrize("version", [None, [], "old", {}, {"kind": "text", "sha256": "bad"}, {"kind": "url", "sha256": "a" * 64}, {"kind": [], "sha256": "a" * 64}, {"kind": "pdf", "sha256": 7}])
def test_invalid_or_unsupported_versions_remain_unknown(native_source, version):
    _, paper = _collect(native_source, {"evidence": {
        "uploaded_sources": ["10.1000/example"], "source_versions": {"10.1000/example": version},
    }})
    assert paper.nlm_source_evidence.reason == "version_unknown"
    assert not paper.nlm_source_evidence.payload_sha256


@pytest.mark.parametrize("versions", [[], None, "legacy"])
def test_malformed_version_map_does_not_break_library(native_source, versions):
    _, paper = _collect(native_source, {"evidence": {"uploaded_sources": ["10.1000/example"], "source_versions": versions}})
    assert paper.nlm_source_evidence.reason == "version_unknown"


@pytest.mark.parametrize("cache", [
    {"uploaded_sources": ["10.1000/other"]},
    {"uploaded_sources": ["https://doi.org/10.1000/example"]},
    {"uploaded_sources": ["/different/bundle/paper.pdf"]},
    {"shard_uploaded_sources": {"shard-1": ["10.1000/example"]}},
    {"source_versions": {"10.1000/example": {"kind": "text", "sha256": "a" * 64}}},
])
def test_no_inferred_identity_from_bundle_shard_url_or_orphan_version(native_source, cache):
    data, paper = _collect(native_source, {"evidence": cache})
    assert paper.nlm_source_evidence.reason == "identity_not_linked"
    assert not paper.nlm_source_evidence.source_key
    assert not paper.nlm_source_evidence.payload_sha256
    assert "does not establish remote absence" in LibrarySection().render(data)


def test_ambiguous_note_and_doi_matches_do_not_select_a_version(native_source):
    _, paper = _collect(native_source, {"evidence": {
        "uploaded_sources": ["10.1000/example", str(native_source[1])],
        "source_versions": {"10.1000/example": {"kind": "text", "sha256": "a" * 64}},
    }})
    assert paper.nlm_source_evidence.reason == "identity_ambiguous"
    assert not paper.nlm_source_evidence.payload_sha256


def test_exact_note_path_identity_is_not_normalized_or_resolved(native_source):
    _, paper = _collect(native_source, {"evidence": {"uploaded_sources": [str(native_source[1])]}})
    assert paper.nlm_source_evidence.reason == "version_unknown"
    assert paper.nlm_source_evidence.source_key == str(native_source[1])


def test_cache_read_permission_failure_has_fixed_reason_without_private_error(native_source, monkeypatch):
    cfg, _ = native_source
    original = Path.read_text
    def read(path, *args, **kwargs):
        if path == cfg.research_hub_dir / "nlm_cache.json":
            raise PermissionError("sensitive exception detail")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", read)
    data, paper = _collect(native_source)
    assert paper.nlm_source_evidence.reason == "cache_unreadable"
    html = LibrarySection().render(data)
    assert "could not be read" in html
    assert "sensitive exception detail" not in html


def test_invalid_cache_encoding_is_unreadable(native_source):
    cfg, _ = native_source
    (cfg.research_hub_dir / "nlm_cache.json").write_bytes(b'\xff')
    _, paper = _collect(native_source)
    assert paper.nlm_source_evidence.reason == "cache_unreadable"


def test_new_details_escape_values_and_offer_no_actions():
    from research_hub.dashboard.source_evidence import SourceEvidence
    from research_hub.dashboard.source_evidence_view import render_source_evidence
    malicious = '<img src=x onerror="alert(1)">'
    paper = PaperRow("s", "title", "", "", "", malicious, zotero_key=malicious, obsidian_path=malicious,
                     nlm_source_evidence=SourceEvidence("recorded", "version_unknown", malicious))
    html = render_source_evidence(malicious, paper)
    assert malicious not in html
    assert "&lt;img" in html
    for forbidden in ("<a ", "<form", "<button", "data-action", "href=", "onclick="):
        assert forbidden not in html
    assert 'lang="zh-Hant"' in html
    assert 'lang="en"' in html


def test_legacy_paper_has_explicit_unknown_values():
    from research_hub.dashboard.source_evidence_view import render_source_evidence
    html = render_source_evidence("", SimpleNamespace())
    assert "No cache observation is available" in html
    assert html.count("Unknown") == 5
    assert "Remote sync: unknown" in html


def test_source_evidence_css_has_readable_wrapping_and_native_controls():
    css = (Path(__file__).parents[1] / "src/research_hub/dashboard/style.css").read_text(encoding="utf-8")
    rules = css.split("/* Read-only provenance")[1].split(".status-badge")[0]
    assert "font-size: 1rem" in rules
    assert "min-height: 44px" in rules
    assert "overflow-wrap: anywhere" in rules
    assert "display: list-item" in rules
    assert "white-space: pre-wrap" in rules


@pytest.mark.parametrize("identity_fields", [
    'doi:\nzotero-key:\n',
    'doi: null\nzotero-key: null\n',
    'doi: ~\nzotero-key: false\n',
    'doi: ["10.1000/example"]\nzotero-key: {value: ABC12345}\n',
    'doi: 1234\nzotero-key: 1234\n',
    'doi: "null"\nzotero-key: "None"\n',
    'doi: "10.1000/example"\ndoi: "10.1000/other"\nzotero-key: ABC12345\nzotero-key: OTHER123\n',
    'doi: "unterminated\nzotero-key: ABC12345\n',
    'doi: |\n  10.1000/example\n  another line\nzotero-key: |\n  ABC12345\n  OTHER123\n',
    'doi: >\n  10.1000/example\n  another line\nzotero-key: >\n  ABC12345\n  OTHER123\n',
    'doi: "10.1000/example\n  continued"\nzotero-key: "ABC12345\n  continued"\n',
    'doi: !!python/object:invalid {}\nzotero-key: !!int "ABC12345"\n',
])
def test_invalid_note_identities_stay_unknown_and_cannot_bind_cached_versions(native_source, identity_fields):
    _, note = native_source
    note.write_text('---\ntitle: "Synthetic"\ntopic_cluster: "evidence"\n' + identity_fields + '---\nManual notes remain.\n', encoding='utf-8')
    data, paper = _collect(native_source, {"evidence": {
        "uploaded_sources": ["zotero-key:", "null", "10.1000/example"],
        "source_versions": {"10.1000/example": {"kind": "text", "sha256": "a" * 64}},
    }})
    assert paper.doi == ""
    assert paper.zotero_key == ""
    assert paper.nlm_source_evidence.reason == "identity_not_linked"
    from research_hub.dashboard.source_evidence_view import render_source_evidence
    html = render_source_evidence("evidence", paper)
    assert html.count("Unknown") == 3
    assert "Historical payload SHA-256" not in html


def test_blank_doi_does_not_consume_following_valid_zotero_key(native_source):
    _, note = native_source
    note.write_text('---\ntitle: Synthetic\ntopic_cluster: evidence\ndoi:\nzotero-key: "ABC12345"\n---\n', encoding='utf-8')
    _, paper = _collect(native_source)
    assert paper.doi == ""
    assert paper.zotero_key == "ABC12345"


def test_source_identities_preserve_quoted_scalar_and_ignore_yaml_comment():
    from research_hub.dashboard.source_evidence import note_source_identities
    assert note_source_identities('doi: "10.1000/example" # explanation\nzotero-key: ABC12345 # local reference\n') == {
        'doi': '10.1000/example', 'zotero-key': 'ABC12345'}
    # Repeated invalid/valid combinations cannot resurrect an ambiguous value.
    assert note_source_identities('doi: null\ndoi: 10.1000/example\ndoi: 10.1000/another\n')['doi'] == ''


@pytest.mark.parametrize("cache", [
    {"uploaded_doi_count": "broken"},
    {"uploaded_sources": ["10.1000/example"], "uploaded_doi_count": "NaN"},
    {"uploaded_doi_count": []},
    {"uploaded_doi_count": -1},
    {"artifacts": {"audio": {"char_count": "broken"}}},
    {"artifacts": {"audio": {"char_count": {}}}},
    {"artifacts": []},
    {"artifacts": {"brief": []}},
    {"artifacts": {"brief": {"titles": 42}}},
    {"artifacts": {"brief": {"titles": [None]}}},
])
def test_malformed_legacy_cache_metadata_cannot_suppress_paper_evidence(native_source, cache):
    cfg, _ = native_source
    artifacts = cfg.research_hub_dir / 'artifacts' / 'evidence'
    artifacts.mkdir(parents=True)
    (artifacts / 'brief-20261023.txt').write_text('Synthetic local brief.\n', encoding='utf-8')
    data, paper = _collect(native_source, {'evidence': cache})
    assert paper.nlm_source_evidence.reason == 'cache_invalid'
    assert data.clusters[0].briefing.full_text == 'Synthetic local brief.'
    html = LibrarySection().render(data)
    assert "local cache format is invalid" in html
    assert "Remote sync: unknown" in html


def test_legacy_numeric_strings_remain_compatible(native_source):
    data, paper = _collect(native_source, {'evidence': {'uploaded_doi_count': '3', 'artifacts': {'audio': {'char_count': '7'}}}})
    assert data.clusters[0].nlm_count == 3
    assert data.clusters[0].nlm_artifacts[0].char_count == 7
    assert paper.nlm_source_evidence.reason == 'identity_not_linked'


def test_invalid_utf8_note_identity_cannot_be_repaired_into_cached_evidence(native_source):
    _, note = native_source
    note.write_bytes(b'---\ntitle: Synthetic\ntopic_cluster: evidence\ndoi: "10.1000/ex\xffample"\nzotero-key: "ABC12345"\n---\nManual notes remain.\n')
    data, paper = _collect(native_source, {'evidence': {
        'uploaded_sources': ['10.1000/example'],
        'source_versions': {'10.1000/example': {'kind': 'text', 'sha256': 'a' * 64}},
    }})
    assert paper.doi == ''
    assert paper.zotero_key == ''
    assert paper.nlm_source_evidence.reason == 'identity_not_linked'
    assert not paper.nlm_source_evidence.payload_sha256
    assert not data.clusters[0].label_counts_available
    assert "Label counts unknown" in LibrarySection().render(data)


def test_new_cluster_field_preserves_existing_positional_argument_order():
    from dataclasses import fields
    assert [field.name for field in fields(ClusterCard)][-3:] == [
        'archived_count', 'archived_papers', 'label_counts_available']


def test_duplicate_json_identity_versions_are_ambiguous_not_last_wins(native_source):
    raw = ('{"evidence":{"uploaded_sources":["10.1000/example"],"source_versions":{'
           '"10.1000/example":{"kind":"text","sha256":"' + 'a' * 64 + '"},'
           '"10.1000/example":{"kind":"text","sha256":"' + 'b' * 64 + '"}}}}')
    data, paper = _collect(native_source, raw=raw)
    assert paper.nlm_source_evidence.reason == 'cache_invalid'
    assert not paper.nlm_source_evidence.payload_sha256
    assert 'Historical payload SHA-256' not in LibrarySection().render(data)
