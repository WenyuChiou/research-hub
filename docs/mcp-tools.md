# MCP tools reference

research-hub exposes its capabilities as Model Context Protocol (MCP) tools. Once you've run `research-hub install --mcp` and restarted Claude Desktop, every tool below is callable by your AI agent.

> Auto-generated from `@mcp.tool()` decorators in `src/research_hub/mcp_server.py`. Last regenerated for v0.30.0.

For the architectural rationale of each tool category (and especially why crystals exist), see [anti-rag.md](anti-rag.md). For a worked example, see [example-claude-mcp-flow.md](example-claude-mcp-flow.md).

---

## Discovery + ingest

### `propose_research_setup(topic: str)`
Propose names for a new research collection without creating anything. Use this BEFORE creating clusters/collections/notebooks. Show the suggestions to the user and ask them to confirm or override before any state-changing call.

### `search_papers(query: str, limit: int = 10, ...)`
Multi-backend academic paper search (OpenAlex + arXiv + Crossref). Returns ranked candidates with title, authors, year, DOI, abstract. Use to find papers by topic, author, or DOI keyword.

### `enrich_candidates(candidates: list[dict])`
Enrich raw search results with abstracts and metadata. Use after `search_papers` if abstracts were missing.

### `verify_paper(identifier: str)`
Resolve a DOI / arXiv ID against multiple sources to confirm it exists and get canonical metadata. Use before adding to catch typos or invalid IDs.

### `discover_new(cluster_slug: str, query: str | None = None)`
Pull discovery candidates from OpenAlex / arXiv / Semantic Scholar relevant to a cluster's existing literature. Returns candidates to be scored.

### `discover_continue(cluster_slug: str)`
Resume a paginated discovery search where it left off.

### `discover_variants(cluster_slug: str)`
Show alternative discovery queries for a cluster.

### `discover_status(cluster_slug: str)`
Return current discover state for a cluster.

### `discover_clean(cluster_slug: str)`
Remove the discover stash directory for a cluster.

### `suggest_integration(slug: str, candidate: dict)`
Decide whether a candidate paper fits an existing cluster, needs a new cluster, or should be skipped.

### `add_paper(identifier: str, cluster_slug: str, ...)` *(via CLI)*
The full ingest pipeline: resolves identifier → creates Zotero entry in cluster-bound collection → writes Obsidian note → updates dedup index. **v0.30 fix:** routes to cluster's `zotero_collection_key` instead of always using the default.

---

## Cluster management

### `list_clusters()`
List all topic clusters with their bindings (Zotero collection key, NotebookLM notebook ID, sync status).

### `show_cluster(slug: str)`
Show detailed info for a cluster including sync status (paper counts, drift alerts, sub-topics).

### `merge_clusters(source: str, into: str)`
Merge one cluster into another. Re-tags Zotero items, moves Obsidian notes.

### `split_cluster(source: str, query: str, new_name: str)`
Split a source cluster into a new cluster based on title keyword overlap. For citation-graph-driven splits, use `suggest_cluster_split` (CLI: `clusters analyze --split-suggestion`).

### `prune_cluster(slug: str, ...)`
Mark papers for deprecation/archival within a cluster after a label audit.

---

## Labels + reading status

### `label_paper(slug: str, label: str)`
Apply a canonical label to a paper. Vocabulary: `seed`, `core`, `method`, `benchmark`, `survey`, `application`, `tangential`, `deprecated`, `archived`.

### `list_papers_by_label(label: str, cluster_slug: str | None = None)`
Filter papers by label across one cluster or the whole vault.

### `mark_paper(slug: str, status: str)`
Update reading status: `unread`, `reading`, `read`, `noted`.

### `move_paper(slug: str, to_cluster: str)`
Move a note (and its Zotero collection membership) to a different cluster.

### `remove_paper(identifier: str, include_zotero: bool = False, dry_run: bool = False)`
Remove a paper from the vault, optionally deleting its Zotero item too. Pass `dry_run=True` first to see what would happen.

---

## Sub-topics

### `propose_subtopics(cluster_slug: str, target_count: int = 5)`
**Phase 1 of subtopic split.** Build a prompt the calling AI uses to propose sub-topic names + descriptions for a cluster.

### `apply_subtopic_assignments(cluster_slug: str, assignments: dict)`
Write `subtopics:` frontmatter to each paper note based on AI assignments.

### `emit_assignment_prompt(cluster_slug: str, subtopics: list[dict])`
**Phase 2 of subtopic split.** Build the assignment prompt asking the AI to map each paper to its best-fit sub-topic.

### `build_topic_notes(cluster_slug: str)`
Generate `topics/NN_<slug>.md` files from paper frontmatter — the per-subtopic landing pages with auto-aggregated paper lists.

### `list_topic_notes(cluster_slug: str)`
List existing sub-topic notes for a cluster.

---

## Topic overviews

### `read_topic_overview(cluster_slug: str)`
Return the current topic overview markdown for a cluster (`hub/<cluster>/00_overview.md`), if present.

### `write_topic_overview(cluster_slug: str, markdown: str, overwrite: bool = False)`
Write or replace the cluster's overview markdown. Use after the AI has synthesized a "what is this cluster about" summary.

### `get_topic_digest(cluster_slug: str)`
**Lazy mode (pre-crystal).** Returns every paper in a cluster plus a markdown digest. Token-heavy (~30 KB for 20 papers). Prefer `list_crystals` + `read_crystal` for cluster-level questions.

---

## Crystals (anti-RAG canonical Q→A)

