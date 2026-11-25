import { useEffect, useState } from "react";
import { api, ApiError, segment } from "./api";
import type { Translate } from "./i18n";
import type { ResearchRecord } from "./types";
import type { ObservationReadScope } from "./ObservationPreview";

const sections = ["why", "objective", "methods", "findings", "conclusions", "key_points", "limitations"] as const;
const titles = ["nativeWhy", "nativeObjective", "nativeMethods", "nativeFindings", "nativeConclusions", "nativeKeyPoints", "nativeLimitations"] as const;
type Evidence = { artifact_id: string; quote: string; start: number; end: number };
type Claim = { text: string; status: "supported" | "analyst_inference" | "unknown"; reason: string; evidence: Evidence[] };
type Selection = { artifact_id: string; sha256: string; start: number; end: number; text_sha256: string };
type Summary = { schema: string; project_id: string; source_record_id: string; source: {title: string; locator: string}; source_revision: string; expected_revision: string; reading_scope: string; selections: Selection[]; sections: Record<typeof sections[number], Claim[]> };
const object = (v: unknown): v is Record<string, unknown> => Boolean(v && typeof v === "object" && !Array.isArray(v));
const nonempty = (v: unknown): v is string => typeof v === "string" && Boolean(v.trim());
const hash = (v: unknown): v is string => typeof v === "string" && /^[a-f0-9]{64}$/.test(v);
const offsets = (v: Record<string, unknown>) => Number.isSafeInteger(v.start) && Number.isSafeInteger(v.end) && (v.start as number) >= 0 && (v.end as number) > (v.start as number);

/** Fail closed on malformed or unbound prose; the service verifies file bytes. */
function validSummary(v: unknown, record: ResearchRecord, scope: ObservationReadScope): v is Summary {
  if (!object(v) || v.human_acceptance !== "pending" || v.semantic_support !== "not_assessed" || !nonempty(v.saved_at) || v.schema !== "native-source-summary-v1" || v.project_id !== scope.projectId || v.source_record_id !== record.id ||
    !object(v.source) || v.source.title !== record.data.title || v.source.locator !== record.data.locator ||
    !hash(v.source_revision) || !hash(v.expected_revision) || !nonempty(v.reading_scope) || v.reading_scope !== (record.data.reading_scope ?? "unknown") ||
    !Array.isArray(v.selections) || !v.selections.length || v.selections.length > 8 || !object(v.sections)) return false;
  const selections: Selection[] = [];
  for (const s of v.selections) {
    if (!object(s) || !nonempty(s.artifact_id) || !hash(s.sha256) || !hash(s.text_sha256) || !offsets(s)) return false;
    const artifacts = scope.artifacts.filter(a => a.id === s.artifact_id && a.project_id === scope.projectId && a.source_record_id === record.id && a.sha256 === s.sha256 && a.current === true && a.role === "evidence");
    if (artifacts.length !== 1 || selections.some(previous => previous.artifact_id === s.artifact_id)) return false;
    selections.push(s as Selection);
  }
  return sections.every(key => {
    const claims = (v.sections as Record<string, unknown>)[key];
    return Array.isArray(claims) && claims.length > 0 && claims.length <= 12 && claims.every(c => {
      if (!object(c) || !nonempty(c.text) || !nonempty(c.reason) || typeof c.status !== "string" || !["supported", "analyst_inference", "unknown"].includes(c.status) || !Array.isArray(c.evidence) || c.evidence.length > 8) return false;
      if (c.status === "supported" && !c.evidence.length) return false;
      return c.evidence.every(e => object(e) && nonempty(e.quote) && offsets(e) && Array.from(e.quote).length === (e.end as number) - (e.start as number) &&
        selections.some(s => s.artifact_id === e.artifact_id && s.start <= (e.start as number) && s.end >= (e.end as number)));
    });
  });
}

