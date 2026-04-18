"""Persona vault factory for v0.34 persona × pipeline test matrix.

Builds a vault state matching one of 4 user personas:

- A: PhD STEM (default)         — Zotero + Obsidian + NLM, 1 cluster + papers
- B: Industry researcher        — NO Zotero, Obsidian + NLM, imported docs
- C: Humanities PhD             — Zotero + Obsidian, 1 cluster + quotes
- H: Internal knowledge mgmt    — NO Zotero, Obsidian + NLM, mixed docs

Used by tests/test_v034_persona_matrix.py to verify research-hub works for
all four user types end-to-end (not just the default).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def _set_root(tmp_path: Path) -> None:
    """Point HubConfig at tmp_path + reset module cache.

    Forces RESEARCH_HUB_CONFIG to a nonexistent path so HubConfig falls back
    to env-var-only mode and doesn't pick up the developer's real config.json
    (which would override RESEARCH_HUB_ROOT and write to the real vault).
    """
    os.environ["RESEARCH_HUB_ROOT"] = str(tmp_path)
    os.environ["RESEARCH_HUB_ALLOW_EXTERNAL_ROOT"] = "1"
    os.environ["RESEARCH_HUB_CONFIG"] = str(tmp_path / "_no_config_.json")
    import research_hub.config as cfg_mod
    cfg_mod._config = None
    cfg_mod._config_path = None


def make_persona_vault(tmp_path: Path, persona: str = "A") -> tuple[Any, dict]:
    """Build a vault state for the requested persona.

    Returns (cfg, info_dict). info_dict has at minimum:
      - persona: the requested persona letter
      - cluster_slug: the primary cluster slug
      - paper_count: how many docs/papers the cluster holds
      - has_zotero: whether this persona has Zotero configured
    """
    if persona not in {"A", "B", "C", "H"}:
        raise ValueError(f"persona={persona!r} unknown. Use A/B/C/H.")

    _set_root(tmp_path)
    import research_hub.config as cfg_mod
    cfg = cfg_mod.HubConfig()

    has_zotero = persona in {"A", "C"}
    cluster_slug = f"persona-{persona.lower()}-test"

    # Cluster registry
    from research_hub.clusters import ClusterRegistry
    registry = ClusterRegistry(cfg.research_hub_dir / "clusters.yaml")
    if registry.get(cluster_slug) is None:
        registry.create(query=cluster_slug, slug=cluster_slug)
        registry.save()

    # Persona-specific seed content
    raw_dir = cfg.raw / cluster_slug
    raw_dir.mkdir(parents=True, exist_ok=True)

    info: dict = {
        "persona": persona,
        "cluster_slug": cluster_slug,
        "has_zotero": has_zotero,
        "raw_dir": raw_dir,
    }

    if persona == "A":
        # PhD STEM: 3 academic papers with full frontmatter
        for i, doi in enumerate(["10.1/foo", "10.1/bar", "10.1/baz"]):
            (raw_dir / f"paper{i}.md").write_text(
                f"---\ntitle: Paper {i}\nauthors: Smith, J\nyear: 2024\n"
                f"doi: {doi}\nsource_kind: paper\ntopic_cluster: {cluster_slug}\n"
                f"labels: [core]\n---\n# Paper {i}\n",
                encoding="utf-8",
            )
        info["paper_count"] = 3

    elif persona == "B":
        # Industry researcher: 3 imported PDFs (Documents, no DOI)
        for i, name in enumerate(["q2-strategy", "competitor-deck", "market-report"]):
            (raw_dir / f"{name}.md").write_text(
                f"---\ntitle: {name.replace('-',' ').title()}\nslug: {name}\n"
                f"source_kind: pdf\ntopic_cluster: {cluster_slug}\n"
                f"raw_path: /tmp/{name}.pdf\nlabels: []\ningestion_source: import-folder\n"
                f"---\n# {name}\n\nImported content preview.\n",
                encoding="utf-8",
            )
        info["paper_count"] = 3

    elif persona == "C":
        # Humanities PhD: 2 papers (URL-based, no DOI) + quotes
        for i, name in enumerate(["foucault-essay", "butler-talk"]):
            (raw_dir / f"{name}.md").write_text(
                f"---\ntitle: {name.replace('-',' ').title()}\nauthors: Author\n"
                f"year: 2020\nurl: https://example.org/{name}\n"
                f"source_kind: paper\ntopic_cluster: {cluster_slug}\nlabels: [seed]\n---\n# {name}\n",
                encoding="utf-8",
            )
        # Quotes
        quotes_dir = cfg.research_hub_dir / "quotes"
        quotes_dir.mkdir(parents=True, exist_ok=True)
        for i in range(5):
            (quotes_dir / f"quote{i}.md").write_text(
                f"---\nslug: foucault-essay\npage: {10+i}\ncluster: {cluster_slug}\n"
                f"---\n> Sample quote text {i} from non-DOI source.\n",
                encoding="utf-8",
            )
        info["paper_count"] = 2
        info["quote_count"] = 5

    elif persona == "H":
        # Internal KM: 4 mixed docs (PDF + MD + URL)
        for i, (kind, name) in enumerate([
            ("pdf", "internal-policy"),
            ("markdown", "team-rituals"),
            ("docx", "vendor-contract"),
            ("url", "competitor-blog-post"),
        ]):
            (raw_dir / f"{name}.md").write_text(
                f"---\ntitle: {name.replace('-',' ').title()}\nslug: {name}\n"
                f"source_kind: {kind}\ntopic_cluster: {cluster_slug}\n"
                f"raw_path: /internal/{name}.{kind}\ningestion_source: import-folder\n"
                f"labels: []\n---\n# {name}\n\nInternal doc content.\n",
                encoding="utf-8",
            )
        info["paper_count"] = 4

    return cfg, info