The architectural innovation of v0.28+. Pre-computed canonical answers replace query-time context assembly. See [anti-rag.md](anti-rag.md).

### `list_crystals(cluster_slug: str)`
List all pre-computed crystal answers for a cluster. Returns `[(slug, question, tldr, confidence, based_on_paper_count, stale)]`. Calling AI uses this to pick which crystal matches the user's question.

### `read_crystal(cluster_slug: str, crystal_slug: str, level: str = "gist")`
Read one crystal at the requested detail level. `level="tldr"` (1 sentence, ~50 tokens), `"gist"` (~100 words, ~150 tokens), `"full"` (~500-1000 words with evidence wiki-links, ~1500 tokens).

### `emit_crystal_prompt(cluster_slug: str, question_slugs: list[str] | None = None)`
Emit a markdown prompt the calling AI should answer to generate crystals. Returns ~30 KB prompt with cluster definition + paper list + 10 canonical questions + JSON output schema. Pass `question_slugs` to regenerate only specific crystals.

### `apply_crystals(cluster_slug: str, crystals_json: dict)`
Persist crystal answers to `hub/<cluster>/crystals/<slug>.md`. Idempotent — re-applying the same JSON overwrites cleanly. Updates `based_on_papers` to current cluster state.

### `check_crystal_staleness(cluster_slug: str)`
Check how many crystals are stale (>10% paper delta since generation). Returns per-crystal `{added, removed, delta_ratio, stale}`.

---

## Fit-check (scope drift detection)

### `fit_check_prompt(cluster_slug: str)`
Build a prompt asking the AI to grade each paper's fit to the cluster's stated scope.

### `fit_check_apply(cluster_slug: str, scored: list)`
Persist fit-check scores to paper frontmatter.

### `fit_check_audit(cluster_slug: str)`
**Gate 3.** Parse latest NotebookLM briefing for off-topic flags.

### `fit_check_drift(cluster_slug: str, threshold: int = 3)`
**Gate 4.** Emit drift-check prompt against current overview.

### `apply_fit_check_to_labels(cluster_slug: str)`
Tag papers rejected by fit-check as `deprecated`.

---

## Autofill (frontmatter completion)

### `autofill_emit(cluster_slug: str)`
Build a prompt asking the AI to fill missing frontmatter fields (year, journal, methodology, key findings) for papers in a cluster.

### `autofill_apply(cluster_slug: str, scored: list[dict] | dict)`
Apply AI-supplied body content to paper notes.

---

## Citation graph

### `get_references(identifier: str, limit: int = 20)`
List papers cited by the given paper (its bibliography). Uses Semantic Scholar; cached locally to avoid 429s.

### `get_citations(identifier: str, limit: int = 20)`
List papers that cite the given paper. Same caching.

### `suggest_cluster_split(cluster_slug: str, min_community_size: int = 8)` *(via CLI)*
Run citation-graph community detection (networkx greedy modularity) to suggest sub-topic splits. Output is a markdown report; user reviews before applying.

---

## Quotes + draft writing

### `capture_quote(slug: str, page: str, text: str, context: str = "")`
Persist a quote to `<vault>/.research_hub/quotes/<slug>.md` for later reference.

### `list_quotes(cluster_slug: str | None = None)`
List captured quotes, optionally filtered by cluster.

### `build_citation(doi_or_slug: str, style: str = "apa")`
Return an inline citation string for a paper. Styles: `apa`, `mla`, `chicago`, `bibtex`.

### `export_citation(slug: str, style: str = "bibtex")`
Export a paper's full citation entry in the requested format.

---

## NotebookLM

### `read_briefing(cluster_slug: str, max_chars: int = ...)`
Return the most recently downloaded briefing text for a cluster from `<vault>/.research_hub/artifacts/<cluster_slug>/brief-*.txt`.

(Browser-automation NotebookLM workflows — `notebooklm bundle / upload / generate / download` — are CLI-only.)

---

## Vault search + status

### `search_vault(query: str, limit: int = 20)`
Search across paper notes by keyword (title, abstract, frontmatter, tags).

### `generate_dashboard()`
Generate the personal HTML dashboard. Returns the path to `dashboard.html`. Open in browser.

### `run_doctor()`
Run health checks on the research-hub installation. Returns structured pass/fail per check.

### `get_config_info()`
Show current configuration paths and settings. Equivalent to `research-hub where`.

---

## Examples (bundled cluster recipes)

### `examples_list()`
List bundled example clusters that ship with research-hub.

### `examples_show(name: str)`
Return the full definition for one bundled example.

### `examples_copy(name: str, cluster_slug: str | None = None)`
Copy an example into the user's cluster registry. Use to bootstrap a new research area from a curated starting point.

---

## Security model (v0.30+)

All tools that accept `cluster_slug` or `slug` parameters validate the input via `research_hub.security.validate_slug()`. Invalid input (path traversal `..`, absolute paths, non-ASCII, shell metacharacters) raises `ValidationError` before any I/O. All tools that accept `identifier` validate via `validate_identifier()` (DOIs and arXiv IDs only).

The dashboard's `/api/exec` endpoint additionally requires:
- Origin header check (must match the page's Host)
- `X-CSRF-Token` header (rotated per server start; embedded in the rendered HTML as `<meta name="csrf-token">`)

If a tool errors with `ValidationError`, your slug is malformed — clean it (lowercase, alphanumeric + `_-` only) and retry.

---

## Total tool count: 50+

Exact count varies slightly by release as we factor or merge tools. See `src/research_hub/mcp_server.py` for the source of truth.
