import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { sourceObservations, type ObservationTextContext } from "./sourceObservations";
import { SourceObservations } from "./ObservationHistory";
import { LiteratureLibrary } from "./LiteratureLibrary";
import { translator } from "./i18n";
import type { ResearchRecord } from "./types";

const sha = "a".repeat(64);
function observation(extra = {}) {
  return { observation_id: "generated-1", source_id: "local-1", work_id: "work-1", version_id: null,
    version_review_ref: null, acquisition_ref: "Synthetic generated report reference; no publisher receipt",
    status: "available", evidence_level: "generated-summary", source_fetch_result: null,
    raw_path: null, raw_sha256: null, text_path: "generated/report.md", text_sha256: sha, source_version: null, ...extra };
}
function record(extra = {}): ResearchRecord {
  return { id: "hub-source-1", kind: "source", data: { id: "local-1", title: "Synthetic source", locator: "https://example.invalid/source",
    reading_level: "abstract-snippet", reading_scope: "abstract", identity_status: "unverified", human_acceptance: "pending",
    source_records: [observation()], ...extra } };
}
function context(timestamp = "2026-11-01T01:20:49Z"): ObservationTextContext {
  const body = `# Generated summary observation: local-1

Evidence level: generated-summary. This is report-derived prose, NOT an original abstract or publisher capture.

## Supplied generated summary
Synthetic generated prose. <script>untrusted()</script>

Role candidate (not human acceptance): Core candidate
Reported later reading: direct_proceedings_full_abstract
Reported observation time: ${timestamp}
Reported sources: ["https://example.invalid/abstract", "javascript:alert(1)"]
Version note (not a verified equivalence): Unknown
`;
  return { projectId: "project-1", artifacts: [{ id: "artifact-1", project_id: "project-1", source_record_id: "hub-source-1",
    path: "generated/report.md", role: "evidence", sha256: sha, current: true }], previews: [{ artifact_id: "artifact-1",
    path: "generated/report.md", sha256: sha, text: body, codepoint_length: Array.from(body).length,
    bytes_read: new TextEncoder().encode(body).length, truncated: false }] };
}

