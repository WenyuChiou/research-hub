# papers_input.json schema

`research-hub run` and `research-hub ingest` read `<vault>/papers_input.json`.
If you have a DOI, `research-hub add <doi>` is usually easier, but manual batch
files should follow this schema.

## Location

`<vault>/papers_input.json`

The vault root is whatever `research-hub doctor` reports for `vault:`.

## Shape

The file must be a JSON array of paper objects.

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
