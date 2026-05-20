# Authenticity guarantee

> **No fabricated references.** Every paper that enters your vault
> resolved to a real identifier, passed integrity and relevance
> checks, **or** was quarantined with a recorded reason and never
> written. This is mechanical and fail-closed — not a promise that
> depends on a model behaving.

## What this is — and what it deliberately is not

research-hub does **not** generate bibliographies with an LLM.
Discovery is **API-sourced** (18 backends: arXiv, Crossref,
OpenAlex, PubMed, Semantic Scholar, …), so a paper's existence and
metadata come from a real index, never a language-model
completion. The authenticity gate (`research_hub.authenticity`)
then verifies each candidate **before** it can enter `raw/`.

The honest, enforceable claim is:

> **resolve + integrity + relevance, or quarantine.**

It is **not** an absolute "zero hallucination" claim. We do not
assert a paper's *content* is correctly characterised, nor that a
resolvable DOI is the *best* source — only that every ingested
reference is a real, resolvable, integrity-checked item, and that
anything failing those checks is set aside with an auditable
reason rather than silently kept or silently dropped.

## The layers (L0–L5)

Every candidate runs the full ladder. A hard-fail at L0/L1/L3/L4
routes the paper to quarantine (it does **not** enter `raw/` or
Zotero); L2 is a provenance *label*, not a gate.

| Layer | Check | On fail |
|---|---|---|
| **L0** provenance | Has at least one identifier (DOI / arXiv / PMID / OpenAlex) | quarantine `no_identifier` |
| **L1** resolution | `doi.org` HEAD (real User-Agent, bounded retry) or arXiv/PMID resolver returns `<400`. Still **fail-closed** for the permanent class | **permanent** (404/410 → `*_unresolved`): quarantine `L1` — fabrication guard. **transient** (rate-limit/anti-bot/unreachable after retry → `*_check_unavailable`, PR-B): falls through to L2 / L3 / fit-check; if those all pass the paper is accepted with `provenance.doi_recheck_pending = True` (a future tool re-verifies the DOI when the publisher's anti-bot lifts), otherwise it's quarantined at the failing downstream layer — not at `L1-deferred`. The `L1-deferred` bucket is structurally empty post-PR-B; the `DEFERRED_LAYER` constant is preserved for downstream tooling/filtering. |
| **L2** corroboration | Cross-backend agreement on title/author/year (≥2 sources via `_records_agree`, OR `crossref` recorded as a backend). Single-source DOIs are augmented by a direct CrossRef `/works/{doi}` metadata verify (PR-A) that, on title/year/author match, records CrossRef as a verified backend. | **label-or-quarantine**: `corroborated` (label) passes; `single-source` quarantines `L2 / uncorroborated` unless exempt (real arXiv preprint / PMID / bioRxiv prefix / citation_count ≥ `min_corroboration_citations`). |
| **L3** integrity | Authors not truncated/anonymous, no mojibake, plausible year, venue sanity | quarantine `metadata_invalid` |
| **L4** relevance | `fit_check` LLM-judge score ≥ threshold. **Fail-closed:** no judge available ⇒ quarantine, never keep-all | quarantine `relevance_unjudged` / `low_relevance` |
| **L5** no-LLM-bibliography | *Invariant, not a per-paper step.* The bibliographic-frontmatter construction path must contain **no** LLM call | `test_authenticity_l5_invariant.py` fails CI |

Accepted papers carry a deterministic `provenance` frontmatter
block (`resolved_via`, `corroboration`, `doi_checked_at`,
`fit_score`) — the record is self-attesting and contains no
model-generated bibliographic field.

### Why L4 is fail-closed (the design choice)

Before v0.95.0rc2, a missing relevance judge meant **keep every
paper** (silent fail-open). That is exactly the failure mode this
guarantee exists to prevent. Now, with relevance checking on (the
default) and no `claude`/`codex`/`gemini` judge on PATH:

- `research-hub auto` **stops before the slow multi-backend
  search** with actionable guidance (Phase C) — you are told
  up-front, not after a long wait that ends in an empty vault.
- The **only** opt-out is the explicit, named `--no-fit-check`,
  which still runs L0/L1/L3 (identifier + resolution + integrity)
  — it disables the *relevance* filter only, never the
  authenticity checks.

There is no `--force-keep`, and no flag that silently writes
unjudged papers.

## When something is quarantined

Quarantine is **not** data loss. The full candidate payload, the
failing layer, and the reason are written to
`.research_hub/quarantine/`. Triage it:

```bash
research-hub quarantine list           # everything held + reasons
research-hub quarantine show <id>      # full JSON payload of one
research-hub quarantine restore <id>   # re-admit after you fix the cause
```

A short or empty vault after `auto` is therefore **auditable**,
not a mystery: the end-of-run summary names the reasons and points
you here. Typical causes and fixes:

| Reason | Meaning | Fix |
|---|---|---|
| `relevance_unjudged` | fit-check on, no LLM judge on PATH | install `claude`/`codex`/`gemini`, or re-run `--no-fit-check`, then `restore` |
| `doi_unresolved` | identifier did not resolve (`<400`) | usually a bad/typo DOI from a backend — inspect with `show`; restore if you can confirm it manually |
| `doi_check_unavailable` | resolver unreachable (offline/timeout) — fail-closed | re-run when network is back; `restore` the held items |
| `no_identifier` | no DOI/arXiv/PMID at all | genuinely unverifiable as-is; keep quarantined unless you can attach an identifier |
| `metadata_invalid` | truncated authors / mojibake / impossible year | inspect; restore only if the metadata is actually fine |

## Scope

- This guarantee covers papers ingested through `research-hub
  auto` / `import-folder` / the discover→ingest flow — i.e. the
  pipeline write path. Items you add to Zotero/Obsidian by hand
  are outside it.
- The gate is **upstream of the Zotero write**, so Zotero only
  ever receives accepted (real, resolved, integrity-checked)
  papers — there is no fabrication risk in the Zotero library
  either.

See also: [CHANGELOG](../CHANGELOG.md) (v0.95.0rc2 — the gate;
v1.0.0 — the guarantee), [docs/stable-api.md](stable-api.md).
