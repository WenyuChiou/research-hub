import {
  useEffect,
  useId,
  useRef,
  useState,
  type Dispatch,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
  type SetStateAction,
} from "react";
import { createPortal } from "react-dom";
import { BrandMark, type BrandDestination } from "./BrandIcons";
import { buildObsidianUri, resolveObsidianVaultName } from "./citations";
import { obsidianStatusLabel, type Translate } from "./i18n";
import type { IntegrationLiveState, Locale, Workspace } from "./types";
import { NotebookLmAuthControls } from "./NotebookLmAuthControls";
import { ObsidianValidationForm } from "./ObsidianValidationForm";
import { ZoteroLibraryForm } from "./ZoteroLibraryForm";
import "./settings.css";

export type SettingsCategory =
  | "connections"
  | "appearance"
  | "ai-runtime"
  | "privacy";

export type SettingsThemeMode = "light" | "dark" | "system";

type LedTone = "ok" | "configured" | "warn" | "error" | "idle";

function observationTime(value: unknown): string | null {
  if (
    typeof value !== "string" ||
    !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$/.test(value)
  ) {
    return null;
  }
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return null;
  const normalized = date.toISOString();
  return normalized.slice(0, 19) === value.slice(0, 19) ? value : null;
}

function CategoryIcon({ category }: { category: SettingsCategory }) {
  const shared = {
    width: 15,
    height: 15,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.85,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
    focusable: false,
  };
  switch (category) {
    case "connections":
      return (
        <svg {...shared}>
          <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
          <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
        </svg>
      );
    case "appearance":
      return (
        <svg {...shared}>
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2" />
          <path d="M12 20v2" />
          <path d="m4.93 4.93 1.41 1.41" />
          <path d="m17.66 17.66 1.41 1.41" />
          <path d="M2 12h2" />
          <path d="M20 12h2" />
        </svg>
      );
    case "ai-runtime":
      return (
        <svg {...shared}>
          <rect x="4" y="4" width="16" height="16" rx="3" />
          <rect x="9" y="9" width="6" height="6" rx="1" />
          <path d="M9 2v2" />
          <path d="M15 2v2" />
          <path d="M9 20v2" />
          <path d="M15 20v2" />
          <path d="M2 9h2" />
          <path d="M2 15h2" />
          <path d="M20 9h2" />
          <path d="M20 15h2" />
        </svg>
      );
    case "privacy":
      return (
        <svg {...shared}>
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
          <path d="m9 12 2 2 4-4" />
        </svg>
      );
  }
}

function ThemePreviewWireframe({ mode }: { mode: SettingsThemeMode }) {
  if (mode === "light") {
    return (
      <svg
        className="theme-preview-svg"
        viewBox="0 0 136 68"
        fill="none"
        aria-hidden="true"
        focusable="false"
      >
        <rect width="136" height="68" rx="5" fill="#eef2f8" />
        <rect width="30" height="68" rx="4" fill="#151f32" />
        <rect x="5" y="8" width="18" height="4" rx="2" fill="#38bdf8" />
        <rect x="5" y="18" width="20" height="3" rx="1.5" fill="#64748b" />
        <rect x="5" y="25" width="16" height="3" rx="1.5" fill="#475569" />
        <rect x="37" y="8" width="91" height="24" rx="4" fill="#fafcff" stroke="#d5deec" />
        <rect x="43" y="14" width="38" height="4" rx="2" fill="#0e5a72" />
        <rect x="43" y="22" width="66" height="3" rx="1.5" fill="#94a3b8" />
        <rect x="37" y="37" width="43" height="23" rx="4" fill="#fafcff" stroke="#d5deec" />
        <rect x="85" y="37" width="43" height="23" rx="4" fill="#fafcff" stroke="#d5deec" />
        <circle cx="45" cy="45" r="3" fill="#10b981" />
        <circle cx="93" cy="45" r="3" fill="#0e5a72" />
      </svg>
    );
  }
  if (mode === "dark") {
    return (
      <svg
        className="theme-preview-svg"
        viewBox="0 0 136 68"
        fill="none"
        aria-hidden="true"
        focusable="false"
      >
        <rect width="136" height="68" rx="5" fill="#0b111d" />
        <rect width="30" height="68" rx="4" fill="#080d17" />
        <rect x="5" y="8" width="18" height="4" rx="2" fill="#38bdf8" />
        <rect x="5" y="18" width="20" height="3" rx="1.5" fill="#475569" />
        <rect x="5" y="25" width="16" height="3" rx="1.5" fill="#334155" />
        <rect x="37" y="8" width="91" height="24" rx="4" fill="#131d30" stroke="#24334a" />
        <rect x="43" y="14" width="38" height="4" rx="2" fill="#38bdf8" />
        <rect x="43" y="22" width="66" height="3" rx="1.5" fill="#64748b" />
        <rect x="37" y="37" width="43" height="23" rx="4" fill="#131d30" stroke="#24334a" />
        <rect x="85" y="37" width="43" height="23" rx="4" fill="#131d30" stroke="#24334a" />
        <circle cx="45" cy="45" r="3" fill="#34d399" />
        <circle cx="93" cy="45" r="3" fill="#38bdf8" />
      </svg>
    );
  }
  return (
    <svg
      className="theme-preview-svg"
      viewBox="0 0 136 68"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <rect width="68" height="68" fill="#eef2f8" />
      <rect x="68" width="68" height="68" fill="#0b111d" />
      <rect width="26" height="68" fill="#151f32" />
      <rect x="5" y="8" width="15" height="4" rx="2" fill="#38bdf8" />
      <rect x="5" y="18" width="16" height="3" rx="1.5" fill="#64748b" />
      <rect x="32" y="9" width="32" height="22" rx="3.5" fill="#fafcff" stroke="#cbd5e1" />
      <rect x="37" y="15" width="20" height="4" rx="2" fill="#0e5a72" />
      <rect x="72" y="9" width="56" height="22" rx="3.5" fill="#131d30" stroke="#24334a" />
      <rect x="78" y="15" width="28" height="4" rx="2" fill="#38bdf8" />
      <rect x="32" y="37" width="32" height="22" rx="3.5" fill="#fafcff" stroke="#cbd5e1" />
      <rect x="72" y="37" width="56" height="22" rx="3.5" fill="#131d30" stroke="#24334a" />
      <line x1="68" y1="0" x2="68" y2="68" stroke="#38bdf8" strokeWidth="1.2" strokeDasharray="3 2" />
    </svg>
  );
}

