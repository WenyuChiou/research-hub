# NotebookLM SDK 0.8.5 compatibility

This review compares Hub source tree `9f6591035d3416238387c5e85cc200bd18ff7720`
(upstream commit `c0962c228c8a461931cd71ae30b27ae9b600e96f`) with the upstream
[`v0.8.5` release](https://github.com/teng-lin/notebooklm-py/releases/tag/v0.8.5)
(2026-10-12). The SDK is third-party software, not a Google-supported consumer API.
The version is an **upgrade candidate**, not a proven repair for a user's session.

## Relevant upstream history

- `0.4.1` (2026-05-11) predates the app-host migration.
- [`0.8.0`](https://github.com/teng-lin/notebooklm-py/releases/tag/v0.8.0)
  (2026-08-03) recognizes the new host during login;
  [`0.8.1`](https://github.com/teng-lin/notebooklm-py/releases/tag/v0.8.1)
  (2026-08-14) defaults to `notebook.google.com` and supports legacy-host cookies.
- [`#2479`](https://github.com/teng-lin/notebooklm-py/issues/2479) documents a
  signed-out HTTP-200 landing page without `SNlM0e`, not evidence that the signed-in
  token field was renamed. [`#2481`](https://github.com/teng-lin/notebooklm-py/pull/2481)
  distinguishes that state using the app's `/login` response routing.
- [`#2038`](https://github.com/teng-lin/notebooklm-py/issues/2038) explains why
  finding an accounts.google.com link anywhere in a page is not expiry evidence.

A missing-token `ValueError`, a browser title, or an old-to-new-host redirect
cannot establish the exact cause. A valid ordinary Chrome session also does not
establish validity of a separately saved SDK session. No private HTML or cookies
are needed for this compatibility review.

## Adapter matrix

| Boundary | SDK 0.8.5 finding | Hub action / offline evidence |
|---|---|---|
| Dependency range | Old `<0.5.0` excludes host/parser fixes | Pin exactly `0.8.5`; browser/cookie extras follow the SDK's actual extras; retain EZProxy's browser-cookie3 fallback |
| `from_storage(path, timeout, keepalive)` | Dual await/context protocol; legacy await remains supported until 1.0 | Real factory/open/close with synthetic loader and rejecting HTTP transport |
| Notebook/source CRUD, fulltext, chat | Hub-used signatures and return fields remain compatible | Bind real signatures; synthetic `Notebook`, `SourceFulltext`, `AskResult`, citations |
| Async generation/poll/download | Status types remain usable; immediate refusal raises; timeout is typed SDK error | Real poller, refusal/timeout/cancellation, exact artifact identity, failure/cache checks |
| Mind map | Returns `MindMapResult.note_id`, no longer a dictionary | Read typed note identity; real SDK parser with synthetic RPC/note persistence |
| Artifact test fixture | `ArtifactsAPI` is now abstract | Compose the real SDK client rather than instantiate the abstract base |
| Upload replay | SDK errors carry commit evidence or a retained source ID, including unwrapped file errors | Preserve non-replayability; synthetic response loss changed three calls to one |
| Cookie refresh | `AuthTokens.cookie_jar` is a bootstrap shadow | Remove direct shadow write; SDK `refresh_auth` owns serialized live-jar persistence |
| CLI storage binding | Root and login `--storage` have separate scopes | Bind both to the same target; real Click test forbids default-profile migration |
| Normal / `--auto-detect` login | SDK automatically captures; app host + SID is not live-auth proof | Delegate capture, then verify saved session through SDK notebook listing |
| `--wait-file` | SDK no longer waits for terminal ENTER | Reject before browser, profile, state or signal-file side effects; never auto-convert consent |

The signature checks do not invoke mutations or model generation. Tests exercise
Hub CLI/MCP/connector artifact paths with synthetic collaborators and blocked
external sockets. They are not live-provider acceptance tests.

## Operational boundary

See [normal login and the unsupported legacy gate](notebooklm.md#one-time-login).
No real login, private cookie extraction/injection, local-user SDK replacement,
headless re-authentication, CDP attachment, or new persistent grant is part of this
VM repair. Native acceptance should be a separate authorized step on the intended
installation; retain the original exception classification and version evidence,
and do not label an indeterminate token parse error as confirmed expiry.

Implementation references:
[`client.py`](https://github.com/teng-lin/notebooklm-py/blob/v0.8.5/src/notebooklm/client.py),
[`mind-map result`](https://github.com/teng-lin/notebooklm-py/blob/v0.8.5/src/notebooklm/_types/research.py),
[`token diagnostics`](https://github.com/teng-lin/notebooklm-py/blob/v0.8.5/src/notebooklm/_auth/extraction.py),
[`managed refresh persistence`](https://github.com/teng-lin/notebooklm-py/blob/v0.8.5/src/notebooklm/_web/transport/session_auth.py),
[`commit evidence`](https://github.com/teng-lin/notebooklm-py/blob/v0.8.5/src/notebooklm/outcomes.py),
[`login CLI`](https://github.com/teng-lin/notebooklm-py/blob/v0.8.5/src/notebooklm/cli/session_cmd.py).