type State = { key: string; status: "loading" | "current" | "missing" | "stale" | "unavailable"; summary?: Summary };
export function NativeSummaryReader({ record, scope, t, exportable = false }: { record: ResearchRecord; scope?: ObservationReadScope; t: Translate; exportable?: boolean }) {
  const eligible = Boolean(scope?.active && scope.projectId && record.kind === "source" && record.id);
  const available = "native_summary_available" in record && record.native_summary_available === true;
  // Include selected source metadata and artifact versions, but not unrelated renders.
  const key = JSON.stringify([eligible, available, scope?.projectId, scope?.revision, record.id, record.data, scope?.artifacts]);
  const [state, setState] = useState<State>();
  const [exportStatus, setExportStatus] = useState<{ tone: "good" | "bad"; text: string } | null>(null);
  const [exportBusy, setExportBusy] = useState(false);
  useEffect(() => {
    if (!eligible || !scope || !available) return;
    const controller = new AbortController();
    setState({key, status:"loading"});
    void (async () => {
      try {
        const result = await api<unknown>(`/projects/${segment(scope.projectId)}/native-summary?source_record_id=${encodeURIComponent(record.id)}`, undefined, controller.signal);
        if (controller.signal.aborted) return;
        if (!object(result) || result.ok !== true || result.human_acceptance !== "pending" || result.semantic_support !== "not_assessed") throw new Error("Invalid summary envelope");
        if (result.status === "current") {
          if (!validSummary(result.native_summary, record, scope)) { setState({key, status:"stale"}); return; }
          setState({key, status:"current", summary:result.native_summary});
        } else if (typeof result.status === "string" && ["missing", "stale", "unavailable"].includes(result.status)) {
          setState({key, status:result.status as State["status"]});
        } else throw new Error("Unknown summary state");
      } catch (error) { if (!controller.signal.aborted) setState({key, status:error instanceof ApiError && error.code === "stale_input" ? "stale" : "unavailable"}); }
    })();
    return () => controller.abort();
  }, [key]);
  if (!eligible) return null;
  const current: State | undefined = !available ? {key, status:"missing"} : state?.key === key ? state : undefined;
  const summary = current?.status === "current" ? current.summary : undefined;

  async function fetchMarkdown(): Promise<string | null> {
    if (!scope?.projectId || !record.id) return null;
    setExportBusy(true);
    setExportStatus(null);
    try {
      const result = await api<{ ok?: boolean; markdown?: string | null; error?: string }>(
        `/projects/${segment(scope.projectId)}/native-summary/markdown?source_record_id=${encodeURIComponent(record.id)}`,
      );
      if (!result?.ok || typeof result.markdown !== "string" || !result.markdown) {
        setExportStatus({ tone: "bad", text: result?.error || t("nativeExportFailed") });
        return null;
      }
      return result.markdown;
    } catch (err) {
      setExportStatus({
        tone: "bad",
        text: err instanceof ApiError ? err.message : t("nativeExportFailed"),
      });
      return null;
    } finally {
      setExportBusy(false);
    }
  }

  async function copyMarkdown() {
    const md = await fetchMarkdown();
    if (!md) return;
    if (!navigator.clipboard?.writeText) {
      setExportStatus({ tone: "bad", text: t("nativeExportFailed") });
      return;
    }
    try {
      await navigator.clipboard.writeText(md);
      setExportStatus({ tone: "good", text: t("nativeExportCopied") });
    } catch {
      setExportStatus({ tone: "bad", text: t("nativeExportFailed") });
    }
  }

  async function downloadMarkdown() {
    const md = await fetchMarkdown();
    if (!md) return;
    const blob = new Blob([md], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${record.id.replace(/[^a-zA-Z0-9._-]/g, "_")}-summary.md`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  return <section className="native-summary" aria-label={t("nativeTitle")}>
    <div className="native-summary-header">
      <div>
        <h4>{t("nativeTitle")}</h4>
        {summary && <span className="badge neutral">{t("nativeDeclaredScope")}: {summary.reading_scope}</span>}
        {summary && <span className="badge warn">{t("nativePending")}</span>}
      </div>
      {exportable && summary && scope?.projectId && (
        <div className="native-export-actions">
          <button type="button" className="button secondary small" disabled={exportBusy} onClick={() => void copyMarkdown()}>
            {t("nativeCopyMarkdown")}
          </button>
          <button type="button" className="button secondary small" disabled={exportBusy} onClick={() => void downloadMarkdown()}>
            {t("nativeDownloadMarkdown")}
          </button>
          {exportStatus && (
            <span role="status" className={exportStatus.tone === "good" ? "small good-text" : "small bad-text"}>
              {exportStatus.text}
            </span>
          )}
        </div>
      )}
    </div>
    {!summary && <p className="small muted" role="status">{t(current?.status === "missing" ? "nativeMissing" : current?.status === "stale" ? "nativeStale" : current?.status === "unavailable" ? "nativeUnavailable" : "nativeLoading")}</p>}
    {summary && <>
      {sections.map((section, i) => <section key={section}><h5>{t(titles[i])}</h5>{summary.sections[section].map((claim, j) => <div className="native-claim" key={j}>
        <span className={`badge ${claim.status === "supported" ? "good" : claim.status === "analyst_inference" ? "warn" : "neutral"}`}>
          {t(claim.status === "supported" ? "nativeSupported" : claim.status === "analyst_inference" ? "nativeInference" : "nativeUnknown")}
        </span>
        {claim.text && <p className="native-prose">{claim.text}</p>}
        <p className="native-reason">{t("nativeReason")}: {claim.reason}</p>
        {claim.evidence.map((e, k) => {
          const artifactName = summary.selections.length > 1
            ? scope?.artifacts.find(a => a.id === e.artifact_id)?.path?.split(/[/\\]/).pop()
            : undefined;
          return <details key={k} className="native-evidence"><summary>{t("nativeEvidence")}{artifactName ? ` · ${artifactName}` : ""}</summary><blockquote className="native-quote">{e.quote}</blockquote></details>;
        })}
      </div>)}</section>)}
    </>}
  </section>;
}
