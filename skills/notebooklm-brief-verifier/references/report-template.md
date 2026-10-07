# NotebookLM brief verification report template

In-conversation report. The skill writes this to chat (no file by default). If reviewed source passages support the brief within the declared scope, the report is short — that's a feature, not a bug.

```
## NotebookLM brief verification report

**Brief**: <path>
**Bundle**: <cluster_slug> (<N> sources)

### Source coverage
- Mentioned in brief: <X> / <N> (mentions are screening signals)
- Not mentioned: <citation keys; assess whether omission matters>

### Attribution and support flags
- "<claim text>" (line <N> of brief) — unattributed; source support unassessed
- "<claim text>" — source passage checked; <unsupported / partial / unverifiable>
  with version, actual source level, locator and reason
- ...

### Cross-source contradictions
- "<claim A>" (cites Smith 2024) vs "<claim B>" (cites Jones 2023) — appear to contradict; brief does not flag this
- ...

### Potential overgeneralizations
- "Studies show..." — actually one paper, Smith 2024
- ...

### Source-checked claims
- Assessed / total claims: <X> / <N>; empty denominator: unavailable
- Unassessed load-bearing claims: <list>
- Version/access/source-level limits: <list>
- "<load-bearing claim>" — reviewed Smith 2024 §3, **supported**
- "<surprising claim>" — reviewed Jones 2023 abstract, **partially supported** (specific to coastal basins, not generalizable)

### Recommended follow-up NotebookLM prompts
- "What does Smith 2024 say about <X> specifically? Cite directly."
- "Compare Smith 2024's claim about <Y> with Jones 2023's findings."

### Verdict
- Completion: <partial / bounded-complete for the declared scope + rationale>
- Reliable for: <broad takeaways, comparison framing>
- Use with caution for: <specific numbers, generalizations>
- Do not cite without spot-check: <list>
```
