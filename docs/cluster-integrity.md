# Cluster Integrity

Cluster integrity checks protect the mapping between:

- cluster registry entries in `.research_hub/clusters.yaml`
- raw source files under `raw/<cluster>/`
- quotes stored in `.research_hub/quotes/`
- rebind proposals that repair folder drift without guessing blindly

The v0.37-A + v0.37-B work adds two things:

- doctor checks for common failure modes
- a persona-aware test matrix covering all 4 supported personas

## Failure modes

### 1. Missing bound folder

Symptom:
- cluster exists in the registry
- `obsidian_subfolder` points to a directory that no longer exists

Doctor check:
- `check_cluster_missing_dir`

Common cause:
- cluster renamed in the registry without moving the folder

Mitigation:
- rebind the cluster to the actual folder
- or move the folder to match the registry binding

### 2. Orphan raw folders

Symptom:
- markdown files exist under `raw/<folder>/`
- that folder is not bound to any cluster

Doctor check:
- `check_cluster_orphan_papers`

Common cause:
- `import-folder` used without `--cluster`
- ad hoc manual folder creation

Mitigation:
- bind the folder to an existing cluster
- or run cluster rebind and review the proposals

### 3. Empty clusters

Symptom:
- cluster exists in the registry
- bound folder exists
- no papers are inside it

Doctor check:
- `check_cluster_empty`

Common cause:
- placeholder clusters created during planning
- papers moved away but registry entry left behind

Mitigation:
- delete the cluster if unused
- or ingest/import papers into it

### 4. Cross-tagged notes

Symptom:
- a note lives under one cluster folder
- its frontmatter points at another cluster

Doctor check:
- `check_cluster_cross_tagged`

Common cause:
- manual editing
- partial moves between clusters

Mitigation:
- fix frontmatter to match the folder
- or move the note into the correct bound folder

### 5. Orphan quotes

Symptom:
- quote references a `paper_slug`
- no bound paper exists for that slug

Doctor check:
- `check_quote_orphan`

Common cause:
- deleted or renamed note
- humanities/archive capture outside the bound cluster structure

Mitigation:
- restore the paper note
- or update/remove the orphaned quote

### 6. Rebind ambiguity

Symptom:
- files exist outside any bound cluster
- the system can only infer a destination heuristically

Repair tool:
- `research-hub clusters rebind --emit`
- `research-hub clusters rebind --apply`

Signals used:
- explicit `cluster:` frontmatter
- Zotero collection key matches
- folder names and related metadata

Mitigation:
- prefer explicit cluster metadata where possible
- review medium/low-confidence proposals before applying

## Persona matrix

| Persona | Typical risk | Strongest signal | Recommended mitigation |
|---|---|---|---|
| **A: PhD STEM** | Folder drift after cluster evolution | `cluster:` frontmatter, Zotero collection key | Use rebind proposals and preserve collection bindings |
| **B: Industry analyst** | `import-folder` dumps into unbound folders | Bound destination folder | Import with `--cluster` or bind imported folders quickly |
| **C: Humanities** | Quotes captured for non-DOI or archive sources | Quote slug + note existence | Audit quote orphans regularly and keep source notes stable |
| **H: Internal KM** | Mixed-doc folders renamed manually | Registry binding vs folder path | Run doctor after reorganizing folders or vendor docs |

## Operational guidance

- Run `research-hub doctor` after any bulk rename, folder import, or manual vault move.
- Use `clusters rebind --dry-run` first when recovering orphan folders.
- Treat warnings as real drift, not cosmetic noise. They usually indicate missing recall paths for MCP or dashboard flows.
- Persona B and H are more likely to hit orphan-folder issues because they rely on local document imports instead of Zotero bindings.
- Persona C is more likely to hit quote-orphan issues because paper identifiers are often URL or archive based rather than DOI based.

## Related docs

- [User personas](personas.md)
- [Import folder](import-folder.md)
- [Cluster memory](cluster-memory.md)
