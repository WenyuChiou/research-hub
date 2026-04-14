# Vault Sync Audit - v0.26.0

## Per-cluster counts

| Cluster | Zotero | Obsidian | Dedup | Status |
|---|---|---|---|---|
| llm-agents-behavioral-science-environmental-interaction | n/a | 0 | 0 | OK |
| llm-agents-social-cognitive-simulation | n/a | 0 | 0 | OK |
| ai-agent-geopolitics-behavioral-patterns | n/a | 7 | 7 | OK |
| climate-migration-decision-modeling | n/a | 0 | 0 | OK |
| llm-agents-software-engineering | n/a | 20 | 20 | OK |

## Orphan clusters (no notes on disk)

llm-agents-behavioral-science-environmental-interaction
llm-agents-social-cognitive-simulation
climate-migration-decision-modeling

## Unknown raw/ folders (not in registry)

ABM-Theories
Behavioral-Theory
Benchmarking
Social-Simulation
general-reference
llm-agent
survey
traditional-abm

## Stale dedup paths

(none)

## Stale manifest cluster references

llm-harness-engineering

## Active drift alerts

| Kind | Cluster | Detail | Fix |
|---|---|---|---|
| folder_mismatch | C:\Users\wenyu\knowledge-base\raw\llm-agent\2505070872025-applying-cognitive-design-patterns.md | Some notes are stored under a different folder than their YAML cluster binding. | research-hub move 2505070872025-applying-cognitive-design-patterns --to <topic_cluster_value> |
| orphan_note | C:\Users\wenyu\knowledge-base\raw\ABM-Theories\2017-caillou-bdi.md | Some notes are unassigned and will be skipped by cluster-based tooling. | research-hub migrate-yaml --assign-cluster 2017-caillou-bdi |
| stale_manifest_cluster | llm-harness-engineering | manifest.jsonl contains entries for cluster slugs missing from clusters.yaml. | research-hub clusters list |

## Summary

- Total clusters: 5
- Clusters with drift: 0
- Total orphans: 3
- Recommended fix commands: research-hub clusters list, research-hub migrate-yaml --assign-cluster 2017-caillou-bdi, research-hub move 2505070872025-applying-cognitive-design-patterns --to <topic_cluster_value>
