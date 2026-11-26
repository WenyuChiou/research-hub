import { discoveryRoute } from "./Discovery";
import { ComposerSessions } from "./composerSession";
import { IntegrationsSetup } from "./IntegrationsSetup";
import { useCompactReadingLayout } from "./readingLayout";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, refreshSessionTokens, segment } from "./api";
import { ErrorMessage, MutationForm } from "./components";
import { ProjectPages, type RecoveredWork } from "./Pages";
import { en, projectWarningLabel, translator, type MessageKey } from "./i18n";
import type {
  IntegrationLiveState,
  Locale,
  Page,
  Project,
  ProjectDetail,
  Task,
  Workspace,
} from "./types";

const pages: Page[] = [
  "overview",
  "literature",
  "evidence",
  "design",
  "manuscript",
  "review",
];

function NavIcon({ page }: { page: Page }) {
  const shared = {
    width: 14,
    height: 14,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
    focusable: false,
  };
  switch (page) {
    case "overview":
      return (
        <svg {...shared}>
          <rect x="3" y="3" width="7" height="7" rx="1.5" />
          <rect x="14" y="3" width="7" height="7" rx="1.5" />
          <rect x="3" y="14" width="7" height="7" rx="1.5" />
          <rect x="14" y="14" width="7" height="7" rx="1.5" />
        </svg>
      );
    case "literature":
      return (
        <svg {...shared}>
          <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
          <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
        </svg>
      );
    case "evidence":
      return (
        <svg {...shared}>
          <path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2" />
          <rect x="9" y="3" width="6" height="4" rx="1" />
          <path d="M9 12h6" />
          <path d="M9 16h4" />
        </svg>
      );
    case "design":
      return (
        <svg {...shared}>
          <path d="M3 3v18h18" />
          <path d="m7 14 4-4 3 3 5-6" />
        </svg>
      );
    case "manuscript":
      return (
        <svg {...shared}>
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <path d="M14 2v6h6" />
          <path d="M8 13h8" />
          <path d="M8 17h5" />
        </svg>
      );
    case "review":
      return (
        <svg {...shared}>
          <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
          <path d="m9 11 3 3L22 4" />
        </svg>
      );
  }
}
function currentPage(): Page {
  const page = window.location.hash.slice(1).split("?", 1)[0];
  return pages.includes(page as Page) ? (page as Page) : "literature";
}
const aborted = (error: unknown) =>
  error instanceof Error && error.name === "AbortError";

const LOCALE_STORAGE_KEY = "research-hub:locale";

function readSavedLocale(): Locale {
  try {
    return window.localStorage?.getItem(LOCALE_STORAGE_KEY) === "zh-TW"
      ? "zh-TW"
      : "en";
  } catch {
    return "en";
  }
}

function deriveProjectId(title: string, existingIds: string[]): string {
  const ascii = title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 56);
  const base = ascii || `project-${Date.now().toString(36).slice(-6)}`;
  if (!existingIds.includes(base)) return base;
  for (let i = 2; i < 1000; i++) {
    const candidate = `${base.slice(0, 58)}-${i}`;
    if (!existingIds.includes(candidate)) return candidate;
  }
  return `project-${Date.now().toString(36)}`;
}

