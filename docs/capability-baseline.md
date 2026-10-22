# What works here, and what still needs checking

**M0 / 0A source baseline:** `6381dfa7d474dd27cd4adb33f0f59ea8ec395150`
(tree `7d0591077bff3ae815737b19a9f6d1958d78d958`, 2026-10-22).
PR #135 is merged. This is a capability inventory, not a release announcement.
Unknown or untested is **not ready**. Software tests do not establish scientific quality.

## Start without accounts

Follow the [pinned source installation](../README.md#workspace-preview) in a
new virtual environment (Python 3.10+). Dependency installation needs network
access; the demo itself needs no accounts, browser login, model, or Node runtime.

```sh
research-hub project demo --root ./workspace-demo --json
research-hub serve --workspace --root ./workspace-demo
```

Choose a **new or empty** demo directory. Open `http://127.0.0.1:8765/app/`.
The left project selector and header identify the current project; six page
names are navigation, not workflow stages. The older `dashboard --sample`
is a different literature dashboard, not this six-page workspace.

Do not use `setup`, `doctor`, search, login or upload as an offline smoke test:
they can inspect configuration, probe integrations or invoke external tools.
The isolated regression below only creates and inspects synthetic local data.

## Three different kinds of evidence

| Capability | Source checkout | Built / installed wheel | Native PC / AI host |
|---|---|---|---|
| Local project/demo, records, artifacts | Implemented in `workspace/`; regression below | Must test the exact wheel, not editable source | Must check actual command path and selected root |
| Six-page UI | `web/src/`; bundled `workspace_static/` | Existing wheel smoke checks served JS/CSS and REST parity | Browser navigation, language, focus and project switching need PC checks |
| CLI and shared services | `workspace/cli.py`, `workspace/service.py` | Verify installed entrypoint and module path | PATH may select a different install |
| MCP | `mcp_server.py`; optional `[mcp]` | Console script presence alone is insufficient; FastMCP must import | Host must load tools and schema; unit parity is not host discovery |
| Writing / connected Codex | Optional adapter and runtime checks exist | Package presence does not configure the producer | Exact trusted adapter, compatible CLI and authentication needed |
| Zotero / Obsidian / NotebookLM | Adapters exist | Dependency availability is not connectivity | Reads, exact write destinations, permission and recovery remain separate checks |

The source package declares version `1.2.0`, but that string alone does not
identify bytes or establish what a published wheel includes. Record the source
commit, wheel filename/SHA256, Python executable, installed module path and host
version separately. A wheel **built locally from this commit** is not a wheel
published to PyPI. Frontend asset hashes and backend provenance must agree;
the current UI does not expose a complete version/setup diagnostic panel.
The workspace SQLite schema is currently initialized with `CREATE TABLE IF NOT
EXISTS`, not a versioned migration ladder; do not invent a schema-version badge.

## Six pages: available actions, not an onboarding mockup

| Page | Existing UI actions | Boundary / missing path |
|---|---|---|
| Project | Create/select project; add question; view goal, activity, readiness and next-step suggestion | Suggestion uses record presence; not scientific assessment or automatic stage advancement |
| Literature | Search providers; add source metadata manually/from results; record inclusion/exclusion and rationale | Search is online. Adding a DOI/URL does not acquire full text or verify support. No guided connector setup/import-dedup wizard |
| Evidence | Add claim, link source IDs, record uncertainty; inspect verification/acceptance fields | Source link is not a verified quotation; no complete source-version/locator drawer |
| Design & results | Record question, method, result and limitation; register existing workspace files | Does not execute or validate a study; registration stores paths/hashes, not scientific approval |
| Manuscript | Register manuscript; add outline; use configured manuscript tools; inspect state/workflow; prepare task | Word/LaTeX edits remain in your editor; optional writing adapter required for its tools |
| Review & delivery | Prepare/run or export/import task handoffs; inspect results; cancel/recover where allowed; human decisions and local delivery actions | No automatic approval/publication. No complete attempt timeline or external-effect reconciliation UI |

The shared CLI/REST/MCP services expose related operations, but this does not
mean every CLI integration has a button. Setup, extras and connector login are
currently CLI/configuration steps. The UI readiness panel is not a full
per-connector setup report. Raw JSON inspection exists; richer source drawers,
recovery timelines and missing-prerequisite guidance remain future work.

## Bounded cloud checks

From a clean clone with test dependencies already installed:

```sh
PYTHONPATH=src python -m pytest -q tests/test_workspace_clean_baseline.py tests/test_workspace_demo.py
```

The clean-baseline test starts an isolated Python subprocess with a fresh HOME,
allowlisted environment, no user site, and a 20-second timeout. An audit guard
rejects socket operations, child processes and access to the original HOME
outside the explicitly selected source, interpreter and temporary-data roots;
regression checks exercise the guards. This is a bounded test fence, not an OS
sandbox. Source imports are pinned to this clone and data goes to a temporary
root. It neither installs dependencies nor claims connector/model readiness.

For a **built wheel**, reuse `scripts/workspace_install_smoke.py` and the
`workspace` job in `.github/workflows/ci.yml`: build, install in a fresh venv,
then run the smoke with that venv's Python. That existing smoke also requires
FastMCP and checks local HTTP assets and CLI/MCP/domain parity. It is not the
isolated source regression above or native-host acceptance. Record unrun checks
as unrun; do not replace wheel evidence with `PYTHONPATH=src` results.

## Native-PC acceptance (still required)

1. Record executable/module path and exact installation provenance; verify
   `research-hub project --help` and `serve --help` describe the intended entry.
2. Create a fresh demo root; confirm both DEMO projects and their warnings.
   Retry the same nonempty root: it must reject without overwriting files.
3. Open `/app/`, select each project and all six pages. Reload, use Back/Forward,
   switch language, keyboard navigation and a narrow window; confirm displayed
   project and records match. Version provenance remains a separate record.
4. With no writing adapter/model login, confirm unavailable/unchecked states
   are not shown as ready. Do not invoke live models to complete this check.
5. For MCP, separately inspect the actual host's loaded tool/schema list.
   For connectors, plan authorized reads and exact write destinations separately;
   this demo and a successful setup exit do not approve writes or uploads.

Rollback: revert these documentation/test changes; they change no application
schema, dependencies, connector permissions or existing user data.
