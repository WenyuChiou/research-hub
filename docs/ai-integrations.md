# AI Integration Guide — Paper Discovery & Topic Overviews

research-hub is designed to be model-agnostic. Any AI that can run a shell command or call an MCP tool can drive the same discovery → ingest → overview workflow. This guide shows the exact path for each common AI surface.

Every path ends the same way: `research-hub topic digest --cluster X` gives the AI every abstract in the cluster, the AI writes an overview, and NotebookLM is used as a final sanity check ("does this cluster actually contain what I said it does?").

---

## The shared workflow

```
┌─────────────┐   ┌──────────────┐   ┌──────────────┐   ┌────────────┐   ┌──────────────┐
│  discover   │ → │    enrich    │ → │    ingest    │ → │  overview  │ → │ NotebookLM   │
│ (find DOIs) │   │ (full meta)  │   │ (Zotero+vault│   │ (topic.md) │   │ (verify fit) │
└─────────────┘   └──────────────┘   └──────────────┘   └────────────┘   └──────────────┘
```

1. **Discover** — find candidate papers for a topic. How you do this depends on what tools your AI has.
2. **Enrich** — turn candidates (DOI / arxiv_id / title) into full `SearchResult` records via OpenAlex/arXiv/Semantic Scholar.
3. **Ingest** — pipe enriched records into `research-hub ingest` which populates Zotero + Obsidian + dedup index.
4. **Overview** — run `research-hub topic digest` to dump cluster abstracts; the AI reads them and writes `00_overview.md`.
5. **NotebookLM** — upload the cluster's PDFs as a notebook, ask "is this really about X?" — the ground truth check.

---

## Claude Code (has WebSearch)

Claude Code is the only AI with direct `WebSearch` access. Use it for discovery; let research-hub do the metadata resolution.

```bash
# 1. Discover — Claude uses its WebSearch tool to find candidate papers.
#    Collect DOIs or arxiv IDs into a file, one per line:
cat > /tmp/candidates.txt <<EOF
10.48550/arXiv.2411.12345
10.48550/arXiv.2410.67890
2411.00000
Tight-Lipped Agents: A Study of LLM Reticence
EOF

# 2. Enrich — research-hub hits OpenAlex/arXiv/Semantic Scholar for each candidate
research-hub enrich - < /tmp/candidates.txt > /tmp/enriched.json

# 3. Build a papers_input.json scaffold
research-hub enrich --to-papers-input --cluster my-topic - < /tmp/candidates.txt \
    > /tmp/papers_input.json
# Claude then fills the summary/key_findings/methodology/relevance fields
# by reading each abstract from the enriched records.

# 4. Ingest
research-hub ingest --cluster my-topic --input /tmp/papers_input.json

# 5. Topic overview
research-hub topic scaffold --cluster my-topic
research-hub topic digest --cluster my-topic > /tmp/digest.md
# Claude reads /tmp/digest.md and writes the overview into
# <vault>/research_hub/hub/my-topic/00_overview.md directly via Edit.

# 6. NotebookLM verification
research-hub notebooklm bundle --cluster my-topic --download-pdfs
research-hub notebooklm upload --cluster my-topic
research-hub notebooklm generate --cluster my-topic --type brief
research-hub notebooklm download --cluster my-topic
# Read the briefing — if it complains about off-topic papers, go back to step 1.
```

**Hybrid tip:** Claude Code can also call the MCP tools below if it's running with research-hub's MCP server attached. Mixing WebSearch (for discovery) with MCP `enrich_candidates` (for metadata) is the most robust path because each step uses the strongest tool for the job.

---

## Claude Desktop / Cursor / Continue / any MCP client

These AIs don't have WebSearch but they can call research-hub's MCP tools directly. Everything runs through tool calls; no shell needed.

Enable MCP in the client's config (example for Claude Desktop at `~/.claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "research-hub": {
      "command": "research-hub",
      "args": ["serve"]
    }
  }
}
```

Then drive the workflow entirely via tool calls:

```
search_papers(
    query="LLM agent software engineering benchmark",
    year_from=2024,
    year_to=2025,
    min_citations=5,
    backends=["openalex", "arxiv"]
) -> list of papers with DOI, abstract, citation_count, year

