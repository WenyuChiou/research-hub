# Reference — Contribution-type classification (gap-to-topic §2)

> Method reference for the `gap-to-topic` skill, §2 Gate ② — classifying a
> candidate's contribution as problem-solving vs incremental (a descriptive
> lens, never a quality verdict).

## 1. Purpose

Gate ② asks *"is this a contribution?"* — the researcher's #1 bottleneck.
This component classifies a candidate topic's contribution as
**problem-solving** or **incremental**. It is a **lens for the §4 human
verdict**, not a gate that passes/fails a topic.

## 2. Input contract

| Input | Source | Shape |
|---|---|---|
| candidate | gap-to-topic §0 | `{gap_id, statement, type: A|B}` — `statement` is the articulated breakthrough point |
| `literature_matrix` | the `literature-triage-matrix` skill → `.research/literature_matrix.md` | table: `citation, year, method, data, claim, limitation, relevance` |
| dead-end evidence | the dead-end-history component (§2 sibling) | `dead_end_analysis` records keyed by `gap_id` (see that mini-design §7) |

## 3. Operational definitions

| Type | Definition | Test |
|---|---|---|
| **problem-solving** | Unlocks a capability that did not exist, or removes a limitation prior work **explicitly named** a blocker | "Does this make a previously-impossible class of work possible?" |
| **incremental** | Improves a metric, extends an existing approach to a new dataset / domain, or combines existing methods | "Is this *better / more / extended* on a task that already worked?" |
| **borderline** | See §5 — has a positive criterion, is not a catch-all |

**`incremental` is not "not worth doing."** Much incremental work is
valuable and publishable. The type is *descriptive*. The *worth* judgment is
the §4 human call — this component never makes it.

## 4. Classification signals

| Signal | Points to |
|---|---|
| Candidate claims a *first* — "enables X for the first time", "no prior method can" | problem-solving |
| Candidate removes a blocker that an on-topic paper **explicitly named** — cross-checked against dead-end evidence (§6) | problem-solving |
| Candidate claims *better / faster / more accurate* on an existing task | incremental |
| Candidate is "method Y applied to domain Z", Y and Z both pre-existing, no new capability claimed | incremental |

## 5. The `borderline` criterion (positive, not a relief valve)

`borderline` is emitted **only** when one of these holds — never as a
default for "hard to call":

- B1 — the candidate claims a new capability, **but** a weaker realised form
  of that capability already exists in prior work (partial novelty); or
- B2 — the §0 A/B type is itself ambiguous (the candidate reads as both a
  method-limitation and an application opening); or
- B3 — the candidate `statement` is too vague to classify — triggers the
  §8 refinement loop.

If none of B1–B3 holds, the component MUST commit to `problem-solving` or
`incremental`. "I am not sure" is not `borderline` — it is a `low`
confidence on a committed type.

## 6. Cross-check with dead-end evidence

The signal "removes an explicitly-named blocker" is only valid when the
cross-check holds, **all three**:

1. same `gap_id` in both records;
2. the dead-end record's `dead_end_status` is `dead-end-stale` or
   `partially-attempted` (a `genuinely-open` gap has no named blocker to
   remove; a `dead-end-fundamental` gap's blocker is the problem itself,
   not something a method removes);
3. for a `dead-end-stale` gap, the contribution justification cites the
   **same verbatim quote** the dead-end record nominated as its blocker
   evidence; for a `partially-attempted` gap (which has no single nominated
   blocker quote) it cites **any** of that gap's dead-end evidence quotes.

This ties the two components at the data level, not via prose.

## 7. Method + output schema

- The LLM assigns `contribution_type` **with a justification that cites
  evidence**. A bare type with no evidence is invalid output.
- **A/B counter-signal check (required).** The training distribution biases
  type-A → problem-solving and type-B → incremental. Before emitting, the
  LLM must explicitly state whether the candidate *falsifies* that default.
  For a type-B candidate the justification MUST state why the domain-novelty
  does or does not constitute a *new capability* (not just "new domain").
  An empty or absent `ab_counter_signal` field is invalid output (same
  enforcement as `quote_verified`).

```yaml
contribution_analysis:
  - gap_id: G1
    contribution_type: problem-solving      # | incremental | borderline
    confidence: high                        # see criteria below
    justification: "<one sentence, citing evidence>"
    ab_counter_signal: "<does the candidate falsify the default A/B mapping?>"
    evidence:
      - paper: "<citation>"
        basis: "explicitly names this as an open blocker"
        quote: "<verbatim>"
        quote_verified: true
    borderline_reason: "<B1 | B2 | B3 — only if type == borderline>"
```

**Confidence criteria (anchored — not LLM self-calibration):**

| Level | Rule |
|---|---|
| `high` | justification cites ≥2 independent papers with **direct** evidence |
| `medium` | cites 1 paper, or the evidence is indirect |
| `low` | classification is inferential, no direct evidence |

**Quote verification (required, shared with the dead-end component).** Every
`evidence.quote` must be confirmed to exist in the cited paper (fuzzy match);
unverified quotes are dropped, never shipped. `quote_verified` records it.

## 8. The §0 refinement loop (B3)

When the candidate `statement` is too vague to classify (`borderline`, B3),
the component does not just flag it — it emits a **structured refinement
request** back to §0:

```yaml
refinement_request:
  gap_id: G1
  reason: "statement does not say what capability is claimed"
  ask: "<one specific question for the researcher, e.g. 'does this enable
         a task that currently cannot be done, or improve one that can?'>"
```

§0 puts the question to the researcher; the sharpened statement re-enters
this component. **Termination:** at most 2 refinement rounds per gap; after
that the gap ships as `borderline` with the open question recorded — the
human resolves it in §4.

## 9. How it renders in the dossier

The researcher does not see raw YAML. §2 of the dossier shows, per gap: the
`contribution_type` as a **neutral label with its gloss** (problem-solving =
"unlocks a new capability"; incremental = "improves/extends existing work —
*this is not a quality judgment*"), the one-sentence justification, and the
evidence quotes. The "not a quality judgment" gloss on `incremental` is
mandatory at the display layer — it is where the human is most likely to
misread the label as an endorsement or a dismissal.

## 10. Multi-gap candidates

A candidate spanning gaps is decomposed by §0 into constituent `gap_id`s;
this component runs **per gap_id**. The dossier shows per-gap contribution
types; it does not average them into one verdict.

## 11. Open questions — with v1 defaults

- **Q1 (third type — `reframing / conceptual`).** v1 default: **two types +
  borderline** (Wenyu's stated distinction). Revisit after ≥20 real runs if
  reframing contributions are consistently mis-bucketed.
- **Q2 (A/B × type 2×2 view).** v1 default: **show the 2×2** in the dossier
  §2 layout — it is cheap and helps the researcher see the pattern.
- **Q3 ("what the field rewards" — venue norms).** v1 default: **out of
  scope** — needs a venue model. Recorded as a v2+ backlog item.
