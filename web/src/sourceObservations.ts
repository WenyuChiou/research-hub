import type { Artifact, ResearchRecord } from "./types";
import type { TextPreview } from "./AbstractDraft";
import { previewMatchesArtifact, readableArtifact } from "./sourceStorage";

/** Existing read API responses, supplied by a caller. This projection does no I/O. */
export interface ObservationTextContext {
  projectId: string;
  artifacts: Artifact[];
  previews: TextPreview[];
}
export interface ObservationView {
  id: string | null;
  generated: boolean;
  evidenceLevel: string | null;
  version: string | null;
  versionReviewed: boolean;
  referencePresent: boolean;
  textHash: string | null;
  body: string | null;
  reportedAt: string | null;
  reportedReading: string | null;
  roleSuggestion: string | null;
  reportedSources: string[];
  binding: "unbound" | "bound-report";
}
const object = (v: unknown): Record<string, unknown> | null =>
  v !== null && typeof v === "object" && !Array.isArray(v) ? v as Record<string, unknown> : null;
const text = (v: unknown): string | null => typeof v === "string" && v.trim() ? v.trim() : null;
// Join keys must retain their bytes; whitespace-distinct IDs/paths are not aliases.
const exactText = (v: unknown): string | null => typeof v === "string" && v.trim() ? v : null;
const hash = (v: unknown): string | null => typeof v === "string" && /^[a-f0-9]{64}$/.test(v) ? v : null;
const levels = new Set(["metadata", "abstract", "full-text", "generated-summary", "unavailable"]);

// These are reported fields in the existing generated Markdown, NOT audit-schema fields.
function report(textBody: string, localId: string) {
  const lines = textBody.replace(/\r\n/g, "\n").split("\n");
  const roleLines = lines.filter(line => line.startsWith("Role candidate (not human acceptance):"));
  const disclaimer = "Evidence level: generated-summary. This is report-derived prose, NOT an original abstract or publisher capture.";
  if (lines[0] !== `# Generated summary observation: ${localId}` ||
      lines.filter(line => line.startsWith("# Generated summary observation:")).length !== 1 ||
      lines.filter(line => line === disclaimer).length !== 1) return null;
  const start = lines.indexOf("## Supplied generated summary");
  const end = lines.findIndex((line, index) => index > start && line.startsWith("Role candidate (not human acceptance):"));
  if (start < 0 || end <= start || roleLines.length !== 1 || lines.indexOf(disclaimer) > start || lines.lastIndexOf("## Supplied generated summary") !== start) return null;
  const tail = lines.slice(end);
  const field = (prefix: string) => {
    const found = tail.filter(line => line.startsWith(prefix));
    return found.length === 1 ? text(found[0].slice(prefix.length)) : null;
  };
  const timestamp = field("Reported observation time:");
  const date = timestamp && /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?Z$/.test(timestamp) ? new Date(timestamp) : null;
  // Round-trip prevents Date.parse from normalizing invalid dates such as February 30.
  const reportedAt = date && Number.isFinite(date.getTime()) && date.toISOString().slice(0, 19) === timestamp?.slice(0, 19) ? timestamp : null;
  let sources: string[] = [];
  try {
    const value: unknown = JSON.parse(field("Reported sources:") ?? "null");
    if (Array.isArray(value) && value.every(v => typeof v === "string")) sources = value;
  } catch { /* A malformed report is not a source receipt. */ }
  return {
    body: text(lines.slice(start + 1, end).join("\n")), reportedAt,
    reportedReading: field("Reported later reading:"),
    roleSuggestion: field("Role candidate (not human acceptance):"), reportedSources: sources,
  };
}

export function sourceObservations(record: ResearchRecord, context?: ObservationTextContext) {
  const savedSummary = [record.data.summary, record.data.abstract]
    .find((value): value is string => typeof value === "string" && !!value.trim()) ?? null;
  const values = Array.isArray(record.data.source_records) ? record.data.source_records : [];
  const ids = values.map(v => exactText(object(v)?.observation_id));
  const localId = exactText(record.data.id);
  const observations: ObservationView[] = values.map((value, index) => {
    const obs = object(value);
    const id = exactText(obs?.observation_id);
    const sourceId = exactText(obs?.source_id);
    const workId = exactText(obs?.work_id);
    const evidenceLevel = exactText(obs?.evidence_level);
    const generated = evidenceLevel === "generated-summary";
    const path = exactText(obs?.text_path);
    const textHash = hash(obs?.text_sha256);
    const view: ObservationView = {
      id, generated, evidenceLevel: evidenceLevel && levels.has(evidenceLevel) ? evidenceLevel : null,
      version: exactText(obs?.version_id), versionReviewed: !!text(obs?.version_review_ref),
      referencePresent: !!text(obs?.acquisition_ref), textHash, body: null,
      reportedAt: null, reportedReading: null, roleSuggestion: null, reportedSources: [], binding: "unbound",
    };
    // Never infer an artifact ID from a hash, use a caller path, or choose the latest version.
    if (record.kind !== "source" || !generated || !context || !context.projectId || !record.id || !localId || !id ||
        ids.indexOf(id) !== index || ids.lastIndexOf(id) !== index || !workId ||
        (sourceId !== localId && sourceId !== record.id) || !path || !textHash || obs?.status !== "available") return view;
    const artifacts = context.artifacts.filter(a =>
      a.project_id === context.projectId && a.source_record_id === record.id &&
      a.path === path && a.sha256 === textHash && readableArtifact(a, context.projectId, record.id));
    if (artifacts.length !== 1) return view;
    const previews = context.previews.filter(p => previewMatchesArtifact(p, artifacts[0]) &&
      p.bytes_read === new TextEncoder().encode(p.text).length && p.codepoint_length === Array.from(p.text).length);
    if (previews.length !== 1) return view;
    const parsed = report(previews[0].text, localId);
    return parsed ? { ...view, ...parsed, binding: "bound-report" } : view;
  });
  const versions = new Set(observations.map(o => o.version).filter(Boolean));
  return {
    savedSummary, originalReading: text(record.data.reading_level) ?? text(record.data.reading_scope),
    observations, versionPending: versions.size > 1 || observations.some(o => !o.version || !o.versionReviewed),
    hasSavedProvenance: !!object(record.data.provenance),
  };
}
