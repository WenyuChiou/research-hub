import { IntegrationsSetup } from "./IntegrationsSetup";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, segment } from "./api";
import { ErrorMessage, MutationForm } from "./components";
import { ProjectPages, type RecoveredWork } from "./Pages";
import { projectWarningLabel, translator, type MessageKey } from "./i18n";
import type {
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
const glyphs = ["◫", "≡", "⌘", "⌁", "¶", "✓"];
function currentPage(): Page {
  const page = window.location.hash.slice(1);
  return pages.includes(page as Page) ? (page as Page) : "overview";
}
const aborted = (error: unknown) =>
  error instanceof Error && error.name === "AbortError";

/** Mounted by main.tsx. All data comes from the local Research Hub API. */
export default function App() {
  const [locale, setLocale] = useState<Locale>("en");
  const [page, setPage] = useState<Page>(currentPage);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [projectId, setProjectId] = useState("");
  const [detail, setDetail] = useState<ProjectDetail | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [detailError, setDetailError] = useState<unknown>(null);
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
  const [refreshCount, setRefreshCount] = useState(0);
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
      cancelHeadingFocus();
      if (window.location.hash === "#main-content") {
        focusMain();
        return;
      }
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
    navigationTarget.current = focusId
      ? { projectId: selectedRef.current, page: next, id: focusId }
      : null;
    const unchanged = window.location.hash === `#${next}`;
    window.location.hash = next;
    setPage(next);
    if (unchanged) queuePageFocus();
  };

  useEffect(() => {
    const controller = new AbortController();
    setError(null);
    api<Workspace>("/workspace", undefined, controller.signal)
      .then((value) => {
        setWorkspace(value);
        setProjectId((selected) => selected || value.projects[0]?.id || "");
      })
      .catch((failure) => {
        if (!aborted(failure)) setError(failure);
      });
    return () => controller.abort();
  }, [refreshCount]);

  useEffect(() => {
    if (!projectId) return;
    const controller = new AbortController();
    setDetailError(null);
    api<ProjectDetail>(
      `/projects/${segment(projectId)}`,
      undefined,
      controller.signal,
    )
      .then((value) => {
        if (controller.signal.aborted) return;
        setDetail(value);
        setPollStatus({ projectId, lastSuccess: Date.now(), stale: false });
      })
      .catch((failure) => {
        if (!controller.signal.aborted && !aborted(failure))
          setDetailError(failure);
      });
    return () => controller.abort();
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
  }
  const activeDetail = detail?.project.id === projectId ? detail : null;
  const showCreate = newProject || workspace?.projects.length === 0;
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content" onClick={focusMain}>
        {t("skip")}
      </a>
      <aside className="sidebar">
        <a className="brand" href="#overview">
          <span className="brand-symbol" aria-hidden="true">
            r<span>h</span>
            <i />
          </span>
          <span>
            {t("app")}
            <small>{t("workspace")}</small>
          </span>
        </a>
        <div className="project-control">
          <label htmlFor="project-switcher">{t("projects")}</label>
          <select
            id="project-switcher"
            value={projectId}
            onChange={(event) => {
              navigationTarget.current = null;
              cancelHeadingFocus();
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
          <button className="new-project" onClick={() => setNewProject(true)}>
            <span aria-hidden="true">＋</span>
            {t("newProject")}
          </button>
        </div>
        <nav aria-label={t("navigation")}>
          {pages.map((item, index) => (
            <a
              key={item}
              href={`#${item}`}
              aria-current={page === item ? "page" : undefined}
            >
              <span className="nav-symbol" aria-hidden="true">
                {glyphs[index]}
              </span>
              <span>{t(item)}</span>
              <span className="nav-number" aria-hidden="true">
                0{index + 1}
              </span>
            </a>
          ))}
        </nav>
        <div className="sidebar-footer">
          <IntegrationsSetup workspace={workspace} projectId={projectId} t={t} />
          <span className="local-marker">
            <i aria-hidden="true" />
            {t("local")}
          </span>
          <p>{t("startEyebrow")}</p>
          <div
            className="language-switch"
            role="group"
            aria-label={t("language")}
          >
            <button
              aria-pressed={locale === "en"}
              onClick={() => setLocale("en")}
              lang="en"
            >
              EN
            </button>
            <button
              aria-pressed={locale === "zh-TW"}
              onClick={() => setLocale("zh-TW")}
              lang="zh-TW"
            >
              繁體中文
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
            className="button text-button"
            onClick={refresh}
            aria-label={t("refresh")}
          >
            <span aria-hidden="true">↻</span>
            <span>{t("refresh")}</span>
          </button>
        </header>
        <div className="content-wrap">
          <div className="page-heading">
            <div>
              <div className="eyebrow">
                {activeDetail
                  ? `${activeDetail.project.archetype === "review" ? t("reviewStudy") : t("empirical")} / ${activeDetail.project.id}`
                  : t("local")}
              </div>
              <h1 ref={headingRef} tabIndex={-1}>
                {t(page)}
              </h1>
              <p>{t(`${page}Subtitle` as MessageKey)}</p>
            </div>
            <span className="page-index" aria-hidden="true">
              0{pages.indexOf(page) + 1}
            </span>
          </div>
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
                <section className="project-onboarding">
                  <div className="onboarding-intro">
                    <SmallEyebrow text={t("startEyebrow")} />
                    <h2>{t("startTitle")}</h2>
                    <p>{t("startBody")}</p>
                    <p>{t("integrationFirstUse")}</p>
                    <div aria-hidden="true" className="onboarding-lines">
                      <i />
                      <i />
                      <i />
                    </div>
                  </div>
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
                          pattern: "[a-z0-9][a-z0-9-]{0,62}",
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
                        const created = await api<{
                          ok: true;
                          project?: Project;
                        }>("/projects", Object.fromEntries(data));
                        const id =
                          created.project?.id || String(data.get("id"));
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
                    {activeDetail.warnings?.length > 0 && (
                      <section className="notice warnings">
                        <strong>{t("warnings")}</strong>
                        <ul>
                          {activeDetail.warnings.map((warning, index) => (
                            <li key={index}>
                              {projectWarningLabel(warning, t)}
                            </li>
                          ))}
                        </ul>
                      </section>
                    )}
                    <ProjectPages
                      key={projectId}
                      detail={activeDetail}
                      workspace={workspace}
                      page={page}
                      t={t}
                      onSaved={onSaved}
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
          <footer className="content-footer">
            <span>RESEARCH HUB</span>
            <span>{t("startEyebrow")}</span>
          </footer>
        </div>
      </main>
    </div>
  );
}
function SmallEyebrow({ text }: { text: string }) {
  return <span className="eyebrow">{text}</span>;
}
