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
- Findings need a concrete path and line/symbol, trigger, consequence, and
  evidence. Separate confirmed defects, hypotheses, and verification gaps; omit
  style-only preferences and follow the platform's required finding format.
- A review task itself does not modify code, install dependencies, start paid
  models, or merge. Every PR merge needs separate explicit user consent after
  the user receives the review summary, actual test status, and remaining gaps.
