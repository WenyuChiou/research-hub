import { useEffect, useMemo, useRef, useState } from "react";
import { buildBibtexExport, buildNotebookLmSourcePack } from "./AgentHandoffModal";
import { ApiError, api, recoverCsrfIfForbidden, segment } from "./api";
import { BibtexIcon, BrandMark, CslJsonIcon, RisEndnoteIcon } from "./BrandIcons";
import {
  buildApaBibliography,
  buildCiteKeyMap,
  buildCslJsonExport,
  buildObsidianUri,
  buildRisExport,
  resolveObsidianVaultName,
} from "./citations";
import type { IntegrationLiveState, Locale, ResearchRecord, Workspace } from "./types";

export interface NotebookLmBundleResponse {
  ok: true;
  export_dir: string;
  pack_file: string;
  manifest_file?: string;
  source_files?: string[];
  source_count: number;
  full_text_count: number;
  abstract_or_metadata_count: number;
  nlm_status: string;
  notebook_url: string;
}

export interface NotebookLmUploadResponse {
  ok: true;
  status: "uploaded" | "partial_failure" | "failed";
  notebook_id: string;
  notebook_name: string;
  notebook_url: string;
  uploaded_count: number;
  skipped_duplicates: number;
  failed_count: number;
  failed_sources?: { source_id: string; title: string; error: string }[];
  receipt_file?: string;
}

export interface ZoteroSyncItemPlan {
  id: string;
  title: string;
  doi: string;
  action: "create" | "skip_duplicate" | "missing_credentials" | "failed";
}

export interface ZoteroFailedItem {
  id: string;
  title: string;
  doi: string;
  reason: string;
}

export interface ZoteroSyncResponse {
  ok: true;
  status: "missing_credentials" | "ready" | "synced" | "partial_failure" | "failed";
  dry_run: boolean;
  candidate_count?: number;
  would_create?: number;
  duplicates?: number;
  created_count?: number;
  failed_count?: number;
  skipped_duplicates?: number;
  created_keys?: string[];
  collection_key?: string | null;
  collection_name?: string;
  library_url?: string;
  failed_items?: ZoteroFailedItem[];
  destination_library?: string;
  source_revisions?: Record<string, string>;
  plan_digest?: string;
  items?: ZoteroSyncItemPlan[];
}

export interface ObsidianPackResponse {
  ok: true;
  export_dir: string;
  base_file: string;
  note_files?: string[];
  note_count: number;
  obsidian_vault_name: string;
}

export interface SyncHooksPanelProps {
  projectId?: string;
  projectTitle?: string;
  sources: ResearchRecord[];
  selectedIds?: readonly string[] | ReadonlySet<string>;
  workspace?: Workspace | null;
  liveIntegrations?: IntegrationLiveState | null;
  locale?: Locale;
  onOpenSetup?: () => void;
  compact?: boolean;
}

type LedTone = "ok" | "configured" | "warn" | "error" | "idle";

