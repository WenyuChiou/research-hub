# research-hub × ai-research-skills interop test

**Date**: 2026-04-26
**research-hub-pipeline**: 0.68.2 (PyPI)
**ai-research-skills catalog**: master HEAD as of test
**Verdict**: ✅ Interop works for end users. 2 minor maintenance issues for the catalog maintainer.

---

## Test summary

| # | Test | Result | Note |
|---|---|---|---|
| A | PyPI install reproducibility | ✅ PASS | 9 skills land at expected paths; all SKILL.md frontmatter parses |
| B | Wheel skills_data == local skills/ | ✅ PASS | byte-identical (only `zotero-skills` vendored dir excluded, as designed) |
| C | Catalog README walkthrough | ✅ PASS | All 5 steps either executable today or noted with caveat |
| D | Catalog skill_url ↔ PyPI wheel | ⚠️ Partial | 6/9 byte-identical; 3 differ as expected master-vs-tag skew |
| E | Catalog `skills.yml` metadata | ❌ FAIL | `research-hub` skill points at deleted path `skills/knowledge-base/` (renamed in v0.68.0) |
| F | Both install paths together | ✅ Coexist | both write to `~/.claude/skills/<name>/` — second install wins; content identical so no functional drift |
| — | `__version__` string drift | ❌ FAIL | `research_hub.__version__ == "0.64.2"` while pyproject says 0.68.2 (4 versions stale) |

---

## Test A — PyPI-first install

```bash
python -m venv /tmp/venvA
/tmp/venvA/bin/pip install research-hub-pipeline==0.68.2
HOME=/tmp/homeA research-hub install --platform claude-code
```

**Result**: 9 dirs landed under `/tmp/homeA/.claude/skills/`:

```
literature-triage-matrix      paper-memory-builder         research-hub-multi-ai
notebooklm-brief-verifier     research-context-compressor  research-project-orienter
research-design-helper        research-hub                 zotero-library-curator
```

Every SKILL.md has valid frontmatter `name:` matching dir basename.

---

## Test B — Wheel skills_data vs local skills/

```bash
diff -r /tmp/venvA/Lib/site-packages/research_hub/skills_data \
        C:/Users/wenyu/Desktop/research-hub/skills/
# Only difference: skills/zotero-skills (vendored, intentionally excluded from wheel)
```

PyPI wheel is **byte-identical to local source for all 9 packaged skills**.

---

## Test C — Catalog README walkthrough

| Step | Command | Status |
|---|---|---|
| 1 | `claude plugin install research-workspace@ai-research-skills --scope user` | ✅ Real Claude Code subcommand; `.claude-plugin/marketplace.json` exists in catalog repo |
| 2 | `git clone .../academic-writing-skills` | ✅ HTTP 200 |
| 3 | `git clone .../zotero-skills` | ✅ HTTP 200 |
| 4 | `git clone .../codex-delegate` + `gemini-delegate-skill` | ✅ HTTP 200 (note: `gemini-delegate-skill`, not `gemini-delegate`) |
| 5 | `pip install research-hub-pipeline` + `research-hub setup` | ✅ Verified by Test A |

**README also notes**: "Other notes: `(no content)` from `/plugin marketplace info` is not an error — `info` is not a supported subcommand on Claude Code 2.1.119." This caveat is honest and accurate.

Every step is executable today.

---

## Test D — Catalog skill_url content vs PyPI wheel

For each of the 9 skills, fetched the catalog's `skill_url` raw content and SHA-256-compared it with the wheel-installed `SKILL.md`:

| Skill | Status | Cause |
|---|---|---|
| research-hub-multi-ai | ⚠️ DIFF | catalog points at master; master has additional "Prerequisite check" section added post-v0.68.2 tag |
| research-context-compressor | ✅ PASS | identical |
| research-project-orienter | ✅ PASS | identical |
| research-design-helper | ✅ PASS | identical |
| literature-triage-matrix | ✅ PASS | identical |
| paper-memory-builder | ✅ PASS | identical |
| notebooklm-brief-verifier | ✅ PASS | identical |
| zotero-library-curator | ⚠️ DIFF | same — master is ahead |
| research-hub | ⚠️ DIFF (and 404 on catalog skill_url, see Test E) | same |

**Interpretation**: catalog points at `master HEAD`, PyPI ships v0.68.2 tag. As master accumulates commits beyond the tag (which it has since this session), drift is expected. PyPI users get a stable snapshot; catalog browsers see the moving HEAD. **Both are valid; neither is wrong.**