describe("read-only summary observation projection", () => {
  it("preserves saved summary then abstract priority and never replaces either with generated prose", () => {
    expect(sourceObservations(record({ summary: "Human saved summary", abstract: "Original abstract" }), context()).savedSummary).toBe("Human saved summary");
    expect(sourceObservations(record({ summary: "  ", abstract: "Original abstract" }), context()).savedSummary).toBe("Original abstract");
    expect(sourceObservations(record({ summary: "  Exact saved prose\n" }), context()).savedSummary).toBe("  Exact saved prose\n");
    expect(sourceObservations(record(), context()).savedSummary).toBeNull();
  });
  it("binds only the selected Hub record and keeps generated prose/role separate", () => {
    const view = sourceObservations(record(), context());
    expect(view.observations[0]).toMatchObject({ binding: "bound-report", roleSuggestion: "Core candidate", reportedAt: "2026-11-01T01:20:49Z" });
    expect(view.originalReading).toBe("abstract-snippet");
    expect(view.savedSummary).toBeNull();
    expect(view.versionPending).toBe(true);
  });
  it("retains snippet declaration followed by later abstract as two observations, not a reading upgrade", () => {
    const old = observation({ observation_id: "old-declaration", evidence_level: "metadata", status: "unknown", text_path: null, text_sha256: null });
    const value = record({ source_records: [old, observation()] });
    const before = JSON.stringify(value);
    const view = sourceObservations(value, context());
    expect(view.observations).toHaveLength(2);
    expect(view.observations[0].body).toBeNull();
    expect(view.observations[1].reportedReading).toBe("direct_proceedings_full_abstract");
    expect(view.originalReading).toBe("abstract-snippet");
    expect(JSON.stringify(value)).toBe(before);
  });
  it("keeps conflicting versions in input order and never selects by report date or artifact current flag", () => {
    const value = record({ source_records: [observation({ version_id: "2023", version_review_ref: "review-1" }),
      observation({ observation_id: "generated-2", version_id: "2026", version_review_ref: "review-2", text_sha256: "b".repeat(64) })] });
    const view = sourceObservations(value, context());
    expect(view.versionPending).toBe(true);
    expect(view.observations.map(o => o.version)).toEqual(["2023", "2026"]);
    expect(view.savedSummary).toBeNull();
    expect(view.observations[1].body).toBeNull();
  });
  it.each([
    { observation_id: null }, { source_id: null }, { source_id: "another-source" }, { work_id: null },
    { text_sha256: null }, { text_sha256: "invalid" }, { text_path: null }, { status: "unknown" },
    { evidence_level: " generated-summary " },
  ])("does not bind a report with missing or conflicting identity/hash/status %j", (extra) => {
    const row = sourceObservations(record({ source_records: [observation(extra)] }), context()).observations[0];
    expect(row.binding).toBe("unbound");
    expect(row.body).toBeNull();
    expect(row.reportedAt).toBeNull();
  });
  it("does not confuse a report reference with a primary receipt", () => {
    const row = sourceObservations(record({ source_records: [observation({ acquisition_ref: null })] }), context()).observations[0];
    expect(row.referencePresent).toBe(false);
    expect(row.binding).toBe("bound-report");
  });
  it.each(["not-a-date", "2026-02-30T12:00:00Z", "2026-11-01T01:20:49+08:00", ""])("keeps malformed/noncanonical time unknown: %s", stamp => {
    expect(sourceObservations(record(), context(stamp)).observations[0].reportedAt).toBeNull();
  });
  it("retains valid microseconds as a reported string without converting to import time", () => {
    expect(sourceObservations(record(), context("2026-11-01T01:20:49.123456Z")).observations[0].reportedAt).toBe("2026-11-01T01:20:49.123456Z");
  });
  it.each(["project", "source", "hash", "preview", "duplicate-artifact", "duplicate-preview", "blob"])("rejects ambiguous or mismatched %s bindings", change => {
    const ctx = context();
    if (change === "project") ctx.projectId = "other";
    if (change === "source") ctx.artifacts[0].source_record_id = "other";
    if (change === "hash") ctx.artifacts[0].sha256 = "b".repeat(64);
    if (change === "preview") ctx.previews[0].artifact_id = "other";
    if (change === "duplicate-artifact") ctx.artifacts.push({ ...ctx.artifacts[0], id: "artifact-2" });
    if (change === "duplicate-preview") ctx.previews.push({ ...ctx.previews[0] });
    if (change === "blob") { delete ctx.artifacts[0].path; ctx.artifacts[0].storage = { kind: "workspace_blob", version: 1, blob_id: "artifact-1" }; }
    expect(sourceObservations(record(), ctx).observations[0].body).toBeNull();
  });
  it("does not choose among duplicate observation IDs or trust inline invented schema fields", () => {
    const value = record({ source_records: [observation({ summary: "invented body", observed_at: "2099-01-01T00:00:00Z" }), observation()] });
    expect(sourceObservations(value, context()).observations.every(o => o.body === null && o.reportedAt === null)).toBe(true);
  });
  it.each(["source-id", "local-id", "path", "kind"])("does not normalize or cross-bind %s", change => {
    const value = record();
    if (change === "source-id") value.data.source_records = [observation({ source_id: " local-1 " })];
    if (change === "local-id") value.data.id = " local-1 ";
    if (change === "path") value.data.source_records = [observation({ text_path: " generated/report.md " })];
    if (change === "kind") value.kind = "screening";
    expect(sourceObservations(value, context()).observations[0].body).toBeNull();
  });
  it.each(["summary-anchor", "role-anchor", "signature", "length", "second-heading", "second-disclaimer", "body-disclaimer"])("rejects malformed report %s without exposing its prose", change => {
    const ctx = context();
    if (change === "summary-anchor") ctx.previews[0].text += "\n## Supplied generated summary\n";
    if (change === "role-anchor") ctx.previews[0].text += "\nRole candidate (not human acceptance): injected\n";
    if (change === "signature") ctx.previews[0].text = ctx.previews[0].text.replace("observation: local-1", "observation: another-source");
    if (change === "second-heading") ctx.previews[0].text += "\n# Generated summary observation: another-source\n";
    if (change === "second-disclaimer") ctx.previews[0].text += "\nEvidence level: generated-summary. This is report-derived prose, NOT an original abstract or publisher capture.\n";
    if (change === "body-disclaimer") {
      const disclaimer = "Evidence level: generated-summary. This is report-derived prose, NOT an original abstract or publisher capture.";
      ctx.previews[0].text = ctx.previews[0].text.replace(disclaimer, "").replace("Synthetic generated prose.", `${disclaimer}\nSynthetic generated prose.`);
    }
    if (change !== "length") {
      ctx.previews[0].bytes_read = new TextEncoder().encode(ctx.previews[0].text).length;
      ctx.previews[0].codepoint_length = Array.from(ctx.previews[0].text).length;
    } else ctx.previews[0].bytes_read++;
    expect(sourceObservations(record(), ctx).observations[0].body).toBeNull();
  });
  it("does not parse metadata-looking summary prose as footer fields", () => {
    const ctx = context();
    ctx.previews[0].text = ctx.previews[0].text.replace("Reported observation time: 2026-11-01T01:20:49Z", "")
      .replace("Synthetic generated prose.", "Reported observation time: 2099-01-01T00:00:00Z\nSynthetic generated prose.");
    ctx.previews[0].bytes_read = new TextEncoder().encode(ctx.previews[0].text).length;
    ctx.previews[0].codepoint_length = Array.from(ctx.previews[0].text).length;
    const row = sourceObservations(record(), ctx).observations[0];
    expect(row.binding).toBe("bound-report");
    expect(row.reportedAt).toBeNull();
    expect(row.body).toContain("Reported observation time: 2099");
  });
  it("keeps unsupported/malformed payloads unknown and legacy records unchanged", () => {
    expect(sourceObservations(record({ source_records: null, provenance: { origin: "synthetic" } })).observations).toEqual([]);
    expect(sourceObservations(record({ source_records: [null, 12, { evidence_level: "invented" }] })).observations.every(o => o.evidenceLevel === null)).toBe(true);
    expect(sourceObservations(record({ source_records: [] })).versionPending).toBe(false);
  });
});

