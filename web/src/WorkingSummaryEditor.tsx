import { useEffect, useId, useRef, useState } from "react";
import { api, ApiError, segment } from "./api";
import { ReadText } from "./components";
import type { Translate } from "./i18n";
import { registeredObservationArtifacts, type ObservationReadScope } from "./ObservationPreview";
import type { Artifact, ResearchRecord } from "./types";
import { normalizeWorkingSummaryText } from "./workingSummaryText";

export interface WorkingSummary {
  text: string;
  artifact_id: string;
  artifact_sha256: string;
  source_revision: string;
  previous_revision: string;
  saved_at: string;
}
interface SummaryContext {
  source_record_id: string;
  artifact_id: string;
  artifact_sha256: string;
  revision: string;
  draft_text: string;
  working_summary: WorkingSummary | null;
}
const hash = (value: unknown): value is string => typeof value === "string" && /^[a-f0-9]{64}$/.test(value);
const isForbiddenRequest = (failure: unknown) => failure instanceof ApiError && failure.status === 403 && failure.code === "forbidden";
function validSummary(value: unknown): value is WorkingSummary {
  const item = value as WorkingSummary | undefined;
  return Boolean(item && typeof item.text === "string" && normalizeWorkingSummaryText(item.text) &&
    typeof item.artifact_id === "string" && item.artifact_id && hash(item.artifact_sha256) &&
    hash(item.source_revision) && hash(item.previous_revision) &&
    typeof item.saved_at === "string" && Number.isFinite(Date.parse(item.saved_at)));
}
export function workingSummary(record: ResearchRecord): WorkingSummary | undefined {
  return record.kind === "source" && validSummary(record.data.working_summary) ? record.data.working_summary : undefined;
}
export function SavedWorkingSummary({record, t}: {record: ResearchRecord; t: Translate}) {
  const saved = workingSummary(record);
  return saved ? <section aria-label={t("workingSummaryTitle")}><h4>{t("workingSummaryTitle")}</h4>
    <ReadText value={saved.text}/><p className="small muted">{t("workingSummaryHelp")}</p></section> : null;
}
interface Props {
  record: ResearchRecord;
  scope?: ObservationReadScope;
  /** Only a page navigation may suspend an otherwise-open reader session. */
  suspended?: boolean;
  t: Translate;
  onOpen?: () => void;
  onSaved?: () => Promise<void>;
}

