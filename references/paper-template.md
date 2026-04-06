# Paper Note Template

Use this template when creating a new paper .md file in the `raw/` directory.
Copy everything below the horizontal rule and fill in the fields.

## Instructions

1. Replace all placeholder text (in angle brackets or parentheses) with actual values.
2. The filename should be a URL-safe slug of the paper title: lowercase, hyphens for spaces, no special characters.
   Example: `inducing-state-anxiety-in-llm-agents.md`
3. All YAML frontmatter fields should be filled in. Leave `zotero-key` empty if the paper has not yet been saved to Zotero.
4. Choose `category` from: `flood-abm`, `llm-agent`, `social-behavior`, `methodology`, `general-reference`.
5. Choose `method-type` from: `survey`, `traditional-abm`, `llm-agent`, or omit if none apply.
6. Add at least one `[[Wiki Link]]` to a relevant topic page.

---

## Template

```markdown
---
title: "<Paper Title>"
authors: "<Author1; Author2; Author3>"
year: <YYYY>
journal: "<Journal or Conference Name>"
doi: "<10.xxxx/yyyy>"
zotero-key: "<ZOTERO_ITEM_KEY or empty>"
collections: ["<Collection1>", "<Collection2>"]
tags: ["<tag1>", "<tag2>", "<tag3>"]
category: "<flood-abm|llm-agent|social-behavior|methodology|general-reference>"
method-type: "<survey|traditional-abm|llm-agent>"
---

# <Paper Title>

## Summary
<Brief summary of the paper's main contributions and findings. 2-3 sentences.>

## Key Findings
- <Finding 1>
- <Finding 2>
- <Finding 3>

## Methodology
<Brief description of the research methods, data sources, sample size, and analytical approach. 2-4 sentences.>

## Relevance
<Why this paper matters for your research. How it connects to your current projects. 1-3 sentences.>

## Wiki Links
- [[<Related-Theory-Page>]]
- [[<Related-Topic-Page>]]
```

---

## Category Selection Guide

Scan the paper's title and abstract for these keyword patterns:

| If the paper mentions... | Use category |
|--------------------------|-------------|
| flood, insurance, NFIP, ABM, disaster, hazard, resilience, coastal, FEMA | `flood-abm` |
| LLM, language model, GPT, generative agent, transformer, prompt, AI agent | `llm-agent` |
| social capital, place attachment, equity, norms, trust, governance | `social-behavior` |
| ODD protocol, SEM, statistics, review, meta-analysis, validation | `methodology` |
| None of the above | `general-reference` |

## Method-Type Selection Guide

| If the paper's research approach is... | Use method-type |
|----------------------------------------|----------------|
| Questionnaire, stated preference, survey instrument, interviews | `survey` |
| Traditional ABM (NetLogo, Repast, Mesa — NOT LLM-powered) | `traditional-abm` |
| Uses or studies LLMs, AI agents, generative agents | `llm-agent` |
| Does not fit any of the above | Omit the field |
