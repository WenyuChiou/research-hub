import { useCallback, useEffect, useId, useRef, useState } from "react";
import { api, ApiError, segment } from "./api";
import { ReadText } from "./components";
import type { Translate } from "./i18n";
import { registeredObservationArtifacts, type ObservationReadScope } from "./ObservationPreview";
import type { Artifact, ResearchRecord, Task } from "./types";
import { normalizeWorkingSummaryText } from "./workingSummaryText";

export interface TaskProvenance {
  kind: "abstract-task"; version: 1; project_id: string; source_record_id: string;
  task_id: string; input_hash: string; action_hash: string; draft_sha256: string;
}
interface SummaryBase {
  text: string; source_revision: string; previous_revision: string; saved_at: string;
}
export type WorkingSummary = SummaryBase & ({artifact_id: string; artifact_sha256: string; provenance?: never} | {provenance: TaskProvenance; artifact_id?: never; artifact_sha256?: never});
interface SummaryContext {
  source_record_id: string;
  artifact_id?: string;
  artifact_sha256?: string;
  provenance?: TaskProvenance;
  revision: string;
  draft_text: string;
  working_summary: WorkingSummary | null;
}
const hash = (value: unknown): value is string => typeof value === "string" && /^[a-f0-9]{64}$/.test(value);
const isForbiddenRequest = (failure: unknown) => failure instanceof ApiError && failure.status === 403 && failure.code === "forbidden";
const provenanceKeys = ["kind", "version", "project_id", "source_record_id", "task_id", "input_hash", "action_hash", "draft_sha256"];
function validProvenance(value: unknown): value is TaskProvenance {
  const p = value as TaskProvenance | undefined;
  return Boolean(p && Object.keys(p).length === provenanceKeys.length && provenanceKeys.every(k => Object.hasOwn(p, k)) &&
    p.kind === "abstract-task" && p.version === 1 && [p.project_id,p.source_record_id,p.task_id].every(v => typeof v === "string" && v.length > 0) &&
    [p.input_hash,p.action_hash,p.draft_sha256].every(hash));
}
function sameProvenance(a: unknown, b: TaskProvenance): boolean {
  return validProvenance(a) && provenanceKeys.every(k => a[k as keyof TaskProvenance] === b[k as keyof TaskProvenance]);
}
function validSummary(value: unknown): value is WorkingSummary {
  const item = value as WorkingSummary | undefined;
  return Boolean(item && typeof item.text === "string" && normalizeWorkingSummaryText(item.text) &&
    (item.provenance ? validProvenance(item.provenance) && Object.keys(item).length === 5 :
      typeof item.artifact_id === "string" && item.artifact_id && hash(item.artifact_sha256)) &&
    hash(item.source_revision) && hash(item.previous_revision) &&
    typeof item.saved_at === "string" && Number.isFinite(Date.parse(item.saved_at)));
}
export function workingSummary(record: ResearchRecord): WorkingSummary | undefined {
  return record.kind === "source" && validSummary(record.data.working_summary) && (!record.data.working_summary.provenance || record.data.working_summary.provenance.source_record_id === record.id) ? record.data.working_summary : undefined;
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
    {selected && <SummarySession key={`${selected.id}:${selected.sha256}`} sourceId={record.id} selection={{kind:"observation", artifact:selected}}
      projectId={scope.projectId} active={scope.active} t={t} onSaved={onSaved} onClose={() => {
        if (!active.current) return;
        setSelected(undefined);
        // React enables the opener before the queued focus restoration.
        queueMicrotask(() => {if (active.current && opener.current?.isConnected) opener.current.focus();});
      }}/>}
  </section>;
}
interface RecoveryDraft {
  id: string; provenance: TaskProvenance; revision: string; text: string; invalidated: boolean;
}
type RecoveryUpdate = {kind:"capture"; draft:RecoveryDraft} | {kind:"invalidate" | "discard"; id:string};
type Phase = "loading" | "ready" | "saving" | "checking" | "blocked" | "saved";
type Selection = {kind:"observation"; artifact:Artifact} | {kind:"task"; provenance:TaskProvenance};
function SummarySession({sourceId, selection, projectId, active, t, onClose, onSaved, onSavePendingChange, onRecoveryChange}: {
  sourceId: string; selection: Selection; projectId: string; active: boolean; t: Translate;
  onClose: () => void; onSaved?: () => Promise<void>; onSavePendingChange?:(pending:boolean)=>void; onRecoveryChange?:(update:RecoveryUpdate)=>void;
}) {
  const artifact = selection.kind === "observation" ? selection.artifact : undefined;
  const provenance = selection.kind === "task" ? selection.provenance : undefined;
  const selectionId = artifact?.id ?? provenance!.task_id;
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
  const initialDraft = useRef("");
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
  function editDraft(value: string) {
    updateDraft(value);
    // Capture raw user edits synchronously, before a parent refresh can unmount
    // this session. Recovery is never an input to context validation or saving.
    // After any save attempt, even a reversion to the initial text can be a
    // newer unsaved edit relative to a write with an unknown/earlier receipt.
    if (provenance && context) onRecoveryChange?.(value === initialDraft.current && !attempted.current
      ? {kind:"discard", id}
      : {kind:"capture", draft:{id, provenance, revision:context.revision, text:value, invalidated:false}});
  }
  function close() {
    onRecoveryChange?.({kind:"discard", id});
    onClose();
  }
  async function read(signal?: AbortSignal) {
    const result = await api<{ok: true; context: SummaryContext}>(`${path}?source_record_id=${segment(sourceId)}&${artifact ? `artifact_id=${segment(artifact.id)}` : `task_id=${segment(provenance!.task_id)}`}`, undefined, signal);
    const item = result.context;
    if (!item || item.source_record_id !== sourceId ||
      (artifact ? item.artifact_id !== artifact.id || item.artifact_sha256 !== artifact.sha256 || item.provenance !== undefined : !sameProvenance(item.provenance, provenance!) || item.artifact_id !== undefined || item.artifact_sha256 !== undefined) || !hash(item.revision) || typeof item.draft_text !== "string" ||
      (item.working_summary !== null && !validSummary(item.working_summary))) throw new Error("Invalid summary context");
    return item;
  }
  const bound = (saved: WorkingSummary | null) => Boolean(saved && (artifact ? saved.artifact_id === artifact.id && saved.artifact_sha256 === artifact.sha256 : sameProvenance(saved.provenance, provenance!)));
  useEffect(() => {
    alive.current = true;
    const controller = new AbortController();
    if (!activeRef.current) return () => {alive.current = false;};
    heading.current?.focus();
    void read(controller.signal).then(item => {
      if (!alive.current || controller.signal.aborted) return;
      initialDraft.current = bound(item.working_summary) ? item.working_summary!.text : item.draft_text;
      setContext(item); updateDraft(initialDraft.current); setPhase("ready");
    }).catch(failure => {
      if (!alive.current || controller.signal.aborted) return;
      setPhase("blocked"); setMessage(isForbiddenRequest(failure) ? "workingSummaryForbidden" : "workingSummaryLoadFailed");
    });
    return () => {
      alive.current = false; controller.abort();
      // Only reveal an already captured edit. Explicit dismissal and confirmed
      // saves remove it first; StrictMode's initial cleanup has nothing to retain.
      onRecoveryChange?.({kind:"invalidate", id});
    };
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
    onRecoveryChange?.({kind:"discard", id});
    pendingRefresh.current = true;
    setPhase("saved"); setMessage("workingSummarySaved");
  }
  async function save() {
    if (!activeRef.current || busy.current || phase !== "ready" || !context || !submittedText || tooLong) return;
    busy.current = true; onSavePendingChange?.(true); setPhase("saving"); setMessage(undefined);
    attempted.current = {text:submittedText, revision:context.revision, draft:latestDraft.current};
    try {
      const result = await api<{ok:true; record:ResearchRecord; reused:boolean}>(path, {
        source_record_id:sourceId, ...(artifact ? {artifact_id:artifact.id, artifact_sha256:artifact.sha256} : {task_id:provenance!.task_id, provenance}),
        expected_revision:context.revision, text:submittedText,
      });
      const saved = workingSummary(result.record);
      if (result.record.id !== sourceId || !saved || !bound(saved) || saved.text !== submittedText || saved.previous_revision !== context.revision)
        throw new Error("Unconfirmed working summary write");
      if (alive.current) await announceSaved();
    } catch (failure) {
      if (alive.current) {
        setPhase("blocked");
        setMessage(isForbiddenRequest(failure) ? "workingSummaryForbidden" : failure instanceof ApiError && failure.code === "stale_input" ? "workingSummaryStale" : "workingSummaryUnknown");
      }
    } finally {busy.current = false; onSavePendingChange?.(false);}
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
        if (!context) {
          initialDraft.current = bound(item.working_summary) ? item.working_summary!.text : item.draft_text;
          updateDraft(initialDraft.current);
        }
        setPhase("ready");setMessage("workingSummaryChecked");
      }
    } catch (failure) {if (alive.current) {setPhase("blocked"); setMessage(isForbiddenRequest(failure) ? "workingSummaryForbidden" : "workingSummaryCheckFailed");}}
    finally {busy.current = false;}
  }
  return <div role="dialog" aria-labelledby={`${id}-heading`} aria-describedby={`${id}-help`}
    className="working-summary-session" onKeyDown={event => {
      if (activeRef.current && event.key === "Escape") {event.stopPropagation(); if (phase !== "saving") close();}
    }}>
    <h4 id={`${id}-heading`} ref={heading} tabIndex={-1}>{t(provenance ? "taskWorkingSummaryOpen" : "workingSummaryReview")} <code>{selectionId}</code></h4>
    <p id={`${id}-help`} className="small muted">{t("workingSummaryHelp")}{provenance && <> {t("taskWorkingSummaryPending")}</>}</p>
    {phase === "loading" && <p role="status">{t("workingSummaryLoading")}</p>}
    {context && <label className="field field-wide">{t("workingSummaryText")}<textarea ref={input} rows={10}
      value={draft} disabled={!active || phase === "saving" || phase === "saved"} onChange={event => {if (activeRef.current) editDraft(event.target.value);}}/></label>}
    {message && <p role={phase === "blocked" ? "alert" : "status"}>{t(message)}</p>}
    {tooLong && <p role="alert">{t("workingSummaryTooLong")}</p>}
    <div className="working-summary-actions">
      <button type="button" className="button" disabled={!active || phase !== "ready" || !submittedText || tooLong} onClick={() => void save()}>
        {t(phase === "saving" ? "workingSummarySaving" : "workingSummarySave")}</button>
      {(phase === "blocked" || phase === "checking") && <button type="button" className="button secondary"
        disabled={!active || phase === "checking"} onClick={() => void check()}>{t(phase === "checking" ? "workingSummaryChecking" : "workingSummaryCheck")}</button>}
      <button type="button" className="button secondary" disabled={!active || phase === "saving"} onClick={close}>{t(phase === "saved" ? "workingSummaryClose" : "cancel")}</button>
    </div>
  </div>;
}

