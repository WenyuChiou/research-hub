from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace

from scripts import backfill_zotero as bz


class NotFoundError(Exception):
    status_code = 404


class FakeZotero:
    def __init__(self, *, items_by_key=None, search_hits=None):
        self.items_by_key = items_by_key or {}
        self.search_hits = search_hits or {}
        self.updated: list[dict] = []
        self.created: list[dict] = []

    def item(self, key):
        payload = self.items_by_key.get(key)
        if isinstance(payload, Exception):
            raise payload
        if payload is None:
            raise NotFoundError(f"404 item not found: {key}")
        return payload

    def items(self, q=None, limit=10):
        del limit
        return list(self.search_hits.get(q, []))

    def update_item(self, data):
        copied = json.loads(json.dumps(data))
        self.updated.append(copied)
        key = copied.get("key", "")
        if key and key in self.items_by_key and isinstance(self.items_by_key[key], dict):
            self.items_by_key[key]["data"] = copied
        return {"successful": {"0": {"key": key}}}

    def item_template(self, item_type):
        return {"itemType": item_type}

    def create_items(self, items):
        copied = json.loads(json.dumps(items))
        self.created.extend(copied)
        return {
            "successful": {
                str(idx): {"key": f"NEW{idx + 1}"}
                for idx, _item in enumerate(copied)
            }
        }


