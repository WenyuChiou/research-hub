from __future__ import annotations

from tests.stress._helpers import build_synthetic_cluster, make_stress_cfg


def test_set_labels_500_papers_no_corruption(tmp_path):
    cfg = make_stress_cfg(tmp_path)
    build_synthetic_cluster(cfg, "stress", 500)

    from research_hub.paper import read_labels, set_labels

    for i in range(500):
        slug = f"stress-stress-{i:04d}"
        set_labels(cfg, slug, labels=["seed", f"custom-{i}"], fit_score=5, fit_reason="stress test")

    for i in range(500):
        slug = f"stress-stress-{i:04d}"
        state = read_labels(cfg, slug)
        assert state is not None
        assert "seed" in state.labels
        assert f"custom-{i}" in state.labels
        text = state.path.read_text(encoding="utf-8")
        assert text.startswith("---")
        assert "\n---\n" in text


def test_rewrite_preserves_body_content(tmp_path):
    cfg = make_stress_cfg(tmp_path)
    build_synthetic_cluster(cfg, "stress", 100)

    from research_hub.paper import set_labels

    for i in range(100):
        slug = f"stress-stress-{i:04d}"
        set_labels(cfg, slug, labels=["core"])
        text = (cfg.raw / "stress" / f"{slug}.md").read_text(encoding="utf-8")
        assert "## Abstract" in text
        assert "Synthetic abstract for stress testing." in text