/** Mounted by main.tsx. All data comes from the local Research Hub API. */
export default function App() {
  const navigationEpoch = useRef(0);
  const [composerSessions] = useState(() => new ComposerSessions());
  const [locale, setLocaleState] = useState<Locale>(readSavedLocale);
  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    try {
      window.localStorage?.setItem(LOCALE_STORAGE_KEY, next);
    } catch {
      // Ignore storage failures when private mode or tests block localStorage.
    }
  }, []);
  const [demoBusy, setDemoBusy] = useState(false);
  const [demoError, setDemoError] = useState<unknown>(null);
  const [page, setPage] = useState<Page>(currentPage);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [projectId, setProjectId] = useState(
    () => discoveryRoute().project ?? "",
  );
  const [discovery, setDiscovery] = useState(discoveryRoute);
  const [detail, setDetail] = useState<ProjectDetail | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [detailError, setDetailError] = useState<unknown>(null);
  const [liveIntegrations, setLiveIntegrations] = useState<IntegrationLiveState>({});
  const [browserOffline, setBrowserOffline] = useState(
    () => typeof navigator !== "undefined" && navigator.onLine === false,
  );
  const [reconnectAttempts, setReconnectAttempts] = useState(0);
  const hadConnectionLossRef = useRef(false);
  const inFlightWorkspaceRef = useRef(false);
  const inFlightDetailRef = useRef(false);
  const latestStateRef = useRef({
    browserOffline: false,
    error: null as unknown,
    detailError: null as unknown,
    locale,
  });
  latestStateRef.current = { browserOffline, error, detailError, locale };
  const [pollStatus, setPollStatus] = useState<{
    projectId: string;
    lastSuccess: number;
    stale: boolean;
    retrying?: boolean;
    reason?: string;
  } | null>(null);
  const [notice, setNotice] = useState<{
    message: string;
    error?: boolean;
  } | null>(null);
  const [newProject, setNewProject] = useState(false);
  const [setupOpenRequest, setSetupOpenRequest] = useState(0);
  const [categoryHost, setCategoryHost] = useState<HTMLDivElement | null>(null);
  const [navigationOpen, setNavigationOpen] = useState(false);
  const navigationToggle = useRef<HTMLButtonElement>(null);
  const lastReadingFocus = useRef<Element | null>(null);
  const sidebar = useRef<HTMLElement>(null);
  const compact = useCompactReadingLayout(next => {
    // Native CSS can hide a control before the matchMedia event is dispatched.
    const focused = document.activeElement === document.body ? lastReadingFocus.current : document.activeElement;
    if (page === "literature" && !next && navigationToggle.current && navigationToggle.current === focused) sidebar.current?.querySelector<HTMLAnchorElement>(".brand")?.focus();
    if (next && page === "literature" && sidebar.current?.contains(document.activeElement)) setNavigationOpen(true);
  });
  const [refreshCount, setRefreshCount] = useState(0);
  const [refreshSpinning, setRefreshSpinning] = useState(false);
  const refreshSpinTimer = useRef<number | null>(null);
  useEffect(() => () => {
    if (refreshSpinTimer.current !== null) window.clearTimeout(refreshSpinTimer.current);
  }, []);
  const selectedRef = useRef(projectId);
  selectedRef.current = projectId;
  const detailRef = useRef(detail);
  detailRef.current = detail;
  const namespaceRef = useRef(
    workspace?.capabilities.prepare_reconciliation?.workspace_instance_id,
  );
  namespaceRef.current =
    workspace?.capabilities.prepare_reconciliation?.workspace_instance_id;
  const intakeNamespaceRef = useRef(
    workspace?.capabilities.text_intake?.workspace_instance_id,
  );
  intakeNamespaceRef.current =
    workspace?.capabilities.text_intake?.workspace_instance_id;
  const headingRef = useRef<HTMLHeadingElement>(null);
  const mainRef = useRef<HTMLElement>(null);
  const headingFocusFrame = useRef<number | null>(null);
  const navigationTarget = useRef<{
    projectId: string;
    page: Page;
    id: string;
  } | null>(null);
  const cancelHeadingFocus = useCallback(() => {
    if (headingFocusFrame.current !== null) {
      cancelAnimationFrame(headingFocusFrame.current);
      headingFocusFrame.current = null;
    }
  }, []);
  const focusMain = useCallback(() => {
    cancelHeadingFocus();
    mainRef.current?.focus();
  }, [cancelHeadingFocus]);
  const t = translator(locale);

  useEffect(() => {
    document.documentElement.lang = locale;
    setNotice(null);
  }, [locale]);
  const queuePageFocus = useCallback(() => {
    cancelHeadingFocus();
    const target = navigationTarget.current;
    navigationTarget.current = null;
    headingFocusFrame.current = requestAnimationFrame(() => {
      headingFocusFrame.current = null;
      if (
        target &&
        target.projectId === selectedRef.current &&
        target.page === currentPage()
      ) {
        const element = document.getElementById(target.id);
        if (element && !element.closest("[hidden]")) {
          element.focus();
          return;
        }
        setNotice({
          message: translator(locale)(
            target.id.startsWith("review-task-")
              ? "returnTargetMissing"
              : "abstractTargetMissing",
          ),
          error: true,
        });
      }
      headingRef.current?.focus();
    });
  }, [cancelHeadingFocus, locale]);

  useEffect(() => {
    const onHashChange = () => {
      navigationEpoch.current++;
      cancelHeadingFocus();
      if (window.location.hash === "#main-content") {
        focusMain();
        return;
      }
      const route = discoveryRoute();
      setDiscovery(route);
      if (route.project) setProjectId(route.project);
      setPage(currentPage());
      if (navigationTarget.current?.page !== currentPage())
        navigationTarget.current = null;
      queuePageFocus();
    };
    window.addEventListener("hashchange", onHashChange);
    return () => {
      window.removeEventListener("hashchange", onHashChange);
      cancelHeadingFocus();
    };
  }, [cancelHeadingFocus, focusMain, queuePageFocus]);
  const navigate = (next: Page, focusId?: string) => {
    navigationEpoch.current++;
    navigationTarget.current = focusId
      ? { projectId: selectedRef.current, page: next, id: focusId }
      : null;
    const unchanged = window.location.hash === `#${next}`;
    setDiscovery({
      requested: false,
      valid: false,
      project: null,
      artifact: null,
    });
    window.location.hash = next;
    setPage(next);
    if (unchanged) queuePageFocus();
  };

  useEffect(() => {
    const controller = new AbortController();
    inFlightWorkspaceRef.current = true;
    setError(null);
    api<Workspace>("/workspace", undefined, controller.signal)
      .then((value) => {
        if (controller.signal.aborted) return;
        inFlightWorkspaceRef.current = false;
        setWorkspace(value);
        setProjectId((selected) => selected || value.projects[0]?.id || "");
        if (
          hadConnectionLossRef.current &&
          !latestStateRef.current.browserOffline &&
          !inFlightDetailRef.current &&
          !latestStateRef.current.detailError
        ) {
          hadConnectionLossRef.current = false;
          setReconnectAttempts(0);
          setNotice({ message: translator(latestStateRef.current.locale)("pollReconnected") });
        }
      })
      .catch((failure) => {
        inFlightWorkspaceRef.current = false;
        if (!aborted(failure)) setError(failure);
      });
    return () => {
      inFlightWorkspaceRef.current = false;
      controller.abort();
    };
  }, [refreshCount]);

  useEffect(() => {
    if (!projectId) {
      inFlightDetailRef.current = false;
      return;
    }
    const controller = new AbortController();
    inFlightDetailRef.current = true;
    setDetailError(null);
    api<ProjectDetail>(
      `/projects/${segment(projectId)}`,
      undefined,
      controller.signal,
    )
      .then((value) => {
        if (controller.signal.aborted) return;
        inFlightDetailRef.current = false;
        setDetail(value);
        setPollStatus({ projectId, lastSuccess: Date.now(), stale: false });
        if (
          hadConnectionLossRef.current &&
          !latestStateRef.current.browserOffline &&
          !inFlightWorkspaceRef.current &&
          !latestStateRef.current.error
        ) {
          hadConnectionLossRef.current = false;
          setReconnectAttempts(0);
          setNotice({ message: translator(latestStateRef.current.locale)("pollReconnected") });
        }
      })
      .catch((failure) => {
        inFlightDetailRef.current = false;
        if (!controller.signal.aborted && !aborted(failure))
          setDetailError(failure);
      });
    return () => {
      inFlightDetailRef.current = false;
      controller.abort();
    };
  }, [projectId, refreshCount]);

  const onSaved = useCallback(
    async (message: string, recovered?: RecoveredWork) => {
      const savedProject = selectedRef.current;
      const startedDetail = detailRef.current;
      const isText = recovered && "savedText" in recovered;
      const responseNamespace = (value: Workspace) =>
        isText
          ? value.capabilities.text_intake?.workspace_instance_id
          : value.capabilities.prepare_reconciliation?.workspace_instance_id;
      const matchingRecovery = () =>
        Boolean(
          recovered &&
          ("savedText" in recovered
            ? recovered.savedText.artifact.project_id === savedProject &&
              recovered.savedText.artifact.source_record_id ===
                recovered.savedText.record.id
            : recovered.task.project_id === savedProject &&
              recovered.task.operation === "paper-abstract-draft") &&
          selectedRef.current === savedProject &&
          (isText ? intakeNamespaceRef.current : namespaceRef.current) ===
            recovered.workspaceInstance,
        );
      if (recovered && !matchingRecovery()) return;
      const insertKnownTask = (value: ProjectDetail): ProjectDetail => {
        if (!recovered) return value;
        if ("savedText" in recovered) {
          const { record, artifact } = recovered.savedText;
          return {
            ...value,
            records: value.records.some((item) => item.id === record.id)
              ? value.records
              : [...value.records, record],
            artifacts: value.artifacts.some((item) => item.id === artifact.id)
              ? value.artifacts
              : [...value.artifacts, artifact],
          };
        }
        return value.tasks.some((task) => task.id === recovered.task.id)
          ? value
          : { ...value, tasks: [...value.tasks, recovered.task] };
      };
      const insertedDetail =
        recovered && startedDetail?.project.id === savedProject
          ? insertKnownTask(startedDetail)
          : startedDetail;
      if (recovered) {
        setDetail((previous) => {
          if (!matchingRecovery() || previous?.project.id !== savedProject)
            return previous;
          return previous === startedDetail
            ? insertedDetail
            : insertKnownTask(previous);
        });
      }
      setNotice({ message });
      const results = await Promise.allSettled([
        api<Workspace>("/workspace"),
        savedProject
          ? api<ProjectDetail>(`/projects/${segment(savedProject)}`)
          : Promise.resolve(null),
      ]);
      if (results[0].status === "fulfilled") setWorkspace(results[0].value);
      if (
        results[1].status === "fulfilled" &&
        results[1].value &&
        selectedRef.current === savedProject
      ) {
        const fresh = results[1].value;
        if (!recovered) setDetail(fresh);
        setPollStatus({
          projectId: savedProject,
          lastSuccess: Date.now(),
          stale: false,
        });
      }
      if (
        recovered &&
        selectedRef.current === savedProject &&
        results[0].status === "fulfilled" &&
        responseNamespace(results[0].value) !== recovered.workspaceInstance
      ) {
        // A replacement workspace is a different authority even at the same origin/project ID.
        setDetail((previous) =>
          previous === startedDetail || previous === insertedDetail
            ? null
            : previous,
        );
        setDetailError(
          new ApiError(
            "The workspace identity changed. Refresh before reviewing its tasks.",
            "workspace_mismatch",
            409,
          ),
        );
      }
      if (
        recovered &&
        matchingRecovery() &&
        (results[0].status !== "fulfilled" ||
          responseNamespace(results[0].value) === recovered.workspaceInstance)
      ) {
        const projectResult = results[1];
        setDetail((previous) => {
          if (!matchingRecovery() || previous?.project.id !== savedProject)
            return previous;
          // The exact returned task is authoritative. Never overwrite an existing
          // task or a newer detail response with this recovery response.
          const candidate =
            previous !== startedDetail && previous !== insertedDetail
              ? previous
              : projectResult.status === "fulfilled" &&
                  projectResult.value?.project.id === savedProject
                ? projectResult.value
                : previous;
          return insertKnownTask(candidate);
        });
        if (projectResult.status === "rejected")
          setDetailError(projectResult.reason);
        else if (projectResult.value?.project.id === savedProject)
          setDetailError(null);
      }
      if (results.some((result) => result.status === "rejected"))
        setNotice({ message: translator(locale)("refreshError"), error: true });
    },
    [locale],
  );

  const pollingKey =
    detail?.project.id === projectId
      ? detail.tasks
          .filter((task) => task.status === "running")
          .map((task) => task.id)
          .join("|")
      : "";
  useEffect(() => {
    if (!pollingKey) return;
    let activeController: AbortController | undefined;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    let failures = 0;
    const poll = async () => {
      const controller = new AbortController();
      activeController = controller;
      let retry = true;
      try {
        const tasks = await Promise.all(
          pollingKey
            .split("|")
            .map((id) =>
              api<{ ok: true; task: Task }>(
                `/tasks/${segment(id)}`,
                undefined,
                controller.signal,
              ),
            ),
        );
        if (cancelled) return;
        if (tasks.some((value) => value.task.status !== "running")) {
          const fresh = await api<ProjectDetail>(
            `/projects/${segment(projectId)}`,
            undefined,
            controller.signal,
          );
          if (cancelled) return;
          setDetail(fresh);
        } else {
          setDetail((previous) =>
            previous?.project.id === projectId
              ? {
                  ...previous,
                  tasks: previous.tasks.map(
                    (task) =>
                      tasks.find((value) => value.task.id === task.id)?.task ??
                      task,
                  ),
                }
              : previous,
          );
        }
        failures = 0;
        setPollStatus({ projectId, lastSuccess: Date.now(), stale: false });
      } catch (failure) {
        if (cancelled) return;
        retry =
          !(failure instanceof ApiError) ||
          failure.status >= 500 ||
          failure.status === 408 ||
          failure.status === 429;
        // Promise.all may fail before sibling task reads finish.
        controller.abort();
        failures += 1;
        setPollStatus((previous) =>
          previous?.projectId === projectId
            ? {
                ...previous,
                stale: true,
                retrying: retry,
                reason:
                  failure instanceof Error ? failure.message : String(failure),
              }
            : previous,
        );
      } finally {
        // Only reads are retried. Cleanup cancels both delayed and in-flight reads.
        if (!cancelled && retry)
          timer = setTimeout(
            () => void poll(),
            Math.min(3000 * 2 ** Math.min(Math.max(failures - 1, 0), 4), 30000),
          );
      }
    };
    timer = setTimeout(() => void poll(), 3000);
    return () => {
      cancelled = true;
      clearTimeout(timer);
      activeController?.abort();
    };
  }, [pollingKey, projectId, refreshCount]);

  function refresh() {
    setDetailError(null);
    setError(null);
    setRefreshCount((count) => count + 1);
    setRefreshSpinning(true);
    if (refreshSpinTimer.current !== null) window.clearTimeout(refreshSpinTimer.current);
    refreshSpinTimer.current = window.setTimeout(() => {
      setRefreshSpinning(false);
      refreshSpinTimer.current = null;
    }, 450);
  }

  const isRetryableConnectionError = (failure: unknown) =>
    failure !== null &&
    (!(failure instanceof ApiError) ||
      failure.status >= 500 ||
      failure.status === 408 ||
      failure.status === 429);
  const connectionLost =
    browserOffline ||
    isRetryableConnectionError(error) ||
    isRetryableConnectionError(detailError);

  useEffect(() => {
    const onOffline = () => setBrowserOffline(true);
    const onOnline = () => {
      setBrowserOffline(false);
      void refreshSessionTokens().then(() => {
        setReconnectAttempts(0);
        refresh();
      });
    };
    window.addEventListener("offline", onOffline);
    window.addEventListener("online", onOnline);
    return () => {
      window.removeEventListener("offline", onOffline);
      window.removeEventListener("online", onOnline);
    };
  }, []);

  useEffect(() => {
    if (!connectionLost) return;
    hadConnectionLossRef.current = true;
    if (browserOffline) return;
    const controller = new AbortController();
    const delay = Math.min(3000 * 2 ** Math.min(reconnectAttempts, 4), 30000);
    const timer = window.setTimeout(() => {
      void refreshSessionTokens(controller.signal).then(() => {
        if (controller.signal.aborted) return;
        setReconnectAttempts((n) => n + 1);
        setRefreshCount((count) => count + 1);
      });
    }, delay);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [connectionLost, browserOffline, reconnectAttempts]);
  const activeDetail = detail?.project.id === projectId ? detail : null;
  const pageCount = (item: Page): number => {
    if (!activeDetail) return 0;
    if (item === "literature") return activeDetail.records.filter((r) => r.kind === "source").length;
    if (item === "evidence") return activeDetail.records.filter((r) => r.kind === "claim").length;
    if (item === "design") return activeDetail.records.filter((r) => r.kind === "analysis").length;
    if (item === "manuscript") {
      return (
        activeDetail.records.filter((r) => r.kind === "outline").length +
        (activeDetail.artifacts.some((a) => a.role === "main_manuscript") ? 1 : 0)
      );
    }
    if (item === "review") return activeDetail.tasks.length;
    return 0;
  };
  const navigationLinks = (items: Page[]) => (
    <>
      {items.map((item) => {
        const count = pageCount(item);
        return (
          <a
            key={item}
            href={"#" + item}
            onClick={() => {
              navigationEpoch.current++;
            }}
            aria-current={page === item ? "page" : undefined}
          >
            <span className="nav-symbol" aria-hidden="true">
              <NavIcon page={item} />
            </span>
            <span className="nav-label-text">{t(item)}</span>
            {count > 0 && (
              <span className="nav-number" aria-hidden="true">
                {count}
              </span>
            )}
          </a>
        );
      })}
    </>
  );
  const selectedProjectTitle = workspace?.projects.find(
    (project) => project.id === projectId,
  )?.title;
  const showCreate = newProject || workspace?.projects.length === 0;
  return (
    <div className={`app-shell${page === "literature" ? " reading-desk-shell" : ""}${navigationOpen ? " navigation-open" : ""}`}
      onFocusCapture={event => { lastReadingFocus.current = event.target as Element; }}>
      <a className="skip-link" href="#main-content" onClick={focusMain}>
        {t("skip")}
      </a>
      <aside className="sidebar" ref={sidebar} onKeyDown={event => {
        if (compact && navigationOpen && event.key === "Escape" && !(event.target as Element).closest('[role="dialog"]')) {
          setNavigationOpen(false); navigationToggle.current?.focus();
        }
      }}>
        <a className="brand" href="#overview">
          <span className="brand-symbol" aria-hidden="true">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
              <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
              <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
              <path d="M9 7h6" />
              <path d="M9 11h4" />
            </svg>
          </span>
          <span>
            {t("app")}
            <small>{t("workspace")}</small>
          </span>
        </a>
        {page === "literature" && <button type="button" ref={navigationToggle} className="button secondary reading-navigation-toggle"
          aria-expanded={navigationOpen} aria-controls="workspace-navigation"
          onClick={() => setNavigationOpen(open => !open)}>{t("readingNavigation")}</button>}
        <div className="project-control">
          <div className="project-control-header">
            <label htmlFor="project-switcher">{t("projects")}</label>
            <button
              type="button"
              className="new-project icon-btn"
              onClick={() => setNewProject(true)}
              aria-label={t("newProject")}
              data-tooltip={t("newProject")}
              data-tooltip-pos="top-end"
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden="true" focusable="false">
                <path d="M12 5v14" />
                <path d="M5 12h14" />
              </svg>
            </button>
          </div>
          <select
            id="project-switcher"
            value={projectId}
            onChange={(event) => {
              navigationEpoch.current++;
              navigationTarget.current = null;
              cancelHeadingFocus();
              setDiscovery({
                requested: false,
                valid: false,
                project: null,
                artifact: null,
              });
              window.history.replaceState({}, "", "#" + page);
              setProjectId(event.target.value);
              setNewProject(false);
              setNotice(null);
            }}
            aria-label={t("chooseProject")}
          >
            {!workspace?.projects.length && (
              <option value="">{t("noProject")}</option>
            )}
            {workspace?.projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.title}
              </option>
            ))}
          </select>
          {selectedProjectTitle && selectedProjectTitle.length > 28 && (
            <p className="selected-project-title">{selectedProjectTitle}</p>
          )}
        </div>
        <nav id="workspace-navigation" aria-label={t("navigation")} hidden={page === "literature" && compact && !navigationOpen}>
          <p className="nav-group-label">{t("catalogResearchNav")}</p>
          {navigationLinks(pages.slice(0, 3))}
          <details className="secondary-navigation" open={pages.slice(3).includes(page)}>
            <summary>{t("catalogWritingNav")}</summary>
            {navigationLinks(pages.slice(3))}
          </details>
          <div ref={setCategoryHost} hidden={page !== "literature"} />
        </nav>
        <div className="sidebar-footer">
          <IntegrationsSetup
            workspace={workspace}
            projectId={projectId}
            liveState={liveIntegrations}
            onLiveStateChange={setLiveIntegrations}
            openRequest={setupOpenRequest}
            t={t}
          />
          <div
            className="language-switch"
            role="group"
            aria-label={t("language")}
          >
            <button
              aria-pressed={locale === "zh-TW"}
              onClick={() => setLocale("zh-TW")}
              lang="zh-TW"
            >
              中
            </button>
            <button
              aria-pressed={locale === "en"}
              onClick={() => setLocale("en")}
              lang="en"
            >
              EN
            </button>
          </div>
        </div>
      </aside>
      <main
        ref={mainRef}
        id="main-content"
        className="main-shell"
        tabIndex={-1}
      >
        <header className="topbar">
          <div className="breadcrumb">
            <span>{t("workspace")}</span>
            <span aria-hidden="true">/</span>
            <strong>{activeDetail?.project.title || t("projects")}</strong>
          </div>
          <button
            type="button"
            className={`button text-button icon-btn${refreshSpinning ? " is-spinning" : ""}`}
            onClick={refresh}
            aria-label={t("refresh")}
            data-tooltip={t("refresh")}
            data-tooltip-pos="bottom-end"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
              <path d="M21 12a9 9 0 1 1-2.64-6.36" />
              <path d="M21 3v6h-6" />
            </svg>
          </button>
        </header>
        <div className={`content-wrap workspace-${page}`}>
          <div className="page-heading">
            <div>
              <div className="eyebrow">
                {activeDetail
                  ? activeDetail.project.archetype === "review"
                    ? t("reviewStudy")
                    : t("empirical")
                  : t("local")}
              </div>
              <h1 ref={headingRef} tabIndex={-1}>
                {t(page)}
              </h1>
              <p>{t(`${page}Subtitle` as MessageKey)}</p>
            </div>
          </div>
          {connectionLost && (
            <div role="status" className="notice notice-warn">
              <span>{t("pollReconnecting")}</span>{" "}
              <button
                type="button"
                className="button secondary small"
                onClick={() => void refreshSessionTokens().then(() => refresh())}
              >
                {t("pollReconnectNow")}
              </button>
            </div>
          )}
          {pollStatus?.projectId === projectId && pollStatus.stale && (
            <div role="alert" className="notice notice-error">
              <span>
                {t(pollStatus.retrying ? "pollDelayed" : "pollStopped")}{" "}
                {pollStatus.reason} {t("pollLastSuccess")}{" "}
                <time dateTime={new Date(pollStatus.lastSuccess).toISOString()}>
                  {new Date(pollStatus.lastSuccess).toLocaleTimeString(locale)}
                </time>
              </span>
            </div>
          )}
          {notice && (
            <div
              role={notice.error ? "alert" : "status"}
              className={`notice ${notice.error ? "notice-error" : "notice-success"}`}
            >
              <span>{notice.message}</span>
              <button onClick={() => setNotice(null)} aria-label={t("dismiss")}>
                ×
              </button>
            </div>
          )}
          {workspace &&
            activeDetail &&
            (error !== null || detailError !== null) && (
              <div className="notice notice-error">
                <p>{t("refreshRetained")}</p>
                {error !== null && <ErrorMessage error={error} t={t} />}
                {detailError !== null && (
                  <ErrorMessage error={detailError} t={t} />
                )}
                <button
                  className="button secondary"
                  onClick={() => void refresh()}
                >
                  {t("retry")}
                </button>
              </div>
            )}
          {error !== null && !workspace ? (
            <>
              <ErrorMessage error={error} t={t} />
              <button
                className="button secondary"
                onClick={() => void refresh()}
              >
                {t("retry")}
              </button>
            </>
          ) : !workspace ? (
            <div className="loading-state" role="status">
              <span className="loading-dot" />
              {t("loading")}
            </div>
          ) : (
            <>
              {showCreate && (
                <section className={workspace.projects.length ? "project-onboarding compact-create" : "project-onboarding"}>
                  {workspace.projects.length === 0 && <div className="onboarding-intro">
                    <SmallEyebrow text={t("startEyebrow")} />
                    <h2>{t("startTitle")}</h2>
                    <p>{t("startBody")}</p>
                    <p>{t("integrationFirstUse")}</p>
                    <div className="onboarding-demo">
                      <button
                        type="button"
                        className="button secondary"
                        disabled={demoBusy}
                        onClick={() => {
                          setDemoBusy(true);
                          setDemoError(null);
                          void api<{ ok: true; projects: Project[] }>("/workspace/demo", {})
                            .then(async (res) => {
                              const preferred =
                                res.projects?.find((p) => p.id === "review-demo")?.id ||
                                res.projects?.[0]?.id ||
                                "";
                              await onSaved(t("saved"));
                              if (preferred) setProjectId(preferred);
                              setNewProject(false);
                            })
                            .catch((failure) => setDemoError(failure))
                            .finally(() => setDemoBusy(false));
                        }}
                      >
                        {demoBusy ? t("loadingDemo") : t("loadDemo")}
                      </button>
                      <p className="small muted">{t("loadDemoHelp")}</p>
                      {demoError !== null && <ErrorMessage error={demoError} t={t} />}
                    </div>
                  </div>}
                  <div className="onboarding-form">
                    <div className="panel-heading">
                      <h2>{t("newProject")}</h2>
                      {workspace.projects.length > 0 && (
                        <button
                          className="button text-button"
                          onClick={() => setNewProject(false)}
                        >
                          {t("cancel")}
                        </button>
                      )}
                    </div>
                    <MutationForm
                      t={t}
                      submit={t("createProject")}
                      fields={[
                        { name: "title", label: t("title") },
                        {
                          name: "id",
                          label: t("projectId"),
                          hint: t("projectIdHint"),
                          required: false,
                          pattern: "[a-z0-9][a-z0-9\\-]{0,62}",
                        },
                        {
                          name: "archetype",
                          label: t("archetype"),
                          options: [
                            { value: "empirical", label: t("empirical") },
                            { value: "review", label: t("reviewStudy") },
                          ],
                        },
                        { name: "goal", label: t("goal"), textarea: true },
                      ]}
                      onSubmit={async (data) => {
                        const payload = Object.fromEntries(data) as Record<string, string>;
                        const suppliedId = (payload.id ?? "").trim();
                        payload.id =
                          suppliedId ||
                          deriveProjectId(
                            payload.title ?? "",
                            workspace.projects.map((p) => p.id),
                          );
                        const created = await api<{
                          ok: true;
                          project?: Project;
                        }>("/projects", payload);
                        const id = created.project?.id || payload.id;
                        await onSaved(t("saved"));
                        setProjectId(id);
                        setNewProject(false);
                      }}
                    />
                  </div>
                </section>
              )}
              {!showCreate &&
                (detailError !== null && !activeDetail ? (
                  <>
                    <ErrorMessage error={detailError} t={t} />
                    <button
                      className="button secondary"
                      onClick={() => void refresh()}
                    >
                      {t("retry")}
                    </button>
                  </>
                ) : activeDetail ? (
                  <>
                    {activeDetail.warnings?.some((warning) =>
                      page !== "literature" || warning !== en.writingAuthorityUnbound
                    ) && (
                      <section className="notice warnings">
                        <strong>{t("warnings")}</strong>
                        <ul>
                          {activeDetail.warnings.filter((warning) =>
                            page !== "literature" || warning !== en.writingAuthorityUnbound
                          ).map((warning, index) => (
                            <li key={index}>
                              {projectWarningLabel(warning, t)}
                            </li>
                          ))}
                        </ul>
                      </section>
                    )}
                    {page === "literature" && activeDetail.warnings?.includes(en.writingAuthorityUnbound) && (
                      <details>
                        <summary>{t("writingWarningSummary")}</summary>
                        <p>{t("writingAuthorityUnbound")}</p>
                      </details>
                    )}
                    <ProjectPages
                      key={projectId}
                      discoveryArtifact={
                        discovery.project === projectId
                          ? discovery.artifact
                          : null
                      }
                      invalidDiscoveryLink={
                        discovery.requested && !discovery.valid
                      }
                      navigationEpoch={navigationEpoch}
                      composerSessions={composerSessions}
                      detail={activeDetail}
                      workspace={workspace}
                      liveIntegrations={liveIntegrations}
                      page={page}
                      observationRevision={refreshCount}
                      categoryHost={categoryHost}
                      locale={locale}
                      t={t}
                      onSaved={onSaved}
                      onOpenSetup={() => setSetupOpenRequest((value) => value + 1)}
                      navigate={navigate}
                    />
                  </>
                ) : projectId ? (
                  <div className="loading-state" role="status">
                    <span className="loading-dot" />
                    {t("loading")}
                  </div>
                ) : null)}
            </>
          )}
        </div>
      </main>
    </div>
  );
}
function SmallEyebrow({ text }: { text: string }) {
  return <span className="eyebrow">{text}</span>;
}
