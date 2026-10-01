# papers_input.json schema

`research-hub run` and `research-hub ingest` read `<vault>/papers_input.json`
by default. Pass `--input PATH` to ingest a separate host-produced handoff
without copying it over the shared default. An explicit missing file is an
error and never falls back to the default.
If you have a DOI, `research-hub add <doi>` is usually easier, but manual batch
files should follow this schema.

## Location

`<vault>/papers_input.json`

The vault root is whatever `research-hub doctor` reports for `vault:`.

## Shape

The file may be a JSON array of paper objects or an object with a `papers`
array, such as `{"papers": [...]}`. UTF-8 files with a leading BOM are accepted.
`ResearchEvidencePacket` is a separate claim/evidence contract; map its
bibliographic records into this schema rather than passing the packet itself.

## Field reference

| Field | Required | Type | Example | Used by | Auto-generated |
|---|---|---|---|---|---|
| `title` | Yes | string | `"Escalation Risks from Language Models..."` | Validation, Zotero, note title | No |
| `doi` | Yes | string | `"10.1145/3630106.3658942"` | Dedup, Zotero, note frontmatter | No |
| `authors` | Yes | array of strings or creator dicts | `[{"creatorType":"author","firstName":"Juan","lastName":"Rivera"}]` | Zotero creators, slug generation | No |
| `year` | Yes | int or string | `2024` | Zotero date, slug generation, note frontmatter | No |
| `abstract` | Full ingest | string | `"We evaluate..."` | Zotero abstract, note abstract | No |
| `journal` | Full ingest | string | `"FAccT 2024"` | Zotero publication title, note citation | No |
| `summary` | Full ingest | string | `"The paper benchmarks..."` | Obsidian `## Summary` | No |
| `key_findings` | Full ingest | array of strings | `["Models escalated more than humans."]` | Obsidian `## Key Findings` | No |
| `methodology` | Full ingest | string | `"Scenario-based wargame benchmark."` | Obsidian `## Methodology` | No |
| `relevance` | Full ingest | string | `"Useful evidence for agent risk work."` | Obsidian `## Relevance` | No |
| `slug` | Optional | string | `"rivera2024-escalation-risks-from-language-models"` | Obsidian filename | Yes |
| `sub_category` | Optional | string | `"ai-agent-geopolitics"` | Obsidian folder routing | Yes |
| `url` | Optional | string | `"https://doi.org/10.1145/3630106.3658942"` | Zotero URL | No |
| `tags` | Optional | array of strings | `["llm-agent", "geopolitics"]` | Zotero tags, note tags | No |
| `volume` | Optional | string | `"12"` | Citation metadata | No |
| `issue` | Optional | string | `"3"` | Citation metadata | No |
| `pages` | Optional | string | `"836-898"` | Citation metadata | No |
| `pdf_url` | Optional | string | `"https://arxiv.org/pdf/2502.10978.pdf"` | Upstream tooling | No |
| `query` / `search_query` | Optional | string | `"llm diplomacy escalation"` | Cluster query tracking | No |
| `provenance` | Optional | object | `{"producer":"host-native","research":{"queries":["round one"]}}` | Retained research/process metadata | No |
| `source_records` | Optional | array of objects | `[{"source_id":"S1","url":"https://example.test/article","locator":"p. 4"}]` | Retained source observations | No |

## Authors

`authors` may be either plain strings or Zotero creator dictionaries.

String form:

```json
"authors": ["Wen-Yu Chang", "Ethan Yang"]
```

Creator-dict form:

```json
"authors": [
  {"creatorType": "author", "firstName": "Wen-Yu", "lastName": "Chang"},
  {"creatorType": "author", "firstName": "Ethan", "lastName": "Yang"}
]
```

If you use creator dicts, `creatorType` is required.

## Minimal example

This is enough for `research-hub ingest --dry-run` to validate and auto-fill
`slug` and `sub_category`. The pipeline will warn that the note and Zotero body
fields are still missing.

```json
[
  {
    "title": "A Minimal Paper",
    "doi": "10.1000/minimal",
    "authors": ["Jane Doe"],
    "year": 2024
  }
]
```

