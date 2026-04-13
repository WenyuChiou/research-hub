# Onboarding

`research-hub` is a local-first literature workflow for researchers who want a repeatable path from search to triage to notes. It helps you search across academic backends, organize papers into topic clusters, and keep a vault ready for synthesis, fit-checking, and downstream AI workflows.

## Who Should Use It

- A computer science researcher building a cluster around LLM agents, benchmarks, or software engineering workflows.
- A biomedicine PhD student tracking protein modeling, clinical methods, or fast-moving preprints.
- A social science postdoc curating policy, economics, or education literature for an active project.

## First-Time Setup

Install the MCP-capable package:

```bash
pip install research-hub-pipeline[mcp]
```

Run a baseline health check:

```bash
research-hub doctor
```

If you are starting from scratch, create your first field-aware cluster:

```bash
research-hub init --field bio
```

You can also run the wizard fully scripted:

```bash
research-hub init --field cs --cluster llm-agents --name "LLM Agents" --query "LLM agent benchmark" --non-interactive
```

## What The Wizard Does

The field-aware onboarding flow creates a cluster and immediately launches `discover new` with field-appropriate backends.

The wizard asks for:

- A field such as `cs`, `bio`, `med`, `social`, or `edu`
- A cluster display name
- A cluster slug
- A search query
- An optional cluster definition

After that it:

1. Creates the cluster in `.research_hub/clusters.yaml`
2. Runs `research-hub discover new ... --field <slug>`
3. Writes the fit-check prompt to `.research_hub/discover/<cluster>/prompt.md`
4. Prints the next commands needed to continue

## Example Flow

```bash
research-hub init --field cs
```

Typical follow-up output points you to:

1. Score the prompt in `.research_hub/discover/<cluster>/prompt.md`
2. Save the scored result as `scored.json`
3. Run `research-hub discover continue --cluster <cluster> --scored scored.json --auto-threshold`
4. Run `research-hub ingest --cluster <cluster> --fit-check`
5. Run `research-hub topic scaffold --cluster <cluster>`

## Bundled Examples

You can bootstrap from one of the bundled example clusters instead of starting from a blank query.

List them:

```bash
research-hub examples list
```

Inspect one:

```bash
research-hub examples show cs_swe
```

Copy one into your own registry:

```bash
research-hub examples copy cs_swe --cluster my-se-agents
```

Each example includes:

- A title and slug
- A recommended field
- A starter query
- A cluster definition
- Suggested year bounds
- Sample DOIs

## Doctor Field Check

`research-hub doctor` now includes a field inference pass for each cluster. It scans note text for venue and keyword signals, then compares the inferred field against the cluster's seed keywords.

This is a warning signal, not a hard validator. A mismatch usually means one of these:

- The cluster query is too broad
- The cluster was created with the wrong field preset
- The note set has drifted into a neighboring discipline

## Recommended Next Steps

- `research-hub topic scaffold --cluster <slug>` to start a cluster overview
- `research-hub fit-check emit --cluster <slug> --candidates ...` for manual screening workflows
- `research-hub doctor` to verify config, vault health, and field alignment
- `research-hub dashboard` for a generated local overview

## Field Reference

The current release ships field presets that map common research areas to backend lists. Coverage includes:

| Field | Typical backends |
| --- | --- |
| `general` | OpenAlex, arXiv, Semantic Scholar, Crossref, DBLP |
| `cs` | OpenAlex, arXiv, Semantic Scholar, DBLP, Crossref |
| `bio` | OpenAlex, bioRxiv, Semantic Scholar, Crossref, PubMed |
| `med` | PubMed, OpenAlex, Semantic Scholar, Crossref |
| `social` | OpenAlex, Crossref, Semantic Scholar, RePEc, SSRN-style metadata sources where available |
| `econ` | RePEc, OpenAlex, Crossref, Semantic Scholar |
| `edu` | ERIC, OpenAlex, Crossref, Semantic Scholar |
| `physics` | arXiv, OpenAlex, Semantic Scholar, Crossref |
| `math` | arXiv, OpenAlex, Crossref, Semantic Scholar |
| `astro` | NASA ADS, arXiv, OpenAlex, Semantic Scholar |
| `chem` | ChemRxiv, OpenAlex, Crossref, Semantic Scholar |

Check `research_hub.search.fallback.FIELD_PRESETS` for the exact backend order used by your installed version.

## Related Docs

- [AI Integrations](ai-integrations.md)
- [CLI Reference](cli-reference.md)
- [NotebookLM](notebooklm.md)
- [Setup](setup.md)
