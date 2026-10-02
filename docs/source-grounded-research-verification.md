# Source-grounded native research verification

## Scope and decision

Base: `a643aceefc52cbf690264a3801e597d787ebd714` (Research Hub master,
checked 2026-10-02). Python/MCP package remains `1.2.0`; the independent
marketplace plugin changes `0.5.1` → `0.5.2` because the repository's CI
skill-version guard requires cache invalidation for skill-content changes.
This is an unreleased, unpushed change, not an installed-host or release claim.

The transfer is architecture-preserving: existing host-native discovery →
deterministic ingest and prose → packet validator → human semantic gate
boundaries stay intact. The ingest architecture and existing Mermaid flow were
inspected; no component, diagram topology, runtime scheduler, ledger/operator,
paid evaluation system, canonical version database or package dependency was
added. Existing strict evidence packet v1, workflow state and papers input
shapes remain unchanged.

## Changes

- One shared, proportionate research protocol maps the original user objective
  and constraints to material information needs, concepts, distinct native
  search paths and screening decisions. Suggestions remain suggestions; planned
  queries, failed providers and unknown payloads do not count as search results.
- Literature roles distinguish topic-core, closest prior work, historical
  classic, methodological comparator and contrary/boundary evidence. Topic
  decisions retain significance, alternatives/dead ends, access/time/cost/data/
  ethics feasibility and the researcher's/advisor's final choice.
- Triage and NotebookLM verification separate metadata, abstracts, generated
  summaries and actual located full-text evidence. Relevant source sections
  replace a universal first-pages window, and reports state sections actually
  reviewed plus assessed/total and unchecked claims.
- An optional `research-source-audit/1.0` sidecar extends the existing Python
  validator boundary without changing packet v1. It binds packet hash and
  claim/source/verifier IDs to recorded work/publication version, actual source
  level/status, raw/text hashes and exact quote ranges/locators. Existing
  source-fetch receipts are replayed with the production validator. Supported,
  contradicted and mixed definitive states require bound decisive assessments;
  partial/unverifiable evidence stays explicit.
- Existing native provenance supports separate versions, acquisition attempts
  and include-to-exclude decision observations. User notes are preserved, and
  exact replay remains byte-stable. This is retained provenance, not automatic
  scientific adjudication or Zotero merging.
- Five consumers use the shared contract: research-hub, literature-triage-matrix,
  notebooklm-brief-verifier, gap-to-topic and research-workflow-orchestrator.
  Missing Hub runtime blocks Hub actions while available native research can
  continue. Source and complete packaged skill directories remain identical.

## Frozen same-input regression

Run `scripts/verify_source_grounded_research.py --fixtures-dir <directory>`
once to create immutable synthetic fixtures, then replay the same directory
against the base and changed source trees. The fixture manifest SHA-256 used
for this comparison was:

`e9b63e23825e83fc976ccc19e8b870ae133191c04a756e806f2c093de5e80e38`

Only HTTP transport and DNS are stubbed. Source acquisition, extraction,
receipt generation/replay, packet validation and the optional audit validator
are production code. Both runs read the same saved packet/profile/source bytes.
The base has packet-only validation and cannot apply the optional audit; its
structural pass never certified source-passage support.

| Same frozen fixture | Base packet-only accepted | Changed optional audit accepted |
|---|---|---|
| Located full-text excerpt | yes | yes |
| Supported abstract at its narrow scope | yes | yes |
| Abstract promoted to required full text | yes | no |
| Wrong publication version | yes | no |
| Fabricated quote absent from saved text | yes | no |
| Generated summary promoted to source support | yes | no |
| Unavailable source marked as support | yes | no |
| Unknown publication version marked as support | yes | no |

The changed wheel replay produces the same eight outcomes. This demonstrates
local binding/rejection improvement while retaining useful supported evidence;
it is not a measured gain in search recall, research quality or native-model
judgment.

## Executed validation

Local Linux, Python 3.12.14; isolated writable HOME for tests. An initial default
HOME run hit read-only `/home/agent/knowledge-base`; the final runs use isolated
fixtures and do not modify the production runtime to hide that environment
problem.