/** Task candidates retain their own provenance; they are never registered observations. */
export function TaskWorkingSummaryEditor({task, t, onSaved, active = true, onSessionChange, onSavePendingChange}: {task:Task; t:Translate; onSaved:()=>Promise<void>; active?:boolean; onSessionChange?:(open:boolean)=>void; onSavePendingChange?:(pending:boolean)=>void}) {
  const [recoveries, setRecoveries] = useState<RecoveryDraft[]>([]);
  const recoveryChange = useCallback((update: RecoveryUpdate) => {
    setRecoveries(previous => {
      if (update.kind === "capture") return [...previous.filter(item => item.id !== update.draft.id), update.draft];
      if (update.kind === "discard") return previous.filter(item => item.id !== update.id);
      return previous.map(item => item.id === update.id ? {...item, invalidated:true} : item);
    });
  }, []);
  const result = task.result as {status?:string; semantic_acceptance?:string; input_hash?:string; artifacts?:{path?:string;sha256?:string}[]} | undefined;
  const sourceId = task.request?.research_draft?.source_pack?.source_record_id;
  const files = Array.isArray(result?.artifacts) ? result.artifacts.filter(a => a && typeof a.path === "string" && /^proposals\/[^/]+\/draft\.md$/.test(a.path)) : [];
  const provenance:TaskProvenance | undefined = task.operation === "paper-abstract-draft" && task.status === "awaiting_human" && result?.status === "completed" &&
      result.semantic_acceptance === "pending" && task.project_id && sourceId && hash(task.action_hash) && hash(result.input_hash) &&
      files.length === 1 && hash(files[0].sha256)
    ? {kind:"abstract-task",version:1,project_id:task.project_id,source_record_id:sourceId,
      task_id:task.id,input_hash:result.input_hash,action_hash:task.action_hash,draft_sha256:files[0].sha256} : undefined;
  return <>
    {provenance && <TaskSummaryChoice key={JSON.stringify(provenance)} provenance={provenance} t={t} onSaved={onSaved} active={active} onSessionChange={onSessionChange} onSavePendingChange={onSavePendingChange} onRecoveryChange={recoveryChange}/>}
    {recoveries.filter(item => item.invalidated && item.provenance.task_id === task.id && item.provenance.project_id === task.project_id).map(item =>
      <section key={item.id} className="working-summary-session" aria-label={t("taskWorkingSummaryRecovery")}>
        <h4>{t("taskWorkingSummaryRecovery")}</h4>
        <p role="status">{t("taskWorkingSummaryRecoveryHelp")}</p>
        <p className="small muted">{t("taskWorkingSummaryRecoveryLifetime")}</p>
        <p className="small">{t("sourceId")}: <code>{item.provenance.source_record_id}</code></p>
        <label className="field field-wide">{t("taskWorkingSummaryRetainedText")}<textarea rows={10} readOnly value={item.text}/></label>
        <details><summary>{t("taskWorkingSummaryOriginalBinding")}</summary>
          <ReadText value={JSON.stringify(item.provenance, null, 2)}/><code>{item.revision}</code>
        </details>
        <button type="button" className="button secondary" disabled={!active} onClick={() => {if(active)recoveryChange({kind:"discard",id:item.id});}}>{t("taskWorkingSummaryDiscardRecovery")}</button>
      </section>)}
  </>;
}
function TaskSummaryChoice({provenance,t,onSaved,active,onSessionChange,onSavePendingChange,onRecoveryChange}:{provenance:TaskProvenance;t:Translate;onSaved:()=>Promise<void>;active:boolean;onSessionChange?:(open:boolean)=>void; onSavePendingChange?:(pending:boolean)=>void; onRecoveryChange:(update:RecoveryUpdate)=>void}) {
  const [open,setOpen] = useState(false);
  useEffect(() => {
    onSessionChange?.(open);
    return () => onSessionChange?.(false);
  }, [open, onSessionChange]);
  const opener = useRef<HTMLButtonElement>(null);
  const activeRef = useRef(active); activeRef.current = active;
  return <section className="working-summary-editor" aria-label={t("taskWorkingSummaryOpen")}>
    <p className="small muted">{t("taskWorkingSummaryPending")}</p>
    <button type="button" ref={opener} className="button secondary" disabled={!active || open} onClick={()=>{if(activeRef.current)setOpen(true);}}>{t("taskWorkingSummaryOpen")}</button>
    {open && <SummarySession sourceId={provenance.source_record_id} projectId={provenance.project_id}
      selection={{kind:"task",provenance}} active={active} t={t} onSaved={onSaved} onSavePendingChange={onSavePendingChange} onRecoveryChange={onRecoveryChange} onClose={()=>{
        if(!activeRef.current)return;
        setOpen(false); queueMicrotask(()=>{if(activeRef.current && opener.current?.isConnected)opener.current.focus();});
      }}/>}
  </section>;
}
