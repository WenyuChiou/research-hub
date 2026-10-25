# Combined workspace browser gate

This extends the existing `scripts/workspace_browser_smoke.py`; it does not add a
second application or browser framework. The fixture helper is
`scripts/workspace_browser_fixtures.py`. All data is synthetic, inside the
smoke's temporary workspace. No user vault, credentials, provider, external
writing adapter or destination write is needed. The runner-availability response
is explicitly mocked and **every Run request is intercepted before dispatch**.

## Assertions

- Actual registered UTF-8 source preview and actual Prepare HTTP/SQLite save:
  source ID, artifact ID, selected-only text and codepoint offsets match despite
  CRLF and an astral character. Selection uses the browser textarea's selection
  API/event, not a forged Prepare request; it is not native keyboard acceptance.
- Overview opens the exact prepared task; Review returns to the same source,
  distinct from an unselected source. Selected text remains available.
- An intercepted uncertain Run response stays locked through identical ready
  refresh and a failed project refresh followed by Retry. Exactly one Run
  request is intercepted; there is no real dispatch or execution result.
- A real Prepare save's response is withheld until the user navigates elsewhere.
  Its late response cannot replace newer navigation; explicit task return goes
  to the second selected source.
- Two synthetic human-decision fixtures use the abstract operation and genuine
  backend freshness. Changing/deleting one generated candidate revokes its
  selection while another remains selected. Historical acceptance remains
  visible; no approval/delivery request or action is created.
- Request counts, a final screenshot and existing trace/page-error reporting
  accompany results. The report labels mocks and synthetic decisions.

## Running later

The existing `workspace` CI job already builds the frontend, installs its
declared test tooling and runs:

```sh
python scripts/workspace_browser_smoke.py --output artifacts/browser
```

In an already provisioned isolated local environment, use that same command
against this exact checkout with the built assets and existing Playwright
Chromium. It binds only an ephemeral loopback server. Do not disable the
browser sandbox or change security settings to force a launch.

The VM preparation deliberately does **not** launch Chromium. Offline fixture
preflight is separate:

```sh
PYTHONPATH=src python -m pytest -q tests/test_workspace_browser_fixtures.py
```

Preflight proves fixture construction, selected-only source binding, and actual
backend stale/unknown behavior, not browser interaction. Browser assertions
remain unexecuted until the existing CI or an authorized isolated browser host
runs this exact revision.

## Boundaries

Only existing registered evidence text is in scope; this is not zero-source
ingestion, PDF reading, a full paper-summarize workflow, semantic evaluation or
external delivery. Transient refresh errors preserve current-project inputs and
uncertain actions, but unknown Prepare outcomes still lack authoritative
idempotent reconciliation. Full close/reopen persistence is not established.
Synthetic acceptance is not a person's research judgment. Native zoom,
screen-reader, Windows and human usability acceptance remain separate gates.
