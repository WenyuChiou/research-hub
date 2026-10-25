# Private SQLite source UI integration (reconstructed)

This integrates the new parked-recovery/source-label UX reconstruction with the separately recovered, hash-verified private SQLite backend. It does not restore lost private UI code, migrate workspaces, or enable a CLI/public API feature. Public WorkspaceService remains file-backed; only explicit Python private service construction advertises experimental BLOB storage.

The UI accepts version-1 exact `workspace_blob` descriptors bound to artifact ID, project and source-record ID, supported text format, byte length and hash. Unknown descriptors never fall back to a made-up path. BLOB previews require the exact `hub-source:<record>` reference, descriptor, format, bytes/count and hash; file previews retain the legacy path contract. Source choices exclude BLOBs belonging to another record/project; labels join exact source/artifact identity and show operator scope/local-save date, not publication date. References render as inert text, not filesystem or navigation links.

Byte selection still maps normalized textarea CRLF/UTF-16 ranges to the original Unicode text (including BOM/non-BMP characters). Prepare remains explicit, and Run is never implied by preview/recovery. Profile3 task review uses the selected passage and exact return source identity. Generic metadata carries no BLOB contents; preview/selected task passage are explicit reads.

Opaque pending identities and parking semantics are unchanged. Parking never cancels server work, deletes an unresolved key, posts or retries. Explicit separate intent does not reuse the old payload/key. Exact old results remain checkable and cannot take over newer navigation. A known resolved record inserted into the matching cached project can open even while bulk refresh fails or hangs; only then may its pending identity be cleared.

Verification: actual private-service synthetic fixture generator plus direct assertions, offline DOM integration and existing regression suites. Optional provider availability probes are explicitly stubbed unavailable; no providers execute. No server/browser/native acceptance: prior VM Chromium socket EPERM and Windows HTTP10013 remain blocked and were not retried. No public release or scientific/human acceptance is claimed.

## Retained CI service/admission regressions

`tests/test_workspace_sqlite_contract.py` is collected by the existing default
pytest jobs. It uses real temporary SQLite workspaces and direct service/handler
calls: exact UTF-8 bytes/replay/read-only lookup, metadata non-disclosure, selected
profile 3 and legacy profile 2, corrupt/unknown storage rejection, project scope,
private-only constructor selection, five insert/commit failure boundaries, and
Origin/CSRF/per-request human-proof admission. Optional capability probes are
explicitly unavailable; sockets, subprocesses and file publication are forbidden.
All patches are restored after each test. Direct handler calls are **not** HTTP
transport, browser, native-platform or real-provider acceptance. These tests do
not replace the separately recorded installed stdio and historical HTTP proofs.
