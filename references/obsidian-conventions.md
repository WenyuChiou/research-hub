---
title: Obsidian Conventions & Templates
description: Markdown best practices, YAML frontmatter template, hub architecture, and graph color config
---

# Obsidian Conventions & Templates

## Obsidian Markdown Best Practices

These conventions ensure clean rendering in Obsidian and compatibility with community plugins:

1. **YAML Frontmatter**: Enclosed in `---`. String values in double quotes. Arrays as JSON `["a", "b"]`. No trailing whitespace. No duplicate keys.
2. **One H1 per file**: The paper title. All other sections use `##` or `###`.
3. **Wikilinks**: `[[Page-Name]]` for links. `[[Page-Name|Display Text]]` for aliases. Use Title-Case-With-Hyphens for page names.
4. **Tags in frontmatter**: Plain strings without `#` prefix. In body text, use `#tag-name` format.
5. **Lists**: Use `-` (not `*` or `+`). Blank line before and after list blocks.
6. **Blank lines**: One blank line before and after headings, code blocks, and block quotes.
7. **No HTML**: Pure Markdown only. Obsidian renders most Markdown natively.
8. **No hard line wrapping**: Let Obsidian handle soft wrapping. Do not insert line breaks at 80 characters.
9. **Callouts**: Use `> [!note]`, `> [!warning]`, `> [!tip]` for callout blocks when needed.
10. **Embeds**: Use `![[Page-Name]]` to embed another note's content. Use `![[Page-Name#Section]]` for section embeds.
11. **Footnotes**: Use `[^1]` inline and `[^1]: footnote text` at the bottom for references.
12. **File naming**: Lowercase with hyphens. No spaces, no special characters. Example: `inducing-state-anxiety-in-llm-agents.md`.

## Three-Layer Hub Architecture

| Layer | Location | Purpose | Example |
|-------|----------|---------|---------|
| Layer 1: Theories | `hub/` (theory pages) | High-level theoretical frameworks | Bounded-Rationality, Protection-Motivation-Theory |
| Layer 2: Topics | `hub/` (topic pages) | Mid-level topic aggregation | Flood-Insurance, LLM-Agents, Managed-Retreat |
| Layer 3: Papers | `raw/` | Individual paper notes with YAML | Each .md file is one paper |

Papers (Layer 3) link upward to topics and theories (Layers 1-2) via `[[wiki links]]`. Topics link to related theories. This creates a navigable, hierarchical knowledge graph in Obsidian.

## Obsidian Graph Color Configuration

Configured in `.obsidian/graph.json` using tag-based queries:
- `tag:#research/flood-abm` ??Blue
- `tag:#research/llm-agent` ??Green
- `tag:#research/social-behavior` ??Orange
- `tag:#research/methodology` ??Purple
- `path:hub/` ??Red (hub pages)
- `path:projects/` ??Yellow (project pages)

If colors do not update after `categorize_graph.py`, restart Obsidian.

## YAML Frontmatter Template

Every paper .md file in `raw/` must have this YAML frontmatter format:

```yaml
---
title: "Paper Title"
authors: "Author1; Author2"
year: 2025
journal: "Journal Name"
doi: "10.xxxx/yyyy"
zotero-key: "XXXXXXXX"
collections: ["ABM", "LLM AI agent"]
tags: ["tag1", "tag2"]
category: "flood-abm"
method-type: "traditional-abm"
sub-category: "Flood-ABM"
status: "unread"
thesis-chapter: ""
research-questions: []
citation-count: 0
related-papers: []
---
```

### Field Descriptions

- **title**: Full paper title in double quotes.
- **authors**: Semicolon-separated author list.
- **year**: Publication year (integer).
- **journal**: Journal or conference name.
- **doi**: Digital Object Identifier (if available).
- **zotero-key**: The Zotero item key returned after saving. Leave empty if not yet saved.
- **collections**: JSON array of Zotero collection names.
- **tags**: JSON array of descriptive tags.
- **category**: One of `flood-abm`, `llm-agent`, `social-behavior`, `methodology`, `general-reference`.
- **method-type**: One of `survey`, `traditional-abm`, or `llm-agent`.
- **sub-category**: The sub-category name from the classification (e.g., `"Risk-Perception"`, `"Flood-ABM"`, `"Consumer-Simulation"`).
- **status**: Reading status. One of `unread`, `skimming`, `deep-read`, `cited`. Default: `unread`.
- **thesis-chapter**: Which thesis chapter this paper relates to (e.g., `"Chapter 3: Flood Insurance ABM"`). Leave empty until assigned.
- **research-questions**: JSON array of research question IDs this paper addresses (e.g., `["RQ1", "RQ2"]`). Leave empty until assigned.
- **citation-count**: Number of citations from Semantic Scholar. Auto-populated during save. Integer, default 0.
- **related-papers**: JSON array of related paper slugs found via citation graph exploration. Auto-populated during Step 7.