const LABELS = {
  "zh-TW": {
    hubTitle: "已連接軟體同步與匯出中樞",
    selectedCount: (n: number) => `已選 ${n} 篇`,
    totalCount: (n: number) => `專案 ${n} 篇`,
    scopeSplit: (full: number, rest: number) => `全文 ${full} · 摘要/書目 ${rest}`,
    openSetup: "設定金鑰",
    noSources: "尚無可同步的文獻",
    nlmSignedIn: "已登入",
    nlmNeedSignIn: "需登入",
    nlmLocalReady: "本機封裝就緒",
    nlmBuildBtn: "產生 NLM 匯入包",
    nlmBuilding: "封裝中…",
    nlmUploadBtn: "☁ 上傳至 NotebookLM",
    nlmUploading: "上傳中…",
    nlmUploadReceipt: (uploaded: number, skipped: number) =>
      skipped > 0
        ? `✓ 已上傳 ${uploaded} 篇至 NotebookLM（略過 ${skipped} 篇重複）`
        : `✓ 已上傳 ${uploaded} 篇至 NotebookLM`,
    nlmPartialReceipt: (uploaded: number, failed: number) =>
      `⚠ 已上傳 ${uploaded} 篇至 NotebookLM，另有 ${failed} 篇上傳失敗`,
    nlmFailedReceipt: (failed: number) =>
      `✕ NotebookLM 上傳失敗（${failed} 篇未能上傳）`,
    nlmReceipt: (total: number, full: number, rest: number) =>
      `✓ ${total} 篇已封裝 · 全文 ${full} / 摘要 ${rest}`,
    nlmOpenBtn: "開啟 NotebookLM ↗",
    nlmOpenNotebookBtn: "開啟此筆記本 ↗",
    nlmOfflineMdBtn: "下載 .md 來源包",
    zotConnected: "已連線",
    zotConfigured: "金鑰就緒",
    zotAuthFailed: "驗證失敗",
    zotUnconfigured: "未設定 API",
    zotDryRunBtn: "預覽同步 (Dry-run)",
    zotPreviewing: "比對中…",
    zotDiffPill: (add: number, dup: number) => `新增 ${add} 篇 · 略過重複 ${dup} 篇`,
    zotConfirmBtn: "確認寫入 Zotero",
    zotSyncing: "寫入中…",
    zotSyncedReceipt: (created: number, skipped: number) =>
      skipped > 0
        ? `✓ 已同步 ${created} 篇至 Zotero · 略過 ${skipped} 篇`
        : `✓ 已同步 ${created} 篇至 Zotero`,
    zotPartialReceipt: (created: number, failed: number) =>
      `⚠ 已同步 ${created} 篇 · ${failed} 篇被 Zotero 拒絕（請重試）`,
    zotFailedReceipt: (failed: number) =>
      `✕ Zotero 同步失敗（${failed} 篇被拒絕，未寫入任何項目）`,
    zotAllDuplicates: "所選文獻皆已存在於 Zotero",
    zotOpenCollectionBtn: "開啟 Collection ↗",
    zotMissingCredsHint: "尚未設定 Zotero API 金鑰，可直接下載 .ris 匯入檔",
    zotRisFallbackBtn: "下載 .ris 匯入檔",
    obsVerified: "Vault 已驗證",
    obsVaultReady: (name: string) => `Vault · ${name}`,
    obsPackReady: "工作區封裝就緒",
    obsPackBtn: "產生筆記與 .base 資料庫",
    obsPacking: "產生中…",
    obsReceipt: (count: number) => `✓ 已產生 ${count} 篇筆記 + .base`,
    obsOpenBtn: "在 Obsidian 開啟 ↗",
    refCardTitle: "書目與寫作軟體",
    refReadyPill: "4 種格式即點即用",
    refBibBtn: "Overleaf .bib",
    refRisBtn: "EndNote .ris",
    refCslBtn: "Quarto CSL-JSON",
    refApaBtn: "APA 7th",
    refDownloaded: (fmt: string) => `✓ 已匯出 ${fmt}`,
    refApaCopied: "✓ 已複製 APA 7th 引文",
    localDisabledHint: "目前伺服器未啟用本機整合路由，可使用右側標準書目匯出",
  },
  en: {
    hubTitle: "Connected Software Sync & Export Hub",
    selectedCount: (n: number) => `${n} selected`,
    totalCount: (n: number) => `${n} project sources`,
    scopeSplit: (full: number, rest: number) => `Full-text ${full} · Abstract/Meta ${rest}`,
    openSetup: "Configure keys",
    noSources: "No sources available to sync",
    nlmSignedIn: "Signed in",
    nlmNeedSignIn: "Sign-in needed",
    nlmLocalReady: "Local pack ready",
    nlmBuildBtn: "Build NLM Pack",
    nlmBuilding: "Bundling…",
    nlmUploadBtn: "☁ Upload to NotebookLM",
    nlmUploading: "Uploading…",
    nlmUploadReceipt: (uploaded: number, skipped: number) =>
      skipped > 0
        ? `✓ Uploaded ${uploaded} to NotebookLM (${skipped} skipped)`
        : `✓ Uploaded ${uploaded} to NotebookLM`,
    nlmPartialReceipt: (uploaded: number, failed: number) =>
      `⚠ Uploaded ${uploaded} to NotebookLM (${failed} failed)`,
    nlmFailedReceipt: (failed: number) =>
      `✕ NotebookLM upload failed (${failed} source(s) failed)`,
    nlmReceipt: (total: number, full: number, rest: number) =>
      `✓ ${total} packed · Full-text ${full} / Abstract ${rest}`,
    nlmOpenBtn: "Open NotebookLM ↗",
    nlmOpenNotebookBtn: "Open Notebook ↗",
    nlmOfflineMdBtn: "Download .md Pack",
    zotConnected: "Ready",
    zotConfigured: "API configured",
    zotAuthFailed: "Auth error",
    zotUnconfigured: "API not set",
    zotDryRunBtn: "Preview Sync (Dry-run)",
    zotPreviewing: "Checking…",
    zotDiffPill: (add: number, dup: number) => `+${add} new · ${dup} duplicate(s) skipped`,
    zotConfirmBtn: "Confirm Write to Zotero",
    zotSyncing: "Writing…",
    zotSyncedReceipt: (created: number, skipped: number) =>
      skipped > 0
        ? `✓ Synced ${created} to Zotero · ${skipped} skipped`
        : `✓ Synced ${created} to Zotero`,
    zotPartialReceipt: (created: number, failed: number) =>
      `⚠ Synced ${created} to Zotero · ${failed} rejected (retry failed items)`,
    zotFailedReceipt: (failed: number) =>
      `✕ Zotero write failed (${failed} item(s) rejected; 0 created)`,
    zotAllDuplicates: "All selected items already exist in Zotero",
    zotOpenCollectionBtn: "Open Collection ↗",
    zotMissingCredsHint: "Zotero API key not configured — use 1-click .ris export",
    zotRisFallbackBtn: "Download .ris",
    obsVerified: "Vault verified",
    obsVaultReady: (name: string) => `Vault · ${name}`,
    obsPackReady: "Workspace pack ready",
    obsPackBtn: "Generate Notes & .base",
    obsPacking: "Generating…",
    obsReceipt: (count: number) => `✓ ${count} note(s) + .base ready`,
    obsOpenBtn: "Open in Obsidian ↗",
    refCardTitle: "Reference & Writing Apps",
    refReadyPill: "4 instant formats",
    refBibBtn: "Overleaf .bib",
    refRisBtn: "EndNote .ris",
    refCslBtn: "Quarto CSL-JSON",
    refApaBtn: "APA 7th",
    refDownloaded: (fmt: string) => `✓ Exported ${fmt}`,
    refApaCopied: "✓ Copied APA 7th bibliography",
    localDisabledHint: "Local integration routes disabled in this mode; direct exports remain ready",
  },
} as const;

