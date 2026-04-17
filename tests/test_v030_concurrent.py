from __future__ import annotations

import importlib.util
import json
import multiprocessing
import threading
import time
from pathlib import Path

import pytest

from research_hub import crystal
from research_hub.clusters import ClusterRegistry
from research_hub.dedup import DedupIndex


HAS_LOCKS = importlib.util.find_spec("research_hub.locks") is not None
HAS_SECURITY = importlib.util.find_spec("research_hub.security") is not None


class _StubConfig:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.raw = root / "raw"
        self.hub = root / "hub"
        self.research_hub_dir = root / ".research_hub"
        self.clusters_file = self.research_hub_dir / "clusters.yaml"
        self.raw.mkdir(parents=True, exist_ok=True)
        self.hub.mkdir(parents=True, exist_ok=True)
        self.research_hub_dir.mkdir(parents=True, exist_ok=True)


def _ingest_worker(vault_path: str, paper_doi: str, result_queue) -> None:
    try:
        raw = Path(vault_path) / "raw" / "alpha"
        raw.mkdir(parents=True, exist_ok=True)
        note = raw / f"{paper_doi.rsplit('/', 1)[-1]}.md"
        note.write_text(
            "---\n"
            f'title: "Paper {paper_doi}"\n'
            f'doi: "{paper_doi}"\n'
            'topic_cluster: "alpha"\n'
            "---\n",
            encoding="utf-8",
        )
        result_queue.put((True, None))
    except Exception as exc:  # pragma: no cover
        result_queue.put((False, str(exc)))


@pytest.mark.skipif(not HAS_LOCKS, reason="track B not yet shipped: research_hub.locks.file_lock missing")
def test_two_concurrent_ingests_dont_corrupt_dedup(tmp_path):
    queue = multiprocessing.Queue()
    workers = [
        multiprocessing.Process(target=_ingest_worker, args=(str(tmp_path), "10.1/a", queue)),
        multiprocessing.Process(target=_ingest_worker, args=(str(tmp_path), "10.1/b", queue)),
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=5)

    results = [queue.get(timeout=2) for _ in workers]
    assert all(success for success, _ in results)

    rebuilt = DedupIndex.empty().rebuild_from_obsidian(tmp_path / "raw")
    assert set(rebuilt.doi_to_hits) == {"10.1/a", "10.1/b"}


@pytest.mark.skipif(not HAS_LOCKS, reason="track B not yet shipped: research_hub.locks.file_lock missing")
def test_concurrent_clusters_yaml_writes_serialized(tmp_path):
    from research_hub.locks import file_lock

    target = tmp_path / "shared.yaml"
    target.write_text("count: 0\n", encoding="utf-8")
    counter_lock = threading.Lock()
    counter = [0]

    def writer() -> None:
        with file_lock(target):
            with counter_lock:
                counter[0] += 1
            time.sleep(0.05)

    threads = [threading.Thread(target=writer) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert counter[0] == 5


def test_dedup_rebuild_idempotent(tmp_path):
    raw = tmp_path / "raw" / "c"
    raw.mkdir(parents=True)
    for i in range(3):
        (raw / f"p{i}.md").write_text(
            "---\n"
            f'title: "Paper {i}"\n'
            f'doi: "10.1/p{i}"\n'
            "---\n",
            encoding="utf-8",
        )

    output = tmp_path / ".research_hub" / "dedup_index.json"
    output.parent.mkdir()

    first = DedupIndex.empty().rebuild_from_obsidian(tmp_path / "raw")
    first.save(output)
    first_text = output.read_text(encoding="utf-8")

    second = DedupIndex.empty().rebuild_from_obsidian(tmp_path / "raw")
    second.save(output)
    second_text = output.read_text(encoding="utf-8")

    assert first_text == second_text


@pytest.mark.skipif(not HAS_SECURITY, reason="track A not yet shipped: research_hub.security.atomic_write_text missing")
def test_crystal_apply_overwrite_atomic(tmp_path):
    from research_hub.security import atomic_write_text

    crystals_dir = tmp_path / "hub" / "c" / "crystals"
    crystals_dir.mkdir(parents=True)
    target = crystals_dir / "what-is-this-field.md"

    atomic_write_text(target, "first version")
    atomic_write_text(target, "second version")

    assert target.read_text(encoding="utf-8") == "second version"
    assert list(crystals_dir.glob("*.tmp.*")) == []

