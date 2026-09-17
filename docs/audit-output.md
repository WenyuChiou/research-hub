# Search attempt audit files (version 1.0.0)

Add `--audit-output NEW_DIRECTORY` to `search`, `enrich`, `verify`,
`references`, or `cited-by`. The directory must not already exist. Existing
stdout, stderr and exit behavior stay compatible when the option is absent.
With auditing, malformed response shapes are reported conservatively instead
of being accepted as empty collections.

```sh
research-hub search "synthetic example query" --backend openalex,crossref --json --audit-output runs/example-search
research-hub references 10.5555/synthetic --json --audit-output runs/example-references
```

Use ordinary `init`/configuration setup first. Audit output is independent of
the vault's ingestion manifest. Each invocation gets a new directory; callers
decide whether to retry and link separate invocations in their own run ledger.

## Public contract

The CLI option, file names and
[`audit-v1.schema.json`](../src/research_hub/schemas/audit-v1.schema.json) are
stable public surfaces. `research_hub.audit` and instrumentation helpers are
internal implementation details, not public Python imports. This addition
does not create a second MCP research implementation.

| File | Meaning |
| --- | --- |
| `events.jsonl` | Append-only UTF-8 attempt starts and finishes, in contiguous sequence order |
| `artifacts/<id>.bin` | Exact decoded HTTP response-body bytes returned by requests |
| `artifacts/<id>.json` | Parsed results before cross-backend merge, actual query variants, or verification results |
| `audit_manifest.json` | Terminal outcome, process return code, event count, and events-file bytes/SHA-256 |

Every event has `schema_version`, `sequence`, `attempt_id`, `parent_id`,
`event`, `operation`, `backend`, `timestamp`, `parameters`, `outcome`,
`error_code`, `http_status`, `record_count`, and `artifacts`. Null means not
available/applicable, never zero. Started events precede the action and have
null outcome. Finished events retain result references and failures.

References contain a directory-relative `path`, byte count and SHA-256 of the
exact saved bytes. JSON result payloads retain existing backend record shapes;
their content is evidence, not a promise of identity or scientific correctness.
Raw responses remain available when normalization drops information. A future
incompatible envelope change requires a new schema version.

Parent links connect command → query/expansion → backend → HTTP/parse attempts.
`backend-search` records each actual backend invocation before filtering,
deduplication, ranking or the final CLI limit. Two backends finding the same DOI
produce two result artifacts even if the normal CLI prints one merged result.
`search-query` records each actual adversarial variant separately. Optional LLM
expansion records its prompt, returned text and failures before fallback.
Enrichment records each resolver and abstract-recovery operation. Unknown
backend names produce explicit `unknown_backend` events.

## Outcomes

| Outcome | Interpretation |
| --- | --- |
| `success` | The operation completed with the observed evidence required for its kind |
| `success_empty` | A backend returned zero records after a successful HTTP response and checked parsing |
| `not_found` | HTTP 404 or 410; distinct from a successful empty search |
| `rate_limited` | HTTP 429 |
| `http_error` | Other unsuccessful HTTP status |
| `network_error`, `timeout` | Transport failed; no empty-search inference is allowed |
| `parse_error` | Invalid JSON/XML or missing/wrong expected collection shape |
| `partial` | Some results/operations succeeded and a child attempt failed or was unobserved |
| `unknown` | Required transport/parse evidence was not observed |
| `cancelled`, `error` | Interruption, unfinished worker, nonzero command, or other exception |

Legacy commands can still exit zero and print `[]` for a failed backend. Read
the audit outcome as well as the exit code. A timeout or failed/unknown attempt
cannot establish search saturation. Transient failures remain recorded even
if a later internal retry succeeds; aggregate outcomes are conservative.

`complete` in the manifest means the terminal ledger was successfully written,
not that every backend succeeded, that recall is complete, or that claims have
been verified. A missing manifest, missing finish, bad JSON, broken reference,
changed hash or incomplete sequence must be treated as incomplete evidence.
Consumers validate files/hashes/references themselves; JSON Schema alone only
checks shape. Do not count an interrupted run as a completed search round.

The default five search backends have explicit JSON/Atom response checks.
Additional requests-based backends preserve their HTTP attempts too. Opaque
SDKs, HTML-only searches without a checked response structure, missing API
configuration and cached verification without a fresh response can be
`unknown`; they are never promoted to `success_empty`. Audit does not add API
keys or install optional search dependencies.

## Failure, concurrency and evidence boundaries

- Attempts and artifacts are never overwritten. A reused output directory
  fails before running the command. Writes use a shared lock; worker contexts
  are propagated explicitly, without monkeypatching global HTTP functions.
- The existing 60-second search-pool deadline produces timeout events. At
  command shutdown, unfinished attempts receive cancelled finishes. Late
  workers cannot alter sealed files or start further recorded HTTP operations.
- Keyboard interruption writes a cancelled terminal record when cleanup can
  run. A forced process kill can leave only the started events; missing terminal
  evidence remains visibly incomplete. Audit-write failures are fatal, not
  silently ignored by a backend's existing exception handling.
- HTTP timestamps bracket the library call, not packet-level timing. Recorded
  redirects show URLs/statuses from the response history. Response bodies are
  decoded by requests, not raw compressed network frames.
- Request headers, cookies and auth objects are excluded. Sensitive parameter
  names and credentials in URLs are redacted; query text and response bodies
  are retained as research evidence. Store runs according to their content's
  privacy requirements; credentials must never be placed inside query text.
- `verify --doi` records resolver evidence only. A resolver HTTP success says
  nothing about title, authors, year, version, identity, or scientific claims.
  Downstream research systems must assess those obligations separately.

Tests use synthetic records and mocked HTTP responses. They cover preserved
duplicates, exact variants, default CLI compatibility, successful empty/404/
429/timeout/parse distinctions, schema rejection, immutable directories,
concurrent shutdown, and credential omission. No benchmark answer key is used.
