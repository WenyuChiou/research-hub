import { useEffect, useRef, useState } from "react";
import { LiteratureLibrary, type CurationStateMap, type SourceCurationInput } from "./LiteratureLibrary";
import { identityMatches } from "./libraryIdentity";
import type { Translate } from "./i18n";
import type {
  IntegrationLiveState,
  ResearchRecord,
  Workspace,
} from "./types";
import type { ObservationReadScope } from "./ObservationPreview";

export interface LibrarySnapshot {
  schema_version: 1;
  captured_at: string;
  vault_label: string;
  read_only: true;
  body_read: false;
  collections: {id: string; name: string; note_count: number}[];
  notes: ResearchRecord[];
}

function validateSnapshot(value: unknown): LibrarySnapshot {
  const item = value as LibrarySnapshot;
  if (!item || item.schema_version !== 1 || item.read_only !== true || item.body_read !== false ||
      typeof item.captured_at !== "string" || !Number.isFinite(Date.parse(item.captured_at)) ||
      !Array.isArray(item.collections) || !Array.isArray(item.notes) || item.notes.length > 1000 ||
      item.notes.some((note) => !note || !/^obsidian:[a-f0-9]{24}$/.test(note.id) || note.kind !== "library-note" || !note.data || note.data.origin !== "obsidian" || note.data.read_only !== true)) {
    throw new Error("Invalid read-only Library snapshot");
  }
  return item;
}

export function LibraryCollection(props: {
  sources: ResearchRecord[]; screenings: ResearchRecord[]; curations?: ResearchRecord[]; t: Translate;
  onScreen: (sourceId: string, decision: string, rationale: string) => Promise<void>;
  onCurate?: (sourceId: string, curation: SourceCurationInput) => Promise<void>;
  onPrepare: (record: ResearchRecord) => void;
  onOpenAddTools?: () => void;
  observationRead?: ObservationReadScope;
  pageSuspended?: boolean;
  categoryHost?: HTMLElement | null;
  onWorkingSummarySaved?: () => Promise<void>;
  workspace?: Workspace | null;
  liveIntegrations?: IntegrationLiveState;
  requestedView?: { mode: "split" | "table"; category?: string; nonce: number };
}) {
  const { t } = props;
  const [snapshot, setSnapshot] = useState<LibrarySnapshot | null>(null);
  const [scope, setScope] = useState("workspace");
  const [pendingView, setPendingView] = useState(props.requestedView);
  const [curationState, setCurationState] = useState<CurationStateMap>({});
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const pending = useRef<AbortController | null>(null);
  const lastViewNonce = useRef(props.requestedView?.nonce ?? 0);
  useEffect(() => () => pending.current?.abort(), []);
  useEffect(() => {
    const nonce = props.requestedView?.nonce ?? 0;
    if (nonce > lastViewNonce.current) {
      lastViewNonce.current = nonce;
      // Only leave read-only Obsidian scope; keep "all" mounted so unsaved
      // workspace working-summary edits are never unmounted via key={scope}.
      setScope((current) => (current === "obsidian" ? "workspace" : current));
      setPendingView(props.requestedView);
    }
  }, [props.requestedView]);
  async function load() {
    if (loading) return;
    const controller = new AbortController();
    pending.current = controller;
    setLoading(true); setFailed(false);
    const timeout = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch("/api/v1/library/snapshot", {signal: controller.signal, headers: {Accept: "application/json"}});
      if (!response.ok) throw new Error("Snapshot unavailable");
      const result = validateSnapshot(await response.json());
      if (controller.signal.aborted) return;
      setSnapshot(result); setScope("obsidian"); setPendingView(undefined);
    } catch {
      if (pending.current === controller) setFailed(true);
    } finally {
      clearTimeout(timeout);
      if (pending.current === controller) { setLoading(false); pending.current = null; }
    }
  }
  const all = [...props.sources, ...(snapshot?.notes ?? [])];
  const visible = scope === "obsidian" ? snapshot?.notes ?? [] : scope === "all" ? all : props.sources;
  return <>
    <section className="library-connection" aria-label={t("libraryConnection")}>
      <div className="library-connection-info">
        <strong>{t("libraryConnection")}</strong>
        {snapshot && (
          <select aria-label={t("libraryScope")} value={scope} onChange={(event) => { setPendingView(undefined); setScope(event.target.value); }}>
            <option value="workspace">{t("libraryWorkspace")} ({props.sources.length})</option>
            <option value="obsidian">{t("libraryObsidian")} ({snapshot.notes.length})</option>
            <option value="all">{t("libraryAll")} ({all.length})</option>
          </select>
        )}
        <details className="library-scope-details">
          <summary>{t("librarySnapshotDetails")}</summary>
          <p>{t("libraryScopeHelp")}</p>
          {snapshot && (
            <p className="small">
              {t("librarySnapshotKind")} · {props.sources.length} {t("libraryWorkspaceSources")} · {snapshot.notes.length} {t("libraryMarkdownNotes")} · {snapshot.collections.length} {t("libraryCollections")} ({t("libraryCaptured")}: {snapshot.captured_at})
            </p>
          )}
        </details>
        {failed && <p role="alert">{snapshot ? t("libraryRetained") : t("libraryUnavailable")}</p>}
      </div>
      <div className="library-connection-actions">
        <button className="button secondary small" disabled={loading} onClick={() => void load()}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
          </svg>
          <span>{loading ? t("loading") : snapshot ? t("libraryReload") : t("libraryLoad")}</span>
        </button>
      </div>
    </section>
    <LiteratureLibrary
      key={scope}
      {...props}
      curationState={curationState}
      onCurationStateChange={setCurationState}
      requestedView={scope !== "obsidian" ? pendingView : undefined}
      sources={visible}
      matches={identityMatches(all)}
    />
  </>;
}
