# Literature-Review Deliverable — Format Specification

The research-hub literature pipeline — `search`, `literature-triage-matrix`,
and `research-design-helper` — each produces a *fragment* of research
output. Run them end to end on one topic and the fragments add up to a
single consolidated document — a **literature-review deliverable**.

This file specifies that deliverable's standard shape so the output is
predictable, reusable, and machine-checkable across runs. It is a format
spec, not a skill: the skills produce the parts; this document defines how
the parts assemble.

A complete worked example (fully synthetic) lives in the catalog repo:
[`ai-research-skills/docs/example-literature-review-deliverable.md`](https://github.com/WenyuChiou/ai-research-skills/blob/main/docs/example-literature-review-deliverable.md).

---

## 1. The pipeline

```
search                   → candidate papers (multi-backend)
  ↓ triage                 drop off-topic / no-abstract; fix the corpus
literature-triage-matrix  → .research/literature_matrix.md  → §2 §3 §4
research-design-helper    → .research/design_brief.md       → §5 §7
  ↓ consolidate
literature-review deliverable (9 sections + 2 companion files)
  ↓ quality gate           accuracy / consistency / honesty / mirror parity
  ↓ render                 Markdown + Word, English + a second language
```

Each skill's own output is an intermediate artifact; the deliverable is the
human-facing synthesis of all of them.

**`paper-memory-builder` is not a literature-review step.** It operates on a
user's *own manuscript draft*, not on the cited corpus. If the reader is
also drafting a manuscript on this topic, `paper-memory-builder` (run on
that draft) produces `.paper/claims.yml`; a `status: gap` claim there can
then be cross-linked from §5 of the deliverable. The linkage is optional —
a literature review stands on its own without it.

## 2. The 9-section contract

Every literature-review deliverable has exactly these nine sections, in
order. Each section has a fixed contract — what it must contain.

| # | Section | Contract |
|---|---|---|
| 1 | **TL;DR** | 3–6 bullets: headline findings, the main disagreement, the sharpest gap. A reader who stops here still knows what to do next. |
| 2 | **Literature inventory** | One row per source: ID, citation, year, evidence type (empirical / conceptual), relevance grade + one-line reason. |
| 3 | **Per-paper summary** | Per source: question · method · sample · findings · author-acknowledged limitation · how to use it. See §5 below for the summarization contract. |
| 4 | **Cross-paper synthesis** | What the corpus agrees on; where it disagrees (name the papers); low-evidence sources flagged. Disagreements are surfaced, never smoothed over. |
| 5 | **Research gaps** | Each gap = statement + evidence it is a gap + what would close it. Gaps are tagged `[G1]…[Gn]`. A gap may optionally carry a `.paper/claims.yml` claim ID when a manuscript draft has been built for the topic (see §1). |
| 6 | **Open questions** | Questions the corpus cannot answer that affect gap prioritization. Distinct from gaps: a gap is closable by a defined study. |
| 7 | **Recommended next step** | The single highest-leverage study the gaps point to, concrete enough to start. One paragraph + a scope line. |
| 8 | **References** | Full, resolvable references — arXiv ID / DOI + URL at minimum, ordered by ID. |
| 9 | **Provenance & limitations** | How the deliverable was produced + honest caveats (see §6). A deliverable without this section is not trustworthy. |

Sections 1–8 each carry a one-line `>` italic contract note in the rendered
file, so the deliverable doubles as a reusable blank template.

## 3. Companion files

Alongside the 9-section Markdown (and its rendered `.docx`), every
deliverable ships two machine-readable companions:

### `<name>.bib` — BibTeX export of §8

A standard BibTeX file. Two ways to produce it:

- **Vault-ingested corpus** — use the built-in exporter:
  `research-hub cite --cluster <slug> --format bibtex --out <name>.bib`.
- **Ad-hoc search corpus** (papers not yet ingested) — generate directly
  from the search-result metadata (DOI / arXiv ID / authors / title / year),
  which already carries every field BibTeX needs.

### `<name>.gaps.yml` — structured export of §5 + §6

So a later pass can list every open research question across deliverables
without re-parsing prose.

```yaml
deliverable: <name>
topic: "<one-line topic>"
generated: "YYYY-MM-DD"
corpus_size: <int>
evidence_grade: screening-grade-triage
gaps:
  - id: G1
    statement: "<one sentence>"
    evidence: "<which papers fail to cover it>"
    closes_via: "<what study would close it>"
    linked_claim: <claims.yml C-id or null>
    status: open
open_questions:
  - id: Q1
    text: "<question>"
```

## 4. The summarization contract (§3)

Per-paper summaries are the deliverable's highest-risk section — it is where
fabrication creeps in. The rules:

- **Fixed fields per paper:** research question · method · sample · key
  findings · author-acknowledged limitation · how to use it.
- **Quantify only what the source quantifies.** If the abstract gives a
  number, transcribe it exactly; if it does not, write *"not specified in
  abstract"* — never infer, round, or soften (`~40%` for an exact `40%` is
  a defect).
- **Abstract-only by default.** Unless full text was fetched, summaries are
  built from abstracts; §9 must disclose this.
- **Relation to the `paper-summarize` skill.** `paper-summarize` fills
  per-cited-paper *Key Findings / Methodology / Relevance* blocks into
  Obsidian + Zotero notes. The deliverable's §3 is a tighter, triage-grade
  summary aimed at one review. They are complementary: `paper-summarize`
  enriches the vault; §3 condenses for the deliverable. Both obey the same
  no-fabrication rule.

## 5. Honesty rules

- **§9 is mandatory.** It states how the corpus was assembled, the evidence
  grade, and what is missing.
- **Screening-grade, not systematic.** Unless a reproducible query with
  formal inclusion/exclusion criteria was run, the deliverable is a
  screening-grade triage; recall is unknown and §9 must say so.
- **Search-recall caveat.** Different query phrasings surface different
  papers; if the corpus is a union of partial searches, §9 says so.
- **No fabricated identifiers.** Every arXiv ID / DOI in §8 and the `.bib`
  must resolve. A synthetic example must mark itself synthetic and use
  obvious placeholder identifiers.

## 6. Bilingual + formats

- **Markdown + Word.** The deliverable ships as `<name>.md` and a rendered
  `<name>.docx`.
- **Two languages.** An English deliverable and a mirror in the working
  language (e.g. `<name>.zh-TW.md`). In the non-English mirror, section
  prose is translated, but paper titles, author names, citation
  identifiers, numbers, claim IDs, gap tags, and the entire §8 References
  list stay in the original language (standard academic practice).
- **Mirror parity.** The two language versions must agree on every section
  count, paper ID, gap tag, claim ID, and number.

## 7. Reuse

The rendered deliverable is also a blank template: keep the section
structure and the `>` contract notes, replace the content. The companion
files (`.bib`, `.gaps.yml`) and the second-language mirror are part of the
standard bundle — a deliverable is the set
`{md, <lang>.md, docx, <lang>.docx, bib, gaps.yml}`.
