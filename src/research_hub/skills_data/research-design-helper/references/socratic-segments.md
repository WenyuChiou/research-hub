# The 5 Socratic Segments

Run in order. After each segment, save the user's answers (verbatim) to the corresponding section of `.research/design_brief.md` (template: `design_brief_template.md`). If the user can't answer a segment yet, write `_TODO: <reason>_` and move on; do not fabricate.

## 1. Research question sharpening

Goal: turn a vague interest into a falsifiable RQ.

Ask:

- "What did you say you were studying, in one sentence?"
- "What would you observe if your hypothesis is FALSE? If you can't describe it, the question isn't sharp yet."
- "What's the smallest version of the question you could answer with a 1-week prototype?"

Output: `## 1. Research question` with the sharpened RQ + the falsification condition.

## 2. Expected mechanism

Goal: write down the causal chain BEFORE the experiment runs.

Ask:

- "Walk me through the mechanism: A causes B because of C; B then affects D through E."
- "Where in this chain are you most uncertain?"
- "If A → B → D is wrong, which intermediate step would you bet breaks first?"

Output: `## 2. Expected mechanism` with the chain + uncertainty annotations.

## 3. Identifiability check

Goal: confirm the experimental design CAN distinguish RQ-true from RQ-false. This is where most ABM / simulation studies silently fail.

Ask:

- "What experiment, dataset, or counterfactual would discriminate between your hypothesis and its main alternative?"
- "What confounders would you need to rule out?"
- "If your data can't tell the two apart, what's the minimum extra data you'd need?"

Output: `## 3. Identifiability check` with the discriminating condition + listed confounders + missing-data plan.

## 4. Validation plan

Goal: pre-commit to how the user will know the result is real.

Ask:

- "What metric quantifies success?"
- "What baseline are you beating?"
- "What's the negative control — a setup where you EXPECT the metric to NOT improve, and that confirms your method isn't just noise?"

Output: `## 4. Validation plan` with metric, baseline, negative control.

## 5. Risk register

Goal: list 3–5 specific things that would kill the design.

Ask:

- "What could go wrong with the data?"
- "What could go wrong with the model assumptions?"
- "What could go wrong with how you interpret the result?"
- "What's the most likely reason a reviewer would reject this study as currently designed?"

For each risk, also ask: "What would early-warning of this risk look like? What would you do?"

Output: `## 5. Risk register` with risks + early-warning + mitigation per row.