# If the user pastes a list of DOIs they already have:
enrich_candidates(candidates=["10.xxx/yyy", "2411.00000"]) -> full records

# After ingest:
get_topic_digest(cluster_slug="my-topic") -> {
    "papers": [...],
    "markdown": "<full text digest the AI reads>"
}

# AI writes the overview content, then:
write_topic_overview(
    cluster_slug="my-topic",
    markdown="<AI-generated overview>",
    overwrite=False
)

read_topic_overview(cluster_slug="my-topic")
    -> returns the content so the user can verify
```

**No WebSearch path** — discovery has to use `search_papers`. Three backends in a fallback chain give good 2024-2025 coverage. For topics where all three miss, the user has to paste DOIs and use `enrich_candidates`.

---

## Codex CLI / Aider / plain shell

Shell-native AIs run `research-hub` directly. No MCP server needed.

```bash
# 1. Discover via CLI (pipes JSON)
research-hub search "LLM agent software engineering" \
    --year 2024-2025 \
    --min-citations 5 \
    --backend openalex,arxiv \
    --json > candidates.json

# 2. Extract DOIs and enrich (idempotent — safe to re-run)
jq -r '.[].doi' candidates.json | research-hub enrich - > enriched.json

# 3. Build papers_input.json
research-hub search "LLM agent software engineering" \
    --year 2024-2025 \
    --to-papers-input \
    --cluster my-topic \
    > papers_input.json
# The AI fills summary/key_findings/methodology/relevance by reading
# each paper's abstract field.

# 4. Ingest
research-hub ingest --cluster my-topic --input papers_input.json

# 5. Topic overview
research-hub topic scaffold --cluster my-topic
research-hub topic digest --cluster my-topic > digest.md
# AI reads digest.md (via cat or its own Read), writes overview to
# <vault>/research_hub/hub/my-topic/00_overview.md

# 6. Ship to NotebookLM for verification
research-hub notebooklm bundle --cluster my-topic --download-pdfs
research-hub notebooklm upload --cluster my-topic
```

**Codex tip:** use `codex exec --full-auto -C ~/vault "do steps 1-5 for cluster llm-agents"` and Codex will run the whole chain.

---

## Gemini CLI

Same as Codex CLI — shell path. The `research-hub` CLI is model-agnostic.

Gemini-specific caveat: when asking Gemini to fill papers_input.json summaries, give it a small JSON batch at a time (5-10 papers) rather than all 25 at once. Gemini's JSON output reliability degrades in long contexts.

---

## When to use what

| You have | Recommended path |
|---|---|
| A list of DOIs or arxiv IDs | `research-hub enrich - < candidates.txt` |
| A topic but no papers | `research-hub search "..." --year 2024-2025 --json` |
| An existing cluster with no overview | `research-hub topic scaffold && research-hub topic digest` |
| A cluster that may be off-topic | Bundle and upload to NotebookLM, then ask "is this about X?" |
| Claude Code with WebSearch available | WebSearch for discovery + `enrich` for metadata |
| Anything else | Three-backend `search_papers` via CLI or MCP |

---

## Offline / airgapped mode

The three backends all require network. If you're offline:

- `research-hub search --backend ""` fails — the backend list can't be empty.
- Use `research-hub add --doi 10.xxx/yyy` or the `add_paper` MCP tool for one-off additions. Both paths accept DOIs you already trust without a search step.
- `research-hub topic digest` and `scaffold` work fully offline — they only read vault files.

---

## Debugging discovery quality

If NotebookLM flags papers as off-topic, the discovery step is to blame. Check:

1. **Lexical vs semantic drift** — Semantic Scholar is lexical, OpenAlex uses concepts. A query like "harness engineering" will miss "agent benchmark for software engineering" on Semantic Scholar but hit it on OpenAlex. Prefer `--backend openalex,arxiv` for conceptual queries.
2. **Year window too wide** — `--year 2020-2025` will dilute a 2025 topic with dated work. Narrow to `2024-2025` for new research areas.
3. **Citation threshold** — `--min-citations 10` removes most preprints. Drop it for fresh topics.
4. **Title drift** — if `enrich_candidates` returns papers with titles unlike your input, the fuzzy match threshold is at 60. Titles below that return `None`. Provide DOIs or arxiv IDs whenever possible.
