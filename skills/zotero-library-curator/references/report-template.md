# Zotero curation report template

The skill always emits a **preview plan**, never applies. If the report has 0 issues, emit a single OK line and stop instead of using this template.

```
## Zotero curation report (read-only)

**Library**: <library_id>  ·  **Items audited**: <N>

### Duplicate DOIs (<count>)
- 10.1234/abcd: 2 items (KEEP item ABC123, MERGE/TRASH XYZ456)
- ...

### Items missing required tags (<count>)
- KEY1: missing [research-hub, cluster/foo]
- ...

### Cluster/collection mismatches (<count>)
- KEY7: tagged cluster/foo but in collection bar
- ...

### Tag hygiene
- Near-duplicate tag candidates: agent-based-modeling (47) vs agent-based-modelling (3)
- Tags used once: ['hopf', 'sufficient', ...] (potential typos)

### Collection bloat
- "survey" collection has 237 items — consider splitting
- "benchmarking" has 8 items — consider merging

### Suggested follow-ups

> **Back up first.** In Zotero desktop: File → Export Library → Zotero
> RDF. Any modifications via `zotero-skills` or `research-hub zotero ...
> --apply` are irreversible without this snapshot.

1. Run `research-hub zotero backfill --tags --notes` to fix the 12 missing-tag items
2. Run `research-hub clusters rebind --emit` to review the 3 mismatches
3. Manually rename the 2 tag near-duplicates in Zotero desktop
4. Defer the bloat/sparsity questions to a human review session
```

The five report sections map 1:1 onto the five audit checks in `audit-checks.md`. Skip a section entirely if its check returned no findings.
