# The 5 Socratic Segments

Run in order. After each segment, save the user's answers (verbatim) to the corresponding section of `.research/design_brief.md` (template: `design_brief_template.md`). If the user can't answer a segment yet, write `_TODO: <reason>_` and move on; do not fabricate.

Use field-appropriate prompts. Empirical data, hypotheses, causal mechanisms, predictive models and LLMs are not required. For theoretical, qualitative or descriptive work, ask about the evidence or argument that would answer the question; record `not-applicable` with a reason for genuinely inapplicable fields. Unresolved questions remain `_TODO_`.

## 1. Research question sharpening

Goal: turn a vague interest into an answerable RQ with explicit claim and time boundaries.

Ask:

- "What did you say you were studying, in one sentence?"
- "Is the target a future observation, a contemporaneous difference, a mechanism, a description, or another kind of claim? What population, setting and time period does the answer cover?"
- "If a hypothesis is part of the design, what would you observe if it is FALSE? Otherwise, what evidence or argument would challenge or revise your proposed answer?"
- "For a prospective claim or decision, what information is available at the decision time, and what only becomes available later? What outcome and observation horizon would answer the question? If time ordering is not relevant, why?"
- "What's the smallest version of the question you could still answer within your confirmed available resources and a justified timeline? What necessary materials and essential comparisons must remain? What would this smaller version explicitly NOT establish?"

Ask the user to choose any reduction in countries, periods, populations or objectives. Do not impose a fixed duration, treat prototype success as feasibility, drop an essential comparator or assume unknown costs are zero. If materials or resources are unconfirmed, record the limitation and a bounded next check rather than calling the version executable.

Output: `## 1. Research question` with the sharpened RQ, claim/time boundary, falsification or revision condition, and smallest answerable version including explicit nonclaims and resource limits.

## 2. Expected mechanism

Goal: write down the proposed mechanism or argument before evaluating it, where applicable.

Ask:

- "If you are making a causal claim, walk me through the mechanism: A causes B because of C; B then affects D through E. Otherwise, what reasoning or conceptual structure supports the proposed answer?"
- "Where in this mechanism or argument are you most uncertain?"
- "If it is wrong, which step or assumption is most vulnerable?"

Output: `## 2. Expected mechanism` with the mechanism or argument + uncertainty annotations; explain any `not-applicable` causal fields.

## 3. Identifiability check

Goal: identify what the proposed evidence or argument can distinguish, and what it cannot establish.

Ask:

- "What experiment, dataset, counterfactual, proof or interpretive evidence would distinguish the proposed answer from its main alternative?"
- "What confounders or competing explanations would you need to address?"
- "If your current materials cannot distinguish them, what minimum extra evidence would you need, and can it actually be obtained?"
- "If you have only two observation occasions, what bounded between-occasion change can they support, and what remains unknown between or beyond them? Do not infer a full trajectory from two occasions alone."
- "If using a vignette, which responses or judgments in that scenario can you study? What would be needed to generalize to observed behavior, future outcomes or real-world mechanisms? A vignette alone does not establish those claims."

Output: `## 3. Identifiability check` with the discriminating condition, competing explanations, missing-material plan and design-specific inference limits. Unavailable necessary outcomes/materials require a bounded check or a user-chosen revision; importance of the question does not remove that constraint.

## 4. Validation plan

Goal: specify how the user will assess the answer and whether any improvement is worth its cost.

Ask:

- "What metric or field-appropriate assessment criterion would support the intended claim?"
- "What baseline or relevant comparison tests that claim? If comparison is not applicable, why?"
- "For a capability comparison, do the candidate and baseline have matched available variables, information time, data splits and planned resources? Disclose and correct information asymmetry before attributing a gain to capability. If the research question explicitly concerns the value of extra information, what extra information is being compared and how will its cost be accounted for?"
- "What minimum worthwhile gain or reduction in uncertainty would change knowledge or a decision, and is it worth the added cost? Use a justified quantitative threshold or qualitative criterion appropriate to the field. If undecided, leave `_TODO_`; do not invent a fixed percentage or a statistical-significance requirement."
- "Where a negative control is applicable, what setup should not show the proposed gain, and which alternative explanation would it test? If it is not applicable, what limitation or other check should be recorded?"

Matching means making comparison conditions explicit and appropriate to the question, not silently adding a stronger baseline or changing the research objective. A method's unmeasured benefit is not itself a reason to reject a question when necessary materials and a comparison path are available; it also does not demonstrate improvement.

Output: `## 4. Validation plan` with assessment criterion, comparator, matched-information conditions (or a justified extra-information comparison), minimum worthwhile gain, incremental cost and applicable controls. Mark inapplicable data splits or model-specific fields with a reason rather than inventing an empirical/LLM design.

## 5. Risk register

Goal: list 3–5 specific things that would kill the design.

Ask:

- "What could go wrong with the necessary materials or their availability?"
- "What could go wrong with the model assumptions or argument, as applicable?"
- "What could go wrong with how you interpret the result?"
- "What's the most likely reason a reviewer would reject this study as currently designed?"

For each risk, also ask: "What would early-warning of this risk look like? What would you do?"

Carry forward any selected-candidate review limitations, including stale bindings, unknown materials, contradictory assessments and unconfirmed resource estimates. Preserve the supplied reasons and next checks; do not turn a structurally valid review into scientific approval.

Output: `## 5. Risk register` with risks + early-warning + mitigation per row.
