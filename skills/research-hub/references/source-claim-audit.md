# Source and claim audit v1

Screen cheaply, then verify the evidence that carries a decision. A DOI lookup,
famous remembered result, citation mention, generated note, or NotebookLM brief
is a discovery lead, not a source-supported finding.

## Minimum audit record

For each load-bearing claim, retain:

1. packet/source and claim IDs; bibliographic work ID and specific publication
   version (or explicitly unknown); acquisition/tool reference and source URL
2. actual material reviewed: metadata, abstract, generated summary, located
   full-text excerpt, or unavailable; source/access and identity judgments
3. saved raw and extracted-text SHA-256 where available; exact quote with
   character range plus section/page locator; source-fetch receipt if used
4. verifier reference; supported, partial, contradicted, or unverifiable
   judgment; applicable population/conditions and uncertainty

Identity, source availability, publication version, and semantic claim support
are distinct judgments. A located abstract cannot upgrade identity or become
full text. Raw byte hashes identify a captured artifact, not the journal/preprint
version, authentic publisher origin, or semantic support. Publication version
needs a documented version review; unknown versions cannot establish same-version
support. Quote presence only proves binding, not entailment or adequacy.

Read the relevant methods, results, limitations, supplement, figure/table, or
correction for decision-relevant detail. The abstract + first pages + conclusion
may suffice for screening but is never a universal full-paper reading protocol.
Never report `Read full PDF` unless that actually occurred. Say which sections
were read and which remain unchecked. If a fourth load-bearing source remains
beyond an approved read/spot-check bound, explicitly leave it unassessed; do not
imply all claims were audited after three spot-checks.

Supported abstract claims remain useful at their actual narrower scope. Narrow
claim wording when evidence is partial; retain contradictions and conditions.
Unattributed claims, missing citation mentions, and nearby apparently opposing
sentences are screening flags, not final support/contradiction verdicts. Compare
the underlying passages before making those judgments.

## Optional executable source-audit profile

For substantive reviews needing local binding checks, keep an optional
`research-source-audit/1.0` sidecar alongside the unchanged strict
`ResearchEvidencePacket` v1. Do not add properties to the v1 packet or change
its status enums. The profile's `partial`/`unverifiable` assessments describe
remaining limits; the packet retains its existing vocabulary. Use `unverified`
(or `mixed` when actually mixed) until packet wording and all required support
are justified.

Before using the optional kwargs, probe the **installed runtime**, not just its
version string. A skill/plugin update does not replace an already installed
Python wheel; the proposed source wheel and an older published wheel can both
report `1.2.0` while exposing different capabilities.

```bash
python - <<'PY'
import inspect
from importlib.resources import files
from research_hub.evidence_harness import validate_evidence_packet
parameters = inspect.signature(validate_evidence_packet).parameters
available = {"source_audit", "artifact_root"} <= parameters.keys()
available = available and files("research_hub").joinpath(
    "schemas/research-source-audit-1.0.json"
).is_file()
print("source-audit/1.0 available:", available)
raise SystemExit(0 if available else 1)
PY
```

If this probe fails, do not call unsupported kwargs or present packet-only
validation as source binding. Preserve manual/native source review and label
mechanical source-audit validation unavailable for that runtime. Available
native discovery remains usable. A tested proposed source build does not imply
publication or installation of a new runtime; those are separate approved steps.

Production validation, **only after that probe passes**, is:

```python
from pathlib import Path
from research_hub.evidence_harness import validate_evidence_packet
findings = validate_evidence_packet(
    packet, source_audit=profile, artifact_root=Path("./evidence"),
)
```

The schema is `research_hub/schemas/research-source-audit-1.0.json`; the Python
validator uses local files only and never fetches a source. Each observation
records work/publication version, actual level/status, raw/text hashes and
paths, and an optional existing source-fetch result. Source-fetch bundles are
replayed with the production receipt validator before use. Native captures are
allowed without source-fetch receipts but provide weaker provenance; identify
them as native captures rather than implying receipt replay or publisher proof.
Paths must stay inside the supplied artifact root. A supported assessment binds
the current packet hash, packet source/claim/verifier IDs, known version,
required evidence level, exact quote/range, and saved bytes. Every claim is
assessed or explicitly listed as unassessed; an unassessed claim cannot be
marked supported. Revalidate after a source, version, or decision changes.

The profile is optional: legacy packet-only callers retain v1 validation.
A packet-only pass means structural/status consistency, never source-passage
verification. A profile pass additionally proves local binding consistency,
never scientific sufficiency, source authenticity, complete coverage, novelty,
or submission readiness. Human source/semantic review remains required.
