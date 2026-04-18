# User personas

research-hub is built for four user types. Each works with a different combination of Zotero / Obsidian / NotebookLM and a different mix of source kinds. v0.34 added test coverage for all four (`tests/test_v034_persona_matrix.py`).

| Code | Persona | Zotero | Obsidian | NotebookLM | Primary source kind |
|---|---|---|---|---|---|
| **A** | PhD STEM (default) | ✅ | ✅ | ✅ | Academic papers (DOI / arXiv) |
| **B** | Industry researcher / consultant / founder | ❌ | ✅ | ✅ | Local PDFs, market reports, internal docs |
| **C** | Humanities PhD | ✅ | ✅ | 🟡 light | Books, archived articles, URL-only sources |
| **H** | Internal knowledge management (lab / company) | ❌ | ✅ | ✅ | Mixed PDF / Markdown / DOCX / web pages |

v0.38 expanded `--persona` from 2 values to 4: `researcher | humanities | analyst | internal`. The dashboard auto-adapts vocabulary, hides irrelevant tabs (Diagnostics for analyst/internal), and skips features that don't apply (Bind-Zotero button, compose-draft, citation graph) per persona.

## v0.38 dashboard preview by persona

Same vault, four different rendered dashboards. Note the changing vocabulary, tab set, and feature visibility:

| Persona | Vocabulary | Hidden tabs | Hidden features | Screenshot |
|---|---|---|---|---|
| **researcher** | Cluster / Crystal / Paper | (none) | (none) | [`dashboard-overview-researcher.png`](images/dashboard-overview-researcher.png) |
| **humanities** | Theme / Synthesis / Source | (none) | (none) | [`dashboard-overview-humanities.png`](images/dashboard-overview-humanities.png) |
| **analyst** | Topic / AI Brief / Document | Diagnostics | Bind-Zotero, compose-draft, citation graph, Zotero column | [`dashboard-overview-analyst.png`](images/dashboard-overview-analyst.png) |
| **internal** | Project area / AI Brief / Document | Diagnostics | Same as analyst | [`dashboard-overview-internal.png`](images/dashboard-overview-internal.png) |

Run `research-hub init --persona <choice>` to set; `research-hub doctor` warns if persona is unset.

---

## Persona A — PhD STEM (the default)

**Who:** PhD students and researchers in CS, ML, biology, physics, etc. Daily reader of arXiv. Maintains a Zotero library + an Obsidian vault for structured notes.

**Tools:** All three.

**Typical pipeline:**
```
research-hub discover new --cluster X
  → emit fit-check prompt → AI scores → filter
research-hub add 10.48550/arxiv.NNNN.NNNNN --cluster X
research-hub label X --add core
research-hub crystal emit --cluster X > prompt.md
  → feed to AI → save crystals.json
research-hub crystal apply --cluster X --scored crystals.json
research-hub ask X "what is the SOTA"   # v0.33 task wrapper
```

**Why research-hub helps:** crystals collapse "what's this cluster about?" from 30 KB of abstract reads to 1 KB of pre-computed answer (~30× token reduction).

**Tested by:** every test file in `tests/` uses Persona A by default.

---

## Persona B — Industry researcher / consultant / founder

**Who:** People working at companies, consulting firms, or startups who do research-heavy work (competitor analysis, market mapping, due diligence) but don't use academic infrastructure (Zotero is overkill; papers don't have DOIs).

**Tools:** Obsidian + NotebookLM. **No Zotero.**

**Typical pipeline:**
```
research-hub init --persona analyst   # one-time
mkdir ~/q2-research && drop PDFs into it
research-hub import-folder ~/q2-research --cluster q2-research   # v0.31
research-hub crystal emit --cluster q2-research > prompt.md
  → AI answers → research-hub crystal apply
research-hub ask q2-research "what are the main themes"   # v0.33
research-hub notebooklm bundle --cluster q2-research
research-hub notebooklm upload  # via Playwright + CDP
research-hub notebooklm download  # pulls AI-generated brief back
```