def _seed_vault(tmp_path: Path, *, slug: str = "survey", cluster_coll: str = "CLUSTER1") -> Path:
    vault = tmp_path / "vault"
    (vault / "raw" / slug).mkdir(parents=True, exist_ok=True)
    research_hub_dir = vault / ".research_hub"
    research_hub_dir.mkdir(parents=True, exist_ok=True)
    (research_hub_dir / "clusters.yaml").write_text(
        json.dumps(
            {
                "clusters": {
                    slug: {
                        "name": slug.title(),
                        "zotero_collection_key": cluster_coll,
                        "obsidian_subfolder": slug,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return vault


def _write_note(vault: Path, slug: str, name: str, frontmatter: str) -> Path:
    path = vault / "raw" / slug / name
    path.write_text(f"---\n{frontmatter.rstrip()}\n---\n\n# Body\n", encoding="utf-8")
    return path


def _patch_zot(monkeypatch, zot: FakeZotero) -> None:
    monkeypatch.setattr(bz, "ZoteroDualClient", lambda: SimpleNamespace(web=zot))


def _patch_pipeline(monkeypatch, helper=None, batch_size: int = 50) -> None:
    if helper is None:
        helper = lambda *args, **kwargs: ([], [], [])
    monkeypatch.setattr(bz, "resolve_pipeline_api", lambda: (helper, batch_size))


def _plan_files(vault: Path, slug: str) -> list[Path]:
    plan_dir = vault / ".research_hub" / "backfill" / slug
    return [
        plan_dir / "case_A_missing.json",
        plan_dir / "case_B_skip.json",
        plan_dir / "case_C_rebind.json",
        plan_dir / "case_D_recreate.json",
    ]


def test_classify_case_B_already_in_collection(tmp_path):
    vault = _seed_vault(tmp_path)
    note = _write_note(vault, "survey", "paper.md", 'title: "Paper"\ndoi: "10.1/a"\nzotero-key: "K1"')
    zot = FakeZotero(items_by_key={"K1": {"key": "K1", "data": {"collections": ["CLUSTER1"]}}})

    entry, used_get = bz.classify_note(
        zot,
        "survey",
        "CLUSTER1",
        note,
        bz.read_note_frontmatter(note),
    )

    assert used_get is True
    assert entry.case == "B"


def test_classify_case_C_item_exists_other_collection(tmp_path):
    vault = _seed_vault(tmp_path)
    note = _write_note(vault, "survey", "paper.md", 'title: "Paper"\ndoi: "10.1/a"\nzotero-key: "K2"')
    zot = FakeZotero(items_by_key={"K2": {"key": "K2", "data": {"collections": ["OTHER"]}}})

    entry, _ = bz.classify_note(zot, "survey", "CLUSTER1", note, bz.read_note_frontmatter(note))

    assert entry.case == "C"
    assert entry.target_zotero_key == "K2"


def test_classify_case_D_item_404(tmp_path):
    vault = _seed_vault(tmp_path)
    note = _write_note(vault, "survey", "paper.md", 'title: "Paper"\ndoi: "10.1/a"\nzotero-key: "K3"')
    zot = FakeZotero(items_by_key={"K3": NotFoundError("404 gone")})

    entry, _ = bz.classify_note(zot, "survey", "CLUSTER1", note, bz.read_note_frontmatter(note))

    assert entry.case == "D"


def test_classify_case_A_no_zotero_key(tmp_path):
    vault = _seed_vault(tmp_path)
    note = _write_note(vault, "survey", "paper.md", 'title: "Paper"\ndoi: "10.1/a"')
    zot = FakeZotero()

    entry, used_get = bz.classify_note(zot, "survey", "CLUSTER1", note, bz.read_note_frontmatter(note))

    assert used_get is False
    assert entry.case == "A"


def test_classify_doi_dedup_downgrades_A_to_C(tmp_path):
    vault = _seed_vault(tmp_path)
    note = _write_note(vault, "survey", "paper.md", 'title: "Paper"\ndoi: "10.1/a"')
    zot = FakeZotero(
        search_hits={
            "10.1/a": [
                {"key": "EXIST1", "data": {"key": "EXIST1", "DOI": "10.1/a"}},
            ]
        }
    )

    entry, _ = bz.classify_note(zot, "survey", "CLUSTER1", note, bz.read_note_frontmatter(note))

    assert entry.case == "C"
    assert entry.target_zotero_key == "EXIST1"


def test_dry_run_writes_plan_files_no_zotero_writes(tmp_path, monkeypatch):
    vault = _seed_vault(tmp_path)
    _write_note(vault, "survey", "missing.md", 'title: "Missing"\ndoi: "10.1/a"')
    _write_note(vault, "survey", "bound.md", 'title: "Bound"\ndoi: "10.1/b"\nzotero-key: "K1"')
    zot = FakeZotero(items_by_key={"K1": {"key": "K1", "data": {"collections": ["CLUSTER1"]}}})
    _patch_zot(monkeypatch, zot)
    _patch_pipeline(monkeypatch)

    assert bz.main(["--vault", str(vault), "--cluster", "survey", "--dry-run"]) == 0

    for path in _plan_files(vault, "survey"):
        assert path.exists(), path
    assert zot.updated == []
    assert zot.created == []


def test_apply_case_C_calls_update_item_with_collections_appended(tmp_path, monkeypatch):
    vault = _seed_vault(tmp_path)
    _write_note(vault, "survey", "paper.md", 'title: "Paper"\ndoi: "10.1/a"\nzotero-key: "K2"')
    zot = FakeZotero(items_by_key={"K2": {"key": "K2", "data": {"key": "K2", "collections": ["OTHER"]}}})
    _patch_zot(monkeypatch, zot)
    _patch_pipeline(monkeypatch)
    monkeypatch.setattr(bz.time, "sleep", lambda seconds: None)

    assert bz.main(["--vault", str(vault), "--cluster", "survey", "--apply"]) == 0

    assert len(zot.updated) == 1
    assert set(zot.updated[0]["collections"]) == {"OTHER", "CLUSTER1"}
    manifest_lines = (vault / ".research_hub" / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
    assert any(json.loads(line)["action"] == "backfill_C" for line in manifest_lines)


def test_apply_case_D_calls_write_papers_to_zotero_and_updates_md(tmp_path, monkeypatch):
    vault = _seed_vault(tmp_path)
    note = _write_note(
        vault,
        "survey",
        "paper.md",
        'title: "Paper"\nauthors: "Jane Doe"\nyear: "2024"\ndoi: "10.1/a"\nzotero-key: "K3"',
    )
    zot = FakeZotero(items_by_key={"K3": NotFoundError("404 gone")})
    _patch_zot(monkeypatch, zot)
    calls: list[list[dict]] = []

    def fake_write(_zot, papers, *_args, **_kwargs):
        calls.append(json.loads(json.dumps(papers)))
        papers[0]["zotero_key"] = "NEW1"
        return ([{"title": papers[0]["title"], "status": "CREATED", "key": "NEW1"}], [], [])

    _patch_pipeline(monkeypatch, helper=fake_write)
    monkeypatch.setattr(bz.time, "sleep", lambda seconds: None)

    assert bz.main(["--vault", str(vault), "--cluster", "survey", "--apply"]) == 0

    assert len(calls) == 1
    assert "zotero-key: \"NEW1\"" in note.read_text(encoding="utf-8")
    manifest_lines = (vault / ".research_hub" / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
    assert any(json.loads(line)["action"] == "backfill_D" for line in manifest_lines)


def test_rate_limit_enforced(tmp_path, monkeypatch):
    vault = _seed_vault(tmp_path)
    items = {}
    for idx in range(5):
        key = f"K{idx}"
        items[key] = {"key": key, "data": {"key": key, "collections": ["OTHER"]}}
        _write_note(
            vault,
            "survey",
            f"paper-{idx}.md",
            f'title: "Paper {idx}"\ndoi: "10.1/{idx}"\nzotero-key: "{key}"',
        )
    zot = FakeZotero(items_by_key=items)
    _patch_zot(monkeypatch, zot)
    _patch_pipeline(monkeypatch)

    start = time.monotonic()
    assert bz.main(
        [
            "--vault",
            str(vault),
            "--cluster",
            "survey",
            "--apply",
            "--rate-limit",
            "2",
        ]
    ) == 0
    elapsed = time.monotonic() - start

    assert len(zot.updated) == 5
    assert elapsed >= 2.0


def test_idempotent_skips_already_applied(tmp_path, monkeypatch):
    vault = _seed_vault(tmp_path)
    _write_note(vault, "survey", "paper.md", 'title: "Paper"\ndoi: "10.1/a"\nzotero-key: "K2"')
    zot = FakeZotero(items_by_key={"K2": {"key": "K2", "data": {"key": "K2", "collections": ["OTHER"]}}})
    _patch_zot(monkeypatch, zot)
    _patch_pipeline(monkeypatch)
    monkeypatch.setattr(bz.time, "sleep", lambda seconds: None)

    assert bz.main(["--vault", str(vault), "--cluster", "survey", "--apply"]) == 0
    assert bz.main(["--vault", str(vault), "--cluster", "survey", "--apply"]) == 0

    assert len(zot.updated) == 1
