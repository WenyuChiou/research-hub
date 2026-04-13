import os
import re

from research_hub.clusters import ClusterRegistry
from research_hub.config import get_config as _get_config
from research_hub.topic import read_overview
from research_hub.vault.progress import count_status_by_cluster

# Merge mapping: normalize duplicate/typo Zotero collection names to canonical wiki names
WIKI_MERGE = {
    "Agent-Based Model": "ABM",
    "agent-based model": "ABM",
    "Agent-Based Modeling": "ABM",
    "Soical capital": "Social Capital",
    "Social norm/ Social capital": "Social Capital",
    "Soical Vulnerability": "Social Vulnerability",
    "Study area": "Study Area",
    "study area": "Study Area",
    "Flood insurance": "Insurance & Risk Transfer",
    "Insurance": "Insurance & Risk Transfer",
    "survey": "Survey Methods",
    "survey paper": "Survey Methods",
    "LR": "Literature Review",
    "SM": "Social Media",
    "SEM": "Structural Equation Modeling",
    "Buoyout": "Buyout Programs",
}


def normalize_collections(collections):
    """Apply WIKI_MERGE to normalize collection names, deduplicating results."""
    normalized = []
    seen = set()
    for collection in collections:
        canonical = WIKI_MERGE.get(collection, collection)
        if canonical.lower() not in seen:
            seen.add(canonical.lower())
            normalized.append(canonical)
    return normalized


def _ingested_sort_key(value: str) -> tuple[int, str]:
    """Sort ingest timestamps with blank values last."""

    return (1, value) if value else (0, "")


def _strip_frontmatter_and_h1(markdown: str) -> str:
    if markdown.startswith("---\n"):
        end = markdown.find("\n---\n", 4)
        if end != -1:
            markdown = markdown[end + 5 :]
    markdown = re.sub(r"^#\s+[^\n]+\n+", "", markdown.lstrip(), count=1)
    return markdown.strip()


