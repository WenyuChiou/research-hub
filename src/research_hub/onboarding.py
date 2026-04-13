"""Field-aware onboarding wizard."""

from __future__ import annotations

from dataclasses import dataclass

from research_hub.search.fallback import FIELD_PRESETS


@dataclass
class WizardResult:
    cluster_slug: str
    cluster_name: str
    field: str
    query: str
    definition: str
    candidate_count: int
    next_steps: list[str]


def _prompt(label: str, default: str = "", required: bool = True) -> str:
    """Prompt on stdin and fall back to a default when blank."""
    suffix = f" [{default}]" if default else ""
    while True:
        value = input(f"{label}{suffix}: ").strip()
        if value:
            return value
        if default:
            return default
        if not required:
            return ""
        print("(required)")


def _print_field_table() -> None:
    print()
    print("Available fields:")
    for slug, backends in sorted(FIELD_PRESETS.items()):
        preview = ", ".join(backends[:3])
        suffix = "..." if len(backends) > 3 else ""
        print(f"  {slug:10s} {len(backends)} backends - {preview}{suffix}")
    print()


def _validate_field(field: str | None) -> str:
    if field is None:
        raise ValueError("field is required")
    if field not in FIELD_PRESETS:
        valid = ", ".join(sorted(FIELD_PRESETS.keys()))
        raise ValueError(f"unknown field {field!r}; valid: {valid}")
    return field


def run_field_wizard(
    cfg,
    *,
    field: str | None = None,
    cluster_slug: str | None = None,
    cluster_name: str | None = None,
    query: str | None = None,
    definition: str | None = None,
    non_interactive: bool = False,
) -> WizardResult:
    """Create a first cluster and run discover_new with a field preset."""
    from research_hub.clusters import Cluster, ClusterRegistry, slugify
    from research_hub.discover import discover_new

    if non_interactive:
        if not all([field, cluster_slug, cluster_name, query]):
            raise ValueError(
                "non-interactive mode requires --field, --cluster, --name, --query"
            )
        field = _validate_field(field)
    else:
        if field is None:
            _print_field_table()
            field = _prompt("Pick a field (cs, bio, med, social, ...)", default="general")
        field = _validate_field(field)
        if cluster_name is None:
            cluster_name = _prompt("Cluster display name", default=f"{field.upper()} cluster")
        if cluster_slug is None:
            cluster_slug = _prompt("Cluster slug", default=slugify(cluster_name))
        if query is None:
            query = _prompt("Search query")
        if definition is None:
            print("(definition is optional but improves fit-check accuracy)")
            definition = _prompt("One-paragraph cluster definition", default="", required=False)

    registry = ClusterRegistry(cfg.clusters_file)
    if registry.get(cluster_slug) is None:
        registry.clusters[cluster_slug] = Cluster(
            slug=cluster_slug,
            name=cluster_name,
            seed_keywords=query.split()[:6],
            first_query=query,
            description=definition or "",
            obsidian_subfolder=cluster_slug,
        )
        registry.save()

    state, _prompt_text = discover_new(
        cfg,
        cluster_slug,
        query,
        field=field,
        definition=definition or None,
    )

    next_steps = [
        f"1. Score the fit-check prompt at <vault>/.research_hub/discover/{cluster_slug}/prompt.md",
        "2. Save scored output to scored.json",
        f"3. Run: research-hub discover continue --cluster {cluster_slug} --scored scored.json --auto-threshold",
        f"4. Run: research-hub ingest --cluster {cluster_slug} --fit-check",
        f"5. Run: research-hub topic scaffold --cluster {cluster_slug}",
    ]

    return WizardResult(
        cluster_slug=cluster_slug,
        cluster_name=cluster_name,
        field=field,
        query=query,
        definition=definition or "",
        candidate_count=state.candidate_count,
        next_steps=next_steps,
    )