function safeExternalHref(raw: string | undefined | null, fallback = ""): string {
  if (!raw || typeof raw !== "string") return fallback;
  try {
    const parsed = new URL(raw);
    if (parsed.protocol === "https:" || parsed.protocol === "http:") {
      return parsed.toString();
    }
  } catch {
    /* Reject invalid/non-http(s) hrefs. */
  }
  return fallback;
}

function rawScopeOf(record: ResearchRecord): string {
  const rl = record.data.reading_level;
  const rs = record.data.reading_scope;
  if (typeof rl === "string" && rl.trim()) return rl.trim();
  if (typeof rs === "string" && rs.trim()) return rs.trim();
  return "metadata";
}

function triggerTextDownload(filename: string, content: string, mime: string): void {
  if (typeof URL.createObjectURL !== "function") return;
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => {
    if (typeof URL.revokeObjectURL === "function") {
      URL.revokeObjectURL(url);
    }
  }, 1000);
}

function formatErrorText(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error && err.message) return err.message;
  return "Request failed";
}

function FormatGlyph({ kind }: { kind: "bib" | "ris" | "csl" | "apa" | "refs" }) {
  if (kind === "bib") {
    return <BibtexIcon size={15} />;
  }
  if (kind === "ris") {
    return <RisEndnoteIcon size={15} />;
  }
  if (kind === "csl") {
    return <CslJsonIcon size={15} />;
  }
  if (kind === "apa") {
    return (
      <svg width="15" height="15" viewBox="0 0 20 20" fill="none" aria-hidden="true">
        <path
          d="M4.5 6.5h11M6.8 10h8.7M6.8 13.5h6.7"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
        />
      </svg>
    );
  }
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M5 4.5h10.5L19 8v11.5a1.5 1.5 0 0 1-1.5 1.5H5a1.5 1.5 0 0 1-1.5-1.5v-13A1.5 1.5 0 0 1 5 4.5Z"
        fill="currentColor"
        fillOpacity="0.12"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinejoin="round"
      />
      <path d="M8 11h8M8 14.5h8M8 18h5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

function SyncStatusPill({ tone, label }: { tone: LedTone; label: string }) {
  return (
    <span className={`sync-status-pill is-${tone}`}>
      <span className={`status-led sync-led is-${tone}`} aria-hidden="true" />
      <span>{label}</span>
    </span>
  );
}

export function SyncHooksPanel({
  projectId,
  projectTitle,
  sources,
  selectedIds,
  workspace,
  liveIntegrations,
  locale,
  onOpenSetup,
  compact = false,
}: SyncHooksPanelProps) {
  const resolvedLocale: Locale =
    locale ??
    (typeof document !== "undefined" && document.documentElement.lang === "en" ? "en" : "zh-TW");
  const copy = LABELS[resolvedLocale];

  const selectedSet = useMemo(() => {
    if (!selectedIds) return new Set<string>();
    return new Set<string>(Array.from(selectedIds).filter((id) => Boolean(id)));
  }, [selectedIds]);

  const allSourceRecords = useMemo(
    () => sources.filter((record) => record.kind === "source"),
    [sources],
  );

  const explicitSelectedRecords = useMemo(() => {
    if (selectedSet.size === 0) return [];
    return allSourceRecords.filter((record) => selectedSet.has(record.id));
  }, [allSourceRecords, selectedSet]);

  const targetSources = useMemo(() => {
    if (explicitSelectedRecords.length > 0) return explicitSelectedRecords;
    return allSourceRecords.filter((record) => record.data.archived !== true);
  }, [allSourceRecords, explicitSelectedRecords]);

  const payloadSourceIds = useMemo(() => {
    if (explicitSelectedRecords.length > 0) {
      return explicitSelectedRecords.map((record) => record.id);
    }
    return undefined;
  }, [explicitSelectedRecords]);

  const zotTargetSig = `${liveIntegrations?.credentials?.zotero_library_type ?? ""}:${liveIntegrations?.credentials?.zotero_library_id ?? ""}`;

  const selectionSignature = useMemo(() => {
    const modePrefix = payloadSourceIds
      ? `sel:${payloadSourceIds.join(",")}`
      : `all:${targetSources.map((s) => s.id).join(",")}`;
    const revToken = targetSources
      .map((record) => {
        const data = record.data ?? {};
        const sortedEntries = Object.keys(data)
          .sort()
          .map((k) => [k, data[k]]);
        const rev = (record as { revision?: string | number }).revision ?? "";
        return `${record.id}@${rev}:${JSON.stringify(sortedEntries)}`;
      })
      .join(";");
    return `${projectId || ""}|${zotTargetSig}|${modePrefix}|${revToken}`;
  }, [projectId, zotTargetSig, payloadSourceIds, targetSources]);
  const selectionSigRef = useRef(selectionSignature);
  selectionSigRef.current = selectionSignature;
  const selectionEpochRef = useRef(0);

  const [nlmBusy, setNlmBusy] = useState(false);
  const [nlmUploadCount, setNlmUploadCount] = useState(0);
  const nlmUploadBusy = nlmUploadCount > 0;
  const [nlmResult, setNlmResult] = useState<NotebookLmBundleResponse | null>(null);
  const [nlmUploadResult, setNlmUploadResult] = useState<NotebookLmUploadResponse | null>(null);
  const [nlmError, setNlmError] = useState<string | null>(null);

  const [zotPreviewBusy, setZotPreviewBusy] = useState(false);
  const [zotWriteCount, setZotWriteCount] = useState(0);
  const zotBusy: "preview" | "sync" | null =
    zotWriteCount > 0 ? "sync" : zotPreviewBusy ? "preview" : null;
  const [zotPreviewEntry, setZotPreviewEntry] = useState<{
    sig: string;
    payloadSourceIds: string[] | undefined;
    data: ZoteroSyncResponse;
  } | null>(null);
  const [zotSynced, setZotSynced] = useState<ZoteroSyncResponse | null>(null);
  const [zotError, setZotError] = useState<string | null>(null);

  const [obsBusy, setObsBusy] = useState(false);
  const [obsResult, setObsResult] = useState<ObsidianPackResponse | null>(null);
  const [obsError, setObsError] = useState<string | null>(null);

  const [refReceipt, setRefReceipt] = useState<string | null>(null);

  useEffect(() => {
    selectionEpochRef.current += 1;
    setNlmBusy(false);
    setNlmResult(null);
    setNlmUploadResult(null);
    setNlmError(null);
    // Keep zotWriteCount intact across scope switches so an in-flight Zotero write cannot overlap!
    setZotPreviewBusy(false);
    setZotPreviewEntry(null);
    setZotSynced(null);
    setZotError(null);
    setObsBusy(false);
    setObsResult(null);
    setObsError(null);
    setRefReceipt(null);
  }, [selectionSignature]);

  const zotPreview =
    zotPreviewEntry && zotPreviewEntry.sig === selectionSignature ? zotPreviewEntry.data : null;

  const localCap = liveIntegrations?.credentials ?? workspace?.capabilities?.local_integrations;
  // Enabled unless an explicit Workspace object omits local_integrations and no live credentials exist.
  const backendHooksAvailable =
    workspace == null ||
    localCap?.status === "available" ||
    Boolean(liveIntegrations?.credentials);

  const fullTextCount = useMemo(
    () => targetSources.filter((r) => rawScopeOf(r) === "full-text").length,
    [targetSources],
  );
  const abstractOrMetaCount = targetSources.length - fullTextCount;
  const citeKeyMap = useMemo(() => buildCiteKeyMap(targetSources), [targetSources]);
  const safeSlug =
    (projectId || "research-hub").replace(/[^a-z0-9-_]/gi, "-").toLowerCase() || "research-hub";

  // 1. NotebookLM status
  const effectiveNlmStatus = nlmResult?.nlm_status ?? liveIntegrations?.notebooklm?.status;
  const nlmPill: { tone: LedTone; label: string } =
    effectiveNlmStatus === "authenticated"
      ? { tone: "ok", label: copy.nlmSignedIn }
      : effectiveNlmStatus === "expired" || effectiveNlmStatus === "missing"
        ? { tone: "warn", label: copy.nlmNeedSignIn }
        : { tone: "configured", label: copy.nlmLocalReady };

  // 2. Zotero status
  const zoteroExplicitlyMissing =
    zotPreview?.status === "missing_credentials" ||
    liveIntegrations?.zotero?.status === "missing_credentials" ||
    (localCap != null && localCap.zotero_configured === false);

  const zoteroConnectedLive =
    zotSynced?.status === "synced" ||
    zotSynced?.status === "partial_failure" ||
    (liveIntegrations?.zotero != null &&
      ["connected_local_and_web", "connected_web", "connected_local"].includes(
        liveIntegrations.zotero.status,
      ));

  const zotPill: { tone: LedTone; label: string } =
    liveIntegrations?.zotero?.status === "auth_failed"
      ? { tone: "error", label: copy.zotAuthFailed }
      : zoteroConnectedLive
        ? { tone: "ok", label: copy.zotConnected }
        : zoteroExplicitlyMissing
          ? { tone: "idle", label: copy.zotUnconfigured }
          : { tone: "configured", label: copy.zotConfigured };

  // 3. Obsidian status & URI
  const resolvedVaultName =
    obsResult?.obsidian_vault_name || resolveObsidianVaultName(workspace, liveIntegrations);
  const obsidianHref = buildObsidianUri(resolvedVaultName) || "obsidian://open";
  const obsPill: { tone: LedTone; label: string } =
    liveIntegrations?.obsidian?.status === "valid"
      ? { tone: "ok", label: copy.obsVerified }
      : resolvedVaultName
        ? { tone: "configured", label: copy.obsVaultReady(resolvedVaultName) }
        : { tone: "configured", label: copy.obsPackReady };

  async function postIntegrationHook<T>(
    subpath: string,
    payload: Record<string, unknown>,
  ): Promise<T> {
    if (!projectId) {
      throw new Error("Missing project identifier");
    }
    const route = `/projects/${segment(projectId)}/integrations/${subpath}`;
    try {
      return await api<T>(route, payload);
    } catch (err) {
      if (await recoverCsrfIfForbidden(err)) {
        return await api<T>(route, payload);
      }
      throw err;
    }
  }

  async function handleNotebookLmBundle() {
    if (!projectId || targetSources.length === 0 || nlmBusy || nlmUploadBusy) return;
    const reqSig = selectionSignature;
    const reqEpoch = selectionEpochRef.current;
    const reqIds = payloadSourceIds ? [...payloadSourceIds] : undefined;
    setNlmBusy(true);
    setNlmError(null);
    try {
      const payload: Record<string, unknown> = {};
      if (reqIds) payload.selected_source_ids = reqIds;
      const response = await postIntegrationHook<NotebookLmBundleResponse>(
        "notebooklm/bundle",
        payload,
      );
      if (selectionEpochRef.current !== reqEpoch || selectionSigRef.current !== reqSig) return;
      setNlmResult(response);
    } catch (err) {
      if (selectionEpochRef.current !== reqEpoch || selectionSigRef.current !== reqSig) return;
      setNlmError(formatErrorText(err));
    } finally {
      if (selectionEpochRef.current === reqEpoch && selectionSigRef.current === reqSig) {
        setNlmBusy(false);
      }
    }
  }

  async function handleNotebookLmUpload() {
    if (!projectId || targetSources.length === 0 || nlmBusy || nlmUploadBusy) return;
    const reqSig = selectionSignature;
    const reqEpoch = selectionEpochRef.current;
    const reqIds = payloadSourceIds ? [...payloadSourceIds] : undefined;
    setNlmUploadCount((count) => count + 1);
    setNlmError(null);
    setNlmUploadResult(null);
    try {
      const payload: Record<string, unknown> = {};
      if (reqIds) payload.selected_source_ids = reqIds;
      const response = await postIntegrationHook<NotebookLmUploadResponse>(
        "notebooklm/upload",
        payload,
      );
      if (selectionEpochRef.current !== reqEpoch || selectionSigRef.current !== reqSig) return;
      setNlmUploadResult(response);
    } catch (err) {
      if (selectionEpochRef.current !== reqEpoch || selectionSigRef.current !== reqSig) return;
      setNlmError(formatErrorText(err));
    } finally {
      setNlmUploadCount((count) => Math.max(0, count - 1));
    }
  }

  async function handleZoteroDryRun() {
    if (!projectId || targetSources.length === 0 || zotBusy) return;
    const reqSig = selectionSignature;
    const reqEpoch = selectionEpochRef.current;
    const reqIds = payloadSourceIds ? [...payloadSourceIds] : undefined;
    setZotPreviewBusy(true);
    setZotError(null);
    setZotSynced(null);
    try {
      const payload: Record<string, unknown> = { dry_run: true };
      if (reqIds) payload.selected_source_ids = reqIds;
      const response = await postIntegrationHook<ZoteroSyncResponse>("zotero/sync", payload);
      if (selectionEpochRef.current !== reqEpoch || selectionSigRef.current !== reqSig) return;
      setZotPreviewEntry({ sig: reqSig, payloadSourceIds: reqIds, data: response });
    } catch (err) {
      if (selectionEpochRef.current !== reqEpoch || selectionSigRef.current !== reqSig) return;
      setZotError(formatErrorText(err));
    } finally {
      if (selectionEpochRef.current === reqEpoch && selectionSigRef.current === reqSig) {
        setZotPreviewBusy(false);
      }
    }
  }

  async function handleZoteroConfirm() {
    if (!projectId || targetSources.length === 0 || zotBusy) return;
    if (!zotPreviewEntry || zotPreviewEntry.sig !== selectionSignature) return;
    const reqSig = zotPreviewEntry.sig;
    const reqEpoch = selectionEpochRef.current;
    const previewedIds = zotPreviewEntry.payloadSourceIds;
    const previewedRevisions = zotPreviewEntry.data.source_revisions;
    const previewedLibrary = zotPreviewEntry.data.destination_library;
    const previewedPlanDigest = zotPreviewEntry.data.plan_digest;
    setZotWriteCount((count) => count + 1);
    setZotError(null);
    try {
      const payload: Record<string, unknown> = { dry_run: false };
      if (previewedIds) payload.selected_source_ids = previewedIds;
      if (previewedRevisions) payload.expected_revisions = previewedRevisions;
      if (previewedLibrary) payload.expected_library = previewedLibrary;
      if (previewedPlanDigest) payload.expected_plan_digest = previewedPlanDigest;
      const response = await postIntegrationHook<ZoteroSyncResponse>("zotero/sync", payload);
      if (selectionEpochRef.current !== reqEpoch || selectionSigRef.current !== reqSig) return;
      if (response.status === "failed") {
        setZotError(copy.zotFailedReceipt(response.failed_count ?? 1));
        setZotSynced(null);
      } else {
        setZotSynced(response);
        setZotPreviewEntry(null);
      }
    } catch (err) {
      if (selectionEpochRef.current !== reqEpoch || selectionSigRef.current !== reqSig) return;
      if ((err as { code?: string } | null)?.code === "stale_preview") {
        setZotPreviewEntry(null);
      }
      setZotError(formatErrorText(err));
    } finally {
      setZotWriteCount((count) => Math.max(0, count - 1));
    }
  }

  async function handleObsidianPack() {
    if (!projectId || targetSources.length === 0 || obsBusy) return;
    const reqSig = selectionSignature;
    const reqEpoch = selectionEpochRef.current;
    const reqIds = payloadSourceIds ? [...payloadSourceIds] : undefined;
    setObsBusy(true);
    setObsError(null);
    try {
      const payload: Record<string, unknown> = {};
      if (reqIds) payload.selected_source_ids = reqIds;
      const response = await postIntegrationHook<ObsidianPackResponse>("obsidian/pack", payload);
      if (selectionEpochRef.current !== reqEpoch || selectionSigRef.current !== reqSig) return;
      setObsResult(response);
    } catch (err) {
      if (selectionEpochRef.current !== reqEpoch || selectionSigRef.current !== reqSig) return;
      setObsError(formatErrorText(err));
    } finally {
      if (selectionEpochRef.current === reqEpoch && selectionSigRef.current === reqSig) {
        setObsBusy(false);
      }
    }
  }

  function handleRisDownload() {
    if (!targetSources.length) return;
    triggerTextDownload(
      `${safeSlug}-${targetSources.length}.ris`,
      buildRisExport(targetSources),
      "application/x-research-info-systems;charset=utf-8",
    );
    setRefReceipt(copy.refDownloaded(".ris"));
  }

  function handleBibDownload() {
    if (!targetSources.length) return;
    triggerTextDownload(
      `${safeSlug}-${targetSources.length}.bib`,
      buildBibtexExport(targetSources, citeKeyMap),
      "application/x-bibtex;charset=utf-8",
    );
    setRefReceipt(copy.refDownloaded(".bib"));
  }

  function handleCslDownload() {
    if (!targetSources.length) return;
    triggerTextDownload(
      `${safeSlug}-${targetSources.length}.csl.json`,
      buildCslJsonExport(targetSources, citeKeyMap),
      "application/vnd.citationstyles.csl+json;charset=utf-8",
    );
    setRefReceipt(copy.refDownloaded("CSL-JSON"));
  }

  async function handleApaExport() {
    if (!targetSources.length) return;
    const apa = buildApaBibliography(targetSources);
    if (navigator.clipboard?.writeText) {
      try {
        await navigator.clipboard.writeText(apa);
        setRefReceipt(copy.refApaCopied);
        return;
      } catch {
        /* Fall back to text download when clipboard permission is unavailable. */
      }
    }
    triggerTextDownload(`${safeSlug}-apa7.txt`, apa, "text/plain;charset=utf-8");
    setRefReceipt(copy.refDownloaded("APA 7th"));
  }

  function handleOfflineNlmMarkdown() {
    if (!targetSources.length) return;
    triggerTextDownload(
      `notebooklm-${safeSlug}.md`,
      buildNotebookLmSourcePack(targetSources, projectTitle, projectId),
      "text/markdown;charset=utf-8",
    );
  }

  const actionsDisabled = !projectId || targetSources.length === 0 || !backendHooksAvailable;

  return (
    <section
      className={`sync-hooks-hub${compact ? " is-compact" : ""}`}
      aria-label={copy.hubTitle}
    >
      <header className="sync-hooks-header">
        <div className="sync-hooks-title-group">
          <h3 className="sync-hooks-title">{copy.hubTitle}</h3>
          <span className="sync-scope-chip">
            {explicitSelectedRecords.length > 0
              ? copy.selectedCount(explicitSelectedRecords.length)
              : copy.totalCount(targetSources.length)}
          </span>
          {targetSources.length > 0 && (
            <span className="sync-scope-detail">
              {copy.scopeSplit(fullTextCount, abstractOrMetaCount)}
            </span>
          )}
        </div>
        {onOpenSetup && (
          <button
            type="button"
            className="button secondary small sync-setup-btn"
            onClick={onOpenSetup}
          >
            {copy.openSetup}
          </button>
        )}
      </header>

      {!backendHooksAvailable && (
        <p className="sync-hooks-mode-note">{copy.localDisabledHint}</p>
      )}

      <div className="sync-hooks-grid">
        {/* 1. NotebookLM */}
        <article className="sync-hook-card" data-destination="notebooklm">
          <div className="sync-card-top">
            <span className="sync-brand-badge brand-notebooklm">
              <BrandMark brand="notebooklm" size={20} />
              <strong>NotebookLM</strong>
            </span>
            <SyncStatusPill tone={nlmPill.tone} label={nlmPill.label} />
          </div>

          <div className="sync-card-actions">
            {backendHooksAvailable ? (
              <>
                <button
                  type="button"
                  className="button primary small sync-action-btn"
                  disabled={actionsDisabled || nlmBusy || nlmUploadBusy}
                  onClick={handleNotebookLmBundle}
                >
                  {nlmBusy ? copy.nlmBuilding : copy.nlmBuildBtn}
                </button>
                <button
                  type="button"
                  className="button secondary small sync-action-btn"
                  disabled={actionsDisabled || nlmBusy || nlmUploadBusy}
                  onClick={handleNotebookLmUpload}
                >
                  {nlmUploadBusy ? copy.nlmUploading : copy.nlmUploadBtn}
                </button>
              </>
            ) : (
              <button
                type="button"
                className="button secondary small sync-action-btn"
                disabled={targetSources.length === 0}
                onClick={handleOfflineNlmMarkdown}
              >
                {copy.nlmOfflineMdBtn}
              </button>
            )}
            <a
              className="button secondary small sync-ext-link"
              href={safeExternalHref(nlmUploadResult?.notebook_url || nlmResult?.notebook_url, "https://notebooklm.google.com/")}
              target="_blank"
              rel="noopener noreferrer"
            >
              {nlmUploadResult?.notebook_url ? copy.nlmOpenNotebookBtn : copy.nlmOpenBtn}
            </a>
          </div>

          {nlmUploadResult && (
            <div
              className={`sync-receipt ${
                nlmUploadResult.status === "failed"
                  ? "is-error"
                  : nlmUploadResult.status === "partial_failure"
                    ? "is-warn"
                    : "is-ok"
              }`}
              role={nlmUploadResult.status === "failed" ? "alert" : "status"}
            >
              <span className="sync-receipt-text">
                {nlmUploadResult.status === "failed"
                  ? copy.nlmFailedReceipt(nlmUploadResult.failed_count || 1)
                  : nlmUploadResult.status === "partial_failure"
                    ? copy.nlmPartialReceipt(
                        nlmUploadResult.uploaded_count,
                        nlmUploadResult.failed_count,
                      )
                    : copy.nlmUploadReceipt(
                        nlmUploadResult.uploaded_count,
                        nlmUploadResult.skipped_duplicates,
                      )}
              </span>
              {nlmUploadResult.notebook_name && (
                <code className="sync-path-chip">{nlmUploadResult.notebook_name}</code>
              )}
              {nlmUploadResult.failed_sources && nlmUploadResult.failed_sources.length > 0 && (
                <small className="sync-diff-note">
                  {nlmUploadResult.failed_sources
                    .slice(0, 2)
                    .map((s) => `${s.title}: ${s.error}`)
                    .join(" · ")}
                </small>
              )}
            </div>
          )}
          {nlmResult && (
            <div className="sync-receipt is-ok" role="status">
              <span className="sync-receipt-text">
                {copy.nlmReceipt(
                  nlmResult.source_count,
                  nlmResult.full_text_count,
                  nlmResult.abstract_or_metadata_count,
                )}
              </span>
              <code className="sync-path-chip">{nlmResult.export_dir}</code>
            </div>
          )}
          {nlmError && (
            <p className="sync-receipt is-error" role="alert">
              {nlmError}
            </p>
          )}
        </article>

        {/* 2. Zotero */}
        <article className="sync-hook-card" data-destination="zotero">
          <div className="sync-card-top">
            <span className="sync-brand-badge brand-zotero">
              <BrandMark brand="zotero" size={20} />
              <strong>Zotero</strong>
            </span>
            <SyncStatusPill tone={zotPill.tone} label={zotPill.label} />
          </div>

          <div className="sync-card-actions">
            {backendHooksAvailable && (
              <button
                type="button"
                className="button secondary small sync-action-btn"
                disabled={actionsDisabled || zotBusy !== null}
                onClick={handleZoteroDryRun}
              >
                {zotBusy === "preview" ? copy.zotPreviewing : copy.zotDryRunBtn}
              </button>
            )}

            {zotPreview?.status === "ready" && (zotPreview.would_create ?? 0) > 0 && (
              <button
                type="button"
                className="button primary small sync-action-btn"
                disabled={actionsDisabled || zotBusy !== null}
                onClick={handleZoteroConfirm}
              >
                {zotBusy === "sync" ? copy.zotSyncing : copy.zotConfirmBtn}
              </button>
            )}

            {(zoteroExplicitlyMissing || !backendHooksAvailable) && (
              <button
                type="button"
                className="button secondary small sync-action-btn"
                disabled={targetSources.length === 0}
                onClick={handleRisDownload}
              >
                {copy.zotRisFallbackBtn}
              </button>
            )}
          </div>

          {zotPreview?.status === "ready" && (
            <div className="sync-diff-pill" role="status">
              <span>
                {copy.zotDiffPill(zotPreview.would_create ?? 0, zotPreview.duplicates ?? 0)}
              </span>
              {(zotPreview.would_create ?? 0) === 0 && (
                <small className="sync-diff-note">{copy.zotAllDuplicates}</small>
              )}
            </div>
          )}

          {zotPreview?.status === "missing_credentials" && (
            <p className="sync-receipt is-warn" role="status">
              {copy.zotMissingCredsHint}
            </p>
          )}

          {zotSynced && (
            <div
              className={`sync-receipt ${zotSynced.status === "partial_failure" ? "is-warn" : "is-ok"}`}
              role="status"
            >
              <span className="sync-receipt-text">
                {zotSynced.status === "partial_failure"
                  ? copy.zotPartialReceipt(
                      zotSynced.created_count ?? 0,
                      zotSynced.failed_count ?? 0,
                    )
                  : copy.zotSyncedReceipt(
                      zotSynced.created_count ?? 0,
                      zotSynced.skipped_duplicates ?? 0,
                    )}
              </span>
              {zotSynced.collection_name && (
                <code className="sync-path-chip">{zotSynced.collection_name}</code>
              )}
              {safeExternalHref(zotSynced.library_url) && (
                <a
                  className="sync-ext-link small"
                  href={safeExternalHref(zotSynced.library_url)}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {copy.zotOpenCollectionBtn}
                </a>
              )}
            </div>
          )}

          {zotError && (
            <p className="sync-receipt is-error" role="alert">
              {zotError}
            </p>
          )}
        </article>

        {/* 3. Obsidian */}
        <article className="sync-hook-card" data-destination="obsidian">
          <div className="sync-card-top">
            <span className="sync-brand-badge brand-obsidian">
              <BrandMark brand="obsidian" size={20} />
              <strong>Obsidian</strong>
            </span>
            <SyncStatusPill tone={obsPill.tone} label={obsPill.label} />
          </div>

          <div className="sync-card-actions">
            {backendHooksAvailable && (
              <button
                type="button"
                className="button secondary small sync-action-btn"
                disabled={actionsDisabled || obsBusy}
                onClick={handleObsidianPack}
              >
                {obsBusy ? copy.obsPacking : copy.obsPackBtn}
              </button>
            )}
            <a
              className="button secondary small sync-ext-link"
              href={obsidianHref}
              rel="noopener noreferrer"
            >
              {copy.obsOpenBtn}
            </a>
          </div>

          {obsResult && (
            <div className="sync-receipt is-ok" role="status">
              <span className="sync-receipt-text">{copy.obsReceipt(obsResult.note_count)}</span>
              <code className="sync-path-chip">{obsResult.export_dir}</code>
            </div>
          )}
          {obsError && (
            <p className="sync-receipt is-error" role="alert">
              {obsError}
            </p>
          )}
        </article>

        {/* 4. Reference & Writing Software */}
        <article className="sync-hook-card" data-destination="references">
          <div className="sync-card-top">
            <span className="sync-brand-badge brand-references">
              <FormatGlyph kind="refs" />
              <strong>{copy.refCardTitle}</strong>
            </span>
            <SyncStatusPill tone="ok" label={copy.refReadyPill} />
          </div>

          <div className="sync-ref-grid">
            <button
              type="button"
              className="button secondary small sync-ref-btn"
              disabled={targetSources.length === 0}
              onClick={handleBibDownload}
            >
              <FormatGlyph kind="bib" />
              <span>{copy.refBibBtn}</span>
            </button>
            <button
              type="button"
              className="button secondary small sync-ref-btn"
              disabled={targetSources.length === 0}
              onClick={handleRisDownload}
            >
              <FormatGlyph kind="ris" />
              <span>{copy.refRisBtn}</span>
            </button>
            <button
              type="button"
              className="button secondary small sync-ref-btn"
              disabled={targetSources.length === 0}
              onClick={handleCslDownload}
            >
              <FormatGlyph kind="csl" />
              <span>{copy.refCslBtn}</span>
            </button>
            <button
              type="button"
              className="button secondary small sync-ref-btn"
              disabled={targetSources.length === 0}
              onClick={handleApaExport}
            >
              <FormatGlyph kind="apa" />
              <span>{copy.refApaBtn}</span>
            </button>
          </div>

          {refReceipt && (
            <div className="sync-receipt is-ok" role="status">
              <span className="sync-receipt-text">{refReceipt}</span>
            </div>
          )}
        </article>
      </div>
    </section>
  );
}
