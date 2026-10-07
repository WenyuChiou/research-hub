# What `paper gaps` can establish

`paper gaps --cluster <slug>` (and `--compare <other>`) synthesizes condensed
local paper notes. It does not execute an external literature search, read the
original full papers, validate publication versions or decide scientific novelty.
A corpus coverage difference is not evidence that nobody has done a study.

The prompt distinguishes local coverage differences, unresolved evidence/scope,
source-supported narrow candidates and unsupported novelty. Zero justified
directions is valid. A candidate needs source passages/version locators,
closest-work overlap and difference, significance, contrary/dead-end evidence
with applicability conditions, and an operational upgrade/kill test. Citation
count and publication age do not exclude a relevant closest work. Topic worth
remains the researcher's and advisor's decision.

## Files and compatibility

The existing reader-facing paths and result objects remain unchanged:

- Single cluster: `hub/<slug>/research-gaps.md` (`GapResult`)
- Cross cluster: `hub/_cross-cluster/<a>-x-<b>-gaps.md` (`CrossClusterGapResult`)

Each write also saves two local companions alongside that file:

- `<stem>-model-output.txt`: the exact UTF-8 model response, including whitespace
- `<stem>-context.json`: consumed note locators/raw-byte hashes, actual note
  material level, recorded publication version, display truncation, source
  observations and original research provenance. Its assessment is always
  `unassessed`, scientific validation `not-performed`, and external coverage
  unknown. This is a preservation snapshot, not a new evidence-validation schema.

The Markdown report starts with a writer-controlled provisional boundary. Model
prose stays under an unverified-draft heading and is never copied into a new
overview teaser. Overview updates retain existing text. Existing sections are
qualified only when this writer's boundary marker or the exact legacy generated
analysis-link marker identifies ownership; ambiguous user-written sections remain
unchanged. Repeated writes do not duplicate owned overview notices/links.

Existing positional writer calls continue to work. The optional `digest=` and
`digests=` keyword arguments let callers bind the snapshot consumed by the model;
the CLI supplies these before writing. Without them, direct callers snapshot the
current local notes at apply time. A changed note after prompting does not replace
the CLI's consumed snapshot. Failed note reads stay recorded as unknown evidence;
an entirely unreadable corpus does not invoke the model.

The ResearchEvidencePacket v1 schema/status enums and gap-to-topic handoff enums
are unchanged. Neither this context nor a packet/source-audit structural pass
certifies source authenticity, semantic sufficiency, complete recall or novelty.
For decision-level work, use the existing
[source-claim audit](../skills/research-hub/references/source-claim-audit.md),
[research protocol](../skills/research-hub/references/research-protocol.md), and
[gap-to-topic](../skills/gap-to-topic/SKILL.md) workflow. Recorded note metadata is
not independently verified source evidence. Paywalls, truncation, conflicting
versions, HTTP 429 and unknown counts remain unknown rather than zero results.

## Verification limits

Offline fixtures execute digest construction, both prompts, direct writers, and
actual CLI handlers with mocked model output, including unsafe novelty prose.
They verify preservation, writer qualification and overview behavior. They do
not establish that a real model follows the prompt or that any scientific gap is
true. No real model/API call or private research data is needed for these checks.

## Preliminary direction checks and user choice

Candidates can improve an existing method/design or propose a new concept. A
paper need not explicitly name the gap. Separate sourced premises, inferences
and untested expected benefits; the effect to be measured is a research question.
Preliminary review asks what observation/derivation/comparison can answer it,
what claims that check cannot establish, whether actual variables/granularity
and data access fit, and whether a minimum study/baseline/validation fits confirmed
resources. This writer validates none of these scientific judgments.

Unknown enabling data/access or lack of an informative test needs a bounded next
check, never an invented numeric zero or a score offset by value. Keep alternatives;
revise substantive mismatches, park critical unknowns and reject only with
supported negative evidence. Eligibility is not selection, including a sole
`go`/`conditional-go` candidate. The design-helper conversational handoff uses an
actual prior user choice if clear, otherwise asks before pre-filling a brief.
No new runtime selection gate, scoring engine or handoff enum is introduced.

The executable CLI tests establish preservation and writer qualification only.
Selection changes in `research-design-helper` are conversational skill guidance;
their documentation/fixture tests do not establish that a live model always asks
or follows that guidance. A clear prior user choice is reused without asking again.

## Optional offline direction record check

`paper direction-check --dossier <path> --review <path> --source-root <root>
--json` is a separate, config-free local reader. It checks an opt-in candidate
version/content binding, evidence bytes/record shape and arithmetic over supplied
planned resource components. It does not call models or the network, write or
repair files, or change how `paper gaps` generates and preserves provisional
prose. See the [direction-review contract](direction-review-contract.md) for the
complete input/output shapes and failure reasons.

The optional `gaps[].candidate_version` and independent review JSON leave the
existing writer, context snapshot, ResearchEvidencePacket v1 and handoff enums
unchanged. Legacy dossiers remain readable in the ordinary flow; the new checker
reports `missing-candidate-version` rather than treating one as version 1. The
complete reviewed candidate is hashed separately from the raw dossier receipt,
so another candidate's edit alone does not stale an unchanged candidate.

All seven prerequisite kinds can contain multiple checks. Their supplied
`supported`, `contradicted`, `unknown` or `not-applicable` statuses remain supplied
assessments, not validator conclusions. A concrete locator and matching source
bytes do not prove passage meaning, authenticity or publication version. An
explicit unknown publication version stays metadata even when bytes are current.
Existing context note locators/hashes and source observations must be preserved;
the checker does not upgrade a note to the original paper. Changed or unavailable
evidence makes the binding noncurrent without rewriting an assessment.

Resource totals combine only the explicitly reviewed set and declared units.
Shared work requires explicit scope and sharing basis; missing basis, required
demand, estimate or capacity leaves unknown rather than an invented zero or
discount. `within-estimate` compares supplied quantities only. Runtime usage,
omitted work and real affordability are not verified. No currency/unit conversion,
automatic scope reduction, budget approval or runtime enforcement is introduced.

Exit 0 means a structurally valid/current report completed, even with unknown or
contradicted checks or an `exceeds-estimate` result. Consumers must inspect the
named fields, including `record_status`, `binding_status`, `prerequisites` and
`resource_estimates`; they cannot use exit success as research approval. Reports
retain `semantic_assessment: not-performed`, `human_selection: outside-checker`,
`execution_authorized: false` and `runtime_budget_verification: not-performed`.
Offline checker tests establish parsing, binding and supplied arithmetic only;
they do not establish scientific adequacy, actual human choice or live model
compliance with either skill's conversational guidance.