- Final full CI-style suite: 3528 passed, 23 skipped, 7 slow deselected,
  3 expected failures; skipped/deselected checks are not passes
- Final full coverage suite: same outcomes, 80.55% total against the CI 62% gate
- Explicit stress suite: 15 passed
- Explicit slow suite: 6 passed (all five clean extras-install/import probes and
  the synthetic 60-second search-pool timeout); 8 skips comprise the same seven
  obsolete NotebookLM module skips plus one opt-in live-vault check
- New profile/installed-probe tests: 30 passed, zero skips
- Independent focused review: 138 passed, 2 optional harness skips; defects
  found in review were fixed and regression-tested before final full runs
- Build: sdist and wheel succeed; wheel includes all 47 byte-identical skill
  files, source-audit validator/schema and unchanged strict packet v1 schema
- Extracted-wheel production replay: same frozen eight-case outcomes
- Native handoff script: preview changes zero files; two in-batch evidence
  records and three after incremental observation; user body/reading state
  preserved; exact replay leaves note bytes unchanged; one synthetic Zotero
  item; unsafe path rejected
- Native version/reversal handoff test invokes actual CLI ingest preview and
  storage with an explicit fixture Zotero seam and stubbed identity gate;
  it does not claim real library writes or synthetic DOI authenticity
- Strict packet v1 schema is byte-unchanged; packet-only callers remain valid,
  and inserting a sidecar property into v1 remains rejected
- `git diff --check` passes

The exact 23 ordinary-suite skips are recorded in the JUnit/skip inventory:
12 repository-disabled obsolete tests (seven NotebookLM browser-era modules and
five old dashboard tests); six live-provider evaluation checks requiring explicit
network opt-in; two unavailable live/private fixtures; one persona factory
conditional; and two optional `agent_collab_harness` integration checks. The
additional live-vault slow check remains skipped. None is counted as a pass.

The normal registry route for `agent-collab-harness==0.4.0` returned
`from versions: none` / `No matching distribution found` in this environment;
that does not establish global unavailability. Official release wheels were
then downloaded and checked against their published SHA-256 digests:

- 0.4.0: `991ca9d92ea0efb5a1282a5d616ab84152a7e0ee472af4ed21acb58389ebe22b`
- 0.5.1: `088fb34363a2bc0f434c4863a47ded95c9f51681caf45f028c36a661c937312d`

Each wheel was installed only into a separate temporary integration path.
The actual workflow-runtime suite passes 22/22 with each SDK, including both
previously skipped public-harness checks. This verifies the exercised legacy-v1
seam, not v2 context-maintenance semantics. The default SDK-less full suite
still tests standalone/missing-optional behavior and records its two skips.
No policy migration, real authorization key, credentials/settings change or
user-machine installation occurred.

The new source-audit reference probes the installed validator's kwargs and
packaged schema before invocation. Package version 1.2.0 alone cannot establish
new profile availability; a skill/plugin update does not update its Python
runtime. When unavailable, manual/native review remains possible but legacy
packet-only validation cannot be described as source audit.

The three expected failures are existing dashboard-cache and legacy
ClusterRegistry/DedupIndex migration tests; they are not passes. The detailed
skip inventory and opt-in slow-check outcomes are recorded with the final
verification artifacts. Live-vault/private-data and unrequested live
provider evaluation remain outside this synthetic/offline acceptance. Local
checks do not substitute for the GitHub OS/Python matrix, loaded Codex/Hermes/
Antigravity behavior or live Zotero/NotebookLM integration.

## Limits and human decisions

Hashes and exact quote presence prove captured-artifact consistency. They do
not prove publisher authenticity, true publication-version identity, semantic
entailment, adequate contrary search, substantive coverage, novelty, feasible
study design or submission readiness. Native captures without source-fetch
receipts have weaker provenance and are explicitly identified as such.

Scope-to-query and completion improvements are instruction contracts checked
for consistency and provenance retention, not an executed native search-quality
study. Real research still needs source/semantic review and explicit topic,
resource/ethics, scientific revision and submission decisions. No journal
submission, release, tag, merge, deploy, credential creation or paid/live model
evaluation was performed.
