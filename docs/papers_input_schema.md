# papers_input.json schema

This is the file the `research-hub run` and `research-hub ingest`
commands read to know what papers to process. The `research-hub add`
command builds it for you automatically — you only need to author it
manually if you have a batch of papers from another source.

## Location

`<vault>/papers_input.json`

The vault root is whatever `research-hub doctor` reports for `vault:`.
Default: `~/knowledge-base/papers_input.json`.

## Format

A JSON array of paper objects. One entry per paper.

## Required fields

| Field | Type | Notes |
|---|---|---|
| `title` | string | Paper title (no quotes inside) |
| `doi` | string | DOI without `https://doi.org/` prefix |
| `authors` | array | See "Authors" section below |
| `year` | int | Publication year |

## Recommended fields (for full citation)

| Field | Type | Notes |
|---|---|---|
| `journal` | string | Journal or venue name |
| `volume` | string | Journal volume |
| `issue` | string | Journal issue |
| `pages` | string | "100-120" or "100, 200" |
| `abstract` | string | Full abstract text |
| `url` | string | Canonical URL |
| `pdf_url` | string | Direct PDF download URL (arXiv-style) |
| `tags` | array of strings | Tags applied to both Zotero + Obsidian |

## Pipeline-specific fields

| Field | Type | Notes |
|---|---|---|
| `slug` | string | Filename stem (e.g., `smith2025-paper-title`) |
| `sub_category` | string | Cluster slug for routing |
| `summary` | string | Goes into Obsidian `## Summary` section |
| `key_findings` | array of strings | Goes into Obsidian `## Key Findings` |
| `methodology` | string | Goes into Obsidian `## Methodology` |
| `relevance` | string | Goes into Obsidian `## Relevance` |

## Authors

The `authors` array can contain either strings OR Zotero creator dicts.
**Zotero creator dicts MUST include `creatorType`.**

### String format (simple)

```json
"authors": ["Wen-Yu Chang", "Ethan Yang"]
```

The pipeline parses these by splitting on whitespace: last token is
the surname.

### Zotero creator format (full)

```json
"authors": [
  {"creatorType": "author", "firstName": "Wen-Yu", "lastName": "Chang"},
  {"creatorType": "author", "firstName": "Ethan", "lastName": "Yang"}
]
```

`creatorType` accepts: `"author"`, `"editor"`, `"translator"`, etc.
**Missing `creatorType` causes a Zotero API 400 error.** The pipeline
validates this BEFORE calling Zotero, so you'll get a clear error
message instead of a cryptic crash.

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
    "abstract": "...",
    "tags": ["llm-agent", "geopolitics", "deterrence"],
    "slug": "rivera2024-escalation-risks-from-language-models",
    "sub_category": "ai-agent-geopolitics",
    "summary": "Authors test 5 LLMs in 8 wargame scenarios...",
    "key_findings": ["Models escalated more than human experts.", "GPT-3.5 was the most aggressive."],
    "methodology": "Wargame benchmark.",
    "relevance": "Direct evidence that LLMs introduce escalation bias when used as policy advisors."
  }
]
```

## Easier path: just use `add`

If you have a DOI, you don't need to write any of this. Run:

```bash
research-hub add 10.1145/3630106.3658942 --cluster ai-agent-geopolitics
```

This fetches all the metadata via Semantic Scholar + CrossRef and
builds the entry for you.