/** Categorized Modern Settings Center: Connections, Appearance, AI Runtime, and Privacy/Diagnostics. */
export function IntegrationsSetup({
  workspace,
  t,
  projectId = "",
  liveState,
  onLiveStateChange,
  openRequest = 0,
  syncSlot,
  themeMode,
  onThemeModeChange,
  locale,
  onLocaleChange,
  initialCategory = "connections",
}: {
  workspace: Workspace | null;
  t: Translate;
  projectId?: string;
  liveState?: IntegrationLiveState;
  onLiveStateChange?: Dispatch<SetStateAction<IntegrationLiveState>>;
  openRequest?: number;
  syncSlot?: ReactNode;
  themeMode?: SettingsThemeMode;
  onThemeModeChange?: (mode: SettingsThemeMode) => void;
  locale?: Locale;
  onLocaleChange?: (locale: Locale) => void;
  initialCategory?: SettingsCategory;
}) {
  const [open, setOpen] = useState(false);
  const [activeCategory, setActiveCategory] =
    useState<SettingsCategory>(initialCategory);
  const [internalTheme, setInternalTheme] = useState<SettingsThemeMode>("light");
  const [internalLocale, setInternalLocale] = useState<Locale | null>(null);

  const inferredLocale: Locale = t("cancel") === "取消" ? "zh-TW" : "en";
  const currentLocale: Locale = locale ?? internalLocale ?? inferredLocale;
  const isZh = currentLocale === "zh-TW";
  const currentTheme: SettingsThemeMode = themeMode ?? internalTheme;

  const trigger = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const tabRefs = useRef<Record<SettingsCategory, HTMLButtonElement | null>>({
    connections: null,
    appearance: null,
    "ai-runtime": null,
    privacy: null,
  });
  const panelId = useId();
  const previousProject = useRef(projectId);
  const handledOpenRequest = useRef(openRequest);

  const openPanel = () => {
    setActiveCategory(initialCategory);
    setOpen(true);
  };

  useEffect(() => {
    if (openRequest > handledOpenRequest.current) {
      handledOpenRequest.current = openRequest;
      setActiveCategory(initialCategory);
      setOpen(true);
    }
  }, [openRequest, initialCategory]);

  const close = () => {
    setOpen(false);
    setActiveCategory(initialCategory);
    trigger.current?.focus();
  };

  useEffect(() => {
    if (open) heading.current?.focus();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target;
      if (
        target instanceof Node &&
        !panel.current?.contains(target) &&
        !trigger.current?.contains(target)
      ) {
        setOpen(false);
        setActiveCategory(initialCategory);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        close();
      }
    };
    document.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [open, initialCategory]);

  useEffect(() => {
    const navigate = () => {
      setOpen(false);
      setActiveCategory(initialCategory);
    }; // Never steal focus from newer navigation.
    window.addEventListener("hashchange", navigate);
    window.addEventListener("popstate", navigate);
    return () => {
      window.removeEventListener("hashchange", navigate);
      window.removeEventListener("popstate", navigate);
    };
  }, [initialCategory]);

  useEffect(() => {
    if (previousProject.current !== projectId) {
      setOpen(false);
      setActiveCategory(initialCategory);
    }
    previousProject.current = projectId;
  }, [projectId, initialCategory]);

  const snapshot = workspace?.setup_snapshot;
  const knownSnapshot =
    snapshot?.schema_version === 1 &&
    snapshot.source === "saved_local_setup_snapshot";
  const freshnessLabels = {
    saved: "integrationFreshSaved",
    stale: "integrationFreshStale",
    missing: "integrationFreshMissing",
    invalid: "integrationFreshInvalid",
    clock_skew: "integrationFreshClockSkew",
  } as const;
  const observedAt =
    knownSnapshot &&
    (snapshot.freshness === "saved" || snapshot.freshness === "stale")
      ? observationTime(snapshot.observed_at)
      : null;
  const freshness =
    knownSnapshot &&
    typeof snapshot.freshness === "string" &&
    Object.hasOwn(freshnessLabels, snapshot.freshness)
      ? (snapshot.freshness === "saved" || snapshot.freshness === "stale") &&
        !observedAt
        ? "invalid"
        : snapshot.freshness
      : "invalid";

  const vault = workspace?.capabilities?.obsidian_validation;
  const selectedVault =
    vault?.version === 1 &&
    vault.status === "available" &&
    vault.read_only === true &&
    vault.scope === "startup_selected_exact_vault" &&
    typeof vault.authorized_vault === "string" &&
    Boolean(vault.authorized_vault.trim());

  const localCap =
    liveState?.credentials ?? workspace?.capabilities?.local_integrations;

  const zoteroLiveOk = Boolean(
    liveState?.zotero &&
      ["connected_local_and_web", "connected_web", "connected_local"].includes(
        liveState.zotero.status,
      ),
  );
  const obsidianLiveOk = liveState?.obsidian?.status === "valid";
  const nlmLiveOk = liveState?.notebooklm?.status === "authenticated";

  const zoteroConnectionText = liveState?.zotero
    ? t(
        liveState.zotero.status === "connected_local_and_web"
          ? "integrationZoteroConnectedBoth"
          : liveState.zotero.status === "connected_web"
            ? "integrationZoteroConnectedWeb"
            : liveState.zotero.status === "connected_local"
              ? "integrationZoteroConnectedLocal"
              : liveState.zotero.status === "auth_failed"
                ? "integrationZoteroAuthFailed"
                : liveState.zotero.status === "missing_credentials"
                  ? "integrationZoteroMissingCreds"
                  : "integrationZoteroUnreachable",
      )
    : t("integrationNotChecked");

  const nlmConnectionText = liveState?.notebooklm
    ? t(
        liveState.notebooklm.status === "authenticated"
          ? "integrationNlmAuthenticated"
          : liveState.notebooklm.status === "expired"
            ? "integrationNlmExpired"
            : "integrationNlmMissing",
      )
    : t("integrationNotChecked");

  const obsidianConnectionText = liveState?.obsidian
    ? obsidianStatusLabel(liveState.obsidian, t)
    : t("integrationNotChecked");

  const compactParts: string[] = [];
  if (liveState?.zotero) {
    compactParts.push(
      t(zoteroLiveOk ? "integrationSummaryZoteroOk" : "integrationSummaryZoteroIssue"),
    );
  }
  if (liveState?.obsidian) {
    compactParts.push(
      t(
        obsidianLiveOk
          ? "integrationSummaryObsidianOk"
          : "integrationSummaryObsidianIssue",
      ),
    );
  }
  if (liveState?.notebooklm) {
    compactParts.push(
      t(nlmLiveOk ? "integrationSummaryNlmOk" : "integrationSummaryNlmIssue"),
    );
  }
  const compactSummaryText = compactParts.length
    ? compactParts.join(" · ")
    : t("integrationCompact");

  const hasLiveProbe = Boolean(
    liveState?.zotero || liveState?.obsidian || liveState?.notebooklm,
  );
  const hasLiveIssue = Boolean(
    (liveState?.zotero && !zoteroLiveOk) ||
      (liveState?.obsidian && !obsidianLiveOk) ||
      (liveState?.notebooklm && !nlmLiveOk),
  );

  const statuses = {
    passed: "snapshotPassed",
    failed: "snapshotFailed",
    cancelled: "snapshotCancelled",
    skipped: "snapshotSkipped",
    unknown: "snapshotUnknown",
  } as const;

  const services = [
    [
      "vault",
      "Obsidian",
      "https://help.obsidian.md/manage-vaults",
      "integrationVault",
    ],
    [
      "zotero",
      "Zotero",
      "https://www.zotero.org/settings/keys",
      "integrationZotero",
    ],
    [
      "notebooklm_auth",
      "NotebookLM",
      "https://notebook.google.com/",
      "integrationNlm",
    ],
  ] as const;

  const connectionsLed: LedTone = hasLiveIssue
    ? "warn"
    : hasLiveProbe
      ? "ok"
      : selectedVault ||
          localCap?.zotero_configured ||
          localCap?.nlm_state_present
        ? "configured"
        : "idle";

  const codexCap = workspace?.capabilities?.codex;
  const writingCap = workspace?.capabilities?.writing;
  const approvalCap = workspace?.capabilities?.approval;
  const aiAnyAvailable =
    codexCap?.status === "available" ||
    writingCap?.status === "available" ||
    approvalCap?.status === "available";
  const aiRuntimeLed: LedTone = aiAnyAvailable
    ? "ok"
    : workspace
      ? "configured"
      : "idle";

  const snapshotHasFailure =
    knownSnapshot &&
    freshness === "saved" &&
    Object.values(snapshot?.components ?? {}).some((val) => val === "failed");
  const privacyLed: LedTone = snapshotHasFailure ? "warn" : "ok";

  const categories: {
    id: SettingsCategory;
    label: string;
    led: LedTone;
  }[] = [
    {
      id: "connections",
      label: isZh ? "連線與同步" : "Connections & Sync",
      led: connectionsLed,
    },
    {
      id: "appearance",
      label: isZh ? "外觀與語言" : "Appearance & Language",
      led: currentTheme === "light" ? "idle" : "configured",
    },
    {
      id: "ai-runtime",
      label: isZh ? "AI 執行與審核" : "AI & Review Gate",
      led: aiRuntimeLed,
    },
    {
      id: "privacy",
      label: isZh ? "安全與系統診斷" : "Diagnostics & Privacy",
      led: privacyLed,
    },
  ];

  const handleTabKeyDown = (
    event: ReactKeyboardEvent<HTMLButtonElement>,
    index: number,
  ) => {
    const order = categories.map((item) => item.id);
    let nextIndex = -1;
    if (event.key === "ArrowDown" || event.key === "ArrowRight") {
      nextIndex = (index + 1) % order.length;
    } else if (event.key === "ArrowUp" || event.key === "ArrowLeft") {
      nextIndex = (index - 1 + order.length) % order.length;
    } else if (event.key === "Home") {
      nextIndex = 0;
    } else if (event.key === "End") {
      nextIndex = order.length - 1;
    }
    if (nextIndex >= 0) {
      event.preventDefault();
      const nextCat = order[nextIndex];
      setActiveCategory(nextCat);
      tabRefs.current[nextCat]?.focus();
    }
  };

  const handleThemeChange = (next: SettingsThemeMode) => {
    if (themeMode === undefined) setInternalTheme(next);
    onThemeModeChange?.(next);
  };

  const handleLocaleChange = (next: Locale) => {
    if (locale === undefined) setInternalLocale(next);
    onLocaleChange?.(next);
  };

  const summaryItems: {
    brand: BrandDestination;
    name: string;
    led: LedTone;
    text: string;
  }[] = [
    {
      brand: "obsidian",
      name: "Obsidian",
      led: liveState?.obsidian
        ? obsidianLiveOk
          ? "ok"
          : "warn"
        : selectedVault || localCap?.obsidian_vault_configured
          ? "configured"
          : "idle",
      text: liveState?.obsidian
        ? t(
            obsidianLiveOk
              ? "integrationSummaryObsidianOk"
              : "integrationSummaryObsidianIssue",
          )
        : selectedVault || localCap?.obsidian_vault_configured
          ? isZh
            ? "已授權唯讀"
            : "Scoped read-only"
          : isZh
            ? "本機待命"
            : "Local standby",
    },
    {
      brand: "zotero",
      name: "Zotero",
      led: liveState?.zotero
        ? zoteroLiveOk
          ? "ok"
          : "warn"
        : localCap?.zotero_configured
          ? "configured"
          : "idle",
      text: liveState?.zotero
        ? t(
            zoteroLiveOk
              ? "integrationSummaryZoteroOk"
              : "integrationSummaryZoteroIssue",
          )
        : localCap?.zotero_configured
          ? isZh
            ? "金鑰已加密"
            : "Key saved"
          : isZh
            ? "本機待命"
            : "Local standby",
    },
    {
      brand: "notebooklm",
      name: "NotebookLM",
      led: liveState?.notebooklm
        ? nlmLiveOk
          ? "ok"
          : "warn"
        : localCap?.nlm_state_present
          ? "configured"
          : "idle",
      text: liveState?.notebooklm
        ? t(nlmLiveOk ? "integrationSummaryNlmOk" : "integrationSummaryNlmIssue")
        : localCap?.nlm_state_present
          ? isZh
            ? "階段已儲存"
            : "Session saved"
          : isZh
            ? "選用登入"
            : "Optional",
    },
  ];

  const snapshotTiles = [
    ["environment", "snapshotEnvironment"],
    ["vault", "snapshotVault"],
    ["zotero", "snapshotZotero"],
    ["notebooklm_auth", "snapshotNlm"],
    ["llm_cli", "snapshotCli"],
    ["skills", "snapshotSkills"],
  ] as const;

  return (
    <>
      <div className="integration-entry">
        <button
          ref={trigger}
          type="button"
          className="button secondary icon-btn"
          title={compactSummaryText}
          aria-label={t("integrationsSetup")}
          data-tooltip={t("integrationsSetup")}
          data-tooltip-pos="top-start"
          aria-expanded={open}
          aria-controls={open ? panelId : undefined}
          onClick={() => (open ? close() : openPanel())}
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
            focusable="false"
          >
            <circle cx="12" cy="12" r="3" />
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
          </svg>
          {hasLiveProbe && (
            <span
              className={`setup-dot ${hasLiveIssue ? "warn" : "ok"}`}
              aria-hidden="true"
            />
          )}
        </button>
      </div>
      {open &&
        createPortal(
          <section
            ref={panel}
            id={panelId}
            role="dialog"
            aria-modal="false"
            aria-labelledby={panelId + "-title"}
            className="integrations-panel settings-center"
            onKeyDown={(event) => {
              if (event.key === "Escape") {
                event.stopPropagation();
                close();
              }
            }}
          >
            <header className="integrations-panel-header">
              <div className="settings-header-title-group">
                <span className="settings-header-glyph" aria-hidden="true">
                  <svg
                    width="14"
                    height="14"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <circle cx="12" cy="12" r="3" />
                    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
                  </svg>
                </span>
                <h2 ref={heading} id={panelId + "-title"} tabIndex={-1}>
                  {t("integrationsSetup")}
                </h2>
                <span className="settings-header-pill">
                  <span className="settings-led is-ok" aria-hidden="true" />
                  <span>127.0.0.1</span>
                </span>
              </div>
              <button
                type="button"
                className="button secondary small icon-btn"
                onClick={close}
                aria-label={t("integrationClose")}
                data-tooltip={t("integrationClose")}
                data-tooltip-pos="bottom-end"
              >
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  aria-hidden="true"
                  focusable="false"
                >
                  <path d="M18 6 6 18" />
                  <path d="m6 6 12 12" />
                </svg>
              </button>
            </header>

            <div className="settings-center-body">
              <nav
                className="settings-nav-rail"
                aria-label={isZh ? "設定分類" : "Settings categories"}
              >
                <div
                  role="tablist"
                  aria-orientation="vertical"
                  className="settings-tablist"
                >
                  {categories.map((cat, idx) => {
                    const selected = activeCategory === cat.id;
                    return (
                      <button
                        key={cat.id}
                        ref={(el) => {
                          tabRefs.current[cat.id] = el;
                        }}
                        id={`${panelId}-tab-${cat.id}`}
                        type="button"
                        role="tab"
                        aria-selected={selected}
                        aria-controls={`${panelId}-pane-${cat.id}`}
                        tabIndex={selected ? 0 : -1}
                        className={`settings-nav-item${selected ? " is-active" : ""}`}
                        onClick={() => setActiveCategory(cat.id)}
                        onKeyDown={(event) => handleTabKeyDown(event, idx)}
                      >
                        <span className="settings-nav-icon">
                          <CategoryIcon category={cat.id} />
                        </span>
                        <span className="settings-nav-label">{cat.label}</span>
                        <span
                          className={`settings-led is-${cat.led}`}
                          aria-hidden="true"
                        />
                      </button>
                    );
                  })}
                </div>
                <div className="settings-rail-footer">
                  <span className="settings-led is-ok" aria-hidden="true" />
                  <span>
                    {isZh ? "本機加密 · 零雲端追蹤" : "Local-first · Zero cloud"}
                  </span>
                </div>
              </nav>

              <div
                id={`${panelId}-pane-${activeCategory}`}
                role="tabpanel"
                aria-labelledby={`${panelId}-tab-${activeCategory}`}
                className="settings-content-pane"
              >
                {activeCategory === "connections" && (
                  <>
                    <div className="settings-pane-header">
                      <div>
                        <h3 className="settings-pane-title">
                          {isZh ? "連線與同步" : "Connections & Sync"}
                        </h3>
                        <p className="settings-pane-desc">
                          {t("integrationsOptional")}
                        </p>
                      </div>
                    </div>

                    <div className="settings-led-strip" role="status">
                      {summaryItems.map((item) => (
                        <div key={item.brand} className="settings-led-pill">
                          <span
                            className={`settings-brand-tile brand-${item.brand}`}
                            aria-hidden="true"
                          >
                            <BrandMark brand={item.brand} size={22} />
                          </span>
                          <div className="settings-led-pill-meta">
                            <span className="settings-led-pill-name">
                              {item.name}
                            </span>
                            <span className="settings-led-pill-state">
                              <span
                                className={`settings-led is-${item.led}`}
                                aria-hidden="true"
                              />
                              <span>{item.text}</span>
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>

                    {syncSlot ? (
                      <details className="settings-sync-drawer" open>
                        <summary className="settings-sync-summary">
                          <span className="settings-sync-summary-title">
                            <span
                              className="settings-led is-configured"
                              aria-hidden="true"
                            />
                            <span>
                              {isZh
                                ? "一鍵匯入與同步至已連接軟體"
                                : "Quick Sync to Connected Apps"}
                            </span>
                          </span>
                          <span
                            className="settings-sync-chevron"
                            aria-hidden="true"
                          >
                            ▾
                          </span>
                        </summary>
                        <div className="settings-sync-body">{syncSlot}</div>
                      </details>
                    ) : null}

                    <ul className="integration-tools">
                      {services.map(([key, label, href, guidance]) => {
                        const status =
                          knownSnapshot && freshness === "saved"
                            ? snapshot.components?.[key]
                            : "unknown";
                        const brand: BrandDestination =
                          key === "vault"
                            ? "obsidian"
                            : key === "zotero"
                              ? "zotero"
                              : "notebooklm";
                        const connText =
                          key === "zotero"
                            ? zoteroConnectionText
                            : key === "notebooklm_auth"
                              ? nlmConnectionText
                              : obsidianConnectionText;
                        const connTone =
                          key === "zotero" && liveState?.zotero
                            ? zoteroLiveOk
                              ? "good"
                              : "warn"
                            : key === "notebooklm_auth" && liveState?.notebooklm
                              ? nlmLiveOk
                                ? "good"
                                : "warn"
                              : key === "vault" && liveState?.obsidian
                                ? obsidianLiveOk
                                  ? "good"
                                  : "warn"
                                : "neutral";
                        const cardLed: LedTone =
                          connTone === "good"
                            ? "ok"
                            : connTone === "warn"
                              ? "warn"
                              : (key === "vault" &&
                                    (selectedVault ||
                                      localCap?.obsidian_vault_configured)) ||
                                  (key === "zotero" &&
                                    localCap?.zotero_configured) ||
                                  (key === "notebooklm_auth" &&
                                    localCap?.nlm_state_present)
                                ? "configured"
                                : "idle";
                        return (
                          <li key={key} className="integration-tool">
                            <div className="setup-tool-header">
                              <h3 className="setup-tool-title">
                                <span
                                  className={`setup-brand-mark brand-${brand}`}
                                  aria-hidden="true"
                                >
                                  <BrandMark brand={brand} size={22} />
                                </span>
                                <span>{label}</span>
                              </h3>
                              <span className="setup-status-cluster">
                                <span
                                  className={`settings-led is-${cardLed}`}
                                  aria-hidden="true"
                                />
                                <span className={`badge ${connTone}`}>
                                  {connText}
                                </span>
                              </span>
                            </div>
                            <p className="setup-tool-desc small muted">
                              <span>{t(guidance)}</span>
                              <a
                                className="setup-doc-link"
                                href={href}
                                target="_blank"
                                rel="noopener noreferrer"
                              >
                                <span>{t("integrationOfficial")}</span>
                                <span aria-hidden="true">↗</span>
                              </a>
                            </p>
                            {key === "vault" && (
                              <>
                                <ObsidianValidationForm
                                  capability={
                                    workspace?.capabilities?.obsidian_validation
                                  }
                                  onValidated={(obsidian) =>
                                    onLiveStateChange?.((prev) => ({
                                      ...prev,
                                      obsidian,
                                    }))
                                  }
                                  t={t}
                                />
                                <div className="integration-inline-row">
                                  <span
                                    className={`badge ${localCap?.obsidian_cli_present ? "good" : "neutral"}`}
                                  >
                                    {t(
                                      localCap?.obsidian_cli_present
                                        ? "obsidianCliDetected"
                                        : "obsidianCliNotDetected",
                                    )}
                                  </span>
                                  {(() => {
                                    const vName = resolveObsidianVaultName(
                                      workspace,
                                      liveState,
                                    );
                                    const uri = buildObsidianUri(vName);
                                    return uri ? (
                                      <a
                                        className="button secondary small"
                                        href={uri}
                                        rel="noopener noreferrer"
                                      >
                                        {t("obsidianOpenApp")}{" "}
                                        <span aria-hidden="true">↗</span>
                                      </a>
                                    ) : null;
                                  })()}
                                </div>
                              </>
                            )}
                            {key === "zotero" && (
                              <ZoteroLibraryForm
                                t={t}
                                capability={localCap}
                                probe={liveState?.zotero}
                                onCredentialsSaved={(creds, zoteroTouched) =>
                                  onLiveStateChange?.((prev) => ({
                                    ...prev,
                                    credentials: creds,
                                    ...(zoteroTouched ? { zotero: null } : {}),
                                  }))
                                }
                                onProbeUpdated={(probe) =>
                                  onLiveStateChange?.((prev) => ({
                                    ...prev,
                                    zotero: probe,
                                  }))
                                }
                              />
                            )}
                            {key === "notebooklm_auth" && (
                              <NotebookLmAuthControls
                                capability={localCap}
                                probe={liveState?.notebooklm}
                                loginJob={liveState?.loginJob}
                                onLoginJobChange={(job) =>
                                  onLiveStateChange?.((prev) => ({
                                    ...prev,
                                    loginJob: job,
                                  }))
                                }
                                onProbeUpdated={(probe) =>
                                  onLiveStateChange?.((prev) => ({
                                    ...prev,
                                    notebooklm: probe,
                                  }))
                                }
                                t={t}
                              />
                            )}
                            <dl className="integration-status">
                              <div>
                                <dt>{t("integrationSelectedDestination")}</dt>
                                <dd>
                                  {t(
                                    key === "vault"
                                      ? selectedVault
                                        ? "integrationSelectedVault"
                                        : "integrationNoStartupVault"
                                      : "integrationDestinationUnknown",
                                  )}
                                </dd>
                              </div>
                              <div>
                                <dt>{t("integrationCurrentConnection")}</dt>
                                <dd>{connText}</dd>
                              </div>
                              <div>
                                <dt>{t("integrationSavedObservation")}</dt>
                                <dd>
                                  {t(
                                    typeof status === "string" &&
                                      Object.hasOwn(statuses, status)
                                      ? statuses[status as keyof typeof statuses]
                                      : "snapshotUnknown",
                                  )}
                                </dd>
                              </div>
                            </dl>
                          </li>
                        );
                      })}
                    </ul>

                    <details className="setup-diagnostics">
                      <summary>{t("integrationAdvancedSetup")}</summary>
                      <p>{t("integrationsHistorical")}</p>
                      <dl
                        className="integration-status"
                        aria-label={t("integrationObservationDetails")}
                      >
                        <div>
                          <dt>{t("integrationObservationSource")}</dt>
                          <dd>
                            {t(
                              knownSnapshot
                                ? "integrationSavedSetupSource"
                                : "integrationObservationUnavailable",
                            )}
                          </dd>
                        </div>
                        <div>
                          <dt>{t("integrationObservedAt")}</dt>
                          <dd>
                            {observedAt ? (
                              <time dateTime={observedAt}>{observedAt}</time>
                            ) : (
                              t("integrationObservationUnavailable")
                            )}
                          </dd>
                        </div>
                        <div>
                          <dt>{t("integrationObservationFreshness")}</dt>
                          <dd>
                            {t(
                              snapshot
                                ? freshnessLabels[freshness]
                                : "integrationFreshMissing",
                            )}
                          </dd>
                        </div>
                      </dl>
                      <ol>
                        <li>
                          {t("integrationSetupStep")}{" "}
                          <code>python -m research_hub setup</code>
                        </li>
                        <li>{t("integrationReuse")}</li>
                        <li>
                          {t("integrationCheck")}{" "}
                          <code>python -m research_hub doctor</code>
                        </li>
                      </ol>
                      <p>
                        {t(
                          localCap?.status === "available"
                            ? "integrationLocalPrivacy"
                            : "integrationPrivacy",
                        )}
                      </p>
                    </details>
                    <a
                      className="settings-guide-chip setup-guide-link"
                      href="https://github.com/WenyuChiou/research-hub/blob/master/docs/setup.md"
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      <span>{t("integrationGuide")}</span>
                      <span aria-hidden="true">↗</span>
                    </a>
                  </>
                )}

                {activeCategory === "appearance" && (
                  <>
                    <div className="settings-pane-header">
                      <div>
                        <h3 className="settings-pane-title">
                          {isZh ? "外觀與語言" : "Appearance & Language"}
                        </h3>
                        <p className="settings-pane-desc">
                          {isZh
                            ? "切換工作區視覺主題與介面語言，長時間閱讀文獻更舒適。"
                            : "Customize workspace theme and interface language for long reading sessions."}
                        </p>
                      </div>
                    </div>

                    <div className="settings-section-block">
                      <div>
                        <h4 className="settings-section-label">
                          {isZh ? "色彩主題" : "Theme Mode"}
                        </h4>
                        <p className="settings-section-hint">
                          {isZh
                            ? "即時套用至文獻總表、閱讀台與圖表。"
                            : "Applies immediately across tables, reader desk, and visual charts."}
                        </p>
                      </div>
                      <div
                        role="radiogroup"
                        aria-label={isZh ? "色彩主題" : "Theme Mode"}
                        className="settings-theme-grid"
                      >
                        {(
                          [
                            {
                              mode: "light",
                              title: isZh ? "淺色 Light" : "Light",
                              desc: isZh
                                ? "典藏紙感日間閱讀"
                                : "Archival daylight paper",
                            },
                            {
                              mode: "dark",
                              title: isZh ? "深色 Dark" : "Dark",
                              desc: isZh
                                ? "深色低眩光夜間護眼"
                                : "Deep slate low-glare",
                            },
                            {
                              mode: "system",
                              title: isZh ? "系統自動 System" : "System",
                              desc: isZh
                                ? "跟隨作業系統外觀"
                                : "Sync with OS setting",
                            },
                          ] as const
                        ).map((opt) => {
                          const checked = currentTheme === opt.mode;
                          return (
                            <button
                              key={opt.mode}
                              type="button"
                              role="radio"
                              aria-checked={checked}
                              className={`settings-theme-card${checked ? " is-selected" : ""}`}
                              onClick={() => handleThemeChange(opt.mode)}
                            >
                              <ThemePreviewWireframe mode={opt.mode} />
                              <span className="settings-radio-row">
                                <span
                                  className="settings-radio-dot"
                                  aria-hidden="true"
                                />
                                <span>{opt.title}</span>
                              </span>
                              <span className="settings-card-sub">
                                {opt.desc}
                              </span>
                            </button>
                          );
                        })}
                      </div>
                    </div>

                    <div className="settings-section-block">
                      <div>
                        <h4 className="settings-section-label">
                          {t("language")}
                        </h4>
                        <p className="settings-section-hint">
                          {isZh
                            ? "切換導覽列、證據標籤與匯出介面語系。"
                            : "Switch navigation, evidence badges, and setup labels."}
                        </p>
                      </div>
                      <div
                        role="radiogroup"
                        aria-label={t("language")}
                        className="settings-locale-grid"
                      >
                        <button
                          type="button"
                          role="radio"
                          lang="zh-TW"
                          aria-checked={currentLocale === "zh-TW"}
                          className={`settings-locale-card${currentLocale === "zh-TW" ? " is-selected" : ""}`}
                          onClick={() => handleLocaleChange("zh-TW")}
                        >
                          <span
                            className="settings-locale-monogram"
                            aria-hidden="true"
                          >
                            繁
                          </span>
                          <span className="settings-locale-copy">
                            <span className="settings-locale-name">
                              繁體中文
                            </span>
                            <span className="settings-card-sub">
                              Traditional Chinese (zh-TW)
                            </span>
                          </span>
                          <span
                            className="settings-radio-dot"
                            aria-hidden="true"
                          />
                        </button>
                        <button
                          type="button"
                          role="radio"
                          lang="en"
                          aria-checked={currentLocale === "en"}
                          className={`settings-locale-card${currentLocale === "en" ? " is-selected" : ""}`}
                          onClick={() => handleLocaleChange("en")}
                        >
                          <span
                            className="settings-locale-monogram"
                            aria-hidden="true"
                          >
                            EN
                          </span>
                          <span className="settings-locale-copy">
                            <span className="settings-locale-name">
                              English
                            </span>
                            <span className="settings-card-sub">
                              International Academic (en)
                            </span>
                          </span>
                          <span
                            className="settings-radio-dot"
                            aria-hidden="true"
                          />
                        </button>
                      </div>
                    </div>
                  </>
                )}

                {activeCategory === "ai-runtime" && (
                  <>
                    <div className="settings-pane-header">
                      <div>
                        <h3 className="settings-pane-title">
                          {isZh ? "AI 執行與審核" : "AI & Review Gate"}
                        </h3>
                        <p className="settings-pane-desc">
                          {isZh
                            ? "所有 AI 任務皆採提案制，須經人工審核後才會納入研究成果。"
                            : "All agent tasks produce proposals gated by explicit human review."}
                        </p>
                      </div>
                    </div>

                    <div className="settings-runtime-grid">
                      {(
                        [
                          {
                            id: "codex",
                            title: "Codex Runner",
                            led: (codexCap?.status === "available"
                              ? "ok"
                              : "warn") as LedTone,
                            badgeTone:
                              codexCap?.status === "available" ? "good" : "warn",
                            badgeText:
                              codexCap?.status === "available"
                                ? isZh
                                  ? "已連線"
                                  : "Available"
                                : isZh
                                  ? "交接封包模式"
                                  : "Handoff mode",
                            desc:
                              codexCap?.message ||
                              (isZh
                                ? "本機無工具隔離草擬，或匯出交接封包由外部代理執行。"
                                : "Isolated no-tool local drafting or structured host handoff packets."),
                          },
                          {
                            id: "writing",
                            title: "Writing Adapter",
                            led: (writingCap?.status === "available"
                              ? "ok"
                              : "warn") as LedTone,
                            badgeTone:
                              writingCap?.status === "available"
                                ? "good"
                                : "warn",
                            badgeText:
                              writingCap?.status === "available"
                                ? isZh
                                  ? "已就緒"
                                  : "Available"
                                : isZh
                                  ? "尚未設定"
                                  : "Unavailable",
                            desc:
                              writingCap?.message ||
                              (isZh
                                ? "執行文稿一致性、文風與 DOCX 結構檢查。"
                                : "Manuscript state binding, prose consistency, and DOCX checks."),
                          },
                          {
                            id: "approval",
                            title: "Human Approval Gate",
                            led: (approvalCap?.status === "available"
                              ? "ok"
                              : "warn") as LedTone,
                            badgeTone:
                              approvalCap?.status === "available"
                                ? "good"
                                : "warn",
                            badgeText:
                              approvalCap?.status === "available"
                                ? isZh
                                  ? "瀏覽器核准已啟用"
                                  : "UI gate enabled"
                                : isZh
                                  ? "終端機 CLI 核准"
                                  : "CLI gate active",
                            desc: isZh
                              ? "候選產出絕不自動覆寫原稿；須由研究者明確記錄接受或退回。"
                              : "Candidate outputs never overwrite originals without an explicit human decision.",
                          },
                          {
                            id: "obsidian-cli",
                            title: "Obsidian CLI (v1.12+)",
                            led: (localCap?.obsidian_cli_present
                              ? "ok"
                              : "idle") as LedTone,
                            badgeTone: localCap?.obsidian_cli_present
                              ? "good"
                              : "neutral",
                            badgeText: localCap?.obsidian_cli_present
                              ? isZh
                                ? "已偵測"
                                : "Detected"
                              : isZh
                                ? "選用"
                                : "Optional",
                            desc: t(
                              localCap?.obsidian_cli_present
                                ? "obsidianCliDetected"
                                : "obsidianCliNotDetected",
                            ),
                          },
                        ] as const
                      ).map((card) => (
                        <div key={card.id} className="settings-runtime-card">
                          <div className="settings-runtime-top">
                            <span className="settings-runtime-title">
                              <span
                                className={`settings-led is-${card.led}`}
                                aria-hidden="true"
                              />
                              <span>{card.title}</span>
                            </span>
                            <span className={`badge ${card.badgeTone}`}>
                              {card.badgeText}
                            </span>
                          </div>
                          <p className="settings-runtime-desc">{card.desc}</p>
                        </div>
                      ))}
                    </div>

                    <div className="settings-pipeline-strip">
                      <span className="settings-pipeline-step">
                        <span
                          className="settings-led is-configured"
                          aria-hidden="true"
                        />
                        <span>
                          {isZh ? "1. 證據綁定草稿" : "1. Grounded Proposal"}
                        </span>
                      </span>
                      <span aria-hidden="true">→</span>
                      <span className="settings-pipeline-step">
                        <span
                          className="settings-led is-warn"
                          aria-hidden="true"
                        />
                        <span>
                          {isZh ? "2. 研究者人工審核" : "2. Human Review Gate"}
                        </span>
                      </span>
                      <span aria-hidden="true">→</span>
                      <span className="settings-pipeline-step">
                        <span
                          className="settings-led is-ok"
                          aria-hidden="true"
                        />
                        <span>
                          {isZh ? "3. SHA-256 驗證封裝" : "3. Verified Bundle"}
                        </span>
                      </span>
                    </div>
                  </>
                )}

                {activeCategory === "privacy" && (
                  <>
                    <div className="settings-pane-header">
                      <div>
                        <h3 className="settings-pane-title">
                          {isZh ? "安全與系統診斷" : "Diagnostics & Privacy"}
                        </h3>
                        <p className="settings-pane-desc">
                          {isZh
                            ? "本機安全邊界狀態與歷史設定診斷矩陣。"
                            : "Local security boundary guarantees and setup snapshot health matrix."}
                        </p>
                      </div>
                      <a
                        className="settings-guide-chip"
                        href="https://github.com/WenyuChiou/research-hub/blob/master/docs/setup.md"
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        <span>{t("integrationGuide")}</span>
                        <span aria-hidden="true">↗</span>
                      </a>
                    </div>

                    <div className="settings-security-grid">
                      <div className="settings-security-card">
                        <span className="settings-security-head">
                          <span
                            className="settings-led is-ok"
                            aria-hidden="true"
                          />
                          <span>Loopback CSRF</span>
                        </span>
                        <span className="settings-security-sub">
                          {isZh
                            ? "僅綁定 127.0.0.1，驗證 Origin 與 X-CSRF-Token。"
                            : "Bound to 127.0.0.1 with strict Origin & CSRF token checks."}
                        </span>
                      </div>
                      <div className="settings-security-card">
                        <span className="settings-security-head">
                          <span
                            className={`settings-led ${localCap?.status === "available" ? "is-ok" : "is-configured"}`}
                            aria-hidden="true"
                          />
                          <span>AES-GCM (0600)</span>
                        </span>
                        <span className="settings-security-sub">
                          {isZh
                            ? "API 金鑰於本機磁碟加密保存，絕不寫入瀏覽器儲存區。"
                            : "API keys encrypted on local disk (0600); never in browser storage."}
                        </span>
                      </div>
                      <div className="settings-security-card">
                        <span className="settings-security-head">
                          <span
                            className="settings-led is-ok"
                            aria-hidden="true"
                          />
                          <span>Read-Only Vault</span>
                        </span>
                        <span className="settings-security-sub">
                          {isZh
                            ? "Obsidian Vault 維持純唯讀；匯出僅寫入 .research/exports/。"
                            : "Authorized vault stays strictly read-only; exports stay in workspace."}
                        </span>
                      </div>
                    </div>

                    <div className="settings-section-block">
                      <div className="settings-matrix-header">
                        <div>
                          <h4 className="settings-section-label">
                            {t("setupSnapshot")}
                          </h4>
                          <p className="settings-section-hint">
                            {t(
                              snapshot
                                ? freshnessLabels[freshness]
                                : "integrationFreshMissing",
                            )}
                          </p>
                        </div>
                        {observedAt && (
                          <span className="badge good">
                            <time dateTime={observedAt}>{observedAt}</time>
                          </span>
                        )}
                      </div>

                      <div className="settings-health-matrix">
                        {snapshotTiles.map(([compKey, labelKey]) => {
                          const raw =
                            knownSnapshot && freshness === "saved"
                              ? snapshot?.components?.[compKey]
                              : "unknown";
                          const safeKey =
                            typeof raw === "string" &&
                            Object.hasOwn(statuses, raw)
                              ? (raw as keyof typeof statuses)
                              : "unknown";
                          const tileLed: LedTone =
                            safeKey === "passed"
                              ? "ok"
                              : safeKey === "failed"
                                ? "error"
                                : safeKey === "skipped" ||
                                    safeKey === "cancelled"
                                  ? "warn"
                                  : "idle";
                          return (
                            <div
                              key={compKey}
                              className="settings-health-tile"
                            >
                              <div className="settings-health-tile-top">
                                <span className="settings-health-name">
                                  {t(labelKey)}
                                </span>
                                <span
                                  className={`settings-led is-${tileLed}`}
                                  aria-hidden="true"
                                />
                              </div>
                              <span className="settings-health-state">
                                {t(statuses[safeKey])}
                              </span>
                            </div>
                          );
                        })}
                      </div>
                    </div>

                    <div className="settings-cli-row">
                      <span className="muted">
                        {isZh ? "終端機診斷指令：" : "CLI Diagnostics:"}
                      </span>
                      <span className="setup-status-cluster">
                        <code className="settings-cli-chip">
                          python -m research_hub setup
                        </code>
                        <code className="settings-cli-chip">
                          python -m research_hub doctor
                        </code>
                      </span>
                    </div>
                  </>
                )}
              </div>
            </div>
          </section>,
          document.body,
        )}
    </>
  );
}
