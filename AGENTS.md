<!-- OPENWIKI:START -->

## OpenWiki

This repository uses OpenWiki for recurring code documentation. Start with `openwiki/quickstart.md`, then follow its links to architecture, workflows, domain concepts, operations, integrations, testing guidance, and source maps.

The OpenWiki GitHub Actions workflow (currently manual-dispatch only) refreshes the repository wiki. Do not hand-edit generated OpenWiki pages unless explicitly asked; prefer updating source code/docs and letting OpenWiki regenerate.

<!-- OPENWIKI:END -->

## Code Review Rules

These rules apply only while conducting code review. They do not replace
implementation or publication instructions or valid authorization for other tasks.

- Review the actual diff at its stated base and head. Route checks by the
  affected paths and trace only the related source, consumer, schema, package,
  and CI contracts. Keep the existing OpenWiki generated-marker block byte for
  byte; do not hand-edit generated OpenWiki pages.
- For PDF extraction, annotation, and reading-order paths, verify that glyph
  direction, margin notes, and reading order preserve the source's meaning and
  placement. If visual inspection is unavailable, report that verification gap
  explicitly; do not bypass the repository's `file://` policy.
- For source selection, acquisition, and saved artifacts, bind claims to the
  exact source identity and version. Treat access failure or missing provenance
  as unknown rather than as evidence about source content.
- For Obsidian and HTML output, check semantic structure, links/frontmatter,
  encoding, and preservation of user-authored content. For demos, identify the
  canonical artifact and entrypoint and report its actual acceptance state;
  schema/checker success alone is not human acceptance.
- Mock output and unrun experiments demonstrate only the behavior actually
  exercised; do not present them as live behavior, validated content, or an
  accepted demo. Keep schema checks distinct from human acceptance.
- When affected code reads paths, renders HTML, or handles source/private data,
  check traversal, injection, and disclosure risks at the concrete input and
  output boundaries. Do not expose private source text in logs or fixtures.
- For packaging changes, compare the source tree with the corresponding
  `web`, wheel, and `skills_data` contents for the changed assets. A source-tree
  check alone does not prove the distributed package contains the same files.
- For a bug fix, inspect representative tests for the failure and a safe
  case. Where feasible, check sensitivity using a known faulty baseline or a
  bounded negative case. Report missing case coverage separately from whether
  failure against old behavior is unverified; a green test alone does not prove
  the fix.
- For changed file access and failure paths, check validation against the
  applicable trusted-root or selected-input scope before reads or writes, and
  redaction of sensitive content before errors or logs are emitted.
- For changes to a best-effort budget or partial-result contract, check its
  stop rule and disclosures of scope, unresolved needs, and next steps. Do not
  promise delivery if a hard cutoff or stuck call prevents finalization.
- For install or packaged-skill changes, compare source, version, packaged
  payload, and cache identity where applicable and evidence is available. For
  changed first-use paths, trace the documented steps, recovery and fallback;
  flag unnecessary repeated work without removing necessary safeguards. Do not
  infer installed-host behavior or user acceptance from fixtures or guidance.

- Findings need a concrete path and line/symbol, trigger, consequence, and
  evidence. Separate confirmed defects, hypotheses, and verification gaps; omit
  style-only preferences and follow the platform's required finding format.
- A review task itself does not modify code, install dependencies, start paid
  models, or merge. Every PR merge needs separate explicit user consent after
  the user receives the review summary, actual test status, and remaining gaps.

## Product Premises and Feature Proposals

These project-specific premises guide future proposals and implementation;
they are requirements, not claims that the current product already satisfies
them. They do not replace the review rules or grant access, write, or release
authorization.

- Researchers still read, assess evidence, and make decisions. AI should help
  them organize, summarize, and reuse selected saved literature, not replace
  their reading or mark material as human-reviewed automatically.
- Keep the core journey coherent: import -> scope-aware summary -> human
  review/classification -> notes/library -> evidence-backed writing. Preserve
  source identity, version, and retrievable provenance across these steps;
  distinguish saved material, AI input coverage, and human review status.
- Zotero, Obsidian, and NotebookLM are optional integrations, not prerequisites
  for being a researcher. Design a useful core reading and library workflow
  without these accounts; disclose unavailable capabilities honestly.
- Apply the user's principle: "少一個功能，不能把多一步操作轉嫁給使用者。"
  Removing a feature is not progress if it shifts work to manual re-entry,
  copy/paste, commands, or another application. Compare the complete task,
  including switching and recovery, rather than counting visible controls.
- Start from an evidenced user pain point, not an assumed need for a panel or
  more integrations. Keep frequent reading actions discoverable and reveal
  advanced options progressively; do not hide essential status or controls.
- Reuse existing material only within the user's selected project/source
  scope. Do not silently scan or upload an entire private library or vault;
  expanding scope or transmitting data needs the applicable authorization.
- Fewer steps must not remove user agency, human review, privacy notices,
  access authorization, or necessary safety confirmations. Make writes and
  their ownership explicit; preserve human content and provide appropriate
  preview, conflict handling, cancellation, and recovery.
- Treat readable text, keyboard access, responsive layout, startup/readiness,
  and recovery as functional requirements. Establish task and performance
  baselines before claiming improvement; distinguish synthetic checks, real
  source/provider tests, independent usability review, and user acceptance.

Before proposing a new workflow, panel, integration, or feature removal,
include this pain-point brief (mark unverified assumptions explicitly):

1. **Who:** intended user and research context.
2. **Current workflow:** how the task is completed today, including tools.
3. **Friction:** the concrete failure, repeated work, or blocked outcome.
4. **Evidence:** observed behavior, user report, or source; state gaps.
5. **Steps removed:** work the proposal genuinely eliminates end to end.
6. **New steps/costs:** setup, permissions, switching, maintenance, and recovery;
   separate necessary safeguards from avoidable friction.
7. **Non-users:** who does not need this feature and their usable fallback.
8. **Acceptance:** observable before/after task results, failure cases, and
   source-fidelity checks; label proposed targets rather than proven metrics.
