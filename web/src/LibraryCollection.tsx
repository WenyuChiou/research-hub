import { useEffect, useRef, useState } from "react";
import { LiteratureLibrary } from "./LiteratureLibrary";
import { identityMatches } from "./libraryIdentity";
import type { Translate } from "./i18n";
import type { ResearchRecord } from "./types";

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
  sources: ResearchRecord[]; screenings: ResearchRecord[]; t: Translate;
  onScreen: (sourceId: string, decision: string, rationale: string) => Promise<void>;
  onPrepare: (record: ResearchRecord) => void;
}) {
  const { t } = props;
  const [snapshot, setSnapshot] = useState<LibrarySnapshot | null>(null);
  const [scope, setScope] = useState("workspace");
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const pending = useRef<AbortController | null>(null);
  useEffect(() => () => pending.current?.abort(), []);
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
      setSnapshot(result); setScope("obsidian");
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
      <div>
        <strong>{t("libraryConnection")}</strong>
        {snapshot && <p>{t("librarySnapshotKind")}</p>}
        <details className="library-scope-details"><summary>{t("librarySnapshotDetails")}</summary><p>{t("libraryScopeHelp")}</p>
          {snapshot && <p className="small">{props.sources.length} {t("libraryWorkspaceSources")} · {snapshot.notes.length} {t("libraryMarkdownNotes")} · {snapshot.collections.length} {t("libraryCollections")}<br />{t("libraryCaptured")}: {snapshot.captured_at}</p>}
        </details>
        {failed && <p role="alert">{snapshot ? t("libraryRetained") : t("libraryUnavailable")}</p>}
      </div>
      <button className="button secondary" disabled={loading} onClick={() => void load()}>{loading ? t("loading") : snapshot ? t("libraryReload") : t("libraryLoad")}</button>
      {snapshot && <label>{t("libraryScope")}<select value={scope} onChange={(event) => setScope(event.target.value)}>
        <option value="workspace">{t("libraryWorkspace")} ({props.sources.length})</option>
        <option value="obsidian">{t("libraryObsidian")} ({snapshot.notes.length})</option>
        <option value="all">{t("libraryAll")} ({all.length})</option>
      </select></label>}
    </section>
    <LiteratureLibrary key={scope} {...props} sources={visible} matches={identityMatches(all)} />
  </>;
}