**Why research-hub helps:** unified ingest path for any source kind (v0.31's `import-folder`); same crystal + brief workflow as PhD students get; doesn't force you to fake DOIs for internal docs.

**Tested by:** `tests/test_v034_persona_matrix.py::test_B_*` (5 tests covering dashboard rendering, ask_cluster fallback, sync recommendations, collect_to_cluster routing).

---

## Persona C — Humanities PhD (quote-heavy)

**Who:** Researchers in literature, history, philosophy, sociology. Fewer "papers", more books / book chapters / archived essays. URL-based references (Project MUSE, JSTOR scans, online archives) as common as DOIs. Quote capture is central to the workflow.

**Tools:** Zotero + Obsidian. NotebookLM is occasional (briefings less central; quote-by-quote work matters more).

**Typical pipeline:**
```
research-hub add https://example.org/foucault-lecture --cluster discourse-analysis
research-hub quote add foucault-lecture \
  --page 14 \
  --text "Power is everywhere... not because it embraces everything, but because it comes from everywhere."
research-hub quote list --cluster discourse-analysis
research-hub compose-draft --cluster discourse-analysis \
  --outline ~/draft-outline.md \
  --max-quotes 10
research-hub cite foucault-lecture --style chicago
```

**Why research-hub helps:** quotes are first-class objects (not buried in paper notes); compose-draft assembles structured drafts pulling cluster overview + quotes + citations; sync_cluster keeps an eye on cluster scope drift even for non-DOI sources.

**Tested by:** `tests/test_v034_persona_matrix.py::test_C_quote_capture_with_url_source`.

---

## Persona H — Internal knowledge management

**Who:** Lab leads, R&D teams, internal-tools developers, anyone running a private "company wiki on steroids". Mixed source types: vendor PDFs, internal `.md` rituals, Word reports, web archives, occasional Zotero items.

**Tools:** Obsidian primary; NotebookLM for AI summaries; **no Zotero** (sources don't live there).

**Typical pipeline:**
```
research-hub init --persona analyst
research-hub import-folder /shared/drive/team-docs --cluster team-onboarding \
  --extensions pdf,md,docx,url
research-hub clusters analyze --cluster team-onboarding --split-suggestion
  # citation graph not useful here; falls back to keyword overlap
research-hub topic build --cluster team-onboarding
research-hub notebooklm brief --cluster team-onboarding   # via brief_cluster wrapper
```

**Why research-hub helps:** unified ingest of mixed source types; sub-topic auto-split (works on non-citation content via keyword overlap); same dashboard + crystals + briefings the academic users get.

**Tested by:** `tests/test_v034_persona_matrix.py::test_H_*` (3 tests covering mixed source kinds, ask_cluster on internal docs, dashboard render).

---

## Choosing your persona at install time

```bash
# Persona A (default — Zotero + Obsidian + NotebookLM)
research-hub init

# Persona B / H (no Zotero, Obsidian + NotebookLM)
research-hub init --persona analyst
```

You can switch anytime by re-running `init --reconfigure` and choosing the other persona. Existing data isn't touched.

---

## Per-persona feature matrix

| Feature | A | B | C | H |
|---|---|---|---|---|
| `add <DOI>` | ✅ | ✅ (no_zotero) | ✅ | ✅ (no_zotero) |
| `import-folder` (v0.31) | ✅ | ✅ critical | ✅ | ✅ critical |
| `discover new` | ✅ critical | 🟡 less common | 🟡 | ❌ rarely |
| `quote` + `compose-draft` | 🟡 | 🟡 | ✅ critical | 🟡 |
| `crystal emit` / `crystal apply` | ✅ critical | ✅ | ✅ | ✅ |
| `ask_cluster` (v0.33) | ✅ critical | ✅ critical | ✅ | ✅ critical |
| `sync_cluster` (v0.33) | ✅ | ✅ | ✅ | ✅ |
| `notebooklm bundle/upload/generate/download` | ✅ | ✅ critical | 🟡 | ✅ |
| `clusters analyze --split-suggestion` | ✅ | 🟡 (no citations) | 🟡 | 🟡 (no citations) |
| Dashboard live mode | ✅ | ✅ | ✅ | ✅ |
| Obsidian graph color-by-label | ✅ | ✅ | ✅ | ✅ |
| MCP server (Claude Desktop, Codex, etc.) | ✅ | ✅ | ✅ | ✅ |

✅ = primary use case · 🟡 = secondary · ❌ = rarely useful for this persona

---

## See also

- [docs/import-folder.md](import-folder.md) — Persona B/H entry point
- [docs/anti-rag.md](anti-rag.md) — why crystals work for all 4 personas
- [docs/task-workflows.md](task-workflows.md) — `ask_cluster` and friends (v0.33+)
- `tests/_persona_factory.py` + `tests/test_v034_persona_matrix.py` — test coverage source of truth
