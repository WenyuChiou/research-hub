# WAGF Skills Brief

This brief defines the recommended skills for WAGF and explains how they should differ from `research-hub`, `academic-writing-skills`, and general AI coding skills.

## Executive Decision

WAGF skills should help researchers design, run, audit, and reproduce LLM-driven agent-based model experiments with governance. They should not be generic writing, Zotero, or literature-management skills.

The main user is a researcher who wants to answer:

- Does governance reduce invalid or hallucinated LLM actions?
- Does targeted retry improve agent decisions?
- How do governed and ungoverned LLM agents differ across models, seeds, and domains?
- Is the ABM correctly coupled to an external model?
- Can another researcher reproduce the experiment and audit trail?

## Product Boundary

Put a skill in WAGF if it depends on:

- WAGF domain packs.
- `skill_registry.yaml`.
- `agent_types.yaml`.
- `lifecycle_hooks.py`.
- Governance modes such as strict, relaxed, disabled, or ablation variants.
- Audit traces, rejection/retry logs, reasoning traces, or validation outcomes.
- ABM state transitions, memory engines, lifecycle hooks, or external model feedback.

Do not put a skill in WAGF if it is mainly about:

- Zotero, Obsidian, NotebookLM, or literature workspace management.
- Manuscript prose rewriting or journal formatting.
- General coding delegation to Codex or Gemini.
- Generic research note organization.

Those belong in `research-hub`, `academic-writing-skills`, `codex-delegate`, or `gemini-delegate-skill`.

## Recommended WAGF Skills

### 1. `wagf-domain-pack-builder`

Purpose: help a researcher create a new WAGF domain pack from a domain description.

Trigger examples:

- "Add a new WAGF domain for drought adaptation."
- "Create a domain pack for evacuation behavior."
- "Help me port WAGF to an energy demand ABM."

Inputs:

- Domain description.
- Candidate agent types.
- Available actions.
- Behavioral theory or decision constructs.
- Environment state variables.
- External model outputs, if any.

Outputs:

```text
domain_pack/
  skill_registry.yaml
  agent_types.yaml
  lifecycle_hooks.py
  README.md
```

Checks:

- Every action has preconditions.
- Every agent type has allowed actions.
- Every governance rule references an available construct.
- Lifecycle hooks do not mutate undocumented state.
- A minimal smoke test can instantiate the domain.

Non-goal:

- Do not invent scientific assumptions silently. Mark unknown domain rules as TODO.

### 2. `wagf-experiment-designer`

Purpose: convert a research question into a reproducible WAGF experiment matrix.

Trigger examples:

- "Design an experiment to test whether governance reduces hallucinated actions."
- "Compare strict vs relaxed governance across models."
- "Plan a cross-model WAGF ablation."

Outputs:

```text
.research/
  wagf_experiment_matrix.yml
  metrics_plan.md
  run_plan.md
```

Recommended matrix columns:

- Research question.
- Hypothesis.
- Domain.
- Model.
- Governance condition.
- Memory condition.
- Seed count.
- Years or time horizon.
- Agent count.
- Metrics.
- Expected artifact path.
- Statistical comparison.

Core metrics:

- Invalid action rate.
- Rejection rate.
- Retry success rate.
- Mean retries per decision.
- Logic-action gap.
- Governance effect size.
- Action distribution shift.
- Construct-action coherence.
- Runtime and cost.

Checks:

- Each research question maps to at least one metric.
- Each metric maps to an output artifact.
- Each comparison has both baseline and treatment conditions.
- Random seeds are explicit.

### 3. `llm-agent-audit-trace-analyzer`

Purpose: turn raw WAGF audit traces into paper-ready governance metrics and diagnostic tables.

Trigger examples:

- "Analyze these WAGF audit traces."
- "Compute governance metrics from JSONL logs."
- "Summarize rejection and retry outcomes by model and condition."

Inputs:

- JSONL or CSV audit logs.
- Experiment matrix.
- Optional agent metadata.

Outputs:

```text
analysis/
  governance_metrics.csv
  governance_summary.md
  rejection_taxonomy.csv
  retry_outcomes.csv
  model_condition_comparison.md
```

Required analysis:

- Count decisions by model, seed, condition, and domain.
- Compute invalid action rate.
- Compute rejection rate.
- Compute retry success rate.
- Compute mean and distribution of retries.
- Group rejected actions by validator and reason.
- Compare governed vs disabled or strict vs relaxed.
- Flag missing fields and malformed traces.

Paper-ready output:

