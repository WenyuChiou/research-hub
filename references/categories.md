---
title: Research Categories & Classification Reference
description: Category definitions, keyword lists, graph colors, sub-category mappings, and WIKI_MERGE dictionary
---

# Research Categories & Classification Reference

## Research Categories and Graph Colors

Each paper is assigned a `category` field that determines its color in the Obsidian graph view. Claude uses LLM-based classification (reading title + abstract) rather than keyword matching to assign categories. The keyword lists below are retained as reference for the `categorize_graph.py` script.

| Category | Graph Color | Reference Keywords |
|----------|-------------|-------------------|
| `flood-abm` | Blue | flood, insurance, NFIP, buyout, ABM, disaster, hazard, resilience, vulnerability, agent-based, FEMA, sea level, coastal, evacuation, watershed, climate change, managed retreat |
| `llm-agent` | Green | LLM, large language model, GPT, generative agent, multi-agent, prompt, transformer, deep learning, neural network, RAG, chain of thought, autonomous agent, active inference, dual process |
| `social-behavior` | Orange | social capital, place attachment, community, equity, environmental justice, norms, trust, governance, governed broker, GBF, collective action, migration, displacement, diversity |
| `methodology` | Purple | ODD protocol, SEM, structural equation, statistical, benchmark, evaluation, framework, review, meta-analysis, validation, regression, factor analysis, psychometric |
| `wiki` | Red | hub topic pages (auto-assigned) |
| `projects` | Yellow | Project pages (auto-assigned) |
| `survey` | Teal | Survey/questionnaire-based research papers |
| `traditional-abm` | Amber | Traditional agent-based model papers (not LLM-based) |
| `general-reference` | Default | Papers that do not match any other category (fallback) |

## Method-Type Classification Details

Classification is based on Claude's reading of the paper's **title**, **abstract**, and **Zotero collections**:

| Method Type | Typical Characteristics |
|-------------|------------------------|
| `survey` | Uses questionnaires, stated preferences, surveys, interviews, household surveys, conjoint analysis, discrete choice experiments |
| `traditional-abm` | Builds/uses traditional ABM (NetLogo, Repast, Mesa), cellular automata, microsimulation, ODD protocol ??NOT LLM-powered |
| `llm-agent` | Uses or studies LLMs, AI agents, generative agents, prompt engineering, RAG, chain of thought |

Chinese collection names added by classifier:
- `survey` ??collection "隤踵"
- `traditional-abm` ??collection "?喟絞ABM"
- `llm-agent` ??collection "LLM隞??"

## LLM-Based Classification (Primary Method)

When saving a paper, Claude reads the abstract and classifies using its own judgment:

1. Read the paper's title and abstract (via `read_*_paper` tools)
2. Determine the best-fit `category` and `method-type` based on content understanding
3. Do NOT rely solely on keyword matching ??understand the paper's actual research focus
4. **Special case**: "A Survey of LLM Agents" is a review paper about LLMs, NOT a questionnaire survey. Claude's judgment handles this naturally.
5. If classification confidence is low, note this and ask user to confirm

## Keyword Reference (for categorize_graph.py)

**flood-abm** also matches these collections: ABM, Flood-Simulation, Survey, survey paper, Literature Review, Study area, introduction, Paper1b_NatureWater, RQ2-Institutional-Feedback, WAGF-Paper, vehicle, LR

**llm-agent** also matches these collections: LLM AI agent, Reflection, Generative-Agents, Memory-and-Cognition, RQ1-Memory-Heterogeneity, Active-Inference, RQ3-Social-Information, WRR_WAGF_2026_Intro, WRR-Technical-Report

**social-behavior** also matches these collections: GBF, Governed Broker Framework, 01-Theoretical-Foundations

## Sub-Category Folder Mapping

Papers are filed into sub-category folders under `raw/`. This table shows the full path mapping:

| Major Category | Sub-Category | Folder Path |
|---------------|-------------|-------------|
| Survey | Risk-Perception | `raw/Risk-Perception/` |
| Survey | Insurance-Adoption | `raw/Insurance-Adoption/` |
| Survey | Evacuation | `raw/Evacuation/` |
| Survey | Social-Capital | `raw/Social-Capital/` |
| Traditional ABM | Flood-ABM | `raw/Flood-ABM/` |
| Traditional ABM | Insurance-Market | `raw/Insurance-Market/` |
| Traditional ABM | Socio-hydrology | `raw/Socio-hydrology/` |
| Traditional ABM | Urban | `raw/Urban/` |
| LLM ABM | Consumer-Simulation | `raw/Consumer-Simulation/` |
| LLM ABM | Game-Theory | `raw/Game-Theory/` |
| LLM ABM | Social-Simulation | `raw/Social-Simulation/` |
| LLM ABM | Benchmarking | `raw/Benchmarking/` |

If a sub-category folder does not exist, create it before writing the .md file.

## WIKI_MERGE Dictionary (Collection Name Normalization)

The `build_hub.py` script normalizes duplicate or misspelled Zotero collection names:

```python
WIKI_MERGE = {
    "Agent-Based Model": "ABM",
    "agent-based model": "ABM",
    "Agent-Based Modeling": "ABM",
    "Soical capital": "Social Capital",
    "Social norm/ Social capital": "Social Capital",
    "Soical Vulnerability": "Social Vulnerability",
    "Study area": "Study Area",
    "study area": "Study Area",
    "Flood insurance": "Insurance & Risk Transfer",
    "Insurance": "Insurance & Risk Transfer",
    "survey": "Survey Methods",
    "survey paper": "Survey Methods",
    "LR": "Literature Review",
    "SM": "Social Media",
    "SEM": "Structural Equation Modeling",
    "Buoyout": "Buyout Programs",
}
```

If new duplicates or misspellings appear, add them to this dictionary and re-run `build_hub.py`.

## Topic Map for Hub Pages

| Hub Topic | Keywords | Description |
|-----------|----------|-------------|
| Agent-Based-Modeling | agent-based, ABM, DYNAMO, agent based, multi-agent | Agent-based modeling approaches for simulating human behavior |
| Flood-Insurance | flood insurance, NFIP, insurance, premium, Risk Rating | NFIP, premium structures, and insurance market dynamics |
| Flood-Risk | flood risk, flood inundation, flood fragility, coastal flood, flood model | Flood risk assessment, modeling, and management |
| LLM-Agents | LLM, large language model, generative agent, GPT, AI-driven, AI agent | LLM applications in agent simulation and decision-making |
| Place-Attachment | place attachment, community attachment, neighborhood attachment | Emotional bonds to places influencing disaster response |
| Social-Vulnerability | social vulnerability, racial inequity, environmental justice, equity | Social vulnerability and environmental justice in disasters |
| Managed-Retreat | managed retreat, buyout, relocation, acquisition | Voluntary buyouts and post-disaster relocation |
| Disaster-Preparedness | preparedness, mitigation, risk perception, protective action | Household preparedness and protective behavior |
| Climate-Adaptation | climate change, adaptation, sea level rise, resilience | Climate adaptation strategies and resilience building |