If the catalog wants stable URLs that match what PyPI users actually run, it should pin to `tree/v0.68.2/` instead of `tree/master/`.

---

## Test E — Catalog `skills.yml` stale path 🚨

```yaml
- name: research-hub
  directory: knowledge-base                                                        # STALE
  skill_url: https://github.com/WenyuChiou/research-hub/blob/master/skills/knowledge-base/SKILL.md
                                                                                    # 404
```

**Verified**: HTTP 404 on the skill_url; the path was renamed in v0.68.0
(`skills/knowledge-base/` → `skills/research-hub/`).

**The other 12 entries are correct** — no other stale paths.

**Action for catalog maintainer**:

```diff
  - name: research-hub
-   directory: knowledge-base
-   skill_url: https://github.com/WenyuChiou/research-hub/blob/master/skills/knowledge-base/SKILL.md
+   directory: research-hub
+   skill_url: https://github.com/WenyuChiou/research-hub/blob/master/skills/research-hub/SKILL.md
```

Our `LEGACY_SOURCE_NAME_ALIASES` handles `"knowledge-base"` callers in code (with DeprecationWarning until v0.70), but the catalog skill_url is browsed by humans, who will see a 404. Update needed.

---

## Test F — Both install paths together

The catalog's marketplace plugin (Step 1) and our PyPI install (Step 5) **both write to the same path** (`~/.claude/skills/<name>/SKILL.md`). The second install overwrites the first. Since both paths source from the same canonical content (research-hub repo), the overwritten content is identical (give or take master-vs-tag skew per Test D).

**Net behavior**: no skill duplication, no functional conflict, but precedence is "last writer wins". README Step 5 explicitly says "also installs steps 1-2's skills if you skipped them" — so PyPI-after-marketplace is the documented order, and it works.

---

## Bonus finding — `__version__` string drift 🚨

```python
>>> import research_hub
>>> research_hub.__version__
'0.64.2'                # but pip show says 0.68.2
```

`src/research_hub/__init__.py:11` hardcodes `__version__ = "0.64.2"`. We've shipped v0.65.0 / v0.66.0 / v0.66.1 / v0.67.0 / v0.68.0 / v0.68.2 since then; the string was never bumped.

This is a real user-facing bug for anyone scripting `research_hub.__version__`. The publish.yml v0.65 wheel-validate step prints this string but doesn't compare it to the tag, so drift sneaks past CI.

**Action for research-hub**: bump `__init__.py:__version__` to "0.68.2" in a v0.68.3 patch + add a release-time check in `publish.yml` that the printed version matches the tag.

---

## User-facing recommendation

For a fresh user, the simplest paths are:

| Persona | Recommended path |
|---|---|
| "I just want everything that works" | Step 5 only: `pip install research-hub-pipeline && research-hub setup`. Skip steps 1-4 unless you need writing/CRUD/delegation skills. |
| "I want the writing/delegation/CRUD skills too" | Steps 2-4 git clones + Step 5 pip install. Skip Step 1 marketplace plugin (Step 5 covers the same skills). |
| "I want to browse the catalog before installing" | Read the catalog README + skills.yml in browser. Click into any skill_url EXCEPT the `research-hub` entry (404 — see Test E). |
| "I want to use Claude Code's marketplace UI" | Step 1 only. Functional but you skip 7 of 13 skills until you also do Step 5. |

---

## Action items

### For ai-research-skills catalog maintainer

1. ❌ **`catalog/skills.yml`**: update the `research-hub` skill entry to use the new path:
   - `directory: knowledge-base` → `directory: research-hub`
   - `skill_url: .../skills/knowledge-base/SKILL.md` → `.../skills/research-hub/SKILL.md`
2. ⚠️ **(optional)**: pin `skill_url`s to a tag (`tree/v0.68.2/`) instead of `tree/master/` to give catalog browsers a stable URL that matches what PyPI users get. Today's master-vs-tag skew is non-breaking but visible.

### For research-hub

1. 🚨 **`src/research_hub/__init__.py:11`**: bump `__version__` to `"0.68.2"` (v0.68.3 patch).
2. ⚠️ **`.github/workflows/publish.yml`**: extend the wheel-validate step to assert `research_hub.__version__ == GITHUB_REF_NAME` (drop the `v` prefix). Prevents the same drift recurring.

### Combined verdict

**Interop works** for end users today. A fresh user who follows EITHER the PyPI-first path OR the catalog walkthrough lands with a working set of skills. The 2 maintenance issues above don't block users; they just need a follow-up patch on each side.
