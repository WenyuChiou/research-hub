# Research follow-up sidecar (optional candidate)

`research_hub.followup` provides a pure-data, versioned sidecar for recording a
bounded follow-up to an existing candidate. It does not change the direction
review packet, its thresholds, the Stage2 evidence schema, or the workflow's
existing retry budget. It does not search, call a model/tool, write files, or
grant execution permission.

## Binding and attempt history

Format: `research-followup-sidecar/1.0`.

The current sidecar binds the complete candidate using the existing
`direction_review.candidate_sha256` helper, and binds a canonical evidence
snapshot plus the material missing-evidence list. Each attempt record preserves
the material missing-evidence entries and binds the candidate ID/version/hash,
evidence snapshot hash, missing-evidence hash, and canonical action hash.
Attempts remain in supplied chronological order; records with prior
candidate/evidence bindings are retained as historical and do not count toward
the current repeat check.

Attempt outcomes are distinct: `success`, `empty`, `failed`, and `unavailable`.
A success requires at least one evidence reference but is only a recorded
outcome, not scientific support. Empty results carry no evidence or failure
code. Failed/unavailable attempts carry a failure code and cannot carry claimed
evidence. The caller must refresh the evidence snapshot when the source evidence
changes.

Validation reconstructs the record against current candidate, evidence,
missing-evidence, and resource-cost inputs. A changed candidate, version,
evidence snapshot, missing-evidence record, resource-cost record, or digest
mismatch returns `record_status: unknown`; callers must not treat it as current
evidence. Hashes bind canonical bytes; they are not signatures or source
authenticity attestations. Call validation with the current candidate, evidence
snapshot, material missing-evidence list, and resource-cost record.
Unknown resource cost stays `unknown`; this helper does not estimate costs or
change budgets.

Repeat detection is deliberately narrow. It compares canonical action records
for exact identity under an unchanged candidate/evidence/missing-evidence
binding. It can flag an identical action after an empty, failed, unavailable, or
no-new-reference result. It does not detect semantic equivalence between
different natural-language requests. A flag does not authorize or forbid a
retry; `execution_authorized` and `additional_retry_authority_granted` remain
false, and no action is run. The sidecar reports the exact-match comparison
basis so callers do not mistake it for semantic-equivalence detection.

## Dashboard integration boundary

The Dashboard does not currently expose a selected research candidate or its
current evidence, missing-evidence, and resource-cost snapshot. The direction
review CLI requires explicit dossier, review, and source-root paths; its inputs
are not selected by the Dashboard. The follow-up validator also requires those
current inputs from its caller. A sidecar's self-reported candidate reference
and hashes cannot identify which candidate is active or prove that the supplied
evidence is current.

Until an existing project-selection interface supplies that binding, the
Dashboard must not load a sidecar in isolation or render its attempt history as
current. A missing or stale binding is `unknown`; an unselected sidecar is not
an active candidate. A later read-only card must receive the active dossier,
validated direction-review evidence, material missing-evidence list, and
resource-cost record from one authoritative project context, then call
`validate_followup_sidecar` against those inputs before displaying attempts.
It must not infer candidate eligibility, human selection, or execution
authority from the sidecar.

## Source and licensing provenance

Design reference only: `WenyuChiou/AutoResearchAgent` at commit
`00055fdb20069526446c963d3804a5c5424024dd`, especially
`plugins/auto-research-agent/cli/stage2_workflow/orchestration.py`
(`make_followup`) and
`plugins/auto-research-agent/cli/stage2_live/research_followups.py`.
Those files motivated version/evidence-bound attempt history, distinct outcome
states, and no-progress stopping. This Hub helper is an independent
implementation: no ARA source code was copied, imported, or vendored. The ARA
revision's `LICENSE` is Apache License 2.0 and its `NOTICE` names OpenAI Codex
and Ratatui; neither file is relicensed or represented as MIT-only here. The
Hub repository's own MIT license remains unchanged.

This is an optional code-level helper and an un-packaged user-facing skill is
not modified; there is no `skills_data` mirror to update for this addition.
