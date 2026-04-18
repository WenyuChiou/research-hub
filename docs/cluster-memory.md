# Cluster Memory

## Overview

Cluster memory is a structured registry stored at `hub/<cluster-slug>/memory.json`.

It captures three record types at the cluster level:

- `entities`: named organizations, datasets, models, benchmarks, people, concepts, venues, or other important nouns.
- `claims`: concrete findings or assertions with confidence and supporting paper slugs.
- `methods`: technique families and named methods extracted from the cluster's paper set.

This release is architecture-only. It creates the storage seam and extraction workflow without changing the CLI, MCP server, or crystal generation flow.

## Why It Exists

Before v0.36, cluster-level knowledge lived in two places:

- raw paper notes in `raw/<cluster>/`
- crystal prose in `hub/<cluster>/crystals/`

Crystals already included evidence mappings, but those mappings were free-text and embedded inside markdown. That made them useful to read but awkward to query, deduplicate, or reuse.

Cluster memory promotes the structured parts into first-class records:

- claims become typed objects with stable slugs and confidence
- entities become reusable canonical references across claims
- methods get their own registry instead of being buried in prose

## How It Differs From Crystals

Crystals and memory serve different jobs.

Crystals:

- are AI-written prose answers to canonical questions
- optimize for synthesis and readability
- live as markdown files under `hub/<cluster>/crystals/`
- include evidence as lightweight embedded tables

Memory:

- is structured JSON for downstream use
- optimizes for stable records and machine-friendly lookup
- lives as `hub/<cluster>/memory.json`
- stores entities, claims, and methods as explicit objects

The intended relationship is:

- crystals explain a cluster
- memory indexes what the cluster contains

## Storage Location

The registry lives at:

```text
hub/<cluster-slug>/memory.json
```

The path is resolved with `safe_join(...)`, and writes go through `atomic_write_text(...)` to preserve the same safety guarantees used elsewhere in the codebase.

## Schema

Top-level document:

```json
{
  "cluster_slug": "alignment",
  "entities": [],
  "claims": [],
  "methods": [],
  "based_on_papers": ["paper-a", "paper-b"],
  "based_on_paper_count": 2,
  "last_generated": "2026-04-18T12:00:00Z",
  "generator": "unknown"
}
```

### Entity

```json
{
  "slug": "openai",
  "name": "OpenAI",
  "type": "org",
  "papers": ["paper-a"],
  "aliases": ["Open AI"],
  "notes": ""
}
```

Fields:

- `slug`: lowercase kebab-case unique within the cluster
- `name`: display name
- `type`: encouraged vocabulary, but open-ended
- `papers`: cluster paper slugs that mention the entity
- `aliases`: alternative spellings or names
- `notes`: optional free-text annotation

Suggested entity types:

- `org`
- `dataset`
- `model`
- `benchmark`
- `method`
- `person`
- `concept`
- `venue`

### Claim

```json
{
  "slug": "rlhf-improves-instruction-following",
  "text": "RLHF improves instruction-following over SFT alone.",
  "confidence": "high",
  "papers": ["paper-a"],
  "related_entities": ["openai"]
}
```

Fields:

- `slug`: lowercase kebab-case unique within the cluster
- `text`: the claim sentence
- `confidence`: `high`, `medium`, or `low`
- `papers`: supporting paper slugs
- `related_entities`: entity slugs already present in the same memory file

Claims without valid supporting papers are dropped during apply.

### Method

```json
{
  "slug": "rlhf",
  "name": "Reinforcement Learning from Human Feedback",
  "family": "rl",
  "papers": ["paper-a"],
  "description": "Train a reward model on preferences and optimize policy against it."
}
```

Fields:

- `slug`: lowercase kebab-case unique within the cluster
- `name`: display name
- `family`: encouraged vocabulary, but open-ended
- `papers`: cluster paper slugs using the method
- `description`: optional short explanation

Suggested method families:

- `supervised`
- `self-supervised`
- `rl`
- `finetune`
- `prompt`
- `search`
- `graph`
- `statistical`
- `geometric`
- `symbolic`
- `hybrid`
- `other`

## Emit / Apply Pattern

Memory generation follows the same two-step pattern used by crystals.

### Emit

`emit_memory_prompt(cfg, cluster_slug)` builds a prompt that includes:

- cluster identity
- cluster definition from `hub/<cluster>/00_overview.md` when present
- the full cluster paper roster via crystal helpers
- a JSON schema for the expected response

This keeps extraction batch-oriented and explicit. The model receives the cluster context in one prompt and returns one JSON object.

### Apply

`apply_memory(cfg, cluster_slug, scored)` validates and writes the AI response.

It performs the following normalization:

- invalid or duplicate slugs are rejected per record type
- paper slugs are filtered to the cluster paper set
- unsupported claims are skipped
- invalid confidence values fall back to `medium`
- related entities are kept only if the entity slug exists in the same payload

The final registry is written once per cluster, not per paper.

## Reused Crystal Helpers

This module intentionally reuses the existing crystal helper seam instead of copying logic.

Imported helpers:

- `_read_cluster_papers`
- `_read_cluster_definition`
- `_strip_frontmatter`
- `_parse_frontmatter`

That keeps cluster memory aligned with the same paper roster and definition parsing used by crystals.

## Extending Vocabularies

Entity types and method families are open vocabularies.

If you need a new type or family:

1. add the string to the suggested tuple if you want it documented in prompts
2. continue accepting arbitrary strings in applied payloads

No schema migration is required because the stored format is already permissive.

## Non-Goals In v0.36

This release does not add:

- new CLI subcommands beyond the planned memory emit/apply/list seam
- MCP write APIs
- per-paper extraction
- crystal changes
- changes to crystal import sites

The purpose of v0.36 is to establish the structured memory layer cleanly so later releases can integrate it into workflows and tools.
