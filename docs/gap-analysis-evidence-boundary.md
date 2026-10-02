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
