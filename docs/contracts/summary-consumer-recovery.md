# Summary receipt consumers

Historical slice: this document describes the consumer-reporting change before
the durable journal was integrated. Current legacy apply also follows the
[schema2 journal apply contract](legacy-summary-journal-apply.md). That journal
retains per-destination outcomes and unresolved claims; this document does not
supersede its dispatch/replay rules.

Text CLI summarize/resummarize and chained enrichment must show the complete existing receipt before returning an incomplete result: every ordered error/unknown/rollback message, skip, warning and confirmed partial count. `SummaryReport.error` remains a short first-error summary, not the only recovery information. JSON CLI and MCP retain their complete existing schema/error arrays; no new status field is invented.

Auto's second summary layer is a distinct model/local-note writer, not a retry of the first remote POST. It now defers when the first layer is incomplete, including partial success or exceptions, because a second writer may otherwise change a note whose remote write/compensation requires reconciliation. Confirmed successes and all errors remain visible. The fully successful path continues its second layer exactly once. Other ingest steps are not rolled back or silently reclassified.

This original consumer-reporting slice did not add a durable remote-write ledger; the later journal integration does. CLI output/MCP receipts provide recovery guidance; restart does not prove an unknown operation failed, and a generic pending-note view is not remote-outcome reconciliation. Destination inspection alone does not authorize or unlock another attempt. Current unresolved, compensated or conflicted journal operations remain blocked; no in-product user-resolution or retry-after-compensation API is provided. The workspace abstract-draft UI uses a separate no-tool profile and does not consume this legacy dual-sink apply receipt.

CI-collected regressions invoke actual imported writer/CLI-handler/auto functions with synthetic adapter and report seams, not extracted replacements. The retained standalone consumer audit additionally extracts unchanged function ASTs; that supplemental result remains source-bound, not installed CLI/MCP transport acceptance. No real provider, private configuration/vault, HTTP server or credentials are used. The original slice added no journal, lookup tool, retry authorization or broad new UI; the later journal integration does not add a user-resolution UI or current-destination readback tool either.