def main() -> int:
    cfg = _get_config()
    raw_dir = str(cfg.raw)
    hub_dir = str(cfg.hub)
    proj_dir = str(cfg.projects)
    root = str(cfg.root)

    os.makedirs(hub_dir, exist_ok=True)
    os.makedirs(proj_dir, exist_ok=True)

    papers = []
    all_md_files = []
    for dirpath, _, filenames in os.walk(raw_dir):
        for filename in sorted(filenames):
            if filename.endswith(".md"):
                all_md_files.append((dirpath, filename))

    for dirpath, filename in all_md_files:
        path = os.path.join(dirpath, filename)
        with open(path, "r", encoding="utf-8") as fh:
            content = fh.read()
        match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
        if not match:
            continue
        meta = {}
        for line in match.group(1).split("\n"):
            if ":" in line:
                key = line.split(":")[0].strip()
                value = ":".join(line.split(":")[1:]).strip().strip('"')
                meta[key] = value
        collections_match = re.search(r"collections:\s*\[(.*?)\]", match.group(1))
        if collections_match:
            raw_collections = [
                item.strip().strip('"').strip("'")
                for item in collections_match.group(1).split(",")
            ]
            meta["collections"] = normalize_collections(raw_collections)
        tags_match = re.search(r"tags:\s*\[(.*?)\]", match.group(1))
        if tags_match:
            meta["tags"] = [
                item.strip().strip('"').strip("'") for item in tags_match.group(1).split(",")
            ]
        rel_dir = os.path.relpath(dirpath, root).replace("\\", "/")
        if rel_dir == "raw":
            meta["filename"] = filename.replace(".md", "")
        else:
            meta["filename"] = rel_dir + "/" + filename.replace(".md", "")
        meta["title_line"] = meta.get("title", filename.replace(".md", ""))
        papers.append(meta)

    print(f"Parsed {len(papers)} papers")

    topic_map = {
        "Agent-Based-Modeling": {
            "keywords": ["agent-based", "ABM", "DYNAMO", "agent based", "multi-agent"],
            "desc": "Agent-based modeling approaches for simulating human behavior in complex systems.",
        },
        "Flood-Insurance": {
            "keywords": ["flood insurance", "NFIP", "insurance", "premium", "Risk Rating"],
            "desc": "National Flood Insurance Program, premium structures, and insurance market dynamics.",
        },
        "Flood-Risk": {
            "keywords": ["flood risk", "flood inundation", "flood fragility", "coastal flood", "flood model"],
            "desc": "Flood risk assessment, modeling, and management strategies.",
        },
        "LLM-Agents": {
            "keywords": ["LLM", "large language model", "generative agent", "GPT", "AI-driven", "AI agent"],
            "desc": "Large language model applications in agent simulation and decision-making.",
        },
        "Place-Attachment": {
            "keywords": ["place attachment", "community attachment", "neighborhood attachment"],
            "desc": "How emotional bonds to places influence disaster response and recovery decisions.",
        },
        "Social-Vulnerability": {
            "keywords": ["social vulnerability", "racial inequit", "environmental justice", "equity", "socioeconomic"],
            "desc": "Social vulnerability, equity, and environmental justice in disaster contexts.",
        },
        "Managed-Retreat": {
            "keywords": ["managed retreat", "buyout", "relocation", "acquisition"],
            "desc": "Managed retreat programs, voluntary buyouts, and post-disaster relocation.",
        },
        "Disaster-Preparedness": {
            "keywords": ["preparedness", "mitigation", "risk perception", "protective action"],
            "desc": "Household disaster preparedness, risk perception, and protective behavior.",
        },
        "Climate-Adaptation": {
            "keywords": ["climate change", "adaptation", "sea level rise", "resilience"],
            "desc": "Climate change adaptation strategies and resilience building.",
        },
    }

    for topic, info in topic_map.items():
        matched = []
        for paper in papers:
            text = (
                paper.get("title_line", "")
                + " "
                + " ".join(paper.get("tags", []))
                + " "
                + " ".join(paper.get("collections", []))
            ).lower()
            if any(keyword.lower() in text for keyword in info["keywords"]):
                matched.append(paper)

        content = f"""---
type: hub-topic
papers: {len(matched)}
---

# {topic.replace('-', ' ')}

{info['desc']}

## Key Papers ({len(matched)})

"""
        for paper in sorted(matched, key=lambda item: item.get("year", "0"), reverse=True):
            content += f"- [[{paper['filename']}|{paper['title_line'][:80]}]] ({paper.get('year', 'n.d.')})\n"

        content += "\n## Related Topics\n\n"
        other_topics = [item for item in topic_map if item != topic]
        content += " ".join(f"[[{item}]]" for item in other_topics[:5]) + "\n"

        hub_path = os.path.join(hub_dir, f"{topic}.md")
        with open(hub_path, "w", encoding="utf-8") as fh:
            fh.write(content)
        print(f"  Hub: {topic}.md ({len(matched)} papers)")

    clusters = ClusterRegistry(cfg.clusters_file)
    if clusters.list():
        clusters_dir = os.path.join(hub_dir, "clusters")
        os.makedirs(clusters_dir, exist_ok=True)
        for cluster in clusters.list():
            matched = [paper for paper in papers if paper.get("topic_cluster") == cluster.slug]
            overview = read_overview(cfg, cluster.slug)
            overview_block = ""
            if overview:
                cleaned = _strip_frontmatter_and_h1(overview)
                if cleaned:
                    overview_block = cleaned + "\n\n---\n\n"
            content = f"""---
type: hub-cluster
cluster: {cluster.slug}
papers: {len(matched)}
---

# {cluster.name}

First query: {cluster.first_query}

{overview_block}## Papers ({len(matched)})

"""
            for paper in sorted(matched, key=lambda item: item.get("year", "0"), reverse=True):
                content += f"- [[{paper['filename']}|{paper['title_line'][:80]}]] ({paper.get('year', 'n.d.')})\n"
            content += (
                "\n## Reading Queue\n\n"
                "```dataview\n"
                "TABLE year, authors, status, citation-count\n"
                'FROM "raw"\n'
                f'WHERE topic_cluster = "{cluster.slug}" AND status = "unread"\n'
                "SORT year DESC\n"
                "LIMIT 15\n"
                "```\n"
                "\n## Deep-read\n\n"
                "```dataview\n"
                "TABLE year, authors, verified\n"
                'FROM "raw"\n'
                f'WHERE topic_cluster = "{cluster.slug}" AND (status = "deep-read" OR status = "cited")\n'
                "SORT year DESC\n"
                "```\n"
                "\n## All Papers (by year)\n\n"
                "```dataview\n"
                "TABLE year, status, citation-count\n"
                'FROM "raw"\n'
                f'WHERE topic_cluster = "{cluster.slug}"\n'
                "SORT year DESC\n"
                "```\n"
            )
            cluster_path = os.path.join(clusters_dir, f"{cluster.slug}.md")
            with open(cluster_path, "w", encoding="utf-8") as fh:
                fh.write(content)
            print(f"  Cluster: {cluster.slug}.md ({len(matched)} papers)")

    projects = {
        "ABM-Paper": {
            "desc": "Agent-based model for flood insurance decision-making with LLM-powered agents.",
            "status": "In Progress",
            "collections": ["ABM", "Flood-Simulation", "LLM AI agent"],
        },
        "Survey-Paper": {
            "desc": "Survey of computational approaches to flood risk and insurance modeling.",
            "status": "In Progress",
            "collections": ["Survey", "Literature Review", "survey paper"],
        },
        "Governed-Broker-Framework": {
            "desc": "Governed Broker Framework for AI-mediated flood insurance markets.",
            "status": "Planning",
            "collections": ["GBF", "Governed Broker Framework"],
        },
    }

    for proj_name, info in projects.items():
        matched = []
        for paper in papers:
            paper_collections = [item.lower() for item in (paper.get("collections") or [])]
            if any(item.lower() in paper_collections for item in info["collections"]):
                matched.append(paper)

        content = f"""---
type: project
status: {info['status']}
papers: {len(matched)}
---

# {proj_name.replace('-', ' ')}

**Status:** {info['status']}

{info['desc']}

## Source Papers ({len(matched)})

"""
        for paper in sorted(matched, key=lambda item: item.get("year", "0"), reverse=True):
            content += f"- [ ] [[{paper['filename']}|{paper['title_line'][:80]}]] ({paper.get('year', 'n.d.')})\n"

        proj_path = os.path.join(proj_dir, f"{proj_name}.md")
        with open(proj_path, "w", encoding="utf-8") as fh:
            fh.write(content)
        print(f"  Project: {proj_name}.md ({len(matched)} papers)")

    status_counts = count_status_by_cluster(cfg.raw)
    cluster_rows = []
    for cluster in clusters.list():
        matched = [paper for paper in papers if paper.get("topic_cluster") == cluster.slug]
        last_ingest = "?"
        ingested_values = [
            str(paper.get("ingested_at", "")).strip()
            for paper in matched
            if str(paper.get("ingested_at", "")).strip()
        ]
        if ingested_values:
            last_ingest = max(ingested_values, key=_ingested_sort_key)[:10]
        counter = status_counts.get(cluster.slug, {})
        cluster_rows.append(
            {
                "slug": cluster.slug,
                "name": cluster.name,
                "total": sum(counter.values()),
                "unread": counter.get("unread", 0),
                "skim": counter.get("skim", 0),
                "deep": counter.get("deep-read", 0),
                "cited": counter.get("cited", 0),
                "last_ingest": last_ingest,
            }
        )

    cluster_rows.sort(key=lambda row: (-row["unread"], -row["total"], row["slug"]))
    unassigned_count = sum(status_counts.get("__unassigned__", {}).values())

    index_content = f"""---
type: index
total_papers: {len(papers)}
---

# Knowledge Base Index

Total papers: **{len(papers)}**

## Clusters Overview

| Cluster | Total | Unread | Skim | Deep | Cited | Last Ingest |
|---|---:|---:|---:|---:|---:|---|
"""
    for row in cluster_rows:
        index_content += (
            f"| [[clusters/{row['slug']}|{row['name']}]] | {row['total']} | "
            f"{row['unread']} | {row['skim']} | {row['deep']} | {row['cited']} | "
            f"{row['last_ingest']} |\n"
        )

    if unassigned_count:
        index_content += f"\n**Unassigned notes:** {unassigned_count}\n"

    index_content += """

## Research Projects

- ABM Paper ??Agent-based flood insurance model
- Survey Paper ??Computational flood risk survey
- Governed Broker Framework ??AI-mediated insurance markets

## Research Hub

"""
    for topic in sorted(topic_map.keys()):
        index_content += f"- {topic.replace('-', ' ')}\n"

    index_content += """
## Global Unread Queue (top 20)

```dataview
TABLE year, authors, topic_cluster, status
FROM "raw"
WHERE status = "unread"
SORT year DESC
LIMIT 20
```

## All Papers by Year

"""
    by_year = {}
    for paper in papers:
        year = paper.get("year", "Unknown")
        by_year.setdefault(year, []).append(paper)

    for year in sorted(by_year.keys(), reverse=True):
        index_content += f"### {year}\n\n"
        for paper in by_year[year]:
            index_content += f"- {paper['title_line'][:80]} ({paper.get('year', 'n.d.')})\n"
        index_content += "\n"

    index_path = os.path.join(hub_dir, "index.md")
    with open(index_path, "w", encoding="utf-8") as fh:
        fh.write(index_content)
    print("  Index: hub/index.md")
    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
