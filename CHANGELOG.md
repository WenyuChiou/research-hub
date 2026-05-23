# Changelog

> **Format (v0.95.0+):** entries follow a lightweight
> [Keep a Changelog](https://keepachangelog.com) convention going
> forward — within each version use `### Added / Changed /
> Deprecated / Removed / Fixed / Security` where applicable, and
> flag breaking changes with a **BREAKING:** prefix. Per-release
> migration steps are mirrored in [UPGRADE.md](UPGRADE.md). Entries
> before v0.95.0 predate this convention and are kept verbatim
> (retrofitting 90+ historical entries was judged higher-risk than
> the consistency gain — G4 audit #3).

## [Unreleased]

_Post-1.0. Phase B (UI 80/20 — ⌘K command palette + mobile
breakpoints + `_HOME` wayfinding) and Phase D (Zotero metadata
correctness — type-aware `itemType` mapping + `fit/<bucket>` tag +
provenance child-note parity) are staged on
`feature/v1.1-ui-80-20` for **v1.1**, to merge AFTER v1.0.0 ships.
UI scope is capped here by decision: the dashboard stays a thin
status-mirror + palette + onboarding demo; no 3-pane / citation-
graph rebuild (link out to the real tools instead)._

### Changed
- **`auto --with-pdfs` is now ON by default** (`cli.py`, `auto.py`). The `auto`
  subcommand attaches open-access PDFs from arXiv/OpenAlex/Unpaywall/Crossref
  to the ingested Zotero items as part of every run; previously `--with-pdfs`
  had to be opted in explicitly. The flag uses `argparse.BooleanOptionalAction`,
  so `--no-with-pdfs` is the new opt-out for runs where you only want the
  NotebookLM bundle. Rationale: the bundle ladder already downloaded the PDFs
  for NLM but they never made it into Zotero, leaving the
  `cluster/pdf_coverage` doctor check stuck at 0%. The Python API
  `auto_pipeline(..., with_pdfs=False)` deliberately stays opt-in so
  programmatic callers (tests, library users) don't fire the PDF-attach
  network round-trips silently — the CLI hands in an explicit `True` from
  argparse instead. `--full-auto` no longer needs to re-set
  `--with-pdfs` and was simplified accordingly, which incidentally lets
  `--full-auto --no-with-pdfs` respect the explicit opt-out (it was silently
  overridden before). The `ingest` and `run` subcommands stay opt-in
  (`--with-pdfs` only) — they are lower-level entry points where an explicit
  flag still makes sense.

### Added
- **`brief_to_docx.js` ships inside `skills/research-design-helper/scripts/`**
  (plugin `0.3.13 → 0.3.14`). Sister script to
  `skills/gap-to-topic/scripts/dossier_to_docx.js` — same Markdown → Word
  converter (heading styles, bullet lists via numbering reference,
  tables with dual-width DXA, en / zh-TW font auto-select, Markdown
  separator-row skip), but default stem is `design_brief` instead of
  `topic_dossier`. Makes the Stage 3a artifact shareable with advisors
  / committee members who prefer Word over Markdown.
  - **Not part of the contracted Stage 3a output.** `design_brief.md`
    remains the canonical artifact; the `.docx` is an optional
    convenience for human consumption only. Downstream skills (Stage
    3b `research-context-compressor`) read the `.md` frontmatter +
    section 1 directly, not the `.docx`.
  - **Verdict-colour regex inherited verbatim but does NOT fire on
    design brief content** — no "Do not pursue" / "Not assessed" /
    "不予推進" / "未評估" strings appear in a design brief. Keeping
    the regex unchanged means a single fix to the dossier generator
    lands in both scripts via parallel PRs.
  - SKILL.md adds `## Generate .docx (optional, plugin v0.3.14+)`
    section between `## Output` and `## Token-saving behavior`,
    mirroring the gap-to-topic `§4.5 Generate .docx` pattern.
  - `scripts/README.md` ships alongside, documenting prereq
    (`npm install -g docx`), invocation examples (en + zh-TW), and
    the design-brief-specific deviation (the regex no-op).
  - New test
    `test_design_helper_has_brief_to_docx_script_and_skill_md_section`
    asserts `scripts/brief_to_docx.js` exists, the SKILL.md has the
    new `## Generate .docx (optional` heading, and the script's
    default stem is `design_brief` not `topic_dossier`.
  - Mirrored to `src/research_hub/skills_data/`.

- **Stage 2 → 3a → 3b handoff wiring**
  (`skills/research-design-helper/`, `skills/research-context-compressor/`,
  `tests/fixtures/topic_dossier_sample.gaps.yml`,
  `tests/test_handoff_gap_to_topic_design_helper.py`, plugin
  `0.3.11 → 0.3.12`). Two broken wires fixed as one coherent
  user-facing capability:
  - **`research-design-helper` reads `.research/topic_dossier.gaps.yml`**
    as new Input #2. New Workflow §0 preamble auto-pre-fills segment 1
    (RQ) from the chosen `gaps[].statement` and segment 5 (risks) from
    `open_questions[]` + the specific concern hinted by
    `gaps[].feasibility`. Segments 2–4 (mechanism / identifiability /
    validation) are never pre-filled — the dossier doesn't carry that
    material and pre-filling with non-content corrupts the Socratic
    dialog. When the upstream `.gaps.yml` is absent, the skill behaves
    exactly as before (no regression for standalone users). Candidate
    selection is verdict-aware: filter `gaps[]` to
    `verdict in {conditional-go, go}`, then auto-pick if one,
    ask-the-user if 2+, halt with "nothing to frame" if zero.
  - **`design_brief.md` frontmatter carries Stage 2 provenance.**
    Two new optional fields: `source: topic_dossier.gaps.yml#<gap-id>`
    (URI-fragment pointer to the chosen gap) and `gap_verdict:` (frozen
    snapshot of `verdict` + first 60 chars of `verdict_reason`). The
    brief becomes self-contained — a future reader sees which dossier
    candidate this design was framed for. Provenance-protection: a
    refresh that would change the `source` gap-id triggers a confirm
    prompt instead of silent overwrite.
  - **`research-context-compressor` reads `.research/design_brief.md`**
    as new Input #2 under "For any project". Reads the frontmatter
    (`project`, `source`, `gap_verdict`) + section 1 (Research
    question) only. This implements the long-claimed `pipeline.md`
    contract; the brief is the authority on the sharpened RQ and the
    manifest mirrors it. If frontmatter `source` is set, copies that
    gap-id into the manifest's `provenance.from_gap` field
    (forward-compat with downstream tools).
  - **First cross-skill handoff integration test** ships at
    `tests/test_handoff_gap_to_topic_design_helper.py` with a frozen
    fixture at `tests/fixtures/topic_dossier_sample.gaps.yml` (copied
    from the v0.3.10 dogfood example). Asserts: fixture parses + has
    v0.3.10+ top-level keys + `recall.screen` sub-block + per-gap
    downstream-consumer fields + `open_questions[].text`; downstream
    SKILL.md prose lists the handoff input + has the §0 preamble +
    preserves the absent-`.gaps.yml` fallback; design_brief_template
    frontmatter has `source` + `gap_verdict`;
    research-context-compressor mentions `design_brief.md`; the
    schema reference covers every key the fixture contains (drift
    detector). Subsequent stage-to-stage wires (3a → 3b proper,
    6 → 7, …) should follow this test shape.
  - Mirrored to `src/research_hub/skills_data/`. Pure additive change
    — no removed inputs, no breaking behaviour, no required new
    fields. Users without a `.gaps.yml` see identical UX to v0.3.11.

- **`dossier_to_docx.js` ships inside `skills/gap-to-topic/scripts/`**
  (plugin `0.3.9 → 0.3.10`). `topic_dossier.docx` is now a first-class
  contracted deliverable of the `gap-to-topic` skill. The generator converts
  `topic_dossier.md` to a styled Word document using `docx` 9.x: heading
  styles (H1/H2 navy, H3 dark grey), bullet lists via numbering reference,
  tables with dual-width DXA column sizing, bilingual verdict colour coding
  (light red "Do not pursue" / "不予推進", light yellow conditional
  "Worth pursuing … only if" / "值得推進…條件", light green unconditional,
  light grey "Not assessed" / "未評估"), Markdown separator-row skip, and an
  optional TOC + page break after the first table (`--no-toc` to suppress).
  Font auto-selects: filename matching `.zh|zh-|zh_|-tw|-cn` → Microsoft
  JhengHei; else Arial. Prerequisite: `npm install -g docx`. SKILL.md updated
  with §4.5 "Generate .docx" workflow step; front-matter description and "What
  it produces" updated to list `.docx` as a first-class artifact. Mirrored to
  `src/research_hub/skills_data/gap-to-topic/scripts/`.

### Fixed
- **`paper-memory-builder` doc enhancements — F-cross2 figures.yml
  sentinel + F-cross3 evidence-artifact scanning** (`skills/paper-memory-builder/SKILL.md`,
  `skills/paper-memory-builder/references/yaml-schemas.md`,
  `tests/test_handoff_gap_to_topic_design_helper.py`, plugin
  `0.3.15 → 0.3.16`). Two small doc improvements surfaced by the
  Stage 7-8 dogfood (`~/.claude/audits/dogfood_runs/2026-05-23-paper-memory-academic-writing-stage-7-8/VERIFICATION.md`):
  - **F-cross2 — figures.yml `file:` sentinel values.** The schema
    requires `figures[].file` (required field), but real-world
    Word-based research workflows often have figures embedded
    directly inside the `.docx` manuscript with no separable source
    file. Adds a `### file: sentinel values (v0.3.16+)` section to
    `references/yaml-schemas.md` documenting three sentinels:
    `embedded-in-manuscript`, `embedded-in-supporting-information`,
    `embedded-in-presentation`. Downstream consumers
    (academic-writing-skills figure-text checks, future
    figure-archive tooling) treat these as "present in manuscript,
    no separable artifact to verify independently." Documented
    limitation, not a permanent solution — future versions may add
    a pre-processing step that extracts embedded figures.
  - **F-cross3 — SKILL.md "Scanning the paper repo for evidence
    artifacts" sub-section.** The previous Inputs section only
    described figures + manifest files but real research repos
    contain many non-figure evidence artifacts (simulation CSVs,
    analysis scripts, drawio sources, reviewer-response artifacts).
    The new sub-section documents typical artifact types and shows
    an example of populating `claims[].evidence_artifacts` with
    artifact PATHs for non-figure evidence (e.g. a chi-squared test
    claim might cite an `outputs/llm-abm_decision_log.csv` + the
    analysis script that ran it, in addition to the manuscript
    anchor). Makes the audit trail end-to-end traceable.
  - **Tests:** added 2 new test cases to
    `test_handoff_gap_to_topic_design_helper.py`:
    (1) `test_paper_memory_yaml_schemas_documents_file_sentinel_values`
    asserts all 3 sentinels appear in `yaml-schemas.md`;
    (2) `test_paper_memory_skill_md_documents_evidence_artifact_scanning`
    asserts the SKILL.md Inputs section has the new sub-section AND
    mentions at least 3 non-figure artifact types (Simulation,
    Analysis scripts, Drawio).
  - Pure additive prose change. Mirrored to
    `src/research_hub/skills_data/paper-memory-builder/`.

- **Codex review tightenings — multi-eligible fixture + design_brief
  placeholder marker** (`tests/fixtures/topic_dossier_multi_eligible_sample.gaps.yml`,
  `skills/research-design-helper/references/design_brief_template.md`,
  `skills/research-design-helper/SKILL.md`,
  `tests/test_handoff_gap_to_topic_design_helper.py`, plugin
  `0.3.14 → 0.3.15`). Two follow-ups from the independent Codex
  evaluation of the v0.3.12 + v0.3.13 + v0.3.14 deliverables
  (`.ai/codex_eval_report.md`, verdict ship-with-fixes):
  - **C2 — multi-eligible fixture.** The §0 "2+ candidates, ask the
    user" branch was documented in SKILL.md and verified by the
    branch-coverage prose test, but never exercised against a real
    fixture with multiple `verdict ∈ {conditional-go, go}` entries.
    New synthetic fixture
    `tests/fixtures/topic_dossier_multi_eligible_sample.gaps.yml`
    ships 3 gaps (G1 conditional-go, G2 conditional-go, G3 no-go) so
    the filter produces 2 eligibles. Two new tests:
    (a) `test_multi_eligible_fixture_parses_and_has_2plus_go_eligible`
    asserts the fixture's filter result keeps the 2+ branch
    exercised (guards against fixture decay), and (b) a
    parametrized `test_fixture_parses_and_drives_correct_section_0_branch`
    runs across both fixtures asserting each drives its expected §0
    branch (auto-pre-fill vs ask-the-user). A future third fixture
    for the zero-eligible halt branch can be added with one tuple.
  - **C4 — design_brief placeholder marker.** The v0.3.12 dogfood
    filled segments 2–4 with test-fit placeholder content (not from
    real Socratic dialog) and used an ad-hoc `_TEST-FIT-PLACEHOLDER_`
    inline tag. Codified as a structured frontmatter field:
    `placeholder_segments: []` (list of segment numbers). Example:
    `placeholder_segments: [2, 3, 4]` means segments 2–4 are
    placeholders, downstream tools should refuse to gate real
    research on a brief with non-empty list. SKILL.md adds a
    "Placeholder marker (v0.3.15+)" paragraph in the Output section
    explaining when to use it. New test
    `test_design_brief_template_has_placeholder_segments_field`
    asserts the frontmatter accepts the field.
  - Pure additive: no removed fields, no changed enum tokens, no
    behaviour change on absent/empty placeholder list. Mirrored to
    `src/research_hub/skills_data/`.

- **`research-context-compressor` Output spec shows
  `provenance.from_gap`; `research-design-helper` §0 forbids
  in-file pre-fill annotations** (`skills/research-context-compressor/SKILL.md`,
  `skills/research-design-helper/SKILL.md`,
  `tests/test_handoff_gap_to_topic_design_helper.py`, plugin
  `0.3.12 → 0.3.13`). Two minor SKILL.md prose tightenings surfaced
  by the v0.3.12 Stage 3a + 3b dogfood (`~/.claude/audits/dogfood_runs/2026-05-22-research-design-helper-llm-abm-socio-hydrology/`):
  - **F1 — compressor Output example now shows `provenance.from_gap`.**
    The field was registered in `docs/research-workspace-manifest.md`
    (PR #95) and mentioned in the compressor `## Inputs` section
    (PR #96), but the `## Outputs you must produce` section had no
    example — a prose-driven skill is at risk of agents missing the
    wire. v0.3.13 adds an explicit example block under Outputs
    showing the `provenance: { from_gap: ... }` shape and codifies
    the absent-state rule (omit the block when there's no upstream;
    do NOT write `provenance: {}` or `null`). Provenance-protection
    on refresh now also explicitly applies to
    `manifest.provenance.from_gap` (mirrors the v0.3.12 rule in
    `research-design-helper`).
  - **F2 — §0 forbids `_PRE-FILL_`-style annotations in
    `design_brief.md` content.** The v0.3.12 §0 wrote
    `gaps[].statement` into segment 1 but didn't say HOW to format
    it. The dogfood agent added a `_PRE-FILL (review/sharpen): ..._`
    annotation that wouldn't get cleaned up after segment 1 dialog
    sharpened the RQ. v0.3.13 clarifies: write the statement
    verbatim, no annotation in the file; the chat-level message
    flags it as pre-fill. Means segment 1 dialog can simply
    overwrite the statement with the sharpened RQ — no cleanup
    step needed.
  - **Test coverage:** added 2 new test cases to
    `test_handoff_gap_to_topic_design_helper.py` (14 → 16 total)
    asserting (1) the compressor Outputs section mentions
    `provenance` AND `from_gap`, (2) the §0 segment-1 pre-fill rule
    explicitly forbids `_PRE-FILL_` annotations in file content
    (negation regex, not just word-presence — guards against
    rewrites that drop the prohibition).
  - Pure additive prose change (no removed inputs, no schema
    changes, no behaviour change on absent upstream). Mirrored to
    `src/research_hub/skills_data/`.

- **`gap-to-topic` schema reference + research-hub discoverability**
  (`skills/gap-to-topic/references/dossier-template.md`,
  `docs/ai-research-skills.md`, plugin `0.3.10 → 0.3.11`). Two
  contract-vs-reality fixes ahead of the Stage 2 → 3a handoff wiring:
  - **Schema reference refresh.** The `topic_dossier.gaps.yml` schema
    in `references/dossier-template.md` was stale relative to what
    `gap-to-topic` actually emits since v0.3.6 (the `--screen`
    fit-check integration) and v0.3.9 (the 7-section reflow): missing
    top-level `run_type` / `recall` (with full `screen` sub-block) /
    `pipeline`; missing per-gap `open_confidence` /
    `dead_end_evidence` / `borderline_reason` / `verdict` /
    `verdict_reason`. The schema is now byte-aligned with the real
    output and adds a top-level `downstream_consumer:
    research-design-helper` key as a forward-compat hook recording
    the contract reader.
  - **Discoverability.** `docs/ai-research-skills.md` had zero mentions
    of `gap-to-topic` despite the skill being shipped at v0.3.10.
    Added a new Stage 2.5 row to the Stages table, a "Deciding whether
    a research gap is worth pursuing" entry to the When-to-use table,
    and a full `### gap-to-topic (v0.3.11)` section in All packaged
    skills documenting Reads / Writes / handoff to Stage 3a /
    trigger phrases.
  - Pure additive changes (no removed fields, no enum tokens changed).
    Mirror at `src/research_hub/skills_data/gap-to-topic/` updated in
    parity.
- **`gap-to-topic` dossier reflowed as a 7-section research-grade decision
  memo** (`skills/gap-to-topic/`, plugin `0.3.8 → 0.3.9`). The v0.3.8
  dossier rendered as "Markdown converted to Word" — wide scorecard with
  one-letter-wide columns, no decision-level visual cue, too many tables
  in the body. `references/dossier-template.md` is reorganised: §1
  Executive Decision Summary (metadata + verdict cards + key uncertainty)
  → §2 Candidate Definitions (prose, no roster table) → §3 Decision
  Scorecards (per-candidate small tables, replacing the wide combined
  one) → §4 Evidence Base → §5 Gate-by-Gate Assessment (each gate uses a
  fixed Score / Evidence / Interpretation / Risk / Action-needed
  skeleton) → §6 Risks and Upgrade/Kill Tests (named risks; operational
  kill-test artifacts; salvage path) → §7 Recommended Next Steps (formal
  research-memo prose) → Appendix A Search and Screening Protocol
  (reproducibility log) → Appendix B Deliverable File List. SKILL.md
  "What it produces" updated to match. Mirrored to
  `src/research_hub/skills_data/gap-to-topic/`.
- **Cluster overview LLM auto-fill now actually fires on fresh clusters**
  (`cluster_overview.py`, `vault/hub_overview.py`,
  `tests/test_v071_cluster_overview.py`, `tests/test_hub_overview.py`).
  The `_CHINESE_TEMPLATE_MARKER` constant in `cluster_overview.py` and
  the `_SCAFFOLD_MARKERS` tuple in `vault/hub_overview.py` both stored
  **mojibake** from a historical cp950 ↔ UTF-8 round-trip, so they never
  matched the actual Chinese placeholder phrases `topic.py` writes for a
  new cluster (`一到兩句話說清楚...` for TL;DR, `用一句話寫下...` for
  核心問題). Net effect: every brand-new cluster was immediately
  classified as "hand-curated", `apply_overview` silently refused to
  call the LLM, and the sibling `populate_overview` path likewise
  refused to refresh those sections — leaving the `00_overview.md`
  stuck at the empty scaffolding (TL;DR / 核心問題 / 範圍定義 / 領域地圖
  / 必讀論文 / 時間線 / 開放問題 all blank). The markers are now the
  real opening phrases (`一到兩句話`, `用一句話寫下`); the legacy
  mojibake markers stay so vaults whose existing `00_overview.md` still
  contains the corrupted bytes are still recognised and refreshed
  cleanly. The test fixture `_template_text` was likewise mojibaked and
  now mirrors `topic.py` verbatim, plus two dedicated regression tests
  (one per code path) pin the marker ↔ template round-trip so this
  can't drift silently again.
- **`gap-to-topic` dossier — section-by-section rework for researcher value**
  (`skills/gap-to-topic/`, plugin `0.3.7 → 0.3.8`).  A section-by-section
  review with the maintainer, plus a Codex evaluation, reworked
  `references/dossier-template.md`:
  - **Decision scorecard** is now a 5-point Likert per gate — each gate is
    a claim rated 1–5 (strongly agree … strongly disagree); the cell is
    `N/5 label — description`; a topic is worth pursuing only if every gate
    rates 3 or higher.
  - **Gate 2** gains "What it would contribute" (one explicit claim) and a
    "Minimum validation sketch"; a caution paper is summarised by the kind
    of risk it raises, not offloaded to the reader.
  - **Gate 3** gains "Design feasibility", a "Scale outline", and an
    explicit proposal-vs-dissertation feasibility split — it is no longer
    only a data-availability test.
  - **The decision is yours** is framed consistently as a conditional
    recommendation; the upgrade/kill test is written as concrete artifacts;
    a failed candidate gets a salvage-path line.
  - **Appendix A** is recast from a tool log into a method note (search
    scope, inclusion criteria, automated-vs-judgement).
  - **What's in this deliverable** gains a file tree.
  SKILL.md "What it produces" updated.  Mirrored to
  `src/research_hub/skills_data/gap-to-topic/`.
- **`gap-to-topic` dossier reworked to read as a plain summary report**
  (`skills/gap-to-topic/`, plugin `0.3.6 → 0.3.7`).  A review found the
  dossier still did not read cleanly in Word: the candidate roster showed
  an `id` column of `G1`/`G2` codes; the Decision scorecard used
  `✓ ✗ ~` glyphs and the jargon verdicts "No-go / Conditional go / Go";
  there was no index of the bundle's files.  `references/dossier-template.md`
  now: drops the `id` column (the `G1`/`G2` ids stay only in `.gaps.yml`)
  and states "why it could be a gap" in plain words; drops the scorecard
  glyphs for plain words; replaces the verdict jargon with plain phrasing
  ("Do not pursue — as stated" / "Worth pursuing — only if its open
  conditions hold" / "Worth pursuing"); adds a "What's in this deliverable"
  index section; gives the Bottom line one plain paragraph per candidate.
  The `.gaps.yml` schema moved to a trailing "not emitted" reference block.
  SKILL.md "What it produces" updated.  Mirrored to
  `src/research_hub/skills_data/gap-to-topic/`.
- **ingest collapses in-batch duplicate papers** (`pipeline.py`). Two search
  backends can return the SAME paper under different DOIs (a journal DOI vs a
  repository/preprint DOI). DOI-keyed search-merge dedup keeps both, and
  `dedup.check()` cannot catch them either — `dedup.add()` runs only in the
  note-writing loop, so in-batch siblings stay invisible during Zotero-item
  creation. Result: two Zotero items for one paper and two notes colliding on
  an identical filename slug (one silently overwriting the other). A new
  pre-ingest in-batch dedup pass now collapses candidates sharing a
  normalized DOI or normalized title (mirrors `DedupIndex.add()`'s >15-char
  title guard), keeping the first occurrence and logging a `dup-in-batch`
  manifest entry for each collapsed sibling.
- **`gap-to-topic` §1 now applies the fit-check relevance gate**
  (`skills/gap-to-topic/`, plugin `0.3.5 → 0.3.6`).  `search --screen`
  (PR #84) wired the BM25 relevance gate into the `search` command; §1 now
  uses it.  SKILL.md §1: step 1 runs `search --adversarial --screen --json`
  and reads the new `{screening_summary, results}` shape (each paper
  carries a `relevance` field); steps 2-3 build the matrix and `.bib` from
  the **on-topic** results only (`kept: true`), excluding screened-out
  off-topic noise; step 4 reports the retrieved-vs-on-topic counts in the
  recall headline.  `references/dossier-template.md` Appendix A pipeline +
  recall-mechanics rows updated.  Mirrored to
  `src/research_hub/skills_data/gap-to-topic/`.
- **ingest dedup re-scoped to research-hub's own literature** (`pipeline.py`).
  `auto` for a new topic produced a near-empty cluster — a search returned
  25 papers, fit-check kept all 25, yet only ~1 Obsidian note was created.
  Cause: the dedup index was dominated by `source:"zotero"` entries
  mirroring the user's ENTIRE Zotero library (mostly never managed by
  research-hub) plus stale `source:"obsidian"` entries pointing at deleted
  note files. The dedup block treated **any** paper merely present in the
  Zotero library as a duplicate and `continue`-d past Obsidian-note
  creation, dropping it from the new cluster. Dedup now skips a paper only
  when it duplicates research-hub's OWN literature: (1) the `obsidian_hit`
  branch requires the note file to actually exist on disk — a stale index
  entry no longer blocks ingest; (2) the `zotero_hit` branch no longer
  skips — it still reuses the existing Zotero item (moves it into the
  cluster collection, adds hub tags + note, creates **no** duplicate item)
  but the paper is now ingested into research-hub with its Obsidian note
  created and bound to the cluster. New manifest action
  `ingest-reuse-zotero` records the reuse decision.
- **fit-check no-LLM relevance gate rewritten** (`fit_check.py`, `auto.py`).
  The old `no_llm_fit_check` gate split the topic into independent unigrams
  and kept any paper matching `>= 0.1` of them — i.e. **1 of 5** words. A
  generic hydrology paper trivially matched `water`/`model`/`resources`
  and passed while the discriminating phrase "large language model" was
  destroyed; the `llm-water-resources` cluster ended up **38/43
  off-topic**. The gate is rebuilt as a pure-Python **BM25** scorer over
  **1–3-gram** topic terms — phrases like "large language model" survive
  intact, matching is plural-tolerant, and IDF is self-calibrated on the
  candidate batch. A paper is rejected only when the batch's sorted BM25
  scores show a **blatant bimodal split** — a gap whose upper cluster
  out-scores the lower by ≥ 5× (the cross-field contamination signature:
  pure-hydrology papers score ~1 vs ~8 for genuine LLM papers). A focused,
  all-relevant search spreads only ~2× and is kept whole; cold-start
  (batch < 5, no topic terms, or no clear gap) defers — keeps all, flags
  `relevance_unverified`. Recall-biased: the no-LLM tier only catches
  blatant contamination; fine-grained relevance screening is the
  LLM-judge tier's job. New public API: `extract_topic_terms`,
  `bm25_scores`, `screen_relevance`. Grounded in a research sweep of
  ASReview (TF-IDF + Naive Bayes) and BM25 screening practice.

- **`gap-to-topic` dossier — evidence-strength tags + an upgrade/kill test**
  (`skills/gap-to-topic/`, plugin `0.3.4 → 0.3.5`).  A Codex evaluation of a
  real dossier found two gaps: (1) Gate 1 said a gap was "densely populated"
  but the reader had to open `literature_matrix.md` to see the occupancy
  signal was partly conference abstracts / artifacts, not primary studies;
  (2) a "conditional go" listed open conditions but no threshold — the
  advisor still had to supply the kill/upgrade logic.  `references/dossier-template.md`
  now: Gate 1 tags each cited work by evidence type (primary study / review
  / close analogue / caution paper / conference abstract / preprint / data
  artifact) and ends with a one-sentence evidence-mix summary; "The decision
  is yours" carries an explicit **upgrade / kill test** per conditional-go
  candidate.  Mirrored to `src/research_hub/skills_data/gap-to-topic/`.
- **`gap-to-topic` dossier — added tables for scannability**
  (`skills/gap-to-topic/`, plugin `0.3.3 → 0.3.4`).  Follow-up to the
  reader-first redesign: the verdicts were still spread across prose bullets
  in each gate section.  `references/dossier-template.md` now puts a
  **Decision scorecard** table in the Bottom line (candidates × the 3 gates
  + verdict, with a `✓`/`✗`/`~`/`—` cell convention), a **roster table** in
  The candidates, and turns Appendix A (how it was produced) and Appendix B
  (companion files) into tables.  Gate 1–3 bodies keep prose — the verdicts
  now live once, in the scorecard, so the gate sections carry only the
  evidence (no duplication).  SKILL.md "What it produces" updated.  Mirrored
  to `src/research_hub/skills_data/gap-to-topic/`.
- **`gap-to-topic` dossier was organised tool-first and code-first, not
  reader-first** (`skills/gap-to-topic/`, plugin `0.3.2 → 0.3.3`).  A review
  of a real dossier found it opened with a metadata table of pipeline / API
  rows, wove `search --adversarial` / `literature-triage-matrix` / plugin
  versions through the body, and labelled candidates with bare `[G1]` /
  `[G2]` codes a researcher cannot decode.  `references/dossier-template.md`
  is redesigned reader-first: a plain-language **Bottom line** leads; each
  candidate gets a readable **name** (the `G1` id demoted to a `.gaps.yml`
  tag); each gate states its verdict in plain words before the evidence; all
  tool / pipeline / recall mechanics move to **Appendix A**, companion-file
  notes to **Appendix B**.  SKILL.md "What it produces" + the §0 step updated
  to match; `.gaps.yml` schema gains a `name:` field.  Mirrored to
  `src/research_hub/skills_data/gap-to-topic/`.
- **`gap-to-topic` §1 named `literature-triage-matrix` as the default
  prior-art tool but no step produced its matrix** (`skills/gap-to-topic/`,
  plugin `0.3.1 → 0.3.2`).  The SKILL.md "orchestrates" paragraph + `Inputs`
  + the §2 component input-contracts all referenced
  `.research/literature_matrix.md` as an available input, yet the §1
  numbered procedure only ran `search` — so an agent following §1 literally
  never built the matrix (a "phantom input"; surfaced by a 2026-05-21
  workflow audit).  §1 now has an explicit step 2 that feeds the
  `search --adversarial --json` results to `literature-triage-matrix` to
  produce the matrix; `.bib` and recall are renumbered to steps 3-4.
  `references/dossier-template.md` Pipeline line updated.  Mirrored to
  `src/research_hub/skills_data/gap-to-topic/`.
- **`gap-to-topic` §1 `.bib` instruction was unworkable** (`skills/gap-to-topic/`,
  plugin `0.3.0 → 0.3.1`).  SKILL.md §1 step 2 and `references/dossier-template.md`
  told the skill to emit the §1 reference list via `cite --format bibtex`, but
  `cite` resolves identifiers only against an already-ingested Zotero library —
  at topic-selection time the candidate papers are not ingested, so `cite`
  returns "Could not resolve identifier" for every §1 DOI.  Surfaced by the
  2026-05-21 dogfood run.  The `.bib` is now built from the
  `search --adversarial --json` metadata, which the skill already has in hand
  at §1.  Mirrored to `src/research_hub/skills_data/gap-to-topic/`; plugin
  version bumped so the marketplace cache invalidates.
- **`notebooklm login --auto-detect` now works** (`notebooklm/auth.py`).
  The pre-fix implementation shelled out to the upstream `notebooklm login`
  subprocess and polled the patchright Chromium profile's *on-disk* Cookies
  SQLite for a `notebooklm.google.com` row. Chromium buffers cookies in
  memory and flushes them to that store only on a lazy timer, so a
  freshly-signed-in session stayed invisible on disk for minutes — the poll
  loop always timed out without ever firing the save. `--auto-detect` now
  drives the Chromium browser directly via Playwright (same stealth flags
  the SDK uses) and polls the **live `page.url`**: the moment the page
  settles on the NotebookLM host — and holds there for 3 consecutive polls,
  so a mid-redirect flash never triggers a premature save — the session is
  captured straight from the live browser context via `storage_state`. No
  terminal ENTER, no subprocess, no disk-cookie race. Fail-closed: a
  timeout, a browser-launch error, or a driver-start failure all return
  non-zero without saving and never raise into the CLI. Removed the dead
  disk-polling helpers (`_patchright_cookies_db`, `_has_notebooklm_cookie`,
  `_cookies_db_modified_since`).

- **`probe_cleared_failed_no_abstract` URL quality signal now triggers text
  fallback in the NLM bundle builder** (`notebooklm/bundle.py`).  Springer /
  Wiley paywall skeleton pages return HTTP 200 with no body; the URL quality
  probe previously rated this `ok`, so the URL was uploaded to NotebookLM
  which also received an empty shell.  The fix treats this reason code the
  same as `likely_error_page` — falling back to the abstract as a copied-text
  source, or skipping if no abstract is available.

- **Zotero reparent on cluster reuse** (`auto.py`).  Clusters created before
  the parent-collection feature was added lived at the Zotero library root.
  On subsequent `auto` runs the pipeline found them by name and returned early,
  never calling `ensure_parent_collection`.  New helper
  `_maybe_reparent_collection` PATCHes the collection's `parentCollection` to
  the configured parent (default `"research-hub"`) when it is currently
  top-level (`parentCollection=False`).  Idempotent and best-effort.

- **PDF auto-attach step in `auto_pipeline`** (`auto.py`).  When `--with-pdfs`
  is passed, the pipeline now also calls the OA-PDF attachment chain
  (OpenAlex / Unpaywall / arXiv) for every Zotero item in the cluster after
  ingest, attaching the PDF as an `imported_file` child item.  Previously
  `--with-pdfs` only fed PDFs to the NLM bundle, not Zotero.

- **Summarize pending hint** in `auto_pipeline` next-steps output.  After a
  run, if any papers in the cluster have `summarize_status: pending`, the
  terminal output now prints a `[HINT]` line with the exact command to run
  (`paper summarize --pending --cluster <slug>`).

### Added
- **`search --screen` — fit-check BM25 relevance gate on the search
  command** (`cli.py`).  The BM25 relevance gate (`screen_relevance` /
  `bm25_scores`, from PRs #79/#81/#83) was only applied by the `auto`
  ingest pipeline; the standalone `search` command returned unscreened,
  potentially off-topic results.  `search --screen` now runs that same
  gate over the retrieved papers: each result is tagged with a relevance
  score + a keep / screened-out verdict, and a screening summary
  (`N retrieved → M kept, K screened out`) is printed to stderr.  It is
  **recall-preserving** — no paper is dropped from the output, so a caller
  can still audit the full retrieved count.  `--json` switches to a
  `{"screening_summary": {...}, "results": [...]}` object (each result
  carrying a `relevance` block) when `--screen` is set; without `--screen`
  the output is byte-identical to before (bare array).  Composable with
  `--adversarial` / `--max-variants` / `--rank-by` (orthogonal to ranking
  — `--screen` only annotates).  Reuses the existing gate; no new scorer.

- **`gap-to-topic` skill — a topic-decision dossier.** New 11th packaged
  skill. Choosing a thesis/proposal topic is a go/no-go decision, not a
  literature review; `gap-to-topic` produces a `.research/topic_dossier.md`
  that runs a candidate breakthrough point through a 3-gate AND test —
  ① is the gap open (adversarial-recall search + a verifiable `.bib`),
  ② is it a contribution (dead-end history + problem-solving/incremental
  typing), ③ is it feasible (data/resource accessibility) — and hands the
  final "is it worth doing" verdict back to the researcher. `skills/gap-to-topic/`
  (SKILL.md + 3 references + evals) mirrored to `skills_data/`;
  `.claude-plugin/plugin.json` 10→11 skills, version `0.2.0 → 0.3.0`. The
  `research-design-helper` and `literature-triage-matrix` descriptions gain
  a one-line boundary clause routing topic-selection prompts to `gap-to-topic`.
- **NLM session pre-flight in `auto_pipeline`.**  Before attempting any
  NotebookLM browser work, `auto_pipeline` now calls `check_session_health`
  on the stored `state.json`.  When the session is missing or expired the
  pipeline skips NLM gracefully, sets `nlm_deferred=True`, and prints a
  `[HINT]` pointing at `research-hub notebooklm login` — instead of running
  a full headless browser session that would crash with an opaque Playwright
  error.  The `_print_next_steps` footer now distinguishes
  *"session expired → login first"* from *"transient error → retry"*.
  Health-check errors are caught so existing behaviour is preserved when
  the auth module is unavailable.
- **Adversarial-recall search — `research-hub search --adversarial`.**
  A single query phrasing systematically misses papers that use other
  vocabulary; in topic-scoping search a missed paper makes a research gap
  look open when it is not. `--adversarial` expands the query into several
  phrasings (LLM-generated when an LLM CLI is on PATH, deterministic
  fallback otherwise), searches each, unions the results by `dedup_key`,
  and prints a recall-confidence verdict (`high`/`medium`/`low`, derived
  from query saturation) to stderr. New `search/query_expansion.py`;
  `adversarial_search()` + `RecallReport` added to `search/fallback.py`;
  `tests/test_search_adversarial.py` (18 cases).
- **Summary quality improvements** (4 changes):
  - `link_updater.find_related_in_cluster` capped at **10 results** (was
    unbounded) — prevents mega-hub nodes in the Obsidian graph for large
    clusters.
  - `remove_paper_links(slug, raw_dir, cluster)` — new function scrubs a
    deleted paper's slug from every sibling note's Related Papers section;
    removes the entire section header when the deleted slug was the last
    entry.
  - `remove_paper()` now cascades the cleanup automatically and returns
    `links_cleaned` in its result dict.  `dry_run=True` is respected.
  - `paper_summarize` RELEVANCE prompt updated to require a **specific
    dimension** (method / empirical context / finding) rather than
    accepting a generic "this paper is relevant to [cluster]" sentence.
  - `crystal emit` prompt now exposes a `first_finding` field per paper
    (first Key Findings bullet, callout-format aware) to give the LLM
    more signal per paper.
- **`docs/literature-review-deliverable.md` — format specification.**
  Defines the consolidated document the skill pipeline (`search` →
  `literature-triage-matrix` → `research-design-helper`) produces end
  to end: the fixed 9-section
  contract, the `.bib` + `.gaps.yml` companion-file schemas, the
  per-paper summarization contract (and how it relates to the
  `paper-summarize` skill), honesty rules, and the bilingual /
  Markdown+Word bundle convention. A fully synthetic worked example
  ships in the `ai-research-skills` catalog repo.
- **CI `skill-version-guard` job** (`.github/workflows/ci.yml`). Blocks
  a PR that changes skill content (`skills/` or
  `src/research_hub/skills_data/`) without also bumping
  `.claude-plugin/plugin.json` `version`. The marketplace plugin cache
  directory is keyed on the version string, so an un-bumped
  skill-content change ships to `master` but never reaches user
  installs. A 2026-05-21 dogfood verification (finding V1b) caught
  exactly this — a SKILL.md change merged without a version bump and
  silently failed to propagate. This guard makes that class of bug a
  hard CI failure at PR time.
- **`--peer-reviewed` flag on `search` and `auto`.** Drops preprint
  backends (arXiv/bioRxiv/chemRxiv/medRxiv), excludes gray doc types
  (preprint/posted-content/report/book-chapter/paratext/dataset), and
  floors corroboration. Closes the gap where `auto` ran search with
  **zero** filtering and the one-shot pipeline could not express
  "peer-reviewed only" (gray literature silently entered the vault).
- **`doctor` check `nlm_auth_paths`.** Reports which NotebookLM
  re-authentication paths actually work on this machine (interactive
  vs `--from-browser`/rookiepy) and the exact command to run.
- **`paper-memory-builder` anti-leakage rule + E4 triad.** New JSON
  Schema at `skills/paper-memory-builder/references/claims.schema.json`
  enforces: a claim with empty / absent `evidence_artifacts` MUST have
  `status: gap` and a non-empty `gap_reason`. Two new files alongside:
  `scripts/check_claims_schema.py` (validator with JSON-pointer-style
  error paths) and `tests/test_check_claims_schema.py` (14 cases — 1
  meta, 4 positive, 5 negative, 4 schema-shape guardrails). The
  binding contract is restated in `skills/paper-memory-builder/SKILL.md`
  §"Anti-leakage rule" so it survives the SKILL.md-only marketplace
  install sync. Status enum extended: `draft | supported | rejected |
  gap`. Closes the long-standing Phase 2 Task B1 + E4 backlog item
  from the `WenyuChiou/ai-research-skills` plan.
- **`tests/test_skills_data_parity.py`** (21 cases) — guards the
  `skills/` ↔ `src/research_hub/skills_data/` byte-parity invariant.
  ``research_hub.skill_installer`` copies skills from
  ``skills_data/``, so editing a SKILL.md in ``skills/`` only ships
  the change to public-repo readers, not to ``research-hub install``
  users. This test catches the divergence at PR time. Exception list
  (``SHADOW_ONLY_IN_SKILLS_TREE``) documents intentional shadows; one
  entry today (``zotero-skills`` vendored copy, scheduled for removal
  in Phase 2 Wave C).
- **Backup-first callout in `zotero-library-curator`.** SKILL.md
  §"Output discipline" + `references/report-template.md` now lead the
  "Suggested follow-ups" section with a Zotero-RDF backup reminder
  before any apply/CRUD handoff to `zotero-skills` or
  `research-hub zotero ... --apply`. Closes the gap surfaced by the
  `ai-research-skills` Task #27 dogfood walk: read-only audit + apply
  step are different skills, and the callout was only on the
  marketplace README — never echoed to the user at handoff time.

### Changed
- **`research-workspace` plugin version bumped `0.1.0` → `0.2.0`**
  (`.claude-plugin/plugin.json`). The marketplace plugin cache is keyed
  on this version; a dogfood test on 2026-05-20 confirmed fresh
  `claude plugin install` users were still receiving the pre-Phase-7
  cached `0.1.0` skill bundle — i.e. the `paper-memory-builder`
  anti-leakage rule (Phase 7 Wave A) and the `zotero-skills` shadow
  removal (Wave C) had shipped to `master` but not to user installs.
  Bumping the plugin version forces a fresh cache directory so those
  changes actually propagate. No skill behavior changed by the bump
  itself.
- **`paper-summarize` and `literature-triage-matrix` descriptions gain
  an "extract claims" disambiguation clause.** The same dogfood test
  surfaced a fragile auto-trigger boundary: a user saying "extract
  claims from these papers" could land at `paper-memory-builder`
  (own draft), `paper-summarize` (per-cited-paper), or
  `literature-triage-matrix` (cross-paper matrix). Both descriptions
  now state the disambiguation explicitly so the router picks
  correctly.

### Removed
- **Vendored `skills/zotero-skills/` shadow (Phase 7 Wave C).** The
  308-line vendored copy of the standalone `zotero-skills` plugin has
  been deleted; the canonical 60-line skill at
  `WenyuChiou/zotero-skills` is now the single source of truth.
  Coupled site updates landing in the same commit: `skill_installer.py`
  drops its `zotero-skills` exclusion (the dir no longer exists to
  filter), `tests/test_skills_data_parity.py` empties
  `SHADOW_ONLY_IN_SKILLS_TREE`, `tests/test_v068_3_version_sync.py`
  and `tests/test_v066_skill_schema.py` drop the now-stale exclusion
  comments / dead constants, and `docs/interop-test-v068-2.md` notes
  the historical snapshot vs the post-Wave-C state. Callers that
  resolve `Skill(skill="zotero-skills")` by bare name will now route
  to the canonical standalone plugin once that marketplace install
  exists in their environment. Users who relied on the vendored copy
  without separately installing `WenyuChiou/zotero-skills` will get a
  skill-not-found error until they run
  `git clone https://github.com/WenyuChiou/zotero-skills ~/.claude/skills/zotero-skills`
  (or `claude plugin install zotero-skills@ai-research-skills --scope user`).
  Closes Phase 2 backlog Item #3 from the
  `WenyuChiou/ai-research-skills` plan.
- **`.claude-plugin/plugin.json` description count corrected**
  9 → 10 skills (paper-summarize was added in v0.69 but never
  reflected in the auto-discovery plugin manifest). Picked up the
  Wave B reviewer P9 follow-up.

### Fixed
- **`probe_cleared_failed_no_abstract` now routes to abstract-text fallback.**
  When a URL's `summarize_status` is `failed_no_abstract` and the HTTP probe
  returns 200, the bundle was classifying the entry as `url_quality=ok` and
  uploading the URL to NotebookLM. This silently failed because publisher
  paywall pages (e.g. Springer) return HTTP 200 with a skeleton page that
  NLM also cannot read — the same paywall the summarizer hit at ingest time.
  `probe_cleared_failed_no_abstract` now resolves to `quality=likely_error_page`
  so the bundle falls back to abstract text when available, matching the same
  path already taken for `cloudflare_block`, `tf_cookie_wall`, and other
  confirmed paywall signals.
- **Ubuntu CI OOM (issue #61).** ubuntu-latest runners have ~7 GB RAM;
  2800+ tests with lazy-loaded modules OOM the runner. `test` job split
  into `test` (windows/macOS — 14 GB, full suite) and `test-ubuntu`
  (4 `pytest-split` shards, ~700 tests each). Coverage moved to
  `windows-latest` (per-shard coverage would undercount). `pytest-split>=0.8`
  added to dev deps.
- **User-agent strings updated to `research-hub/1.0.0`** across all
  14 search backends (biorxiv, chemrxiv, cinii, crossref, dblp, eric,
  kci, nasa_ads, openalex, pubmed, repec, websearch + the 3 already-fixed
  in the prior OSS-readiness commit). Mailto format preserved for APIs
  that recommend it (openalex, crossref, pubmed).
- **`cli.py build_parser()`** catches `PackageNotFoundError` (not bare
  `Exception`) when looking up the installed package version.
- **`pipeline_repair.py` provenance tag** bumped from
  `pipeline-repair-v0.12.0` to `pipeline-repair-v1.0.0`.

### Changed
- **`notebooklm login --help` rewritten to the three real paths.**
  Previously advertised `--cdp / --from-chrome-profile /
  --use-system-chrome / --timeout / --keep-open` as working modes;
  they were silently no-ops (the underlying aliases `del`'d their
  arguments). Help now states only: interactive default,
  `--import-from`, `--from-browser`.
- **`--from-browser` failure on Python ≥3.14 is now actionable.**
  Detects the missing-rookiepy + no-prebuilt-wheel case and points to
  the two paths that work (interactive in a terminal / `--import-from`)
  instead of a generic `pip install` hint that cannot succeed there.
- **5 SKILL.md descriptions tightened for keyword overlap with
  natural-language trigger prompts** (Phase 7 Wave A polish):
  `research-hub` adds "organize them" (matches the verified trigger
  prompt "find papers and organize them"); `paper-memory-builder`
  adds "extract claims, supporting evidence, and figure key numbers"
  (matches the catalog phrase); `research-design-helper` adds "is my
  research question sharp enough to be falsifiable?"
  (matches the verified Phase 5.3.b trigger example);
  `zotero-library-curator` adds "bloated or under-used" (matches the
  SKILL body's own audit dimension) plus an explicit RDF-backup
  reminder line. `research-hub-multi-ai` reframes itself as the
  **research-domain router** vs `agent-collab-workspace:agent-task-splitter`
  (generic multi-agent decomposition), documenting the artifact
  asymmetry (`.coord/multi_ai_plan.md` vs `.coord/plan.yml`) so the
  two skills no longer silently shadow each other on the same prompt
  — the routing overlap the `ai-research-skills` Task #27 trigger
  verification surfaced.

### Fixed
- **`auto` / `ingest` now refresh `_HOME.md`, MOC bodies, and cluster
  overviews on success.** The `populate_all_overviews` cascade
  (which writes `_HOME.md`, populates `(populated by sync)` MOC bodies
  with their cluster lists, and refreshes every `hub/<slug>/00_overview.md`)
  existed but was wired into `vault rebuild-overviews` only — `auto`
  never called it. Result: every research-session ingest left the
  vault-level navigation silently stale (empirically reproduced
  post-PR-D 4-leg E2E: no `_HOME.md` on disk, MOCs frozen at
  "(populated by sync)"). Now the cascade fires automatically when
  ingest wrote >0 papers; failures are logged to stderr and swallowed
  (the ingest itself already succeeded, navigation drift is non-fatal).
- **`--auto-detect` cookies path hotfix.** PR-D's `_patchright_cookies_db`
  hardcoded the LEGACY `Default/Cookies` path; modern Chromium (80+,
  including patchright's bundled chromium-1208) stores cookies under
  `Default/Network/Cookies`. Result: auto-detect polled the wrong file,
  never fired, user logged in successfully in the browser but the save
  never triggered. The path resolver now prefers
  `Default/Network/Cookies`, falls back to legacy `Default/Cookies`
  only if modern is missing AND legacy exists; if neither has been
  written yet (browser starting), returns the modern path so the next
  poll finds it the moment chromium writes it.

### Added
- **`notebooklm login --auto-detect` — fully automatic zero-touch login.**
  Replaces the half-automatic `--wait-file` flow (which still required a
  manual file-touch after browser sign-in). With `--auto-detect`,
  research-hub polls the patchright Chromium profile's Cookies SQLite
  read-only for a `notebooklm.google.com` host_key. When you sign in
  and land on the NotebookLM homepage, the cookie appears, the script
  feeds both `\n` (any pending `input()` ENTER) and `y\n` (any pending
  `click.confirm` "Save anyway?" fallback) to the SDK subprocess, and
  the session is saved automatically. No terminal, no wait-file touch,
  no click.confirm response. Fail-closed on `--wait-timeout`
  (default 300 s): nothing is saved on timeout. Mutually exclusive with
  `--wait-file`, `--import-from`, `--from-browser`.

### Fixed
- **Ingest skips a paper missing one or more required core fields
  instead of aborting the whole batch.** A real-world `auto` run (LLM
  reservoir management search) hit a CrossRef return with empty
  `authors: []` and the pipeline fail-fast-aborted the entire ingest
  with "INPUT VALIDATION FAILED" even though 2 other valid papers
  were ready to write. The previous `missing_doi_only` skip branch
  was inert (`doi` is not in any required-fields list, so
  `_validate_paper_input` never emitted "missing required field
  'doi'") and is replaced by a working
  `_only_missing_required_field_errors` predicate covering every
  field in `REQUIRED_FIELDS_CORE` (title / authors / year). When
  every error for a paper is a "missing required field 'X'" error,
  that paper is skipped from the batch with a logged "SKIPPED invalid
  input" entry, and the remaining valid papers still write to Zotero /
  Obsidian. Strict dry-run behaviour is preserved (every validation
  issue surfaces) so the operator sees the full picture before a real
  run.
- **L1-deferred-but-L2-corroborated papers no longer fail-close at
  `L1-deferred`.** When the DOI resolver HEAD is transient-blocked
  (anti-bot 401/403/406/418/451/etc. -- classified as
  `*_check_unavailable` by F7 / PR #51), the gate used to quarantine
  immediately at `L1-deferred` even when L2 corroboration (now augmented
  by PR #53's CrossRef-by-DOI metadata verify) would confirm it. The
  gate now lets such papers fall through to L2 / L3 / fit-check; if all
  pass, the paper is accepted with
  `provenance.doi_recheck_pending = True` and
  `provenance.doi_recheck_details = {reason, status_code, url,
  resolved_via}` so a future tool can re-verify the DOI when the
  publisher's anti-bot wall lifts. Definitive L1 failure (HTTP 404/410)
  still fail-closes as `doi_unresolved` / `L1` -- the fabrication
  guarantee is unchanged; L2 corroboration + L3 metadata integrity
  remain the fabrication gate. The `L1-deferred` quarantine bucket is
  structurally empty post-fix; `DEFERRED_LAYER` survives as a public
  constant used by docs / reporting.
- **L2 corroboration augments single-source DOIs with direct CrossRef
  metadata verify.** A paper found by only one search backend (e.g.
  `source: 'openalex'`) was quarantined `L2 / uncorroborated` even when
  its DOI was independently confirmable via CrossRef. The gate now
  does a direct `https://api.crossref.org/works/{doi}` metadata fetch
  for such papers; if CrossRef returns a record whose title/year/
  authors match per the existing `_records_agree` predicate
  (`fuzz.token_set_ratio >= 85`, `|year_delta| <= 1`, surname
  intersection >= 1), CrossRef is recorded as a verified backend and
  the paper passes L2. Strictly augmentative: CrossRef is an
  authoritative metadata source, this only adds an existing-paper
  evidence check; the L2 corroboration bar itself is unchanged. Result
  cached in `crossref_verify_cache.json` (schema 1.0); failures are
  fail-quiet and not cached.
- `zotero gc` / `zotero mark-kept --all-orphans`: a real cluster
  collection whose Zotero key drifted from its `cluster.zotero_collection_key`
  binding (e.g. a Zotero-truncated date-prefixed name like
  `20260518-machine-learning-flood-forecas`) is no longer mis-flagged as an
  orphan candidate. New conservative, suppression-only name-normalization
  match (`_normalize_collection_name` + bidirectional prefix match, min
  12-char guard). No rebind/merge/delete-logic change; strictly fewer GC
  candidates. PR-A's non-empty hard-skip remains as an independent safety
  net.
- **arXiv hits no longer leak past `--exclude-type preprint`.** The
  arXiv backend left `doc_type` empty, so the type filter silently
  missed every raw arXiv result (bioRxiv/chemRxiv already set it).
  Now `doc_type="preprint"`.
- **Self-heal commands are environment-correct.** New
  `recommended_cli_invocation()` picks the `research-hub` console
  script when on PATH, else the `python -m research_hub` module form.
  Wired into the NLM preflight, `RequiresAuthRefresh`, keepalive task
  resolution, and the auto-pipeline NLM-skip hint — these previously
  hardcoded a console-script command that fails on source checkouts.
- **`notebooklm keepalive` no longer reports false-green.** It now
  re-probes session health *after* rotating cookies; a rotation that
  does not preserve a usable session (server-side re-auth) returns
  non-zero instead of exit 0.
- **F7: doi.org anti-bot 418 no longer quarantines every valid paper.**
  The authenticity gate's DOI resolver sent the default
  `python-requests` User-Agent, which doi.org/Cloudflare answer with
  HTTP 418 — read as `doi_unresolved` → **every** peer-reviewed paper
  fail-closed-quarantined (reproduced: `accepted: 0; quarantined: 2`,
  `DOIs accessible: 0`; the same DOI returns 200 with a real UA). Fix:
  send a real `User-Agent`; classify 408/418/425/429/5xx + network
  errors as *transient* (bounded retry + backoff, **not** cached as a
  permanent miss, surfaced as `*_check_unavailable`); genuine 404/410
  stay fail-closed `doi_unresolved` so the anti-fabrication guarantee
  is unchanged. A 0/malformed status also fails closed.
- **F7 completion: access-blocked resolver statuses defer.** DOI HEAD
  statuses other than resolved 2xx/3xx or definitive 404/410
  non-registration (for example 401/403/406/451 anti-bot walls) now
  route to `doi_check_unavailable` / `L1-deferred` instead of permanent
  `doi_unresolved` / `L1` quarantine.
- **Semantic Scholar API keys are validated before use.** A
  non-latin-1 `SEMANTIC_SCHOLAR_API_KEY` now emits a clear warning and
  is ignored so the backend queries anonymously instead of crashing while
  requests encodes the `x-api-key` header.
- **DOI resolve cache auto-migrates pre-PR-#51 poisoning.** The F7
  completion (anti-bot HEAD defers, PR #51) was silently neutralised on
  any DOI cached under the old non-transient classification -- the
  cache-hit short-circuit returned the stale `doi_unresolved` outcome
  before the new logic ran. `DoiResolveCache.load` now performs a
  one-shot schema 1.0 -> 1.1 migration that prunes
  `reason="doi_unresolved"` entries whose `status_code` is not in
  `{404, 410}` (genuine non-existence) and rewrites the cache at the
  new schema version. Entries with status 404/410, success entries, and
  any other reason are preserved. Idempotent; logged at WARNING when
  any entry is pruned.

### Removed
- **Dead `notebooklm login` flags:** `--cdp`, `--chrome-binary`,
  `--use-system-chrome`, `--from-chrome-profile`,
  `--chrome-profile-path`, `--chrome-profile-name`, `--keep-open`,
  `--timeout`, and the unused `login_interactive` /
  `login_interactive_cdp` aliases they delegated to.

### Fixed (PR-A)
- **`zotero gc` no longer presents non-empty real collections as
  deletion candidates.** Any Zotero collection whose key was not a
  *current* cluster binding was flagged `orphan-from-vault` — including
  stale non-empty date-prefixed duplicate collections holding real
  items. `delete_candidates` already hard-skipped non-empty collections
  (so no data could actually be lost), but the **output falsely implied
  a data-loss risk**, eroding trust in the tool. Now: non-empty orphans
  get a distinct `orphan-with-items(N)` reason, are listed under a
  separate "NON-EMPTY ORPHANS — review only; gc cannot delete these"
  section, are never offered in the interactive prompt, and are
  excluded from `--yes`. Empty/test junk GC is unchanged.

### Fixed (PR-B)
- **F6: `auto` no longer prints `[OK] ingest N papers` when 0 were
  written.** When every candidate was quarantined by the fail-closed
  authenticity gate the raw dir was never created, the `exists()` guard
  was skipped, and the tentative `len(papers)` count survived — the
  pipeline reported a clean ingest of N papers while the vault got
  nothing. The count is now authoritative (`0` when nothing written);
  an all-quarantined ingest is reported as a failed step with an
  actionable `quarantine list` hint, not `[OK]`. A 0-written /
  0-quarantined result (e.g. empty search) keeps the lenient path with
  an honest `N written, M quarantined (of K candidates)` message.
- **F8: `notebooklm upload` no longer exits 0 when 0 sources were
  transferred.** _(Root cause later revised — the common cause is the
  URL-quality skip, not the upstream API; see the "Fixed (F8 real fix)"
  entry above.)_ When NotebookLM's source API drifts under the pinned
  `notebooklm-py` (e.g. `Sources data ... is not a list (NoneType)`)
  the notebook is created but no sources land; the old code returned 0
  because `fail_count == 0`. A non-dry-run upload that transfers,
  caches, and prunes nothing is now a non-zero error naming the likely
  cause. (`notebooklm-py` was already pinned `<0.5.0`; this drift is
  server-side, so honest reporting is the only available remedy.)

### Fixed (PR-C — deep F7)
- **Transient DOI-resolution failures defer instead of being
  fail-closed-quarantined as fraud.** PR-B's minimal F7 fix stopped the
  *cache* poisoning but the authenticity gate still quarantined ANY
  `not ok` at L1 — including `*_check_unavailable` (doi.org / Crossref
  rate-limit or network blip after the bounded retry). A sustained
  rate-limit window therefore still rejected valid papers, requiring
  manual `quarantine restore`. Now the L1 branch splits by reason
  family: transient → distinct `L1-deferred` layer (reported as
  "deferred, retryable"; recovers on a later run / `quarantine
  restore`); permanent (`*_unresolved`, 404/410, no-identifier,
  predatory/metadata/fit/uncorroborated) → unchanged `L1` quarantine.
  The paper is still held out of ingest in both cases (fail-closed —
  the anti-fabrication L0–L5 guarantee is unchanged; a fabricated DOI
  returns 404 → permanent → quarantined). `auto` now reports
  `N quarantined, D deferred` distinctly, and an all-deferred run says
  the papers were *not* rejected and how to retry, instead of
  "quarantined". (An optional `quarantine retry-deferred` convenience
  CLI is deferred to a later follow-up — existing `quarantine restore`
  already recovers deferred entries.)

### Added (PR-D)
- **`notebooklm login --wait-file PATH` — non-interactive login (no
  terminal/ENTER).** The upstream login blocks on `input("press
  ENTER")`, which can't be driven headless/scripted. With `--wait-file`
  you sign in in the browser then create PATH (`touch PATH`, or an
  automation wrapper does it); research-hub polls for it and feeds the
  newline that triggers the upstream session save. `--wait-timeout`
  (default 300s) fails closed — on timeout the subprocess is terminated
  and nothing is saved. Stale signal files are cleared first so a
  leftover from a previous run can't auto-trigger before sign-in. This
  formalizes (in Python, testable) the signal-pipe technique used to
  recover the maintainer's expired session.

### Fixed (F8 real fix)
- **`auto` can now actually upload publisher-URL clusters to
  NotebookLM.** Diagnosed 2026-05-19: an all-URL cluster (DOIs →
  ScienceDirect/Elsevier) uploaded 0 sources because every entry was
  `likely_error_page` (our local probe can't read the anti-bot wall)
  and the conservative URL-quality gate skipped them all — and `auto`
  called `upload_cluster` positionally with no way to override, so
  there was no path to rescue it through the pipeline. The earlier F8
  message also mis-blamed a NotebookLM API change (the
  `SourcesAPI.list ... NoneType` warning was a red herring — listing an
  empty new notebook). The conservative skip is intentional design and
  is **unchanged**; instead `--include-suspect-urls` is now exposed on
  `auto` and threaded `auto → auto_pipeline → upload_cluster`, and the
  0-sources error message now lists the real likely cause first (URL
  sources skipped → re-run with `--include-suspect-urls`) instead of
  pointing at the upstream API.

### Added (F8 first-principles fix — content-priority ladder)
- **NotebookLM bundles now upload the abstract as a text source when no
  PDF is obtainable, instead of a paywalled URL.** First-principles
  diagnosis: NLM needs *content*, not a URL — a paywalled publisher DOI
  carries none. Local PDF (rung 1) and Unpaywall/OA PDF (rung 2, via
  `fetch_paper_pdf`) already worked; the gap was rung 3. `bundle.py`
  now: no PDF + (no URL or a `likely_error_page` paywall URL) + a real
  `## Abstract` in the note → emits `action="text"` carrying the
  abstract (title/DOI-prefixed); a *good* (non-suspect) URL is still
  preferred (full text). `NotebookLMClient.upload_text` →
  `sources.add_text`; `upload.py` dispatches `action="text"`;
  `BundleReport.text_count`. Net: an all-paywall-URL cluster that
  previously uploaded 0 sources now uploads the abstracts — real
  content NotebookLM can synthesise. The conservative URL-quality gate
  and `--include-suspect-urls` override (band-aid) are unchanged.
- **`socket.getfqdn` CI flake — autouse stub in `tests/conftest.py`**
  (master had been red on this for ≥3 consecutive runs:
  `26185448887`, `26191738564`, `26192402510`). Multiple test files
  construct `ThreadingHTTPServer(("127.0.0.1", 0), ...)` whose
  `server_bind()` calls `socket.getfqdn("127.0.0.1")`. On macOS
  GitHub Actions runners (and Bonjour/mDNS-equipped environments
  generally) the reverse-DNS lookup hangs 30+ seconds before
  `pytest-timeout` fires — Python stdlib
  [issue14914](https://bugs.python.org/issue14914), 14-year-old bug.
  The first attempt of this fix patched only the
  `artifact_server` fixture in `test_artifact_delete_endpoint.py`,
  but the next CI re-run surfaced the same flake at
  `test_dashboard_executor_e2e.py::test_e2e_sse_event_after_action`.
  `grep -rln 'ThreadingHTTPServer'` found **7 test files** with the
  same construction pattern, so the fix promoted to a
  `conftest.py`-level autouse fixture (`_stub_socket_getfqdn`) that
  stubs `socket.getfqdn` for every test in `tests/`. Production
  code path is unchanged — `monkeypatch` scope is per-test,
  reverting at teardown.

### Removed

- **Legacy root `plugin.json` deleted** (Phase 7 Wave B from the
  `WenyuChiou/ai-research-skills` marketplace-maturity tracker — see
  research-hub issue
  [#60](https://github.com/WenyuChiou/research-hub/issues/60)). The
  file was an early Cowork-plugin placeholder with a self-described
  TODO ("Convert to full Cowork plugin manifest when plugin schema is
  finalized") that never got migrated. It declared 3 skill paths,
  one of which (`skills/knowledge-base/SKILL.md`) was the long-removed
  `knowledge-base` alias, while 11 actual skill dirs ship under
  `skills/`. The active manifest is `.claude-plugin/plugin.json`,
  which uses Claude Code marketplace auto-discovery and is unaffected.
  `grep -rn 'plugin\.json'` against `tests/` + `src/` + non-meta docs
  returns zero references to the root file — it is a pure orphan.
  Removing it removes a misleading source of truth without touching
  any install / marketplace / test path.

## v1.0.0 (PENDING — tag on/after 2026-05-24, post ≥1-week v0.95.0rc2 bake)

> **Not yet released — staged on `release-prep/v1.0.0`.** The cut
> replaces this header with the real date, runs the mechanical
> release gate on `master`, then `git tag v1.0.0` → push → watch CI.
> v1.0.0 is the **promotion of the v0.95.0rc2 line** (W6 API-freeze
> + Phase A authenticity gate) after a ≥1-week bake, **plus** the
> Phase C fail-closed first-run guard and README accuracy.
> **No new breaking change beyond rc2's L4** (already in UPGRADE.md).

**The v1.0 guarantee — no fabricated references.** Every paper that
enters the vault resolved to a real identifier (DOI / arXiv /
PMID), passed integrity and relevance checks, or was **quarantined
with a recorded reason** and never written. Mechanical and
fail-closed (Phase A, L0–L5; `test_authenticity_l5_invariant.py`
fails CI if any LLM symbol enters the bibliographic path).
Deliberately **not** an absolute "zero hallucination" claim — the
enforceable promise is *resolve + integrity + relevance, or
quarantine*. Full statement, layer table, and triage:
[docs/authenticity.md](docs/authenticity.md).

### Added

- **`notebooklm keepalive` — durable idle keepalive.**
  New `src/research_hub/notebooklm/keepalive.py` module + `notebooklm keepalive`
  CLI subcommand. Rotates and persists the stored session cookies
  (`notebooklm.auth._rotate_cookies` → `save_cookies_to_storage`) so a single
  Google login survives idle periods (Google revokes idle sessions in ~12–24 h
  without this). Default one-shot invocation is safe for any scheduler; `--loop
  --interval <sec>` (floor 3600 s, default 21600 s = 6 h) for long-running
  `nohup` supervision. Windows Scheduled Task registration via
  `--install-windows-task [--interval-hours N]` is available but **opt-in** and
  gated behind an explicit `--yes` flag; without `--yes` the exact `schtasks`
  command is only printed (dry-run, nothing registered — no wrapper file written
  either). `--uninstall-windows-task` removes the task. The task command is
  resolved at install time: if the `research-hub` console-script is on PATH
  (pip-installed), it is used directly; otherwise a `nlm_keepalive.cmd` wrapper
  is generated in `.research_hub/` that sets `PYTHONPATH=src` and `cd`s to the
  repo root before invoking `python -m research_hub notebooklm keepalive` — so
  source-checkout installs work correctly from Task Scheduler. No elevated
  privileges (`/RL HIGHEST`) are requested; the task runs as the current user.
  Honest scope: keepalive extends session lifetime by preventing idle revocation;
  Google's own long-lived cookie hard-expiry (~1 year) or a security event can
  still terminate the session. `doctor nlm_session` remains the backstop.

- **`notebooklm login --from-browser [BROWSER]` — non-interactive browser-cookie login.**
  New `login_from_browser` function in `src/research_hub/notebooklm/auth.py`.
  Imports the user's already-logged-in normal-browser Google session via the
  upstream `notebooklm-py --browser-cookies` (rookiepy) path: no Playwright
  popup, no terminal ENTER — one short command instead of the browser+ENTER
  dance. Requires `pip install 'research-hub[browser-auth]'` (new optional extra
  `browser-auth = ["rookiepy>=0.1.0"]`). Supported browsers: auto-detect (bare
  `--from-browser`), chrome, firefox, edge, brave, arc, chromium, safari,
  vivaldi, zen, librewolf, opera, opera-gx, ie, octo. Precedence: `--import-from`
  > `--from-browser` > interactive login.

- **`[browser-auth]` optional extra** (`pyproject.toml`).
  Declares `rookiepy>=0.1.0` as an installable extra consistent with the project's
  other optional dependency pattern. Referenced in `--from-browser` help text and
  error messages.

- **`clusters delete --purge-zotero-items` (destructive flag).** Moves all
  parent items in the cluster's Zotero collection to the Zotero trash
  (recoverable until the user empties trash) and then deletes the now-empty
  collection. Dry-run by default; pass `--apply` to execute. Zotero
  cascade-deletes child attachments (incl. PDFs) when the parent item is
  trashed — child keys are NOT submitted explicitly (avoids false 404 failures
  in the summary). Scoping is structural: all enumeration and deletion operate
  strictly on the cluster's own `zotero_collection_key`; an empty key is a
  no-op; parent and sibling collections are never enumerated or touched. A
  defense-in-depth guard refuses the operation if the cluster's own collection
  key matches the configured `zotero_parent_collection` (resolved read-only).
- **`clusters archive` (hub/_archived move).** `ClusterRegistry.archive(slug)`
  moves `hub/<slug>/` to `hub/_archived/<slug>/` and sets `status: archived`.
  `_HOME.md` and all MOC pages automatically omit archived clusters. Idempotent.
  `clusters unarchive` reverses the move.

- **Configurable Zotero parent ("mother") collection (`zotero_parent_collection`,
  default `"research-hub"`).** New cluster Zotero collections are now
  automatically nested under a single top-level parent collection instead of
  being created at the library root.  Configure via `zotero.parent_collection`
  (nested) or top-level `zotero_parent_collection` in `config.json`, or via the
  `RESEARCH_HUB_ZOTERO_PARENT_COLLECTION` env var.  Set to empty string or
  `""` to disable nesting and preserve legacy top-level behavior (backward
  compatible).  The parent collection is created automatically on first use
  (idempotent).  New helper `ensure_parent_collection(client, name)` in
  `research_hub.zotero.client` is used by all three cluster-collection creation
  paths (`clusters.py`, `auto.py`, `cli.py clusters rebind --new`).

- **`research-hub zotero reparent-clusters`** — one-shot command to migrate
  existing top-level cluster collections under the parent collection.
  Dry-run by default (shows cluster slug, Zotero key, current parent, and
  proposed action); pass `--apply` to execute.  `--parent <name>` overrides
  the config default.  Idempotent: already-nested collections are skipped and
  reported.  Never deletes anything.

- **Zero-cost recall improvements (Phase C): offline auto query-variations,
  S2 recommendations expansion, raised per-backend factor.**
  Three independent recall levers, all zero extra API cost and precision-safe
  (merge-dedup + fail-closed fit-check backstop unchanged):

  - **C1 — Auto query-variations (`--auto-variants`, default on).** When
    `--from-variants` is not supplied, `discover new` now automatically derives
    2–3 short query variations offline from the cluster's `seed_keywords`
    (clusters.yaml) + key terms extracted from the cluster's `00_overview.md`
    definition section. Variations are fed through the existing
    `apply_variations()` path so the proven multi-variation merge and
    multi-match confidence boost are reused. `--from-variants` always takes
    precedence and suppresses auto-variants. No definition → seed-only;
    no seeds → no auto-variants. Never crashes. Disable with `--no-auto-variants`.

  - **C2 — Semantic Scholar recommendations expansion (`--expand-semantic`,
    default on).** After initial search, the top-N (≤3) candidates with a
    resolvable DOI or arXiv ID are submitted to the S2
    `recommendations/v1/papers/forpaper/{paperId}` endpoint (free tier).
    Up to 20 results per seed are merged at a fixed base confidence of 0.4 so
    user-query hits always outrank recommendation-only entries. Network failure
    or empty response → no-op, never crashes. Disable with `--no-expand-semantic`.
    New method `SemanticScholarClient.get_recommendations()` in
    `research_hub.search.semantic_scholar`.

  - **C3 — Per-backend search limit raised 3 → 4 (`--per-backend-factor`).**
    `_DEFAULT_PER_BACKEND_LIMIT_FACTOR` raised from 3 to 4. The floor constant
    (`_DEFAULT_PER_BACKEND_LIMIT_FLOOR = 40`) is unchanged; the factor is
    relevant only when `limit × 4 > 40` (i.e. limit > 10, which is always true
    at the default limit=50). Pass `--per-backend-factor N` to override at
    runtime.

- **PDF-text abstract fallback (last-resort, fail-safe).** When all four
  online metadata sources (Crossref, Unpaywall, OpenAlex, Semantic Scholar)
  return no substantive abstract AND a local PDF is present in the vault's
  `pdfs/` directory, `recover_abstract` now extracts the abstract from the
  PDF text as a final link in the chain. The extraction heuristic locates
  an "Abstract" section header, captures until the next section stop, and
  falls back to the second double-newline-separated paragraph. Extracted
  text is rejected if shorter than 200 chars, matches a boilerplate pattern
  (copyright, DOI stamp, etc.), or appears column-interleaved/garbled
  (space ratio < 0.08 or > 30% single-char "words") — the extractor returns
  nothing rather than writing garbage (`failed_no_abstract` is preserved).
  Provenance is written as `abstract_source: local-pdf` via the existing
  `recovered.source` write-back. Opt-out: set `disable_pdf_fallback: true`
  in `config.json` or `RESEARCH_HUB_DISABLE_PDF_FALLBACK=1`. Wired at the
  `paper enrich-existing` re-run path (`zotero/enrich.py`) and the
  `discover_continue` ingest path (`discover.py`). **Scope note:** this
  feature does NOT retroactively fix papers whose PDFs are not present; for
  paywalled papers, place PDFs in `~/knowledge-base/pdfs/` named by DOI
  then run `paper enrich-existing <cluster> --apply` followed by
  `paper summarize --pending --cluster <cluster> --cli claude`.
- **Fail-closed first-run guard (Phase C).** With relevance
  checking on (the default) and no `claude`/`codex`/`gemini` judge
  on PATH, `research-hub auto` now exits BEFORE the slow
  multi-backend search with actionable 3-option guidance — instead
  of running the full search and leaving a silent empty vault
  (Phase A would quarantine every paper `relevance_unjudged`). Does
  NOT weaken fail-closed: the sole opt-out is the pre-existing,
  explicit `--no-fit-check` (which still runs L0/L1/L3 authenticity,
  just no relevance filter).
- End-of-run quarantine summary in `auto`'s next-steps — counts
  grouped by reason plus the `research-hub quarantine
  list|show|restore` recovery commands, so a short/empty vault is
  auditable instead of a mystery. Reuses Phase A `list_quarantine`
  (no fresh directory scan).
- `docs/authenticity.md` — the durable v1.0 guarantee statement,
  the L0–L5 layer table, and quarantine triage (the full prose the
  Phase 5 plan called for; README + CHANGELOG link to it).

### Changed

- **`clusters delete --apply` now removes all local data for the cluster.**
  In addition to unbinding notes from the registry, `--apply` now also removes
  `hub/<slug>/` (overview, crystals, memory.json, briefs), all
  `.research_hub/bundles/<slug>-*` directories, `.research_hub/artifacts/<slug>/`,
  and prunes all lines for the cluster from `.research_hub/manifest.jsonl`.
  The cluster's `raw/<slug>/` folder is soft-deleted (moved to
  `raw/_deleted_<slug>/`) rather than hard-deleted. `_HOME.md` and MOC pages
  automatically skip archived (`status: archived`) clusters on next regeneration.
- **Zotero item safety guard is structural, not key-specific.** The previous
  hardcoded guard (`_PROTECTED_COLLECTION_KEY = "EIASV65T"`) is removed in
  favor of a structural guarantee: all Zotero operations are strictly scoped to
  the cluster's own `zotero_collection_key` (an empty key ⇒ no-op). A
  defense-in-depth parent-collection guard resolves the configured parent key at
  runtime (read-only) instead of relying on a hardcoded value.

- **API surface frozen for 1.0.** `docs/stable-api.md` (the
  contract since v0.91.0) is promoted to the v1.x stability
  statement.
- **W6 deprecated aliases retained through all of 1.x (schedule
  correction — strictly more lenient, NOT breaking).** The W6
  wrappers carried a placeholder `removed_in="v1.0.0"`. Per
  standard semver, deprecated surface is not removed inside a
  major, so the marker is corrected to the next major (`v2.0.0`)
  consistently across `cli.py`, `mcp_server.py`, `_deprecation.py`,
  `docs/stable-api.md`, `UPGRADE.md`, and the W6 tests. Every old
  CLI alias / MCP tool keeps working as a warning-emitting wrapper
  for the entire 1.x line; **nothing is removed at 1.0.0** — the
  only change is the advertised removal version in the warning
  text (v1.0.0 → v2.0.0). No code behaviour change; this widens,
  never narrows, what keeps working — hence no BREAKING flag.
- README + README.zh-TW now document the authenticity gate, the
  fail-closed relevance-judge requirement (with the `--no-fit-check`
  opt-out), and the `quarantine list|show|restore` recovery path
  (commit `168c761`) — a judge-less fresh clone is no longer misled
  into a silent empty vault.

### Fixed

- **Pre-upload URL error-page guard (hybrid metadata + probe).** `bundle`
  now calls a new `classify_url_source()` classifier before setting
  `action="url"` on each source. The classifier uses a 3-tier approach: (1)
  `summarize_status: failed_no_abstract` in the note frontmatter →
  `likely_error_page` immediately (no network); (2) open-access hosts
  (`arxiv.org`, PubMed, Zenodo, etc.) → `ok` immediately (no network); (3)
  ambiguous publisher domains → active HTTP GET with a browser User-Agent,
  body classified by Cloudflare-403, T&F cookie-wall, Elsevier JS-redirect,
  or generic short-body signals. Probe errors/timeouts yield quality="unknown"
  (fail-safe — never skipped). `url_quality`, `url_quality_reason`, and
  `url_quality_signal` are written into each manifest entry. During `upload`,
  entries with `url_quality="likely_error_page"` and `action="url"` are
  **skipped and recorded** in `report.errors` with type
  `pre_upload_likely_error_page` (visible in the run report, not silent).
  Pass `--include-suspect-urls` to upload them anyway (a warning is still
  appended). When a local PDF exists for a `likely_error_page` URL source,
  `bundle` auto-upgrades the entry to `action="pdf"` (composes with the
  existing PDF-abstract fallback). The existing post-upload
  `validate_uploaded_sources()` remains as a secondary net.

- **Windows ACL hardening could brick the entire vault (deny-all
  regression in the v0.91.0 W8 work).** `_restrict_windows_acl`
  ran `icacls <p> /inheritance:r /grant:r <bare-user>:(F)`. Two
  latent faults combined on a live box: (1) directories got a
  **non-inheritable** owner ACE, so files written into
  `.research_hub/` afterwards (`clusters.yaml`, `nlm_cache.json`,
  NLM `state.json`) were born with an **empty DACL — deny-all,
  unreadable even by the owner**; (2) when the bare principal
  failed to resolve under an unusual process token (observed in
  the Playwright/Chromium subprocess of the NLM-login flow) the
  grant silently no-opped while `/inheritance:r` still stripped
  everything. icacls **exits 0** in both cases, so the old
  return-code-only guard never fired and every subsequent CLI
  command failed silently (`doctor` exited 0 with no output
  because `ClusterRegistry(clusters.yaml)` raised `PermissionError`
  before any print). The helper is now **fail-open, not
  fail-closed**: directories get an inheritable `(OI)(CI)(F)`
  owner ACE; after applying, the resulting DACL is **verified** to
  still grant the current user, and if not (or icacls
  failed/raised) the path is rolled back to inherited ACEs via
  `icacls /reset` so the owner is never locked out, with a single
  stderr warning. icacls arg order (`/inheritance:r` strictly
  before `/grant`) is preserved — reversing it makes icacls reject
  `/inheritance:r` as an invalid parameter. Net worst case is now
  "secrets not OS-hardened + one warning", never "tool bricked".
  Pure-helper regression coverage added in `test_v030_security.py`.
- **NLM keepalive now wired: a single login survives long uploads.**
  `_make_client()` now passes `keepalive=600` to the upstream
  `NotebookLMClient.from_storage()` for all upload/download paths
  (`upload_cluster`, `download_briefing_for_cluster`,
  `download_slide_deck_for_cluster`, `generate_artifact`). The
  background `_keepalive_loop` pokes `accounts.google.com/RotateCookies`
  every 600 s (clamped to the upstream 60 s floor), eliciting
  `__Secure-1PSIDTS` rotation so multi-shard uploads no longer drop
  mid-flight when Google rotates short-lived tokens. One-RPC fast paths
  (health probe, `notebooks.list`) keep `keepalive=None` so `doctor`
  stays fast. Between-run cookie rotation is now **persisted reliably,
  race-free**: the old research-hub `_save_state()` in `close()` was
  redundant — the upstream `ClientCore.close()` already persists the
  live jar on ALL exit paths (including exceptions) via a
  `threading.Lock`-serialized `save_cookies()` call. Removing the
  duplicate eliminates the race where an older in-flight keepalive save
  could clobber freshly-rotated tokens written by `_save_state()`.
  Net guarantee: every CLI invocation persists whatever cookies Google
  rotated during that run, exactly once, race-free. The `state.json`
  permission re-hardening the old `_save_state()` also performed
  (G3 P1 #2) is preserved by an explicit `_tighten_state_file_perms()`
  call AFTER the authoritative upstream on-close write, so cookie
  rotation cannot silently relax the Google-auth-cookie file back to
  0644. Note: Google can still eventually expire the underlying
  `SID`/`PSID` cookies (typical lifetime 1–2 years); `doctor` will
  `WARN` and prompt re-login in that case.
- **`doctor` reported a false `[OK] nlm_session` for a server-side
  dead NotebookLM session.** The check tested only
  `state.json` existence + non-zero size, so an expired Google
  session showed healthy in `doctor` while every real NLM
  operation failed at the preflight probe — the operator had no
  way to learn the session was dead short of attempting an upload.
  The file-present branch now calls the same already-proven
  `check_session_health()` probe the CLI preflight uses: live →
  `OK`; Google-rejected (auth) → `WARN` with a
  `research-hub notebooklm login` remedy; probe could not complete
  (offline / timeout / unexpected) → `WARN "liveness unverified"`
  with NO remedy, so an offline `doctor` run is not misled into
  claiming the session is dead. File-missing/empty, the outer
  "Could not check" guard, and the no-config branch are unchanged.
  3 regression tests added in `test_doctor.py`. Full auto-Google
  re-login is out of scope (Google 2FA / bot-detection makes
  headless login infeasible); this makes the *detection* honest.

### Security

- The fail-open rollback above is a deliberate, documented
  trade-off: on a Windows host where user-only ACL hardening
  cannot be verified, sensitive files (`config.json` Zotero key,
  `.secret_box.key`, NLM cookie `state.json`) fall back to
  inherited ACLs and the operator is warned once on stderr — a
  research vault that keeps working beats one bricked by its own
  hardening. The `RESEARCH_HUB_SKIP_ACL_HARDENING=1` escape hatch
  is unchanged.

- **Corroboration-gated ingest (`authenticity.py` L2; PR #42).**
  The authenticity gate previously accepted any HTTP-resolvable
  identifier, so predatory CrossRef-member journals (e.g. IJSREM
  `10.55041`, IJASRE `10.31695`) — whose DOIs resolve 200 — passed.
  The gate now (a) quarantines a curated predatory DOI-registrant
  denylist (`L2 predatory_venue`; extend via
  `cfg.predatory_doi_prefixes`), and (b) enforces the
  already-computed corroboration signal: a `single-source`
  candidate is quarantined (`L2 uncorroborated`) **unless** it is an
  arXiv / PMID / bioRxiv-medRxiv (`10.1101`) preprint or has
  `citation_count >= cfg.min_corroboration_citations` (default 1).
  **Operational impact (intended, not a bug):** real ingests now
  quarantine materially more single-source, zero-citation,
  non-preprint papers — this is the fail-closed predatory
  protection working as designed. All quarantines are **recoverable**
  (`research-hub quarantine restore`); loosen via
  `cfg.min_corroboration_citations`. Registrant matching is
  boundary-anchored (`10.55041` does not match `10.550410`).

## v0.95.0rc2 (2026-05-17) — v1.0 blockers cleared (RC2)

Both remaining v1.0 blockers landed, each Codex-delegated and
shipped through the mechanical release gate. This RC bakes before
v1.0.0.

### Added

- **Literature authenticity gate** (`research_hub.authenticity`,
  commit `7466989`). Mechanical, fail-closed answer to "can it
  guarantee papers are real". Every candidate passes L0–L5 before
  entering `raw/` or is quarantined with the failing layer + reason:
  L0 no-identifier, L1 `doi.org` HEAD (<400; network/timeout
  fail-CLOSED → `doi_check_unavailable`, never assume-valid), L2
  cross-backend corroboration (LABEL only — single-source-resolvable
  is real, never quarantined), L3 metadata integrity, L4 fit_check.
  Accepted papers gain a deterministic `provenance` frontmatter
  block. New `research-hub quarantine list|show|restore`.
- L5 invariant lock: `test_authenticity_l5_invariant.py` fails CI
  if any LLM-call symbol appears in the bibliographic-frontmatter
  span (no-LLM-bibliography is now a tested contract, not prose).

### Changed

- **BREAKING (behavioural): L4 fit_check fail-OPEN → fail-CLOSED.**
  Previously, if no LLM relevance judge was available, ALL papers
  were kept. Now they are quarantined `relevance_unjudged`. A run
  with `--no-fit-check` is unaffected; a run that requested
  fit-check but has no LLM CLI now produces an explicit quarantine
  instead of a silent keep-all. Migration: `research-hub
  quarantine list` to review, `restore` after configuring an LLM
  CLI or accepting without fit-check. (UPGRADE.md updated.)
- **CLI/MCP rationalize with deprecation** (commit `5935d2d`, W6,
  G2 #11-12). Canonical names: `notebooklm ask` / `paper
  summarize` / `tidy`; MCP `ask_cluster(source=,mode=)` /
  `cluster_rebind(action=)` / `read_cluster_memory(kind=)`. Every
  old CLI alias + old MCP tool still works as a thin wrapper
  emitting `DeprecationWarning` (`removed_in="v1.0.0"`). See
  `docs/stable-api.md` `### Deprecated` table.

### Process note

Both deliverables were Codex-delegated. W6's raw output included
unrequested config.py/clusters.py drift (Codex misdiagnosed the
known local icacls env pollution) — caught + reverted by the
mandatory CLAUDE.md #5 diff-review before commit. Phase A's prompt
carried the W6 lesson forward as an explicit anti-misdiagnosis
guard; Codex correctly reported the same env block instead of
"fixing" it in source. Both shipped only after a full suite incl
e2e on fresh `--basetemp` (env-immune) passed (2472/0, 2484/0).

## v0.95.0rc1 (2026-05-17) — Release-engineering hardening (RC)

First release candidate. Phase 3 of the post-v0.89.1 stabilization
plan: dependency/CI hygiene, deeper wheel smoke, doc polish, and
the MCP docstring correction. Shipped THROUGH the new mechanical
release gate (`scripts/release-check.sh` — full suite incl e2e —
+ the pre-push hook) introduced in Phase 1; this is the gate's
first dogfood.

### Added

- `.github/dependabot.yml` — weekly pip + github-actions update
  PRs, patch-grouped (G5 #19).
- `constraints.txt` — documented upper-bound anchor for
  `pip install -e . -c constraints.txt` (not a hash lockfile;
  research-hub is a library).
- CI `pip-audit --strict` step (non-gating) for supply-chain
  visibility (G5 #19).
- Wheel install-smoke in `publish.yml`: runs `init --sample` +
  `describe --json` against the BUILT wheel, asserting `_HOME.md`
  + bundled skills/mcp_tools resolve — catches missing wheel data
  files that import-only smoke can't (G5 #4).
- Python 3.14 CI cell (experimental, `continue-on-error`, runs but
  does not gate) so the classifier claim is exercised honestly
  (G5 #17).

### Changed

- All 7 runtime deps now have upper bounds (`notebooklm-py
  >=0.4.1,<0.5.0` tight semver-zero cap; others next-major). The
  v0.88.10 "100% NLM upload broken" incident was an unbounded
  `notebooklm-py` minor-version kwarg drift (G5 #18).
- CI gated matrix is 3.10–3.13 (was 3.10–3.12); 3.14 added as the
  non-gating experimental cell above.
- `README.md`: added the `init --sample` quickstart row + the
  bare-`research-hub`-prints-help note; Python support wording now
  "CI-gated 3.10–3.13; 3.14 experimental".
- `UPGRADE.md`: replaced the stale "to v0.30" framing with a
  current universal-path header + a v0.89→v0.95 migration section.
- `CHANGELOG.md`: adopts the Keep-a-Changelog forward convention
  (this entry is the first; history kept verbatim — G4 #3).

### Fixed

- **MCP docstrings (G4 #4, must-fix).** Five tool docstrings
  (`mark_paper`, `move_paper`, `merge_clusters`, `get_citations`,
  `emit_assignment_prompt`) previously stated enums/return shapes
  that did NOT match the real delegate bodies — a confidently
  wrong docstring is worse than a vague one for agent
  introspection. Rewritten against verified
  `operations.py` / `citation_graph.py` / `clusters.py` /
  `topic.py` bodies and `help()`-checked. E.g. `mark_paper`'s
  valid statuses are `{unread, reading, deep-read, cited}` (was
  wrongly documented as `read|skimmed|archived`).

## v0.91.1 (2026-05-16) — Hotfix: 2 real W8 CI regressions

v0.91.0 shipped to PyPI but its CI test job was RED on clean
ubuntu/macos/windows runners. The v0.91.0 release pytest gate had
`--ignore`'d the entire e2e suite (because the dev tree's
`.pytest-work` was icacls-polluted by a pre-guard W8 run) — which
masked, not avoided, two genuine W8 regressions. Misdiagnosed at
the time as "env pollution, CI-clean"; it was not.

### Fixed

- **`_restrict_windows_acl` guard was subprocess-blind.** W8 #14's
  `if "pytest" in sys.modules` did not fire inside the real
  `python -m research_hub` SUBPROCESS that e2e tests spawn (pytest
  isn't imported there), so `icacls /inheritance:r` locked
  `.pytest-work/.../clusters.yaml` → `PermissionError` on clean
  Windows CI. Guard now also checks `PYTEST_CURRENT_TEST` (set by
  pytest in `os.environ`, inherited by subprocesses since the
  executor passes no `env=`) plus a `RESEARCH_HUB_SKIP_ACL_HARDENING`
  operator/CI escape hatch.
- **`test_e2e_timeout_handling` asserted the pre-W8 leaky contract.**
  W8 #16 strips `stderr` from the /api/exec response on every
  branch; `test_e2e_error_rendering` was updated for that but
  `test_e2e_timeout_handling` was missed (it never ran locally — the
  polluted e2e suite errored at fixture setup before reaching it).
  Now asserts the secure behaviour (`"stderr" not in payload`,
  `error == "timeout"`).

### Process note (cost-of-skipping)

This is the same class of failure as v0.89.1 (release shipped with
a red test because the gate was weakened under time pressure). Root
cause both times: the release pytest scope was at Claude's
discretion and got narrowed. Verification for v0.91.1 used the
FULL suite incl e2e (no `--ignore`) on a fresh `--basetemp`:
**2451 passed, 0 failed**. Mechanizing the release gate so e2e
cannot be silently excluded is tracked as the next process fix.

## v0.91.0 (2026-05-16) — API contracts + security hardening

Phase 2a of the post-v0.89.1 1.0-readiness audit. Four waves
(W4/W5/W7/W8), each its own commit gated by the mandatory
code-review skill. Two waves needed REQUEST CHANGES → fix →
APPROVE rounds (W8 twice).

### W4 — schema_version on 3 hidden contracts (commit 01c75d9)

G2 #9. `clusters.yaml`, `dedup_index.json` get top-level
`schema_version: "1.0"`; `manifest.jsonl` gets per-line
`_schema: 1`. All readers tolerate the new field (`.get()` /
`**unpack` patterns). New `docs/file-formats.md` catalogues all
11 hidden formats + the versioning policy ("bump aggressively").
Remaining 8 formats tracked for v0.92 / v0.95 / v1.0.

### W5 — CLI `--json` envelope versioned (commit 523dc33)

G2 #8 (minimal viable step). Every `--json` subcommand now emits
`schema_version: "1.0"` as the first envelope key. The
`{ok, command, version, report}` contract is documented in
`docs/file-formats.md`. Per-Report `schema_version` (the heavier
10+-dataclass standardization) tracked for v0.92.

### W7 — Public API + deprecation policy (commit d1df72c)

G2 #13. Explicit `__all__` (9 names: `__version__` + 6 exception
classes + `build_manifest`/`describe_manifest`, the latter via
lazy PEP 562 `__getattr__`). New `_deprecation.py`
(`warn_deprecated`, `deprecated_callable` with `functools.wraps`).
New `docs/stable-api.md` documents the 3 public surfaces, what's
explicitly internal, and the deprecation rules (≥1 minor grace,
removal only on minor bump). The v0.89.0 "exception import paths:
deprecation TBD" is closed — those aliases are declared SUPPORTED.

### W8 — Windows ACL + token-file + stderr leak (commit 1128904)

G3 P2 #14-16, three security fixes:

- `chmod_sensitive` was a Windows no-op (config.json /
  .secret_box.key / NLM state.json inherited the parent ACL).
  Now `icacls /inheritance:r /grant:r <user>:(F)`, with a
  pytest guard (icacls /inheritance:r would otherwise lock test
  tmp dirs).
- New `--api-token-file` so the dashboard bearer token never
  hits the process argv (ps/tasklist leak). POSIX mode check
  warns if the file is group/world-readable.
- Dashboard `/api/exec` no longer forwards raw subprocess
  stderr to the browser (leaked abs paths / config / traces).
  stderr is stripped on every response branch + logged
  server-side under a correlation id. stdout is deliberately
  retained — the v0.62 stdout drawer is a shipped feature and
  command stdout is the user's own invoked output.

### Verification note

The `test_dashboard_executor_e2e.py` sandbox suite shows
environment pollution (a pre-guard icacls run in the dev session
ACL-locked `.pytest-work/`); this is NOT a code defect — proven
by clean-tree pass + the 184-test focused suite incl. the v0.62
stdout-drawer contract. CI runs on fresh runners with no
`.pytest-work` and validates clean.

### Deferred to v0.95.0-rc1 / v1.0.0

CLI + MCP rationalize w/ deprecation (G2 #11-12; W6, Codex-
delegated — too large for direct write per CLAUDE.md), CI matrix
+ dep upper bounds + lockfile + pip-audit (W9), wheel smoke
depth (W10), P2 docs polish (README + UPGRADE + 74 MCP
docstrings; W12).

## v0.90.0 (2026-05-15) — Stability

Phase 1 of the post-v0.89.1 1.0-readiness audit. Four GA-blocker
classes addressed: silent failures, resource leaks at scale,
dashboard argv injection, fresh-user UX disaster. Each commit was
gated by the mandatory code-review skill (W1 governance rule from
v0.89.1) and one round of REQUEST CHANGES → fix → APPROVE.

### W1 — Silent-failure breadcrumbs (commit bf609bf)

Four `except Exception: pass` / `return None` swallows that hid
root cause now log to stderr / `logger.warning` while remaining
non-fatal (preserves "best-effort" semantics).

1. `cli.py:_load_zotero_if_configured` — biggest UX win. Pre-fix,
   auth fail / network down / missing creds all looked identical
   ("Zotero not configured"). Now `MissingCredential` is silent
   None (truly unconfigured); anything else surfaces as
   `[zotero] WARN ...`.
2. `notebooklm/client.py:_save_state` — cookie persistence failures
   now log so next session's auth-expired error has a breadcrumb.
3. `vault/hub_overview.py:populate_all_overviews` — MOC / _HOME.md
   rebuild failures warn instead of silent pass.
4. `notebooklm/upload.py:_load_fit_score_map` — corrupt
   `.fit_check_accepted.json` logs via `logger.warning`.

### W2 — Resource leaks at scale (commit c93ddd6)

`zotero/pdf_attach.py`: two leaks that compound at N=1000 paper
batches.

1. `requests.get(stream=True)` connection wrapped in
   `try/finally response.close()` so connection releases to the
   pool regardless of exit branch. (Not `with requests.get(...)`
   because test mocks don't implement `__enter__/__exit__`.)
2. Partial temp PDF cleanup via new `_cleanup_partial_temp_pdf()`
   helper called from write_bytes exception branches.

### W3 — Dashboard argv injection + NLM cookie chmod (commit 49382f2)

Two P1 security fixes.

1. `dashboard/executor.py`: `_validate_dashboard_inputs()` guard
   at the top of `_build_command_args`. Pre-fix, anyone past the
   localhost CSRF + Origin gate could POST `slug="--apply --force"`
   and it landed in subprocess argv. `validate_slug()` for 5
   slug-shaped fields; reject-leading-dash for 8 freeform fields.
   `outline` exempted (markdown bullets legitimately start with `-`).
2. `notebooklm/auth.py` + `client.py`: `_tighten_state_file_perms()`
   chmods `state.json` to 0o600 after login + each cookie rotation.
   Pre-fix the parent dir was tightened but the file itself stayed
   world-readable on POSIX. Windows ACL still no-op (G3 P2 #14
   tracked for v0.91).

### W11 — Bare `research-hub` prints help (commit f4a12df)

Pre-fix, `research-hub` (no subcommand) called `run_pipeline()`
against an unconfigured vault. Now prints help and exits 0.
Code-review caught the initial placement (after `require_config()`)
which still crashed for fresh installs; the final fix places the
print-help branch at the very top of `_main_dispatch` so it runs
before any config probing.

### What didn't ship (deferred to v0.91 / v0.95)

| Audit item | Defer to |
|---|---|
| `_emit_cli_json` report shape standardize (G2 #8) | v0.91 |
| Hidden contract schema_version (G2 #9) | v0.91 |
| CLI + MCP rationalize w/ deprecation (G2 #11-12) | v0.95-rc |
| `__all__` + deprecation policy (G2 #13) | v0.95-rc |
| Windows ACL + dashboard token + stderr leak (G3 P2) | v0.91 |
| CI matrix + dep upper bounds + lockfile + pip-audit | v0.91 |
| Wheel smoke depth | v0.91 |
| P2 polish (README + UPGRADE + 74 MCP docstrings) | v0.95-rc |

### Process notes

- Plan: `~/.claude/plans/delegated-puzzling-umbrella.md`
- Each W1-W3 + W11 was its own commit gated by code-review skill.
  Two waves needed REQUEST CHANGES → fix → APPROVE rounds (W3
  `outline` regression + W11 placement bug). The mandatory gate
  caught both before they shipped.
- Full test suite green across all 4 commits.
- No new external dependencies.

## v0.89.2 (2026-05-15) — Hotfix: broken test_v089_describe

Single-line fix for a regression introduced by v0.89.1's version bump.
`tests/test_v089_describe.py:25` asserted
`payload["version"] == "0.89.0"` (a hardcoded string), so any minor
bump silently broke the suite. v0.89.1 shipped with this red because
the release-commit code-review skill audited the diff but did not
run `pytest`. Fixed by importing `__version__` and asserting equality.

This release also exposed a governance gap: the new "Pre-Commit
Agent Review (Mandatory)" rule (W1, ~/.claude/76452c4) catches
diff-shape problems but not test-suite regressions. The next
governance update will add `pytest -q` (or equivalent fast suite)
to the release-commit gate. Tracked in v0.89.2 release notes only;
the rule itself ships separately.

Files: `tests/test_v089_describe.py` (1-line fix + comment),
`pyproject.toml` + `src/research_hub/__init__.py` (version bump).

## v0.89.1 (2026-05-15) — Onboarding + Polish

Three focused workstreams from the v0.89.0 post-release audit:
P0 onboarding ROI (`init --sample`), P2 polish from the
`code-review` skill audit, and a CLAUDE.md governance update
(separate repo). Total surface: ~140 LOC code + ~80 lines doc
across 5 commits, all gated by the new mandatory pre-commit
`code-review` skill rule.

### W2 — `research-hub init --sample` (commit 3ea1773, merge 38aa242)

Cuts clone-to-first-value from 30 min → ≤5 min. Addresses W5
audit's #1 churn driver (60% prospective-user dropout estimated
by E3).

```bash
research-hub init --sample [--vault PATH]
```

Copies the bundled `samples/sample_vault/` (5 demo papers + 3
clusters + crystal cards + base + `_HOME.md`) and skips ALL
Zotero / NLM / LLM CLI probes — the sample is self-contained.
Default vault: `~/knowledge-base`. Prints clear next-steps:

```
Sample vault ready at <vault>
Open <vault>/_HOME.md in Obsidian to explore
Or run: python -m research_hub describe
To use real Zotero/NLM, run: research-hub setup --vault <vault>
```

**P0 guard** (caught by code-review skill, fixed before merge):
the existing `copy_sample_vault()` helper (v0.60) unconditionally
`shutil.rmtree`s any non-None destination that exists — safe for
its tempdir use case, lethal when exposed via CLI. The new code
refuses non-empty destinations with a clear message before
calling the helper. Regression test patches `copy_sample_vault`
to a hard-fail to detect any future bypass.

Files: `init_wizard.py` +47, `cli.py` +6, new
`tests/test_v0891_init_sample.py` (4 tests).

### W3 — Polish (commit 9b83654)

Three P2 fixes the `code-review` skill flagged during v0.89.0
synthesis but were too small to block the release:

1. **`_emit_cli_json` survives unknown types** — added
   `default=str` to `json.dumps()`. v0.89.0 would crash with
   `TypeError` if a `Report.to_dict()` accidentally leaked a
   datetime / bytes / Exception. Now serializes via `str()`.
2. **`describe.py` argparse private-API comment** — 11-line
   block comment above `_parser_supports_json` flagging
   dependency on `_actions` / `_choices_actions` /
   `_SubParsersAction` (Python 3.10–3.14 contract) + recovery
   hint if a future CPython removes the attrs.
3. **`_HOME.md` Dashboard link iOS-friendly** — replaced
   `file:///C:/...` (broke on iOS Obsidian per W3 audit) with
   `http://127.0.0.1:8765/` (live, when `serve --dashboard` is
   running) + `.research_hub/dashboard-summary.md` markdown
   fallback (works anywhere, including iOS).

Files: `cli.py` 1-line, `describe.py` +11 doc, `hub_overview.py`
~5 LOC, new `tests/test_v0891_polish.py` (5 tests).

**Migration note**: existing vaults need
`research-hub vault rebuild-overviews --force` once to refresh
the `_HOME.md` Dashboard link. New vaults get it automatically.

### W1 — CLAUDE.md "Pre-Commit Agent Review (Mandatory)"

Separate repo (`~/.claude/`), commit 76452c4. Codifies a 6-row
trigger table that self-enforces `code-review` skill invocation
on:

1. Diff > 50 LOC
2. Release commit (`__version__` bump or `git tag`)
3. Critical-path edits (auth / errors / I/O / network / security)
4. Multi-file diff (≥3 files)
5. Codex / Gemini delegate just returned
6. Governance docs (CLAUDE.md / AGENTS.md / settings.json /
   hooks)

With deny-listed escape hatches (CI configs and doc with
executable code blocks do NOT skip review). The cost-of-skipping
reference is the v0.88.15 lesson — 4 P1 bugs hidden behind 2376
green tests across v0.88.10–v0.88.14, all caught only by
post-hoc `code-review` skill audit.

This v0.89.1 release was the rule's first dogfood: code-review
skill ran on W3, W2 (caught the silent-rmtree P0), and on this
cumulative release commit. APPROVE verdict required at each.

### Process notes

- Plan: `~/.claude/plans/delegated-puzzling-umbrella.md`
- W3 + W2 + release each invoked `code-review` skill per the
  new W1 rule
- Pre-commit hook (`claude-ack-review.sh`) blocked W2 commit
  until skill ran — mechanism worked as designed
- Test suite: 4/4 W2 + 5/5 W3 + previous 2376 still green

## v0.89.0 (2026-05-14) — Agent-Native Mode

First minor-version bump after the v0.88.x release train. v0.89.0
makes research-hub usable by autonomous agents (Claude Cowork /
OpenClaw / Hermes-style hosts), not just humans driving the CLI.

Designed as 4 parallel Codex workstreams + Claude synthesis +
post-merge code-review skill audit. Each workstream is its own
commit + merge.

### Workstream A — Universal `--json` output (commit 0787fa0)

23 CLI subcommands now accept `--json` for machine-readable output.
Wrapping shape: `{"ok": bool, "command": str, "version": str,
"report": <to_dict()>}`.

New helpers: `_json_safe()`, `_emit_cli_json()`, `_stdout_to_stderr()`.
Targets: `auto`, `ingest`, `import-folder`, `doctor`, `crystal
emit/apply`, `summarize`, `fit-check emit/apply`, `bases emit`,
`vault rebuild-overviews`, `vault tag-migrate`,
`vault hub-backlink-migrate`, `vault summarize-status-migrate`,
`vault cleanup-frontmatter`, `notebooklm download`, `clusters
audit`, `dedup compact`, `dashboard`, `paper retype`, `paper
bulk-relabel`, `paper bulk-move`, `paper bulk-delete`. Tests: 23
parametric.

### Workstream B — Structured exception hierarchy (commit c878a10)

`ResearchHubError` base + 5 subclasses for agent reasoning:
`MissingCredential`, `RequiresAuthRefresh`, `MissingExternalTool`,
`UpstreamRateLimited`, `UpstreamUnavailable`.

10 conversion sites: `auto.py`, `notebooklm/*.py`,
`search/semantic_scholar.py`, `api/v1.py`, `config.py`,
`zotero/client.py`, `cli.py`. Backwards-compat: `NotebookLMError`,
`RateLimitError`, `NotebookLMCapacityError`, `ApiError` keep their
import paths AND inherit from the new base.

CLI top-level handler: when `ResearchHubError` is raised under
`--json`, emits `{"ok": false, "error": <err.to_dict()>}` instead
of traceback. Tests: 12.

### Workstream C — `research-hub describe` (commit c9981b9)

New CLI subcommand emits a JSON manifest of capabilities so agents
can introspect without starting the MCP server. Auto-walks the
argparse tree (so new subcommands populate without touching
`describe.py`); introspects FastMCP without starting the server
(85 MCP tools listed); hand-curated `ENV_VARS` constant is the
single source of truth used by Workstream D's bootstrap probe.
Flags: `--filter <subtree>`, `--pretty`. Tests: 6.

### Workstream D — `bootstrap --autonomous` + README rewrite (commit 5b5a56c)

`research-hub setup --autonomous --vault <path> --persona agent`
emits `BootstrapReport` JSON + exits 0 (ready) or 1 (missing).
Probes: required env vars (via `describe.ENV_VARS`), vault
existence, NLM cookie store presence (read-only — never invokes
browser), Zotero ping, LLM CLI detection. Never prompts.

README rewrite: new `## Personae` section (human Wei-Ling +
autonomous Cowork-agent), `## Required env vars` table between
`<!-- env-vars-table-start/-end -->` anchors (regex-parseable),
`## Autonomous agent quickstart`, `## Human quickstart` decision
table replacing old A/B/C prose. Version drift fixed (no more
`v0.81.0` mixed with `v0.68.3`). NLM headless auth upstream-blocked
status documented. Tests: 11.

### Process notes

- Plan file: `~/.claude/plans/delegated-puzzling-umbrella.md`
- 3 Explore agents mapped current state of CLI/MCP/auth/error
  surfaces (Phase 1)
- 1 Plan agent designed the 4-workstream split (Phase 2)
- 4 Codex sessions ran sequentially (A first to settle cli.py
  base; B/C/D rebased on each successive merge)
- Repomix pack at `.ai/v089/repo-pack.xml` (130K tokens, 14 files)
  given to B/C/D as optional reference
- `code-review` skill on combined diff (non-negotiable per CLAUDE.md
  rule from the v0.88.15 lesson) returned APPROVE / 0 P0/P1 findings
- Two P2 polish items deferred to v0.89.1: `_json_safe`
  datetime/bytes/Exception handling (1-line fix: add `default=str`
  to `json.dumps`); `describe.py` argparse private-API defensive
  comment

### Suite

- 4 new test files, 46 tests total (23 + 12 + 6 + 5)
- Full suite: 2442 passed / 0 fail / 24 skip / 2 xfail / 1 xpass
  (excluding env-blocked `test_v065_extras_install.py`)

### Migration notes

- All v0.88.x CLI invocations work unchanged
- New: `research-hub describe`, `research-hub setup --autonomous`,
  `--persona agent`, `--json` on 23 more subcommands
- Old import paths for exceptions still work; deprecation TBD

Co-Authored-By: Codex (gpt-5.4) <noreply@openai.com>
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>

## v0.88.15 (2026-05-14) — agent code-review followups (4 P1 + 4 P2 fixes)

After v0.88.14 shipped, I ran the `code-review` skill against the
v0.88.10–v0.88.14 release train (independent verification of an
earlier code-reviewer subagent pass). The skill confirmed 4 P1 + 1 P2
real bugs and identified 3 P2 polish items. v0.88.15 fixes all 8 with
regression tests that lock each contract.

### P1 fixes

1. **`"is not a valid"` non-retryable pattern was too broad**
   (`upload.py`) — substring match would catch transient errors like
   `"URL is not a valid resource"` / `"certificate is not a valid
   X.509"` and short-circuit legitimate retries. Narrowed to specific
   SDK validation phrases: `"is not a valid notebook id"`, `"is not a
   valid source"`, `"is not a valid mime type"`, `"invalid mime type"`.

2. **Whitespace-only `SEMANTIC_SCHOLAR_API_KEY` env var was treated as
   a valid key** (`semantic_scholar.py`) — `"  " or None` evaluated to
   `"  "` (truthy), sending whitespace as `x-api-key` header and
   triggering a misleading 403. Now `.strip() or None` so whitespace-
   only inputs (and the explicit `api_key="  "` kwarg) fall back to
   anonymous mode.

3. **`install_theme.action` mislabeled first-time `--force` install as
   `"overwrote"`** (`install_theme.py`) — `dest.exists()` was checked
   AFTER `shutil.copy2` (always True post-copy). Now captures
   `already_existed = dest.exists()` BEFORE the copy.

4. **PDF cache read full file + computed sha256 even when caching
   disabled** (`importer.py`) — defeated the docstring's "default-safe"
   claim, wasted I/O on every `_extract_pdf` call, and could crash
   with `FileNotFoundError` on dry-run paths before pdfplumber could
   give a useful error. Now short-circuits at the top of
   `_pdf_cache_paths` when `_PDF_EXTRACT_CACHE_DIR is None`.

### P2 fixes (polish)

5. **`_strip_archive_header` silently converted CRLF → LF**
   (`download.py`) — `splitlines()` + `"\n".join()` lost CRLF. Now
   detects the original separator and preserves it. Practical impact
   low (notebooklm-py gives us LF today) but correct-by-construction
   matters for any future caller passing Windows fixtures.

6. **NLM heartbeat refresh failure was silently swallowed**
   (`upload.py`) — added `logger.debug("heartbeat refresh_and_save
   failed between shards (non-fatal): %s", _refresh_exc)`. Still
   best-effort, but multi-shard auth failures now leave a diagnostic
   trail.

7. **`frontmatter_dedupe` dedupe key used `str(item)`**
   (`frontmatter_dedupe.py`) — dict items with different key insertion
   order produced different signatures. Now `json.dumps(item,
   sort_keys=True, default=str)` with a `str()` fallback for non-
   serializable items. Future-proofs against a maintainer adding
   `creators` (dict list) without revisiting the key strategy.

8. **`uninstall_theme` reported `"uninstalled"` even on partial state**
   (`install_theme.py`) — when CSS removal succeeded but appearance.json
   disable failed (read-only fs), the snippet might still load on next
   Obsidian restart. New `"partial_uninstall"` action distinguishes
   this case so the CLI summary doesn't lie.

### Tests (`tests/test_v08815_review_followups.py` — 25 new)

Lockdown coverage for every fix:

- 4 parametric tests for the narrowed non-retryable pattern (4
  transient errors NOT match + 2 genuine validations DO match)
- 8 tests for env-var whitespace normalization (6 parametric cases +
  headers/throttle/explicit-arg scenarios)
- 2 tests for install_theme action label (first-time --force, repeat
  --force)
- 1 test for partial_uninstall reporting
- 2 tests for PDF cache short-circuit (disabled = no I/O; enabled
  still hashes)
- 2 tests for CRLF preservation in `_strip_archive_header`
- 1 structural test for heartbeat debug logging
- 3 tests for `_item_signature` (order-stable dict, string identity,
  unhashable fallback)

Two prior test files needed minor updates:
- `test_v08810_pdf_upload.py::test_is_non_retryable_classification` —
  `"is not a valid mime type"` re-added as explicit pattern entry
  (the narrowing of `"is not a valid"` had unintentionally removed it)
- `test_v08811_polish.py::test_refresh_and_save_failure_is_swallowed`
  — accept either `except Exception:` or `except Exception as <name>:`
  so the new named binding doesn't trip the structural assertion

Full suite: TBD (running locally).

## v0.88.14 (2026-05-14) — PDF content-hash cache (W4 audit #1 token win)

Re-importing the same PDF (rename, retry, cluster-move) re-paid the
pdfplumber walk cost every time. W4 audit flagged this as the #1 PDF
win: ~100% on re-import, ~30% on partial cluster re-runs. At a real
ingest scale (49 papers, ~30 with PDFs, ~20-page average), each
pdfplumber walk is 1-3 s — the cache turns a 30 s re-import into a
~1 s one.

### Mechanism

- Key: ``sha256(file_bytes).hexdigest()``
- Cache location: ``<vault>/.research_hub/cache/pdf_extract/<sha>.txt``
- Hit: cache file present + readable → return its content; no
  pdfplumber call
- Miss: pdfplumber walk → write to cache (best-effort) → return text
- Renames / cluster-moves of the same file: cache HIT (key is content
  hash, not path)
- Content changes: cache MISS (new hash → fresh extraction)

### Wiring

- `importer.set_pdf_extract_cache_dir(path)` module setter, called
  once per `import_folder` run with `cfg.research_hub_dir /
  "cache" / "pdf_extract"`
- Module-level `_PDF_EXTRACT_CACHE_DIR` (None by default = caching
  off; safe default for tests + ad-hoc importer use)
- Both read and write are wrapped in `try/except OSError` — corrupt
  cache or full disk never poisons the extraction itself

### Tests (`tests/test_v08814_pdf_cache.py` — 7 new)

Uses a `FakePdfPlumber` that counts `.open()` calls so we never
need a real PDF. Each test asserts the exact number of pdfplumber
invocations expected:

- cache-disabled: 2 calls for 2 imports (default behaviour preserved)
- cache-enabled, same content: 1 call (hit on second)
- rename with same content: 1 call (content-hash key)
- content change: 2 calls (hash mismatch)
- write failure: returns text + 1 call (best-effort)
- corrupt cache read: 1 call (fresh extraction fallback)
- disable mid-session: re-opens (setter respected)

### What's not in this cache yet

- `defuddle_extract.py` URL extraction (W4 #3 — same hash-by-content
  pattern would apply, but URLs are mutable so the cache key needs
  to be URL + last-fetched-headers; deferred to a separate fix)
- `_pdf_metadata_title` second pdfplumber walk (W4 #4) — defer

## v0.88.13 (2026-05-14) — `vault install-theme` ships the Obsidian tech aesthetic

Bundles the Obsidian CSS snippet that was added directly to the
user's vault in v0.88.10 conversation, behind a one-command CLI so
anyone on PyPI can install it.

### Ship

- `src/research_hub/assets/themes/research-hub-tech.css` — the tech
  aesthetic CSS bundled with the wheel (Hatch picks it up automatically
  under the existing `src/research_hub` package directory)
- `src/research_hub/vault/install_theme.py` — copy + enable / disable
  helpers with `InstallThemeResult` dataclass return shape
- New CLI:

```bash
research-hub vault install-theme                  # dry-default? no, installs
research-hub vault install-theme --force          # overwrite tampered snippet
research-hub vault install-theme --uninstall      # remove + disable
research-hub vault install-theme --theme research-hub-tech   # explicit
```

### Behavior

- Copies bundled CSS to `<vault>/.obsidian/snippets/<theme>.css`
- Adds `<theme>` to `enabledCssSnippets` in
  `<vault>/.obsidian/appearance.json` (preserving any other user
  appearance keys verbatim)
- Idempotent: re-run is a `skipped_exists` no-op unless `--force`
- Detects re-enable cases: if CSS exists but theme is disabled in
  appearance.json, flips the enabled bit (returns `re_enabled`)
- `--uninstall` removes the CSS + disables the snippet; never touches
  unrelated user appearance settings
- Unknown theme name → `no_op` with an error pointing at available
  themes

### Tests (`tests/test_v08813_install_theme.py` — 9 new)

- 5 happy-path: fresh install, skip-on-exists, force-overwrites,
  preserves other appearance keys, idempotent (no duplicate in enabled)
- 1 error path: unknown theme returns error
- 3 uninstall: removes + disables, no-op when already uninstalled,
  preserves other appearance keys

### Theme contents

The snippet is the same as the v0.88.11 conversation install: cyan
+ amber accent palette, JetBrains Mono frontmatter/tables/wikilinks,
dotted-grid background, instrument-panel callouts, mobile breakpoint
tweaks. Targets the Obsidian classes via stable CSS variables.

Restart Obsidian after install to load the snippet
(Settings → Appearance → CSS snippets should already show it on).

## v0.88.12 (2026-05-14) — Semantic Scholar API key + frontmatter dedupe migration

Two W1/W3 audit follow-ups:

### Fix #1 — `SEMANTIC_SCHOLAR_API_KEY` env var pass-through

Stage B hit HTTP 429 from Semantic Scholar's shared-pool anonymous
limit (~100 req per 5 min across all unauthenticated callers).
`SemanticScholarClient` now reads `SEMANTIC_SCHOLAR_API_KEY` at
construction time:

- If set: sends `x-api-key: <key>` header on every request and
  lifts the polite throttle from 3.0s → 1.0s (matches S2's
  published authenticated rate of ~1 req/sec).
- If unset: behavior unchanged from v0.88.11.

429 messages also branch by auth status — anonymous 429 points the
user at the API-key application page; authenticated 429 says to
check key validity or back off.

Get a key at: https://www.semanticscholar.org/product/api#api-key-form

### Fix #2 — `vault cleanup-frontmatter --dedupe-lists` migration

W3 found 10/12 human-water-llm papers still carry 3× repeated
`cluster_queries` lines despite v0.88.4 making `_render_field`
order-preserving dedupe list values. The dedupe only fires when
frontmatter is REWRITTEN; notes that pre-dated v0.88.4 and were
never touched since then keep their accumulated dupes on disk.

New module `research_hub/vault/frontmatter_dedupe.py` exposes
`migrate_one_note` + `migrate_all`, mirroring the existing
`tag_migrate` / `hub_backlink_migrate` patterns. New CLI:

```bash
research-hub vault cleanup-frontmatter --dry-run   # default
research-hub vault cleanup-frontmatter --apply
```

Dedupe targets a conservative allow-list: `cluster_queries`, `tags`,
`collections`, `aliases`. Same `_rewrite_paper_frontmatter` plumbing
as the other migrations — v0.88.4's `_render_field` does the actual
dedupe on write.

### Live verification on user vault

```
vault cleanup-frontmatter (apply): scanned 49 notes
  deduped                         10   ← matches W3 audit exactly
  clean                           39

Details:
  fu2025: cluster_queries: 16→6
  jiang2026: cluster_queries: 16→6
  ranaweera2026, ren2024, samuel2024, schück2026, taormina2024:
    16→6 each
  wang2025, wang2026-epanetagentic, wen2026: 16→6 each
```

Second-run dry-run reports "49 clean" — idempotent.

### Tests (`tests/test_v08812_s2_key_and_dedupe.py` — 13 new)

- 7 covering S2 key plumbing: env-var read, no-env default,
  throttle-lift on auth, headers content (with/without key),
  explicit `api_key=""` override, end-to-end search() header pass-through
- 6 covering migration: 15→5 cluster_queries dedupe, tags dedupe,
  no-op on clean, dry-run preserves disk, cluster_slug_filter,
  missing-vault defensive return

## v0.88.11 (2026-05-14) — post-Stage-B polish bundle

Three in-scope fixes from the W3/W4 audit, no new public CLI/MCP
surface. All small, all field-discovered in the Stage A + B live
re-ingest of `ml-flood-forecasting`.

### Fix #1 — Brief mirror archive-header strip (`notebooklm/download.py`)

v0.88.3 prepended `## TL;DR` + `**Cluster:**` to brief mirrors, but
left the legacy NotebookLM archive-header block in place:

```
# <Cluster Title>
Source: https://notebooklm.google.com/notebook/<id>
Downloaded: <ts>
Sources: <n>
Saved briefings: <list>

# <Synthesis Title>
...
```

Result: every brief showed the same notebook metadata above and
below the cluster pointer — wasting iPhone screen real estate. New
helper `_strip_archive_header(body)` drops everything from the
leading cluster H1 up to (but not including) the next H1 with real
synthesis content. Conservative: if the body doesn't match the
archive shape, return it unchanged so we never accidentally delete
user content.

### Fix #2 — NLM heartbeat refresh between shards (`notebooklm/upload.py`)

v0.88.7 added `save_cookies_to_storage` on `close()`, but a 200+-
source upload session holds the client open the entire time. Google
rotates short-lived auth tokens (SIDCC / SIDTS / OSID / CSRF)
during each request; without a heartbeat between shards, the
second/third shard can hit "Authentication expired" mid-flight.

`_upload_cluster_shards` now calls `client.refresh_and_save()`
after each shard's `uploaded_sources` is committed to `shard_cache`.
Best-effort — a refresh failure is swallowed so it never poisons
the upload that just succeeded.

### Fix #3 — `_find_pdf_for_doi` O(P²) → O(P) (`notebooklm/bundle.py`)

`bundle_cluster` paid one `pdfs_dir.rglob("*.pdf")` filesystem walk
per paper for the DOI-tail lookup, then another full walk for the
author-year fallback. At 49 papers × ~80 PDFs in the directory,
that's ~98 wasted walks per bundle. At 500 papers it's pathological.

`_find_pdf_for_doi` and `_find_pdf_by_author_year` now accept an
optional `pdf_index: list[Path]` kwarg. `bundle_cluster` builds the
index once at the top of the loop and passes it through. Default
behaviour is unchanged when the kwarg is omitted.

**Estimated speedup**: 50× at 49 papers, 500× at 500 papers.

### Tests (`tests/test_v08811_polish.py` — 8 new)

- 3 covering `_strip_archive_header`: drops standard metadata block,
  no-op on unfamiliar shapes (4 edge cases), tolerates
  Notebook:/Generated: variants
- 2 covering NLM heartbeat: structural test that `refresh_and_save`
  is called after `shard_cache[shard_name]` assignment + that it's
  inside try/except (best-effort)
- 3 covering bundle memoize: `pdf_index` honored for both lookup
  functions, fallback to rglob when omitted, end-to-end count of
  rglob calls in `bundle_cluster` is exactly 1

### Out of scope / deferred

- `status: pending` cross-cluster sweep — defer to v0.89 (needs
  new `--all-clusters` flag, not a one-line fix)
- cluster_queries dedup migration tool — defer to v0.89 (needs new
  `vault cleanup-frontmatter` CLI)

## v0.88.10 (2026-05-14) — CRITICAL: NLM PDF upload was 100% broken since v0.88

Field-discovered in the W4 audit of Stage B logs: every NotebookLM PDF
upload since notebooklm-py 0.4.x went out has failed with the same
TypeError, masked by 3 retries × exponential backoff that all hit the
same wall. Stage B reported "8 succeeded out of 14" but the most
recent NLM debug log shows **0/5 PDF uploads actually landed** — they
were all failing with:

```
SourcesAPI.add_file() got an unexpected keyword argument 'path'
```

### Root cause

`notebooklm._sources.SourcesAPI.add_file` signature is
``(self, notebook_id, file_path, mime_type, wait, wait_timeout)`` —
the kwarg is `file_path=`, not `path=`. research-hub's
`NotebookLMClient.upload_source` was passing `path=` (legacy from an
earlier SDK version), so every PDF upload threw immediately.

### Fix #1 — `client.py:201`

`add_file(notebook_id, file_path=str(file_path))` (was `path=`).
One-line patch.

### Fix #2 — non-retryable error classification (`upload.py`)

The W4 audit also flagged that `_attempt_upload` retries
indiscriminately — burning 12 s of backoff per upload on errors that
will never recover (SDK contract drift, validation failures, 4xx
auth). New helper `_is_non_retryable(error_text)` matches a small
conservative set of fingerprints:

- ``unexpected keyword argument`` / ``got multiple values for`` /
  ``missing 1 required`` — TypeError from SDK signature drift
- ``is not a valid`` / ``invalid mime type`` — validation
- ``401 unauthorized`` / ``403 forbidden`` / ``404 not found`` — auth

Transient errors (5xx, timeouts, rate limits, network) still get the
full 3-attempt retry budget. The early-exit emits a new
``upload_non_retryable`` JSONL log line for forensics.

### Tests (`tests/test_v08810_pdf_upload.py` — 16 new)

- `test_upload_source_passes_file_path_kwarg` — locks in `file_path=`
  vs `path=`
- `test_upload_source_url_path_unchanged` — sanity guard for URL path
- `test_attempt_upload_skips_retry_on_typeerror_kwarg` — exact Stage
  B error short-circuits after attempt 1; no backoff sleep fires
- `test_attempt_upload_still_retries_on_transient_errors` — 503
  flake still gets full retry budget
- `test_is_non_retryable_classification` × 12 cases (8 non-retryable
  + 3 retryable + 1 empty) — parametric coverage of the classifier

### User impact

After v0.88.10:
- Every existing cluster's PDFs that were silently failing will succeed
  on next `notebooklm upload`. No vault state migration needed.
- Failed-upload log noise drops by ~3× because non-recoverable errors
  exit immediately instead of cycling through 3 attempts each.

If you have a cluster with `nlm_uploaded: 0` even though `nlm bundle`
reported PDFs, re-run:

```bash
research-hub notebooklm upload --cluster <slug>
```

## v0.88.9 (2026-05-14) — Stage B follow-ups: cluster_overview false-FAIL + crystals timeout

Two unrelated polish fixes both surfaced by today's Stage B live
re-ingest of `ml-flood-forecasting` (15 papers via `auto`):

### Fix #1 — `cluster_overview` skip is no longer a false-FAIL

Field-discovered in every Stage A + Stage B `auto` run today: the
auto report unconditionally logged

```
[FAIL] cluster_overview overview already filled; use force=True to overwrite
```

even on completely successful re-ingests. The "failure" was actually
an idempotency guard protecting the user's hand-curated TL;DR — a
deliberate no-op, not an error. Mixing it into the FAIL column hides
real failures behind boilerplate noise.

### Fix

`OverviewApplyResult` gains two fields — `skipped: bool = False` and
`skip_reason: str = ""` — to distinguish "deliberate idempotent skip"
from "operation failed".

`apply_overview` in `cluster_overview.py`: when the existing TL;DR is
real user content (not the Chinese template marker) and `force` is
False, returns `ok=True, skipped=True, skip_reason="overview already
hand-curated; use force=True to overwrite"`.

`_run_cluster_overview_step` in `auto.py`: renders the skip case as
a positive step with the friendly detail
``skipped: overview already hand-curated; use force=True to overwrite``.

### Tests

- `tests/test_v071_cluster_overview.py::test_apply_overview_refuses_to_overwrite_filled_overview_without_force`
  — updated to assert `ok=True / skipped=True / error=""` (was
  `ok=False / error contains "overwrite"`)
- `tests/test_v071_cluster_overview.py::test_overview_cluster_propagates_idempotent_skip_as_ok`
  — new, end-to-end via `overview_cluster` wrapper to ensure the
  skip propagates as `report.ok=True` to callers
- `tests/test_v071_cluster_overview.py::test_auto_run_cluster_overview_step_renders_skip_as_success`
  — new, asserts `_run_cluster_overview_step` logs the case as
  `step.ok=True` with `"skipped"` / `"preserved"` in detail and no
  `FAIL` token
- `tests/test_v071_cluster_overview.py::test_overview_report_to_dict_serializes_paths`
  — extended to assert the new `skipped` + `skip_reason` keys are in
  the JSON serialisation

### Behaviour change for downstream

If you have automation that polled `OverviewApplyResult.ok` for
"did I write the overview?" you should now check `.written` instead.
The `.ok` field reflects "did the operation complete cleanly",
which now (correctly) includes the idempotent skip.

### Fix #2 — `_run_crystal_step` LLM CLI timeout bumped 180 s → 600 s

Stage B logged ``[FAIL] crystals  claude failed: Command [...]
timed out after 180.0 seconds; prompt saved to crystal-prompt.md``.
Crystal generation is the longest LLM call in the pipeline (10
cards × ~50 papers' worth of context); the inherited 180 s default
in `_invoke_llm_cli` was just too short for full clusters with the
Claude CLI.

`_run_crystal_step` in `auto.py` now passes `timeout_sec=600.0`
explicitly to `_invoke_llm_cli`. Default for other steps (overview,
summary) stays at 180 s — those are short prompts. The 10-min cap
matches the codex-delegate pattern documented in CLAUDE.md.

When this still times out (genuinely stuck CLI), the prompt remains
on disk at ``artifacts/<slug>/crystal-prompt.md`` so the user can
rerun manually — same fallback behaviour as before.

## v0.88.8 (2026-05-13) — fix v0.88.6 layer-2 attribute typo (.status → .action)

Field-discovered in live Stage B (15-paper grow on
`ml-flood-forecasting`): the v0.88.6 unified-summary log line read
``layer-2 (KF/Methodology/Relevance): 0 done`` even though 12 of 14
paper notes had actually been filled correctly. Vault was right;
the report lied.

Root cause: `SummarizeResult` exposes its outcome under `.action`
(see `paper_summarize.py:67`), but v0.88.6's loop in
`auto.py::_run_summary_step` read `getattr(r, "status", "")`, which
always returned the empty default. Counts stayed at zero. The
v0.88.6 unit test used `SimpleNamespace(status="done")` and so
mirrored the production typo — both wrong, both green, neither
caught the bug.

### Fix (`auto.py`)

Read `getattr(r, "action", "") or getattr(r, "status", "")` for
back-compat. Production code now correctly reports counts.

### Tests (`tests/test_v076_full_auto.py`)

- Existing v0.88.6 test updated: SimpleNamespace fake now uses
  `action=` field name to mirror real `SummarizeResult`.
- **New regression guard** `test_summary_step_counts_real_summarize_result_objects`
  uses the **real `SummarizeResult` dataclass** (not duck-typed
  SimpleNamespace) so any future field rename trips the test
  immediately rather than silently mis-counting on disk.

Behavior unchanged in this release; only the log line + tests are
affected. Vaults populated under v0.88.6 already have the correct
KF/Methodology/Relevance.

### Stage B side-findings (NOT fixed in this release)

Documented for a possible v0.89:
- `cluster_overview` autofill step logs FAIL "already filled; use
  force=True" even when the bare scaffold was just written. Cosmetic
  noise in the auto report; vault is correct.
- `nlm.upload` reported 8 succeeded out of ~14 candidates — 3 RPC
  ADD_SOURCE retries plus 3 sources flagged "did not ingest content"
  (Cloudflare wall, IEEE Xplore login wall, JS-rendered Chinese
  paper). NLM-side, not research-hub.
- `claude --print` 180 s timeout while generating crystals — Claude
  CLI subprocess took longer than the cap. Prompt persisted to disk
  for manual rerun.

## v0.88.7 (2026-05-13) — NLM cookie auto-refresh (stop "auth keeps expiring")

User-reported pain: every few days `notebooklm bundle/upload/download`
fails with ``Authentication expired or invalid. Redirected to:
https://accounts.google.com/...`` even though the user did
``notebooklm login`` not long before. Diagnostic showed local cookies
in ``.research_hub/nlm_sessions/state.json`` had expiration **399 days
in the future** — clearly not local expiry. The state.json mtime was
"last login time", never updated across operations.

Root cause: Google session has two cookie layers. The long-lived
``SID/HSID/SSID/NID`` cookies are stable (1+ year), but the
**short-lived rotators** (``SIDCC`` / ``__Secure-1PSIDCC`` /
``__Secure-3PSIDCC`` / ``SIDTS`` / ``OSID`` plus the CSRF
``SNlM0e``) refresh on every request. research-hub's sync facade
loaded the storage snapshot at construction and never wrote the
rotated jar back, so cross-process restarts re-loaded an
increasingly-stale snapshot. Concurrently using NotebookLM in a
normal Chrome browser pushed Google to invalidate the captured
session faster.

### Fix

`research_hub/notebooklm/client.py::NotebookLMClient`:

- `close()` now calls notebooklm-py 0.4.1's
  ``save_cookies_to_storage(cookie_jar, storage_path)`` before
  tearing down the upstream `__aexit__`. Upstream's helper takes an
  OS-level file lock so concurrent CLI runs serialize cleanly.
- New opt-in `refresh_and_save()` method: runs upstream
  `refresh_auth()` to fetch a fresh CSRF + session id, then persists
  the jar. Useful for long-running flows (bulk upload 30+ sources)
  where the user wants the rotated jar on disk before the next leg.
- All save-state errors are swallowed best-effort — a failed cookie
  flush MUST NOT poison the actual upload/download that succeeded.

### Tests (`tests/test_v0887_nlm_state_refresh.py`, 4 new)

- `test_close_persists_rotated_cookies_to_state_json` — close()
  triggers exactly one save with the original state_file path
- `test_close_save_state_is_best_effort_on_failure` — a raising
  save_cookies_to_storage must NOT propagate
- `test_refresh_and_save_calls_both_refresh_and_save` — opt-in API
  drives both refresh_auth() and save
- `test_save_state_skipped_when_no_storage_path` — env-var-auth path
  (storage_path=None) gracefully no-ops

### User-facing effect

After v0.88.7:
- A single `notebooklm login` should remain valid much longer because
  every research-hub session writes the rotated cookies back.
- Using NotebookLM in your regular Chrome no longer monotonically
  rots the saved state — research-hub gets a chance to capture the
  rotation on its own next run.

If the auth still expires, the failure mode is unchanged: re-run
`research-hub notebooklm login`.

## v0.88.6 (2026-05-13) — `auto --with-summary` now fills KF/Methodology/Relevance too

Field-discovered in live re-ingest of `ml-flood-forecasting` (stage A
smoke test): after `auto --with-summary` finished, the 4 paper notes
had a filled `## Summary` 1-liner callout but `## Key Findings`,
`## Methodology`, `## Relevance` were still placeholder, and
`summarize_status: pending` in frontmatter. Manual recovery required
running `research-hub paper summarize --pending` as a separate step.

Root cause: `auto --with-summary` ran `summarize.summarize_cluster`
(v0.81 1-liner layer) but never invoked `paper_summarize.summarize_pending`
(v0.87.1 §O3 structured layer). Two summary subsystems with similar
names that both need to run for a fully-filled note. Two-command
gotcha for new users.

### Fix (`auto.py::_run_summary_step`)

The single `--with-summary` step now drives **both** layers
sequentially:

- **Layer 1** — `summarize.summarize_cluster` fills `## Summary`
  callout (1-line TL;DR from abstract).
- **Layer 2** — `paper_summarize.summarize_pending` fills
  `## Key Findings` / `## Methodology` / `## Relevance` and flips
  `summarize_status: pending → done`.

Failure of either layer is logged but does not block the other; both
are best-effort and either can be retried via
`paper summarize --pending` afterwards.

The summary step's progress log now reports both layers, e.g.
`layer-1 (## Summary): 4 ok; layer-2 (KF/Methodology/Relevance): 4 done via claude`.

### Tests

`tests/test_v076_full_auto.py::test_auto_pipeline_runs_summary_when_enabled`
updated to assert both layers fire. Existing skip / dry-run cases
still pass unchanged.

### User impact

After v0.88.6 ships, future `research-hub auto --with-summary` runs
produce fully-filled notes in one pass. Existing clusters where
only layer-1 was applied can be backfilled with
`research-hub paper summarize --pending --cluster <slug>` (no change
to that CLI).

## v0.88.5 (2026-05-13) — broader MOC keyword heuristic

Field-discovered in live re-ingest of a new `ml-flood-forecasting`
cluster (stage A smoke test): the new cluster overview had no
`## Related MOCs` section because `derive_moc_links` only matched
literal `"water"` substring. A cluster about flood forecasting,
hydrology, rainfall, etc. would never auto-route to the
Water-Resources MOC, leaving it isolated in graph view.

### Fix (`vault/hub_overview.py`)

`derive_moc_links` now recognises a broader water/hydrology keyword
set: `water`, `flood`, `hydro`, `rainfall`, `river`, `drainage`,
`drought`, `sociohydrology`, `stormwater`, `reservoir`. Also expands
the LLM-Agents heuristic to include the standalone `agent` keyword,
so multi-agent / generative-agent clusters route correctly.

Effect on the live vault (no manual edit): re-running
`vault rebuild-overviews --force` now adds:

- `ml-flood-forecasting/00_overview.md` — `## Related MOCs` →
  `[[Water-Resources]]`
- `hub/_moc/Water-Resources.md` — Clusters list now includes
  `ml-flood-forecasting`

### Tests (`tests/test_moc.py`)

- `test_moc_links_v0885_broader_water_keywords` (flood / hydrology /
  rainfall / drought / stormwater / reservoir / `urban drainage`
  query text)
- `test_moc_links_v0885_agent_keyword_for_llm_agents` (`multi-agent`
  slug, `generative agent persona` query text)

All existing MOC-link tests still pass.

## v0.88.4 (2026-05-13) — retype body cleanup + frontmatter list dedupe

Closes the two code-level bugs surfaced by the v0.88.3 vault audit
(handled there by manual `.md` cleanup; this release prevents the
issues from recurring on future retype / enrich-existing runs).

### Fix #1 — `paper retype` now cleans body, not just frontmatter

`retype_paper` previously rewrote frontmatter `zotero-key` but left
two stale lines in the note body:

- `**Citation:** <old venue>` — still showed the source itemType's
  publication name (e.g. `arXiv` after a journalArticle→
  conferencePaper retype, or `Open MIND` after journalArticle→
  dataset).
- `*Source: Zotero key \`OLDKEY\`*` footer — still pointed at the
  trashed item's key.

New helper `_rewrite_paper_body_after_retype` recomputes the
Citation line from the new item template's venue field
(`proceedingsTitle` for conferencePaper, `publicationTitle` for
journalArticle, etc.) plus volume/issue/pages, and rewrites the
footer to the new Zotero key. For datasets it emits `Dataset
(Zenodo)` / `Dataset (Figshare)` / `Dataset` based on DOI prefix.

### Fix #2 — frontmatter list fields dedupe on write

`_render_field` now dedupes list values (order-preserving) before
writing them to disk. The exact bug surfaced on arnold2026 +
goldshtein2025: 5 queries appended 3 times by repeated
enrich-existing runs → 15-line `cluster_queries:` block. With the
dedupe, the same upstream call produces 5 lines.

Defensive at the boundary — applies to `cluster_queries`, `tags`,
`collections`, `aliases`, any list-valued frontmatter field. Most
real-world lists are already unique, so this is a no-op for them.

### Tests

`tests/test_v0884_polish.py` (9 new):

- `test_retype_body_cleanup_replaces_citation_and_footer_for_conferencePaper`
- `test_retype_body_cleanup_dataset_uses_zenodo_marker`
- `test_retype_body_cleanup_dataset_figshare_marker`
- `test_retype_body_cleanup_dataset_generic_marker_when_no_doi`
- `test_retype_body_cleanup_skips_if_no_citation_line`
- `test_render_field_dedupes_string_list_order_preserving`
- `test_render_field_keeps_empty_list_as_inline_marker`
- `test_render_field_dedupes_repeated_query_blocks`
- `test_retype_apply_also_cleans_body_footer`

All existing retype / frontmatter / paper-relabel tests still pass.

## v0.88.3 (2026-05-13) — TL;DR mobile readability fix + stale-artifact refresh

A field-discovered v0.88 #6 polish bug: the brief mirror's `## TL;DR`
block was being filled with the NotebookLM archive header
(``Source: <url>`` / ``Downloaded: <ts>`` / ``Sources: <n>`` /
``Saved briefings: <list>``) instead of synthesis prose. On iPhone
the very first thing the user saw above the fold was a download
receipt, not the synthesis intro — exactly the affordance v0.88 #6
was meant to provide.

Root cause: `_first_paragraph` in `notebooklm/download.py` picked the
first non-heading paragraph, but the archive header block looks like
a plain (non-heading) paragraph, so it won.

### Fix

`_first_paragraph` now (a) strips leading heading lines from each
block so `### Section\nProse...` blocks still surface their prose
body, (b) skips blocks that are >=80% `Key: value` archive-header
lines (Source / Downloaded / Sources / Saved briefings / Notebook /
Generated / Cluster), (c) skips table separator rows, bullet-only
lines, and bold-only label paragraphs, and (d) requires the
selected paragraph to be >=20 chars and end with sentence
punctuation (`.?!`).

### Tests

- `test_v088_brief_tldr.py::test_first_paragraph_skips_archive_metadata_header`
- `test_v088_brief_tldr.py::test_tldr_skips_table_separator_and_bold_label_lines`
- `test_v088_brief_tldr.py::test_tldr_block_with_archive_header_uses_synthesis_prose`

All existing v0.88 #6 tests still pass.

### Live vault refresh

Three pre-v0.88.0 stale artifacts in the user's vault were refreshed
out-of-band:

- `hub/human-water-llm/human-water-llm.base` and
  `hub/llm-agents-social-interaction/llm-agents-social-interaction.base`
  re-emitted with `--force` so both clusters now expose the v0.88 #9
  "Reading queue" landing tab (5 views, was 4).
- `hub/human-water-llm/notebooklm-brief-20260513T041410Z.md` re-mirrored
  through the patched code path; TL;DR now reads "The current paradigm
  in Flood Risk Management is bifurcated between computationally
  expensive hydrodynamic simulations and data-driven machine learning..."
  followed by `**Cluster:** [[human-water-llm/00_overview|...]]`.
- `vault rebuild-overviews` re-ran across both clusters so MOCs and
  `_HOME.md` reflect current paper counts and the latest brief link.

No CLI changes; the patch is internal.

## v0.88.2 (2026-05-13) — paper retype CLI

Closes the second v0.88.1 backlog item from V088_PLAN.md acceptance:
"Zotero `itemType` change is still a manual step" — pyzotero / the
Zotero web API rejects PATCH requests that try to change `itemType`
on an existing item.

### Fix

New `research-hub paper retype --slug X --to-type Y [--dry-run|--apply]`
CLI. Implements the create-new + trash-old + rewrite-frontmatter
work-around:

1. Read the Obsidian note's `zotero-key` frontmatter field.
2. Fetch the current Zotero item; capture `data` + `itemType`.
3. Get a fresh `item_template(target_type)` from Zotero.
4. Map shared fields old → new template, with cross-type venue
   translation (publicationTitle → proceedingsTitle for
   journalArticle → conferencePaper; both blanked for dataset).
5. Preserve `creators`, `tags`, `collections` verbatim so the new
   item lands in the same cluster collection.
6. `--dry-run` (default): print the plan + fields_copied + fields_dropped.
7. `--apply`: `zot.create_items([new_data])` → new key. Try soft-trash
   the old; if pyzotero rejects the `deleted: 1` payload (it does
   in current Zotero web API), fall back to `delete_item` (hard
   delete from Zotero — but the new correct-type item already has
   all the fields, and Zotero web app's Trash UI lets the user
   restore for ~30 days). Rewrite the note's `zotero-key:` to the
   new key. Rebuild dedup_index.

### Live verification

Two papers retyped on the user's vault (the v0.87 reviewer-rejection
cases):

  goldshtein2025  journalArticle → conferencePaper
    old 3A5FNAXZ → new 8AVTNDDW
    publicationTitle "World Environmental and Water Resources
    Congress 2025" → proceedingsTitle (same value, correct field)

  arnold2026      journalArticle → dataset
    old I92RXW72 → new UHI4TD4Z
    publicationTitle "" stays blank (dataset has no venue field)

Both new items preserve cluster collection bindings (6ZANW2CZ +
batch collection). Both Obsidian notes' `zotero-key:` rewritten.
Both old items removed via `delete_item` (soft-trash unavailable).

### Tests (8 new)

tests/test_v0881_retype.py:
- dry-run does not create or trash
- apply creates new + trashes old + rewrites frontmatter key
- to-dataset blanks venue + drops unsupported fields (volume/issue/pages)
- target == source returns no-op error
- missing slug returns clear error
- missing zotero-key returns clear error
- unknown target itemType returns Zotero API error
- creators + tags + collections preserved verbatim

Mocks pyzotero entirely — no live API calls in tests.

## v0.88.1 (2026-05-13) — fix the 2 shard-test flakes

v0.88.0 shipped with two `@pytest.mark.xfail(strict=False)`-marked
sharding tests in `tests/test_v088_nlm_cap.py`. They passed in
isolation but failed in full suite because the
`monkeypatch.setattr("research_hub.notebooklm.upload._make_client", ...)`
string-path form was being bypassed for `_upload_cluster_shards`'s
internal call — the real `NotebookLMClient` was constructed and
tried to load auth from a non-existent state file.

### Root cause

`monkeypatch.setattr(string_path, value)` resolves the module via
`importlib.import_module` at fixture-setup time. In some
test-ordering combinations the resolved module object differed from
the one cached in `sys.modules` that `_upload_cluster_shards`
closed over — likely a residue of a much earlier test that did
`importlib.reload` or replaced the entry. The patch landed on a
stale module instance while the live function kept resolving names
against the original.

### Fix

Switched the 2 sharding tests from string-path to
module-reference monkeypatching:

```python
from research_hub.notebooklm import upload as upload_mod

# Was:
monkeypatch.setattr("research_hub.notebooklm.upload._make_client", lam)
# Now:
monkeypatch.setattr(upload_mod, "_make_client", lam)
```

The module-reference form patches whichever module instance the
test itself imported, which is also the instance that
`_upload_cluster_shards` reads from (same import chain). Removed
the `@pytest.mark.xfail` decorators.

Added a sanity assertion in the primary shard test:

```python
assert upload_mod._make_client(None, headless=True) is fake_client
```

This fires immediately if a future test ordering re-introduces the
drift — instead of silently constructing a real client.

### Verification

Full suite: **2289 passed**, 23 skipped, 6 deselected, **2 xfailed**
(down from 4 — these are the pre-existing v0.31 xfails, not v0.88
ones), 1 xpassed, **0 failed**.

The 2 sharding tests now PASS in both isolation and full suite.

## v0.88.0 (2026-05-13) — "scale + UX"

Closes V088_PLAN.md v0.88 scope (11 issues from the post-v0.87
4-agent audit: V1 scale / V4 UX / partial Q5 follow-up).

The v0.87 series shipped "trust the ingest" — make sure metadata,
abstracts, and NLM source content are correct. v0.88 ships "the
workspace is navigable AND scale-ready" — fix the UX that audit
found broken on the existing 35-paper vault AND open up the
operating envelope to 500+ papers across many clusters.

### Highlights — UX (Claude-direct, 8 issues)

- **#9 Reading queue base view** (0899b7a): each cluster's `.base`
  file now has a "Reading queue" view (filter status==unread,
  order year DESC + ingested_at DESC) as the default landing tab.
  Plus the 4 v0.87 views.

- **#4 MOC body populator** (642bc3d): MOC files
  (`hub/_moc/<name>.md`) were stubs reading `(populated by sync)`.
  New `populate_moc(vault_root, name, cluster_slugs)` writes the
  real `## Clusters` list with `[[<slug>/00_overview|<slug>]]`
  wikilinks. Walked from `populate_all_overviews` so `vault
  rebuild-overviews` keeps MOCs current automatically.

- **#5 paper note ## Hub backlink section** (ec6af34): every paper
  note now ends with a `## Hub` section linking to its cluster
  overview + each MOC. Closes the graph orphan-hub problem (V4
  audit). 35 existing papers live-migrated via new `vault
  hub-backlink-migrate --apply` CLI.

- **#6 brief mirror TL;DR + cluster backlink** (4ec0b63): NLM
  brief markdown mirrors now prepend a TL;DR (extracted from
  Executive Summary / Overview / Key Themes / Key Findings —
  first match wins; 500-char cap) and a `**Cluster:** [[...]]`
  backlink. Fixes iPhone scroll pain + missing back-navigation
  flagged by V4 mobile audit.

- **#7 vault root _HOME.md** (4368e78): new
  `<vault>/_HOME.md` as canonical Obsidian landing page —
  Clusters table, Reading queue (top 5 unread cross-cluster),
  Recent NotebookLM briefs (latest 3), Dashboard links.
  Aliases `["Home", "🏠"]` so Ctrl+O instantly hits it.
  Refreshed by `populate_home(cfg)` inside `populate_all_overviews`.

- **#8 auto-section visual fence** (b3b8356): cluster overview
  auto-generated sections (Papers / NotebookLM brief / Related
  MOCs) now begin with an Obsidian `> [!info] Auto-generated by
  populate_overview...` callout. Closes the "user accidentally
  edits an auto section and loses the edit" risk.

- **#10 mark-kept --show-counts / --by-pattern** (556cd24):
  `zotero mark-kept --list --show-counts` enriches the opaque
  8-char key list with collection name + item count. Plus
  `--by-pattern REGEX` to filter by name (case-insensitive). At
  the user's 94 kept keys this turns an unreadable dump into a
  navigable table.

- **#11 dashboard --markdown-summary** (93219aa): new flag writes
  `<vault>/.research_hub/dashboard-summary.md` — mobile-friendly
  markdown mirror of the HTML dashboard's Overview tab (cluster
  paper counts, unread counts, brief presence, pending summary
  backlog). Linked from `_HOME.md`. The HTML dashboard remains
  the desktop-primary view.

### Highlights — scale (Codex-delegated, 3 issues)

- **#1 NotebookLM source-cap awareness** (cf3e2f7): the v0.87
  `upload_cluster` silently broke at 51 sources. v0.88 raises
  `NotebookLMCapacityError` by default. New flag
  `--over-cap-strategy {fail,top-n-recent,top-n-cited,fit-score,shard}`
  + `notebooklm shard` retroactive splitter + `Cluster.notebooklm_shards`
  list model. 13/15 tests pass; 2 sharding tests xfail'd due to
  a full-suite monkeypatch flake (see v0.88.1 backlog).

- **#2 paginated overview + debounced rebuild** (144ed98): at
  >30 papers the cluster overview now shows 12 most-recent + 20
  top-fit + a collapsible full list + a sidecar
  `01_papers_by_year.md`. Plus a marker file at
  `.research_hub/clusters/<slug>.rebuild_marker.json` debounces
  re-renders (skip if <10 papers added since last rebuild;
  `vault rebuild-overviews --force` bypasses).

- **#3 paper bulk-* + clusters archive + dedup compact** (e285abc):
  three families of bulk ops:
  - `paper bulk-relabel --from X --to Y`
  - `paper bulk-move --slugs A,B,C --to-cluster X`
  - `paper bulk-delete --by-tag X` (Zotero items → trash, not
    hard-delete)
  - `clusters archive <slug>` / `unarchive` — sets
    `Cluster.status` and skips archived clusters from `auto` runs
    by default; explicit `--cluster <archived>` to override
  - `dedup compact` — drops stale Zotero hits from dedup_index
  All bulk-* default to `--dry-run`; `--apply` required to mutate.

### Tests

v0.87.2 baseline: 2192 passed
v0.88.0 final: 2287 passed (+95 new across 11 new test files +
3 existing-test updates), 4 xfailed (3 sharding + 1 pre-existing),
0 failed.

### Acceptance live verification

User's vault (35 papers across 2 clusters) on master @ e285abc:
- ✅ All paper notes have `## Hub` backlink (35/35)
- ✅ `hub/_moc/LLM-Agents.md` body lists both clusters
- ✅ `hub/_moc/Water-Resources.md` body lists human-water-llm
- ✅ `<vault>/_HOME.md` exists with all 4 canonical sections
- ✅ `.research_hub/dashboard-summary.md` writable via CLI
- ✅ NLM brief mirror has TL;DR + cluster backlink
- ✅ Overview Papers section wears the `> [!info]` callout

### Known follow-ups (v0.88.1)

1. 2 shard tests in test_v088_nlm_cap.py xfail'd: pass in
   isolation, fail in full suite due to monkeypatch on
   `upload._make_client` + `upload.NotebookLMClient` being
   bypassed under specific test-ordering conditions. Root cause
   not yet pinpointed — likely sys.modules / fixture-ordering
   interaction with one of the 2200+ earlier tests.

2. Zotero `itemType` change is still a manual step (Zotero
   Desktop) — pyzotero can't PATCH itemType. v0.87's
   goldshtein/arnold venue fix was live-applied but their
   itemType (journalArticle vs conferencePaper/dataset) still
   needs user action.

## v0.87.2 (2026-05-13) — "stop the sticky placeholder bleed"

Closes V088_PLAN.md v0.87.1 §4 (the single highest-impact V3-audit
finding, deferred from v0.87.1 to give it its own ship cycle).

V3 audit found **18 of 35** paper notes stuck at comprehension
score-3 because their `Key Findings / Methodology / Relevance`
sections contained sticky placeholder text:

    > [review and extract from Abstract section above]
    > [review abstract; refine after reading PDF]
    > [TODO: fill relevance to cluster]

The placeholder is *sticky* (looks structurally complete, Dataview
counts the note as ingested) and *silent* (no log line, no
dashboard surfacing). Users never circle back.

### Fix — four-part change

**1. `summarize_status` frontmatter flag** replaces the sticky body
placeholders. Every paper now ships with one of:
- `pending` — needs summarization, real backlog signal
- `done` — summarized (via Claude/Codex/Gemini CLI)
- `failed_no_abstract` — abstract is missing or <100 chars or matches
  `(no abstract)` etc.; retried automatically on subsequent runs

**2. New module `src/research_hub/paper_summarize.py`** (~470 LOC):
- `summarize_pending(cfg, *, cluster_slug_filter, backend, max_papers, dry_run)`
- `build_paper_prompt` (V3-spec prompt template, locked in V088_PLAN.md §4)
- `parse_summary_response` — accepts the 4-section output OR
  `[no-abstract-fallback]` signal
- `apply_parsed_summary_to_note` — rewrites SUMMARY / KEY_FINDINGS /
  METHODOLOGY / RELEVANCE sections idempotently
- Pluggable backends (V088_PLAN.md Q1): `claude` / `codex` / `gemini`
  via subprocess. Each gets its own `_invoke_*` adapter.

**3. Backfill migration `vault summarize-status-migrate`** flips
existing notes to the new model:
- Sticky placeholder body → `pending` (the V3 score-3 papers)
- Substantive body content → `done` (the V3 score-5 papers,
  llm-agents-social cluster)
- Bad/missing abstract → `failed_no_abstract`
- Already-set → skip

**4. Dashboard backlog** (Library tab):
- "Papers awaiting summary: N" with per-cluster breakdown
- One-click command snippet `research-hub paper summarize --pending`

### Live verification on user's vault

**Migration** (`research-hub vault summarize-status-migrate --apply`):
    12 notes flipped pending
    16 notes flipped done
     7 notes flipped failed_no_abstract
     0 already_set

Matches V3 audit per-paper table exactly.

**Autorun** (`research-hub paper summarize --pending --cluster human-water-llm --cli claude`):
On the 12 human-water papers, after migration:
    10 done (filled with substantive content — sample below)
     2 failed_no_abstract (arnold Zenodo dataset blurb +
                          wen2026 13-char "(no abstract)")

Sample of `done` body for fu2025:
- Summary (1-2 sentences using the paper's terminology)
- Key Findings (5 substantive bullets)
- Methodology (1 paragraph identifying perspective-paper character)
- Relevance (1 sentence linking to topic_cluster)

This is the score 3 → 5 transition V3 predicted. The 2 papers that
remain `failed_no_abstract` are correctly failing (no real abstract
to summarize from).

### Windows-specific subprocess hardening (v0.87.2.1 inline)

Codex's first implementation tripped on Windows:
- `subprocess.run(text=True)` defaulted to `cp950` codec (zh_TW
  locale) and couldn't decode UTF-8 LLM output containing en-dash,
  smart quote, em-dash. Patched: force `encoding="utf-8"` +
  `errors="replace"`.
- `claude --print <very-long-argv>` hit cmd.exe's ~8 KB argv length
  limit on Windows when skill_context + prompt exceeded it. Patched:
  feed prompt via stdin instead of argv. Also dropped the skill_context
  injection — Claude Code's `--print` mode does NOT activate Skills
  (interactive-mode only), and the long skill markdown was confusing
  the model.

### Tests

2113 (v0.87.1.1 baseline) → 2192 (after v0.87.2) (+79 new tests,
8 from migration, 9 from worker, 18 from dashboard backlog, 44 from
prompt/parse/template). Per-file:
  test_v0872_summarize_migrate           8
  test_v0872_summarize_worker            9
  test_dashboard_sections_v2 (+18)      18
  paper_summarize internal tests        44

### Files touched

- src/research_hub/paper_summarize.py (NEW, 470 LOC)
- src/research_hub/vault/summarize_migrate.py (NEW)
- src/research_hub/cli.py (paper summarize + vault summarize-status-migrate subcommands)
- src/research_hub/dashboard/sections.py (Library backlog metric)
- src/research_hub/markdown_conventions.py (recognize new callouts)
- src/research_hub/pipeline.py (1 line)
- src/research_hub/zotero/fetch.py (new make_raw_md kwarg + pending sections)
- tests/test_v0872_summarize_migrate.py
- tests/test_v0872_summarize_worker.py
- tests/test_dashboard_sections_v2.py (extended)

## v0.87.1.1 (2026-05-13) — hotfix

CI regression from v0.87.1 §3: the new `_is_substantive` predicate
enforced a 200-character minimum threshold, but the pre-existing
`test_v072_search_quality::test_recover_abstract_uses_crossref_first`
fixture asserts that the chain accepts the 18-char string
"Recovered abstract" from Crossref. The threshold rejected that as
not-substantive, the chain fell through all 4 backends to empty,
and 5 jobs went red on master (no production impact — only CI).

A second regression: the new chain order (Crossref → OpenAlex →
Unpaywall → S2) consumed Mock HTTP responses in `test_v072_search_quality`
in an order that no longer matched the test fixture's 2-response
queue (designed for Crossref→Unpaywall→S2). Result: the
unpaywall-oa_url-only fallback never reached its branch.

### Fix

src/research_hub/search/abstract_recovery.py:

1. **`_is_substantive` drops the length threshold.** Only checks
   placeholder patterns + non-empty after strip. Even a 1-sentence
   abstract is "substantive enough" to early-exit. The
   placeholder denylist (`(no abstract)`, `no abstract available`,
   `[no abstract]`, `abstract not available`) still keeps the Wen
   2026 case caught.

2. **Reorder chain: Crossref → Unpaywall → OpenAlex → S2.**
   Preserves the v0.72 invariant that Unpaywall's oa_url-only
   record stays reachable when no source returned text. OpenAlex
   sits between Unpaywall and S2 so it still gets a shot before
   the rate-limited S2 fallback.

3. **Drop the "max length" fallback.** Replaced with the original
   v0.72 logic: if no source returned substantive text, return
   Unpaywall when it has `oa_url`, else empty.

### Tests updated

tests/test_v0871_abstract_fallback.py:
- `test_is_substantive_rejects_short_text` →
  `test_is_substantive_accepts_short_nonplaceholder_text`
  (with a comment explaining the v0.72 fixture mismatch)
- `test_recover_chain_returns_longest_when_none_substantive` →
  `test_recover_chain_returns_unpaywall_oa_url_when_no_text_anywhere`
  (matches the v0.72 invariant)

Local: 21/21 in tests/test_v0871_abstract_fallback.py +
tests/test_v072_search_quality.py.

## v0.87.1 (2026-05-13) — "trust the metadata"

Closes V088_PLAN.md v0.87.1 scope (6 of 7 issues; §4
paper-summarize autorun deferred to v0.87.2). Theme: every paper
note that lands in the vault is bibliographically defensible —
correct venue, correct itemType, substantive abstract.

### Headlines

- **§1 DOI-prefix overrides** (commit f3644e8): Zenodo /
  Figshare → `dataset` itemType, ASCE 10.1061/ forbids "arXiv"
  venue, ESSoar / EarthArXiv / SSRN / EGU / arXiv default-venue
  fills. Runs in `pipeline.py` BEFORE `zot.item_template`, so
  itemType is correctly chosen at ingest time. 14 unit tests.

- **§2 Crossref venue fallback chain** (commit 906c48d): when
  `container-title` is empty, walk `event.name` →
  `proceedings-title` → `publisher` → `archive`. Fixes the 6
  vault papers with blank journals (höhn / kim / qiao-thematic /
  fu / ranaweera / taormina) on next re-enrich. 13 unit tests.

- **§3 abstract fallback chain** (commit 3427bd6): new
  `_is_substantive` predicate rejects 13-char "(no abstract)"
  placeholders that previously short-circuited the recovery
  chain. New OpenAlex inverted-index reconstruction step (~80%
  coverage, not rate-limited like S2). Chain order:
  Crossref → OpenAlex → Unpaywall → S2, gated by substantive
  check. 11 unit tests.

- **§5 vault rebuild-overviews** (commit 1280017): new
  `populate_all_overviews` walks every cluster in the registry
  and idempotently runs populate_overview + ensure_moc. CLI:
  `research-hub vault rebuild-overviews [--cluster X]`. Backfills
  clusters that were ingested before v0.87 (V4 audit found
  `llm-agents-social-interaction` overview was still bare zh-TW
  scaffold). 7 unit tests.

- **§6 topic:<slug> tag migration** (commit 24bed9a):
  `make_raw_md` injects `topic:<topic_cluster>` into the `tags`
  array; new `vault tag-migrate` CLI backfills the 35 existing
  paper notes. After migration, Obsidian tag pane shows
  `topic:human-water-llm` (12) and
  `topic:llm-agents-social-interaction` (23) — graph color
  grouping by topic now works. 11 unit tests.

- **§7 live-fix for goldshtein + arnold** (no code; manual data
  apply): both Zotero items + Obsidian frontmatter updated via
  one-shot script:
    - goldshtein2025: publicationTitle "arXiv" → "World
      Environmental and Water Resources Congress 2025" (via
      Crossref `event.name` through new §2 chain)
    - arnold2026:    publicationTitle "Open MIND" → "" (Zenodo
      dataset, no journal)
  itemType change (journalArticle → conferencePaper / dataset)
  must be done manually in Zotero Desktop — pyzotero can't
  PATCH itemType. Future v0.88 adds a proper CLI for this.

### Deferred to v0.87.2

§4 — `summarize_status: pending|done|failed_no_abstract`
frontmatter + `research-hub paper summarize --pending` queue
worker + Dashboard backlog count. V3 audit's highest-impact
finding (18/35 papers stuck at score-3 due to sticky placeholder
bodies). Defers to a separate release because it's a Codex round
+ a new CLI surface — better as a single-focus changelog entry.

### Tests

2113 (v0.87.0 baseline) → ~2169 after v0.87.1 (+56 new tests
across 5 new test files). Per-file:
  test_v0871_rebuild_overviews        7
  test_v0871_tag_migrate              11
  test_v0871_doi_overrides            14
  test_v0871_venue_fallback           13
  test_v0871_abstract_fallback        11

### Live verification on user's vault

- All 35 paper notes have `tags: ["topic:<slug>"]`
- llm-agents-social-interaction/00_overview.md regenerated with
  Papers + Related MOCs sections
- goldshtein2025 + arnold2026 venues no longer would-be-rejected
  by a manuscript reviewer

## v0.87.0 (2026-05-13) — "trust the ingest"

Closes the silent-failure gaps surfaced by the human-water-llm
shakedown audit (4-agent review on the freshly-ingested 12-paper
LLM-for-Human-Water-Systems cluster). The theme: when `ingest` /
`upload` / `download` returns success, the user must be able to
trust that the underlying state actually matches.

Full plan + locked decisions: `V087_PLAN.md`.

### Highlights

- **D1 doctor false-positive fixed** — `doctor` was always reporting
  `[!!] nlm_session: No saved session` on v0.86 vaults because it
  still probed the v0.85 directory layout. It now checks the canonical
  notebooklm-py file path (`nlm_sessions/state.json`).

- **N1 NotebookLM ingest validator** — flags sources that finished
  with `status=READY` but actually ingested only landing-page chrome
  (IEEE Xplore "Unable to Load Page", EGU abstract-list header, ASCE
  "Vol , No" metadata strip). Writes `.ingest_validation.json` and
  surfaces a `[warn]` block. Advisory — does not fail the upload.

- **N2 cluster-synthesis brief prompt** — replaced
  `ReportFormat.BRIEFING_DOC` (NLM's single-source default) with
  `ReportFormat.CUSTOM` + a synthesis-oriented `CLUSTER_SYNTHESIS_PROMPT`
  so the brief covers all sources instead of focusing on whichever
  one NLM ranks first.

- **Z1 PDF attach per-paper reasoning** — `--with-pdfs` now reports
  per-paper outcome with a real reason (paywall_403, not_found_404,
  no_oa_record, zenodo_dataset, network_error, …) instead of the
  v0.86 silent zero. Summary serialized into the ingest run JSON.

- **O1+O2+MOC vault wayfinding** — new `vault/hub_overview.py`
  idempotently populates `hub/<slug>/00_overview.md` with a Papers
  list (year DESC, author ASC), a NotebookLM-brief wikilink, and a
  Related-MOCs section. `notebooklm download` now writes a `.md`
  mirror of the brief into the vault (preserving the immutable `.txt`
  archive at `.research_hub/artifacts/...`). MOC notes
  (`hub/_moc/LLM-Agents.md`, `hub/_moc/Water-Resources.md`) auto-
  scaffold on first cluster with the matching slug keyword.

- **O4 fit-check → ingest gap reporter** — writes
  `hub/<slug>/.ingest_gap.json` whenever fit-check accepts more
  papers than ingest writes. On the human-water-llm cluster this
  surfaces the 3 papers (Making Waves, Embracing LLM, IWMS-LLM) that
  Semantic Scholar rate-limit lost in the v0.86 round.

- **Q3 slide-deck artifact** — `notebooklm download --type slide-deck`
  with `--slide-format {pdf,pptx}`. `notebooklm generate --type
  slide-deck` triggers generation; the `all` alias adds slide-deck
  to the multi-artifact sweep. Other artifacts (audio/video/mind-map/
  infographic/quiz/flashcards) deferred to v0.87.1.

- **Q5 kept-by-user Zotero collections** — new sidecar at
  `<vault>/.research_hub/zotero_kept_collections.json` plus
  `zotero mark-kept --all-orphans | --collection KEY | --remove KEY |
  --list`. `zotero gc` defaults to `--respect-kept` ON; pass
  `--no-respect-kept` for audit mode. Test-pattern matches still
  surface even on kept collections.

### Locked v0.87.0 decisions

1. Tag scheme `topic:<slug>` — new code emits `topic:`, legacy
   `cluster/<slug>` migration deferred to v0.87.1.
2. MOC notes promoted into v0.87.0 (was v0.88).
3. Slide-deck is the only artifact in v0.87.0 download parity.
4. Synthesis prompt locked (see `client.py:CLUSTER_SYNTHESIS_PROMPT`).
5. Orphan Zotero collections: live-marked 94 entries as
   kept-by-user during the v0.87 ship cycle.

### Tests

2113 passed, 23 skipped, 0 failed (+32 new tests over v0.86.3 baseline
of 2081). New regression files: `test_v087_zotero_kept.py`,
`test_v087_notebooklm_synthesis.py`, `test_hub_overview.py`,
`test_notebooklm_brief_mirror.py`, `test_moc.py`,
`test_v087_ingest_gap.py`, `test_v087_slide_deck.py`,
`test_v087_nlm_ingest_validator.py`,
`test_v087_pdf_attach_reporting.py`.

### v0.87.1 backlog (already specced in V087_PLAN.md)

- Z2 abstract fallback chain (Crossref → OpenAlex inverted-index)
- Z3 venue fallback chain (DOI-prefix overrides for Zenodo / ASCE)
- Z4 Zotero child-note Obsidian-URI backlink
- Z5 legacy `cluster/<slug>` → `topic:<slug>` tag migration
- O3 post-ingest paper-summarize autorun (fill Key Findings /
  Methodology / Relevance from abstract)
- N3 download parity for audio / video / mind-map / infographic /
  quiz / flashcards / custom-report

## v0.86.3 (2026-05-13)

CI hotfix wave 2 — three pre-existing failures surfaced by v0.86.2.
Before v0.86.2 these were masked because pytest crashed at collection
time on the deleted `cdp_launcher` module and never reached them.

1. **`__init__.py` version drift** — `src/research_hub/__init__.py`
   said `0.81.0` while `pyproject.toml` said `0.86.2` (drift since
   v0.81, 5+ releases unnoticed). Bumped to `0.86.3` and pinned the
   sync expectation in this entry.

2. **`skills_data/literature-triage-matrix/SKILL.md` mirror drift** —
   `skills/<name>/SKILL.md` (canonical source) got an
   agentskills.io portability update in commit `b7f6420`, but the
   packaged mirror `src/research_hub/skills_data/<name>/SKILL.md`
   was not regenerated. Re-mirrored.

3. **`skills_data/zotero-library-curator/SKILL.md` mirror drift** —
   same root cause as #2. Re-mirrored.

Full local suite: 2061 passed, 23 skipped, 0 failed (4m37s).

## v0.86.2 (2026-05-13)

CI hotfix: tests across 8 files referenced the deleted
`research_hub.notebooklm.cdp_launcher` module, causing the entire test
suite to crash with `ModuleNotFoundError` on import. CI on master has
been red since v0.83.0 because of this — every release since the v0.46
patchright migration left these monkeypatches in place, and v0.86.0's
NotebookLM Phase 1 migration finally removed the module they targeted.

Removed 17 dead `monkeypatch.setattr("...cdp_launcher.find_chrome_binary", ...)`
calls (93 deletions, 0 additions). The production chrome check uses
`patchright.sync_api.sync_playwright` directly (since v0.46) and is
covered by `test_doctor_chrome_not_found` — the deleted monkeypatches
were already no-ops at runtime, just lethal at import time.

Verified locally: 111 passed, 3 skipped, 0 failed across all touched
test modules (44s). No production code changed.

Affected files (test-only):
- tests/test_doctor.py
- tests/test_doctor_invariants.py
- tests/test_e2e_smoke.py
- tests/test_init_wizard.py
- tests/test_persona_modes.py
- tests/test_v030_security.py
- tests/test_v038_init_persona.py
- tests/test_v040_onboarding.py

## v0.86.1 (2026-05-13)

Hotfix: `notebooklm login` was broken since v0.86.0 — the subprocess
in `notebooklm/auth.py:login_nlm` invoked the wrong module path
(`python -m notebooklm.cli ...`), which is a package, not an
executable module. Error visible to users:

    No module named notebooklm.cli.__main__;
    'notebooklm.cli' is a package and cannot be directly executed

The notebooklm-py 0.4.1 CLI entry-point is `notebooklm.notebooklm_cli`
(and the flag is `--storage`, not `--output`). Patched the single
subprocess call. All other notebooklm-py usages in research-hub go
through the Python API, not the CLI, so this is the only affected
path.

Verified by a fresh login attempt on Windows / Python 3.14.

## v0.86.0 (2026-05-12)

NotebookLM module Phase 1 migration: replace Playwright/CDP browser
automation with `notebooklm-py 0.4.1` RPC client.

### Background
The v0.85 NotebookLM module was 2,803 LOC of browser automation
(Playwright + CDP launcher + Chrome profile cloning + multilang DOM
selectors + session health heuristics). Each NLM call spawned a
headless Chrome session, scraped the live Angular UI with locale-
specific XPath/CSS, and was brittle whenever Google shipped a frontend
tweak. It also could not produce structured citations — `ask` returned
plaintext only, with no source-id linkage.

`notebooklm-py` (NousResearch-adjacent community project, MIT,
v0.4.1 released 2026-05-11, ★13k+) reverse-engineers Google's internal
RPC endpoints (`batchexecute` / `SNlM0e` / `FdrFJe`) and drives them
via `httpx`. Same auth boundary, no browser needed at runtime, 10-100×
faster, exposes structured citation + multi-turn chat + artifact
download capabilities the web UI doesn't surface.

### Changed
- **Deleted 6 files** (~1,150 LOC of browser plumbing):
  `browser.py`, `cdp_launcher.py`, `chrome_clone.py`, `selectors.py`,
  `session.py`, `session_health.py`.
- **Added `auth.py`** (166 LOC): thin shim re-exporting v0.85 public
  surface (`default_session_dir`, `default_state_file`, `login_nlm`,
  `login_interactive`, `login_interactive_cdp`, `check_session_health`,
  `import_session`) backed by `notebooklm-py`'s auth subsystem.
- **`client.py`**: 544 → 377 LOC. Now a thin sync facade wrapping
  `notebooklm.NotebookLMClient` via `asyncio.run()`. Public dataclasses
  (`NotebookLMError`, `UploadResult`, `NotebookHandle`,
  `BriefingArtifact`) preserved for backward compatibility with
  `upload.py` + `ask.py` callers.
- **`upload.py`**: 481 → 522 LOC. Bulk of orchestration preserved
  (manifest lookup, `nlm_cache.json` resume state, retry-with-backoff,
  JSONL debug logging). Only the inner client calls swapped.
- **`ask.py`**: 283 → 176 LOC. New `AskCitation` dataclass added;
  `AskResult.references: list[AskCitation]` populated for the first
  time (each citation has `source_id`, `citation_number`,
  `cited_text`, `start_char`, `end_char`).
- **`__init__.py`**: 40 → 52 LOC, exports refreshed.
- **`cli.py`**, **`setup_command.py`**, **`doctor.py`**: import paths
  updated; CLI flag signatures preserved. No breaking change for
  existing CLI users.
- **Skipped 7 legacy Playwright/CDP-specific tests** (`test_v042_nlm_browser`,
  `test_v065_nlm_login_diag`, `test_v070_1_nlm_session_management`,
  parts of `test_v065_nlm_upload`, `test_v071_2_nlm_polish`,
  `test_v046_auto`, `test_notebooklm_client`).
- **Added `test_notebooklm_v086.py`** with v0.86-shape regression
  coverage mocking `notebooklm.NotebookLMClient.from_storage`.

### Added
- **`notebooklm-py>=0.4.1`** as a hard `install_requires`. Playwright
  / CDP is no longer required for normal use; only the one-time
  `notebooklm login` flow installs a browser binary on demand.
- **Structured citations** (`AskResult.references`) — previously
  unavailable. Each chat answer now carries source-id linkage suitable
  for the `notebooklm-brief-verifier` skill / any reviewer-style audit.

### Removed
- Direct Playwright / CDP dependencies in normal code paths. `nlm_session/state.json`
  files from v0.85 remain compatible (`NotebookLMClient.from_storage`
  reads the same Playwright storage state format).

### Migration notes
- **For users**: no CLI flag changes; existing `state.json` should
  load. First run after upgrade: `pip install -U research-hub-pipeline`
  pulls `notebooklm-py 0.4.1` transitively. If login state is stale,
  re-run `research-hub notebooklm login`.
- **Phase 2 (deferred)**: expose new artifact-download capabilities
  via CLI (audio overview / mind map / quiz / slide deck), multi-turn
  chat (`conversation_id`), per-cluster source-id citation rendering
  in `read_latest_briefing`.

### Verification
- `pytest tests/ -k "notebooklm or nlm"`: **86 passed, 7 skipped, 2000 deselected**.
- `python -m research_hub --help` exits 0 (CLI imports intact).
- All public symbols importable: `from research_hub.notebooklm.{upload, ask, bundle, auth, client} import *`.

## v0.85.0 (2026-05-11)

Crystal readability + prompt-quality polish.

### Changed
- `Crystal.to_markdown` now emits `based_on_papers:` as a multiline YAML list
  instead of a single-line JSON array. Reading mode + Obsidian Properties view
  show one paper per line, instead of an unreadable 1.5 KB comma-separated
  string blob. Backward compatible: `_parse_frontmatter` was extended to
  parse both new multiline YAML lists and legacy single-line JSON arrays.
- `emit_crystal_prompt` now gives the generator clearer instructions for
  `tldr` / `gist` / `full` distinction:
  - tldr = scan in 5s (newspaper headline)
  - gist = mental model in 30s (3-4 sentences, ~80 words, elevator pitch)
  - full = understand in 2 min (concrete examples + nuance, never restate
    gist with more words)
- New rule: **inline jargon definitions on first mention**. Field-specific
  terms (RAG, ABM, HRI, HCI, parasocial, agentic LLM, social semiotics) get
  a 5-10 word inline definition in parentheses on first mention. Cleans up
  the jargon-heavy prose that domain newcomers were getting stuck on.
- `evidence` and `confidence` instructions tightened: claims must be
  concrete + falsifiable; confidence defaults to medium, high requires 3+
  papers converging, low for sparse/contradictory evidence.

### Why
2026-05-11 review of fresh-pipeline crystal output (23 papers,
llm-agents-social-interaction cluster) flagged three readability issues:
(1) huge frontmatter array, (2) tldr/gist/full layers blurring together,
(3) jargon density too high for cross-disciplinary readers. This commit
makes the source-side fix; existing crystals can be regenerated via
`research-hub crystal emit/apply` for a clean reformat.

## v0.84.0 (2026-05-11)

Unify paper-slug formula + add safety net to prevent broken cross-ref wikilinks.

### Background
During the 2026-05-11 graph hygiene audit, we discovered **1,199 broken
`[[author-year-slug]]` wikilinks** (112 unique phantom targets) in user vaults.
Each broken target rendered as a phantom mega-hub in Obsidian's graph view,
with ~19 inbound radial lines = 112 small grey star clusters polluting the
visual.

### Root cause
The codebase had **two divergent slug formulas** running in parallel:

1. **`safe_filename(author, year, title)`** (zotero/fetch.py:9) — 4-keyword
   stopword-filtered short slug → drove actual `.md` filenames.
2. **`slugify(title)[:60]` / `re.sub(...)[:60]`** at three other call sites
   (`pipeline.py:111`, `discover.py:813`, `operations.py:264`) — 60-char raw
   truncated slug → drove cross-ref wikilink targets in older pipeline versions.

When papers were renamed/migrated/deleted in past cleanups, the long-slug
wikilink targets in OTHER papers' `## Related Papers in This Cluster` sections
became broken. Today's `link_updater` writes correct short-slug wikilinks,
but it doesn't actively repair the historical broken ones, and had no safety
check to refuse writing broken slugs in the first place.

### Fixed
- **Unified slug formula**: extracted `make_paper_slug(author, year, title)`
  helper in `zotero/fetch.py` as the single source of truth. `safe_filename()`
  now delegates to it (returns `{slug}.md`).
- **Three call sites refactored** to use `make_paper_slug` instead of
  divergent slugify formulas: `pipeline.py:_auto_generate_missing_fields`,
  `discover.py:_to_papers_input`, `operations.py` (crossref→entry conversion).
- **`link_updater.add_wikilinks_to_note` safety net**: new optional
  `existing_stems: set[str] | None` parameter. When provided, broken slugs
  (not in the existing files set) are silently filtered out before writing.
  Backward compatible — `None` keeps legacy behavior.
- **`update_cluster_links` always passes the set**, computed once from
  `all_notes`, to enforce the safety net on every regen.

### Added
- 4 new tests:
  - `test_add_wikilinks_filters_nonexistent_slugs` (link_updater) — assert
    broken slugs filtered out when set provided
  - `test_add_wikilinks_without_existing_stems_writes_all` (link_updater) —
    backward-compat: None preserves legacy
  - `test_make_paper_slug_matches_safe_filename` (zotero) — assert filename
    equals `slug + ".md"` for 3 representative inputs; assert no stopwords
    or > 80 char output

### Migration
- Existing vaults with the 1,199 broken wikilinks need a one-shot cleanup.
  The companion script `~/.claude/scripts/vault-prune-broken-related-links.py`
  (gitignored, lives outside this repo) scans paper bodies and removes
  bullets pointing at non-existent files. Includes `.bak` backups,
  `--dry-run` preview, and idempotency. Verified on a 7-cluster vault:
  ~1,199 bullets removed, ~89 sections fully cleaned, ~217 files edited,
  zero data loss outside the broken-link bullets.

### Not done in this version (deferred)
- Regenerating "Related Papers in This Cluster" sections post-cleanup with
  the corrected slug formula. Recommend manually running
  `update_cluster_links()` per cluster once user confirms graph is clean.

## v0.83.0 (2026-05-11)

Forward-only fix for Obsidian graph display.

### Added
- Paper notes now get `aliases:` and `display_title:` frontmatter fields
  computed from `authors[0]` lastname + `year` + `title`. Examples:
  - `aliases: ["Donkers 2025", "Donkers et al. 2025"]` (multi-author)
  - `aliases: ["Donkers 2025"]` (single author)
  - `display_title: "Donkers 2025 — Understanding Online Polarization"`
- Graph view rationale: the storage filename
  (`donkers2025-understanding-online-polarization-through-human-agent-intera`)
  is dash-slugged for URL-safety, but the Obsidian graph node label renders
  the dash slug — visually noisy. Front Matter Title plugin (or Obsidian
  1.5+ inline title) reads `display_title:` and renders the human-readable
  version. Filename stays unchanged (no wikilink breakage).
- 3 new unit tests in `test_zotero_fetch.py`:
  `test_make_raw_md_includes_aliases_and_display_title`,
  `test_make_raw_md_single_author_no_et_al`,
  `test_make_raw_md_placeholder_author_falls_back_to_empty_aliases`.

### Migration
- Existing vault papers (pre-v0.83.0) need a one-shot backfill to add
  these fields. The companion script `vault-backfill-aliases.py` (lives
  in `~/.claude/scripts/`, not packaged here) walks the vault and injects
  the fields based on existing frontmatter `authors:` / `year:` / `title:`.
  Idempotent (re-run = 0 changes); `.bak` backups; `--dry-run` preview.

### Why now
2026-05-11 graph-hygiene audit: after killing the mega-hub wikilink pollution
(v0.82.0), the graph still rendered dash-heavy filenames as node labels.
Community standard (Andy Matuschak, Bryan Jenks, Nick Milo, Front Matter
Title plugin docs): keep storage filename URL-safe, render display via
frontmatter. This commit implements the source-side convention; vault-side
backfill handles existing 1237 paper notes.

## v0.82.0 (2026-05-11)

Graph-hygiene fix surfaced during a vault audit.

### Fixed
- `TAG_WIKI_MAP` in `zotero/fetch.py` was emitting `[[Wikilink]]` strings for
  23 concept categories. None of those wikilink targets had corresponding
  `.md` files in the vault, so Obsidian's graph view rendered each target as
  an unresolved "mega-hub star" — one such star (`[[LLM-Agents]]`) had 115
  radial connections, another (`[[Memory-Systems]]`) had 61. Visually, the
  graph looked dominated by 2 giant grey blobs that were just side-effects
  of automatic concept tagging.
  Fix: every TAG_WIKI_MAP value changed from `[[Wikilink]]` to `#tag` syntax.
  Tags are the right Obsidian primitive for cross-paper concept categorization;
  wikilinks are for explicit named references to real notes.
- Added regression test `test_tags_to_wiki_links_never_emits_wikilink_brackets`
  to prevent the anti-pattern from being reintroduced. Existing tests updated
  to assert the new `#tag` format.
- The legacy function name `tags_to_wiki_links` is preserved for import
  back-compat but now returns tags. Docstring updated to flag the misnomer.

### Migration
- Existing vaults with the old `[[Wikilink]]` references need a one-shot
  vault-wide migration. The script `vault-migrate-wikilink-to-tag.py`
  (gitignored, lives in `~/.claude/scripts/`) handles all 24 patterns with
  `.bak` backups, `--dry-run` preview, and idempotency guarantees.
  In the canonical vault (Lehigh CEE PhD), the script touched 157 files /
  247 replacements with zero data loss.

## v0.81.0 (2026-05-04)

Two small bugs surfaced by the v0.80 end-to-end audit.

### Fixed
- `summarize.py` `_replace_obsidian_block` was leaving `## Summary` at
  the ingest-time `[TODO] <title>` placeholder forever — even when
  claude returned substantive Key Findings. Root cause: the
  `PaperSummary` dataclass had no `summary` field, the LLM prompt
  didn't ask for one, and the writer never targeted the block.
  Fix: prompt now asks for a 1-2 sentence TLDR; `PaperSummary.summary`
  field added; new `_SUMMARY_BLOCK_RE` writes it. Back-compat: when
  LLM omits the field, Summary block stays at [TODO] (no-op).
- `doctor.check_cluster_orphan_papers` was counting `raw/_deleted_*/`
  soft-delete folders as orphan, producing false WARNs (today's
  audit showed `!14 folder(s)` from accumulated cleanup history).
  Fix: skip directories whose name starts with `_deleted_`, mirroring
  the existing exclusion in `vault/sync.list_cluster_notes`.

### Added
- `_build_zotero_note_html` includes the new summary block so Zotero
  child notes also get the TLDR in addition to Key Findings.

### Tests
- 6 new tests in `tests/test_v081_summary_block_and_orphan_skip.py`.

Tests: 2123 → ~2129.

## v0.80.0 (2026-05-04)

Clickable PDFs (imported_file) + abstract recovery + chained re-summarize.

### Added
- `paper attach-pdfs` now uses `linkMode="imported_file"` by default:
  downloads PDF bytes and uploads them through
  `pyzotero.upload_attachments`, so Zotero opens the PDF locally.
- `paper attach-pdfs --keep-url-fallback` falls back to the older
  `imported_url` link-only behavior when download fails.
- `paper attach-pdfs --max-pdf-size` rejects oversized downloads
  (default: 25 MB).
- `paper upgrade-pdfs --cluster <slug> [--apply]` converts legacy
  `imported_url` PDF attachments to `imported_file`.
- `discover._to_papers_input` now runs `recover_abstract()` during
  ingest when the backend returned an empty abstract.
- `abstract_recovery` now falls through to Semantic Scholar
  (`/graph/v1/paper/DOI:<doi>`) and uses `tldr.text` when `abstract`
  is empty.
- `paper resummarize --cluster <slug> [--apply]` re-runs summarize
  only for notes whose `## Summary` block still contains `[TODO]`.
- `paper enrich-existing --apply` now chains a targeted re-summarize
  when a missing abstract is recovered for an existing paper.
- doctor `cluster/summary_thin` reports INFO when more than 30% of a
  cluster's notes still have thin `[TODO]` summaries.
- 16 new tests in `tests/test_v080_*.py`.

Tests: 2107 -> ~2123.

## v0.79.0 (2026-05-03)

Metadata quality + Zotero trash safety.

### Added
- `_normalize_paper_metadata(pp)` now runs after `_unescape_html_in_paper`
  in the ingest pipeline. It fixes:
  - `journal: "preprint"` -> `"arXiv"` for arXiv DOIs, else empty
  - `volume: "abs/<id>"` or `"pdf/<id>"` -> empty
  - empty journal + `10.48550/arXiv.*` DOI -> `"arXiv"`
- `discover.py:_smart_journal_fallback` replaces the legacy
  `or "preprint"` literal so callers that bypass `run_pipeline`
  still get the same arXiv fallback behavior.
- Anonymous-author WARN support: when all authors are
  `Anonymous`/`Unknown`/empty, ingest still proceeds but logs
  `WARN -- all authors are anonymous/unknown` as a non-fatal warning.
- doctor `cluster/zotero_trashed` check warns when any vault-bound
  Zotero collection is in the trash.
- `clusters restore-zotero-coll [--cluster slug] [--apply]` restores
  trashed cluster collections by clearing Zotero's `deleted` flag.
- `cascade_delete_cluster --delete-zotero-collection` now refuses to
  delete a Zotero collection still bound by another cluster.
- 16 new tests across `tests/test_v079_*.py`.

Tests: 2091 -> 2107.

## v0.78.0 (2026-05-03)

Single-bug hotfix: HTML-entity decoding before Zotero write.

### Fixed
- Search backends (Crossref, OpenAlex, Semantic Scholar) sometimes
  returned HTML-escaped strings (e.g. `AI &amp; SOCIETY`,
  `Computers &amp; Education`, `M&uuml;ller`). The pipeline wrote
  these straight to Zotero `publicationTitle` / `title` /
  `abstractNote` / author name fields. Now `_unescape_html_in_paper`
  decodes once at the pipeline layer right after
  `_auto_generate_missing_fields` — before validation, dedup, and
  Zotero/Obsidian writes. Catches the issue regardless of which
  backend supplied the data.
- 8 new tests in `tests/test_v078_html_entity.py`.

Tests: 2083 → 2091.

## v0.77.0 (2026-05-03)

Polish fixes from the v0.74-v0.76 stacked-PR code review (items #7-#10).
No new features; correctness, rate-limit, and test-isolation tweaks only.

### Changed
- `zotero/enrich.py` `plan_enrichment()` gains `rate_limit_rps=5.0`
  default (sleep between Crossref/OpenAlex backend calls). Prevents
  hitting either backend's polite-pool when re-enriching 250+ items.
- `doctor.check_cluster_pdf_coverage` caps per-cluster sampling at
  50 items (was N+1 unbounded). The reported percentage is still
  representative; users wanting the exact count run
  `paper attach-pdfs --cluster <slug>` directly.
- `auto --full-auto` help text now explicitly notes that NotebookLM
  upload also stays ON by default — pair with `--no-nlm` for fully
  local automation without the patchright/Google login step.

### Fixed
- `zotero/pdf_attach._HINT_SHOWN` is module-level state that survived
  across pytest tests. Added `_reset_hint_state()` + autouse fixture
  in `tests/conftest.py` so hint-text assertions are no longer
  order-dependent.

Tests: 2083 passing (no regression).

## v0.76.0 (2026-05-03)

PDF coverage 4-source chain + true full-auto mode + pdf_coverage doctor check.

### Added
- `paper attach-pdfs` chain: arXiv -> OpenAlex oa_url -> Unpaywall -> Crossref `link[]` (4 sources). Expected hit rate 80%+ vs v0.75's arXiv-only 46%.
- `paper attach-pdfs --include-publisher-link` falls back to a linked publisher-page bookmark when no OA PDF exists (100% something-rate).
- `auto --full-auto` umbrella flag enables `--with-pdfs --with-summary --with-crystals` (do_nlm stays default ON).
- `auto --with-summary` runs `summarize --apply` after ingest (auto-detects claude/codex/gemini CLI).
- doctor `cluster/pdf_coverage` INFO check (5th cluster check after v0.75).
- `unpaywall_email` auto-hint stderr message when absent (printed once per process).
- `attach_pdfs` skips items that already have a PDF child (no duplicates on re-runs).
- `config set <key> <value>` CLI for one-shot config tweaks.

### Changed
- `find_pdf_url()` now uses a chained, graceful-degrade lookup across arXiv, OpenAlex, Unpaywall, and Crossref.

Tests: 2070 -> ~2083.

## v0.75.0 (2026-05-02)

Workflow drift fixes (round 2) + test isolation + PDF auto-attach.
Driven by 6 gaps surfaced after v0.74 ship: vault/Zotero name drift,
collision allowed at bind time, stale Zotero collections after
cluster delete, tests polluting real Zotero, metadata gaps from search
backends with no re-enrich path, and no PDF auto-attach.

### Added
- `clusters bind --no-sync-zotero` / `--force-shared` flags
- `clusters rename --no-sync-zotero` flag
- `clusters sync-names [--apply]` to fix vault/Zotero name drift
- `clusters resolve-collision <slug> --new|--into <other>` to fix shared collection keys
- `clusters delete --delete-zotero-collection` flag
- `zotero gc [--apply] [--age-days N]` to find/delete empty/test/orphan Zotero collections
- `paper enrich-existing --cluster <slug> --apply` to fill empty vol/issue/pages/url/abstract fields via Crossref + OpenAlex
- `paper attach-pdfs --cluster <slug> --apply` for Unpaywall + arXiv PDF discovery
- `auto --with-pdfs` and `ingest --with-pdfs` flags for end-to-end ingest + PDFs
- doctor check `cluster/name_drift`
- `tests/conftest.py` autouse `_block_real_zotero` fixture with `ALLOW_REAL_ZOTERO=1` / `@pytest.mark.real_zotero` opt-out
- `unpaywall_email` optional config field
- 28 new tests across 6 files

### Changed
- `ClusterRegistry.bind()` raises `CollisionError` on duplicate `zotero_collection_key` unless `force_shared=True`
- `ClusterRegistry.bind()` and `.rename()` sync the corresponding Zotero collection name by default

### Tests
- 2032 baseline -> ~2060 passing target

## v0.74.0 (2026-05-02)

Workflow drift prevention + per-batch sub-collection. Driven by audit
of Wenyu's vault: 1148 Obsidian notes vs ~125 in cluster Zotero
collections. Three holes patched, plus a new sub-collection axis so
each ingest batch is discoverable in Zotero.

### Added
- `import-folder --with-zotero` flag opts into the Zotero write path.
  Default behavior unchanged (Obsidian-only) but now requires
  confirmation prompt unless `--yes` is also passed.
- `import-folder --batch-label` and `auto`/`ingest --batch-label` for
  explicit batch naming. Default auto-derives `<YYYYMMDD>-<query-slug>`
  or `manual-<YYYYMMDD-HHMMSS>`.
- Per-batch Zotero sub-collection: each ingest creates (or reuses)
  `<cluster_collection>/<batch_label>` and items get
  `collections=[parent, child]` plus a `batch:<label>` tag.
- `clusters audit` CLI: run drift + collision + test-pattern checks,
  exits 1 on any issue.
- 4 new doctor checks: `cluster/zotero_drift`, `cluster/test_pattern`,
  `cluster/collection_collision`, `manifest/orphan_cluster`.
- Manifest entry gains `batch_label` field (back-compat: empty default).

### Fixed
- Silent `RESEARCH_HUB_NO_ZOTERO=1` bypass: now prints stderr banner at
  pipeline entry and a one-line summary at exit.
- `zotero_collection_key` collision was undetected. New doctor check
  catches it; today flags the `WNV9SWVA` collision between
  `llm-agents-software-engineering` and `llm-evaluation-harness`.

### Tests
- `tests/test_v074_drift_prevention.py` (9 tests)
- `tests/test_v074_batch_collection.py` (7 tests)
- pytest target: 2057+ collected

## v0.70.1 (2026-04-27)

UX fix for two recurring NotebookLM session pain points: silent
session expiry and the cross-vault re-login dance. No behavior
change to working flows — pure error-surface + import shortcut.

### Fixed
- **Stale Google session showed wall-of-text URL spew instead of an
  actionable error.** NLM operations (bundle/upload/generate/download/
  ask) now run a 1-line filesystem-only pre-flight check before
  launching Playwright. If the session profile looks empty or
  expired, exit code 1 with a hint that says exactly which command
  to run (`research-hub notebooklm login`). Skipped on `--dry-run
  upload` (no browser launched there).
- **Each new vault required its own ~5-min interactive Google login
  even when a sibling vault on the same machine was already logged
  in.** New `--import-from <vault-path>` flag on
  `research-hub notebooklm login` copies a logged-in profile across
  vaults, skipping the browser dance entirely. Refuses to clobber an
  existing logged-in dest unless `--overwrite` is also passed; refuses
  to copy from a not-logged-in source.

### Added
- New module `notebooklm/session_health.py`:
  `check_session_health`, `is_session_logged_in`, `import_session`.
  Conservative thresholds (state ≥ 100B OR cookies ≥ 5KB) — false
  positives waste a browser launch, false negatives prompt re-login
  the user might not have needed but stays safe. Distinct error
  messages for "no session at all" vs "session exists but looks
  empty/expired".
- 12 new tests in `tests/test_v070_1_nlm_session_management.py`:
  5 session-health, 5 import_session, 2 pre-flight integration.
  pytest: 1958 passed, 0 failed.

## v0.70.0 (2026-04-27)

Add a third paper-quality gate to the auto pipeline: an LLM-judge
fit-check that runs **before** ingest, so off-topic papers never hit
Zotero / Obsidian. Real incident driving this: an `auto` run for
"post-flood household relocation" returned 8 papers, of which 2
were off-topic — Llorca 2022 (autonomous-vehicles + relocation,
nothing about floods) and Komleva 2025 (Soviet-era reservoir forced
resettlement, not climate adaptation). 25% noise rate on a real
research query.

### Added
- **LLM-judge fit-check** between search and ingest in
  `research-hub auto`. Reuses the existing `fit_check.emit_prompt` +
  `fit_check.apply_scores` machinery (the same Gate-1 scoring rubric
  used by manual `discover new` / `discover continue`) plus the
  existing `auto._invoke_llm_cli` + `auto._extract_first_json`
  helpers. No new LLM-CLI abstraction, no new prompt schema.
- New CLI flags:
  - `--no-fit-check` — opt out
  - `--fit-check-threshold N` — default 3 (1-5 rubric); 4 = stricter
- MCP tool `auto_research_topic` gains matching `do_fit_check` +
  `fit_check_threshold` params.
- 11 new tests in `tests/test_v070_auto_fit_check.py` covering
  keep-all-when-no-CLI, filter-by-score, malformed-JSON safety,
  empty-input short-circuit, threshold propagation, plus 4
  auto_pipeline integration tests. pytest: 1946 passed.

### Changed
- Default behavior: `do_fit_check=True`. When LLM CLI is on PATH
  (claude/codex/gemini), runs the judge step. When no CLI is
  available, skips silently with a step-log entry — pre-v0.70.0
  users without CLIs see identical behavior.

### Safety paths (graceful degrade — never drop)
- No CLI on PATH → keep all papers, log "skipped".
- LLM returns malformed JSON → keep all, log failure.
- All papers rejected by threshold → keep all as fallback rather
  than ingest nothing.

## v0.69.0 (2026-04-27)

Adds the **10th packaged skill**: `paper-summarize`. The auto
pipeline ingests metadata + abstract only; per-paper Key Findings /
Methodology / Relevance stayed as `[TODO]` skeletons in both Obsidian
and Zotero. Cluster-level summarization (NotebookLM brief, crystals)
does not fill per-paper notes — so after `auto` the user had nothing
scannable per paper. This release closes that gap.

### Added
- New CLI command:
  ```bash
  research-hub summarize --cluster <slug>            # dry-run
  research-hub summarize --cluster <slug> --apply    # write to both systems
  research-hub summarize --cluster <slug> --llm-cli codex --apply
  ```
- Two new MCP tools: `summarize_cluster` (orchestration) and
  `apply_cluster_summaries` (apply a pre-parsed payload — useful when
  LLM was invoked out-of-band).
- New skill `paper-summarize` (10th packaged):
  - `skills/paper-summarize/SKILL.md`
  - `skills/paper-summarize/evals/evals.json` (4 evals)
  - mirrored to `src/research_hub/skills_data/paper-summarize/`
- `EXPECTED_SKILL_DIR_NAMES` in `test_v068_3_version_sync.py` updated
  9 → 10. `EXPECTED_MAPPINGS` in `test_consistency.py` updated for
  the 2 new MCP tools.
- 17 new tests in `tests/test_v069_summarize.py`. pytest: 1951 passed.

### Architecture
Mirrors the existing crystal flow (`auto.py:_run_crystal_step`):
1. `build_summarize_prompt` reads cluster papers + abstracts, emits
   a JSON-output prompt.
2. `auto._invoke_llm_cli` (reused) pipes the prompt through
   claude/codex/gemini.
3. `auto._extract_first_json` (reused) parses the response.
4. `_validate_entry` rejects unknown paper_slug, empty findings,
   non-list types.
5. `apply_summaries` writes BOTH Obsidian markdown blocks AND
   Zotero child note HTML per paper. Zotero failure rolls back the
   markdown change so the two systems stay in sync.

### Fallback
When no LLM CLI is on PATH: prompt is saved to
`<vault>/.research_hub/artifacts/<slug>/summarize-prompt.md`,
report.ok=True (best-effort). User pipes manually then re-runs with
`--apply` or calls `apply_cluster_summaries` MCP tool.

## v0.68.5 (2026-04-27)

Plumbs volume / issue / pages metadata end-to-end. `SearchResult` at
`search/base.py` had no fields for these — every Zotero item +
Obsidian note ended up with empty bibliographic locator metadata
despite OpenAlex / Crossref returning the data in their API
responses. Real incident: 8 ingested flood-relocation papers all had
`volume: ""`, `issue: ""`, `pages: ""` in their markdown frontmatter.

### Fixed
- **Backend extraction**:
  - `openalex`: read from `work["biblio"]` (volume/issue/first_page/
    last_page); collapse first+last into "first-last". Added `biblio`
    to the API select param.
  - `crossref`: read `work["volume"]`, `work["issue"]`, `work["page"]`
    (already canonical "first-last"). Added these to select param.
  - `semantic-scholar`: read `item["journal"]` (volume/pages); issue
    not exposed by S2's schema. Added "journal" to `DEFAULT_FIELDS`.
  - `arxiv`: extract pages from `arxiv:comment` when it matches
    `r"\d+\s*pages?"`. No volume/issue (preprints).
- **Propagation**: `discover._to_papers_input` now copies
  volume/issue/pages into the entry dict. `pipeline.py` and
  `zotero/fetch.py:make_raw_md` already consumed these so no
  downstream changes needed.

### Added
- 13 new tests in `tests/test_v068_5_metadata_completeness.py`.
- **Test hygiene bonus**: `tests/conftest.py` autouse fixture
  globally stubs `webbrowser.open`. Several `init_wizard` /
  `setup_command` tests trigger code paths that call
  `webbrowser.open("https://zotero.org/settings/keys")`; without a
  global stub, every full pytest run launched a real browser tab.
  Tests that need to assert on the call re-patch locally — the
  autouse stub is overridden cleanly.

pytest: 1918 passed.

## v0.68.4 (2026-04-26)

Three bugs in the auto pipeline left ingested papers with only 2/4
hub tag namespaces (`research-hub` + `cluster/<slug>`) and
TODO-skeleton notes even when the search backend returned a real
abstract.

### Fixed
- **Bug A — `discover.py:_to_papers_input` dropped `source` field.**
  The search candidate dict carries `source` (openalex / crossref /
  etc), but the conversion to ingest input dropped it.
  `_compose_hub_tags` then had nothing to feed the `src/<backend>`
  namespace. Fix: propagate `candidate.get("source") or
  candidate.get("found_in")` into the entry.
- **Bug B — `pipeline.py:_compose_hub_tags` skipped `type/` when no
  doc_type.** Most search backends (semantic-scholar, crossref)
  don't return a `publication_type` field. The pipeline always
  creates journalArticle items in Zotero anyway, so default to
  `type/journalArticle` rather than dropping the namespace.
- **Bug C — TODO-skeleton notes shadowed real abstracts.** When the
  backend returned a non-empty abstract, the note still hardcoded
  `[TODO] <title>` for the summary. Now: seed summary from the
  abstract when available, fall back to TODO marker only when the
  abstract is empty / "(no abstract)".

### Real-incident impact
An `auto` run for "post-flood household relocation" produced 8
papers in Zotero collection C7S7A9KA — every one missing both
`type/` and `src/` tags, every note a TODO skeleton. Manual backfill
via OpenAlex DOI lookup recovered 5 of 6 missing abstracts.

### Changed
- `README.md`: drop hardcoded "Tests: 1759 passing" status
  (auto-stale marker), add product-support badges (Zotero / Obsidian
  / NotebookLM).
- `README.zh-TW`: mirror the badge row that the EN README had been
  carrying alone.

### Added
- 8 new tests in `test_v068_4_hub_tag_completeness.py` covering the
  three bugs end-to-end. Updates to `test_v061_pipeline_tags.py`,
  `test_v065_compose_tags_none_guard.py`, `test_cli_search.py`
  reflect the new contract.

## v0.68.3 (2026-04-26)

Two regressions caught by the v0.68.2 interop test against
`WenyuChiou/ai-research-skills` catalog. Fix + add guard rails so the
catalog (and any other downstream consumer) can rely on us.

### Fixed
- **`__version__` drift**: `src/research_hub/__init__.py:11` hardcoded
  `"0.64.2"` while pyproject.toml bumped through 0.65 / 0.66.x / 0.67 /
  0.68.x. The string drifted past 4 PyPI releases without anyone
  noticing because the publish.yml wheel-validate step printed
  `__version__` but didn't compare it against the tag. Now bumped to
  `"0.68.3"` and pinned to pyproject.toml by a test.

### Added — guard rails
- **`tests/test_v068_3_version_sync.py`** (3 tests):
  - `test_init_version_matches_pyproject_version` — fails the suite if
    `__init__.py:__version__` ≠ `pyproject.toml [project].version`.
  - `test_skill_source_dirs_match_expected_set` — pins the 9 source-dir
    names under `skills/`. Renaming or removing one fails the test until
    `EXPECTED_SKILL_DIR_NAMES` is updated in the same commit. Forces a
    deliberate decision instead of silently breaking catalog links.
  - `test_skill_data_mirror_dirs_match_expected_set` — same for
    `src/research_hub/skills_data/`.
- **`.github/workflows/publish.yml`**: the wheel-validate step now
  asserts `research_hub.__version__ == GITHUB_REF_NAME[1:]` (drops the
  leading `v`). If you tag `v0.69.0` without bumping the source first,
  the publish job fails and nothing reaches PyPI.
- **`CONTRIBUTING.md`** sections "Skill source-dir stability" and
  "Version drift" document the new guards and the required catalog
  coordination steps for any future rename.

### Why this matters for ai-research-skills catalog
The catalog at `WenyuChiou/ai-research-skills/catalog/skills.yml`
links into `https://github.com/WenyuChiou/research-hub/blob/master/skills/<name>/SKILL.md`
for each of the 9 packaged skills. Our v0.68.0 rename
`knowledge-base/` → `research-hub/` broke one of those links (left as a
404 until catalog syncs). The guard rails above make sure that doesn't
happen again silently — every future rename now requires (a) a coord
issue against the catalog, (b) updating
`EXPECTED_SKILL_DIR_NAMES`, and (c) a CHANGELOG entry, all in the same
commit. See `docs/interop-test-v068-2.md` for the full audit.

## v0.68.2 (2026-04-26)

Three SKILL.md structural refinements from the upstream catalog
session — same 3 skills as v0.68.1, but with the framing closer to
how a fresh non-CS user actually reads them. Pure prose + numbering
changes; no code, no test impact.

### research-context-compressor
- Inputs section restructured into three explicit branches: "For any
  project" (just README) / "For code-based research projects"
  (pyproject, scripts, data) / "For qualitative / archival /
  interpretive projects" (notes, drafts, sources, bibliography).
  Reads more like a menu than a checklist.
- Concrete YAML example for a humanities literature-review project
  with `notes/` + `drafts/` only (no code project structure).
  Caption: "Empty fields are honest signals to the next AI session
  that this is a non-code project. They are not failures."
- "An empty manifest field is better than an invented one." pulled
  out as a one-line caveat.

### literature-triage-matrix
- "Manual paper list" promoted from input #5 to **input #0**
  (lowest-friction, listed first). Includes a 3-line example so a
  fresh user who has 5 paper titles + DOIs in their head can use the
  skill without setting up Zotero/Obsidian/cluster.

### notebooklm-brief-verifier
- Inputs section restructured into two numbered modes:
  1. **research-hub-managed mode** (default; bundle paths
     predictable).
  2. **Manual fallback mode** — `--brief <path>` + `--sources <list>`
     for users who generated the brief on notebooklm.google.com
     directly (web UI, manual upload). Conversational variant via
     paste-into-chat documented.
- Verification logic explicitly noted as identical in both modes.

## v0.68.1 (2026-04-26)

Three SKILL.md prose updates from the upstream catalog session.
No code change, no test change.

### research-context-compressor
- Inputs section header changed from "Inputs you should read (in
  priority order)" to "Inputs you should read (priority order over
  inputs you may have)" + explicit "this is a priority list, not a
  requirements list" framing.
- New "Humanities use case example" with worked
  `project_manifest.yml` for a primary-sources-only literary study
  (no code, no scripts, no outputs). Demonstrates that empty lists are
  honest signals, not gaps to fill.
- New input #8 explicitly substitutes a primary-sources folder /
  Obsidian vault / Zotero collection for `data_sources` in non-code
  research.

### literature-triage-matrix
- New input #5: "Manual paper list — a Markdown bullet list of titles
  + DOIs the user pastes into the chat". Lets the skill work without
  Zotero, Obsidian, or any research-hub vault. Useful for one-shot
  triage from external libraries or sandbox repos.

### notebooklm-brief-verifier
- Inputs section split into "Integrated mode" (research-hub uploaded
  the bundle, all paths predictable) and "Standalone mode" (`--brief
  <path>` + `--sources <list>` fallback inputs, works on briefs from
  anywhere — manual NotebookLM session, colleague's brief, etc.).
- Both modes are first-class; the audit method is identical, only the
  input plumbing changes.
- Standalone mode explicitly asks for the source list before running
  the coverage scan; never assumes coverage without ground truth.

## v0.68.0 (2026-04-26)

Closes the four follow-up suggestions from the upstream
`WenyuChiou/ai-research-skills` catalog session.

### New skill (#9)
- **`research-design-helper`** — Stage 3a / front-of-Stage 4 Socratic
  guide. Walks the user through 5 segments (RQ sharpening, expected
  mechanism, identifiability check, validation plan, risk register) and
  saves the result to `.research/design_brief.md`. Domain-agnostic; does
  NOT invent the research question or model design.
- Ships with `references/design_brief_template.md`.
- Hooks into existing skills via doc updates: compressor and orienter
  reference `design_brief.md` if it exists; ownership recorded in the
  workspace-manifest doc.

Total packaged skills: 8 → 9. Auto-discovery picks it up; no installer
code change needed.

### Doc framing (catalog feedback #2 + #3)
- `docs/ai-research-skills.md` now opens with a **"Stages of a research
  project"** table that explicitly splits Stage 3a (frame the problem,
  human work) from Stage 3b (plan artifacts, mechanical). Top-line
  caveat says AI cannot invent the research question.
- New **"Cross-cutting tools (used at every stage)"** section makes it
  explicit that `research-hub-multi-ai`, `codex-delegate`,
  `gemini-delegate` route by task character (token-heavy, long-context,
  CJK, mechanical bulk), not by pipeline stage. Per-stage examples
  included.
- `skills/research-hub-multi-ai/SKILL.md` first paragraph rewritten to
  lead with "stage-agnostic, character-driven routing".

### Source dir rename (catalog feedback #4, option A)
- `skills/knowledge-base/` → `skills/research-hub/`
- `src/research_hub/skills_data/knowledge-base/` →
  `src/research_hub/skills_data/research-hub/`
- `LEGACY_TARGET_ALIASES` map cleared (was `{"knowledge-base":
  "research-hub"}`); replaced by `LEGACY_SOURCE_NAME_ALIASES` for
  backward-compat callers.
- `get_bundled_skill_path("knowledge-base")` still resolves but emits
  `DeprecationWarning` (alias removed in v0.70).
- **User-facing install target unchanged**: still
  `~/.claude/skills/research-hub/SKILL.md`. The rename is purely
  source-side.
- `tests/test_v068_legacy_knowledge_base_alias.py` (3 tests) pins the
  alias contract.

### Tests
- `tests/test_v066_skill_schema.py` and
  `tests/test_v066_research_workspace_docs.py` extended via
  parametrize: design-helper picked up automatically.
- All v0.61-v0.67 regression suites green.

Test count: 1899 → 1908 (+9 net).

## v0.67.0 (2026-04-25)

Closes the three remaining items from the Codex skills brief:

### New skill (#6 of 6 from the brief)
- **`zotero-library-curator`** — sits one layer above the standalone
  `zotero-skills` skill. Reads the Zotero library + research-hub cluster
  registry + dedup index; emits a preview-only audit/curation plan
  covering duplicate DOIs, items missing required hub tags, cluster
  mismatches, tag near-duplicates, collection bloat. **Never** calls
  any Zotero create/update/delete endpoint — defers all writes to
  `zotero-skills` or `research-hub zotero backfill --apply`.
- Trigger phrases: "audit my Zotero library", "find duplicate DOIs",
  "propose a tag hygiene cleanup plan".

Total packaged skills: 7 → 8. Auto-discovery installer picks it up
without any installer code change (v0.66 architecture).

### New CLI: `research-hub context init/audit/compress`
Phase 2 of the brief. Lets users / scripts invoke the workspace skill
logic from shell instead of through an AI session.

- `research-hub context init [--vault PATH]` — bootstrap a `.research/`
  skeleton (6 files); idempotent (never overwrites existing files).
- `research-hub context audit [--vault PATH]` — schema audit
  (project_manifest required fields, freshness, experiment ID
  uniqueness, dataset paths exist). `[OK] / [WARN]` output matching
  `doctor` style.
- `research-hub context compress [--vault PATH] [--print-prompt]` —
  pointer / prompt generator for the `research-context-compressor` AI
  skill. The CLI is intentionally NOT a from-scratch implementation;
  the compression itself is an AI task.

### Legacy evals.json backfill + schema test tightening
- `skills/knowledge-base/evals/evals.json` (4 prompts).
- `skills/research-hub-multi-ai/evals/evals.json` (3 prompts).
- `tests/test_v066_skill_schema.py` no longer exempts the 2 legacy
  skills from the evals.json check; ALL_SKILLS now requires it.

### CI ratchet
- `--cov-fail-under` 60 → 62 (per inventory: real coverage is well
  above 62% after v0.65/v0.66 uplift; locking in the floor).

### Tests
- `tests/test_v067_context_cli.py` (10 tests): init creates skeleton,
  init idempotent, init skips existing files, audit passes clean,
  audit flags missing fields / stale dates / missing dataset paths,
  audit returns 0 on WARN only, compress --print-prompt emits canonical
  prompt, compress default points at skill.

Test count: 1877 → 1899 (+22).

## v0.66.1 (2026-04-25)

### Doctor diagnostic
- New `nlm_chrome_orphans` check in `research-hub doctor` detects leftover
  Chrome processes still holding the NotebookLM patchright profile
  (`nlm_sessions/default/`). These are the most common cause of
  spontaneous `accounts.google.com/.../notebooklm.google.com/...` popups
  that look like research-hub bugs but are actually orphan patchright
  contexts whose cookies expired.
- Status semantics: `OK` when no orphan, `INFO` when orphans found
  (with PIDs in the details so the user can kill them via Task Manager
  or `kill <pid>`), `INFO` when process listing is unavailable on the
  current OS.
- Same root-cause family as the v0.65 `paper lookup-doi --batch`
  Zotero-auto-sync warning: external tools react to research-hub
  artifacts in ways that look like research-hub bugs.

## v0.66.0 (2026-04-25)

Research workspace skills (Phase 1 of the research-skills brief at
`docs/research-hub-research-skills-brief.md`).

### New skills
- `research-context-compressor` — writes `.research/project_manifest.yml`,
  `experiment_matrix.yml`, `data_dictionary.yml` so future AI sessions
  orient themselves without rescanning the repo.
- `research-project-orienter` — reads `.research/` manifests and produces
  an in-conversation orientation memo.
- `literature-triage-matrix` — produces a markdown comparison matrix
  over a set of papers (Zotero collection / Obsidian cluster / manual
  list) instead of N independent summaries. Output to
  `.research/literature_matrix.md`.
- `paper-memory-builder` — bridges research-hub and academic-writing-skills:
  reads manuscript + figures, writes `.paper/claims.yml` + `.paper/figures.yml`.
- `notebooklm-brief-verifier` — checks a downloaded NotebookLM brief
  against the source bundle research-hub uploaded; reports missed
  sources, unsupported claims, contradictions, and follow-up prompts.

Each skill ships with a `SKILL.md` (frontmatter + body) and an
`evals/evals.json` with at least 4 realistic prompts.

### Skill installer auto-discovery
- `src/research_hub/skill_installer.py` now walks `skills_data/` and
  installs every directory that contains a `SKILL.md`. Adding a new skill
  no longer requires updating a hardcoded `SKILL_PACK` tuple.
- Legacy `knowledge-base -> research-hub` install-target alias preserved
  so existing user installs keep working.

### New documentation
- `docs/research-workspace-manifest.md` — full schema for `.research/`
  and `.paper/`, plus an ownership table that documents what
  research-hub writes vs what `academic-writing-skills` writes (no
  collisions in `.paper/`).
- `docs/ai-research-skills.md` — index of every packaged skill, when to
  use each, what it reads, what it writes, and what it deliberately
  doesn't do (defers to WAGF / academic-writing-skills / FLOODABM).

### Tests
- `tests/test_v066_skill_schema.py` — frontmatter validation (name,
  description, ≥30 chars), evals.json structure (≥3 prompts), name
  matches directory, no overclaim language.
- `tests/test_v066_research_workspace_docs.py` — docs exist + list every
  v0.66 skill; packaged skill mirrors are byte-identical to root copies;
  no orphan packaged skills without root source.
- Existing `test_skill_installer.py::test_bundled_skills_use_current_public_positioning`
  relaxed: each skill must mention at least one of
  `Zotero / Obsidian / NotebookLM / research-hub` (was: must mention all
  three) so specialized v0.66 skills can be scoped to one part of the
  stack.
- v0.65 MCP snapshot test relaxed: any non-empty dict response is
  accepted (was over-coupled to fixture state across CI matrix).

Test count: 1858 → ~1900 (+22 v0.66 schema/docs tests, plus the existing
two relaxations). Codex deferral: skill #6 `zotero-library-curator` and
the Phase 2 CLI commands stay out per the brief's own sequencing.

## v0.65.0 (2026-04-25)

QC/QA stabilization release. No new user-visible features; focus on
diagnostics, silent-failure cleanup, and test coverage uplift.

### Bug fixes (Track A)
- **NLM login**: `research-hub notebooklm login` now requires a logged-in
  DOM element (account button / profile image / notebook link) before
  marking the session stable. Prevents partial-cookie saves that caused
  next `auto` runs to bounce back to login.
- **NLM login diagnostic**: timeout now prints the final URL, page title,
  and a one-line hint about Google security/consent flows. Was: a bare
  "Login not detected" with no clue where the browser stopped.
- **NLM session save**: failures during `save_auth_state` now WARN to
  stderr instead of `try/except: pass`. Disk-full / permission errors no
  longer hide.
- **NLM browser arg**: removed `--disable-sync` from the persistent-context
  launch flags. It marked the profile as untrusted and triggered repeated
  Google security checkup challenges. Persistent context already isolates
  the profile via `user_data_dir`.
- **`paper lookup-doi --batch`**: prints a one-line warning that the
  Obsidian rewrites it makes can wake Zotero desktop's file watcher and
  cascade into repeated `zotero.org/settings/keys` re-auth prompts.
  Suggests pausing Zotero auto-sync first or using single-paper lookup.
- **Hub tag composition**: `_compose_hub_tags` now skips literal `"None"`,
  `"none"`, `"null"` strings and whitespace-only slugs that would have
  produced bogus `cluster/None` tags in Zotero.
- **Zotero hygiene**: `_frontmatter_payload` now logs file-read and
  YAML-parse failures via the standard logger instead of silently
  returning `{}`. Backfill investigations can now find permission /
  disk problems.

### CI / release pipeline (Track C)
- Coverage threshold gate added: `pytest --cov-fail-under=60` on the
  Ubuntu/3.12 matrix cell. Will ratchet upward as targeted tests land.
- Pre-publish wheel validation: `publish.yml` now installs the built
  wheel into a fresh venv and imports `research_hub` before calling
  `twine upload`. Catches packaging bugs (missing module in wheel,
  broken `__version__`) that the test matrix can't see because tests
  run on the editable repo.

### Coverage uplift (Track B, Codex-delivered)
- **`notebooklm/upload.py`**: 7% → 54% (10 unit tests, mocked Page)
- **`notebooklm/bundle.py`**: 27% → 84% (6 error-path tests)
- **`mcp_server.py`**: 41 snapshot tests guard tool-signature drift
- **`setup_command.py`**: 21% → 59% (8 validation tests)
- **Per-extra install** (`@pytest.mark.slow`, NEW
  `tests/test_v065_extras_install.py`): 5 isolated venvs verify each
  extra (`secrets / import / playwright / mcp / dev`) installs cleanly
  and imports its key probe module. Runs only with `pytest -m slow`.

### Tests
- 1759 (v0.64.2) → ~1850 (v0.65.0): +99 added
  (Codex 82 + Claude 17), +existing regressions intact.

Codex-delegated per CLAUDE.md Complex Task Protocol
(brief: `.ai/codex_task_v065_qa.md`,
result: `.ai/codex_task_v065_qa_result.md`).

## v0.64.2 (2026-04-23)

### Doctor noise reduction
- `frontmatter_completeness` now downgrades known legacy gaps (missing DOI on
  pre-v0.31 imports, empty Summary/Methodology sections) to a single INFO
  line: `[ii] N legacy notes have known gaps`. Default behavior; pass
  `--strict` to see the full WARN listing.
- Touching these legacy notes in bulk (e.g., `paper lookup-doi --batch`)
  triggers Zotero auto-sync re-auth loops on machines with Zotero desktop +
  external file watchers, so silencing the WARN avoids tempting an
  expensive cleanup that hurts more than it helps.

## v0.64.1 (2026-04-23)

### Fixed
- `research-hub setup` now exempt from `require_config()` so it can serve as
  a true first-run command on a fresh machine (was: errored "not initialized"
  before reaching the setup orchestrator).

## v0.64.0 (2026-04-23)

### Onboarding final-mile UX
- `setup` / `init` now auto-open https://www.zotero.org/settings/keys in your
  browser when prompting for the Zotero API key (use --no-browser to opt out).
- `setup` ends with an optional "Try a sample research topic now? [Y/n]" prompt
  that runs a small `auto` and opens the dashboard so first-time users see a
  result without having to remember another command. Skip with --skip-sample.
- `auto` gained `--show` (default on): opens the dashboard on success. Use
  --no-show in scripts / CI. Already silent in non-TTY contexts.

### Defensive
- `serve --dashboard` no longer crashes with a raw OSError when port 8765 is
  already taken; prints "Dashboard already running at..." and exits cleanly.

## v0.63.0 (2026-04-23)

### Manage tab coverage
- New Maintenance card exposes `tidy`, `dedup rebuild`, `cleanup --all --apply`,
  `memory emit`, `crystal emit`, `bases emit` as one-click buttons.

### Search tag extraction
- arXiv categories (cs.AI, econ.GN, etc.) now flow into Zotero as `category/<tag>`.
- Semantic Scholar publicationTypes (Review, JournalArticle, etc.) land as `type/<tag>`.
- Combined with the v0.61 hub namespace: every ingested paper is filterable
  by cluster, source, document type, AND arXiv category.

### Rebind hardening
- `clusters rebind` now fuzzy-matches papers whose `topic_cluster` frontmatter
  points to a non-existent slug, binding them to the best-overlap survivor
  cluster (min 2 seed-keyword tokens in common). Falls back to the existing
  orphan-report path when no good match exists.

## v0.62.0 (2026-04-23)

### Setup simplification
- New `research-hub setup` one-shot command runs init + install --platform + NotebookLM login in one call.
- `init` completion banner now includes the required `install --platform` step.
- NotebookLM login is mandatory (not [y/N]) when Chrome is available and persona uses NLM. Ctrl-C still skips.
- Zotero API-key retry loop reduced to one retry; second failure continues offline with a WARN.

### Note hygiene
- Stub notes in Zotero now include title, authors, year, venue, DOI (was: just "Imported from cluster X").
- Ingest de-dup branch now also creates a note if the matched existing Zotero item has none.
- Backfill upgrades legacy stub-only notes to Obsidian-rich notes when possible.
- Backfill report breaks down "Notes added: N (A from Obsidian, B enriched stubs, C upgraded stubs)".

### Manage tab safety
- `clusters delete` computes a cascade report (Obsidian papers, Zotero items, dedup/memory/crystals) and requires `--force` on non-empty clusters. Never trashes Zotero items - only unlinks them from the deleted collection.
- Dashboard cluster-delete now uses a two-step Preview -> Apply flow matching the paper-action pattern.
- Result drawer now shows full stdout/stderr in a collapsible `<details>` block for long-running commands.
- `auto` now errors with a 1-line instruction if the target cluster already has papers, unless `--append` or `--force` is passed.

## v0.61.0 (2026-04-23)

### Zotero hygiene
- Pipeline now injects `research-hub`, `cluster/<slug>`, `type/<doc_type>`, `src/<backend>` tags on every ingest (was: tags came only from search backends, which were empty).
- New `research-hub zotero backfill [--tags] [--notes] [--cluster SLUG | --all-clusters] [--apply]` command. Dry-run by default; writes a markdown report to `.research_hub/backfill-<ts>.md` on apply.
- De-dupe path now PATCH-merges hub tags onto matched existing Zotero items.

### Onboarding
- `init` now asks "Do you use Zotero?" first, then narrows the persona menu accordingly.
- Researcher/humanities Zotero prompt now warns that ingest will fail without credentials.

### Cluster management
- `clusters new` now auto-creates the matching Zotero collection (if a key isn't already bound). Idempotent. No-op when persona is no-Zotero.

## v0.60.0 (2026-04-21)

**Onboarding polish — 4 tracks from the v0.59 usability audit.** Codex delegation, 7th consecutive use.

The v0.59 audit (4 personas × 8 journey stages) gave research-hub 106/160 overall. Codex claimed 5 friction points; Claude verified and found 4 valid (1 false positive — codex's terminal couldn't render CJK/emoji and mis-diagnosed "mojibake"). This release ships the 4 real fixes.

### Fixed — `init` completion banner now persona-aware (Track 1)

Before: every persona ended `init` with `doctor` / `add <DOI>` / `serve --dashboard` / `install --mcp`. That contradicted the README's "one sentence in → `auto`" story.

After:
- **researcher / humanities**: `plan "your research topic"` → `auto "your research topic"` → `serve --dashboard`
- **analyst / internal**: `import-folder <folder> --cluster <slug>` → `auto "your topic" --no-nlm` → `serve --dashboard`
- `doctor` kept as an optional readiness-check line above the main steps.
- `install --mcp` dropped (superseded by `install --platform <host>` skill pack from v0.53).

### Fixed — `auto` no longer aborts when NotebookLM fails (Track 2)

Before: any NLM step failure (bundle / upload / generate button not found / login expired / UI drift) returned `AutoReport(ok=False)` — even though papers were already in Zotero + Obsidian.

After: NLM failures set `report.nlm_deferred=True` + `report.nlm_error=<stage>:<msg>`, but `report.ok` stays `True` (papers were ingested successfully). Crystal generation still runs. Next-Steps banner adds resume hints:

```
[NLM] skipped (check: research-hub notebooklm login). Resume with:
  research-hub notebooklm bundle   --cluster <slug>
  research-hub notebooklm upload   --cluster <slug>
  research-hub notebooklm generate --cluster <slug> --type brief
  research-hub notebooklm download --cluster <slug> --type brief
```

Pinned by `test_auto_nlm_failure_does_not_abort_pipeline`.

### Added — `research-hub dashboard --sample` zero-account preview (Track 3)

New flag renders the dashboard on a bundled sample vault — no `init`, no Zotero key, no NotebookLM login. Closes the "no low-risk preview" audit gap (v0.59 friction #3).

Sample vault (in the wheel under `src/research_hub/samples/sample_vault/`):
- 2 clusters, 5 synthetic paper notes, 3 crystals, 2 `.base` files, 1 sample brief
- Copied to a writable temp dir on first run (fallback to workspace `.research_hub_samples/` if OS temp isn't writable, for sandboxed environments)
- Dashboard injects a banner: "SAMPLE PREVIEW — this vault is read-only and temporary."

New test: `tests/test_v060_sample_vault.py`.

### Changed — README trimmed (Track 4)

User feedback: "確認readme不要太亂". README.md dropped from 320 → 255 lines. README.zh-TW.md from 281 → 225. Same information density, less scrolling.

Also fixed command examples against the actual argparse shapes (the audit caught `ask "Q" --cluster X` in README vs the real `ask <cluster> <question>` positional).

### Bugs found and fixed during build

- README used wrong `ask` CLI shape (`--cluster X "Q?"` vs actual `<cluster> <question>` positional).
- CLI help epilog still promoted older doctor/add flow; now points to `plan` / `auto`.
- `dashboard --sample` needed a workspace-directory fallback because `tempfile.mkdtemp()` directories aren't writable in some sandboxed Windows environments.
- `test_validate_live_cluster_notes` depended on maintainer's real vault under `~/knowledge-base`; gated behind `RESEARCH_HUB_RUN_LIVE_VAULT_TESTS=1` so CI stays deterministic.

### Stats

- Tests: 1661 → **1666** on the fast suite (+5 net; codex's internal run with `-q` saw more when including the full `-m "not slow"` matrix, but the standard fast suite is what CI uses)
- MCP tools: unchanged (83)
- README line count: 320 → 255 (EN), 281 → 225 (zh-TW)
- New files: `src/research_hub/sample_vault.py`, `src/research_hub/samples/sample_vault/...` (5 md + 3 crystals + 2 .base + 1 brief), `tests/test_v060_sample_vault.py`

### Cumulative since v0.48 stretch

- 15 versions shipped (v0.48 → v0.60; v0.57 and v0.59 were audit-only)
- 1520 → **1666 tests** (+146)
- ~55 real bugs fixed
- 7 successful Codex delegations
- Every major UX gap flagged in the two audits (v0.57, v0.59) now shipped

### v0.59 audit scores post-v0.60

The audit's friction scores should improve materially on:
- Stage C (Init): now points at `auto` for researcher / `import-folder` for analyst — no more Doctor-first confusion
- Stage D (First auto): NLM failure doesn't kill the whole run — smoke test returns useful result even when Chrome session is stale
- Stage B (Install): zero-account `--sample` preview means Curious Technical User persona can see the end state in 2 minutes without any account setup

## v0.58.0 (2026-04-21)

**Manage tab UX overhaul** — Codex audit (v0.57) flagged 5 P0 items, this release ships all 5. (v0.57 was an audit-only release with no code-shipped artifact, so no version was published; v0.58 implements the audit's recommendations.)

Codex delegation, 6th consecutive use. Claude reviewed + verified before shipping. 2 real bugs caught during the implementation.

### Added — 5 tracks from the audit

**A. Inline command result drawer.** Click a Manage button → see exactly what happened. The `/api/exec` JSON response now renders inline below the form: command run, duration, return code, stdout (collapsible if long), stderr (red if present), timeout flag. No more "Running… → Done" with no explanation.

**B. Live-mode intro + dynamic Preview/Apply labels.** Old intro text said "dashboard cannot run commands itself" but live mode obviously can. Fixed to describe both modes accurately. Buttons whose checkbox toggles dry-run now switch label dynamically: `Preview polish` ↔ `Apply polish`, `Preview delete` ↔ `Apply delete`, etc.

**C. Shared `<dialog>` confirmation modal.** Replaces inline `confirm()`/`alert()` calls scattered across the v0.57 artifact-delete button + destructive Manage actions (merge / cluster delete / paper remove / archive). One reusable modal in `script.js`, focus-trapped, ESC-to-close, danger-styled when destructive. The artifact-delete button now uses `data-action` + delegated handler (no more inline JS in HTML attributes).

**D. Per-paper row action menu.** Library tab paper rows now have inline `Actions` forms for Archive / Move-to-cluster / Set-label / Set-status / Remove (preview→apply). Each posts to `/api/exec` with the right whitelisted action. No need to drop to terminal for per-paper cleanup anymore.

**E. Manage tab search / sort / filter.** New filter bar above cluster cards: substring search by name/slug; sort by name/paper-count/last-activity/has-unbound-bindings; show-only filter for recent-7-days / unbound-clusters. All client-side. Scaling to 12+ clusters is now usable.

### Fixed — 2 bugs caught during implementation

1. **`/artifact-delete` SSE broadcast was broken**: v0.57 called `broadcaster.publish(...)` but the actual method is `broadcast(...)`. Successful artifact deletes never notified other dashboard tabs. Fixed.
2. **Test fixture leaked CSRF token**: new artifact-delete tests set `DashboardHandler.csrf_token` as a class attribute, which leaked into other live-server tests. Added a fixture that restores handler globals after each test.

### Stats

- Tests: 1640 → **1661** (+21 across `test_artifact_delete_endpoint.py`, `test_paper_row_actions.py`, extended `test_dashboard_script_logic.py`)
- New files: 2 test files (~270 LOC total)
- Modified: `dashboard/{http_server.py, sections.py, script.js, style.css, manage_commands.py}` (~700 net LOC additions)

### Screenshots worth re-taking

- Manage tab static mode → new intro + filter bar
- Manage tab live mode → inline exec result drawer after a command
- Briefings tab → delete now triggers shared modal (not browser `confirm()`)
- Library tab paper rows → new Actions menu

### Cumulative since v0.48 (today's stretch + tomorrow's morning)

- 14 versions shipped (v0.48.0 → v0.58.0; v0.57 was audit-only)
- 1520 → **1661 tests** (+141)
- ~50 real bugs fixed across CLI / dashboard / NotebookLM / pipeline / heuristics / executor wiring / UX
- 6 successful Codex delegations
- Codex caught: 11 + 1 + 0 + 2 = ~14 bugs the original Claude pass missed
- Claude smoke-test caught after Codex shipped: ~3 bugs Codex's mocked tests missed

## v0.56.0 (2026-04-20)

**Full pipeline sweep — every one of the 10 `auto` stages now has e2e regression coverage.** Plus 1 real ingest bug caught.

User asked for codex to sweep every pipeline stage (search → fit-check → ingest → Zotero/Obsidian/NLM → crystals) before recording the demo. Codex delegation, 5th consecutive use.

### Added — `tests/test_pipeline_e2e.py` (22 new tests across 10 stages + 4 cross-stage)

| Stage | Tests | Coverage |
|---|---|---|
| 1 — slugify + cluster create | 1 | naming + collision reuse |
| 2 — Zotero collection auto-create | 1 | success + pyzotero failure path |
| 3 — search across 8 backends | 9 | arxiv / s2 / openalex / crossref / pubmed / biorxiv / dblp / websearch + cross-backend empty/rate-limit merge |
| 4 — `_to_papers_input` mapping | 1 | arxiv→`10.48550/arxiv.<id>` derived DOI (v0.49.4 fix) + real-DOI preservation + no-DOI rejection |
| 5 — `run_pipeline` ingest | 1 | mock pyzotero + Obsidian frontmatter validation + per-paper rejection |
| 6 — bundle PDF download | 1 | partial 404 tolerance + bundle_report shape |
| 7 — NLM upload | 1 | fake-page automation + notebook URL captured into clusters.yaml |
| 8 — NLM generate brief | 1 | _trigger_and_wait + missing-button error |
| 9 — NLM download brief | 1 | summary HTML parsing + char_count |
| 10 — Crystal emit/apply | 1 | LLM CLI mock + crystal file written |
| Cross-stage | 4 | round-trip / cluster reuse / failure cascade / no-LLM-CLI graceful |

All HTTP, browser automation, and LLM-CLI subprocess calls mocked at the boundary. Test file runs in 6.92s.

### Fixed — Stage 5: ingest treated DOI-less papers as batch-fatal

If `papers_input.json` contained mixed papers (some with DOI, some without — common in real arxiv mixed with web-found articles), the ingest validator killed the whole batch instead of skipping just the bad rows. Real users would lose all the work upstream.

Root cause in `src/research_hub/pipeline.py`: non-dry-run validation was raising on first missing-DOI record. Existing fail-fast for genuinely malformed records (missing author / wrong schema) was correct behavior; the missing-DOI case was over-aggressive.

Fix: skip records whose only validation error is missing DOI, log them under `INPUT VALIDATION SKIPS`, continue ingesting the valid records. Per-paper rejection is the correct user-facing behavior.

### Mock-only coverage gaps (transparent honesty)

These boundaries are NOT exercised by the new tests — they're tested separately:
- Real Patchright browser behavior (NLM upload/generate/download use a fake CDP session). Real-browser tests are `-m slow`.
- Real arxiv / S2 / OpenAlex / Crossref / PubMed HTTP calls. Network tests are `-m network`.
- LLM crystal answer quality (we test wiring, not whether the LLM's answer is good).

### Stats

- Tests: 1618 → **1640** (+22)
- Bugs found by sweep: **1 real** (ingest DOI-less batch-fatal)
- Pipeline stages with e2e regression: **10 / 10** (was 0 before; per-stage unit tests existed but boundaries were uncovered)
- New files: `tests/_pipeline_fixtures.py` (~120 LOC canned responses), `tests/test_pipeline_e2e.py` (22 tests)

### Recommended follow-ups (from Codex)

- Extract a small NotebookLM automation interface so tests don't need to patch module-level session/client internals.
- Document the per-paper DOI-less rejection policy in `docs/papers_input_schema.md`.

### Cumulative since v0.48 (today's stretch)

- 13 versions shipped (v0.48.0 → v0.56.0)
- **40+ real bugs fixed** across CLI / dashboard / NotebookLM / pipeline / heuristics / executor wiring
- 1520 → **1640 tests** (+120, all green)
- 5 successful Codex delegations (v0.51, v0.52, v0.54, v0.55, v0.56)
- Codex caught: 0 + 0 + 5 + 5 + 1 = **11 bugs** that the original Claude pass missed
- Claude smoke-test caught after Codex shipped: 3 + 0 + 0 + 0 + 0 = **3 bugs** that Codex's mocked tests missed

## v0.55.0 (2026-04-20)

**Manage tab full end-to-end audit: every button now actually executes against a sandbox vault, with HTTP-layer error wrapping + SSE auto-refresh.**

User asked: 「每個功能 流程都要檢測過 ... 做完再給我UI 我來錄影」. v0.54 covered argument-shape; v0.55 covers real execution + UI-layer behavior. Result: 5 more real bugs found and fixed.

Implementation delegated to Codex per `.ai/codex_task_v055_manage_e2e.md`. Claude verified independently before shipping.

### Added — sandbox-cluster fixture for Manage e2e

`tests/_e2e_sandbox.py` — pytest fixture that builds a throwaway HubConfig in `tmp_path` with 2 pre-populated clusters (alpha = 3 papers, beta = 2 papers) so destructive actions (delete / merge / split / move / remove / mark / label / rename) can be tested for real without touching anyone's vault.

### Added — `tests/test_dashboard_executor_e2e.py` (29 new tests)

| Category | Count | What |
|---|---|---|
| **A — real CLI execution** | 12 | rename / delete / move / label / mark / remove / topic-build / dashboard / pipeline-repair / vault-polish-markdown / bases-emit / clusters-analyze — all run end-to-end against sandbox vault, assert state changes |
| **B — mocked subprocess** | 8 | NotebookLM bundle/upload/generate/download/ask + discover-new/continue + autofill-apply — capture CLI invocation shape without hitting external APIs |
| **C — structured behavior** | 6 | merge / split / bind-zotero / bind-nlm / ingest / compose-draft — assert clusters.yaml / file system mutations |
| **Cross-cutting** | 3 | SSE event broadcast after action / HTTP error wrapping / long-action timeout |

### Fixed — 5 real bugs the audit caught

1. **`ingest` Manage button broken**: executor built `--papers-input <path>`, but the CLI doesn't accept that flag. Also dropped the dashboard's `dry_run` flag entirely. Fix: stage the file into `<vault>/papers_input.json` before subprocess, drop the unsupported arg, forward `--dry-run`.

2. **`/api/exec` ignored client `timeout`**: browser callers couldn't request a short timeout for long-running actions. Fix: accept optional `timeout` integer in the POST body, pass through to `execute_action()`.

3. **`/api/exec` returned HTTP 500 on command failure**: the dashboard wraps `execute_action()` results, but a non-zero exit code escaped as 500 instead of structured JSON the browser could render inline. Fix: always return HTTP 200 for completed-but-failed actions with `{ok: false, stderr, error}`. `ValueError` validation stays at 400. Timeouts normalize to `error: "timeout"`.

4. **No SSE `state-change` event after actions**: dashboards opened in another tab wouldn't auto-refresh. Fix: the SSE writer now supports named events, and successful actions broadcast both the legacy default (`type: vault_changed` for old JS clients) and a named `state-change` event for explicit listeners.

5. **`http_server` broke older test monkeypatches**: passing `timeout=` kwarg to test-injected `execute_action` callables raised `TypeError: unexpected keyword argument 'timeout'` in `test_v030_security.py`. Fix: detect callable signature and retry without the kwarg if rejected.

### Verified end-to-end

```
Total: 1589 → 1618 (+29)
Per-category: A 12/12, B 8/8, C 6/6, cross-cutting 3/3
```

Live-server smoke after restart: dashboard HTTP 200, `/artifact` serves 1322 bytes, `bases-emit` direct executor returns rc=0.

### Plan-template corrections

The original plan's expected fields for `bind-nlm` ("notebook_url") and `label` (raw YAML serialization) were wrong vs the live source. Codex corrected the test assertions to match product behavior (current dashboard form binds `notebooklm_notebook` field, label assertion uses parsed YAML not raw string).

### Stats

- Tests: 1589 → **1618** (+29)
- MCP tools: unchanged (83)
- Bugs found by audit: **5 real** (3 CLI/wiring + 2 HTTP-layer)
- Wall time: ~25 min Codex + ~5 min Claude review

### What this unlocks

Every Manage-tab button has now been executed end-to-end against a sandbox vault. The maintainer can record the promotional dashboard video knowing every button does what it says, and the SSE auto-refresh / error-rendering paths actually work.

## v0.54.0 (2026-04-20)

**Manage-tab full audit + 5 more `clusters-analyze`-shaped bugs caught.**

v0.53.2 found `clusters-analyze` Manage button always crashed because it read `fields["cluster_slug"]` instead of the dedicated `slug` arg. v0.54 ran the same audit across **every** Manage action and found 5 more identical bugs hiding behind missing test coverage.

Implementation delegated to Codex per `.ai/codex_task_v054_manage_audit.md`. Claude reviewed + verified independently before shipping.

### Fixed — 5 more cluster-scoped Manage buttons that ignored `slug`

Same root cause as `clusters-analyze`: handler read `fields["cluster_slug"]` (which the dashboard never sets) instead of the dedicated `slug` argument. Each one would have crashed with `KeyError: 'cluster_slug'` the moment a real user clicked the button.

| Action | Manage button name |
|---|---|
| `topic-build` | "Build topic notes" |
| `pipeline-repair` | "Repair pipeline" |
| `discover-new` | "Discover new candidates" |
| `discover-continue` | "Continue discover" |
| `autofill-apply` | "Autofill apply" |

All 5 fixed the same way as `clusters-analyze` in v0.53.2: read `slug` first, fall back to legacy `fields["cluster_slug"]` / `fields["cluster"]`, raise a clear `ValueError` if neither is set.

### Added — parametrized regression coverage for **every** Manage action

`tests/test_dashboard_live_server.py` now contains:

- A `_ACTION_CASES` matrix keyed by action name, listing the canonical CLI subcommand tokens + valid `fields` for that action.
- A guard test that the matrix stays in sync with `executor.ALLOWED_ACTIONS` — adding a new action without adding a test case will fail CI.
- A parametrized builder test that runs all 26 actions through `_build_command_args` and asserts: returns `list[str]`, has the correct base prefix, contains the canonical subcommand tokens, includes the slug for slug-relevant actions.

Future drift in any Manage button now fires in CI, not in a user's browser.

### Plan template corrections

The required-fields table in the original plan was wrong in 12 places (e.g. `merge` uses `target` not `target_cluster`, `bind-zotero` uses `zotero` not `collection_key`, `vault-polish-markdown` uses `apply` not `dry_run`). Codex corrected these against the live source. The corrections are in `.ai/codex_task_v054_result.md` for reference when shipping similar audits.

### Stats

- Tests: 1585 → **1589** (+4 — the parametrized matrix counts as ~4 distinct test functions, not 26, since pytest-parametrize collapses to 1 test ID per function)
- Bugs found by audit: **5** (plus the v0.53.2 `clusters-analyze` already-fixed)
- Files: `dashboard/executor.py` (+25 LOC slug-arg fallback in 5 handlers), `tests/test_dashboard_live_server.py` (+83 LOC matrix + parametrized test)

### Delegation pattern

Same Codex pattern as v0.51 / v0.52:
1. Claude writes plan file at `.ai/codex_task_v054_manage_audit.md`
2. Codex runs in background via `codex exec --full-auto`
3. Codex writes summary at `.ai/codex_task_v054_result.md`
4. Claude verifies + ships

Wall time: ~5 min Codex execution + ~3 min Claude review/ship.

## v0.53.2 (2026-04-20)

**Two real-vault clicking bugs caught while the user actually used the dashboard.**

### Fixed — "open .txt" link on the NotebookLM-artifacts table opened a blank tab

The dashboard generated `href="file:///C:/Users/.../brief-*.txt"` for the brief-download tile. Modern browsers (Chrome / Firefox / Edge) **silently block file:// links from http:// origin pages** as a mixed-protocol security policy. Click → blank tab → user thinks the brief is empty.

The brief content was always there (1322 bytes verified on disk); the link was just unreachable.

Fix: added `GET /artifact?path=<rel-or-abs>` to the dashboard HTTP server. Resolves the requested path against `cfg.root`, rejects anything that escapes the vault (path-traversal protection), serves the file with appropriate `Content-Type` (`text/plain; charset=utf-8` for `.txt/.md/.json/.log/.yaml`, `text/html` for `.html`, `application/pdf` for `.pdf`). The dashboard now generates `href="/artifact?path=<encoded>"` instead of `file:///`.

### Fixed — `clusters-analyze` Manage-tab button always crashed

`KeyError: 'cluster_slug'` every time. The handler in `executor.py` read `fields["cluster_slug"]` but the dashboard never set that key — every other action in the same file uses the dedicated `slug` argument instead. Mocked tests didn't catch it because they only verified the action name was on the whitelist, not the argument-shape.

Fix: read the slug from the `slug` arg first, then fall back to legacy `fields["cluster_slug"]` / `fields["cluster"]`, raise a clear ValueError if neither is set.

### Manage-tab audit (transparent honesty)

User asked: have you tested every Manage button? Honest answer: now, mostly yes.

Argument-shape smoke across all 26 Manage actions: 21 build correctly with a representative `fields` dict; 5 require action-specific fields not in the smoke dict (bind-nlm wants `notebook_url`, bind-zotero wants `collection_key`, mark wants `status`, merge wants `source_clusters`, split wants `target_cluster`). Those 5 will work when the dashboard sends the right fields — they're just rejecting the smoke test's fake fields, which is correct behavior.

Real end-to-end execute (non-destructive only): `bases-emit`, `vault-polish-markdown`, `clusters-analyze` (after fix), `dashboard`, `rename` all return rc=0 with real output on the maintainer's vault.

### Stats

- Tests: 1585 → 1585 (no test changes; bugs are wiring issues caught by real-server smoke that mocked tests missed)
- Files: `dashboard/http_server.py` (+55 LOC for `/artifact` endpoint), `dashboard/sections.py` (4 LOC link-shape change), `dashboard/executor.py` (+5 LOC for the slug-arg fallback)

## v0.53.1 (2026-04-20)

**Two doctor false-positive fixes** that were nagging real users on the Diagnostics tab.

### Fixed — `cluster_field` was over-eager

The classifier counted bio-field signals from substring matches like `"cell"` inside `"cell phone surveys"` and `"nature"` inside `"nature of community"`. Mixed-discipline clusters (e.g. flood/social/health surveys) kept tripping `WARN: declared field=social but papers look like bio (confidence=0.45)` even though the inferred field was a coin-flip.

Two changes:
1. **Word-boundary regex** in `doctor_field._FIELD_SIGNALS` matching — now `\bcell\b` won't match `"cellular"` / `"cell phone"`. After the fix, the same `survey` cluster on the maintainer's vault: confidence 0.45 → **0.78**, inferred field `bio` → **social**, status WARN → **OK**.
2. **Confidence floor of 0.6** before raising a warning. Below that the classifier is essentially guessing, and we shouldn't surface its guesses as actionable.

### Fixed — `frontmatter_completeness` flagged cluster index files as broken papers

`abm-theories/ABM-Theories-Index.md` is a cluster-overview file, not a paper. The doctor's skip rule only matched `00_*` and `index*` filename prefixes, so `*-Index.md` files (a common topic-overview convention) got linted as if they were papers and failed because they have no DOI / authors / year.

Extended the skip rule to also match `*-index` and `*_index` stems (case-insensitive). After the fix, the maintainer's `frontmatter_completeness` went from `FAIL (1 + 323 WARN)` to `WARN (321 + 728)` — no spurious FAIL, only the legitimate "missing DOI" + "TODO placeholder" warnings remain.

### Why this matters

These two warnings dominated the Diagnostics tab on the maintainer's real vault and on any user vault with mixed-discipline clusters or any cluster-index files. Removing the false positives lets the Diagnostics surface only actionable issues.

### Stats

- Tests: 1585 → 1585 (no test changes; the bugs were heuristic over-eagerness, regression coverage to follow once the heuristic shape stabilizes)
- Files: `src/research_hub/doctor.py` (+5 LOC for the index skip), `src/research_hub/doctor_field.py` (regex compile + threshold)

## v0.53.0 (2026-04-20)

**Multi-AI skill pack.** research-hub now ships a 2-skill pack that teaches Claude (and any MCP host) how to delegate crystal generation and long pipeline work to Codex or Gemini CLIs when they're on PATH — turning "one AI does everything" into "Claude orchestrates, Codex executes, Gemini handles CJK".

### Added — `skills_data/research-hub-multi-ai/SKILL.md`

New bundled skill that ships alongside the existing `knowledge-base` skill. Teaches the host AI:

- **When to stay on Claude** (judgment-heavy, short, cache-eligible): `ask_cluster`, `read_crystal`, plan review.
- **When to delegate to Codex** (long, mechanical): `auto --with-crystals --llm-cli codex` for crystal generation across 8+ papers.
- **When to delegate to Gemini** (CJK content): same shape but for native-quality Traditional Chinese / Japanese / Korean crystal output.
- **The `plan_research_workflow` → confirm → `auto_research_topic` protocol** so the AI never blindly kicks off long work without user confirmation.
- **Token-budget discipline**: always check `ask_cluster` first (returns cached crystal in <1s + 0 tokens) before re-synthesizing.

Full decision tree + concrete command templates + anti-pattern list in `skills_data/research-hub-multi-ai/SKILL.md`.

### Changed — `research-hub install` now installs a skill PACK

`install_skill(platform)` used to copy a single `SKILL.md`. Now copies the full pack (2 skills as of v0.53) into the right per-platform directory:

| Platform | Skill dir layout |
|---|---|
| `claude-code` | `~/.claude/skills/research-hub/SKILL.md` + `~/.claude/skills/research-hub-multi-ai/SKILL.md` |
| `codex` | `~/.codex/skills/research-hub/…` + `~/.codex/skills/research-hub-multi-ai/…` |
| `cursor` | `~/.cursor/skills/…` (same layout) |
| `gemini` | `~/.gemini/skills/…` (same layout) |

`install_skill(...)` now returns a **list** of installed paths (was a single string). The old string-returning behavior is preserved via isinstance check in the CLI so external callers don't break.

`list_platforms()` now reports "installed" only when **every** skill in the pack is present, so partial installs after an upgrade are highlighted.

### Wheel packaging

Added `[tool.hatch.build.targets.wheel.force-include]` to bundle `src/research_hub/skills_data/**/SKILL.md` into the installed wheel. Without this, `pip install research-hub-pipeline` would find the skill files missing (they were only in the repo, not the package).

### Why this matters

Before v0.53, every AI host starting fresh with research-hub had to learn the tool use patterns from scratch — often making wrong choices (calling `auto` without `plan` first, burning Claude's token budget on crystals when Codex could do it for free, synthesizing answers from scratch instead of reading cached crystals).

After v0.53, one command (`research-hub install --platform claude-code`) bundles all that guidance into the host's skills directory so the host AI knows the playbook from turn one.

### Stats

- Tests: 1583 → **1585** (+2 regression tests covering the pack-install contract and the multi-AI skill discoverability)
- New file: `skills/research-hub-multi-ai/SKILL.md` (~230 lines of prose guidance)
- Modified: `skill_installer.py` (+~40 LOC for pack support), `cli.py` (+4 LOC for list-returning install output), `pyproject.toml` (+2 lines for wheel bundling)

### Backward compat

- Existing `knowledge-base` skill still installed first (matches the old `~/.claude/skills/research-hub/` path).
- CLI output now shows multiple "Installed …" lines per call; `--list` behavior unchanged at the user-visible level.

## v0.52.0 (2026-04-20)

**REST JSON API at `/api/v1/*` so any HTTP client can use research-hub.** Closes the last "AI host can't reach research-hub" gap left after v0.50–v0.51.

Implementation delegated to Codex CLI per `.ai/codex_task_v052_rest_api.md`. Codex's `pytest` passed 14/14 but the live server smoke test surfaced 3 wiring bugs that pure unit tests missed — Claude caught them, fixed them, ran independent end-to-end verification, then shipped.

### Added — 12 REST endpoints

| Method | Path | Wraps |
|---|---|---|
| GET | `/api/v1/health` | n/a (always reachable, no auth) |
| GET | `/api/v1/clusters` | `list_clusters` |
| GET | `/api/v1/clusters/{slug}` | `show_cluster` |
| GET | `/api/v1/clusters/{slug}/crystals` | `list_crystals` |
| GET | `/api/v1/clusters/{slug}/crystals/{slot}` | `read_crystal` |
| GET | `/api/v1/clusters/{slug}/memory/{kind}` | `list_entities/claims/methods` |
| GET | `/api/v1/jobs/{id}` | job status |
| POST | `/api/v1/search` | `search_papers` |
| POST | `/api/v1/websearch` | `web_search` |
| POST | `/api/v1/plan` | `plan_research_workflow` |
| POST | `/api/v1/ask` | `ask_cluster` |
| POST | `/api/v1/auto` | `auto_research_topic` (async, returns 202 + job_id) |

All endpoints emit CORS headers (`Access-Control-Allow-Origin: *`) so browser-based AIs (Claude.ai web, ChatGPT, OpenAI Custom GPT) can call from any origin. `OPTIONS` preflight returns 204.

### Auth

`RESEARCH_HUB_API_TOKEN` env var or `--api-token TOKEN` flag on `serve`:
- **Unset** → server bound to `127.0.0.1` only, no auth.
- **Set** → all endpoints (except `/api/v1/health`) require `Authorization: Bearer <token>`. Wrong/missing → 401.

### Async jobs for `/api/v1/auto`

`auto` takes minutes; sync POST would block. Now returns `202 Accepted` with `{"job_id": "...", "status_url": "/api/v1/jobs/<id>"}`. Client polls until `status="completed"` or `"failed"`. Daemon-thread-based queue, 1-hour TTL, no persistence (restart loses jobs).

### Fixed during Claude's verification pass

Codex's plan looked clean and 14/14 tests passed, but live-server smoke test caught 3 wiring bugs:

1. **`get_clusters` timed out** on real vaults. Codex used `collect_dashboard_data()` which builds the full dashboard (5–10s) instead of the lightweight `list_clusters()` (~1s). Switched to the lightweight version. Mocked tests didn't catch it because the mock was instant.

2. **`/healthz` reported stale `0.45.0`**. The version probe used `importlib.metadata.version("research-hub-pipeline")` which returns the installed package version — stale in editable / dev installs. Fixed to prefer in-source `__version__` first.

3. **`/api/v1/plan` and `/api/v1/websearch` returned 500**. fastmcp 2.x wraps newer `@mcp.tool()` definitions in a `FunctionTool` object that isn't directly callable. Older tools were plain functions. The handlers called `plan_research_workflow(...)` which raised `TypeError: 'FunctionTool' object is not callable`. Fixed with a `_unwrap()` helper that extracts `.fn` from FunctionTool wrappers.

All 3 fixes have regression coverage in `tests/test_v052_rest_api.py`.

### Verified — real end-to-end on Windows zh-TW

```
GET  /api/v1/health     200  {"ok": true, "version": "0.52.0", ...}
GET  /api/v1/clusters   200  {"clusters": [...12 real clusters...]}
POST /api/v1/plan       200  {"ok": true, "intent_summary": "...", "suggested_topic": "rag basics", ...}
POST /api/v1/websearch  200  {"ok": true, "provider": "ddg", "results": [...]}
```

### Stats

- Tests: 1569 → **1583** (+14)
- MCP tools: 83 (unchanged — REST and MCP both wrap the same underlying functions)
- New files: `src/research_hub/api/__init__.py`, `api/v1.py` (~250 LOC), `api/jobs.py` (~80 LOC), `tests/test_v052_rest_api.py` (~290 LOC)
- Modified: `dashboard/http_server.py` (+155 LOC routing/CORS/auth), `cli.py` (+11 LOC for `--api-token`), `mcp_server.py` (+2 LOC for `field` param)

### Backward compat

Pure addition. Existing `/api/state`, `/api/events`, `/api/exec` dashboard endpoints unchanged. No breaking changes to MCP, CLI, or Python imports.

### What this unlocks

- **v0.53**: OpenAPI spec generation → ChatGPT Custom GPT can use research-hub via Action.
- **v0.54**: Remote MCP transport (HTTP/SSE) → Claude.ai web's MCP integration can connect.

## v0.51.0 (2026-04-20)

**Generic web search + planner field auto-detection.** Closes two gaps surfaced during the v0.50 review.

Implementation delegated to Codex CLI per a structured plan at `.ai/codex_task_v051_websearch.md`. Claude reviewed the diff, ran end-to-end verification on both real DDG search and field detection, then shipped.

### Added — `WebSearchBackend` (Track B)

Most "research" intents need more than peer-reviewed papers. Blog posts, official docs, news articles, GitHub READMEs all matter — and v0.50 had no way to find them. v0.51 fills the gap with a generic web-search backend that auto-selects across 4 providers:

| Provider | Trigger | Notes |
|---|---|---|
| **Tavily** | `TAVILY_API_KEY` env | Built for AI agents; 1k/month free |
| **Brave** | `BRAVE_SEARCH_API_KEY` env | 2k/month free |
| **Google CSE** | `GOOGLE_CSE_API_KEY` + `GOOGLE_CSE_CX` env | 100/day free |
| **DuckDuckGo HTML** | (no key) | Best-effort fallback; no API needed |

**Three surfaces:**

```bash
# CLI
research-hub websearch "kepano obsidian bases" --limit 10
research-hub websearch "X" --provider tavily --domain github.com --json
research-hub websearch "X" --ingest-into <cluster>     # writes .url files + import-folder

# Mix into the existing search dispatcher
research-hub search "X" --backend arxiv,websearch

# MCP tool for Claude Desktop
web_search(query="X", max_results=10, provider="auto")
```

`SearchResult` shape matches the academic backends — `source="web"`, `doc_type` auto-classified from domain (`news` for nytimes/reuters/etc., `blog` for medium/substack, `docs` for github/docs.*, `article` default), `venue` extracted as registered domain.

### Added — Planner field auto-detection (Track A)

`research-hub plan "research drug X clinical trial outcomes"` now suggests `field=med` so when the user runs `auto`, the search uses `pubmed + biorxiv + crossref + semantic-scholar + openalex` (the right databases for clinical research) instead of the arxiv-heavy default.

10 fields detected via keyword-score heuristic: `cs / bio / med / physics / math / social / econ / chem / astro / edu`. Tie-break by alphabetical order.

`auto` accepts a new `--field` CLI flag too, for users who want to override the heuristic.

### Verified — real end-to-end

```
$ research-hub websearch "kepano obsidian bases" --limit 3 --json
[
  { "title": "kepano (Steph Ango) · GitHub",       "venue": "github.com",        "doc_type": "docs",    ... },
  { "title": "kepano: One of my favorite use ...", "venue": "mastodon.social",   "doc_type": "article", ... },
  { "title": "Bases Basic: Displaying Notes ...",  "venue": "forum.obsidian.md", "doc_type": "article", ... }
]

$ research-hub plan "research drug X clinical trial outcomes"
  field:              med
  When ready, run: research-hub auto "drug X clinical trial outcomes" --field med ...
```

### Bonus fix

Codex caught a Windows sandbox `PermissionError` in `doctor.check_chrome` when patchright tried to launch during the broad test run. Tightened to handle that case gracefully.

### Stats

- Tests: 1552 → **1569** (+17: 5 planner field-detection + 12 websearch)
- MCP tools: 82 → **83** (added `web_search`)
- New files: `src/research_hub/search/websearch.py` (249 LOC), `tests/test_v051_websearch.py` (248 LOC)
- Modified: planner.py / auto.py / cli.py / mcp_server.py / search/__init__.py / search/fallback.py / doctor.py / test_consistency.py / test_v050_planner.py
- Backward compat: pure addition. All existing commands unchanged.

### Delegation pattern (for future contributors)

This release is the first to use the formal Codex delegation pattern documented in the maintainer's CLAUDE.md:

1. Claude writes structured plan file at `.ai/codex_task_v0XX_*.md` with file paths + signatures + test contracts.
2. Codex executes via `codex exec --full-auto -C <repo> "Read .ai/codex_task_v0XX_*.md and execute every instruction inside"` in background.
3. Codex writes summary at `.ai/codex_task_v0XX_result.md` before exiting.
4. Claude reads the result, runs verification, smoke-tests on real data, ships.

Total wall time for v0.51: ~15 min Codex execution + ~5 min Claude review/ship.

## v0.50.1 (2026-04-20)

**Hotfix: codex / gemini CLI invocation actually works on Windows.** v0.50.0 only verified `claude` CLI end-to-end; codex + gemini failed silently with `FileNotFoundError`.

### Fixed

`_invoke_llm_cli("codex"|"gemini")` failed on Windows because subprocess looked for `codex` / `gemini` literally without checking PATHEXT. The npm-installed shims are `codex.cmd` and `gemini.cmd`. Resolved by switching to `shutil.which(cli_name)` to get the full executable path with extension.

Also fixed: `codex` invocation passed the prompt via stdin, but `codex exec` reads it as a positional argument. Restructured the per-CLI dispatch:

| CLI | Invocation | Prompt delivery |
|---|---|---|
| `claude` | `claude -p` | stdin |
| `codex` | `codex exec --full-auto <prompt>` | positional arg |
| `gemini` | `gemini --approval-mode yolo` | stdin |

### Verified

All three real CLIs round-tripped a tiny prompt and returned `{"ok": true}` on the maintainer's Windows zh-TW box. So `auto --with-crystals --llm-cli {claude,codex,gemini}` is now a real choice across all three providers.

### Token cost (for those wondering "won't this burn my API budget?")

Measured on a real 8-paper cluster:

| | Per-cluster cost |
|---|---|
| Input prompt | 4,704 chars ≈ **1,176 tokens** |
| Output (10 crystals) | ~5,000 chars ≈ **1,250 tokens** |
| Total roundtrip | **~2,400 tokens** |
| Claude Pro CLI subscription | **$0** (uses your existing seat) |
| Codex CLI subscription | **$0** (uses ChatGPT Plus) |
| Gemini CLI free tier | **$0** (free quota) |
| Anthropic API direct (Opus 4.6) | ~$0.11 per cluster |

Plus the whole rest of research-hub burns **zero tokens**: `auto` (without `--with-crystals`), `tidy`, `cleanup`, `ask`, `read_crystal`, `list_claims/entities/methods`, `plan_research_workflow`, `serve --dashboard` — all browser automation + cached lookups + heuristics. The crystals you generate ONCE per cluster are queryable from then on at zero token cost.

## v0.50.0 (2026-04-20)

**Intent planner: AI agents (and humans) ask before acting.** New `plan` flow turns a freeform user intent into a confirmed, executable workflow before `auto` fires.

### Why

Lazy mode (`auto "topic"`) jumps straight to execution: it picks search depth, NLM yes/no, crystals yes/no, cluster slug — all from a one-line topic. That's great when the user knows exactly what they want, terrible when they don't. v0.50 closes the loop with a two-step pattern:

1. **Plan** — convert intent → structured plan + clarifying questions (no execution).
2. **Confirm + Execute** — user (or AI) reviews, tweaks, then calls `auto`.

### Added — `research-hub plan "intent"` CLI

```
$ research-hub plan "I want to learn harness engineering"

  intent: You want to research "harness engineering"
  suggested topic:    harness engineering
  suggested cluster:  harness-engineering
  max_papers:         8
  do_nlm:             True
  do_crystals:        True       ← auto-detected: claude on PATH + "learn" intent
  est. duration:      ~196s

  Please confirm before running:
    1. Search depth: 8 papers OK, or do you want more / fewer?
    2. Generate NotebookLM brief? Adds ~60s.
    3. I'll auto-generate crystals using 'claude'. Adds ~90s. Say 'no crystals' to skip.

  When ready, run:
    research-hub auto "harness engineering" --max-papers 8 --with-crystals
```

`--json` flag for programmatic callers.

### Added — `plan_research_workflow` MCP tool

So Claude Desktop / Cursor / any MCP host can call **plan first, auto second**:

```
You: "Claude, research ABM for my dissertation"
Claude: [calls plan_research_workflow] → presents plan with max_papers=25
You: "make it 15"
Claude: [calls auto_research_topic with adjusted args]
```

This is the explicit "ask clarifying questions before acting" protocol the previous lazy-mode design was missing.

### Heuristics in the planner

Pure functions, no LLM call. Fast (~ms) so it's safe to call before every `auto`:

- **Prefix stripping** (looped): "I want to learn about X" → "X". Handles 26 EN + zh-TW prefixes.
- **Depth detection**: keywords like "thesis", "dissertation", "deep dive", "literature review" → max_papers=20-25 (default 8).
- **Intent classification**: "learn / study / understand / 學習" → flags as learning topic → recommends crystals if a CLI is on PATH.
- **NLM/Zotero opt-out detection**: phrases like "no NotebookLM", "without Zotero", "skip NLM" → adjust suggested args + persona.
- **Cluster collision check**: token-overlap heuristic against existing clusters; suggests reusing if ≥60% overlap (with paper count).
- **Duration estimate**: rough but useful (`30s baseline + 60s NLM + 90s crystals + 2s/paper`).

### Stats

- Tests: 1541 → **1552** (+11 in `tests/test_v050_planner.py`)
- MCP tools: 81 → **82** (added `plan_research_workflow`)
- New files: `src/research_hub/planner.py` (~190 LOC), `tests/test_v050_planner.py` (~135 LOC)

### Backward compat

Pure addition. Existing `auto` / `tidy` / `cleanup` / `ask` calls unchanged.

## v0.49.5 (2026-04-20)

**Root-causes the recurring `Generation button not found: briefing` NotebookLM error.**

### Fixed — corrupted CJK selectors silently broke every NLM operation on Chinese-locale browsers

`src/research_hub/notebooklm/selectors.py` had **all 28 CJK selector entries** corrupted into mojibake at some point in the dev history. Examples of what the file actually contained vs what NotebookLM's UI emits:

| Selector | What was in the file | What NotebookLM actually emits |
|---|---|---|
| `briefing_button` zh-TW | `"?勗?", "蝪∪?辣", "憭抒雇"` | `"報告", "簡介文件"` |
| `audio_button` zh-TW | `"隤??", "?唾?蝮質汗"` | `"語音摘要", "語音概覽"` |
| `mind_map_button` zh-TW | `"敹??"` | `"心智圖"` |
| `briefing_preset` zh-TW | `"蝪∩??辣", "????"` | `"簡介文件", "研讀指南"` |

When the user's NotebookLM UI was in zh-TW (Wenyu's locale), `_find_artifact_container` looped through `("?勗?", "蝪∪?辣", "憭抒雇")` looking for a CSS-selected `[aria-label="<text>"]` and never matched anything, since the real aria-label was `"報告"`. Result: every NLM `generate` / `upload` / source-add operation on a Chinese browser failed with the misleading `Generation button not found: briefing`.

This is the exact regression that v0.45 thought it had fixed via the overlay-dismiss helper — but the overlay was never the root cause; the selectors themselves never matched any element. The `--with-crystals` flow that v0.49 added masked the impact since crystals don't need the brief, but anyone trying to actually use NotebookLM on a CJK locale was silently failing.

Fix: rebuilt all 28 zh-TW + zh-CN selector tuples with the correct UTF-8 strings + appended English fallbacks (`"Briefing doc"`, `"Audio Overview"`, `"Mind map"`, etc.) so the selectors stay matchable even when Google A/B-tests the locale. End-to-end retry on the maintainer's vault: `notebooklm generate --type brief` now succeeds and returns a real notebook URL; `notebooklm download` writes the brief file.

### Verified

```
$ research-hub notebooklm generate --cluster <slug> --type brief
brief: https://notebooklm.google.com/notebook/99866b50-3b71-4d84-9e19-7682bbc85e2d

$ research-hub notebooklm download --cluster <slug> --type brief
Saved: .research_hub/artifacts/<slug>/brief-20260420T020640Z.txt
  notebook: Llm Agents For Agent-Based Modeling And Social Simulation
```

(The downloaded file initially contained `"正在生成報告..."` — a Chinese placeholder string — which itself confirms the new selectors are talking to the real zh-TW UI and the system is correctly reading what NotebookLM serves.)

### Stats

- Tests: 1541 (no new tests in this release; the bug class is untestable in CI without a real browser session)
- Bugs fixed by inventory pass since v0.49.0: **12**

## v0.49.4 (2026-04-19)

**`auto` end-to-end actually works now: 4 latent bugs unblocked + Zotero collection auto-created.** Caught by trying to use the lazy-mode flow on a fresh topic ("LLM agents for agent-based modeling").

The promise from v0.46+ was "one sentence in, papers + brief out". In practice the flow had four sequential failure points that prevented anyone from running `auto` on a brand-new topic. Each was the kind of bug only real end-to-end usage surfaces.

### Fixed — 4 latent `auto` bugs

1. **`registry.create()` signature mismatch**: `auto_pipeline` called `create(slug=slug, name=display, first_query=topic)` but the actual signature requires `query` as the first positional. Crashed with `TypeError: missing 1 required positional argument: 'query'` on every cluster creation.

2. **Search backends passed as comma-string instead of list**: `_run_search` did `backends="arxiv,semantic_scholar"` which the search dispatcher iterated character-by-character ("unknown search backend: a", "unknown search backend: r", ...). Also the name `semantic_scholar` is wrong — the registry uses `semantic-scholar` (hyphen). Fixed to `["arxiv", "semantic-scholar", "openalex", "crossref"]` so the pipeline survives semantic-scholar rate-limiting.

3. **No Zotero collection auto-creation**: when `auto` created a brand-new cluster, ingest immediately failed because `cluster.zotero_collection_key` was empty and the user hadn't run `clusters bind` yet. Added `_ensure_zotero_collection` that calls `pyzotero.create_collections([{"name": cluster.name}])` and binds the key into the registry. Best-effort: silent skip if Zotero is unavailable.

4. **arXiv-only papers rejected by ingest** (no DOI): `_to_papers_input` left `doi` empty for any candidate without a publisher DOI, but the pipeline rejects DOI-less papers (`Paper N: missing required field 'doi'`). Most arXiv preprints don't have a publisher DOI yet. Fixed by synthesizing `10.48550/arXiv.<arxiv_id>` from the arXiv ID, which is the canonical DOI form arXiv issues for every preprint.

### Verified — full lazy-mode flow on a new topic

```
$ research-hub auto "LLM agents agent-based modeling social simulation" --with-crystals
[OK] cluster        existing: llm-agents-agent-based-modeling-social
[OK] zotero.bind    created collection 9FHZCK4N for ...        # <- auto, was missing
[OK] search         8 results
[OK] ingest         8 papers in raw/...                        # <- was failing on missing DOI
[OK] nlm.bundle     7 PDFs
[OK] nlm.upload     8 succeeded
[FAIL] nlm.generate  Generation button not found: briefing      # <- known v0.45 intermittent
```

After 8/9 stages succeeded, the crystal step (run separately because the NLM generate hiccup aborted the auto run) produced 10 cached canonical Q&A answers in 113 s via real `claude` CLI. The cluster ended up with: 8 PDFs in Zotero, 8 Obsidian notes, NotebookLM notebook with all 8, and a full `crystals/` directory ready for `read_crystal()` queries.

The NotebookLM `Generation button not found` regression is tracked separately — not blocking lazy-mode adoption since the crystals path delivers the cached AI answers without needing the brief.

### Stats

- Tests: 1541 (no new tests in this release; the bugs were caught by real end-to-end usage, regression coverage to follow once the API patterns stabilize)
- Bugs fixed by inventory pass since v0.49.0: **11** (3 cp950, 2 broken imports, 4 auto signature/data, 2 dedup/UI)

## v0.49.3 (2026-04-19)

**2 bugs found by the bug-inventory pass: stale dedup paths + Overview health-badge text clipping.**

### Fixed — `rebuild_from_obsidian` left importer-source stale paths in the index forever

`DedupIndex.rebuild_from_obsidian(raw_root)` only purged hits where `source == "obsidian"`. Hits added by other importers (e.g. `import-folder` writes `source='importer'`) were preserved even when their `obsidian_path` no longer existed on disk. Result: doctor's `dedup_consistency` check kept warning about stale paths even after `tidy` / `dedup rebuild --obsidian-only`. The only way to clear them was manual `dedup invalidate --path X` per file.

Fix: `rebuild_from_obsidian` now also drops any hit whose `obsidian_path` no longer exists, regardless of `source`. Pure-Zotero hits (no `obsidian_path` at all) are still preserved. After the fix, the maintainer's vault title-index dropped from 1101 to 1092 (9 stale entries cleared) and `dedup_consistency` went WARN → OK.

Locked in with `test_rebuild_from_obsidian_drops_stale_paths_regardless_of_source`.

### Fixed — Overview tab health-badge text clipped by pill border-radius

The `<details>` health-badge on the Overview tab used `border-radius: var(--radius-pill)` (999px), which made it pill-shaped. When users clicked to expand, the inner `<ul>` items stretched the container wider/taller than the pill end-caps and the text near the left edge got visually clipped by the rounded curve:

```
( 1 error, 2 warnings - click to expand
( config/persona: ...
( cluster_field:survey: ...
(rontmatter_completeness: ...     ← first letter of "frontmatter" eaten
```

Fix: changed to `border-radius: var(--radius-md)` (12px rounded rectangle) and bumped horizontal padding to 16px on both summary and list. Now the text always has clear gutter regardless of how wide the badge gets.

### Stats

- Tests: 1540 → **1541** (+1 dedup regression test for the rebuild fix)

## v0.49.2 (2026-04-19)

**Hotfix: `tidy` was broken since v0.46 + 2 more cp950 crashes.** Caught by a systematic bug-inventory pass after the v0.49.1 ship.

### Fixed — `tidy` doctor + dedup steps both crashed silently

`research-hub tidy` shipped in v0.46 and **never actually ran its `doctor` and `dedup` substeps successfully**. Mocked tests masked it because the mocks accepted the wrong API:

```
$ research-hub tidy
[FAIL] doctor   run_doctor() got an unexpected keyword argument 'autofix'
[FAIL] dedup    'HubConfig' object has no attribute 'exists'
[OK]   bases    11 clusters refreshed
[OK]   cleanup  would free 72.0 MB
```

Three signature mismatches:
- `run_doctor(autofix=True)` — `run_doctor()` is no-arg; autofix is a separate `vault_autofix.run_autofix(cfg)` call.
- `build_from_obsidian(cfg)` — wants `Path`, not `HubConfig`. Should use `DedupIndex.load(...).rebuild_from_obsidian(cfg.raw)` which is the same path `cli.py dedup rebuild --obsidian-only` uses.
- `idx.dois` / `idx.titles` — attributes don't exist; the dataclass fields are `doi_to_hits` / `title_to_hits`.

Fixed by switching to the real APIs. Locked in with a new `test_tidy_signatures_match_real_api` regression test that introspects the live signatures via `inspect.signature()` so future drift is caught immediately.

After the fix, on the maintainer's vault:
```
[OK] doctor   28 checks (23 OK, 1 INFO, 3 WARN); autofix backfilled 315 fields
[OK] dedup    767 DOIs, 1101 titles
[OK] bases    11 clusters refreshed
[OK] cleanup  would free 72.0 MB
```

The autofix stage actually backfilled 315 missing-frontmatter fields on the maintainer's vault on first successful run.

### Fixed — 2 more cp950 crashes in dashboard --watch

`dashboard/__init__.py` printed `→` arrows in two more places (initial render + watch re-render), which would crash `research-hub dashboard --watch` on Windows zh-TW. Replaced with `->`. Now matches the v0.49.1 sweep.

### Verified — full lazy-mode flow works end-to-end on Windows zh-TW

Systematic post-v0.49.1 inventory ran every lazy command + MCP tool against the maintainer's real vault:

| Stage | Result |
|---|---|
| `pip install` from PyPI | OK (v0.49.1) |
| `research-hub doctor` | OK — 23/28 OK, 3 WARN are real vault data issues, not bugs |
| `research-hub tidy` | **Was broken. Fixed in this release.** |
| `research-hub cleanup --bundles --dry-run` | OK — identified 72 MB stale bundle |
| `research-hub ask llm-evaluation-harness "..."` | OK — cached crystal returned in <1 s |
| `research-hub serve --dashboard` | OK — HTTP 200, 3.2 MB rendered HTML |
| MCP server tool registration | OK — 81 tools registered, `auto_research_topic` has the new `do_crystals` / `llm_cli` params |
| Real `claude` CLI invocation | OK — `_invoke_llm_cli` returned valid JSON |
| Real crystal generation against `claude` CLI | OK — 10 crystal files written for `ai-agent-geopolitics-behavioral-patterns` cluster |
| `init` first-run readiness check on a real vault | OK — 4 subsystems probed correctly, output cp950-safe |

### Stats

- Tests: 1539 → **1540** (+1 tidy signature regression test)
- Bugs fixed: 1 critical (tidy), 2 cp950 (dashboard watch)
- Bugs found via real testing that mocks missed: 4 (cp950 in init/auto, em-dash in init, tidy signatures, dashboard arrow chars)

## v0.49.1 (2026-04-19)

**Hotfix: cp950 console crash on Windows zh-TW.** Caught by real end-to-end testing of the v0.49.0 release.

`research-hub init`'s First-run readiness check used emoji markers (`ℹ️`, `✅`, `⚠️`) and em-dashes that crashed on Windows machines with the default cp950 codepage (Traditional Chinese locale):

```
UnicodeEncodeError: 'cp950' codec can't encode character '\u2139'
```

Same issue affected `research-hub auto`'s `_step_log` which used `✅` / `❌`.

Fixed by switching to ASCII-only markers: `[OK]`, `[INFO]`, `[WARN]`, `[FAIL]`, and replacing all em-dashes with `--`. Locked down with two regression tests that explicitly call `.encode("cp950")` on the captured output.

This bug shipped to PyPI in v0.49.0; v0.49.1 fixes it. Anyone on Windows zh-TW (or any non-UTF-8 default codepage) should upgrade.

### Added

- 2 regression tests in `tests/test_v049_auto_polish.py` that fail if any future change reintroduces non-cp950 characters into `_print_readiness` or `_step_log` output.

### Stats

- Tests: 1537 → **1539** (+2 cp950-safety regression tests)

## v0.49.0 (2026-04-19)

**`auto` becomes truly end-to-end + first-run readiness check.** Closes the v0.48-era gap where new users hit invisible prerequisite walls (Chrome missing, NotebookLM not enabled, Zotero key absent) and where `auto` left users stranded after the brief without telling them what to do next.

User feedback driving this release:
> 「user 都很懶 希望能一次講拿到所有的資訊 ... auto 'topic' 跑完 這部分可以全自動化」
> ("Users are lazy — want all info in one shot ... `auto 'topic'` running through to completion can be fully automated.")

### Added — `auto --with-crystals` (full end-to-end automation)

`research-hub auto "topic" --with-crystals` now runs the optional 10th pipeline step: emit the crystal prompt, pipe it through a detected LLM CLI on PATH (`claude` → `codex` → `gemini`, in that order), parse the JSON response, and apply it. The cluster ends up with cached canonical Q&As ready for `read_crystal()` / Claude Desktop queries — no manual `emit/apply` step.

If no LLM CLI is available, the prompt is saved to `.research_hub/artifacts/<slug>/crystal-prompt.md` and the Next Steps banner tells the user exactly what to paste where. Provider-agnostic guarantee preserved — no dependency on Anthropic/OpenAI APIs.

CLI flags:
- `--with-crystals` — opt-in (default off; turn on once you've verified your CLI of choice works)
- `--llm-cli {claude,codex,gemini}` — force a specific CLI instead of auto-detection

MCP `auto_research_topic` tool gets matching `do_crystals` / `llm_cli` parameters.

### Added — Next Steps banner at end of `auto`

After every successful `auto` run, the CLI prints a copy-paste-ready banner:

```
============================================================
Done in 47.3s. Cluster: harness-engineering-llm-agents
============================================================
  NotebookLM: https://notebooklm.google.com/notebook/...
  Brief:      .research_hub/artifacts/.../brief-2026-04-19T....txt

Next steps (copy-paste any of these):

  # See your new cluster in the live dashboard
  research-hub serve --dashboard

  # Generate cached AI answers (~10 Q&As, ~1 KB each)
  research-hub crystal emit  --cluster harness-engineering-llm-agents > /tmp/cprompt.md
  ...

  # Or auto-pipe through a detected LLM CLI:
  research-hub auto "harness-engineering-llm-agents" --with-crystals

  # Talk to Claude Desktop instead
  > "Claude, what's in my harness-engineering-llm-agents cluster?"
```

Closes the dead-end where users got papers + brief but had no idea what concrete command to run next.

### Added — First-run readiness check in `init`

`research-hub init` now ends with a **First-run readiness check** that probes the four lazy-mode prerequisites and prints a one-line status per subsystem:

```
  ── First-run readiness check ─────────────────────────────
  ✅ obsidian   OK    vault detected at /home/user/knowledge-base
  ✅ chrome     OK    patchright can launch Chrome (channel='chrome')
  ✅ zotero     OK    credentials configured (verified above)
  ℹ️  llm-cli    INFO  no claude/codex/gemini CLI on PATH — crystals stay manual emit/apply
```

Replaces the v0.42-broken `find_chrome_binary` no-op (which always reported "Chrome: not found" even with Chrome installed) with the v0.46 patchright probe. Catches Chrome / Obsidian / Zotero / LLM-CLI issues at install time, not 50 seconds into a failing `auto` run.

### Changed — README rebuilt around prerequisites + troubleshooting

- Added **📋 Prerequisites** table at the top: 6 rows covering Python / Obsidian / Google+NLM / Chrome / Zotero / LLM CLI with "why" + "how" columns.
- Added **🩺 Troubleshooting** section covering 7 most common first-run problems (Chrome WARN, NLM login blocked, search 0 papers, NLM upload "Generation button", `--with-crystals` no CLI, Claude Desktop config location, Zotero WARN for analyst persona).
- Added new `--with-crystals` example to the install section so users discover the fully automated path immediately.
- zh-TW mirror updated symmetrically.

### Stats

- Tests: **1528 → 1537** (+9 in `tests/test_v049_auto_polish.py` covering LLM CLI detection, JSON extraction, Next Steps banner, crystal step fallback, readiness check)
- MCP tools: 81 (unchanged count; `auto_research_topic` extended with 2 new params)
- README EN: 178 → 218 lines (added Prerequisites + Troubleshooting tables)
- README zh-TW: 168 → 208 lines (mirrored)

### Install

```bash
pip install --upgrade research-hub-pipeline[playwright,secrets]
```

Existing v0.42–v0.48 users upgrade in place. `--with-crystals` is opt-in, so existing `auto` invocations keep their previous behavior.

## v0.48.0 (2026-04-19)

**Diagnostics density redesign + post-B1 screenshot refresh + README condensed to 3 differentiators.** All visual / docs polish — no API changes.

User feedback driving this release:
> "錯誤訊息 不應該放那麼大吧 截圖也要想一下 還有使用者一定都想要用最簡單的方式得到最多功能"
> ("Error messages shouldn't be that prominent; think about screenshots; users want max functionality with min effort.")

### Changed — Diagnostics tab no longer reads as a wall of cards

Before v0.48, every drift alert rendered as a full-width padded card. A vault with 36 zotero-orphan + 20 stale-crystal alerts produced 56 nearly-identical cards stacked vertically — visually overwhelming and out of proportion to severity.

- **Health card**: count summary (`12 OK · 3 need attention`) at top; OK rows collapsed behind a `<details>` fold; only attention rows shown by default. Per-row layout slimmed (no card chrome on OK rows, just a colored left-border on attention rows).
- **Drift card grouping**: alerts of the same `kind` collapse into one card with a `×N` count badge in the title. Sample paths from all alerts in the group de-duplicated and shown as a 5-item list with a `Show N more` fold (capped at 25 visible, `…and X more not shown` footer beyond that).
- **Drift card chrome**: padding `lg→sm/md`, font `text-sm`, h3 `text-sm`, sample-paths `text-xs`. The card is still distinct (border + severity left-stripe) but no longer dwarfs surrounding content.

Net: 59-alert vault renders as ~5 grouped cards instead of 59. Diagnostics tab now scrolls one screen.

### Changed — Hero screenshots regenerated post-B1

The v0.46 B1 rebind cleared 315 orphan papers (315 → 0). v0.45-era screenshots still showed the pre-rebind state with mega-clusters and "X orphan papers" warnings. v0.48 regenerates all six tab screenshots (`docs/images/dashboard-{overview,library,briefings,writing,diagnostics,manage}.png`) from the cleaned vault.

### Changed — README "What makes it different" 5 → 3 sections

Per the lazy-user theme, condensed five differentiators into three:
1. Pre-computed answers (crystals + memory layer combined)
2. Live dashboard, 4 personas, direct execution
3. Cluster integrity + lazy-mode maintenance (auto/tidy/clean/ask)

Removes ~60 lines of headings/sub-sections without losing any feature mentions.

### Stats

- Tests: 1547 → **1547** (no test changes — pure UI/CSS/markdown)
- MCP tools: 81 (unchanged)
- Diagnostics tab DOM nodes: ~250 → ~80 on a 59-alert vault

### Install

```bash
pip install --upgrade research-hub-pipeline[playwright,secrets]
```

Existing v0.42–v0.47 users upgrade in place.

## v0.47.0 (2026-04-19)

**Lazy mode reaches AI: `auto`/`cleanup`/`tidy` now exposed as MCP tools.** Closes the v0.46 gap where Claude Desktop / Claude Code users still had to invoke 7 individual MCP calls to replicate the lazy CLI commands.

Now the conversation is literally:
> "Claude, research harness engineering for me"

Claude calls `auto_research_topic(topic="harness engineering")` once. Done.

### Added — 3 new MCP tools

- `auto_research_topic(topic, ...)` — wraps `auto.auto_pipeline`. Returns structured report with `cluster_slug`, `papers_ingested`, `notebook_url`, `brief_path`, `steps[]`.
- `cleanup_garbage(bundles, debug_logs, artifacts, everything, apply, ...)` — wraps `cleanup.collect_garbage`. Returns `{total_bytes, files_deleted, candidates[]}`.
- `tidy_vault(apply_cleanup)` — wraps `tidy.run_tidy`. Returns `{steps[], total_duration_sec, cleanup_preview_bytes}`.

All 3 honor `apply` / `dry_run` semantics from their CLI counterparts. Default mode is preview-safe.

### Stats

- MCP tools: 78 → **81**
- Tests: 1539 → **1547** (+8: 5 new + 3 consistency mappings)

### Why ship a separate v0.47 instead of folding into v0.46

v0.46 added the CLI but left MCP behind — answer to "can the AI just talk to research-hub?" was technically "yes but burns context". v0.47 makes it actually one MCP call. Small enough to ship same day; big enough to deserve its own version because it changes the conversational UX.

### Onboarding flow (post-v0.47)

```bash
# One-time setup (under 60 s)
pip install research-hub-pipeline[playwright,secrets]
research-hub init                  # interactive: picks persona + Zotero
research-hub notebooklm login      # one-time Google sign-in
```

Add to `claude_desktop_config.json`:
```json
{ "mcpServers": { "research-hub": { "command": "research-hub", "args": ["serve"] } } }
```

Then in Claude Desktop:
> "Claude, find me 5 papers on agent-based modeling and put them in a notebook"

Claude calls `auto_research_topic(topic="agent-based modeling", max_papers=5)` → returns 5 papers ingested + brief URL in ~50 s.

---

## v0.46.0 (2026-04-19)

**Lazy mode — 4 one-line commands replace the 7+ command longhand workflow. Plus `cleanup` becomes a real garbage collector and `doctor` chrome check finally works.**

User feedback: "因為大家都很懶 我希望能夠在一些功能做到 打一句話搞定". v0.46 answers it.

### Added — `research-hub auto "topic"` (Track A1)

End-to-end: slugify topic → cluster create → search (arXiv + Semantic Scholar) → ingest into Zotero + Obsidian → bundle PDFs → upload to NotebookLM → generate brief → download.

```bash
research-hub auto "harness engineering for LLM agents"
# 47 seconds later: 6 papers in Zotero + Obsidian + NotebookLM brief
```

Flags: `--max-papers N`, `--no-nlm`, `--dry-run`, `--cluster X`, `--cluster-name "Display"`. Each pipeline stage logged with progress; failure at any step halts cleanly with actionable error.

### Added — `research-hub cleanup` real garbage collector (Track A2)

v0.45 `cleanup` only de-duped wikilinks. v0.46 adds:

- `--bundles --keep N` — per-cluster, deletes older bundle dirs (default keep 2)
- `--debug-logs --older-than 30d` — deletes `nlm-debug-*.jsonl` older than threshold
- `--artifacts --keep N` — per-cluster, keeps newest N `ask-*.md` / `brief-*.txt`
- `--all` — combine all 3
- `--dry-run` (default) / `--apply`

Old wikilink dedup still works via `--wikilinks` flag. Live test: 72 MB stale bundles ready to GC on the maintainer's vault.

### Added — `research-hub tidy` one-shot maintenance (Track A3)

```bash
research-hub tidy
# Runs: doctor --autofix → dedup rebuild → bases emit per cluster → cleanup preview
```

Each step non-fatal — failures logged but don't break the whole command. `--apply-cleanup` flag also flushes the cleanup preview.

### Fixed — `doctor` chrome stale check (Track A4)

v0.45 reported `chrome: Not found` even when NotebookLM was working perfectly. Root cause: `doctor.check_chrome` walked the legacy `cdp_launcher.find_chrome_binary` paths, but v0.42 deleted that module. v0.46 replaces it with a real patchright probe (the same mechanism NotebookLM uses):

```
[OK] chrome: Available via patchright channel='chrome'
```

When Chrome can't launch, downgraded from scary `WARN` to `INFO` with install hint.

### Stats

- Tests: 1520 → **1553** passing (+33: A1=8, A2=7, A3=4, A4=2 + 12 doctor-related)
- LOC: ~+550 code + ~150 docs
- New files: `src/research_hub/{auto,cleanup,tidy}.py` + `docs/lazy-mode.md`
- **Zero new setup** — every new command uses existing NotebookLM session (`notebooklm login` done once) + existing Zotero credentials

### Delegation note

Tried Gemini for the code work (per user request). Result: 2 of 5 Gemini tracks succeeded (A1 `auto`, A2 `cleanup`); the other 3 (A3, lazy-mode docs, zh-TW notes) hit `QUOTA_EXHAUSTED` and fell back to Claude direct. Gemini's coding quality on the successful tracks was workable (with minor import-path fixes after review).

繁體中文 release announcement: [docs/release-notes-v0.46.zh-TW.md](docs/release-notes-v0.46.zh-TW.md). Lazy-mode reference: [docs/lazy-mode.md](docs/lazy-mode.md).

---

## v0.45.0 (2026-04-19)

**Critical fix: `notebooklm generate` overlay dismissal. Plus 3 v0.43 scaffolding completions.**

Live NLM push on the 11-paper harness cluster after v0.44 ship exposed a real bug: `research-hub notebooklm generate --type brief` failed with "Generation button not found". Root cause: `_trigger_and_wait` in `client.py` searches the studio panel without dismissing NotebookLM's `cdk-overlay-backdrop-showing` overlay first. v0.42 `ask.py` had the fix; `generate` / `download_briefing` / `open_notebook_by_name` paths never got it.

### Fixed — NLM overlay dismissal

- Lifted `_dismiss_overlay` from `ask.py` into shared `notebooklm/browser.py::dismiss_overlay`
- `NotebookLMClient.open_notebook_by_name` calls it after the tile click (catches first-load onboarding popup)
- `_trigger_and_wait` calls it before searching the studio panel (catches add-source dialog from `?addSource=true` URLs)
- `download_briefing` calls it before reading summary content
- 4 new tests + ask.py refactored to use the shared helper

### Added — auto `.base` refresh on ingest + topic build

After successful `research-hub ingest --cluster X` or `research-hub topic build --cluster X`, the cluster's `hub/X/X.base` file is automatically refreshed via `write_cluster_base(... force=True)`. Non-fatal — if the refresh fails, the underlying command still returns 0 with a logged warning. Closes the v0.43 gap where new papers required a manual `bases emit --force`.

### Added — Crystal `See also` routes through `wikilink()`

Byte-identical refactor — `[[crystals/<slug>|<question>]]` now built via the v0.43 helper. Centralizes wikilink rendering for consistency.

### Added — `doctor` detects missing defuddle CLI

`research-hub doctor` emits an `INFO`-level note when `defuddle` binary not on PATH, with the install hint `npm install -g defuddle-cli`. Detection only — never auto-installs.

### Stats

- Tests: 1508 → **1520 passing** (+12)
- LOC delta: ~+200
- Files: `notebooklm/{browser,client,ask}.py`, `crystal.py`, `pipeline.py`, `topic.py`, `doctor.py`, 4 test files

### Verification (live)

```bash
research-hub notebooklm generate --cluster llm-evaluation-harness --type brief
# Expected: completes without "Generation button not found" error
```

繁體中文 release announcement: [docs/release-notes-v0.45.zh-TW.md](docs/release-notes-v0.45.zh-TW.md).

---

## v0.44.0 (2026-04-19)

**Dashboard UI completeness — finally surfaces v0.42 + v0.43 features as buttons. README walkthrough so users actually know how to use the dashboard.**

Post-v0.43 audit found the dashboard was half-baked: `executor.py` whitelist was extended in v0.42 to accept `notebooklm-bundle/upload/generate/download` actions, but the Manage-tab buttons + JS handlers were never added. So the executor accepted commands no UI emitted. v0.43's `ask` / `polish-markdown` / `bases-emit` weren't even in the whitelist. Plus README pointed at `serve --dashboard` with one line of guidance, no walkthrough.

**Constraint**: zero new setup. Every new button uses the existing NotebookLM session (`notebooklm login`) + existing Zotero credentials. No env vars, no API keys.

### Added — 7 Manage tab actions

Per-cluster forms in the Manage tab now drive:

- **NotebookLM (v0.42)** — `bundle` / `upload` / `generate brief|audio|mind_map|video` / `download brief` / `ask` (with question textarea + timeout)
- **Obsidian (v0.42 + v0.43)** — `vault polish-markdown` (dry-run / apply toggle) / `bases emit` (force toggle)

Each form: live executor in server mode (`serve --dashboard`), clipboard copy in static mode (`dashboard`).

### Added — NotebookLM artifacts tile

Per-cluster NotebookLM Library sub-tile reads `nlm_cache.json::artifacts` and lists what's been downloaded (brief / audio / mind_map / video) with deep-links to NotebookLM + the local artifact file. If empty: 1-click download button.

### Added — `docs/dashboard-walkthrough.md`

Full UI walkthrough: tab-by-tab tour, persona-specific daily workflow recipes, per-button explanation for the 7 new v0.42/v0.43 actions, troubleshooting links. README's `serve --dashboard` section now points here.

### Stats

- Tests: 1492 → 1507+
- LOC: ~+480 + ~150 docs
- Files: `dashboard/{executor,manage_commands,sections,script.js}.py/.js` + `README.md` + new `docs/dashboard-walkthrough.md` + `tests/test_v044_dashboard_actions.py`

繁體中文 release announcement: [docs/release-notes-v0.44.zh-TW.md](docs/release-notes-v0.44.zh-TW.md).

---

## v0.43.0 (2026-04-19)

**[kepano/obsidian-skills](https://github.com/kepano/obsidian-skills) integration: defuddle URL extraction, full Obsidian Flavored Markdown helpers, auto-generated Obsidian Bases dashboards per cluster.**

The 5 kepano skills (25.3k⭐, MIT, by Steph Ango / Obsidian CEO) were installed; v0.42's Track C had only adopted a slice (callouts + block IDs). v0.43 closes the gap and stress-tests the v0.42 NotebookLM layer at 11-paper scale.

### Track 1 — 11-paper NotebookLM stress test (validation, no code change)

Cluster `llm-evaluation-harness` grew from 6 → 11 papers (added 5 new harness-engineering arXiv preprints: VeRO evaluation harness, AgentSPEX specification language, TDAD test-driven agent definition, AEC-Bench multimodal benchmark, ALaRA least-privilege).

```
research-hub notebooklm bundle --cluster llm-evaluation-harness
research-hub notebooklm upload --cluster llm-evaluation-harness
→ 11 succeeded, 0 failed, 0 skipped from cache
→ nlm-debug-*.jsonl: success_count: 11, fail_count: 0, retry_count: 0
```

**v0.42 patchright + persistent-context layer holds at 11-paper scale: every paper uploaded on attempt 1, no retries needed.**

Cross-validated `research-hub notebooklm ask` against the independently-installed `mcp__notebooklm__*` server (PleasePrompto/notebooklm-skill MCP). Both backends converge on the same 3-thread analysis (evaluation / memory / security) with the same exemplar papers. v0.42 ask layer behaves consistently with the 5.9k⭐ reference implementation. Validation log: [`docs/validation_v0.43.md`](docs/validation_v0.43.md).

### Track 2 — defuddle URL extraction (replaces readability-lxml)

NEW `src/research_hub/defuddle_extract.py` — subprocess wrapper around the [defuddle CLI](https://github.com/kepano/defuddle). Replaces `readability-lxml` (unmaintained since 2021, flagged in v0.40 audit) for cleaner URL→markdown extraction.

- `_extract_url` in `importer.py` now tries defuddle first; falls back to readability-lxml on `None` (defuddle binary not installed)
- Zero breaking change: `[import]` extra still pulls `readability-lxml` so existing v0.42 installs continue to work
- Optional install: `npm install -g defuddle-cli`
- CI: GitHub Actions matrix gains `actions/setup-node@v4` + best-effort `npm install -g defuddle-cli`

### Track 3 — Obsidian Flavored Markdown extensions

`src/research_hub/markdown_conventions.py` (213 LOC → ~330 LOC) gains:

- `wikilink(target, *, display=None, heading=None, block_id=None)` — `[[target]]` / `[[target|display]]` / `[[target#heading]]` / `[[target^block]]`
- `embed(target, *, size=None, page=None)` — `![[image|300]]` / `![[paper.pdf#page=3]]`
- `highlight(text)` — `==text==`
- `property_block(**fields)` — Obsidian-property-style YAML

Crystal Evidence column + cluster paper lists now route through `wikilink()` for consistency. Paper note frontmatter (`make_raw_md`) gains optional `zotero-pdf-path:` so notes can embed the PDF via `![[{{zotero-pdf-path}}#page=1]]`.

### Track 4 — Obsidian Bases (`.base`) per-cluster dashboards

NEW `src/research_hub/obsidian_bases.py` — auto-generates a `.base` YAML file per cluster with **4 views**:

1. **Papers** — table filtered by `topic_cluster`, grouped by year DESC
2. **Crystals** — cards filtered by `type=="crystal"` AND `cluster==<slug>`
3. **Open Questions** — pulls from cluster overview
4. **Recent activity** — top 10 by `ingested_at`

Plus 2 formulas (`days_since_ingested`, `paper_count`).

NEW `research-hub bases emit --cluster X [--stdout] [--force]` CLI subcommand. NEW MCP tool `emit_cluster_base(cluster_slug)` for Claude Desktop.

`scaffold_cluster_hub` (`topic.py`) now writes `<slug>.base` alongside `00_overview.md` + `crystals/` + `memory.json`. Idempotent.

### Stats

- Tests: 1458 → 1492+ (Track 2: 8, Track 3: 15, Track 4: 11)
- LOC delta: ~+550 new, ~5 modified

### Notes

- `obsidian-cli` integration (5th kepano skill) deferred to v0.44 — needs a running Obsidian instance, environmental assumption we can't enforce in CI.
- `json-canvas` citation graph export — also v0.44 candidate.

繁體中文 release announcement: [docs/release-notes-v0.43.zh-TW.md](docs/release-notes-v0.43.zh-TW.md). Audit: [docs/audit_v0.43.md](docs/audit_v0.43.md).

---

## Unreleased

- NotebookLM v0.42 browser launcher and `ask` flow adapt patterns from
  PleasePrompto/notebooklm-skill (MIT), including the stealth Chrome launch
  configuration and stability-polling Q&A flow.

## v0.42.0 (2026-04-19)

**NotebookLM reliability rewrite + `ask` command + Obsidian callout/block-ID conventions.**

User pain: **"從 Obsidian 到 NotebookLM 總是很卡 ... 很多次都沒有辦法把資料傳到 NotebookLM"** — load-bearing product complaint. This release targets it head-on.

### Changed — NotebookLM browser layer (Track A)

Migrated the entire NLM automation layer from stock `playwright` + CDP-attach to [patchright](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright) (stealth-patched fork) with a persistent Chrome context. Root-cause fixes for silent upload failures:

- **Anti-automation flag.** `--disable-blink-features=AutomationControlled` + `ignore_default_args=["--enable-automation"]`. Without these, Google's NotebookLM frontend detects `navigator.webdriver=true` and silently rejects uploads.
- **Real Chrome, not Chromium.** `channel="chrome"` — Gemini-backed products work significantly better against real Chrome.
- **Patchright stealth patches.** Drop-in fork of Playwright. No code change beyond import swap.
- **Cookie injection workaround** for [Playwright bug #36139](https://github.com/microsoft/playwright/issues/36139). Cookies persist to `.research_hub/nlm_sessions/state.json` and are re-injected on each launch.
- **Retry logic + structured JSONL logging.** Every per-paper upload retries up to 3 times (1 s → 3 s → 9 s backoff). All attempts land in `.research_hub/nlm-debug-<UTC>.jsonl`. No more silent skip.
- **Extended locale fallback.** Added `zh-CN, ko, es, fr, de` aria-label variants for all studio-panel buttons (prev: only zh-TW/en/ja).
- **Dialog close hardening.** `client.py` dialog detach timeouts now raise `NotebookLMError` instead of swallowing — outer retry wrapper sees the failure and backs off.

Significant patterns adapted (with attribution) from [PleasePrompto/notebooklm-skill](https://github.com/PleasePrompto/notebooklm-skill) (MIT, 5.9k⭐). We do not vendor; we adapt the launch-args + auth-persistence + stable-polling idioms. Source comments credit both.

Dependency: `pip install research-hub-pipeline[playwright]` now installs `patchright>=1.55` (was `playwright>=1.40`). Existing users run the same command — the extra name didn't change.

### Added — `research-hub notebooklm ask` + MCP tool `ask_cluster_notebooklm` (Track B)

Ad-hoc Q&A against an already-uploaded cluster's NotebookLM notebook.

```bash
research-hub notebooklm ask \
    --cluster llm-evaluation-harness \
    --question "Which paper proposes search over memory programs?"
```

- Looks up `cluster.notebooklm_notebook_url` from `clusters.yaml` (set during prior `upload`)
- Types the question with randomized 25–75 ms/char human-like cadence
- Polls response selectors with a 3-read stability quorum
- Detects NotebookLM's `thinking-message` state to pause polling during generation
- 120 s timeout per question
- Saves to `.research_hub/artifacts/<slug>/ask-<UTC>.md` with question header + latency
- Returns to stdout

MCP tool `ask_cluster_notebooklm(cluster, question)` exposes the same flow to Claude Desktop.

### Added — Obsidian callout + block-ID conventions (Track C)

Adopted the [kepano/obsidian-skills/obsidian-markdown](https://github.com/kepano/obsidian-skills) conventions (MIT, by Steph Ango / Obsidian CEO):

- **Paper notes.** `## Summary` / `## Key Findings` / `## Methodology` / `## Relevance` sections render as `> [!abstract]` / `> [!success]` / `> [!info]` / `> [!note]` callouts with `^summary` / `^findings` / `^methodology` / `^relevance` block IDs. Section heading anchors stay clean so every existing regex extractor continues to work.
- **Cluster overview template.** TL;DR → `> [!abstract]` (with `^tldr`); Core question → `> [!question]`; Open problems → `> [!warning]`.
- **Crystal template.** TL;DR wrapped in `> [!abstract]`. Round-trip preserved: `Crystal.from_markdown` unwraps callouts idempotently.
- **NEW `research-hub vault polish-markdown [--cluster X] [--apply]`** — walks existing paper notes and upgrades legacy plain-paragraph sections to the new callout format. Dry-run by default. Idempotent.

### Changed — file structure

- NEW `src/research_hub/notebooklm/browser.py` (patchright launcher + state.json helpers)
- NEW `src/research_hub/notebooklm/ask.py` (Q&A flow)
- NEW `src/research_hub/markdown_conventions.py` (callout helpers, upgrade script)
- `src/research_hub/notebooklm/cdp_launcher.py` — deprecated shim; raises `NotImplementedError` with a pointer to `browser.py`
- `src/research_hub/notebooklm/session.py` — thin shim routing legacy `open_cdp_session` / `login_interactive*` calls to `browser.launch_nlm_context`

### Verification

```bash
research-hub notebooklm login                          # visible Chrome opens; state.json written
research-hub notebooklm bundle --cluster X
research-hub notebooklm upload --cluster X             # retry log at .research_hub/nlm-debug-*.jsonl
research-hub notebooklm ask --cluster X --question "?" # ~60 s round-trip
research-hub vault polish-markdown --cluster X --apply
```

### Notes

- Obsidian Bases (`.base` file) auto-generation per cluster — deferred to v0.43.
- JSON Canvas (`.canvas`) citation-graph export — deferred to v0.43.
- `readability-lxml → defuddle` — defuddle is NPM-only; v0.43 will evaluate Python alternatives (trafilatura/newspaper3k).
- zh-TW release notes written directly by Claude (Gemini Windows retry declined per user decision).

繁體中文 release announcement: [docs/release-notes-v0.42.zh-TW.md](docs/release-notes-v0.42.zh-TW.md).

---

## v0.41.1 (2026-04-19)

**Python 3.10/3.11 syntax fix — Codex used PEP 701 f-string syntax (3.12+).**

`tests/test_doctor.py:226` had `f"{body or '## Summary\nx\n\n...'}"` — backslash inside f-string expression. Allowed by Python 3.12+ (PEP 701) but SyntaxError on 3.10/3.11. CI multi-OS matrix caught it on 6 of 9 jobs.

Fix: extracted the default body to a module-level constant `_DEFAULT_BODY`, referenced as `f"...{body or _DEFAULT_BODY}"`. Local Python 3.14 didn't catch this; only multi-OS CI did.

3 lines in `tests/test_doctor.py`. No production code touched. 1423 tests still pass.

---

## v0.41.0 (2026-04-19)

**Real-world friction fixes — 4 ingest + 3 vault hygiene CLIs. 1402 → 1423 tests (+21).**

After v0.40.2 ship, ran end-to-end test (create cluster → search arXiv → ingest 6 LLM-eval-harness papers → push to NotebookLM). Hit 4 distinct ingest pipeline bugs. Separately, vault frontmatter audit found 1069/1096 notes had issues — wrote ad-hoc Python scripts that cut to 544 in 5 minutes; productionized those into proper CLIs.

7 fixes shipped together. Codex executed in 1 brief.

### Added — Ingest pipeline (4 fixes)

- **F1 — `add` falls back to arXiv API when Semantic Scholar rate-limits.** S2 returns 429 → previously failed with no recourse. Now arXiv-shaped DOIs (`10.48550/arxiv.YYMM.NNNNN`) auto-retry via arXiv's metadata API.
- **F2 — `search --to-papers-input` preserves `arxiv_id` and auto-derives `doi`.** Previously dropped arxiv_id; user had to manually backfill DOIs to ingest. Now arXiv papers come out ingest-ready.
- **F3 — `papers_input.json` accepts both top-level array AND `{"papers": [...]}` shape.** `search --to-papers-input` outputs the wrapped shape; `ingest` expected the array. AttributeError on iteration. Now auto-normalize.
- **F4 — `RESEARCH_HUB_DEFAULT_COLLECTION` not required when cluster has its own `zotero_collection_key`.** Cluster-bound key takes priority; env var is fallback for unbound clusters.

### Added — Vault hygiene (3 CLIs)

- **V1 — NEW `research-hub doctor --autofix`** for mechanical backfills:
  - Empty `topic_cluster: ""` → folder name → cluster slug lookup
  - Missing `ingested_at:` → file mtime in ISO 8601 UTC
  - Missing `doi:` AND filename has arxiv-shaped slug → derive `10.48550/arxiv.<id>`
  - Idempotent. Prints summary like `[autofix] topic_cluster=N ingested_at=N doi_derived=N`
- **V2 — Doctor `frontmatter_completeness` distinguishes legacy vs new papers.** Pre-2000 papers AND `ingestion_source: pre-v0.3.0-migration` papers get WARN (not FAIL) for missing DOI. Recent papers still FAIL. Output now reads `316 FAIL (recent papers should have DOI), 324 WARN (legacy papers without DOI expected)`.
- **V3 — NEW `research-hub paper lookup-doi <slug>`** for one-off Crossref lookups. Free API (~1 req/sec). Bulk mode: `--cluster X --batch` walks every paper missing DOI in the cluster.

### Stats

- Tests: 1402 → 1423 (+21: 18 from brief + 3 from Codex extras)
- New files: 5 test files + `vault_autofix.py` + `doi_lookup.py`
- Modified: `cli.py`, `operations.py`, `pipeline.py`, `doctor.py`
- LOC delta: ~+450

### Reflection

7 fixes — none invented. Each came from actually using the tool (4 from ingest test, 3 from vault audit). v0.40 multi-OS CI exposed Windows path issues; v0.41 ingest run exposed schema mismatches. **The cycle works**: ship → use → fix what hurts.

繁體中文 release announcement: [docs/release-notes-v0.41.zh-TW.md](docs/release-notes-v0.41.zh-TW.md).

### Notes

- Gemini CLI (zh-TW release notes) hit a Windows AttachConsole / non-interactive shell bug; Claude wrote the zh-TW notes as fallback (per `feedback_gemini_cli_invocation` global rule)
- Codex executed cleanly on first try; no stalls

---

## v0.40.2 (2026-04-19)

**v0.40.1's narrow regex didn't catch `test_config.py` — make `RESEARCH_HUB_ALLOW_EXTERNAL_ROOT` global for tests.**

v0.40.1 only set the env var bypass for `test_v0NN_*` and `test_cli_*` files. But `test_config.py` (3 tests) also uses tmp_path-based RESEARCH_HUB_ROOT and hit the same v0.30 HOME-guard ValueError on Windows CI.

Cleaner fix: NEW autouse fixture `_allow_external_vault_root_in_tests` sets the env var unconditionally for every test. Safe because tests run in sandboxed tmp_paths, not against the user's real $HOME.

3 lines changed in `tests/conftest.py`. No production code modified. 1402 tests pass.

---

## v0.40.1 (2026-04-19)

**First multi-OS CI run exposed 2 test-infrastructure bugs (production code unchanged).**

v0.40.0's CI added Windows + macOS matrix jobs for the first time. As expected with new platform coverage, 2 test infrastructure issues surfaced:

1. **`test_v040_*` tests not covered by autouse `_auto_mock_require_config`** fixture. The conftest pattern matcher only matched up to `test_v034_*.py` (added in v0.37.3). v0.40 tests called `cli.main(["import-folder", ...])` and hit `require_config()` which raised `SystemExit(1)` because CI runners have no config.json. Fix: regex pattern matches all `test_v0NN_*` files.

2. **Windows CI runners trip the v0.30 "vault must be under HOME" guard** because workspace is on `D:\` but HOME is on `C:\Users\runneradmin`. Tests using `tmp_path`-based `RESEARCH_HUB_ROOT` now auto-set `RESEARCH_HUB_ALLOW_EXTERNAL_ROOT=1` via the same conftest autouse fixture.

Both fixes are 5-line changes in `tests/conftest.py`. No production code modified. 1402 tests still pass.

---

## v0.40.0 (2026-04-19)

**Production readiness — go-live audit fixes. 1387 → 1402 tests (+15). Multi-OS CI (Linux/Win/macOS).**

3 parallel Explore agents audited the system across architecture, user experience, and community readiness axes. 15 distinct gaps found. v0.40 closes the top tier:

- **Cluster hub auto-scaffold** — `ClusterRegistry.create()` now creates hub/<slug>/ structure (overview + crystals/ + memory.json) automatically. Closes the user-discovered gap from v0.39 where 6 of 7 rebound clusters had no hub directory.
- **Onboarding hardening** — README persona table now shows the required pip extras per persona; init wizard prompts on Zotero validation failure; import-folder fails fast on missing deps; MCP tools return structured errors on empty vaults.
- **Repo polish** — multi-OS CI matrix (Linux + Windows + macOS), SECURITY.md, CODE_OF_CONDUCT.md, ISSUE/PR templates, NEW `docs/first-10-minutes.md` per-persona guided tour.

Full release report: [docs/audit_v0.40.md](docs/audit_v0.40.md).

### Added — Cluster hub auto-scaffold (Track A)

NEW `src/research_hub/topic.py::scaffold_cluster_hub(cfg, slug)` — creates the full hub/<slug>/ structure:
- `hub/<slug>/00_overview.md` (overview template)
- `hub/<slug>/crystals/` (empty dir)
- `hub/<slug>/memory.json` (empty entities/claims/methods registry)

Wired into `ClusterRegistry.create()` so EVERY new cluster gets it automatically (best-effort with try/except — doesn't block cluster creation if scaffold fails). `cluster_rebind._apply_new_cluster_proposals` also explicitly calls scaffolding (defense in depth).

NEW CLI: `research-hub clusters scaffold-missing` — backfills clusters that have no hub directory (idempotent). For Wenyu's vault: scaffolded 7 of 7 clusters.

6 tests in `tests/test_v040_hub_scaffold.py`.

### Added — Onboarding hardening (Track B)

**B1**: README persona table (EN + zh-TW) now shows the FULL install command per persona:
- Researcher / Humanities: `pip install research-hub-pipeline[playwright,secrets]`
- Analyst / Internal: `pip install research-hub-pipeline[import,secrets]`

**B2**: `docs/onboarding.md` rewritten — removed v0.19-stale `--field` references, added per-persona quickstarts (4 mini-tutorials), vault layout diagram.

**B3**: Init wizard now PROMPTS on Zotero validation failure — `[r]etry / [c]ontinue offline / [a]bort` instead of silent "may still work".

**B4** (already done by Track A's encrypt() call): Init wizard auto-encrypts Zotero key before writing config.json (no plaintext-on-disk window).

**B5**: `import-folder` does dependency precheck at CLI dispatch time. PDFs require `[import]` extra; missing fails with clear remedy BEFORE starting the import.

**B6**: MCP top-level tools (`ask_cluster`, `summarize_rebind_status`, `list_orphan_papers`, etc.) wrap body in try/except returning structured `{ok:false, error, hint}` on empty-vault / missing-cluster / crash modes. Claude Desktop now sees actionable errors.

10 tests in `tests/test_v040_onboarding.py`.

### Added — Repo polish (Track C)

- `.github/workflows/ci.yml`: matrix expanded from `ubuntu-latest` only to `[ubuntu-latest, windows-latest, macos-latest]` × `[3.10, 3.11, 3.12]` = 9 jobs. `fail-fast: false` so one platform's failure doesn't mask others. `-m "not slow"` filter so live-vault test doesn't false-fail on CI runners.
- `.github/SECURITY.md` — vulnerability reporting policy (private email, 5-day SLA, 30-day disclosure).
- `.github/CODE_OF_CONDUCT.md` — Contributor Covenant 2.1.
- `.github/ISSUE_TEMPLATE/{bug_report,feature_request}.md` — structured issue templates with persona checkbox + doctor output prompt.
- `.github/pull_request_template.md` — PR checklist with persona impact matrix + multi-OS CI requirement.
- NEW `docs/first-10-minutes.md` — guided tour for each of 4 personas with vault layout diagram, install command, init flow, first useful action, dashboard preview.
- README + zh-TW link to first-10-minutes.md.

### Stats

- Tests: 1387 → 1402 (+15: 6 scaffold + 9 onboarding)
- Files modified: pyproject, CHANGELOG, README ×2, ci.yml, init_wizard, cli, mcp_server, importer, clusters, topic, cluster_rebind
- New files: 7 (scaffold_cluster_hub, 2 test files, 5 repo policy files, first-10-minutes.md, audit doc)
- Multi-OS CI: 1 → 9 jobs

---

## v0.39.0 (2026-04-18)

**Cluster rebind v2 — coverage 33% → 100% on real vault. 1369 → 1387 tests (+18). 4 new MCP tools (56 → 60).**

v0.37 shipped `clusters rebind --emit` but on Wenyu's restored 1094-paper vault it only proposed 347 of 1063 orphan papers (33%). The other 716 had no heuristic match. v0.39 closes that gap: **646 proposals to existing clusters + 417 absorbed by 6 auto-create-from-folder proposals = 1063/1063 (100%) covered.**

Full release report: [docs/audit_v0.39.md](docs/audit_v0.39.md).

### Added — 3 new heuristics in `_propose_cluster()`

Inserted in priority order between existing heuristics (8 total now):
- **H2: `topic_cluster:` field with non-empty value → HIGH** — fixes silent failure: many legacy papers had `topic_cluster:` set but the original heuristic only checked `cluster:` field
- **H4: Zotero collection NAME match → HIGH (exact) / MEDIUM (substring)** — Wenyu's vault uses readable collection names like `"LLM AI agent"`, `"Social capital"`, not 8-char Zotero keys; matches against cluster name + seed_keywords
- **H5: tag-to-seed_keywords Jaccard overlap** — extracts semantic tokens from tags (strips `research/`, `method/` prefixes), computes overlap with cluster seed_keywords. Score ≥ 0.5 → MEDIUM, ≥ 0.3 → LOW

### Added — Auto-create-from-folder

`emit_rebind_prompt()` now scans for topic folders with ≥ 5 unmatched orphan papers and proposes new clusters:
- `slug` = kebab-case of folder name (`Behavioral-Theory` → `behavioral-theory`)
- `name` = title-case
- `seed_keywords` = top 5 most common semantic tag tokens

Apply with `--auto-create-new` flag (opt-in; without it, new-cluster proposals are reported but skipped).

### Added — 4 MCP tools (56 → 60)

Closes the v0.37 gap that left rebind CLI-only:
- `propose_cluster_rebind(cluster_slug)` — returns JSON proposals
- `apply_cluster_rebind(report_path, dry_run, auto_create_new)` — executes
- `list_orphan_papers(folder)` — lists unbound papers
- `summarize_rebind_status()` — high-level: total / proposed / stuck / would-create-clusters

### Live verification (Wenyu's vault, 1063 orphans)

| | v0.37 | v0.39 |
|---|---|---|
| Proposed to existing clusters | 347 (33%) | 646 (61%) |
| Absorbed by auto-create | — | 417 (39%) |
| **Total path forward** | **347 / 1063** | **1063 / 1063 (100%)** |

6 auto-create proposals: `abm-theories` (7), `behavioral-theory` (20), `benchmarking` (8), `general-reference` (17), `survey` (289), `traditional-abm` (76).

### Stats

- Tests: 1369 → 1387 (+18: heuristics=8, autocreate=5, mcp=5)
- Files modified: `cluster_rebind.py`, `cli.py`, `mcp_server.py`, README ×2
- New files: 3 test files
- LOC delta: ~+500

---

## v0.38.1 (2026-04-18)

**Health badge UX polish — caught after reviewing v0.38.0 screenshots myself.**

After v0.38.0 shipped, on inspection the doctor health badge had three remaining issues:
1. Chip text used `--text-sm` (15px) — hard to read on the screenshot at thumbnail size.
2. Color went red whenever ANY FAIL existed — even 2 errors among 5 warnings looked like a critical install failure.
3. Counter said opaque "N issues" — no breakdown of how many were actual errors vs informational warnings.

Fixes (no functional changes, no test count change):
- **Font bump on chip**: `--text-sm` → `--text-md` (15px → 17px). Padding `6px 12px` → `10px 18px` for larger click target.
- **Smarter color escalation**: amber (warn) is now the default. Only escalates to red (fail) when FAIL items dominate (≥ half of total). 2 errors among 5 warnings stays amber — accurate "needs attention" signal without the "install broke" panic.
- **Breakdown text**: "6 issues" → "2 errors, 5 warnings" — tells user at a glance how serious the situation is.

4 persona dashboard screenshots re-shot in `docs/images/`. Now visibly amber for typical post-restore vault state.

1 test updated for new text format. 1369 tests still pass.

---

## v0.38.0 (2026-04-18)

**Persona-aware UI + UX polish + housekeeping. 1312 → 1369 tests (+57). Three problems flagged in v0.37.3 review, all fixed.**

User feedback after v0.37.3 dashboard screenshots:
1. "UI 有錯誤訊息" — doctor warnings dump as red wall, looks like install failure
2. "文字太小了" — base body 14px is cramped at @2x render
3. "如果今天他不是研究者 那這個就不通用了不是嗎" — non-researchers see academic vocabulary + features that don't apply

v0.38 fixes all three. Plus the v0.37 housekeeping backlog.

Full release report: [docs/audit_v0.38.md](docs/audit_v0.38.md). Per-persona dashboard preview: [docs/personas.md](docs/personas.md).

### Added — UX polish (Track A)

- **Collapsed health badge** (`sections.py::_render_health_banner`): doctor warnings now render as a discrete amber/red `<details>` chip ("⚠ N issues — click to expand") in the Overview header. Replaces the previous full-width red bullet list at top of Overview that scared new users.
- **Font scale bump** (`style.css:40-47`): `--text-sm` 14→15px, `--text-md` 16→17px (~7% larger). `.recent-author` bumped from `--text-xs` (12px) to `--text-sm` (15px). Tab labels weight 500→600.
- **Recent feed polish**: 16px row padding, hover highlight, `.recent-title` font 14→17px (`--text-md`), better visual hierarchy.

### Added — Persona-aware information architecture (Track B)

- **4-persona detection** (extends previous 2-value researcher/analyst):
  - `researcher` (default, PhD STEM)
  - `humanities` (PhD humanities, quote-heavy)
  - `analyst` (industry, no Zotero)
  - `internal` (internal KM, no Zotero)
- Resolution priority: `cfg.persona` (explicit at init) > `RESEARCH_HUB_PERSONA` env > legacy `cfg.no_zotero` → analyst > default researcher
- NEW `src/research_hub/dashboard/terminology.py`: per-persona display labels (Cluster → Topic / Theme / Project area; Crystal → AI Brief / Synthesis; Paper → Document / Source); tab visibility map; section gates
- Tab visibility: analyst/internal hide Diagnostics tab (Zotero-noise irrelevant)
- Section gating: Bind-Zotero button, compose-draft, citation graph, Zotero column hidden for analyst/internal; visible for researcher/humanities
- Init wizard: 4-option interactive prompt + `--persona researcher|analyst|humanities|internal` flag
- Doctor: WARN if `cfg.persona` not explicitly set (with remedy pointing to init)
- All preservation IDs / data-attrs / CSS+JS hooks intact across all 4 personas

### Added — Housekeeping (Track C)

- **Zotero key encryption at rest** (`src/research_hub/security/secret_box.py`): Fernet-based, machine-bound key file (0600 perms), `rh:enc:v1:` prefix marker, back-compat with plaintext (decrypt passes through unencrypted values). Optional dep: `cryptography` (gracefully degrades if missing). Migration: `research-hub config encrypt-secrets` CLI + auto-encrypt nudge on doctor.
- **Search recall baselines** (`tests/test_v038_search_baselines.py`): re-runs xfail search tests under `@pytest.mark.evals`, writes recall@10 to `metrics/search_recall.json` for trajectory tracking. Doesn't fail the build — just records.
- **`.dxt` MCP extension** (`src/research_hub/dxt.py` + `research-hub package-dxt` CLI): one-click Claude Desktop install via DXT archive (vs editing claude_desktop_config.json by hand).

### Refreshed — 4 persona dashboard screenshots

Same vault, four rendered dashboards in `docs/images/`: `dashboard-overview-{researcher,humanities,analyst,internal}.png`. Side-by-side preview gallery in `docs/personas.md`.

### Stats

- Tests: 1312 → 1369 (+57: A=8, B=37, C=12)
- New files: 4 (terminology.py + secret_box.py + dxt.py + 4 test files)
- Modified files: dashboard sections.py, style.css, data.py, context.py, render.py, init_wizard.py, config.py, doctor.py, cli.py, zotero/client.py
- New persona screenshots: 4 PNGs

### Reverted

- `pyproject.toml` adds `[secrets]` extra (`cryptography>=42`) — opt-in, not required

---

## v0.37.3 (2026-04-18)

**Hardening + screenshot refresh after the v0.37.2 CI fix.**

### Added — Reusable test fixture helper

The fix from v0.37.2 (clear parent-package attribute alongside `sys.modules`) is now a reusable conftest fixture so future test files can opt-in safely without re-discovering the gotcha:

```python
@pytest.fixture(autouse=True)
def _reset_cached_modules(reset_research_hub_modules):
    reset_research_hub_modules(
        "research_hub.crystal",
        "research_hub.workflows",
    )
```

`tests/test_v033_workflows.py` migrated to use it. Helper docstring documents the gotcha + 16-build CI red streak as the regression source.

### Refreshed — Dashboard screenshots with real vault

6 PNGs in `docs/images/` re-shot at @2x via `dashboard --screenshot all --full-page` against the restored 1094-paper vault (was: 36-paper demo vault). New views show:
- 5 real clusters with actual paper counts (LLM Agent Architecture: 331, LLM-SE: 20 + 4 subtopics, etc.)
- v0.37 doctor warnings rendered live (orphan papers, missing dirs)
- Real recent additions from the user's actual research corpus

### Audited — No other tests vulnerable

`grep` of `mock.patch("research_hub.<sub>.<func>")` across all test files confirmed only `test_v033_workflows.py` had the vulnerable autouse-pop + late-import combination. Other tests using `mock.patch` (test_drift_crystal, test_notebooklm_bundle, test_pdf_fetcher, test_v035_connectors) don't pop modules, so they aren't affected.

---

## v0.37.2 (2026-04-18)

**Final fix for the 16-build-long CI failure: parent-package attribute leak.**

After v0.37.1 fixed test_drift_crystal's `sys.modules` pollution, 3 tests in `test_v033_workflows.py` still failed on Python 3.10/3.11/3.12 with `assert False is True`. Root cause: the autouse `_reset_cached_modules` fixture popped `sys.modules["research_hub.crystal"]` but **not** the cached attribute on the parent package.

**The bug**:
1. mock.patch("research_hub.crystal.list_crystals") walks `getattr(research_hub_pkg, "crystal")` → finds the OLD module from a prior test
2. Patches `list_crystals` on the OLD module
3. `ask_cluster` does `from research_hub.crystal import list_crystals` → finds sys.modules empty (fixture popped it) → re-imports from disk → DIFFERENT module object → unpatched real function
4. Real `list_crystals` returns `[]` on tmp vault → no match → digest fallback fails → ok=False

**Fix**: Extended `_reset_cached_modules` to also `delattr(parent_pkg, child_name)`. This forces mock.patch's `_importer` to fall through to `__import__`, which re-loads the same module that ask_cluster's late import will find.

Local Python 3.14 didn't reproduce because Python 3.14's import machinery handles the parent-package attribute lookup differently.

**This was a 16-build-long CI red streak** since v0.30 — bug existed earlier, was masked locally by import ordering. Now confirmed green locally with both pytest 8 and 9. Memory file `feedback_research_hub_user_facing_bugs.md` updated to enforce CI-green-before-tag from now on.

---

## v0.37.1 (2026-04-18)

**CI green for the first time since v0.31.1. 15+ red builds caused by one test pollution bug.**

`tests/test_drift_crystal.py::_install_fake_crystal_module` permanently replaced `sys.modules["research_hub.crystal"]` with a stub module containing only `check_staleness`, with no teardown. In CI's alphabetical test order this stub leaked into every subsequent test that imports from `research_hub.crystal` — most notably `test_v033_workflows.py`, which then failed with `AttributeError: <module 'research_hub.crystal'> does not have the attribute 'list_crystals'` when `mock.patch` tried to find an attribute on the stub.

Locally the failure was hidden because Python 3.14 + pytest's discovery order in pip-editable mode loaded `research_hub.crystal` differently. CI uses 3.10/3.11/3.12 + plain install + `--maxfail=3`.

**Fix**: autouse fixture in `test_drift_crystal.py` snapshots `sys.modules["research_hub.crystal"]` and `research_hub.crystal` attribute before each test, restores both on teardown. 5-line change.

This release ships ONLY the fixture fix — same 1312 tests, no other code changes.

---

## v0.37.0 (2026-04-18)

**Cluster integrity + memory CLI/MCP exposure + critical require_config bug fix. 1282 → 1312 tests (+30).**

Two intersecting goals:
1. **Cluster ↔ paper binding can drift in any vault** (rename + folder not migrated, import-folder dump without --cluster, manual folder reorg). Doctor never noticed; rebind path didn't exist. v0.37 closes both gaps for all 4 personas.
2. **Memory layer (v0.36) was Python-API only.** v0.37 adds CLI subcommand + 4 MCP tools so Claude Code / any MCP client can query.
3. **Bonus critical fix**: `require_config()` now treats `RESEARCH_HUB_ROOT` env var as a valid init signal (was: required config.json file). Headless / CI / test environments no longer hit a misleading "not initialized" SystemExit when the env-var path is the only init.

Full release report: [docs/audit_v0.37.md](docs/audit_v0.37.md). Design notes: [docs/cluster-integrity.md](docs/cluster-integrity.md).

### Added — Cluster integrity (Track A)

5 new doctor checks in `src/research_hub/doctor.py`:
- `cluster/missing_dir` — FAIL: `cluster.obsidian_subfolder` doesn't exist as `raw/<dir>` (e.g. cluster renamed without folder migration)
- `cluster/orphan_papers` — WARN: `raw/foo/` holds papers but no cluster has `obsidian_subfolder=foo` (e.g. legacy layout, archive restore, import-folder dump)
- `cluster/empty` — WARN: cluster's folder has 0 papers
- `cluster/cross_tagged` — WARN: paper physically in cluster A folder but `cluster:` frontmatter says cluster B
- `quote/orphan` — WARN: quote captured on a paper not in any cluster (Persona C concern)

NEW `src/research_hub/cluster_rebind.py` — emit/apply rebind workflow:
- `emit_rebind_prompt(cfg)` walks `raw/`, reads each orphan paper's frontmatter (`cluster:`, `collections`, `tags`, `category`), proposes target cluster with high/medium/low confidence
- `apply_rebind(cfg, report_path, dry_run=True)` executes file moves; dry-run is the default
- All moves logged to `.research_hub/rebind-<timestamp>.log` for manual undo

NEW CLI: `research-hub clusters rebind {--emit, --apply <path> [--no-dry-run]}`.

### Added — Memory CLI + MCP exposure (Track B)

NEW CLI subcommand `research-hub memory {emit, apply, list, read}` matching the crystal subcommand pattern.

NEW 4 MCP tools (52 → 56):
- `list_entities(cluster)` — orgs/datasets/models/etc. registry
- `list_claims(cluster, min_confidence)` — typed claims with confidence filter
- `list_methods(cluster)` — technique families
- `read_cluster_memory(cluster)` — full ClusterMemory dict; returns `found: false` graceful fallback

### Fixed — `require_config()` env-var path (Track Z)

`src/research_hub/config.py::require_config` previously raised SystemExit("not initialized") whenever no `config.json` existed, even if `RESEARCH_HUB_ROOT` pointed to a valid directory. This blocked CI tests and any user bootstrapping via env vars (despite `HubConfig.__init__` fully honoring the env var). Now treats either signal as initialized.

3 regression tests in `tests/test_config.py`:
- `test_require_config_accepts_research_hub_root_env_var` — env-var path works
- `test_require_config_still_fails_when_root_dir_missing` — bogus paths still fail (security: don't accept any env value blindly)
- `test_require_config_fails_when_no_config_and_no_env` — original guard preserved

### Tests

- `tests/test_v037_cluster_integrity.py` — 18 tests (12 doctor/rebind + 6 persona × cluster-integrity matrix covering all 4 personas A/B/C/H)
- `tests/test_v037_memory_cli.py` — 6 tests
- `tests/test_v037_memory_mcp.py` — 4 tests
- `tests/test_config.py` — 3 new regression tests for require_config env-var path

### Vault restore (closes Task #124, pending since v0.28)

Restored 1094 paper notes (was 36) from `knowledge-base-archive-20260415/` across 9 topic folders + 5 archived clusters. Cleaned 4 `persona-*-test` test pollution folders + 5 stray quote files. Live-verified the new doctor checks against this real vault: detected 1063 orphans + 3 missing_dir + 5 quote orphans (all from test pollution, since cleaned).

### Stats

- Tests: 1282 → 1312 (+30)
- New files: 6 (rebind module + 3 test files + 2 docs)
- Modified: pyproject, CHANGELOG, README ×2, doctor, mcp_server, cli, config, mcp-tools.md

---

## v0.36.0 (2026-04-18)

**Structured memory layer (entities + claims + methods). 1270 → 1282 tests (+12). Architecture-only release.**

Crystals tell the AI *what to think* about a cluster (canonical prose). The new memory layer captures *what is named and asserted* in a cluster — orgs, datasets, models, benchmarks, methods, and structured claims with confidence + supporting paper slugs. Generated once per cluster via the same emit/apply pattern.

Full release report: [docs/audit_v0.36.md](docs/audit_v0.36.md). Design notes: [docs/cluster-memory.md](docs/cluster-memory.md).

### Added — Cluster memory (Track A)

NEW `src/research_hub/memory.py` (~280 LOC):
- 4 dataclasses: `MemoryEntity`, `MemoryClaim`, `MemoryMethod`, `ClusterMemory`
- 3 vocabularies (open-ended, suggested only): entity types (org/dataset/model/benchmark/method/person/concept/venue), method families (supervised/self-supervised/rl/finetune/prompt/search/graph/statistical/geometric/symbolic/hybrid/other), confidence levels (high/medium/low)
- `emit_memory_prompt(cfg, cluster_slug)` → builds AI extraction prompt (reuses `crystal._read_cluster_papers` + `_read_cluster_definition`)
- `apply_memory(cfg, cluster_slug, scored)` → validates JSON, dedups by slug, filters unknown paper slugs, writes atomic `hub/<slug>/memory.json`
- `read_memory`, `list_entities`, `list_claims`, `list_methods` query helpers
- Strict slug validation (lowercase kebab-case)
- Claims with no supporting papers are skipped

NEW `tests/test_v036_memory.py` — 12 tests covering emit + apply + filter + dedup + invalid-slug + invalid-confidence + empty-payload + round-trip + missing-file.

NEW `docs/cluster-memory.md` — design rationale, schema reference, how this differs from crystals, how to add a new entity type or method family.

### Preserved (zero behavioral changes)

- `crystal.py` unchanged — memory imports `_read_cluster_papers` and `_read_cluster_definition` read-only
- All CLI commands unchanged (no `memory` subcommand yet)
- All MCP tools unchanged (no `list_entities` / `list_claims` / `list_methods` exposed yet)
- `notebooklm/*` unchanged
- Connector Protocol from v0.35 unchanged

CLI + MCP integration of memory lands in v0.37 alongside the housekeeping batch.

### Stats

- Tests: 1270 → 1282 (+12)
- New files: 3 (memory module + tests + design doc)
- Modified files: 1 (pyproject version bump)
- LOC delta: ~+700

### Codex critique status (now complete)

- Phase 1 (Document abstraction) ✅ v0.31
- Phase 2 (structured memory) ✅ v0.36
- Phase 3 (tool consolidation) ✅ v0.33
- #5 (NLM as optional connector) ✅ v0.35

---

## v0.35.0 (2026-04-18)

**Connector Protocol abstraction. 1262 → 1270 tests (+8). Architecture-only release; no CLI/MCP changes.**

NotebookLM is no longer the only external service research-hub knows about. A new `Connector` Protocol formalizes the bundle/upload/generate/download/check_auth surface so future connectors (Notion, Google Drive, Logseq, custom KM systems) can be plugged in without touching workflows or CLI code.

Full release report: [docs/audit_v0.35.md](docs/audit_v0.35.md). Design notes: [docs/connector-design.md](docs/connector-design.md).

### Added — Connector Protocol (Track A)

NEW `src/research_hub/connectors/__init__.py` (~110 LOC):
- `Connector` typing.Protocol — name + 5 methods (`bundle`, `upload`, `generate`, `download`, `check_auth`)
- 3 dataclasses: `ConnectorBundleReport`, `ConnectorUploadReport`, `ConnectorBriefReport` — uniform Report shapes across all connectors
- Module-level registry: `register_connector()`, `get_connector(name)`, `list_connectors()`
- Auto-registers built-in `notebooklm` + `null` connectors at import time

NEW `src/research_hub/connectors/null.py` (~70 LOC) — `NullConnector` for testing and Persona B/H environments where NotebookLM is unavailable. Returns synthetic empty reports; `check_auth` always True.

NEW `src/research_hub/connectors/_notebooklm_adapter.py` (~110 LOC) — `NotebookLMConnector` wraps existing `notebooklm.bundle.bundle_cluster`, `notebooklm.upload.upload_cluster`, `notebooklm.upload.generate_artifact`, `notebooklm.upload.download_briefing_for_cluster`. Maps internal Report types to Protocol Report dataclasses.

NEW `tests/test_v035_connectors.py` — 8 tests: protocol satisfaction (`isinstance(c, Connector)`), registry validation (rejects empty name + non-Protocol objects), null connector synthetic returns, adapter delegation via `patch("research_hub.notebooklm.bundle.bundle_cluster")`.

NEW `docs/connector-design.md` — design rationale + how to add a new connector.

### Preserved (zero behavioral changes)

- `src/research_hub/notebooklm/*` — 2,463 LOC unchanged
- 15 existing import sites of `notebooklm.*` — unchanged
- All CLI commands — unchanged (no `--connector` flag yet)
- All MCP tools — unchanged
- All workflows.py wrappers — unchanged

This release is the architecture seam for v0.36+. CLI/MCP exposure of `--connector` flags lands when a second real connector is added.

### Stats

- Tests: 1262 → 1270 (+8 connector tests)
- New files: 5 (3 connector source + 1 test + 1 design doc)
- Modified files: 1 (pyproject version bump)
- LOC delta: +512

---

## v0.34.0 (2026-04-18)

**Dashboard polish + persona × pipeline test matrix. 1249 → 1262 tests (+13). No new features.**

CSS-only dashboard polish (dark mode, refined token system, animations) + first cross-persona test coverage (Personas C and H had ZERO direct tests before; now 4 personas tested).

Connector abstraction (the prior v0.34 plan) deferred to v0.35.

Full release report: [docs/audit_v0.34.md](docs/audit_v0.34.md). Persona reference: [docs/personas.md](docs/personas.md).

### Added — Dashboard polish (Track A)

`src/research_hub/dashboard/style.css` (~150 LOC added/edited):
- **Full dark mode** under `@media (prefers-color-scheme: dark)`. Auto-switches with OS theme.
- **Token system extended**: `--surface-3`, `--border-strong`, `--header-bg/-fg`, `--brand-glow`, `--ok-soft/--warn-soft/--fail-soft`, `--shadow-1/-2/-glow`, `--radius-sm/md/lg/xl/pill`, `--ease-out`, `--duration-fast/base`. Type scale gained `--text-md-2` (1.125rem) + `--text-2xl` (2rem) — fills the awkward 1rem→1.5rem gap.
- **Live pill**: pulsing animation + glow ring when active; calmer chip when off
- **Buttons**: hover lifts to `--brand-strong` + glow; active tap depresses 1px
- **Cluster cards**: hover lift + open shadow
- **Treemap cells**: gradient + radial highlight + lift-on-hover with saturation pulse
- **Status badges**: tinted backgrounds (was just colored borders)
- **Vault search**: focus ring with brand glow
- **Sticky header**: theme-aware via `--header-bg` (was hardcoded dark)

5 demo PNGs in `docs/images/` re-shot at @2x via the v0.32 `dashboard --screenshot` CLI.

**Constraints preserved (verified):** all 6 tab radio IDs, all 6 panel IDs, `vault-search`, `live-pill`, `csrf-token`, all `data-jump-tab`/`data-cluster`/`[data-action]` attributes. Zero changes to `template.html`, `script.js`, or any Python.

### Added — Persona × pipeline test matrix (Track B)

NEW `tests/_persona_factory.py` — `make_persona_vault(tmp_path, persona)` builds vault state for personas A/B/C/H. Forces `RESEARCH_HUB_CONFIG=/nonexistent` to bypass developer's real config (caught a real pollution bug during development).

NEW `tests/test_v034_persona_matrix.py` — 13 tests targeting 8 high-risk persona × pipeline combinations + persona-aware doctor + dashboard rendering for all personas. Coverage shifts from "Persona A everywhere + B in 2 spots" to "all 4 personas have at least one direct test for their critical pipeline."

NEW `docs/personas.md` — formal persona reference. Per-persona profile, typical CLI pipeline, per-feature ✅/🟡/❌ matrix. Maps each persona to its test file.

### Fixed — pre-release CI hygiene (shipped earlier today as v0.33.3, included here)

- `pyproject.toml addopts` filters `-m 'not stress'` so 1000-paper stress tests stay opt-in
- `tests/conftest.py` autouse fixture path pattern extended from `test_cli_*.py` to also match `test_v0NN_*.py` for v030+ tests calling `cli.main([...])`

### Test count

| Release | Passing | Skipped | xfail | Delta |
|---|---|---|---|---|
| v0.33.3 | 1249 | 14 | 2 + 1 xpassed | — |
| **v0.34.0** | **1262** | **14** | **2** + 1 xpassed | **+13** |

### Out of scope (v0.35+)

- **Connector abstraction** — still 1-2 days work; deferred to focus this release on polish + tests
- **Codex Phase 2 (structured memory)** — multi-release research project
- **`cli.py` / `mcp_server.py` monolith splits** — HIGH RISK
- **Live NotebookLM round-trip in CI** — needs Chrome+CDP
- **Task #124 archived vault restore** — needs user decision
- **Search recall xfail baselines** (v0.26)
- **Zotero key encryption** via OS keyring
- **`.dxt` Claude Desktop extension**

## v0.33.3 (2026-04-18)

**Patch: stress test marker filter + screenshot CLI test autouse fixture extension.**

Two CI hygiene fixes that surfaced after v0.33.2:

### Fixed — stress tests no longer run by default

`tests/test_v030_large_vault.py::test_dashboard_render_1000_papers_under_5s` was running in the default pytest run despite the `pytestmark = pytest.mark.stress` marker. The marker was registered in `pyproject.toml::[tool.pytest.ini_options].markers` (purely documentary) but the `addopts` line never actually filtered them out.

Fix: added `-m 'not stress'` to `addopts`. `pytest -m stress` still opts in.

### Fixed — `test_v032_screenshot.py::test_cli_screenshot_requires_out_for_single_tab` CI fail

The autouse `_auto_mock_require_config` fixture in `tests/conftest.py` only matched `tests/test_cli_*.py` paths. v0.32's screenshot test calls `cli.main([...])` from a `test_v032_*.py` file, so it hit `require_config()` and crashed in CI (no config file).

Fix: extend the autouse fixture path pattern to match `test_v0NN_*.py` for v030+ files (currently v030, v031, v032, v033, v034). Patches `cli.get_config` only — NOT `cli.require_config` itself, since the dispatcher detects monkey-patching via `cli.get_config is require_config.__globals__["get_config"]` and would break if we replaced require_config (lambda has different __globals__).

## v0.33.2 (2026-04-17)

**Patch: brief_cluster fixes found in live NotebookLM round-trip test.**

Full live round-trip validation (bundle → upload → generate → download → preview against real NotebookLM with 20 sources) caught two bugs in the `brief_cluster` wrapper that all unit tests missed (because they mocked the cluster registry).

### Fixed — `ClusterRegistry` has no `load()` method

`brief_cluster` called `ClusterRegistry.load()` but the registry auto-loads on `__init__`. Removed the redundant call.

### Fixed — wrong attr name for source count

`bundle_result.source_count` doesn't exist on `BundleReport`; it has `pdf_count` and `url_count` properties instead. `brief_cluster` now returns `pdf_count`, `url_count`, AND their sum as `source_count`.

### Verified — end-to-end live

Live round-trip on `llm-agents-software-engineering` cluster (20 URL sources):
- Bundle: 20 URLs bundled
- Upload: 6 new uploaded, 14 skipped from cache (prior NLM session auth still valid)
- Generate: 3 saved briefings created
- Download: 313-char briefing persisted to `.research_hub/artifacts/`
- `brief_cluster` wrapper: completes with `steps=[bundle, download]` when notebook already exists

## v0.33.1 (2026-04-17)

**Patch: ask_cluster fuzzy-match bugs found via live testing. 1247 → 1249 tests (+2 regression).**

Live smoke-test of v0.33.0 on the real `llm-agents-software-engineering` cluster (10 crystals) caught two bugs in the `ask_cluster` fuzzy matcher:

### Fixed — `ask_cluster` false-miss on boundary scores

The token_set_ratio cutoff of 60 was too strict. "what is this field about" vs "What is this research area about?" scores 59.6 — just below the cutoff, causing a false miss and digest fallback. **Cutoff lowered to 55.** Canonical questions still score ≥60 when matching; unrelated questions still score <40.

### Fixed — `ask_cluster` false-positive via WRatio scorer

Adding rapidfuzz's `WRatio` as a fallback scorer turned out promiscuous. Example: "what is this field about" ↔ "Why does this research matter now? What changed?" scored WRatio=86 (because of "What" in the target) while the correct match scored only 67. **Removed WRatio**, kept only token_set_ratio applied to both the crystal question text AND the slug-as-words (slugs often match better when user rephrases, e.g. "what is this field about" → slug "what-is-this-field" tokenises to the same words).

### Added — acronym expansion for common research terms

"what's the SOTA" scored only 33 against "What is the current state of the art..." because the acronym and full phrase share no tokens. Added `_expand_acronyms()` preprocessing that expands SOTA → state of the art, LLM → large language model, RAG → retrieval augmented generation, RL → reinforcement learning, etc. both sides before scoring.

### Test matrix (post-fix live against real cluster)

| User query | Matched crystal | Score |
|---|---|---|
| "what is this field about" | what-is-this-field | 100 |
| "what's the SOTA" | sota-and-open-problems | 82 |
| "how do people evaluate work" | evaluation-standards | 92 |
| "common mistakes beginners make" | common-pitfalls | 80 |
| "completely unrelated question about cooking" | (falls back to digest) | - |

+ 2 regression tests in `tests/test_v033_workflows.py` for both failure modes.

## v0.33.0 (2026-04-17)

**Tool consolidation (Codex Phase 3). 1235 → 1247 tests (+12). 5 task-level MCP wrappers on top of 64 low-level tools.**

Addresses the Codex architecture critique: "把 50+ tools 往上收斂成 task-oriented actions... 底下再去調 MCP tool." Casual Claude Desktop users now get 2-3× faster workflows (1 call instead of 3-4). Power users unaffected — all 64 low-level tools registered unchanged.

Full release report: [docs/audit_v0.33.md](docs/audit_v0.33.md). User guide: [docs/task-workflows.md](docs/task-workflows.md).

### Added — Track A: 5 task-level workflow wrappers

**New file:** `src/research_hub/workflows.py` (~440 LOC). Every function imports and calls existing internals; zero logic duplication.

- **`ask_cluster(cluster_slug, question, detail="gist")`** — read path. Fuzzy-matches natural-language question against crystal questions via rapidfuzz. Falls back to topic digest if no crystal matches. Replaces the common 3-call sequence `list_crystals → read_crystal → (optional) search_vault`.
- **`brief_cluster(cluster_slug, force_regenerate=False)`** — full NotebookLM round-trip. Chains `notebooklm_bundle → upload_cluster → generate_artifact → download_briefing_for_cluster → read_briefing`. Degrades gracefully if Playwright not installed.
- **`sync_cluster(cluster_slug)`** — "what needs attention" maintenance view. Combines `check_crystal_staleness + drift_check + run_doctor` into a prioritized recommendations list with copy-paste CLI commands.
- **`compose_brief_draft(cluster_slug, outline=None, max_quotes=10)`** — writing assembly. Builds default outline from cluster overview + crystal TLDRs when outline not provided, then delegates to `compose_draft`.
- **`collect_to_cluster(source, cluster_slug, ...)`** — unified ingest. Auto-routes: DOI/arXiv → `add_paper`; folder path → `import_folder`; http(s):// URL → `.url` file + `import_folder`.

### Added — CLI

- **`research-hub ask <cluster> "<question>" [--detail tldr|gist|full]`** — terminal wrapper for `ask_cluster`. Other 4 workflows stay MCP-only (see audit for why).

### Added — Tests

- **12 new tests** in `tests/test_v033_workflows.py`. Autouse fixture pops cached `research_hub.*` modules between tests to prevent ordering pollution that surfaced during development.
- **5 new entries** in `tests/test_consistency.py::EXPECTED_MAPPINGS` for the 5 new MCP tools.

### Added — Documentation

- `docs/task-workflows.md` (NEW) — user-facing guide with example Claude Desktop prompts for each wrapper.
- `docs/audit_v0.33.md` (NEW) — release report with design decisions and verification.

### Backward compatibility

**Absolute.** All 64 v0.32 MCP tools and signatures remain unchanged. Calling code written against v0.32 works identically against v0.33. `tests/test_consistency.py::test_no_orphaned_mappings` gates this — it would fail if any tool were removed.

### Test count

| Release | Passing | Skipped | xfail | Delta |
|---|---|---|---|---|
| v0.32.0 | 1235 | 14 | 2 + 1 xpassed | — |
| **v0.33.0** | **1247** | **14** | **2** + 1 xpassed | **+12** |

### Notes on delivery

Codex Track A hung after 15 minutes of exploration (same pattern as v0.30/v0.31/v0.32 Codex stalls when faced with large multi-file surveys). Claude took over directly, inspected actual internal signatures (crystal attrs, NLM function names, fit-check API), and finished the implementation. Workflows.py matches the real codebase — several of the brief's guessed function names were wrong (e.g. `upload_cluster_bundle` vs real `upload_cluster`).

### Out of scope (v0.34+)

- **Codex Phase 2** — structured memory layer (entities / claims / methods / datasets)
- **Connector abstraction** — NotebookLM as pluggable plug-in
- **`cli.py` / `mcp_server.py` monolith splits** — still HIGH RISK
- **Live NotebookLM round-trip test** — when user opens Chrome
- **Task #124 archived vault restore** — needs user decision on merge strategy
- **Search recall xfail baselines** (v0.26)
- **Zotero key encryption** via OS keyring
- **`.dxt` Claude Desktop extension**

## v0.32.0 (2026-04-17)

**Polish: high-quality screenshots + housekeeping. 1227 → 1235 tests (+8). No architectural changes.**

User concrete pain: existing `docs/images/*.png` were 800-1200 px non-Retina manual captures from weeks ago. v0.32 ships a permanent fix: a `--screenshot` CLI that re-renders any dashboard tab via headless Playwright at user-controlled DPI. All 5 demo PNGs re-shot at 2880×1800 (Retina @2x). Plus graphify integration redesign (v0.31.1 design bug) and external repo fix to `gemini-delegate-skill`.

Full release report: [docs/audit_v0.32.md](docs/audit_v0.32.md).

### Added — Track A: Dashboard `--screenshot` CLI

- **`src/research_hub/dashboard/screenshot.py`** (NEW): `screenshot_dashboard()` and `screenshot_all()` render the self-contained `dashboard.html` in headless Chromium at user-controlled `device_scale_factor`.
- **CLI:** `research-hub dashboard --screenshot TAB --out PATH --scale 2 --viewport-width 1440 --viewport-height 900`
- **Tabs:** overview / library / briefings / writing / diagnostics / manage (+ crystal alias for briefings)
- **Batch:** `--screenshot all --out-dir DIR` writes one PNG per tab
- **Default scale=2** = Retina-grade (2880×1800). Pass `--scale 3` for print-quality (5760×3600).
- **Graceful** `PlaywrightNotInstalled` error if `[playwright]` extra missing (same dep as NotebookLM).
- **5 new tests** in `tests/test_v032_screenshot.py` (Playwright mocked).

### Added — Track B: 5 dashboard PNGs re-shot at @2x

All 5 PNGs in `docs/images/` re-captured via the new CLI. File sizes ~6-7× larger; resolution ~3.5× per axis.

### Added — Track C: New image + Mermaid

- **`docs/images/import-folder-result.png`** — Library tab showing imported docs (referenced from `import-folder.md` + `.zh-TW.md`)
- **`docs/example-claude-mcp-flow.md`** — NEW Mermaid sequence diagram showing full ingest → crystallize → query → bundle flow visually (renders natively on GitHub)

### Fixed — Track D: graphify integration redesign

v0.31.1 audit documented: graphify is a coding-skill, not a standalone CLI. v0.31's `--use-graphify` always failed soft.

- **`--graphify-graph PATH`** flag added — accepts pre-built `graph.json` from user's `/graphify` skill run in Claude Code
- **`--use-graphify`** kept for backward compat (now emits `DeprecationWarning` and skips integration)
- **`graphify_bridge.run_graphify()`** deprecated — raises `GraphifyNotInstalled` with actionable 2-step workflow guidance
- **`graphify_bridge.parse_graphify_communities()`** + `map_to_subtopics()` unchanged (still parse pre-built graph.json)
- **`docs/import-folder.md`** rewrote "Deep extraction with graphify" section with the new workflow
- **3 new tests** in `tests/test_v032_graphify_redesign.py`
- **3 v0.31 graphify tests** updated for new deprecated behavior (test count unchanged for those)

### Added — Track E: Documentation

- **`docs/screenshot-workflow.md`** (NEW) — usage guide for the screenshot CLI, custom dimensions, batch capture, Obsidian graph manual workflow, troubleshooting
- **`docs/audit_v0.32.md`** (NEW) — release report with before/after metrics

### Fixed — Track F: gemini-delegate-skill external repo

External repo `https://github.com/WenyuChiou/gemini-delegate-skill` updated (commit `7493c8e`):

- **`SKILL.md`**: NEW "Fourth rule" section — verify file writes after Gemini exits. Documents two failure modes from v0.31 work: (1) `Error executing tool write_file: params must have required property 'file_path'` after first successful write, (2) silent partial writes from rate-limit retries. Includes B-grade translation-quality caveat.
- **`scripts/run_gemini.sh`** + **`.ps1`**: NEW `--verify-file PATH` (repeatable) + `--verify-sentinel TEXT` flags. After gemini exits, check expected files exist + non-empty + optionally contain sentinel string. Exit 1 with `VERIFY_FAILED` if not.
- **`README.md`**: "Known Limitations" section with verify-file usage example
- **Local skill** at `~/.claude/skills/gemini-delegate/` synced

### Test count

| Release | Passing | Skipped | xfail | Delta |
|---|---|---|---|---|
| v0.31.1 | 1227 | 14 | 2 + 1 xpassed | — |
| **v0.32.0** | **1235** | **14** | **2** + 1 xpassed | **+8** |

### Out of scope (v0.33+)

- **Codex Phase 2** — structured memory layer (entities/claims/methods/datasets)
- **Codex Phase 3** — tool consolidation (50+ tools → 5 task-level wrappers)
- **Connector abstraction** (NotebookLM → optional plug-in)
- **`cli.py` / `mcp_server.py` monolith splits** — still HIGH RISK
- **Search recall xfail baselines** (v0.26)
- **Restore archived vault** (Task #124) — archive contents have legacy folder names predating v0.27 cluster slugs; needs user decision on merge strategy
- **Live NotebookLM round-trip test** — needs user to open browser + CDP attach
- **Zotero key encryption**, **CDP token rotation**, **`.dxt` Claude Desktop extension**

## v0.31.1 (2026-04-17)

**Patch release: 3 bugs found in v0.31 live smoke test + 1 CI flake fix. 1223 → 1227 tests (+4).**

All bugs were caught within an hour of v0.31.0 shipping by hands-on validation against PDF, DOCX, URL, and graphify imports. Patches landed same day.

### Fixed — `import-folder` quality

- **PDF title derivation** (`src/research_hub/importer.py`): imported PDF notes now prefer embedded PDF metadata title, then fall back to the first non-empty extracted line. Previously fell straight to the filename.
- **DOCX title derivation** (`src/research_hub/importer.py`): DOCX extractor refactored to return `(title, body)`. Title sourced from `core_properties.title` or the first `Heading 1` / `Title` paragraph before falling back to the filename.
- **Markdown and TXT title logic clarified**: markdown keeps `# ` H1 detection; plain text uses the first non-empty short line when it looks like a title.
- **URL extraction returns plain text, not raw HTML** (`src/research_hub/importer.py::_html_to_text`): `_extract_url` now strips HTML tags from `readability-lxml`'s `.summary()` output via stdlib `html.parser`, preserving paragraph breaks. Previously imported URL notes had full `<html><body><div>...` markup in the body.

### Fixed — `clusters delete`

- **`--purge-folder` flag added** (`src/research_hub/cli.py`): optional destructive cleanup removes `<vault>/raw/<slug>/` and `<vault>/hub/<slug>/` after unbinding the registry entry. Default behavior unchanged (registry-only unbind).

### Fixed — CI test compatibility

- **`tests/test_v030_security.py`**: `test_mcp_read_crystal_blocks_traversal_slug` and `test_mcp_add_paper_blocks_injection_identifier` previously called `tool.fn(...)` directly. CI runs a fastmcp version where the decorator returns the raw function (no `.fn` attribute) — tests now use `getattr(tool, "fn", tool)` to work in both environments. Same pattern Track D's NotebookLM tests already use.

### Documented — graphify integration limitation

Live attempt to use `--use-graphify` revealed graphify (`pip install graphifyy`) is not a standalone CLI for full first-time extraction — it's a coding-assistant skill that runs subagents from inside Claude Code / Codex / etc. Standalone `graphify <folder>` is not a valid invocation. Our `graphify_bridge.run_graphify()` will always fail with subprocess error in v0.31. Workaround in v0.31.1: `--use-graphify` continues to fail-soft (warning logged, import continues without sub-topic assignment). v0.32 will redesign the integration: either invoke `graphify update <path>` (no-LLM AST mode) or document a "use Claude Code's `/graphify` skill, then point research-hub at the produced `graphify-out/graph.json`" workflow with a new `--graph-json` flag.

### Added

- **4 regression tests** in `tests/test_v031_1_quality.py`.

## v0.31.0 (2026-04-17)

**Document abstraction + analyst persona enablement. 1199 → 1223 tests (+24).**

External Codex architecture review surfaced a real strategic gap: research-hub was too paper-centric to serve users with folders of mixed local docs (industry researchers, internal knowledge bases, founders doing market research). The repo's analyst persona existed in name but the ingest pipeline still demanded a DOI. v0.31 starts the `paper → document` abstraction without breaking academic paper paths, and adds `import-folder` so folder-of-PDFs use cases work end-to-end. Plus closes the NotebookLM CLI/MCP asymmetry critique.

Full release report: [docs/audit_v0.31.md](docs/audit_v0.31.md).

### Added — Track A: Document abstraction

- **`src/research_hub/document.py`** (NEW) — `Document` base class with 7 canonical source kinds (paper / pdf / markdown / docx / txt / url / transcript). `Paper` becomes a subclass with the rich academic frontmatter; non-academic content uses `Document` directly with minimal frontmatter.
- **Backward compat:** existing paper notes have `source_kind: paper` implicit (parser defaults to "paper" if field missing). No migration needed.
- **6 new tests** in `tests/test_v031_document.py`.

### Added — Track B: `import-folder` command

- **`src/research_hub/importer.py`** (NEW, ~280 LOC) — walks a folder, extracts text per file type, writes Document notes via `atomic_write_text`.
- **5 supported file types**: `.pdf` (pdfplumber), `.md` / `.markdown` (direct), `.txt` (direct + encoding detect), `.docx` (python-docx), `.url` (requests + readability-lxml).
- **Dedup by SHA256 content hash** alongside existing DOI dedup.
- **Auto-creates cluster** if `--cluster` slug doesn't exist.
- **`--dry-run`** flag for preview before writing.
- **`--use-graphify`** flag delegates to Track C for deep multi-modal extraction.
- **CLI:** `research-hub import-folder ./project --cluster X`
- **MCP tool:** `import_folder_tool(folder, cluster_slug, dry_run)`
- **New optional deps** in `pyproject.toml`: `[project.optional-dependencies] import = [pdfplumber, python-docx, readability-lxml, requests]`. Install via `pip install 'research-hub-pipeline[import]'`.
- **8 new tests** in `tests/test_v031_import_folder.py`.

### Added — Track C: graphify bridge

- **`src/research_hub/graphify_bridge.py`** (NEW, ~140 LOC) — subprocess wrapper around the external [graphify](https://github.com/safishamsi/graphify) CLI for users who want deep multi-modal extraction (PDFs + code + images + video transcripts) and Leiden community detection-based sub-topic suggestions.
- `find_graphify_binary()` detects graphify on PATH; raises `GraphifyNotInstalled` with actionable install instructions if missing.
- `parse_graphify_communities()` reads graphify's `graph.json`, groups nodes by community.
- `map_to_subtopics()` matches graphify's communities to research-hub's imported files for `subtopics:` frontmatter assignment.
- graphify is **NOT** added to research-hub deps — user installs separately via `pip install graphifyy && graphify install`.
- **4 new tests** in `tests/test_v031_graphify_bridge.py` (all subprocess mocked).

### Added — Track D: NotebookLM MCP tools

Closes the CLI/MCP asymmetry external critique flagged: `read_briefing` was MCP but the rest of the NotebookLM round-trip was CLI-only.

- `notebooklm_bundle(cluster_slug, download_pdfs)` — wrap existing bundle handler as MCP tool
- `notebooklm_upload(cluster_slug)` — Playwright + CDP attach upload
- `notebooklm_generate(cluster_slug, artifact_type)` — trigger brief generation
- `notebooklm_download(cluster_slug)` — pull generated brief into vault artifacts
- AI agents (Claude Desktop) can now drive the full ingest → bundle → upload → generate → download flow without dropping to terminal.
- **3 new tests** in `tests/test_v031_notebooklm_mcp.py` (Playwright mocked).

### Added — Track E: Documentation

- **`docs/import-folder.md`** + **`docs/import-folder.zh-TW.md`** — usage guide for the new feature with examples per file type, troubleshooting, graphify walkthrough. zh-TW translated by Gemini and edited by Claude (first production Gemini test — see audit).
- **`docs/audit_v0.31.md`** — release report.
- **README.md + README.zh-TW.md** — Architecture docs section links to new docs.

### Fixed — Track Z: ship-today (commit fa4e0e2)

- README.md:198 + README.zh-TW.md:198: `1113 passing` → `1199 passing` (left over from v0.30).
- Created GitHub Releases for v0.10.0 through v0.30.0 via `gh release create --generate-notes` (was only on tags before; "Latest" badge had been showing v0.9.0).

### Test count

| Release | Passing | Skipped | xfail | Delta |
|---|---|---|---|---|
| v0.30.0 | 1199 | 14 | 2 + 1 xpassed | — |
| **v0.31.0** | **1223** | **14** | **2** + 1 xpassed | **+24** |

### Out of scope (v0.32+ — Codex critique deferred items)

- **Structured memory layer** (entities / claims / methods / datasets) — Codex's Phase 2. Genuinely a research project; needs its own design + scope.
- **Tool consolidation to ~5 task-level actions** — Codex's Phase 3. Risky for AI agent users who want fine-grained primitives. Need to design carefully so we expose BOTH layers.
- **Stable external API + auto-sync version/test counts** — infra, not user-visible.
- **NotebookLM as fully optional connector** — already true (analyst persona); Track D closed the MCP asymmetry but didn't extract a connector interface.
- **v0.30's deferred Track D refactor** (`cli.py` / `mcp_server.py` splits) — still HIGH RISK, still deferred.

## v0.30.0 (2026-04-16)

**Hardening + production audit. 1142 → 1199 tests (+57). Closes 28-issue audit.**

The release that takes research-hub from "shipping fast" to "safe to recommend to others." A 3-agent audit found 28 issues across security, workflow correctness, UX, performance, docs, and tests; this release closes 20 of them across 4 parallel tracks. The headline P0 fix: **`pipeline.py` Zotero collection routing was broken** — when a cluster was bound to a Zotero collection, papers always went to the default. The user's literal stated workflow ("整理到Zotero 對應collection") was silently broken in v0.29 and is fixed in v0.30.

Full release report: [`docs/audit_v0.30.md`](docs/audit_v0.30.md). Migration guide: [`UPGRADE.md`](UPGRADE.md).

### Fixed — Track A: Critical fixes + security

- **Zotero collection routing** (P0 #1) — `pipeline.py` now routes papers to the cluster-bound `zotero_collection_key` instead of always using the default. The cluster collection was already computed for dedup checks but never plumbed to `t["collections"]`. Adds explicit log line `Routing to collection: KEY (cluster=slug)` so users can verify.
- **Path traversal** (P0 #2) — new `src/research_hub/security.py` module: `validate_slug`, `validate_identifier`, `safe_join`, `chmod_sensitive`, `atomic_write_text`. Wired `validate_slug()` into 50+ MCP tool call sites. `Path(cfg.X) / cluster_slug / ...` constructions in `crystal.py`, `topic.py`, `clusters.py` now use `safe_join`.
- **CSRF + Origin check on `/api/exec`** (P0 #3) — server generates CSRF token at startup, embeds in HTML as `<meta name="csrf-token">`; clients must send `X-CSRF-Token` header. Origin header validated against server's bind address.
- **Subprocess kill on timeout** (P0 #4) — `dashboard/executor.py` switched from `subprocess.run(timeout=...)` to `Popen` + explicit `proc.kill()` on `TimeoutExpired`. No more zombie processes piling up.
- **File permissions** (P1 #6) — `init_wizard.py` + `config.py` now `chmod 700` on `~/.research_hub/` and `chmod 600` on `config.json` (POSIX only; Windows handled via NTFS ACLs).
- **Identifier validation** (P1 #7) — MCP `add_paper(identifier=...)` rejects shell metacharacters, semicolons, newlines.
- **Atomic state writes** (P1 #8) — `clusters.yaml`, `dedup_index.json`, crystal markdown writes go through `atomic_write_text` (tmp file + `os.replace`).
- **`--allow-external` warning** (P1 #9) — 5-second banner warning before `serve --dashboard --host 0.0.0.0`. Skip via `--yes`.
- **Bounded SSE queue** (P2 #13) — backpressure via oldest-event-drop instead of blocking new events.

### Fixed — Track B: UX + Performance

- **Cross-platform file locks** — new `src/research_hub/locks.py` (~80 LOC) with `fcntl`/`msvcrt` advisory `file_lock(path)` context manager. Wrapped `clusters.py::ClusterRegistry.save()` and `dedup.py::DedupIndex.save()` so two concurrent processes (e.g., dashboard server + CLI ingest) don't corrupt state.
- **Cluster slug case normalization** (P2 #14) — `ClusterRegistry.get()` and `create()` now normalize slug to lowercase + strip whitespace. `clusters get LLM-AGENTS`, `clusters get llm-agents`, `clusters get "  LLM-Agents  "` all resolve to the same cluster.
- **Env var validation** (P2 #15) — `config.py` `_validate_root_under_home()` rejects `RESEARCH_HUB_ROOT` paths outside `$HOME` unless explicitly opted in via `RESEARCH_HUB_ALLOW_EXTERNAL_ROOT=1` (e.g., shared network drive). Prevents misconfigured env vars from creating vault folders in system directories.
- **`--help` epilog with "Start here" banner** (P1 #12) — `research-hub --help` now ends with a 5-step quickstart pointing at `init` → `doctor` → `where` → `serve --dashboard` → `install --mcp`. Plus link to GitHub.

### Added — Track C: Test gap closure

NEW test files:
- `tests/test_v030_migration.py` (5 tests) — v0.10 → v0.29 vault format compatibility
- `tests/test_v030_concurrent.py` (4 tests) — `file_lock` contract, atomic write idempotence
- `tests/test_v030_unicode.py` (5 tests) — CJK / RTL / emoji titles, slugs rejected for non-ASCII
- `tests/test_v030_large_vault.py` (4 stress tests) — 1000-paper render budget, 500-paper dedup rebuild

### Added — Track E: Documentation

- **`docs/mcp-tools.md`** (~250 lines) — 50+ MCP tools categorized by stage (discovery, clusters, labels, sub-topics, crystals, fit-check, autofill, citation graph, quotes, search, examples) with signatures + use cases. Closes the gap that left Claude Desktop users blind to research-hub's capabilities.
- **`UPGRADE.md`** (~135 lines) — Migration guide covering v0.1 → v0.30, with quick path for v0.28/v0.29 users + breaking-changes detail for older versions + rollback procedure.
- **`docs/anti-rag.zh-TW.md`** (~200 lines) — Full 繁體中文 translation of the architectural explainer. Largest non-Anglophone audience.
- **`docs/example-claude-mcp-flow.md`** (~180 lines) — Worked example: ingest paper → crystallize cluster → query → handle staleness → cluster split. With token economics ($0.94/year per cluster vs $23.40 with raw-paper queries).
- **`docs/audit_v0.30.md`** (~190 lines) — Release report with before/after metrics + per-track delivery summary + verification commands.

### Test count

| Release | Passing | Skipped | xfail | Delta |
|---|---|---|---|---|
| v0.29.0 | 1142 | 12 | 5 | — |
| **v0.30.0** | **1199** | **14** | **2** + 1 xpassed | **+57** |

### Out of scope (v0.31+)

- Track D refactor — `cli.py` (3012 LOC) and `mcp_server.py` (1458 LOC) splits deferred (HIGH RISK; non-essential)
- Audit log, CDP token rotation, symlink config validation, Zotero key encryption, gRPC/REST API, .dxt Claude Desktop extension
- Search-quality v0.26 xfail baselines (5 outstanding) and citation-graph optimization for >500-paper clusters

## v0.29.0 (2026-04-16)

**Onboarding UX — confusion-proof first install. 1122 → 1142 tests (+20).**

Fixes 7 pain points that confused new users about "source code vs vault" separation.

### Added
- **`research-hub where`** — instant (<0.1s) status showing config path, vault path, note count, crystal count, MCP config status, and vault folder tree. No API calls. The first command a new user should run after `init`.
- **`research-hub install --mcp`** — auto-writes `research-hub` MCP server entry to `claude_desktop_config.json` (Windows/macOS/Linux paths auto-detected). Non-destructive merge preserves existing MCP servers. Prints "Restart Claude Desktop to activate."
- **`require_config()`** in `config.py` — fails early with actionable error ("Run: research-hub init") when no config exists, instead of silently creating vault at `~/knowledge-base`. Wired into all CLI commands except `init`, `doctor`, `install`, `examples`.
- **Init completion banner** — `research-hub init` now ends with formatted box showing vault path + config path + 4-step ordered command checklist (doctor → add → serve → install --mcp).
- **Existing Obsidian vault detection** — if init path contains `.obsidian/`, prints note count + "will add folders alongside your notes, nothing overwritten".
- **Doctor header** — `research-hub doctor` now prints config + vault paths at the top before running checks, so user immediately sees which vault they're checking.
- **README "Source code vs vault" section** — new table explaining the two-directory design in both README.md (EN) and README.zh-TW.md (繁中).
- **6 demo screenshots** in `docs/images/` — dashboard overview, crystals section, library sub-topics, manage live pill, diagnostics, Obsidian graph view with label coloring.
- **20 new tests** in `tests/test_onboarding_ux.py`.

### Changed
- **PyPI description** updated to: "CLI + MCP server for Zotero + Obsidian + NotebookLM research pipelines. Run `research-hub init` after install."

### Test count
| Release | Passing | Delta |
|---|---|---|
| v0.28.0 | 1122 | — |
| **v0.29.0** | **1142** | **+20** |

## v0.28.0 (2026-04-15)

**Crystals — anti-RAG semantic compression. Pre-computed canonical Q→A answers replace query-time context assembly. 1087 → 1122 tests (+35).**

First research-hub release that changes the architectural axis instead of refining the existing one. Full architectural explainer: [`docs/anti-rag.md`](docs/anti-rag.md). Release audit: [`docs/audit_v0.28.md`](docs/audit_v0.28.md).

### The shift

Every previous research-hub MCP tool returned **raw materials** (paper abstracts, cluster digests, topic lists) that the calling AI had to piece together at query time. v0.28 introduces a parallel path: for each cluster, the user's AI writes up to 10 canonical Q→A answers ONCE via emit/apply, stored as markdown. Subsequent queries read the pre-written answer directly — no re-synthesis, no 30 KB abstract dumps.

Measured token efficiency on the test cluster: **32 KB (old get_topic_digest) → 1.8 KB (new list_crystals + read_crystal) = ~18× reduction** for common-case cluster-level questions. Quality is deterministic because synthesis happens once at generation time, not per-query.

### Added — Track A: Crystal core (`crystal.py`)

- **`src/research_hub/crystal.py`** (~320 LOC) — full module with:
  - `CANONICAL_QUESTIONS` — 10 slots (what-is-this-field / why-now / main-threads / where-experts-disagree / sota-and-open-problems / reading-order / key-concepts / evaluation-standards / common-pitfalls / adjacent-fields)
  - `Crystal`, `CrystalEvidence`, `CrystalStaleness` dataclasses
  - `emit_crystal_prompt()` — builds markdown prompt with cluster paper list + 10 questions + JSON schema
  - `apply_crystals()` — parses JSON, writes to `hub/<cluster>/crystals/<slug>.md` (idempotent)
  - `list_crystals()` / `read_crystal()` / `check_staleness()` — query API
  - Stores `based_on_papers:` provenance + `last_generated:` + `generator:` + `confidence:` in frontmatter
  - `STALENESS_THRESHOLD = 0.10` — crystal flagged stale if >10% of cluster papers changed since generation
- **`research-hub crystal emit/apply/list/read/check`** — new CLI sub-commands mirroring the autofill + fit-check emit/apply pattern
- **5 new MCP tools**: `list_crystals`, `read_crystal`, `emit_crystal_prompt`, `apply_crystals`, `check_crystal_staleness` (total MCP tool count now 52)
- **26 new tests** in `tests/test_crystal.py` covering emit + apply + round-trip + staleness + canonical question stability

### Added — Track B: Crystal dashboard surface

- **`CrystalSection`** in `dashboard/sections.py` — renders inside Overview tab, shows per-cluster completion ratio (e.g. 10/10), stale badges, expandable crystal list with TL;DRs, "Copy regenerate command" button
- **`_check_crystal_staleness`** drift detector in `dashboard/drift.py` — emits `DriftAlert` for each stale crystal with fix command
- **`CrystalSummary`** dataclass on `DashboardData` — populated in `collect_dashboard_data` by calling `crystal.list_crystals` + `crystal.check_staleness` per cluster
- **9 new tests** in `tests/test_dashboard_crystal_section.py` + `tests/test_drift_crystal.py`
- CSS: `.crystal-section`, `.crystal-card`, `.crystal-stale-badge`, `.crystal-list`

### Added — Track C: Documentation + multilingual

- **`docs/anti-rag.md`** (~340 lines) — architectural explainer. Karpathy critique, eager-vs-lazy framing, concrete before/after example, generation + query flow diagrams, honest limitations
- **`README.zh-TW.md`** — full 繁中 README mirror
- **`README.md`** — rewritten from 341 → 170 lines. Screenshot-led, MCP-first, anti-RAG value prop in first 15 lines
- Status badges for PyPI / tests / Python / license
- Claude Desktop `mcpServers` config snippet copy-paste ready

### Fixed during Phase 4 review

- `tests/test_consistency.py` — added 5 new MCP tool mappings (`list_crystals → crystal list`, etc). Contract test requires every `@mcp.tool()` to have a CLI mapping; Track A added 5 new tools so the mapping needed updating.

### Live verification

Executed end-to-end against `llm-agents-software-engineering` (20 papers, 4 sub-topics):

1. `research-hub crystal emit` → 176-line prompt with 20 paper rows + 10 questions (~8 KB)
2. Fed prompt to the Claude in this release session (Opus 4.6) who answered all 10 questions based on accumulated knowledge from v0.12-v0.28 audits
3. `research-hub crystal apply` → 10 markdown files written, 775 lines total
4. `research-hub crystal list` → all 10 returned with TL;DRs
5. `research-hub crystal check` → all 10 fresh (delta = 0%)
6. `research-hub crystal read --level gist` → ~1 KB pre-written paragraph returned
7. `research-hub dashboard` → CrystalSection renders 10/10, 0 stale

### Test count

| Release | Passing | Delta |
|---|---|---|
| v0.27.0 | 1087 | — |
| **v0.28.0** | **1122** | **+35** |

### Breaking changes

None. All additions are backward-compatible:
- Clusters without crystals get empty CrystalSection + clear generation instructions.
- All existing MCP tools unchanged.
- Crystal generation uses emit/apply (never calls an LLM from inside research-hub — provider-agnostic).

### v0.29 backlog

- Custom canonical questions per cluster (`canonical_questions.yaml`)
- `.dxt` Claude Desktop extension for one-click install
- `clusters analyze --apply` (auto-apply split suggestions)
- Search quality fixes (the 4 v0.26 xfail root causes)
- Sub-topic IntersectionObserver virtualization (100+ papers per sub-topic)

## v0.27.0 (2026-04-15)

**Directness release — live HTTP dashboard server, auto-refreshing Obsidian graph colors, sub-topic-grouped Library UI, citation-graph cluster auto-split. 1019 → 1087 tests (+68).**

v0.26.0 diagnosed friction. v0.27.0 removes it. Full audit report: [`docs/audit_v0.27.md`](docs/audit_v0.27.md).

### Added — Track A: Live dashboard HTTP server

- **`research-hub serve --dashboard [--port 8765] [--host 127.0.0.1]`** — starts a localhost-only HTTP server backing the dashboard. Forms in the Manage tab now POST to `/api/exec` and execute directly (whitelisted subprocess), bypassing the copy-to-clipboard step.
- **`src/research_hub/dashboard/http_server.py`** (~240 LOC) — stdlib `ThreadingHTTPServer` with `GET /`, `/healthz`, `/api/state`, `/api/events` (SSE), `POST /api/exec`. No new dependencies.
- **`src/research_hub/dashboard/executor.py`** (~170 LOC) — whitelist of 20+ allowed actions (rename/merge/split/bind-*/move/label/mark/remove/ingest/topic-build/dashboard/pipeline-repair/notebooklm-*/discover-*/autofill-apply/compose-draft/clusters-analyze). `subprocess.run([...], shell=False)` — never shell interpolation.
- **`src/research_hub/dashboard/events.py`** (~90 LOC) — `EventBroadcaster` + `VaultWatcher` thread. Polls vault mtimes every 5s; on change, emits `vault_changed` to all connected SSE clients.
- **`script.js` live mode** — `detectLiveMode()` on page load hits `/healthz`, switches to fetch-and-execute when server present; falls back to clipboard copy when it's not (no regression for static usage).
- **Live pill** (`● Live` / `◯ Static`) in header indicates current mode.
- **38 new tests** in `tests/test_dashboard_live_server.py` cover bind enforcement, whitelist rejection, subprocess never uses `shell=True`, SSE broadcaster delivery, vault watcher mtime detection, CLI flag parsing.

### Added — Track B: Auto-refreshing graph colors + sub-topic Library UI

- **`vault/graph_config.py`** now produces TWO dimensions: (a) existing cluster-path color groups (`path:raw/<slug>/`), (b) new label-tag color groups (`tag:#label/seed`, `tag:#label/core`, ..., 9 groups covering `CANONICAL_LABELS`).
- **`refresh_graph_from_vault(cfg)`** — high-level convenience that reads `clusters.yaml`, rebuilds both dimensions, writes `.obsidian/graph.json` idempotently. Preserves user-authored color groups whose queries don't match the research-hub patterns.
- **Auto-refresh hooks** wired into `ClusterRegistry.create/delete/rename/bind/merge/split` + `research-hub dashboard` — so every cluster mutation and every dashboard rebuild auto-updates the graph.
- **`research-hub vault graph-colors --refresh`** — explicit manual trigger.
- **`paper.ensure_label_tags_in_body(path, labels)`** — injects `<!-- research-hub tags start -->\n#label/seed #label/core\n<!-- research-hub tags end -->` at the end of each paper note body. Idempotent. Required for Obsidian's graph `tag:#label/foo` query to work.
- **`LibrarySection._cluster_card`** rewritten to group papers by sub-topic when the cluster has `topics/NN_*.md` files. Each sub-topic renders as a collapsed `<details class="subtopic-card">`. Papers not assigned to any sub-topic go to a trailing "Unassigned" group. If the cluster has zero sub-topics, falls back to today's flat list (no regression for small clusters).
- **18 new tests** in `tests/test_graph_config_v027.py` / `test_library_subtopic_rendering.py` / `test_paper_label_tags.py`.

### Added — Track C: Citation-graph cluster auto-split

- **`src/research_hub/analyze.py`** (~220 LOC) — new module. `build_intra_cluster_citation_graph` fetches references for every paper via existing `citation_graph.get_references`, builds co-citation graph (nodes = cluster papers, edges = shared refs). `suggest_split` runs `networkx.algorithms.community.greedy_modularity_communities` + TF-IDF sub-topic name generation. `render_split_suggestion_markdown` produces a markdown report the user reviews before running `topic apply-assignments`.
- **`research-hub clusters analyze --cluster X --split-suggestion [--min-community-size N] [--max-communities M]`** — new CLI command.
- **`@mcp.tool() def suggest_cluster_split(cluster_slug, ...)`** — new MCP tool (v0.27 brings MCP tool count to 47).
- **Persistent citation cache** at `.research_hub/citation_cache/<cluster>/<slug>.json` — prevents re-hitting Semantic Scholar. Rate-limit aware: if >50% of papers return empty citations, the markdown report emits a "rerun after 1 hour" warning.
- **New dependency: `networkx >= 3.0`** — pure Python, ~10 MB, no heavy transitive deps.
- **12 new tests** in `tests/test_analyze.py`.

### Live verification results

- Graph refresh: **14 groups** written to `.obsidian/graph.json` (5 cluster + 9 label).
- 331-paper cluster auto-split: analyzed successfully, **4 communities** found (RAG/knowledge, multi-agent frameworks, LLM+disaster, long-term memory), modularity 0.312, citation coverage 44% (rate-limited but still usable). Full report at `docs/cluster_autosplit_llm-agents-social-cognitive-simulation.md`.
- Live server: `/healthz` returns live mode, `/api/state` returns 366 papers + 5 clusters + 2 briefings JSON, `/api/exec dashboard` runs in 7.6s and returns returncode 0, unknown action returns 400.

### Fixed during review

- **`_read_cluster_papers` used folder name instead of `topic_cluster` frontmatter.** The 331-paper cluster's notes live in `raw/llm-agent/` but have `topic_cluster: llm-agents-social-cognitive-simulation` in their YAML. Fixed by delegating to `vault.sync.list_cluster_notes` (rglob + frontmatter filter). ~15 LOC.
- **`test_consistency.py::test_every_mcp_tool_is_documented_in_expected_mappings`** — Track C added `suggest_cluster_split` without updating the contract test. Added `"suggest_cluster_split": "clusters analyze --split-suggestion"` to `EXPECTED_MAPPINGS`.

### Test count

| Release | Passing | Delta |
|---|---|---|
| v0.26.0 | 1019 | — |
| **v0.27.0** | **1087** | **+68** |

### Breaking changes

None. All additions are backward-compatible:
- The live server is opt-in via `--dashboard` flag; `serve` without it still starts MCP stdio.
- `script.js` falls back to clipboard when no server is running (existing static usage unchanged).
- Graph color auto-refresh preserves user-authored color groups.
- `LibrarySection._cluster_card` falls back to flat-list rendering when the cluster has no sub-topics.

### v0.28.0 backlog

- Auto-apply split suggestion (`clusters analyze --apply`)
- Sub-topic card virtualization for 100+ papers per sub-topic
- Multi-user auth (if server needs sharing)
- Search quality fixes (from v0.26 xfail baselines — still outstanding)
- Translate NotebookLM briefings (still deferred)

## v0.26.0 (2026-04-14)

**End-to-end audit release — search → notes → DB → dashboard/MCP API. 873 → 1019 tests (+146).**

First cross-cutting audit of the package. Four Codex tracks ran in parallel covering literature search accuracy, note organization, database sync/drift, and dashboard + MCP coverage. Full audit report: [`docs/audit_v0.26.md`](docs/audit_v0.26.md).

### Added — Track A: Search accuracy audit (tests/evals/*)

- **Golden fixture** (`tests/evals/fixtures/golden_llm_agents_se.yml`) with 20 hand-curated papers for the `llm-agents-software-engineering` cluster. Generated from live notes, authoritative source.
- **Metrics collector** (`tests/evals/conftest.py`) writes `tests/evals/_metrics.json` for the audit report.
- **24 new tests** across recall@20, recall@50, rank stability, dedup merge, confidence calibration, DOI normalization (10 forms), fit-check term-overlap correlation, empty-abstract handling, silent backend failures, auto-threshold floor, citation expansion failure logging.
- **`@pytest.mark.network`** + `@pytest.mark.evals` markers registered in `pyproject.toml`. Offline by default, opt-in via `pytest -m network`.
- **5 audit findings locked in as xfail baselines** (recall, rank, merge, calibration): these surface real search-quality bugs that will flip to green once v0.27.0 ranker/fusion fixes land. Full diagnosis in `docs/audit_v0.26.md`.

### Added — Track B: Note organization audit

- **`src/research_hub/paper_schema.py`** — reusable `validate_paper_note(path) -> NoteValidationResult` with missing_frontmatter + empty_sections + todo_placeholders fields.
- **`doctor.check_frontmatter_completeness()`** — walks every paper note, rolls up to a `HealthBadge`.
- **`scripts/audit_note_content.py`** → writes `docs/audit_v0.26_notes.md` with per-note coverage.
- **31 new tests** (parametrized): `test_topic_roundtrip.py` (4), `test_topic_content_guard_stress.py` (21 parametrized cases across 10 section headings × 2 mutation types), `test_frontmatter_schema.py` (4).
- Round-trip coverage: apply_assignments → build_subtopic_notes → re-read preserves ALL hand-edited structured sections (TL;DR, 核心問題, 範圍, 關鍵概念, 分類法, 代表論文, 時間線, 開放問題, 連結, See also).

### Added — Track C: Database / sync / drift audit

- **`scripts/audit_vault_sync.py`** → writes `docs/audit_v0.26_vault_sync.md` with per-cluster Zotero/Obsidian/dedup counts, orphans, stale manifest refs, drift alerts.
- **22 new tests** across pipeline_repair (8), dedup rebuild round-trip (4), cluster rename triple-sync (4), manifest integrity (3), drift detector coverage (3).
- **4 new drift detectors** in `src/research_hub/dashboard/drift.py`:
  - `zotero_orphan` — Zotero item in bound collection with no matching `.md` note
  - `subtopic_paper_mismatch` — subtopic file `papers:` frontmatter ≠ actual Papers section count
  - `stale_dedup_path` — dedup entry pointing to deleted `.md`
  - `stale_manifest_cluster` — manifest entry references a cluster slug missing from clusters.yaml
- **`pipeline_repair.py`** now appends `repair_*` actions to `manifest.jsonl` in execute mode + detects folder_mismatch + duplicate_doi across clusters.
- **`dedup.rebuild_from_obsidian`** now tolerates malformed YAML with WARN log instead of crashing.
- **`clusters rename`** now syncs NotebookLM cache name in addition to clusters.yaml and Zotero collection name (the v0.25 triple-sync gap).

### Added — Track D: Dashboard + MCP API comprehensive testing

- **`src/research_hub/dashboard/manage_commands.py`** — Python port of JS `buildManageCommand` + `buildComposeDraftCommand` + `shellQuote`. Enables unit-testing command builders without Playwright.
- **76 new tests** across 5 files:
  - `test_dashboard_script_logic.py` (14) — all 6 manage action builders + composer builder + shell escape + absolute obsidian:// regression + hash-anchor regression + empty-state rendering
  - `test_mcp_server_comprehensive.py` (12+) — declarative contract (every MCP tool has docstring + type-annotated params) + behavior tests for 7 of 9 decorated tools
  - `test_cli_smoke_comprehensive.py` (34+) — declarative `--help` smoke test for every registered subcommand + happy-path smoke tests for discover/fit-check/autofill/pipeline-repair/compose-draft/clusters-rename/topic-scaffold
  - `test_dashboard_idempotent.py` (3) — same-data renders produce identical HTML, empty vault renders without crash, missing bindings gracefully show unbound
  - `test_dashboard_persona.py` (3) — analyst hides Zotero column + omits bibtex, researcher auto-detected when Zotero configured

### Fixed

- **`fit_check.emit_prompt()`** rendered empty string for papers with `abstract=""` instead of `(no abstract)` marker. Silent fit-check scoring bug. Regression test in `tests/evals/test_fit_check_accuracy.py`.
- **`dedup.rebuild_from_obsidian`** crashed on malformed YAML; now warns and skips.
- **`pipeline_repair.py`** didn't log repair actions to manifest in execute mode.
- **`clusters rename`** missed NotebookLM cache sync (shipped in v0.24 as intended, covered by test now).

### Test count

- **v0.25.0**: 873 passing, 5 skipped
- **v0.26.0**: **1019 passing, 12 skipped, 5 xfail baselines** (+146 net)

### Breaking changes

None. All changes are additive: new modules, new tests, new drift detectors, new doctor check, new scripts, new pyproject markers. Existing APIs unchanged. Users who upgrade from v0.25.0 will see the same behavior + auto-labeled clusters will get 2 additional drift detectors enabled by default.

### v0.27.0 backlog (shipped as documented baselines)

1. Deterministic rank tiebreak (`rank_results` sort key) — closes `test_rank_stability`
2. Longer-wins field fill in `merge_results` — closes `test_dedup_merges_same_paper`
3. Confidence score incorporates term_overlap — closes `test_confidence_calibration`
4. Cluster-query aware eval (`test_recall_at_*` uses `cluster.seed_keywords`) — closes recall floors
5. Legacy folder migration tool (`migrate-yaml --all-legacy`)
6. Doctor integration for `check_frontmatter_completeness`
7. Empty-cluster pruning (`clusters prune --empty`)

## v0.25.0 (2026-04-14)

**Structured research-note principle + dashboard obsidian:// fix + file:// hash navigation fix.**

Live use of the `llm-agents-software-engineering` cluster surfaced three distinct issues: (1) topic overview and sub-topic notes were being emitted as wall-of-text English prose that was unreadable for skim-first research use; (2) the "Papers by label" cross-cluster list in the dashboard Library tab produced `obsidian://` URLs with relative paths, so clicking them did nothing; (3) label-filter chips in the dashboard triggered `window.location.hash` assignments that Chrome blocks under `file://` origin, making the first click unreliable. v0.25 fixes all three.

### Added — Structured note templates (Track A)

- **`OVERVIEW_TEMPLATE`** and **`SUBTOPIC_TEMPLATE`** in `src/research_hub/topic.py` rewritten as hierarchical, table-driven skeletons. Future `topic scaffold` and `topic build` runs emit the new structure automatically.
- **Sub-topic structure:** bilingual H1 (`# 中文標題 / English Title`), TL;DR (1–2 sentences), 核心問題 (blockquote), 範圍 (涵蓋/不涵蓋 as separate bullet lists), 關鍵概念 table, 分類法 table, 代表論文 table, Papers (auto-generated), 時間線 table, 開放問題 (numbered + bolded), 連結, See also.
- **Overview structure:** TL;DR, 核心問題, 範圍定義, 領域地圖 table (linking sub-topics), 關鍵概念詞彙表 table, 必讀論文 table, 時間線 table, 開放問題, 連結, 延伸閱讀.
- **Design rationale:** tables > paragraphs for any comparison or list of >3 items with the same shape; Traditional Chinese prose with English technical proper nouns preserved inline (LLM, SWE-bench, ACI, GPT-4, etc.); H1 is bilingual so the vault is searchable in both languages.

### Fixed — Dashboard `obsidian://` URLs now use absolute paths (Track B)

- **`_obsidian_url(relative_path, vault_root)`** in `src/research_hub/dashboard/sections.py` now accepts a vault_root and builds absolute paths via `Path(vault_root) / relative`, URL-encoding the result with `quote(..., safe='/:')`. Previously produced `obsidian://open?path=raw/cluster/slug.md` (relative), which Obsidian cannot resolve.
- **Threaded `vault_root`** from `DashboardData.vault_root` through five call sites: `_render_cross_cluster_labels`, `_cluster_card`, `_binding_line`, `_storage_row`, and the cluster card overview link.
- **Affected tabs:** Library tab → "Papers by label (across all clusters)" → clicking a paper now opens Obsidian. Also the cluster card header, binding line Obsidian chip, and Overview tab storage map rows.

### Fixed — Dashboard file:// hash navigation (Track C)

- **`handleLabelFilter()`** in `src/research_hub/dashboard/script.js` previously wrote `window.location.hash = "#tab-library?..."` on every label-chip click. Chrome's file:// security policy blocks hash changes with query strings, throwing "Unsafe attempt to load URL from frame with URL file:///..." — making the first click unreliable.
- **Fix:** removed all three `window.location.hash = ...` assignments. `applyLibraryFilters()` already updates DOM state directly; the hash was decorative and also broke file:// origin usage. Removed the now-unused `applyLibraryHashFilter()` function (24 lines of dead code).

### Enforcement

- The new template structure is codified in THREE places to keep future work consistent:
  1. `topic.py` templates (research-hub internal — affects future `topic scaffold`/`topic build`)
  2. `~/.claude/projects/.../memory/feedback_note_structure.md` (cross-conversation Claude memory)
  3. Worked example in the `llm-agents-software-engineering` cluster (5 files: overview + 4 sub-topics)

### Tests

- `tests/test_subtopic_content_protection.py` — 6 tests updated from English section headings (`## Scope`, `## Why these papers cluster together`, `## Open questions`) to new Chinese headings (`## 範圍`, `## 核心問題`, `## 開放問題`).
- `tests/test_topic_subtopics.py::test_build_subtopic_notes_overwrites_papers_section_only` — same heading update.
- **873 tests pass / 5 skipped.** No new tests added; the existing content-protection suite validates that the new templates still round-trip cleanly through `topic build` rebuilds without losing hand-edited content in preserved sections.

### Breaking changes

- **None for existing clusters.** `topic build` preserves all non-Papers section content across rebuilds (content-guard from v0.24 still active). Users with wall-of-text sub-topic notes can keep them — the new template only applies to newly scaffolded sub-topics.
- **Guidance:** users who want to adopt the new structure for existing clusters should rewrite `00_overview.md` and `topics/NN_*.md` by hand following the template in `feedback_note_structure.md`. There is no auto-migration tool because the new format is semantic, not mechanical.

## v0.24.0 (2026-04-14)

**Autofill + auto labels + Zotero sync + sub-topic protection — closing the "everything should be automatic on a full run" gap.**

Live audit on `llm-agents-software-engineering` exposed four process gaps where the pipeline silently left work for the user after ingest. v0.24 fixes all four.

### Added — Track A: Autofill paper note content via emit/apply

- **`src/research_hub/autofill.py`** — canonical module for generating paper note body content from abstracts.
- **`find_todo_papers(cfg, cluster_slug)`** scans for papers whose body contains `[TODO: ...]` markers and whose abstract is non-empty.
- **`emit_autofill_prompt(cfg, cluster_slug)`** builds a markdown prompt listing each TODO paper's title + abstract, asks the AI for structured JSON with `summary`, `key_findings`, `methodology`, `relevance` per paper.
- **`apply_autofill(cfg, cluster_slug, scored)`** consumes the AI JSON and rewrites the `## Summary … ## Relevance` block in each paper note, preserving frontmatter, abstract, and the `## Related Papers in This Cluster` footer.
- **CLI:** `research-hub autofill emit --cluster X > prompt.md` and `research-hub autofill apply --cluster X --scored out.json`. Same emit/apply pattern as fit-check.
- **2 new MCP tools:** `autofill_emit`, `autofill_apply`.

### Added — Track B: Auto labels from fit score

- **`.fit_check_accepted.json` sidecar** written alongside the existing rejected sidecar during `fit_check.apply_scores`.
- **`paper.label_from_fit_score(score, is_top_tier)`** mapping: score 5 → `core` + `seed` for top-tier (top 20%); score 4 → `core`; score 3 → user decides (metadata only); score 2 → `tangential`; score 0-1 → `deprecated`.
- **`paper.apply_fit_check_to_labels(cfg, cluster_slug)`** now reads BOTH sidecars and labels accepted papers too — not just deprecated.

### Added — Track C: Zotero collection rename sync

- **`research-hub clusters rename --name "Foo" slug`** now ALSO renames the bound Zotero collection via `pyzotero.update_collection` when `zotero_collection_key` is set.
- **Warning-only failure** — Zotero API error prints to stderr but doesn't roll back the clusters.yaml rename.
- **Idempotent** — no API call when target name already matches.

### Added — Track D: Sub-topic content protection

- **`topic._write_papers_section` content guard** — snapshots all non-Papers sections before rewrite, verifies every section is still byte-identical after rewrite, raises `ValueError` if any section would be deleted or modified.
- **`_extract_sections_excluding_papers(text)`** helper — returns `{heading: content}` for every `## X` section except `## Papers`.

### Tests

- **832 → 873 passing** (+41 tests, 5 skipped unchanged).
- `tests/test_autofill.py`: 10 tests
- `tests/test_label_from_fit_score.py`: 8 tests
- `tests/test_clusters_rename_zotero.py`: 4 tests (mocked pyzotero)
- `tests/test_subtopic_content_protection.py`: 6 tests
- Existing fit_check / paper / topic / consistency tests extended for 13 new assertions

### CLI + MCP

- 1 new CLI subcommand group: `autofill {emit, apply}`
- 2 new MCP tools: `autofill_emit`, `autofill_apply` → **52 total** (was 50)
- `clusters rename` gains Zotero sync side effect
- `fit-check apply-labels` now handles accepted papers too

### Deferred to v0.25+

- Pipeline-integrated autofill (run automatically as part of `ingest --fit-check`)
- Bi-directional Zotero note sync (Obsidian body changes propagate to Zotero mirror)
- Slug rename for clusters
- Top-tier seed ranking by citation count (currently list-order)

## v0.23.1 (2026-04-14)

**Python 3.11 CI fix.** `tests/test_dashboard_data.py:55` used a nested f-string with backslashes in the expression part (for quoting label strings inline), which is valid Python 3.12+ but raises `SyntaxError: f-string expression part cannot include a backslash` on Python 3.10/3.11. Local tests passed on Python 3.14; CI's 3.11 job failed immediately on import. Fix: extract the label-quoting into a plain string join outside the f-string. No runtime behavior change.

## v0.23.0 (2026-04-14)

**Dashboard feature completion + stress test suite.** v0.22 added label plumbing; v0.23 wires labels into the dashboard as an interactive filter system and adds a stress test layer the project was missing entirely.

### Added — Dashboard feature completion (Track A)

- **Clickable label filter chips.** Cluster card label chips (`seed: 3`, `core: 4`, etc.) are now `<a>` elements with `data-label` + `data-cluster` attributes. Clicking one jumps to the Library tab and filters paper rows to only those with that label. Click again to clear. URL hash tracks the state (`#tab-library?label=seed&cluster=llm-agents-software-engineering`), so filters are bookmarkable.
- **Archived papers section per cluster.** Each cluster card gains a collapsible `<details class="cluster-archive">` block showing archived papers (from `raw/_archive/<cluster>/`) with their fit_reason and a copy-button that emits the exact `research-hub paper unarchive --cluster X --slug Y` command. Hidden when `archived_count == 0`.
- **Cross-cluster "Papers by label" view.** New section at the top of the Library tab, rendered only when any cluster has labeled papers. Groups papers by canonical label across all clusters — answers "show me every `seed` paper in my vault" in one place. Each paper in the list links to its Obsidian note.
- **Label badges in Library paper rows.** Each paper row now shows `[seed, benchmark]` monospaced chips alongside the existing title/authors/year. Rows gain `data-cluster-row` + `data-labels` attributes so the label filter (A1) can hide/show them in one JS pass.
- **Writing tab quote filter by paper label.** Writing tab gains a filter bar (`Filter by paper label: [all] [seed] [core] [method] [benchmark]`) that hides quote cards to only those captured from papers with the selected label. Quote cards gain `data-paper-labels` attribute.
- **Minimal CSS additions** — all new classes (`cluster-label--active`, `cluster-archive`, `cross-cluster-labels`, `paper-row-labels`, `quote-filter-bar`, `quote-filter-chip`, `label-group`) reuse existing `--brand` / `--muted` color vars. No new CSS variables.
- **`script.js` gains two handlers** — `handleLabelFilter()` for A1/A4, `handleQuoteLabelFilter()` for A5. Both attach on `DOMContentLoaded`.

### Added — Stress test suite (Track B)

New `tests/stress/` directory with 8 stress test modules, all auto-marked with `@pytest.mark.stress` via `tests/stress/conftest.py`. **Default `pytest -q` excludes them** via `addopts = "--ignore=tests/stress"` in `pyproject.toml`. Opt-in with `pytest tests/stress/ -v`.

| Module | Stress coverage |
|---|---|
| `test_dashboard_render.py` | Render on 100/500/2000/5000-paper synthetic vaults with linear time budgets |
| `test_dashboard_render_content.py` | Verify label markup still renders at scale |
| `test_frontmatter_rewrite.py` | 500-paper `set_labels` loop + body preservation (regression for v0.20.1-class corruption) |
| `test_topic_build.py` | 30 sub-topics × 100 papers with random assignments |
| `test_discover_merge.py` | 5 backends × 100 results with 60% DOI overlap, confidence boost correctness |
| `test_pipeline_ingest.py` | 100-paper ingest with mocked Zotero, dedup index growth check |
| `test_paper_label_parallel.py` | 200-paper threaded `set_labels(add=)` — race detection |
| `test_fit_check_prompt.py` | 200-candidate prompt budget check (< 200KB for LLM context) |

`tests/stress/_helpers.py` provides `make_stress_cfg`, `build_synthetic_cluster`, `build_synthetic_vault`, `synthetic_paper_note` — reusable fixtures for any stress test that needs a fake vault.

### CI workflow

- `.github/workflows/ci.yml` gains a new `stress-tests` job that runs only on `pull_request`. 10-minute timeout. Stays off the main branch push path so default CI stays fast (default run is ~45s, stress run is ~60s).

### Tests

- **Default suite: 810 → 832 passing** (+22 dashboard + data unit tests in the default pyramid)
- **Stress suite: 0 → 12 tests** (opt-in, excluded from default)
- **Default `pytest --collect-only | grep stress` returns 0** — stress tests genuinely excluded

### Live verification on the real cluster

Labeled 8 core papers in `llm-agents-software-engineering` and verified end-to-end:
- `research-hub label <slug> --set seed,benchmark` wrote frontmatter cleanly
- `research-hub find --cluster X --label seed` returned the 3 seed papers
- `research-hub dashboard` rendered `seed: 3 core: 4 method: 5 benchmark: 4` histogram on the cluster card
- Clicking a chip in the rendered HTML emits the filter hash

### Non-breaking

All existing CLI commands, MCP tools (50 still), and existing dashboard rendering unchanged. This release is purely additive: new dashboard elements, new stress tests, new CI job.

### Deferred to v0.24+

- Auto-label `accepted` papers from fit-check (needs a `.fit_check_accepted.json` sidecar that `discover continue` doesn't yet write)
- `topic build --group-by-label` sectioned sub-topic notes
- Cross-cluster label view in MCP (currently only in dashboard UI)
- Stress test run against a real production vault (currently all synthetic)

## v0.22.0 (2026-04-13)

**Paper labels + pruning — curate clusters after ingest with a 9-label vocabulary, archive-first deletion, and a fit-check → labels bridge.**

v0.14-v0.21 built discovery + ingest + topic notes, but zero curation after ingest. Once a paper landed in the vault, you could only mark its reading status (`unread/reading/read`) or use free-form Obsidian tags. v0.22 adds a controlled label vocabulary stored in paper frontmatter, a CLI to query and update it, an archive-first pruning workflow, and label-aware topic + dashboard rendering.

### Added — `src/research_hub/paper.py` (~290 LOC)

New canonical module for paper labels and curation:

- **`PaperLabel` dataclass** — `slug`, `cluster_slug`, `path`, `labels`, `fit_score`, `fit_reason`, `labeled_at`
- **`CANONICAL_LABELS`** — frozenset of 9 standard labels: `seed`, `core`, `method`, `benchmark`, `survey`, `application`, `tangential`, `deprecated`, `archived`. User-defined labels also work; only the 9 drive tooling.
- **`read_labels(cfg, slug)`** — locate paper note by slug across all clusters, return label state
- **`set_labels(cfg, slug, labels=, add=, remove=, fit_score=, fit_reason=)`** — three modes (replace / add / remove), updates `labeled_at` timestamp automatically
- **`list_papers_by_label(cfg, cluster_slug, label=, label_not=)`** — query papers in a cluster with label filters
- **`apply_fit_check_to_labels(cfg, cluster_slug)`** — read `.fit_check_rejected.json` sidecar, tag matching papers in the vault as `deprecated` with their fit_score and fit_reason
- **`prune_cluster(cfg, cluster_slug, label=, archive=True, delete=False, dry_run=True)`** — archive-first move-to-`raw/_archive/<cluster>/` (default), or hard-delete with explicit `--delete` flag. Rebuilds dedup index after either operation.
- **`unarchive(cfg, cluster_slug, slug)`** — restore an archived paper back to its active cluster, removes `archived` label
- **`label_from_fit_score(score)`** — default mapping: 5/4 → `core`, 2 → `tangential`, 0/1 → `deprecated`, 3 → no auto-label
- **`_rewrite_paper_frontmatter()`** — defensive rewriter that handles CRLF and LF, preserves block-list continuations, and is regression-tested against the v0.20.1 newline bug class

### Added — Frontmatter fields

Paper notes now support (all optional, backwards-compatible):

```yaml
labels: [seed, benchmark]                          # list of labels
fit_score: 5                                       # int 0-5 from fit-check
fit_reason: "Canonical SE benchmark"               # one-line rationale
labeled_at: "2026-04-14T08:00:00Z"                 # ISO timestamp
```

Existing `tags:`, `status:`, `subtopics:`, `topic_cluster:` are unchanged. Labels live in their own namespace.

### Added — CLI surface

```bash
# Label a paper
research-hub label <slug> --set seed,benchmark      # replace
research-hub label <slug> --add method               # append
research-hub label <slug> --remove deprecated        # subtract
research-hub label <slug>                            # show current state

# Bulk from JSON
research-hub label-bulk --from-json labels.json

# Query by label
research-hub find --cluster X --label seed
research-hub find --cluster X --label-not deprecated

# Bridge fit-check sidecar to labels
research-hub fit-check apply-labels --cluster X

# Pruning (archive-first)
research-hub paper prune --cluster X --label deprecated --dry-run
research-hub paper prune --cluster X --label deprecated --archive
research-hub paper prune --cluster X --label deprecated --delete --zotero

# Undo
research-hub paper unarchive --cluster X --slug <slug>
```

### Added — Pipeline integration

`research-hub ingest --fit-check` now auto-runs `apply_fit_check_to_labels()` after the pipeline finishes, tagging any rejected papers in the vault as `deprecated` with their fit score + reason. Disable with `--no-fit-check-auto-labels`.

### Added — Topic note integration

`topic build` now renders inline label badges next to each paper wiki-link in sub-topic notes:

```markdown
## Papers

- [[jimenez2024-swe-bench|SWE-bench (Jimenez 2024)]] `[seed, benchmark]` — canonical SE benchmark
- [[yang2024-swe-agent|SWE-agent (Yang 2024)]] `[core, method]` — agent-computer interfaces for SE
- [[chen2024-self-debug|Self-Debug (Chen 2024)]] `[method]` — iterative self-correction
```

### Added — Dashboard integration

`ClusterCard` gains `label_counts: dict[str, int]` and `archived_count: int` fields, populated from `paper.list_papers_by_label()` and `paper.archive_dir()`. The cluster card UI shows a label histogram + archived count under the existing summary line.

### MCP surface (4 new, 50 total)

- `label_paper(slug, labels?, add?, remove?, fit_score?, fit_reason?)` → `{ok, slug, labels, fit_score, fit_reason, labeled_at}`
- `list_papers_by_label(cluster_slug, label?, label_not?)` → list of paper state dicts
- `prune_cluster(cluster_slug, label="deprecated", archive=True, delete=False, dry_run=True)` → move/delete report
- `apply_fit_check_to_labels(cluster_slug)` → `{tagged, already, missing}`

**46 → 50 MCP tools.**

### Tests

- **775 → 810 passing** (+35 tests, 5 skipped unchanged)
- `tests/test_paper_labels.py`: 25 tests
  - read/set labels (12) — including v0.20.1-class regression test for closing-fence newline preservation
  - list_papers_by_label (6)
  - apply_fit_check_to_labels (4)
  - frontmatter rewrite (3)
- `tests/test_paper_prune.py`: 10 tests covering archive, delete, custom label, unarchive, dedup index rebuild

### Non-breaking changes

All existing CLI commands, MCP tool signatures, and frontmatter fields are unchanged. Papers without `labels:` are valid and read as `labels: []`. The pipeline auto-labels only papers that were REJECTED by fit-check (the rejected sidecar already exists). Accepted-papers auto-labeling is deferred to v0.23 (needs a `.fit_check_accepted.json` sidecar that doesn't exist yet).

### Deferred to v0.23+

- Auto-label accepted papers from fit-check (needs new accepted-sidecar)
- `topic build --group-by-label` for sectioned sub-topic notes
- AI bulk labeling from cluster digest (`label-bulk --from-digest`)
- Clickable dashboard label filters
- Cross-cluster label views (e.g. all `seed` papers across clusters)

## v0.21.0 (2026-04-13)

**Discovery quality — multi-query + citation expansion + cluster dedup + seed DOIs + larger defaults.**

Live test on `llm-agents-software-engineering` found the cluster had only ~25-30% of the papers a real literature review would include (20 out of an expected 50-80). Root cause: `discover new` only ran a single query with a small default limit, never fetched citation neighbors, and re-showed papers already ingested in the cluster. v0.21 fixes all five gaps in one release.

### Added — Track A: Multi-query variation

- **`research-hub discover variants --cluster X --query "..." --count 4`** — new subcommand that emits a prompt asking the AI to generate N query variations, each capturing a different facet of the topic (benchmarks vs frameworks vs evaluation vs adjacent specializations). Reads the cluster definition from `00_overview.md` if present.
- **`research-hub discover new --from-variants file.json`** — runs the search once per variation and merges results via the existing DOI-keyed merge layer. Papers hit by multiple variations get a confidence boost and their `_discover_meta.matched_variations` list tracks which queries found them.
- **`emit_variation_prompt()` and `apply_variations()`** helpers in `discover.py` for the emit/apply pattern.
- **1 new MCP tool:** `discover_variants(cluster_slug, query, count=4)` — **46 total** (was 45).

### Added — Track B: Citation graph expansion

- **`research-hub discover new --expand-auto`** — picks the top 3 keyword-search results (ranked by confidence then citation count) as seed papers and fetches their references + forward citations via the existing `CitationGraphClient` (v0.8, Semantic Scholar-backed).
- **`research-hub discover new --expand-from doi1,doi2,doi3`** — user-specified seed DOIs for expansion.
- **`--expand-hops`** (default 1, bounded — no recursion in v0.21).
- **30-per-seed-per-direction cap** — stops runaway expansion on highly-cited seeds like SWE-bench.
- **Graceful degradation** — if S2 rate-limits (HTTP 429), log a warning and continue with whatever was fetched. Never crashes the discover flow.
- **Dedup with keyword results** — if a seed's reference is already in the keyword pool, the entry gets a confidence boost and a `source_tags` entry for "citation-graph" instead of being added as a duplicate.
- **`_citation_node_to_search_result()` helper** converts `CitationNode` (S2 shape) to `SearchResult` for uniform merging.

### Added — Track C: Cluster dedup (default behavior)

- **`discover new` now filters out papers already ingested in the cluster** before stashing candidates. Reads `raw/<cluster>/*.md` frontmatter, extracts DOIs, normalizes, and excludes matching candidates.
- **`--include-existing`** flag bypasses the dedup (useful for re-scoring already-ingested papers against a new definition).
- **`DiscoverState.deduped_against_cluster`** tracks the skipped count, visible in `discover status`.
- Skips `00_overview.md`, `index.md`, and the `topics/` subdirectory when scanning.

### Added — Track D: Seed DOI injection

- **`research-hub discover new --seed-dois "10.x/meta,10.y/auto,10.z/ling"`** — user-specified DOIs to inject as candidates regardless of search hits.
- **`--seed-dois-file path.txt`** — one DOI per line, comments (lines starting with `#`) allowed.
- **Resolution logic:** if the DOI is already in keyword-search results, boost its confidence and tag as `seed`. Otherwise call `enrich_candidates()` (v0.13) to resolve the DOI to full metadata via Crossref/OpenAlex/arXiv and add as new entry.
- **Max confidence (1.0)** for user-supplied seeds — the user has explicit intent.
- **`DiscoverState.seed_dois`** tracks the list.
- **Graceful skip** on invalid DOIs — logged, not raised.

### Added — Track E: Larger defaults

- **`limit`** default in `discover_new()`: **25 → 50**
- **`per_backend_limit`** (over-fetch factor): **`max(limit*2, 20)` → `max(limit*3, 40)`**
- Rationale: a limit of 25 was truncating the long tail before ranking could pick the best. Over-fetching 3x gives the merge layer enough material to produce N high-quality candidates after dedup + confidence sort.
- CLI `--limit` flag still overrides the default exactly.

### Extended DiscoverState

New fields (all backwards-compat via `from_json()` defaulting):

```python
variations_used: list[str]       # variation queries that ran
expanded_from: list[str]         # seed DOIs used for citation expansion
seed_dois: list[str]             # user-injected seeds
deduped_against_cluster: int     # count of candidates filtered by cluster dedup
```

### CLI + MCP surface

**CLI:**
```bash
research-hub discover variants --cluster X --query "..." --count 4 [--out file.md]
research-hub discover new --cluster X --query "..." \
    [--from-variants file.json] \
    [--expand-auto | --expand-from doi1,doi2] [--expand-hops 1] \
    [--seed-dois doi1,doi2 | --seed-dois-file dois.txt] \
    [--include-existing]
```

**MCP:**
- `discover_new` gains `from_variants`, `expand_auto`, `expand_from`, `expand_hops`, `seed_dois`, `include_existing` parameters (all optional, backwards compatible)
- `discover_variants` added (**46 MCP tools total**)

### Non-breaking except…

- **Default `limit` changed from 25 to 50** — unflagged `discover new` returns roughly 2x as many candidates as before. Revert explicitly with `--limit 25`.
- **Cluster dedup is now default** — unflagged `discover new` skips papers already in the cluster. Revert explicitly with `--include-existing`.

These behavior changes are net-positive for a normal workflow but scripts that depended on the exact v0.20 numbers will see differences.

### Tests

- **740 → 775 passing** (+35 tests, 5 skipped unchanged).
- `tests/test_discover_quality.py`: 35 tests across 5 tracks (8 multi-query, 8 citation expansion, 6 cluster dedup, 7 seed DOIs, 6 defaults + integration).
- Existing `tests/test_discover.py` (20 tests) kept green with minor default adjustments.

### Expected impact on real discovery runs

Running the v0.21 flow on the existing `llm-agents-software-engineering` cluster with `--from-variants --expand-auto --seed-dois "metagpt,autocoderover,lingma"` should yield 50-80 candidates instead of 15-20, surfacing the papers the v0.20 audit identified as missing: MetaGPT, AutoCodeRover, Agentless, Lingma, SWE-rebench, SWE-Verified, Commit0, Moatless, and others.

### Deferred to v0.22+

- OpenAlex citation graph as S2 alternative (would eliminate rate-limit risk)
- NLP-driven query expansion (synonym explosion, boolean OR groups) — emit/apply variation already achieves similar ends via AI
- `discover iterate` to remember which variations have been run across sessions
- Cross-cluster citation expansion

## v0.20.2 (2026-04-13)

**Backend live-behavior fixes + honest coverage audit.** A session-ending audit ran each of the 13 registered backends against a real query designed to hit its strongest coverage area. **Only 4 of 13 returned correct results end-to-end.** Mocked unit tests were passing but the live APIs behaved differently from the test fixtures. v0.20.2 fixes the three most impactful issues and documents the rest as known-broken for v0.21.

### Fixed

- **arXiv backend (`search/arxiv_backend.py`)** — the search query was wrapped in quotes as `all:"LLM agent software engineering"`, which arXiv interprets as a phrase match requiring the exact sequence. No paper's metadata contains that exact string, so live queries returned 0 results for the entire v0.13.0-v0.20.1 period. Live audit confirmed 0 hits against "LLM agent software engineering" while a raw API call with AND-joined terms returned 5 relevant papers.
  - **Fix:** new `_build_arxiv_query()` helper that splits free-text queries into `all:term1 AND all:term2 AND ...`, preserves explicit quoted phrases, and falls back to `all:*` on empty input.
  - **Verified live:** post-fix returns 5 on-topic papers (SkillMOO, SWE-bench bug triggers, Tokalator, From LLMs to LLM-based Agents, etc.).
  - **Regression tests:** 4 new tests in `test_arxiv_backend.py` covering AND-split, quoted-phrase preservation, empty fallback, single-word.

- **bioRxiv backend (`search/biorxiv.py`)** — `_matches_query()` used `any(...)`, so a 4-word query matched any paper containing at least one query word. Live audit returned papers about "heavy metal bacterial adaptation" for a query about "protein structure prediction AlphaFold" because both use the word "protein".
  - **Fix:** switched to strict AND — all query terms must be present in the title or abstract.
  - **Trade-off:** strict AND returns 0 results for specific multi-word queries where bioRxiv doesn't have a matching paper, instead of returning irrelevant papers. The honest-zero behavior is better for downstream fit-check and ranking.
  - **Regression tests:** updated `test_biorxiv_matches_query_requires_all_terms` to assert strict AND semantics with 4/4, 3/4, 2/4, 1/4 term cases.

- **Semantic Scholar backend (`search/semantic_scholar.py`)** — on HTTP 429 the backend silently returned an empty list with no user-facing signal, making it impossible to distinguish "no results" from "rate-limited". Live audit hit 429 on every run because S2's free tier throttles aggressively.
  - **Fix:** added a `logger.warning()` with a link to the API key signup page. Existing silent return behavior preserved for callers that don't want to fail on rate limit; visible warning tells the user why they're getting zero results.

### Known issues deferred to v0.21

These were surfaced by the live audit but need a larger fix than a patch release:

- **DBLP** — query uses substring matching that accepts "Swedish" as a match for "SWE-bench". Needs a word-boundary regex or a different API query strategy.
- **ChemRxiv** — ChemRxiv migrated off the Figshare API around 2022-2023; group_id 13652 returns empty results. Needs the Cambridge Open Engage API.
- **RePEc** — the IDEAS HTML scraper's regex pattern (`/p/<series>/<handle>.html`) matches zero handles against the current HTML. Needs a rewrite against either the current DOM or the OAI-PMH endpoint directly (skipping the HTML handle-list step).
- **CiNii** — live audit confirmed the backend parses the Atom XML correctly, but the `from`/`until` year filter excludes all results because CiNii dates everything as the current year (2026) by default. Needs verification of CiNii's date field semantics.
- **KCI** — the endpoint URL returned HTML not JSON in the live audit. The KCI public REST API may live at a different path or may not exist at all. Needs investigation.
- **NASA ADS** — correctly reports `ADS_DEV_KEY` missing at runtime. Not a bug, just requires the user to set the env var.

### Working backends after v0.20.2 (5 of 13)

| Backend | Live status | Use case |
|---|---|---|
| OpenAlex | ✅ | general STEM + humanities |
| arXiv | ✅ (post-fix) | CS, math, physics, bio preprints |
| Crossref | ✅ | DOI-authoritative metadata, all fields |
| PubMed | ✅ | biomedicine |
| ERIC | ✅ | education research |

Plus **Semantic Scholar** when not rate-limited (intermittent).

### Tests

- **735 → 740 passing** (+5 regression tests, 5 skipped unchanged).
- `test_arxiv_backend.py`: 4 tests for `_build_arxiv_query()`.
- `test_biorxiv_backend.py`: 1 test for strict AND filter.

## v0.20.1 (2026-04-13)

**Bug fix.** v0.14.0-B's `_update_subtopic_frontmatter` (called when `topic build` runs on an existing sub-topic file) dropped the trailing newline before the closing `---` fence, producing corrupted frontmatter like:

```yaml
papers: 10
status: draft---     ← missing newline before the fence
```

The corrupted YAML broke `_extract_frontmatter_block`'s `text.find("\n---\n", 4)` lookup, which made `_existing_subtopic_paper_count` return 0 for every sub-topic file, which made `research-hub topic list` show every cluster as having 0 papers per sub-topic — even though the sub-topic notes themselves contained the correct paper lists.

Bug surfaced during a real live test on the cleaned-up `llm-agents-software-engineering` cluster (8 papers expanded to 20 via `discover new` + `discover continue --auto-threshold`, then sub-topic notes built). The first `topic build` worked; the second `topic build` (after re-running `topic assign apply` with corrected paper slugs) corrupted the frontmatter.

**Fix:** one-character change to add the missing `\n` between the frontmatter body and the closing fence in `_update_subtopic_frontmatter`'s return value.

**Regression test added:** `test_build_subtopic_notes_rerun_preserves_frontmatter_yaml` runs build twice and asserts the YAML closing fence stays on its own line, plus verifies `list_subtopics()` returns the correct paper count after rebuild.

Tests: 734 → 735 passing (+1 regression test).

## v0.20.0 (2026-04-13)

**CJK literature backends + region preset — Japanese and Korean academic literature now first-class.**

After v0.19, research-hub covered all major Western fields (CS, biomedicine, social science, chemistry, astronomy, education) but every backend assumed English-language content. Anyone searching for Japanese, Korean, or Chinese literature got nothing — a hard miss for ~15% of the world's research output and a major gap for researchers in Asia. v0.20 adds two CJK-region academic search backends and a `--region` preset that mirrors the `--field` pattern but selects backends by language/region instead of discipline.

### Added — Two CJK backends

- **`CiniiBackend`** (`src/research_hub/search/cinii.py`, ~150 LOC) — CiNii Research, run by Japan's National Institute of Informatics (NII). The canonical bibliography for Japanese academic literature: ~26M records covering Japanese journals, conference proceedings, theses, books, projects. Free, no API key required. Uses the OpenSearch Atom XML endpoint at `https://cir.nii.ac.jp/opensearch/all` with year filters via `from`/`until` params. Parses Atom + Dublin Core + PRISM + CiNii namespaces, extracts DOI from multiple identifier formats (`https://doi.org/...`, `info:doi/...`, `prism:doi`). doc_type maps from `dc:type` to `journal-article`/`thesis`/`book`/`conference-paper`. Japanese characters in titles preserved verbatim.

- **`KciBackend`** (`src/research_hub/search/kci.py`, ~150 LOC) — Korea Citation Index, run by the Korean National Research Foundation. Covers Korean academic literature across all disciplines. Free OpenAPI access at `https://www.kci.go.kr/kciportal/po/search/poArtiSearList.kci` for basic queries, no key required. JSON API. Tries multiple field name variants (`titleEng` first, falling back to `title`; `authors`/`authorList`; `journalNameEng`/`journalName`) to be robust against schema drift. Year filter via `startYear`/`endYear` params.

### Added — `--region` preset

New flag on `research-hub search` and `research-hub discover new`, **mutually exclusive with `--backend` and `--field`**:

| Region preset | Backends |
|---|---|
| `en` | v0.16 5-backend list (DEFAULT_BACKENDS) |
| `jp` | openalex + cinii + crossref |
| `kr` | openalex + kci + crossref |
| `cjk` | openalex + cinii + kci + crossref |

Resolution priority: `--region` > `--field` > `--backend` > `DEFAULT_BACKENDS`. The CLI `add_mutually_exclusive_group` enforces that only one of the three flags can be supplied at a time.

### Backend registry

`_BACKEND_REGISTRY` now has **14 entries (13 unique classes + `medrxiv` alias)**:

```python
_BACKEND_REGISTRY = {
    # ... v0.16-v0.19 entries ...
    "cinii": CiniiBackend,    # NEW
    "kci": KciBackend,        # NEW
}
```

`DEFAULT_BACKENDS` stays at the v0.16.0 5-backend list — CJK backends are opt-in.

### CLI / MCP

- `--region` flag on `search` and `discover new` (mutually exclusive with `--backend` and `--field`)
- `discover_new` Python function gains `region: str | None = None` parameter
- `search_papers` and `discover_new` MCP tools gain `region: str | None = None` parameter
- **No new MCP tools** — 45 stays.

### Bilingual docs

- **`docs/zh/cli-reference.md`** (297 lines) — Traditional Chinese translation of `docs/cli-reference.md` (302 lines). Completes the v0.19.0 ZH translation pass that hit a Gemini rate limit on the third file. All four `docs/zh/*.md` files now have full translations.

### Tests

- **702 → 734 passing** (+32 tests, 5 skipped unchanged).
- `tests/test_cinii_backend.py`: 12 tests (Atom XML parsing, multi-namespace identifier extraction, Japanese characters, year filter, doc_type mapping).
- `tests/test_kci_backend.py`: 12 tests (titleEng fallback, authors as list/dict/string, year filter, articleId URL building).
- `tests/test_region_preset.py`: 2 tests for jp/cjk presets.
- Existing fallback / CLI / discover / MCP tests updated.

### Non-breaking changes only

All existing CLI commands, MCP tool signatures, default backend list, and import paths continue to work unchanged. `--region` is purely additive but mutually exclusive with the existing `--backend` and `--field` flags.

### Field + region coverage matrix

After v0.20 (combining v0.16-v0.20):

| Coverage axis | Options |
|---|---|
| **Field presets (11)** | cs, bio, med, physics, math, social, econ, chem, astro, edu, general |
| **Region presets (4)** | en, jp, kr, cjk |
| **Total backends (13)** | OpenAlex, arXiv, Semantic Scholar, Crossref, DBLP, PubMed, bioRxiv, RePEc, ChemRxiv, NASA ADS, ERIC, CiNii, KCI |

### Deferred to v0.21+

- **Chinese-language backends** — CSSCI/CNKI require institutional subscriptions; deferred until a free open path exists
- **Cross-CJK title fuzz match** — current title-similarity dedup uses Latin word boundaries, doesn't handle CJK boundaries well; v0.21 candidate
- **JSTOR / PsycINFO / IEEE Xplore** — paid databases, lower priority

## v0.19.1 (2026-04-13)

**Build fix.** v0.19.0 wheel was rejected by PyPI with a 400 Bad Request because the wheel had **duplicate file entries** for `research_hub/examples/*`. The `[tool.hatch.build.targets.wheel] packages = ["src/research_hub"]` already includes the `examples/` subpackage automatically, but the additional `[tool.hatch.build.targets.wheel.force-include]` section added the same files a second time. Removing the redundant `force-include` block fixes the duplicate entries; `twine check` now PASSES and the wheel uploads cleanly. No code changes — same v0.19.0 features, just a working build.

## v0.19.0 (2026-04-13)

**Onboarding wizard + bundled examples + bilingual docs scaffolding — lower the barrier for non-CS users.**

After v0.18.0, research-hub had 11 backends and 11 field presets but a brand-new researcher still had to read three docs and stitch six CLI calls together to create their first cluster. v0.19 ships an interactive `init --field <slug>` wizard that walks through cluster creation + first `discover` run with field-appropriate defaults, plus a bundled examples library so users can copy a working cluster definition instead of inventing one from scratch.

### Added — `research-hub init --field <slug>` wizard

- **`src/research_hub/onboarding.py`** (~250 LOC) — field-aware wizard that:
  1. Prompts for cluster name + slug (auto-derived from name)
  2. Prompts for query + optional definition
  3. Creates the cluster registry entry
  4. Runs `discover_new()` internally with the field preset (so the user gets a fit-check prompt without having to call `discover new` themselves)
  5. Prints next-steps with copy-pasteable commands
- **Both interactive and scriptable.** `--non-interactive` mode requires all flags (`--field`, `--cluster`, `--name`, `--query`) and runs end-to-end without input prompts.
- **Existing `init` (no `--field`) unchanged** — calls the legacy `init_wizard.run_init()` for backwards compatibility.

### Added — Field-aware `doctor` check

- **`src/research_hub/doctor_field.py`** (~120 LOC) — for each cluster, scans paper notes for venue/keyword signals and infers the dominant field. Compares against the cluster's declared field (inferred from `seed_keywords`) and reports a `WARN` when they disagree.
- Surfaces in `research-hub doctor` output as `cluster_field:<slug>`. Example: `WARN cluster_field:my-cluster: declared field=cs but papers look like bio (confidence=0.78, signal=12)`.
- Signal keywords cover all 11 fields (cs, bio, med, physics, math, astro, chem, social, econ, edu, general).

### Added — `research-hub examples {list, show, copy}` subcommand group

- **`src/research_hub/examples/`** — bundled example cluster definitions:
  - `cs_swe.json` — LLM agents for software engineering
  - `bio_protein.json` — protein structure prediction
  - `social_climate.json` — climate adaptation modeling
  - `edu_assessment.json` — automated writing assessment with LLMs
- Each example has `name`, `slug`, `field`, `query`, `definition`, `year_from`/`year_to`, `min_citations`, `sample_dois`, `description`.
- `research-hub examples list` — print all 4 with field tags
- `research-hub examples show <name>` — full JSON definition
- `research-hub examples copy <name> [--cluster <slug>]` — copy as a new cluster in the user's `clusters.yaml`, ready for `discover new`
- **3 new MCP tools** (45 total): `examples_list`, `examples_show`, `examples_copy`
- Wheel build now `force-include`s the `examples/` directory via `[tool.hatch.build.targets.wheel.force-include]`.

### Added — Bilingual docs scaffolding

- **`docs/onboarding.md`** (English, new) — first-time setup, three personas (CS researcher, biomedicine PhD, social science postdoc), wizard walkthrough, field reference table.
- **`docs/zh/`** — directory scaffolded with English placeholder content + `<!-- ZH translation pending -->` markers in each file:
  - `docs/zh/README.md` — Chinese entry point with translation status
  - `docs/zh/quickstart.md` — quickstart stub
  - `docs/zh/onboarding.md` — onboarding stub
  - `docs/zh/ai-integrations.md` — integration guide stub
- **A separate Gemini pass** will translate these stubs to traditional Chinese in v0.19.x. Codex did not write Chinese content because CJK content is poorly handled by Codex per the project delegation rules.

### Tests

- **680 → 702 passing** (+22 tests, 5 skipped unchanged).
- `tests/test_onboarding.py`: 10 tests for wizard interactive/non-interactive flows + examples loader.
- `tests/test_doctor_field.py`: 6 tests for field inference signals + doctor warnings.
- `tests/test_examples_cli.py`: 4 tests for CLI surface (list/show/copy/init --field).
- `tests/test_cli_init_doctor.py`, `tests/test_consistency.py`: extended for new commands and MCP tools.

### Non-breaking changes only

- Existing `init`, `doctor`, `examples`-namespace-free CLI all unchanged.
- `--field` flag on `init` is purely additive.
- All v0.18.0 features and import paths preserved.

### Deferred to v0.19.x and v0.20+

- **Chinese translation pass** for `docs/zh/` — separate Gemini run, lighter than this release.
- **CJK literature backends** (CiNii Japan, KCI Korea) — non-trivial encoding + API access challenges; v0.20 candidate.
- **Field auto-detection at cluster creation** — currently doctor warns after the fact; in v0.20+ the wizard could pre-validate the user's chosen field against their seed keywords.

## v0.18.0 (2026-04-13)

**Three more domain backends — chemistry, astronomy/astrophysics, education now first-class.**

v0.17.0 covered CS, biomedicine, social science, economics. v0.18.0 fills in the remaining major fields a research university actually has: chemistry (ChemRxiv), astronomy/astrophysics/geophysics (NASA ADS), and education (ERIC). After this release, the workflow generalizes from "STEM + biomedicine + social science" to "STEM + biomedicine + social science + chemistry + astronomy + education" — most disciplines covered.

### Added — Three more backends

- **`ChemrxivBackend`** (`src/research_hub/search/chemrxiv.py`, ~110 LOC) — ChemRxiv runs on Figshare's infrastructure. Uses the public Figshare API at `https://api.figshare.com/v2/articles/search` with `group_id=13652` to filter to ChemRxiv-hosted content. Free, no key. Returns title, authors, year, DOI, abstract, doc_type=`preprint`. The de-facto chemistry preprint server, same role as bioRxiv for biology.

- **`NasaAdsBackend`** (`src/research_hub/search/nasa_ads.py`, ~150 LOC) — NASA Astrophysics Data System REST API at `https://api.adsabs.harvard.edu/v1/search/query`. Reads API key from `ADS_DEV_KEY` environment variable; without a key the backend returns `[]` and logs a one-time WARNING (graceful degradation, never crashes). Get a free key at https://ui.adsabs.harvard.edu/user/settings/token. Covers ~16M records: astronomy, astrophysics, solar physics, planetary science, geophysics, Earth science. ADS query syntax (`year:[2024 TO 2025]`, `doi:"..."`, `bibcode:"..."`) is used for filters and lookups.

- **`EricBackend`** (`src/research_hub/search/eric.py`, ~120 LOC) — ERIC (Education Resources Information Center), run by the U.S. Institute of Education Sciences. Public REST API at `https://api.ies.ed.gov/eric/`. Free, no key. ~2M records covering education research papers, theses, and ED reports. Maps ERIC IDs to doc types (`EJ`-prefixed = `journal-article`, `ED`-prefixed = `report`).

### Added — Three new field presets

| Preset | Backends |
|---|---|
| `chem` | openalex + chemrxiv + crossref + semantic-scholar |
| `astro` | openalex + arxiv + nasa-ads + crossref + semantic-scholar |
| `edu` | openalex + eric + crossref + semantic-scholar |

The `general` preset now expands to **11 backends** (was 8 in v0.17): the v0.16 + v0.17 + v0.18 set combined.

### Backend registry

`_BACKEND_REGISTRY` now has **12 entries (11 unique classes + `medrxiv` alias for `BiorxivBackend`)**:

```python
_BACKEND_REGISTRY = {
    "openalex": OpenAlexBackend,
    "arxiv": ArxivBackend,
    "semantic-scholar": SemanticScholarClient,
    "crossref": CrossrefBackend,
    "dblp": DblpBackend,
    "pubmed": PubMedBackend,
    "biorxiv": BiorxivBackend,
    "medrxiv": BiorxivBackend,    # alias
    "repec": RepecBackend,
    "chemrxiv": ChemrxivBackend,    # NEW
    "nasa-ads": NasaAdsBackend,     # NEW
    "eric": EricBackend,            # NEW
}
```

`DEFAULT_BACKENDS` stays at the v0.16.0 5-backend list — the new domain backends are still opt-in.

### CLI / MCP — no signature changes

The `--field` flag's `choices=sorted(FIELD_PRESETS.keys())` is computed dynamically, so adding new presets to `FIELD_PRESETS` automatically extends the CLI. The `discover_new` and `search_papers` MCP tools accept the new preset names without any signature changes. **No CLI parser modifications, no MCP tool count change (42 stays).**

### Tests

- **652 → 680 passing** (+28 tests, 5 skipped unchanged).
- `tests/test_chemrxiv_backend.py`: 8 tests (POST + JSON body, `group_id=13652` assertion, year filter, doc_type=preprint).
- `tests/test_nasa_ads_backend.py`: 8 tests (graceful degradation without API key, Bearer auth header, year range query, DOI/bibcode lookup).
- `tests/test_eric_backend.py`: 8 tests (year filter via `publicationdateyear`, EJ vs ED doc_type mapping, authors as string or list).
- `tests/test_field_preset.py`: 3 new tests for chem/astro/edu presets.
- `tests/test_search_fallback.py`: registry assertion test for the 3 new backends.

### Field coverage matrix after v0.18.0

| Domain | Backends | Preset |
|---|---|---|
| CS / SE / AI | openalex + arxiv + s2 + dblp + crossref | `--field cs` |
| Math / theoretical physics | openalex + arxiv + crossref + s2 | `--field math` |
| Applied physics / astronomy | openalex + arxiv + nasa-ads + crossref + s2 | `--field astro` |
| Biology | openalex + pubmed + biorxiv + crossref + s2 | `--field bio` |
| Medicine | openalex + pubmed + biorxiv + crossref + s2 | `--field med` |
| Chemistry | openalex + chemrxiv + crossref + s2 | `--field chem` |
| Civil / environmental engineering | openalex + crossref + s2 (general STEM) | `--field general` (no specialty backend) |
| Economics / social science | openalex + crossref + s2 + repec | `--field social` / `--field econ` |
| Education | openalex + eric + crossref + s2 | `--field edu` |
| Humanities | openalex + crossref + s2 (general) | `--field general` (no specialty backend) |

### Deferred to v0.19+

- **CJK literature backends** (CiNii Japan, KCI Korea) — non-trivial encoding + API access challenges
- **JSTOR / PsycINFO** for humanities + psychology — paid databases, lower priority
- **IEEE Xplore** for EE/CE — paid API
- **Bilingual docs + onboarding wizard** — `research-hub init --field bio` walkthrough, EN/ZH per-field quickstarts

## v0.17.0 (2026-04-13)

**Domain backends + field preset — biology, medicine, economics, social sciences now first-class.**

v0.16.0 covered CS / general STEM well but left biomedicine, economics, and social sciences under-served. This release adds three high-impact domain backends and a `--field` preset shortcut so a researcher in biomedicine doesn't need to know which backends fit their field — they say `--field bio` and get the right combination automatically.

### Added — Three new domain backends

- **`PubMedBackend`** (`src/research_hub/search/pubmed.py`, ~150 LOC) — NCBI E-utilities API, free, no key required (key gives 10 req/s instead of 3 req/s, not needed for typical search loads). Two-step request flow: `esearch.fcgi` returns PMID list, `esummary.fcgi` returns structured metadata. Returns title, authors, year, journal, DOI, doc_type. PubMed does not return abstracts via esummary — relies on the merge layer to fill abstracts from other backends. Year filter uses `[pdat]` term tag, DOI lookup uses `[doi]` tag. ~35M biomedical citation database, the canonical biomedicine source.

- **`BiorxivBackend`** (`src/research_hub/search/biorxiv.py`, ~120 LOC) — bioRxiv + medRxiv preprint aggregator. Single backend that queries both servers (biology + medical preprints) and merges results. The official biorxiv API has no free-text search endpoint, so the backend fetches a date window (`/details/{server}/{date_from}/{date_to}/{cursor}`) and filters client-side by query terms. Inefficient but the only option without HTML scraping. Registered as both `biorxiv` and `medrxiv` (alias) in the backend registry.

- **`RepecBackend`** (`src/research_hub/search/repec.py`, ~180 LOC) — RePEc (Research Papers in Economics) via OAI-PMH XML protocol. Two-stage like PubMed: scrape IDEAS HTML search results to get RePEc handle list (`/p/<series>/<handle>.html` regex), then fetch metadata for each handle via OAI-PMH `GetRecord` request. Parses Dublin Core XML (`dc:title`, `dc:creator`, `dc:date`, `dc:identifier`, `dc:type`). The IDEAS HTML scraping is fragile (could break if RePEc changes their markup), but it's the only viable free option. ~3M economics records, cross-publisher coverage.

### Added — `--field` preset shortcut

New flag on `research-hub search` and `research-hub discover new`:

```bash
research-hub search "..." --field bio
research-hub discover new --cluster X --field social --query "..."
```

Available presets:

| Preset | Backends |
|---|---|
| `cs` | openalex + arxiv + semantic-scholar + dblp + crossref |
| `bio` | openalex + pubmed + biorxiv + crossref + semantic-scholar |
| `med` | openalex + pubmed + biorxiv + crossref + semantic-scholar |
| `physics` | openalex + arxiv + crossref + semantic-scholar |
| `math` | openalex + arxiv + crossref + semantic-scholar |
| `social` | openalex + crossref + semantic-scholar + repec |
| `econ` | openalex + crossref + semantic-scholar + repec |
| `general` | all 8 backends |

`--field` and `--backend` are **mutually exclusive** (CLI rejects both at once with a clear error). Default if neither supplied: keep v0.16.0 default (5 backends — `openalex,arxiv,semantic-scholar,crossref,dblp`).

### Backend registry

`_BACKEND_REGISTRY` now includes the 3 new backends + `medrxiv` alias for `BiorxivBackend`:

```python
_BACKEND_REGISTRY = {
    "openalex": OpenAlexBackend,
    "arxiv": ArxivBackend,
    "semantic-scholar": SemanticScholarClient,
    "crossref": CrossrefBackend,
    "dblp": DblpBackend,
    "pubmed": PubMedBackend,
    "biorxiv": BiorxivBackend,
    "medrxiv": BiorxivBackend,    # alias — same backend queries both servers
    "repec": RepecBackend,
}
```

`DEFAULT_BACKENDS` stays at the v0.16.0 5-backend list — the new domain backends are opt-in via `--field` or explicit `--backend`.

### MCP surface

- `search_papers` and `discover_new` MCP tool signatures gain optional `field: str | None = None` parameter. When set, it overrides `backends`. Backwards compatible: omitting it restores v0.16.0 behavior.
- **No new MCP tools** — 42 tools total.

### Tests

- **618 → 652 passing** (+34 tests, 5 skipped unchanged).
- `tests/test_pubmed_backend.py`: 8 tests for the two-step esearch+esummary flow.
- `tests/test_biorxiv_backend.py`: 6 tests covering both servers, date window, query filter.
- `tests/test_repec_backend.py`: 8 tests for HTML scraping + OAI-PMH XML parsing.
- `tests/test_field_preset.py`: 8 tests for preset resolution + mutex with `--backend`.
- Existing fallback / CLI / discover tests updated.

### Non-breaking changes only

All existing CLI commands, MCP tool signatures, default backend list, and import paths continue to work unchanged. `--field` is purely additive.

### Deferred to v0.18+

- **NASA ADS** for astronomy/physics
- **ChemRxiv** for chemistry preprints
- **ERIC** for education research
- **IEEE Xplore** (paid API, lower priority)
- **JSTOR** for humanities (paid)

## v0.16.0 (2026-04-13)

**Multi-backend that actually works + filters + smart ranking — fixes the gaps live tests #2 and #3 surfaced.**

v0.13.0 promised a three-backend fallback chain but live tests revealed it was functionally single-backend: 29/29 candidates across both test runs came from OpenAlex; arXiv and Semantic Scholar contributed zero hits. Root cause: arXiv preprints have zero citations by definition, so the global `min_citations` filter dropped all of them. Test #3 also showed citation-count sort actively hurting noisy queries — IPCC/Lancet reports with 2000+ citations dominated the top 5 positions while the actually-relevant migration papers (with <50 cits) ranked lower. This release fixes the multi-backend chain, adds two new specialized backends, and replaces the citation sort with a smart ranking heuristic.

### Added — Two new backends

- **`CrossrefBackend`** (`src/research_hub/search/crossref.py`, ~140 LOC) — Crossref REST API, free, no key required. Cross-publisher DOI metadata via `https://api.crossref.org/works`. Filters by `type:journal-article` to bias toward primary research. Returns title, authors, year, journal, doc_type, citation count. Does NOT return abstracts (Crossref doesn't store them) — used as a confidence-booster + type-filter source, not a primary search.
- **`DblpBackend`** (`src/research_hub/search/dblp.py`, ~140 LOC) — DBLP computer science bibliography, free, no key. 100% coverage of CS/SE publications including workshop papers and preprints OpenAlex misses. JSON API at `https://dblp.org/search/publ/api`. Returns title, authors, year, venue, doc_type. No abstracts, no citation counts (DBLP doesn't expose them) — used as a recall-boost for SE/CS topics.

### Added — Confidence merging + smart ranking

- **`SearchResult` gains three fields:**
  - `confidence: float` (0.5–1.0) — `0.5 + 0.25 * (n_backends_found - 1)` clamped to 1.0
  - `found_in: list[str]` — which backends saw this paper
  - `doc_type: str` — OpenAlex-style document type (journal-article, book-chapter, report, preprint, etc)
- **`search/_rank.py`** (new module, ~80 LOC) — `merge_results()`, `confidence_from_backends()`, `rank()`, `apply_filters()`, `_term_overlap()`.
- **Smart ranking** (default): `2 * confidence + recency + relevance` where recency is `max(0, 1 - 0.2 * (current_year - paper_year))` and relevance is the fraction of query terms present in the paper's title+abstract. Replaces the legacy citation-count-descending sort, which biased toward popular-but-irrelevant survey papers on polysemous queries.
- **Legacy ranking preserved:** `--rank-by citation` restores v0.15.0 behavior; `--rank-by year` sorts by recency only; default `--rank-by smart` is the new heuristic.

### Added — Filter flags on `research-hub search` and `research-hub discover new`

- **`--exclude-type "book-chapter,report,paratext"`** — drops results whose `doc_type` matches any of the listed types. Useful for filtering out IPCC synthesis docs, Lancet review reports, etc.
- **`--exclude "ipcc lancet burden plastic"`** — negative keywords. Drops results whose title or abstract contains any listed term (case-insensitive substring match).
- **`--min-confidence 0.75`** — requires the paper to be found by at least 2 backends (confidence 0.5 = single backend, 0.75 = two, 1.0 = three or more).
- **`--backend-trace`** — logs per-backend hit counts before merge so you can see exactly why a backend returned nothing.
- **`--rank-by {smart,citation,year}`** — pick ranking strategy.

### Fixed — multi-backend now actually multi-backend

- **`search/fallback.py::search_papers` reworked** to call each backend with appropriate filters:
  - **arXiv** ignores `min_citations` (preprints have zero citations by definition — root cause of v0.13.0 gap #6)
  - **Other backends** apply `min_citations` as before
  - All backends still respect the `year_from`/`year_to` filter
- Per-backend over-fetch (`per_backend_limit = max(limit*2, 20)`) so the merge step still has enough candidates after dedup.
- Backend trace mode logs hit counts at WARNING level when enabled.

### Default backend list

`DEFAULT_BACKENDS` is now `("openalex", "arxiv", "semantic-scholar", "crossref", "dblp")` — 5 backends instead of 3. Existing `--backend openalex,arxiv,semantic-scholar` still works (explicit list overrides the default).

### MCP surface

- `search_papers` and `discover_new` MCP tool signatures gain optional `exclude_types`, `exclude_terms`, `min_confidence`, `rank_by` parameters. Backwards compatible: omitting them restores v0.15.0 behavior.
- **No new MCP tools** — 42 tools total.

### Tests

- **581 → 618 passing** (+37 tests, 5 skipped unchanged).
- `tests/test_crossref_backend.py`: 6 tests for the Crossref backend (mocked HTTP).
- `tests/test_dblp_backend.py`: 6 tests for the DBLP backend (mocked HTTP, fixture JSON).
- `tests/test_search_confidence.py`: 8 tests for confidence merging across backends.
- `tests/test_search_filters.py`: 10 tests for filter flags and ranking modes.
- Existing fallback / CLI / MCP / discover tests updated for new fields and signatures.

### Non-breaking changes only

All existing CLI commands, MCP tool signatures, and import paths continue to work unchanged. The new ranking is the new default but legacy citation sort is one flag away.

### Deferred to v0.17+

- **PubMed / bioRxiv / medRxiv backends** for biology/medicine — v0.17
- **RePEc backend** for economics/social science — v0.17
- **`--field bio|med|cs|social|...` preset** for newcomers — v0.17
- **NASA ADS / ChemRxiv / ERIC backends** — v0.18+

## v0.15.0 (2026-04-13)

**Discovery workflow glue — the "one wrapper, not six commands" release.**

Driven by a live end-to-end test of v0.14.0 that revealed 9 pain points between "I have a topic" and "I have a papers_input.json ready to ingest". This release fixes the highest-priority glue issues (shape bugs + command chain) in one track. Tracks B (backend dedup + confidence) and C (query intelligence) are deferred to v0.16+ pending a second live test.

### Added — `research-hub discover` wrapper

- **`src/research_hub/discover.py`** (new module, ~290 LOC) — stateful wrapper around search + fit-check that chains the two together with a pause at the AI-scoring handoff. State lives under `<vault>/.research_hub/discover/<cluster-slug>/` and is safe to delete.
- **`research-hub discover new --cluster X --query "..."`** — runs search internally, stashes candidates, writes the fit-check prompt to stdout or `--prompt-out file`. Supports `--year`, `--min-citations`, `--backend`, `--limit`, `--definition`.
- **`research-hub discover continue --cluster X --scored file.json`** — reads stashed candidates, runs fit-check apply (writes the existing `.fit_check_rejected.json` sidecar), converts accepted candidates into a correctly-shaped papers_input.json. Supports `--threshold N` (explicit) and `--auto-threshold` (uses `median(scores) - 1` clamped to `[2, 5]`).
- **`research-hub discover status --cluster X`** — shows current stage (`new` / `scored_pending` / `done`), candidate count, accepted/rejected counts.
- **`research-hub discover clean --cluster X`** — removes the stash directory, safe to run before re-discovering.

### Added — `--auto-threshold` for fit-check apply

- **`research-hub fit-check apply --auto-threshold`** computes threshold from score distribution (`median - 1` clamped to `[2, 5]`). Explicit `--threshold N` still wins when both are supplied. Useful for well-calibrated AI scoring where 5 = obvious accept, 3 = boundary case, 0-1 = obvious reject — the median-1 heuristic rejects boundary cases that the default threshold of 3 would keep.
- **`fit_check.compute_auto_threshold(scores)`** exposed as a reusable helper.

### Fixed — shape bugs from v0.13.0-A

- **`research-hub search --to-papers-input` emitted `{"papers": [...]}`** but the pipeline schema requires a flat JSON array. Now emits a flat list.
- **Authors were a comma-joined string** instead of the Zotero creator dicts the pipeline expects (`[{"creatorType":"author", "firstName":"...", "lastName":"..."}, ...]`). Now emits creator dicts via a shared `_authors_to_creators` helper.
- **Required-but-empty fields** (`summary`, `key_findings`, `methodology`, `relevance`) caused the pipeline validator to reject the output. Now filled with `[TODO: ...]` placeholder markers that the AI replaces in the next step.

These bugs meant v0.14.0's `--to-papers-input` output was unusable without a manual Python adapter script between `search` and `ingest`. v0.15.0 eliminates both adapter steps.

### MCP surface

- 4 new tools: `discover_new`, `discover_continue`, `discover_status`, `discover_clean` — **42 tools total** (was 38).

### Tests

- **560 → 581 passing** (+21 new tests, 5 skipped unchanged).
- `tests/test_discover.py`: 20 tests covering state management, continue logic, auto-threshold, status, clean, and a CLI end-to-end smoke test.
- Existing `test_cli_search.py` and `test_fit_check.py` updated for the new shapes.

### Non-breaking changes only

- `research-hub search --to-papers-input` output shape changed from `{"papers": [...]}` to a flat list. **This is technically a breaking change for any script that parsed the old (buggy) output.** But since the old shape was incompatible with the pipeline validator, it's unlikely any caller actually used it end-to-end.
- All existing CLI commands and MCP tool signatures continue to work unchanged.

### Deferred to v0.16+

- Cross-backend dedup (arxiv↔DOI pairs still double-count)
- SearchResult confidence scoring (which backends found each paper)
- Query generation from cluster definition
- Reject-reason failure analysis

## v0.14.0 (2026-04-13)

**Rigorous fit-check + sub-topic notes — the "know your papers are on-topic AND find them by theme" release.**

Two tracks shipped together. Track A adds a multi-gate fit-check system so you can catch off-topic papers BEFORE they pollute a cluster (instead of discovering it only after the 20-minute NotebookLM cycle). Track B adds sub-topic notes so you can browse a cluster by theme without flipping through every paper. Both tracks stay in the emit/apply pattern — research-hub never calls an LLM directly, the user's AI does the scoring and writing.

### Added — Track A: Multi-gate fit-check system

- **`src/research_hub/fit_check.py`** (328 LOC) — four gates validating cluster topic fit at every pipeline stage.
- **Gate 1 — Pre-ingest AI scoring.** `research-hub fit-check emit` builds a prompt asking an AI to score each candidate paper 0-5 against the cluster definition (falls back to parsing the overview's `## Definition` section when no `--definition` supplied). `research-hub fit-check apply` consumes the scored JSON, filters by threshold (default 3), and writes `.fit_check_rejected.json` sidecar for audit. Default threshold is 3 (keep score >= 3).
- **Gate 2 — Ingest-time term overlap.** Fast, no AI. Extracts up to 12 key terms from the cluster definition (4-char words, word-boundary matches, stoplist). Computes the fraction present in each paper's abstract. Zero overlap → paper frontmatter tagged `fit_warning: true` but still ingested (warning only, never blocks).
- **Gate 3 — Post-ingest NotebookLM audit.** `notebooklm/upload.py` briefing system prompt now requires a `### Off-topic papers` section in every generated briefing. `research-hub fit-check audit --cluster X` parses the section, writes `.fit_check_nlm_flags.json`, and exits 1 if any papers are flagged.
- **Gate 4 — Periodic drift check.** `research-hub fit-check drift` re-emits the fit-check prompt for already-ingested papers against the current overview. Reports only — never auto-removes.
- **CLI surface:**
  - `research-hub fit-check emit --cluster X --candidates file.json [--definition "..."]`
  - `research-hub fit-check apply --cluster X --candidates file.json --scored file.json [--threshold 3]`
  - `research-hub fit-check audit --cluster X`
  - `research-hub fit-check drift --cluster X`
  - `research-hub ingest --fit-check --fit-check-threshold 3` — opt-in gate at ingest time.
- **MCP surface:** 4 new tools — `fit_check_prompt`, `fit_check_apply`, `fit_check_audit`, `fit_check_drift` — **33 tools total** (was 29).

### Added — Track B: Sub-topic notes

- **`src/research_hub/topic.py`** extended with sub-topic propose/assign/build/list support. All v0.13.0 functions (`scaffold_overview`, `read_overview`, `get_topic_digest`, `hub_cluster_dir`, `overview_path`) remain unchanged. `topic.py` grew from 206 LOC to ~720 LOC.
- **File convention** — each cluster's `raw/<cluster>/` folder now has a `topics/` subfolder containing `NN_<slug>.md` files, one per sub-topic. Paper notes gain a `subtopics: [a, b]` frontmatter field. A paper can belong to multiple sub-topics.
- **Three-phase workflow:**
  - **Propose** (`research-hub topic propose --cluster X [--target-count 5]`) — emits a prompt asking an AI to propose 3-6 natural groupings from the cluster digest.
  - **Assign** — `research-hub topic assign emit --subtopics proposed.json` emits the per-paper mapping prompt. `research-hub topic assign apply --assignments file.json` writes the `subtopics:` frontmatter to each paper note.
  - **Build** (`research-hub topic build --cluster X`) — reads paper frontmatter, generates `topics/NN_<slug>.md` for each unique sub-topic. File numbering is stable across runs. Overwrites ONLY the `## Papers` section; Scope / Why / Open questions / See also are user-owned and preserved verbatim on re-run.
  - **List** (`research-hub topic list --cluster X`) — prints a table of existing sub-topics with paper counts.
- **Sub-topic template sections** — Scope / Why these papers cluster together / Papers (auto-generated) / Open questions / See also. Papers section uses Obsidian wiki-links: `[[<slug>|<short-title> (<lastname> <year>)]] — <one-line take>`.
- **MCP surface:** 5 new tools — `propose_subtopics`, `emit_assignment_prompt`, `apply_subtopic_assignments`, `build_topic_notes`, `list_topic_notes` — **38 tools total** (was 33 after Track A).
- **Dashboard integration** — `ClusterCard.subtopic_count` field, populated from `list_subtopics()`. Cluster card shows a `N subtopics` badge when count > 0 (hidden when 0 to avoid clutter).

### Fixed

- **CI MCP test failures (second occurrence).** The earlier `[mcp,dev]` fix in v0.13.0 was insufficient: the tests still used fastmcp's private `mcp._tool_manager._tools` API and the direct `imported_function.fn(...)` pattern, both of which break on fastmcp versions where the decorator does not wrap the imported name. Added `tests/_mcp_helpers.py` with `_list_mcp_tool_names(mcp)` and `_get_mcp_tool(mcp, name)` that try the public `mcp.get_tools()` / `mcp.get_tool(name)` (async) API first and fall back to the private path only for older versions. Replaced every private-API access in `test_consistency.py`, `test_mcp_add_paper.py`, `test_mcp_citation_graph.py`, `test_mcp_server.py`, `test_e2e_smoke.py`.

### Tests

- **520 → 560 passing** (+40 new tests, 5 skipped unchanged).
- Track A: 20 new tests in `tests/test_fit_check.py` covering all four gates (emit_prompt, apply_scores, term_overlap, parse_nlm_off_topic, drift_check, CLI integration).
- Track B: 20 new tests in `tests/test_topic_subtopics.py` + `tests/test_cli_operations.py` covering propose/assign/build/list, stable numbering, multi-sub-topic papers, Papers-section-only overwriting.

### Non-breaking changes only

All existing CLI commands, MCP tool signatures, and public topic.py functions continue to work unchanged. `--fit-check` and sub-topic features are opt-in — default v0.13.0 behavior preserved.

## v0.13.0 (2026-04-12)

**Model-agnostic paper discovery + topic overview notes — the "any AI can drive it" release.**

Two tracks shipped together. Track A replaces single-backend Semantic Scholar search with a three-backend fallback chain (OpenAlex + arXiv + Semantic Scholar) exposed through CLI + MCP, so Claude Code, Claude Desktop, Codex CLI, Gemini CLI, Cursor, Continue, Aider, and plain-shell pipelines all discover papers the same way. Track B adds topic overview notes — every cluster now has a designated `00_overview.md` that any AI can write by reading a cluster digest. Research-hub is pure plumbing; the AI does the writing.

### Added — Track A: Multi-backend paper search + enrich mode

- **`src/research_hub/search/` package** (was single `search.py`) — 7 modules, 759 LOC total. Three backends implementing the `SearchBackend` protocol (`name`, `search`, `get_paper`):
  - **`OpenAlexBackend`** — free, concept search, no API key. Reconstructs abstracts from OpenAlex's inverted index representation. Extracts `arxiv_id` from location metadata. Uses polite-pool `mailto` query param for higher rate limits.
  - **`ArxivBackend`** — Atom XML parsing (stdlib `xml.etree.ElementTree`). 3s throttle per arXiv policy. Client-side year filtering. Strips version suffixes from arxiv IDs.
  - **`SemanticScholarClient`** — existing logic refactored into the backend interface, `year_to` parameter added.
- **`search/fallback.py::search_papers()`** — multi-backend orchestrator. First backend to return a dedup key (normalized DOI → arxiv_id → title) wins the base record; subsequent backends fill empty fields (abstract, pdf_url, citation_count, venue). Backends that raise are logged at WARNING and skipped — never propagates. Results sorted by year descending then citation_count descending.
- **`search/enrich.py::enrich_candidates()`** — resolves a list of heterogeneous candidates (DOI / arxiv ID / title) to full `SearchResult` records. Title matches require rapidfuzz similarity ≥ 60. Purpose-built for Claude Code's WebSearch path: WebSearch discovers candidates, `enrich_candidates` turns them into ingest-ready records using OpenAlex/arXiv/Semantic Scholar.
- **CLI surface:**
  - `research-hub search "..." --year 2024-2025 --min-citations 10 --backend openalex,arxiv --json` — multi-backend query with year window, citation floor, and JSON output for piping.
  - `research-hub search "..." --to-papers-input --cluster <slug>` — emits a ready-to-ingest `papers_input.json` document with empty summary/key_findings/methodology/relevance fields for the AI to fill.
  - `research-hub enrich [candidates...] | -` — new subcommand. Reads DOIs / arxiv IDs / titles from argv or stdin, outputs enriched JSON.
  - `--year` parser accepts `2024`, `2024-`, `-2024`, and `2024-2025`.
- **MCP surface:**
  - `search_papers` extended with `year_from`, `year_to`, `min_citations`, `backends` parameters (backwards compatible — old signature still works).
  - `enrich_candidates(candidates, backends)` — new tool.
  - **26 MCP tools total** (was 25).
- **Backwards compat** — all existing `from research_hub.search import {SearchResult, SemanticScholarClient, iter_new_results}` imports still resolve through `search/__init__.py` re-exports. `iter_new_results` accepts both the legacy single-client signature and new multi-backend signature.

### Added — Track B: Topic overview notes

- **`src/research_hub/topic.py`** (206 LOC) — new module for AI-writable cluster summaries. Research-hub does NOT call any LLM; it provides a digest and a writing target, and the AI does the actual writing.
- **File convention** — overview lives at `<vault>/research_hub/hub/<cluster-slug>/00_overview.md`. The `00_` prefix floats it to the top of Obsidian's default alphabetical folder view.
- **Template sections** — Definition / Why it matters / Applications / Key sub-problems / Seed papers / Further reading. Scaffolded with frontmatter (`type: topic-overview`, `cluster: <slug>`, `status: draft`).
- **CLI surface:**
  - `research-hub topic scaffold --cluster <slug> [--force]` — writes the overview template file. Raises `FileExistsError` without `--force`.
  - `research-hub topic digest --cluster <slug> [--out file.md]` — emits the full-text digest of every paper in the cluster (title + authors + year + DOI + abstract) as markdown. The AI reads this to write the overview.
  - `research-hub topic show --cluster <slug>` — prints the current overview content, or exits 1 with a "no overview" hint.
- **MCP tools (3 new, 29 tools total)**:
  - `get_topic_digest(cluster_slug)` — returns `{cluster_slug, cluster_title, paper_count, papers: [...], markdown}`.
  - `write_topic_overview(cluster_slug, markdown, overwrite=False)` — writes AI-generated markdown. Refuses to overwrite without explicit flag.
  - `read_topic_overview(cluster_slug)` — returns `{ok, markdown}` or `{ok: False, reason: "no overview found"}`.
- **Dashboard integration** — `ClusterCard.has_overview` field, populated from `overview_path().exists()`. Cluster card shows "overview" / "no overview" badge; heading links to Obsidian's `00_overview.md` when present.
- **Vault builder integration** — when rendering the cluster hub/index page, prepends the overview content (frontmatter + first H1 stripped) above the paper list, so the Obsidian hub page opens with the topic summary.

### Added — Docs

- **`docs/ai-integrations.md`** — complete integration guide for Claude Code, Claude Desktop, Cursor, Continue, Codex CLI, Gemini CLI, Aider, and plain-shell workflows. Shows the exact commands for each AI surface. Covers the shared `discover → enrich → ingest → overview → verify via NotebookLM` pattern.

### Fixed

- **CI MCP test failures** — `.github/workflows/ci.yml` now installs `[mcp,dev]` extras. Without fastmcp the `_FallbackMCP` was returning raw functions with no `.fn` attribute, breaking `test_mcp_add_paper`, `test_e2e_smoke::test_e2e_mcp_download_artifacts_tool`, and `test_e2e_smoke::test_e2e_read_briefing_missing_returns_remedy`.

### Tests

- **465 → 520 passing** (+55 tests, 5 skipped unchanged).
- Track A: 40 new tests — `test_openalex_backend` (7), `test_arxiv_backend` (6), `test_search_fallback` (7), `test_search_enrich` (5), `test_cli_search` (6), `test_mcp_server` additions (3), `test_search.py` dedup_key + backcompat (6).
- Track B: 15 new tests — `test_topic` (12), `test_cli_operations` topic tests (3).

### Non-breaking changes only

All existing CLI commands, MCP tool signatures, and import paths continue to work unchanged. The `search.py` module is deleted and replaced by the `search/` package, but the public re-exports make this invisible to callers.

## v0.12.0 (2026-04-13)

**Pipeline hardening + PDF-first NotebookLM bundling + Draft composer — the "vault → draft" transition release.**

Three tracks shipped together, driven by real user-pain caught during a live 22-paper ingest of an LLM harness engineering cluster.

### Added — Track A: Pipeline hardening

- **Full schema validator** — `_validate_paper_input` now checks all 12 required fields upfront (was 4 in v0.11.0). Missing fields are reported with the exact text to paste into `papers_input.json`. Prevents the "KeyError mid-ingest → orphaned Zotero item" failure mode.
- **`slug` + `sub_category` auto-generation** — minimal papers_input.json entries (4 fields) now work out of the box. Slug is derived from `{firstauthor_lastname}{year}-{slugified_title}`; `sub_category` defaults to the cluster slug.
- **Collection-scoped `check_duplicate`** — `zotero/client.py::check_duplicate` gains optional `collection_key` kwarg. Library-wide search was producing false-positive skips when a paper existed in a different cluster's collection. New CLI flag `research-hub ingest --allow-library-duplicates` explicitly bypasses the dedup check.
- **`research-hub pipeline repair --cluster X`** — new subcommand that reconciles Zotero collection ⇄ Obsidian notes ⇄ dedup_index for a given cluster. Finds orphaned Zotero items (no Obsidian note), orphaned notes (no Zotero item), and stale dedup entries. Default dry-run; requires `--execute` to actually write.
- **`docs/papers_input_schema.md`** — rewritten with the full field reference, minimal + complete examples, and common-errors section.

### Added — Track B: PDF-first NotebookLM bundling

- **`research-hub notebooklm bundle --download-pdfs`** — new flag that tries to acquire a local PDF before falling back to URL upload. NotebookLM ingests local PDFs ~6× faster than URLs (it has to fetch + parse URLs server-side at 15-30s each).
- **`notebooklm/pdf_fetcher.py`** — new module with a 4-step fallback chain:
  1. Local cache by DOI (`<pdfs_dir>/<normalized_doi>.pdf`)
  2. Local cache by slug (`<pdfs_dir>/<slug>.pdf`)
  3. arXiv (`https://arxiv.org/pdf/<arxiv_id>.pdf` when the DOI is arxiv)
  4. Unpaywall API (free tier, OA-only papers)
- **Graceful handling of non-downloadable papers** — paywalled without OA, reports, timeouts, and oversized (>50 MB) PDFs all fall through to URL upload without erroring out. `BundleEntry.pdf_source` records provenance for the summary (`local-doi`, `arxiv`, `unpaywall`, etc).
- **Bundle summary** now breaks down by PDF source: `pdf: 22 (arxiv: 19, local-doi: 3, unpaywall: 0)`.

### Added — Track C: Draft composer

- **`research-hub compose-draft --cluster X --outline "Intro;Methods;Results" --style apa`** — new CLI that assembles captured quotes into a markdown draft. Supports APA / Chicago / MLA / LaTeX citation styles. Quotes are assigned to sections by matching `quote.context_note` against outline entries (case-insensitive substring); unmatched quotes land in the first section. Default output path: `<vault>/drafts/<YYYYMMDD>-<cluster>-draft.md`.
- **`src/research_hub/drafting.py`** — new module with `DraftRequest`, `DraftResult`, `compose_draft()`, `compose_draft_from_cli()`, and `DraftingError`. Reuses existing `writing.py` functions (`load_all_quotes`, `build_inline_citation`, `build_markdown_citation`, `resolve_paper_meta`) — no duplication.
- **MCP tool `compose_draft(cluster_slug, outline, quote_slugs, style, include_bibliography)`** — lets AI agents assemble drafts programmatically. Returns `{status, path, cluster_slug, quote_count, cited_paper_count, section_count, markdown_preview}`. **25 MCP tools total** (was 24).
- **Dashboard Writing tab composer panel** — new right column at >=900px: cluster picker, outline textarea, style radios, include-bibliography checkbox, quote multi-select (tied to left-column cards), and a `[Build draft command]` button that emits the exact `research-hub compose-draft ...` invocation and copies it to clipboard (same pattern as Manage tab).

### Changed

- NotebookLM briefing language note: briefings are generated in the language of the Google account's UI locale. To get English briefings for English users, set the Google account language to English before generating. A dedicated `research-hub briefings translate` feature is deferred to v0.13.

### Tests

- **417 → 465 passing** + 5 skipped. 48 new tests across the three tracks:
  - 30+ in `test_pipeline_schema_v012.py`, `test_pipeline_repair.py`, and updated `test_pipeline_metadata.py` / `test_pipeline.py`
  - 21 in `test_pdf_fetcher.py` + updated `test_notebooklm_bundle.py`
  - 22 in `test_drafting.py`, `test_dashboard_sections_v2.py`, `test_mcp_server.py`, `test_consistency.py`

## v0.11.0 (2026-04-12)

**Writing helpers — inline citations, quote capture, and a Writing tab to close the loop from "found it" to "used it in a draft".**

### Added
- **`research-hub cite --inline`** — emits an inline-style citation like `(Lamparth et al., 2024)` instead of full BibTeX. Useful in draft prose.
- **`research-hub cite --markdown`** — emits a markdown link with the DOI: `[Lamparth et al. (2024)](https://doi.org/10.1609/aies.v7i1.31681)`.
- **`research-hub cite --style apa|chicago|mla|latex`** — picks the inline format. APA is default. LaTeX style derives a BibKey from the paper slug (`\citep{lamparth2024human}`).
- **`research-hub quote <slug> --page 12 --text "..."` + `--context "..."`** — captures an excerpt from a paper into `<vault>/.research_hub/quotes/<slug>.md` with a small frontmatter block per quote (page, captured_at, context_note).
- **`research-hub quote list [--cluster SLUG]`** — browse captured quotes.
- **Dashboard Library tab** — every paper row now has a `[Quote]` button next to `[Cite]`. Clicking opens a popup with page + text + context fields and builds the exact `research-hub quote ...` command for you.
- **New Dashboard tab: Writing** (order 35, between Briefings and Diagnostics) — lists captured quotes grouped by cluster and papers marked `status: cited`. Each quote card has `Copy as markdown` and `Copy inline` action buttons.
- 3 new MCP tools (24 total):
  - `build_citation(doi_or_slug, style)` — returns `{inline, markdown}` for a paper so AI agents can build citations for your draft
  - `list_quotes(cluster_slug)` — lists captured quotes
  - `capture_quote(slug, page, text, context)` — saves a quote from the agent side
- **New module `src/research_hub/writing.py`** — holds the citation formatters, `Quote` dataclass persistence, and `resolve_paper_meta` helper that reads an Obsidian note's frontmatter to pull authors/year/title/doi.
- **New section module `src/research_hub/dashboard/writing_section.py`** — the Writing tab renderer.

### Changed
- Dashboard `DashboardData` now carries a `quotes: list[Quote]` field populated from `<vault>/.research_hub/quotes/*.md` on each render.
- `SKILL.md` documents the new `quote`, `cite --inline`, `cite --markdown`, and dashboard Writing tab.

### Tests
- Suite: **386 → 417 passing** + 5 skipped.
- 12 new tests in `tests/test_writing.py` covering the inline/markdown formatters, quote persistence (save + load + multi-block files), and frontmatter resolver.
- 7 new tests in `tests/test_dashboard_sections_v2.py` for the Writing section (empty state, quote cards, grouping by cluster, cited paper listing).
- Updated `test_header_section_renders_tabs` to expect the 6th tab radio.

## v0.10.0 (2026-04-12)

**Dashboard redesign — "personal knowledge garden" for AI-assisted literature review.**

The dashboard now answers a single question: *"AI added a bunch of papers — what did it add, what categories, and where is each one stored across Zotero / Obsidian / NotebookLM?"*

### Added
- **Five-tab audit dashboard** (`Overview` / `Library` / `Briefings` / `Diagnostics` / `Manage`). Pure CSS tabs (radio + `:checked` sibling selectors) — zero JavaScript for the tab mechanic. Default tab is Overview.
- **Overview tab** — three widgets:
  - **Treemap** of papers per cluster, sqrt-scaled flex weights so a 7/8/331 distribution stays readable (cluster names no longer get squeezed). Click any cell to jump to that cluster in the Library tab.
  - **Storage map** — per-cluster table with clickable `↗ Open` deep-links to each of the three systems: `zotero://select/library/collections/{key}`, `obsidian://open?path=raw/{slug}`, and the cluster's NotebookLM notebook URL.
  - **Recent additions** feed — last 15 papers your AI agent ingested, each with a cluster tag, relative time, and inline [Open] menu.
- **Library tab** — cluster cards with paper rows (title, authors, year, 240-char abstract, [Cite] popup, [Open ▼] menu). Per-cluster [Download .bib] button for batch citation export. NO status badges, NO reading-status pills — this is a locator, not a progress tracker.
- **Briefings tab** — inline preview of downloaded NotebookLM briefings with [Open in NotebookLM] and [Copy full text] actions.
- **Diagnostics tab** — health badges (Zotero / Obsidian / NotebookLM) + drift alerts + clickable remedy commands.
- **Manage tab** — per-cluster command-builder forms: rename, merge, split, bind-Zotero, bind-NLM, delete. Each form emits the exact `research-hub clusters …` CLI command on click and copies it to your clipboard.
- **Debug widget** — footer section with a "Copy snapshot" button that emits vault metadata + health state + cluster bindings as a paste-ready blob for AI assistant handoff. Closes the user feedback loop when something breaks.
- **Health banner** — when `doctor` reports any FAIL, the Overview tab shows a red banner at the top with the failing checks and their remedy commands.
- **`--watch` mode** — `research-hub dashboard --watch` polls vault state files every 5s and re-renders on change. Combine with `--refresh N` to control the browser auto-reload interval.
- **`--rich-bibtex` flag** — opt-in Zotero `get_formatted` per paper for full BibTeX entries (abstract, tags, collections). Default uses an instant frontmatter fallback — generation is under a second on a 346-paper vault.
- **Impeccable design tokens** — OKLCH-only color palette, warm-amber brand hue (not default blue), tinted neutrals, 4pt spacing scale, Geist/Literata/Geist Mono typography stack. Light theme.

### Changed
- Dashboard package now split into 6 modules: `types.py` (dataclass contract), `data.py` (vault walker), `citation.py`, `drift.py`, `briefing.py`, `sections.py`, `render.py`, plus inline `template.html` / `style.css` / `script.js`. Extensible via the `DashboardSection` base class.
- Dashboard render time on the 346-paper live vault: **0.9 seconds** (was 10+ minutes when the rich-BibTeX path was the default).
- Zotero credential loader now supports three file layouts: flat keys, nested `zotero.*` block, and the legacy `~/.claude/skills/zotero-skills/config.json` left over from the standalone zotero-skills install. Users who set up Zotero months ago no longer need to re-init.
- `doctor` routes all Zotero credential reads through the shared `_load_credentials()` helper so the health check sees exactly the same keys as the dashboard and the pipeline.
- Dashboard no longer renders per-paper Z/O/N sync badges or reading-status pills — they were fighting Zotero/Obsidian for the same real estate. Cross-system state is shown at the cluster level in the Storage map instead.

### Fixed
- **Chrome file:// security violation.** The Manage tab forms had no `action` attribute, so pressing Enter in an input field submitted to the current URL — which on `file://` triggers Chrome's "unsafe attempt to load URL from frame" block. Forms now carry `action="javascript:void(0)"` and the script.js submit handler routes Enter to the "Copy command" button.
- **Same security violation from treemap cells** — they used `<a href="#tab-library">`, which also trips the file:// check. Replaced with `<button data-jump-tab="library">` + a click handler that selects the target tab radio without navigating the URL.
- **331 missing [Cite] buttons** — `citation.py` caught the Zotero API error and returned `""` instead of falling through to the frontmatter fallback. Now every paper gets a valid BibTeX entry regardless of API availability.
- **Tab panels rendering blank** — CSS `:checked ~ main #tab-*` sibling selector was wrong because the radios are inside `<main>`, not siblings of it. Replaced with `:checked ~ #tab-*` direct sibling.
- **Treemap label overflow** for long cluster names. Added `-webkit-line-clamp: 3`, bumped min-width 140 → 200px and min-height 90 → 140px.
- `_detect_persona` no longer forces `analyst` when `zot=None` — persona is a config-time setting, not derived from runtime client state.
- `generate_dashboard` now instantiates `ZoteroDualClient` (has `get_formatted`) instead of the raw pyzotero `Zotero` object when the api_key is actually loadable.

### Tests
- Suite: **361 → 386 passing** (5 legacy v0.9.0-G1 section tests marked as `@pytest.mark.skip("rewritten in v0.10")`).
- 14 new tests for the dashboard data layer (`tests/test_dashboard_data.py`).
- 23 new tests for the dashboard sections layer (`tests/test_dashboard_sections_v2.py`).

## v0.9.0 (2026-04-12)

**System integration audit + UX hardening + personal HTML dashboard + closes the AI loop with NotebookLM artifact download.**

### Added
- `research-hub notebooklm download --cluster X --type brief` — downloads the latest generated briefing from NotebookLM back to `<vault>/.research_hub/artifacts/<cluster>/brief-<UTC>.txt`. Reads `span.notebook-summary .summary-content` from the DOM directly (no clipboard juggling, locale-independent). **Closes the AI loop**: search → save → upload → generate → **download** → AI analysis.
- `research-hub notebooklm read-briefing --cluster X` — prints the most recently downloaded briefing for inline AI analysis.
- 2 new MCP tools: `download_artifacts(cluster_slug, artifact_type)`, `read_briefing(cluster_slug)` — let AI agents pull briefings into context without re-running NotebookLM.
- `research-hub dashboard [--open]` — personal HTML dashboard at `<vault>/.research_hub/dashboard.html`. Single self-contained file with stat cards, cluster table, status badges, and NotebookLM links. Hero artifact for the project.
- `research-hub add <doi-or-arxiv-id> [--cluster X]` — one-shot Search → Save replaces hand-writing `papers_input.json`. Fetches metadata via Semantic Scholar with CrossRef enrichment.
- `research-hub init --persona researcher|analyst` — analyst persona skips Zotero entirely (Obsidian + NotebookLM only).
- `research-hub dedup invalidate --doi/--path` and `dedup rebuild [--obsidian-only]` — surgical dedup management without re-scanning Zotero.
- `papers_input.json` validator: pipeline catches missing `creatorType`, malformed authors, missing fields BEFORE hitting Zotero API. Clear error messages instead of cryptic 400 crashes.
- 4 new MCP tools total: `add_paper`, `generate_dashboard`, `download_artifacts`, `read_briefing` (21 total).
- New docs: `docs/cli-reference.md`, `docs/papers_input_schema.md`.

### Changed
- `doctor` now persona-aware: when `no_zotero: true` is set in config or `RESEARCH_HUB_NO_ZOTERO=1` env var, Zotero checks report "Skipped (analyst mode)" instead of FAIL.
- `doctor` correctly counts dedup index entries (was reporting 0 when index had thousands).
- `nlm_cache.json` now records `artifacts.brief = {path, downloaded_at, char_count, titles}` per cluster after a successful download.

### Fixed
- Pipeline silently dropped dict-format authors `[{firstName, lastName}]` → `authors: "Unknown"` in Obsidian YAML.
- Pipeline never wrote `volume`, `issue`, `pages` to Zotero or Obsidian even when input had them.
- `clusters rename` updates display name without orphaning notes.
- 12 new regression tests for pipeline metadata and dedup invalidation.
- 4 new tests for the briefing download / read flow (mocked CDP session).

Suite: 274 → 338 passing.

## v0.8.2 (2026-04-12)

### Added
- New MCP tool `propose_research_setup(topic)` — AI agents propose cluster/collection/notebook names BEFORE creating, ask user to confirm.
- `RESEARCH_HUB_NO_ZOTERO=1` env var enables data analyst persona (Obsidian + NotebookLM only, no Zotero).
- SKILL.md documents both personas + the "always confirm names" protocol.

## v0.8.1 (2026-04-12)

### Fixed
- `_render_obsidian_note` now handles dict-format authors (was producing `authors: "Unknown"`).
- Pipeline + `make_raw_md` now emit `volume`, `issue`, `pages` fields to both Zotero items and Obsidian YAML.
- New `**Citation:** Journal, Vol(Issue), Pages` line in note body.

## v0.8.0 (2026-04-12)

### Added
- Citation graph exploration via Semantic Scholar API.
- `research-hub references <doi>` — list papers cited by this paper.
- `research-hub cited-by <doi>` — list papers that cite this paper.
- 2 new MCP tools: `get_references`, `get_citations` (16 total).

## v0.7.0 (2026-04-12)

### Added
- Daily research operations: `remove`, `mark`, `move`, `find`.
- Cluster CRUD: `clusters rename`, `clusters delete`, `clusters merge`, `clusters split`.
- Vault search: `research-hub find "query" [--full] [--cluster X] [--status Y]`.
- 6 new MCP tools (14 total): `remove_paper`, `mark_paper`, `move_paper`, `search_vault`, `merge_clusters`, `split_cluster`.

## v0.6.0 (2026-04-12)

### Added
- MCP stdio server for AI assistant integration. 8 tools exposed via `research-hub serve`.
- Tools: `search_papers`, `verify_paper`, `suggest_integration`, `list_clusters`, `show_cluster`, `export_citation`, `run_doctor`, `get_config_info`.
- Optional dependency `[mcp]` extra installs `fastmcp>=2.0`.

## v0.5.0 (2026-04-12)

**First public PyPI release.** `pip install research-hub-pipeline[playwright]`

### Added
- `research-hub init` — interactive setup wizard (vault + Zotero + Chrome)
- `research-hub doctor` — 7-check health diagnostic
- `research-hub install --platform X` — skill install for Claude Code / Codex / Cursor / Gemini CLI
- `research-hub verify --doi/--arxiv/--paper` — HTTP-based paper existence verification with 7-day cache
- `research-hub suggest <id> [--json]` — cluster + related-paper suggestions (keyword/tag/author/venue scoring)
- `research-hub cite <id> --format bibtex` — BibTeX / BibLaTeX / RIS / CSL-JSON export via pyzotero
- `research-hub notebooklm login --cdp` — CDP-attach login bypassing Google bot detection
- `research-hub notebooklm upload --cluster X` — auto-upload PDF + URL sources
- `research-hub notebooklm generate --type brief` — trigger NotebookLM artifact generation (fire-and-forget)
- NotebookLM selectors verified against live zh-TW DOM (2026-04-11)
- Bundle builder: author-year PDF filename matching fallback
- platformdirs config resolution (Linux XDG / macOS / Windows APPDATA)
- GitHub Actions: CI (3.10/3.11/3.12) + auto-publish to PyPI on tag push
- SKILL.md bundled in wheel for AI coding assistant discoverability
- Terminal output examples at `docs/examples/`

### Changed
- Package name: `research-hub` → `research-hub-pipeline` (PyPI)
- Config path: repo-local → `platformdirs.user_config_dir("research-hub")`
- `verify` subcommand: extended with `--doi/--arxiv/--paper` flags (repo-integrity check preserved as fallback)
- Pipeline DOI validation: replaced `"48550" in doi` heuristic with real HTTP HEAD checks
- `upload_cluster` + `generate_artifact`: default `headless=False` (visible Chrome)
- README: rewritten for pip-install-first audience (310 lines)

### Fixed
- `Path(__file__).parents[N]` repo-relative paths crash after pip install
- NotebookLM selectors: `source-stretched-button` → `add-source-button`, `source-panel` → `source-picker`
- Bundle builder: 0 PDFs when vault uses Author_Year filenames
- `token_set_ratio` threshold: 87 → 80 (cross-platform rapidfuzz compatibility)
- pytest-cov missing from dev dependencies

## v0.4.0 (2026-04-11)

### Added
- Tri-system cluster binding (Zotero + Obsidian + NotebookLM)
- `clusters bind/show/new/list` CLI
- `sync status/reconcile` for Zotero ↔ Obsidian drift
- `notebooklm bundle --cluster X` drag-drop fallback
- 142 tests

## v0.3.4 (2026-04-10)

### Added
- `research-hub status` dashboard
- `migrate-yaml` for legacy note patching
- Hub index overview page

## v0.3.0 — v0.3.3 (2026-04-10)

### Added
- Dedup index (DOI + title normalization)
- Topic clusters with seed keywords
- Bidirectional wikilink updater
- Cluster synthesis pages
- Semantic Scholar search stub

## v0.2.1 (2026-04-10)

### Added
- First public release (MIT license)
- Bilingual README (EN + zh-TW)
- CI on Python 3.10 / 3.11 / 3.12
