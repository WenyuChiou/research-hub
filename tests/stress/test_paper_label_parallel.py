from __future__ import annotations

import threading

from tests.stress._helpers import build_synthetic_cluster, make_stress_cfg


def test_set_labels_parallel_200_papers(tmp_path):
    cfg = make_stress_cfg(tmp_path)
    build_synthetic_cluster(cfg, "stress", 200)

    from research_hub.paper import read_labels, set_labels

    errors = []

    def label_one(i: int) -> None:
        try:
            set_labels(cfg, f"stress-stress-{i:04d}", add=["processed"])
        except Exception as exc:  # pragma: no cover - failure path asserted below
            errors.append(exc)

    threads = [threading.Thread(target=label_one, args=(i,)) for i in range(200)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors, f"parallel errors: {errors[:3]}"
    for i in range(200):
        state = read_labels(cfg, f"stress-stress-{i:04d}")
        assert state is not None
        assert "processed" in state.labels