/** Selection is always explicit, including when a source has several reports. */
export function WorkingSummaryEditor(props: Props) {
  const artifacts = props.scope?.active || props.suspended ? registeredObservationArtifacts(props.record, props.scope) : [];
  // Refresh and temporarily hiding this reader are not selection changes or Cancel.
  // Validate binding even while hidden; active still gates requests and side effects.
  const identity = JSON.stringify([props.scope?.projectId,
    props.record.id, artifacts.map(a => [a.id, a.sha256, a.path, a.current])]);
  return <SummarySelection key={identity} {...props} artifacts={artifacts}/>;
}
function SummarySelection({record, scope, t, onOpen, onSaved, artifacts}: Props & {artifacts: Artifact[]}) {
  const [selected, setSelected] = useState<Artifact>();
  const opener = useRef<HTMLButtonElement | null>(null);
  const active = useRef(Boolean(scope?.active));
  active.current = Boolean(scope?.active);
  if (!scope || !artifacts.length) return null;
  return <section className="working-summary-editor" hidden={!scope.active} aria-label={t("workingSummaryReview")}>
    <p className="small muted">{t("workingSummaryReviewHelp")}</p>
    <div className="working-summary-choices">{artifacts.map(artifact => <button key={artifact.id} type="button"
      className="button secondary" disabled={!scope.active || Boolean(selected)}
      aria-label={`${t("workingSummaryReview")} ${artifact.id}`}
      onClick={event => {if (active.current) {opener.current = event.currentTarget; setSelected(artifact); onOpen?.();}}}>
      {t("workingSummaryReview")} <code>{artifact.id}</code>
    </button>)}</div>
    {selected && <SummarySession key={`${selected.id}:${selected.sha256}`} record={record} artifact={selected}
      projectId={scope.projectId} active={scope.active} t={t} onSaved={onSaved} onClose={() => {
        if (!active.current) return;
        setSelected(undefined);
        // React enables the opener before the queued focus restoration.
        queueMicrotask(() => {if (active.current && opener.current?.isConnected) opener.current.focus();});
      }}/>}
  </section>;
}
type Phase = "loading" | "ready" | "saving" | "checking" | "blocked" | "saved";
function SummarySession({record, artifact, projectId, active, t, onClose, onSaved}: {
  record: ResearchRecord; artifact: Artifact; projectId: string; active: boolean; t: Translate;
  onClose: () => void; onSaved?: () => Promise<void>;
}) {
  const [context, setContext] = useState<SummaryContext>();
  const [draft, setDraft] = useState("");
  const [phase, setPhase] = useState<Phase>("loading");
  const [message, setMessage] = useState<Parameters<Translate>[0]>();
  const alive = useRef(true);
  const activeRef = useRef(active);
  activeRef.current = active;
  const pendingRefresh = useRef(false);
  const busy = useRef(false);
  const latestDraft = useRef("");
  const attempted = useRef<{text: string; revision: string; draft: string} | null>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const id = useId();
  const path = `/projects/${segment(projectId)}/working-summary`;
  // Match the server's prose normalization without replacing an unsaved edit.
  const submittedText = normalizeWorkingSummaryText(draft);
  const tooLong = Array.from(submittedText).length > 40000;
  function updateDraft(value: string) {
    latestDraft.current = value;
    setDraft(value);
  }
  async function read(signal?: AbortSignal) {
    const result = await api<{ok: true; context: SummaryContext}>(`${path}?source_record_id=${segment(record.id)}&artifact_id=${segment(artifact.id)}`, undefined, signal);
    const item = result.context;
    if (!item || item.source_record_id !== record.id || item.artifact_id !== artifact.id ||
      item.artifact_sha256 !== artifact.sha256 || !hash(item.revision) || typeof item.draft_text !== "string" ||
      (item.working_summary !== null && !validSummary(item.working_summary))) throw new Error("Invalid summary context");
    return item;
  }
  const bound = (saved: WorkingSummary | null) => saved?.artifact_id === artifact.id && saved.artifact_sha256 === artifact.sha256;
  useEffect(() => {
    alive.current = true;
    const controller = new AbortController();
    if (!activeRef.current) return () => {alive.current = false;};
    heading.current?.focus();
    void read(controller.signal).then(item => {
      if (!alive.current || controller.signal.aborted) return;
      setContext(item); updateDraft(bound(item.working_summary) ? item.working_summary!.text : item.draft_text); setPhase("ready");
    }).catch(failure => {
      if (!alive.current || controller.signal.aborted) return;
      setPhase("blocked"); setMessage(isForbiddenRequest(failure) ? "workingSummaryForbidden" : "workingSummaryLoadFailed");
    });
    return () => {alive.current = false; controller.abort();};
  }, []);
  useEffect(() => {
    if (!activeRef.current) return;
    if (phase === "ready" && !message) input.current?.focus();
    if (phase === "saved") heading.current?.focus();
  }, [phase]);
  useEffect(() => {
    if (!active || !pendingRefresh.current) return;
    // Consume before invoking a callback which may rerender this same session.
    // Selection changes/Cancel unmount this ref rather than transferring it.
    pendingRefresh.current = false;
    void (async () => {
      try {await onSaved?.();} catch {if (alive.current) setMessage("workingSummarySavedRefreshFailed");}
    })();
  }, [active, phase, onSaved]);
  async function announceSaved() {
    pendingRefresh.current = true;
    setPhase("saved"); setMessage("workingSummarySaved");
  }
  async function save() {
    if (!activeRef.current || busy.current || phase !== "ready" || !context || !submittedText || tooLong) return;
    busy.current = true; setPhase("saving"); setMessage(undefined);
    attempted.current = {text:submittedText, revision:context.revision, draft:latestDraft.current};
    try {
      const result = await api<{ok:true; record:ResearchRecord; reused:boolean}>(path, {
        source_record_id:record.id, artifact_id:artifact.id, artifact_sha256:artifact.sha256,
        expected_revision:context.revision, text:submittedText,
      });
      const saved = workingSummary(result.record);
      if (result.record.id !== record.id || !saved || !bound(saved) || saved.text !== submittedText || saved.previous_revision !== context.revision)
        throw new Error("Unconfirmed working summary write");
      if (alive.current) await announceSaved();
    } catch (failure) {
      if (alive.current) {
        setPhase("blocked");
        setMessage(isForbiddenRequest(failure) ? "workingSummaryForbidden" : failure instanceof ApiError && failure.code === "stale_input" ? "workingSummaryStale" : "workingSummaryUnknown");
      }
    } finally {busy.current = false;}
  }
  async function check() {
    if (!activeRef.current || busy.current) return;
    busy.current = true; setPhase("checking");
    try {
      const item = await read();
      if (!alive.current) return;
      setContext(item);
      const request = attempted.current;
      if (request && bound(item.working_summary) && item.working_summary!.text === request.text &&
        item.working_summary!.previous_revision === request.revision) {
        // The GET confirms the earlier request, not edits made while blocked or
        // while this read was pending. Retain those edits without a refresh.
        if (latestDraft.current === request.draft) await announceSaved();
        else {setPhase("ready");setMessage("workingSummaryEarlierSaved");}
      } else {
        // An existing edit is retained even when its original context was stale.
        if (!context) updateDraft(bound(item.working_summary) ? item.working_summary!.text : item.draft_text);
        setPhase("ready");setMessage("workingSummaryChecked");
      }
    } catch (failure) {if (alive.current) {setPhase("blocked"); setMessage(isForbiddenRequest(failure) ? "workingSummaryForbidden" : "workingSummaryCheckFailed");}}
    finally {busy.current = false;}
  }
  return <div role="dialog" aria-labelledby={`${id}-heading`} aria-describedby={`${id}-help`}
    className="working-summary-session" onKeyDown={event => {
      if (activeRef.current && event.key === "Escape") {event.stopPropagation(); if (phase !== "saving") onClose();}
    }}>
    <h4 id={`${id}-heading`} ref={heading} tabIndex={-1}>{t("workingSummaryReview")} <code>{artifact.id}</code></h4>
    <p id={`${id}-help`} className="small muted">{t("workingSummaryHelp")}</p>
    {phase === "loading" && <p role="status">{t("workingSummaryLoading")}</p>}
    {context && <label className="field field-wide">{t("workingSummaryText")}<textarea ref={input} rows={10}
      value={draft} disabled={!active || phase === "saving" || phase === "saved"} onChange={event => {if (activeRef.current) updateDraft(event.target.value);}}/></label>}
    {message && <p role={phase === "blocked" ? "alert" : "status"}>{t(message)}</p>}
    {tooLong && <p role="alert">{t("workingSummaryTooLong")}</p>}
    <div className="working-summary-actions">
      <button type="button" className="button" disabled={!active || phase !== "ready" || !submittedText || tooLong} onClick={() => void save()}>
        {t(phase === "saving" ? "workingSummarySaving" : "workingSummarySave")}</button>
      {(phase === "blocked" || phase === "checking") && <button type="button" className="button secondary"
        disabled={!active || phase === "checking"} onClick={() => void check()}>{t(phase === "checking" ? "workingSummaryChecking" : "workingSummaryCheck")}</button>}
      <button type="button" className="button secondary" disabled={!active || phase === "saving"} onClick={onClose}>{t(phase === "saved" ? "workingSummaryClose" : "cancel")}</button>
    </div>
  </div>;
}