- One short narrative paragraph.
- One metrics table.
- One caveats section.
- Reproducible command list.

### 4. `model-coupling-contract-checker`

Purpose: verify the contract between WAGF/ABM agents and external models such as flood, hydrology, irrigation, seismic, or catastrophe models.

Trigger examples:

- "Check whether my ABM is correctly coupled to this flood model."
- "Audit the external model feedback loop."
- "Verify units and time steps between WAGF and the CAT model."

Inputs:

- ABM state schema.
- External model input schema.
- External model output schema.
- Time-step definition.
- State mutation rules.
- Example run output.

Checks:

- Units are explicit and compatible.
- Time steps align.
- External model outputs are not used before they exist.
- State mutation direction is documented.
- Feedback loops do not double-count damage, cost, or exposure.
- Missing values and out-of-range values are handled.
- Randomness and seeds are documented.

Outputs:

```text
coupling_contract_report.md
coupling_schema_findings.yml
```

This is the most important skill for the user's research identity: LLM-driven ABM coupled with external models.

### 5. `abm-reproducibility-checker`

Purpose: verify that another researcher can reproduce a WAGF experiment.

Trigger examples:

- "Check whether this WAGF experiment is reproducible."
- "Prepare this experiment for paper submission."
- "Audit seeds, configs, outputs, and figure commands."

Inputs:

- `pyproject.toml` or `requirements.txt`.
- Experiment configs.
- Run scripts.
- Output directories.
- Figure generation scripts.
- README or paper methods section.

Checks:

- Environment is documented.
- Seeds are explicit.
- Commands are runnable.
- Data provenance is stated.
- Outputs match figure references.
- Temporary files are not required.
- Tests pass or known failures are documented.

Outputs:

```text
reproducibility_report.md
artifact_inventory.yml
missing_repro_steps.md
```

## Recommended WAGF Documentation

Add a docs page:

```text
docs/skills/wagf-skills.md
```

It should explain:

- Which skill to use for domain extension.
- Which skill to use for experiment planning.
- Which skill to use for audit trace analysis.
- Which skill to use for external model coupling.
- Which skill to use before paper submission.

## Suggested Directory Layout

```text
skills/
  wagf-domain-pack-builder/
    SKILL.md
    evals/evals.json
  wagf-experiment-designer/
    SKILL.md
    evals/evals.json
  llm-agent-audit-trace-analyzer/
    SKILL.md
    evals/evals.json
  model-coupling-contract-checker/
    SKILL.md
    evals/evals.json
  abm-reproducibility-checker/
    SKILL.md
    evals/evals.json
```

## Tests And Evaluation

Each skill should have at least 3 realistic eval prompts:

- One happy path.
- One messy real-world path.
- One near-miss where the skill should refuse to overclaim or ask for missing information.

Suggested test prompts:

1. Domain pack:
   "Create a WAGF domain pack for drought adaptation with farmers choosing irrigation reduction, crop switching, and insurance."
2. Experiment designer:
   "Design an ablation to compare governed vs disabled agents across Gemma, Claude, and GPT models with 5 seeds."
3. Audit trace analyzer:
   "Analyze these JSONL traces and report rejection rate, retry success, and logic-action gap by condition."
4. Coupling checker:
   "Check whether this flood-depth CSV can safely drive household adaptation decisions in an annual ABM."
5. Reproducibility checker:
   "Audit this WAGF experiment folder for missing seeds, configs, figure commands, and data provenance."

## Acceptance Criteria

WAGF skills are ready when:

- They do not duplicate research-hub or academic-writing skills.
- They produce concrete artifacts, not generic advice.
- They preserve scientific uncertainty and do not invent domain assumptions.
- They reduce repeated reading of configs, traces, and run logs.
- They make WAGF easier for an outside researcher to extend and reproduce.

## Recommended Implementation Order

1. Fix current WAGF test failures first.
2. Add `wagf-experiment-designer`.
3. Add `llm-agent-audit-trace-analyzer`.
4. Add `model-coupling-contract-checker`.
5. Add `abm-reproducibility-checker`.
6. Add `wagf-domain-pack-builder` after the domain-pack API is stable.

## Current Test Risk To Address First

Before promoting WAGF skills, fix the known local test failures:

- `tests/test_human_centric_memory_engine.py` expects string retrieval, while `HumanCentricMemoryEngine.retrieve()` returns dict payloads.
- `tests/test_gemma4_nw_crossmodel_analysis.py` expects `ibr == 0.25`, while current implementation returns `0.5`.

Resolve these before advertising WAGF as a stable researcher-facing framework.