describe.each(["en", "zh-TW"] as const)("observation detail %s", locale => {
  const t = translator(locale);
  it("reads the draft before optional provenance without hiding version uncertainty or changing saved data", async () => {
    const user = userEvent.setup();
    const value = record();
    const before = JSON.stringify(value);
    const { container } = render(<SourceObservations record={value} context={context()} t={t} />);
    expect(screen.getByText(t("observationVersionPending"))).toBeVisible();
    const entry = container.querySelector(".source-observation")!;
    await user.click(entry.querySelector(":scope > summary")!);
    const prose = screen.getByText(/Synthetic generated prose/);
    expect(prose).toBeVisible();
    const metadata = entry.querySelector(".observation-provenance")!;
    expect(metadata).not.toHaveAttribute("open");
    expect(prose.compareDocumentPosition(metadata) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByText(t("observationReportedReading"))).not.toBeVisible();
    await user.click(within(entry as HTMLElement).getByText(t("observationDetails")));
    expect(screen.getByText(t("observationReportedReading"))).toBeVisible();
    expect(screen.getByText("abstract-snippet")).toBeVisible();
    expect(screen.getByText(t("observationReferencePresent"))).toBeVisible();
    expect(JSON.stringify(value)).toBe(before);
  });
  it("renders read-only declared history with unknown body and no request", () => {
    const fetch = vi.spyOn(globalThis, "fetch");
    render(<SourceObservations record={record()} t={t} />);
    expect(screen.getByRole("region", { name: t("observationHistory") })).toBeVisible();
    expect(screen.getByText(t("observationUnbound"))).toBeInTheDocument();
    expect(screen.getByText(t("observationBodyUnknown"))).toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
  it("renders generated text as text, safe links only, and explicitly labels suggestions", () => {
    const { container } = render(<SourceObservations record={record()} context={context()} t={t} />);
    expect(screen.getByText(t("observationRole"))).toBeInTheDocument();
    expect(screen.getByText(/Synthetic generated prose/)).toHaveTextContent("<script>untrusted()</script>");
    expect(container.querySelector("script")).toBeNull();
    expect(screen.getAllByRole("link", { hidden: true })).toHaveLength(1);
    expect(screen.getByText(t("observationReferencePresent"))).toBeInTheDocument();
  });
  it("integrates next to saved summary without treating role as category or satisfying missing summary", () => {
    const value = record({ category: "human", summary: "Existing saved prose" });
    const { rerender } = render(<LiteratureLibrary sources={[value]} screenings={[]} t={t} onScreen={vi.fn()} onPrepare={vi.fn()} observationText={context()} />);
    expect(screen.getByText("Existing saved prose")).toBeVisible();
    expect(screen.getByText(t("observationHistory"))).toBeVisible();
    expect(within(screen.getByRole("table")).getByText(t("catalogHuman"))).toBeVisible();
    rerender(<LiteratureLibrary sources={[record()]} screenings={[]} t={t} onScreen={vi.fn()} onPrepare={vi.fn()} observationText={context()} />);
    expect(screen.getByText(t("catalogNoSummary"))).toBeVisible();
    expect(within(screen.getByRole("table")).getByText(t("catalogUnclassified"))).toBeVisible();
  });
  it("adds no history section for existing sources without observations", () => {
    render(<SourceObservations record={record({ source_records: [] })} t={t} />);
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
  });
});