## Complete example

```json
[
  {
    "title": "Escalation Risks from Language Models in Military and Diplomatic Decision-Making",
    "doi": "10.1145/3630106.3658942",
    "authors": [
      {"creatorType": "author", "firstName": "Juan-Pablo", "lastName": "Rivera"},
      {"creatorType": "author", "firstName": "Gabriel", "lastName": "Mukobi"}
    ],
    "year": 2024,
    "journal": "Proceedings of the 2024 ACM Conference on Fairness, Accountability, and Transparency",
    "volume": "",
    "issue": "",
    "pages": "836-898",
    "abstract": "The paper evaluates LLM behaviour in simulated decision scenarios.",
    "url": "https://doi.org/10.1145/3630106.3658942",
    "tags": ["llm-agent", "geopolitics", "deterrence"],
    "slug": "rivera2024-escalation-risks-from-language-models",
    "sub_category": "ai-agent-geopolitics",
    "summary": "Authors test five LLMs in eight wargame scenarios.",
    "key_findings": [
      "Models escalated more than human experts.",
      "GPT-3.5 was the most aggressive."
    ],
    "methodology": "Wargame benchmark.",
    "relevance": "Direct evidence that LLMs can introduce escalation bias in policy support workflows."
  }
]
```

## Native research handoff and replay

Capable hosts can do multi-round native search, browse sources, follow citation
chains, verify evidence, and reason before producing this bibliographic input.
Research Hub remains the deterministic ingestion/storage seam. Its scholarly
search commands are optional adapters; no second research agent or dedicated
deep-search API is required.

Add optional metadata to each paper when it has been gathered:

```json
"provenance": {
  "producer": "host-native",
  "research": {"queries": ["round one", "citation follow-up"]},
  "doi_recheck_pending": true
},
"source_records": [
  {"source_id": "S1", "url": "https://example.test/article", "locator": "p. 4"},
  {"source_id": "S2", "url": "https://example.test/correction", "locator": "abstract"}
]
```

`provenance` must be an object; `source_records` must be a list of objects.
In-batch and existing-note duplicates retain nested mappings and distinct list
observations while preserving original scalar provenance. Store different
retrieval observations in lists instead of expecting an existing scalar to be
overwritten. User-authored note body, reading status, and annotations remain;
system-generated cluster queries or related-link metadata can be added or
refreshed. Exact replay leaves note bytes unchanged. Existing-note metadata
that cannot be edited safely fails closed; anchored/aliased target fields need
manual repair rather than silent rewriting. Metadata is included in newly
created Zotero child notes; existing child notes are not updated.

Metadata retention is not independent verification. Preserve source locators,
evidence level, gaps, and pending checks honestly. Existing authenticity,
integrity, and human semantic gates still apply. Host research alone does not
authorize library/vault writes or publication.

## Preview and writes

```bash
research-hub ingest --input ./handoff.json --cluster example-review --dry-run
```

`run --input PATH --dry-run` works too. Preview validates local input without
invoking Zotero, search, or paid models. It preserves canonical notes, manifest,
dedup index, labels, pipeline log, and pipeline output, and prints its current
diagnostics. `ingest --json` does not expose stale prior output after a preview,
failure, or no-op. A successful preview is not an ingest; check the configured
vault and Zotero collection before an authorized real run. Supplied and
generated output paths are checked for traversal and symlink escapes before
client access.

See [the same-case acceptance comparison](native-research-handoff-verification.md)
for storage-only fixtures and intentional limits.

## Common errors

- `KeyError: 'methodology'`
  Add a `methodology` field before running a real ingest.
- `Paper N: 'key_findings' must be a list of strings`
  Use `["finding one", "finding two"]`, not one string.
- `dict authors must have 'creatorType'`
  Add `"creatorType": "author"` to every author dict.

## Recovery

If a partial ingest created Zotero items but failed before writing notes or
updating the dedup index, inspect and repair the cluster with:

```bash
research-hub pipeline repair --cluster <slug> --dry-run
research-hub pipeline repair --cluster <slug> --execute
```
