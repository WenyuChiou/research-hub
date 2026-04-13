"""Bundled example cluster definitions."""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

EXAMPLE_NAMES = ["cs_swe", "bio_protein", "social_climate", "edu_assessment"]


def load_example(name: str) -> dict[str, Any]:
    """Load one bundled example by name."""
    if name not in EXAMPLE_NAMES:
        raise FileNotFoundError(f"unknown example: {name}; valid: {', '.join(EXAMPLE_NAMES)}")
    resource = files("research_hub.examples").joinpath(f"{name}.json")
    return json.loads(resource.read_text(encoding="utf-8"))


def list_examples() -> list[dict[str, Any]]:
    """Return all bundled examples."""
    return [load_example(name) for name in EXAMPLE_NAMES]


def copy_example_as_cluster(cfg, example_name: str, cluster_slug: str | None = None) -> str:
    """Copy a bundled example into the user's clusters registry."""
    from research_hub.clusters import Cluster, ClusterRegistry

    example = load_example(example_name)
    slug = cluster_slug or example["slug"]
    registry = ClusterRegistry(cfg.clusters_file)
    if registry.get(slug) is not None:
        raise ValueError(f"cluster {slug} already exists; pick a different --cluster")

    registry.clusters[slug] = Cluster(
        slug=slug,
        name=example["name"],
        seed_keywords=example["query"].split()[:6],
        first_query=example["query"],
        description=example.get("definition", ""),
        obsidian_subfolder=slug,
    )
    registry.save()
    return slug
