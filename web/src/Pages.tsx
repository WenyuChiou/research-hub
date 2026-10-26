import { DiscoveryPanel } from "./Discovery";
import { ComposerSessions } from "./composerSession";
import { artifactReference } from "./sourceStorage";
import { linkedSourceArtifact, sourceArtifactLabels } from "./sourceArtifact";
import { useRef, useState, type ReactNode } from "react";
import { api, segment } from "./api";
import {
  Disclosure,
  EmptyState,
  InspectJson,
  MutationForm,
  Panel,
  ReadText,
  SmallLabel,
  SourceLink,
  StatusBadge,
  type FieldSpec,
} from "./components";
import {
  nextOperation,
  operationLabel,
  statusLabel,
  type Translate,
  type MessageKey,
} from "./i18n";
import { TaskCard, TaskComposer } from "./Tasks";
import { ManuscriptTools } from "./ManuscriptTools";
import { DeliveryPanel } from "./Delivery";
import { ReturningWork } from "./ReturningWork";
import { AbstractDraftComposer } from "./AbstractDraft";
import { TextIntakeForm } from "./TextIntake";
import {
  TextIntakeRecoveryPanel,
  useTextIntakeRecovery,
} from "./TextIntakeRecovery";
import type { SavedText } from "./textIntake";
import {
  PreparationRecoveryPanel,
  usePreparationRecovery,
} from "./PrepareRecovery";
import type {
  Operation,
  Page,
  ProjectDetail,
  ResearchRecord,
  SearchResult,
  Workspace,
  Task,
} from "./types";

export interface RecoveredPreparation {
  task: Task;
  workspaceInstance: string;
}

export interface RecoveredText {
  savedText: SavedText;
  workspaceInstance: string;
}
export type RecoveredWork = RecoveredPreparation | RecoveredText;

export interface PagesProps {
  discoveryArtifact?: string | null;
  invalidDiscoveryLink?: boolean;
  composerSessions?: ComposerSessions;
  navigationEpoch?: { current: number };
  detail: ProjectDetail;
  workspace: Workspace;
  page: Page;
  t: Translate;
  onSaved: (message: string, recovered?: RecoveredWork) => Promise<void>;
  navigate: (page: Page, focusId?: string) => void;
}
const textValue = (value: unknown) => String(value ?? "");

export function ProjectPages({
  discoveryArtifact = null,
  invalidDiscoveryLink = false,
  composerSessions: providedSessions,
  navigationEpoch: providedEpoch,
  detail,
  workspace,
  page,
  t,
  onSaved,
  navigate: parentNavigate,
}: PagesProps) {
  const localEpoch = useRef(0);
  const navigationEpoch = providedEpoch ?? localEpoch;
  const [localSessions] = useState(() => new ComposerSessions());
  const composerSessions = providedSessions ?? localSessions;
  const composerScope = composerSessions.scope(workspace);
  const navigate: PagesProps["navigate"] = (...args) => {
    navigationEpoch.current++;
    parentNavigate(...args);
  };
  const recovery = usePreparationRecovery(
    detail.project.id,
    workspace.capabilities.prepare_reconciliation,
    detail.tasks,
    async (task, key) => {
      composerSessions.settlePreparation(
        composerScope,
        detail.project.id,
        key,
        task.id,
      );
      await onSaved(t("taskCreated"), {
        task,
        workspaceInstance:
          workspace.capabilities.prepare_reconciliation!.workspace_instance_id,
      });
    },
    (key) =>
      composerSessions.settlePreparation(composerScope, detail.project.id, key),
  );
  const intake = useTextIntakeRecovery(
    detail.project.id,
    workspace.capabilities.text_intake,
    detail,
    async (savedText) => {
      await onSaved(t("saved"), {
        savedText,
        workspaceInstance:
          workspace.capabilities.text_intake!.workspace_instance_id,
      });
    },
  );
  const [intakeOpen, setIntakeOpen] = useState(false);
  const [intakeIntent, setIntakeIntent] = useState(0);
  const [prepareIntent, setPrepareIntent] = useState(0);
  const [sourceOpenVersion, setSourceOpenVersion] = useState(0);
  function openSavedText(saved: SavedText) {
    setSourceOpenVersion((value) => value + 1);
    setIntakeOpen(false);
    setAbstractSourceId(saved.record.id);
    navigate("literature", "record-" + saved.record.id);
  }
  function linkedArtifact(record: ResearchRecord) {
    return linkedSourceArtifact(record, detail.artifacts, detail.project.id);
  }
  function savedPreview(record: ResearchRecord) {
    const artifact = linkedArtifact(record);
    const saved = intake.entries.find(
      (e) => e.saved?.record.id === record.id,
    )?.saved;
    return artifact?.current &&
      saved?.preview_status === "available" &&
      saved.preview?.sha256 === artifact.sha256
      ? saved.preview
      : undefined;
  }
  const [operation, setOperation] = useState<Operation>("frame");
  const [abstractSourceId, setAbstractSourceId] = useState<string | null>(null);
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [searchWarnings, setSearchWarnings] = useState<string[]>([]);
  const records = (kind: string) =>
    detail.records.filter((record) => record.kind === kind);
  const sources = records("source");
  const sourceOptions = sources.map((source) => ({
    value: source.id,
    label: `${textValue(source.data.title)} · ${source.id}`,
  }));
  const next = nextOperation(detail);
  const pending =
    detail.tasks.find((task) => task.status === "awaiting_human") ??
    detail.tasks.find((task) => ["running", "blocked"].includes(task.status));
  const needSources = records("question").length > 0 && sources.length === 0;
  const recordFields = (names: string[], labels?: MessageKey[]): FieldSpec[] =>
    names.map((name, index) => ({
      name,
      label: t(labels?.[index] ?? (name as MessageKey)),
      textarea: true,
    }));
  async function saveRecord(kind: string, data: Record<string, unknown>) {
    await api(`/projects/${segment(detail.project.id)}/records`, {
      kind,
      data,
    });
    await onSaved(t("saved"));
  }
  const genericForm = (
    kind: string,
    fields: FieldSpec[],
    submit: MessageKey,
    extra: Record<string, unknown> = {},
  ) => (
    <MutationForm
      t={t}
      fields={fields}
      submit={t(submit)}
      onSubmit={async (data) =>
        saveRecord(kind, { ...Object.fromEntries(data), ...extra })
      }
    />
  );
  function recordList(
    items: ResearchRecord[],
    empty: MessageKey,
    render: (record: ResearchRecord) => ReactNode,
  ) {
    return items.length ? (
      <div className="record-list">
        {items.map((record) => (
          <article
            className="research-record"
            key={record.id}
            id={`record-${record.id}`}
            tabIndex={-1}
          >
            {render(record)}
            <InspectJson
              title={`${t("inspect")} · ${record.id}`}
              value={record}
            />
          </article>
        ))}
      </div>
    ) : (
      <EmptyState>{t(empty)}</EmptyState>
    );
  }
  const artifactPanel = (
    <Panel
      title={t("artifacts")}
      meta={<span className="count">{detail.artifacts.length}</span>}
    >
      {detail.artifacts.length ? (
        <div className="file-list">
          {detail.artifacts.map((artifact) => (
            <article key={artifact.id} className="file-row">
              <span className="file-icon" aria-hidden="true">
                ↳
              </span>
              <div>
                <SmallLabel>
                  {artifact.role in roleLabels
                    ? t(roleLabels[artifact.role])
                    : artifact.role}
                </SmallLabel>
                <p className="file-path">{artifactReference(artifact)}</p>
                <details className="inspect">
                  <summary>{t("fingerprint")}</summary>
                  <code className="hash">{artifact.sha256}</code>
                </details>
              </div>
              <span
                className={`badge ${artifact.current ? "neutral" : "warn"}`}
              >
                {artifact.current ? t("current") : t("changed")}
              </span>
            </article>
          ))}
        </div>
      ) : (
        <EmptyState>{t("noArtifacts")}</EmptyState>
      )}
      <Disclosure title={t("registerArtifact")}>
        <MutationForm
          t={t}
          submit={t("registerArtifact")}
          fields={[
            { name: "path", label: t("filePath"), hint: t("filePathHint") },
            {
              name: "role",
              label: t("fileRole"),
              options: Object.entries(roleLabels).map(([value, key]) => ({
                value,
                label: t(key),
              })),
            },
          ]}
          onSubmit={async (data) => {
            await api(
              `/projects/${segment(detail.project.id)}/artifacts`,
              Object.fromEntries(data),
            );
            await onSaved(t("saved"));
          }}
        />
      </Disclosure>
    </Panel>
  );

  return (
    <>
      <TextIntakeRecoveryPanel
        recovery={intake}
        t={t}
        onOpen={openSavedText}
        onSeparate={() => {
          if (intake.blocked) return;
          setIntakeIntent((v) => v + 1);
          setIntakeOpen(true);
          navigate("literature");
        }}
      />
      <PreparationRecoveryPanel
        recovery={recovery}
        onSeparate={() => {
          if (recovery.blocked) return;
          setPrepareIntent((v) => v + 1);
          navigate("literature");
        }}
        t={t}
        onReview={(taskId) => navigate("review", `review-task-${taskId}`)}
      />
      <div hidden={page !== "overview"} className="page-content">
        <section className="next-step">
          <div>
            <SmallLabel>{t("nextStep")}</SmallLabel>
            <h2>
              {pending
                ? statusLabel(pending.status, t)
                : needSources
                  ? t("search")
                  : t(operationLabel(next.operation))}
            </h2>
            <p>
              {pending
                ? t("executionNote")
                : needSources
                  ? t("noSources")
                  : t(next.hint)}
            </p>
            <button
              className="button primary"
              onClick={() => {
                if (pending) navigate("review");
                else if (needSources) navigate("literature");
                else {
                  setOperation(next.operation);
                  navigate("review");
                }
              }}
            >
              {pending
                ? t("viewReview")
                : needSources
                  ? t("viewLiterature")
                  : t("prepareTask")}
              <span aria-hidden="true">↗</span>
            </button>
          </div>
          <div className="folio" aria-hidden="true">
            <span>RESEARCH / FIELDNOTES</span>
            <i />
            <i />
            <i />
            <strong>
              {String(records("question").length + 1).padStart(2, "0")}
            </strong>
          </div>
        </section>
        <div className="page-grid">
          <div className="main-column">
            <Panel title={t("projectBrief")}>
              <div className="brief">
                <SmallLabel>{t("goal")}</SmallLabel>
                <p className="goal-text">
                  {detail.project.goal || t("noGoal")}
                </p>
                <div className="question-block">
                  <SmallLabel>{t("researchQuestion")}</SmallLabel>
                  {records("question").length ? (
                    records("question").map((record) => (
                      <ReadText key={record.id} value={record.data.text} />
                    ))
                  ) : (
                    <p className="muted">{t("noQuestion")}</p>
                  )}
                </div>
              </div>
              <Disclosure title={t("addQuestion")}>
                {genericForm(
                  "question",
                  [{ name: "text", label: t("question"), textarea: true }],
                  "addQuestion",
                )}
              </Disclosure>
            </Panel>
            <ReturningWork detail={detail} t={t} navigate={navigate} />
          </div>
          <aside className="side-column">
            <Panel title={t("workbench")}>
              <dl className="inventory">
                <div>
                  <dt>{t("literature")}</dt>
                  <dd>
                    {sources.length}
                    <span>{t("sourceCount")}</span>
                  </dd>
                </div>
                <div>
                  <dt>{t("evidence")}</dt>
                  <dd>
                    {records("claim").length}
                    <span>{t("claimCount")}</span>
                  </dd>
                </div>
                <div>
                  <dt>{t("artifacts")}</dt>
                  <dd>
                    {detail.artifacts.length}
                    <span>{t("artifactCount")}</span>
                  </dd>
                </div>
              </dl>
            </Panel>
            <Readiness workspace={workspace} t={t} />
          </aside>
        </div>
      </div>

      <div hidden={page !== "literature"} className="page-content">
        <DiscoveryPanel
          projectId={detail.project.id}
          artifacts={detail.artifacts}
          selected={discoveryArtifact}
          invalid={invalidDiscoveryLink}
          active={page === "literature"}
          t={t}
        />
        <div>
          <button
            className="button primary"
            disabled={!intake.supported || intakeOpen}
            onClick={() => {
              setIntakeOpen(true);
              setAbstractSourceId(null);
            }}
          >
            {t("intakeAdd")}
          </button>
          {!intake.supported && (
            <p role="status">
              {t("intakeUnavailable")}{" "}
              {workspace.capabilities.text_intake?.message}
            </p>
          )}
        </div>
        {intakeOpen && (
          <TextIntakeForm
            key={intakeIntent}
            recovery={intake}
            t={t}
            onClose={() => setIntakeOpen(false)}
            onOpen={openSavedText}
          />
        )}

        <Panel title={t("search")} className="search-panel">
          <MutationForm
            t={t}
            submit={t("searchAction")}
            reset={false}
            fields={[{ name: "query", label: t("searchQuery") }]}
            onSubmit={async (data) => {
              const value = await api<{
                ok: true;
                results: SearchResult[];
                warnings: string[];
              }>(`/projects/${segment(detail.project.id)}/search`, {
                query: data.get("query"),
                limit: 5,
              });
              setResults(value.results);
              setSearchWarnings(value.warnings ?? []);
              await onSaved(t("saved"));
            }}
          />
          {searchWarnings.map((warning, index) => (
            <p className="notice" key={index}>
              {warning}
            </p>
          ))}
          {results !== null && (
            <section className="search-results">
              <h3>{t("searchResults")}</h3>
              {results.length ? (
                results.map((result) => (
                  <div key={result.source_id} className="search-result">
                    <div>
                      <h4>{result.title}</h4>
                      <SourceLink locator={result.locator} />
                      <p className="small muted">{result.doi}</p>
                    </div>
                    <MutationForm
                      t={t}
                      fields={[]}
                      submit={t("addSource")}
                      onSubmit={async () => {
                        await saveRecord("source", {
                          title: result.title,
                          locator: result.locator ?? "",
                          doi: result.doi ?? "",
                          identity_status: "unverified",
                        });
                      }}
                    />
                  </div>
                ))
              ) : (
                <EmptyState compact>{t("noResults")}</EmptyState>
              )}
            </section>
          )}
        </Panel>
        <div className="page-grid">
          <Panel
            title={t("sources")}
            meta={<span className="count">{sources.length}</span>}
          >
            {recordList(sources, "noSources", (record) => (
              <>
                <div className="record-title">
                  <h3>{textValue(record.data.title)}</h3>
                  <span className="badge neutral">
                    {statusLabel(
                      textValue(record.data.identity_status || "unverified"),
                      t,
                    )}
                  </span>
                </div>
                {record.data.locator_kind === "local-copy" ? (
                  <p>{t("intakeLocalLocator")}</p>
                ) : (
                  <SourceLink locator={record.data.locator} />
                )}
                <p className="small muted">{textValue(record.data.doi)}</p>
                {record.data.intake != null && (
                  <p>
                    {t("intakeDeclaredScope")}:{" "}
                    {t(
                      record.data.reading_scope === "abstract"
                        ? "intakeScopeAbstract"
                        : "intakeScopeUnknown",
                    )}
                  </p>
                )}
                <code className="record-id">{record.id}</code>
                <button
                  className="button secondary"
                  onClick={() => {
                    navigationEpoch.current++;
                    setIntakeOpen(false);
                    setSourceOpenVersion((value) => value + 1);
                    setAbstractSourceId(record.id);
                  }}
                >
                  {t("abstractOpen")}
                </button>
                {abstractSourceId === record.id && (
                  <AbstractDraftComposer
                    key={JSON.stringify([composerScope, record.id])}
                    navigationEpoch={navigationEpoch}
                    sessions={composerSessions}
                    sessionKey={
                      composerScope.startsWith("invalid:")
                        ? undefined
                        : JSON.stringify([
                            composerScope,
                            detail.project.id,
                            record.id,
                          ])
                    }
                    projectId={detail.project.id}
                    source={record}
                    artifacts={detail.artifacts}
                    artifactLabels={sourceArtifactLabels(
                      detail.records,
                      detail.artifacts,
                      detail.project.id,
                      t,
                    )}
                    separateIntentVersion={prepareIntent}
                    restoreVersion={sourceOpenVersion}
                    initialArtifactId={linkedArtifact(record)?.id}
                    initialPreview={savedPreview(record)}
                    capability={workspace.capabilities.codex}
                    recovery={recovery}
                    t={t}
                    onReview={(taskId) =>
                      navigate(
                        "review",
                        taskId ? `review-task-${taskId}` : undefined,
                      )
                    }
                    onCancel={() => {
                      setAbstractSourceId(null);
                      navigate("literature", `record-${record.id}`);
                    }}
                    onPrepared={async () => {
                      await onSaved(t("taskCreated"));
                    }}
                  />
                )}
              </>
            ))}
            <Disclosure title={t("addSource")}>
              {genericForm(
                "source",
                [
                  { name: "title", label: t("title") },
                  { name: "locator", label: t("locator") },
                  { name: "doi", label: t("doi"), required: false },
                ],
                "addSource",
                { identity_status: "unverified" },
              )}
            </Disclosure>
          </Panel>
          <Panel title={t("screening")}>
            {recordList(records("screening"), "noScreening", (record) => {
              const source = sources.find(
                (item) => item.id === record.data.source_id,
              );
              return (
                <>
                  <div className="record-title">
                    {source ? (
                      <h3>
                        {textValue(source.data.title).trim() ||
                          t("screeningSourceUntitled")}
                      </h3>
                    ) : (
                      <p>{t("screeningSourceUnavailable")}</p>
                    )}
                    <span className="badge neutral">
                      {statusLabel(textValue(record.data.decision), t)}
                    </span>
                  </div>
                  <code className="record-id">
                    {textValue(record.data.source_id)}
                  </code>
                  {source && (
                    <>
                      <p>
                        {t("intakeDeclaredScope")}:{" "}
                        {t(
                          source.data.reading_scope === "abstract"
                            ? "intakeScopeAbstract"
                            : "intakeScopeUnknown",
                        )}
                      </p>
                      <button
                        className="button secondary"
                        onClick={() =>
                          navigate("literature", `record-${source.id}`)
                        }
                      >
                        {t("abstractReturnSource")}
                      </button>
                    </>
                  )}
                  <ReadText value={record.data.rationale} />
                </>
              );
            })}
            <Disclosure title={t("screenSource")}>
              <MutationForm
                t={t}
                submit={t("screenSource")}
                note={t("sourceHelp")}
                disabled={!sources.length}
                fields={[
                  {
                    name: "source_id",
                    label: t("source"),
                    options: sourceOptions,
                  },
                  {
                    name: "decision",
                    label: t("decision"),
                    options: [
                      { value: "include", label: t("include") },
                      { value: "exclude", label: t("exclude") },
                    ],
                  },
                  { name: "rationale", label: t("rationale"), textarea: true },
                ]}
                onSubmit={async (data) =>
                  saveRecord("screening", Object.fromEntries(data))
                }
              />
            </Disclosure>
          </Panel>
        </div>
      </div>

      <div hidden={page !== "evidence"} className="page-content">
        <div className="page-grid">
          <Panel
            title={t("claims")}
            meta={<span className="count">{records("claim").length}</span>}
          >
            {recordList(records("claim"), "noClaims", (record) => (
              <>
                <ReadText value={record.data.text} />
                <div className="evidence-links">
                  <SmallLabel>{t("sourceIds")}</SmallLabel>
                  {Array.isArray(record.data.source_ids) &&
                  record.data.source_ids.length ? (
                    record.data.source_ids.map((id) => {
                      const source = sources.find((item) => item.id === id);
                      return (
                        <div key={String(id)}>
                          <code>{String(id)}</code>
                          {source && (
                            <SourceLink
                              locator={source.data.locator}
                              title={textValue(source.data.title)}
                            />
                          )}
                        </div>
                      );
                    })
                  ) : (
                    <span className="missing-evidence">{t("unsupported")}</span>
                  )}
                </div>
                <div className="limitation">
                  <SmallLabel>{t("uncertainty")}</SmallLabel>
                  <ReadText value={record.data.uncertainty} />
                </div>
              </>
            ))}
          </Panel>
          <Panel title={t("addClaim")}>
            <MutationForm
              t={t}
              submit={t("addClaim")}
              fields={[
                { name: "text", label: t("claim"), textarea: true },
                {
                  name: "source_ids",
                  label: t("sourceIds"),
                  hint: t("sourceIdsHelp"),
                  required: false,
                  multiple: true,
                  options: sourceOptions,
                },
                {
                  name: "uncertainty",
                  label: t("uncertainty"),
                  textarea: true,
                },
              ]}
              onSubmit={async (data) =>
                saveRecord("claim", {
                  text: data.get("text"),
                  source_ids: data.getAll("source_ids"),
                  uncertainty: data.get("uncertainty"),
                })
              }
            />
          </Panel>
        </div>
      </div>

      <div hidden={page !== "design"} className="page-content">
        <div className="page-grid">
          <Panel title={t("analysis")}>
            {recordList(records("analysis"), "noAnalysis", (record) => (
              <>
                <h3>{textValue(record.data.question)}</h3>
                {(["method", "result", "limitation"] as const).map((key) => (
                  <div
                    key={key}
                    className={
                      key === "limitation" ? "limitation" : "record-part"
                    }
                  >
                    <SmallLabel>{t(key)}</SmallLabel>
                    <ReadText value={record.data[key]} />
                  </div>
                ))}
              </>
            ))}
            <Disclosure title={t("addAnalysis")}>
              {genericForm(
                "analysis",
                recordFields(["question", "method", "result", "limitation"]),
                "addAnalysis",
              )}
            </Disclosure>
          </Panel>
          {artifactPanel}
        </div>
      </div>

      <div hidden={page !== "manuscript"} className="page-content">
        <ManuscriptTools detail={detail} t={t} onSaved={onSaved} />
        <div className="page-grid">
          <Panel title={t("argument")}>
            {recordList(records("outline"), "noOutline", (record) => (
              <>
                <h3>{textValue(record.data.section)}</h3>
                {(["function", "claim", "evidence", "bridge"] as const).map(
                  (key) => (
                    <div className="record-part" key={key}>
                      <SmallLabel>{t(key)}</SmallLabel>
                      <ReadText value={record.data[key]} />
                    </div>
                  ),
                )}
              </>
            ))}
            <Disclosure title={t("addOutline")}>
              {genericForm(
                "outline",
                recordFields([
                  "section",
                  "function",
                  "claim",
                  "evidence",
                  "bridge",
                ]),
                "addOutline",
              )}
            </Disclosure>
          </Panel>
          <div className="side-column">
            <Panel title={t("manuscriptState")}>
              {detail.manuscript ? (
                <InspectJson title={t("inspect")} value={detail.manuscript} />
              ) : (
                <EmptyState>{t("noManuscript")}</EmptyState>
              )}
              <button
                className="button secondary panel-button"
                onClick={() => {
                  setOperation(records("outline").length ? "draft" : "outline");
                  navigate("review");
                }}
              >
                {t("prepareTask")}
                <span aria-hidden="true">↗</span>
              </button>
            </Panel>
            {detail.workflow && (
              <Panel title={t("workflowState")}>
                <InspectJson title={t("inspect")} value={detail.workflow} />
              </Panel>
            )}
            <Panel title={t("registerArtifact")}>
              <MutationForm
                t={t}
                submit={t("registerArtifact")}
                fields={[
                  {
                    name: "path",
                    label: t("filePath"),
                    hint: t("filePathHint"),
                  },
                ]}
                onSubmit={async (data) => {
                  await api(
                    `/projects/${segment(detail.project.id)}/artifacts`,
                    { path: data.get("path"), role: "main_manuscript" },
                  );
                  await onSaved(t("saved"));
                }}
              />
            </Panel>
          </div>
        </div>
      </div>

      <div hidden={page !== "review"} className="page-content">
        <button
          className="button secondary"
          onClick={() => navigate("overview")}
        >
          {t("returnOverview")}
        </button>
        <div className="notice execution-note">
          <span aria-hidden="true">↳</span>
          <p>{t("executionNote")}</p>
        </div>
        <div className="page-grid">
          <div className="main-column">
            <Panel
              title={t("recentActivity")}
              meta={<span className="count">{detail.tasks.length}</span>}
            >
              {detail.tasks.length ? (
                <div className="task-list">
                  {detail.tasks.map((task) => (
                    <div
                      key={task.id}
                      id={`review-task-${task.id}`}
                      tabIndex={-1}
                    >
                      <TaskCard
                        runnerAvailable={
                          workspace.capabilities.codex.status === "available"
                        }
                        onReturnToSource={(sourceId) => {
                          setAbstractSourceId(sourceId);
                          navigate("literature", `record-${sourceId}`);
                        }}
                        task={task}
                        approvalMessage={
                          workspace.capabilities.approval.message
                        }
                        t={t}
                        onSaved={onSaved}
                      />
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyState>{t("noTasks")}</EmptyState>
              )}
            </Panel>
            <Panel title={t("comments")}>
              {recordList(records("review"), "noComments", (record) => (
                <>
                  <div className="record-title">
                    <span className="badge neutral">
                      {statusLabel(textValue(record.data.severity), t)}
                    </span>
                    <span className="badge neutral">
                      {statusLabel(textValue(record.data.status), t)}
                    </span>
                  </div>
                  <ReadText value={record.data.comment} />
                </>
              ))}
              <Disclosure title={t("addComment")}>
                {genericForm(
                  "review",
                  [
                    { name: "comment", label: t("comment"), textarea: true },
                    {
                      name: "severity",
                      label: t("severity"),
                      options: ["S0", "S1", "S2", "S3", "S4"].map((value) => ({
                        value,
                        label: value,
                      })),
                    },
                  ],
                  "addComment",
                  { status: "OPEN" },
                )}
              </Disclosure>
            </Panel>
          </div>
          <aside className="side-column">
            <Panel title={t("prepareTask")}>
              <TaskComposer
                projectId={detail.project.id}
                operation={operation}
                t={t}
                onSaved={onSaved}
              />
            </Panel>
            <Readiness workspace={workspace} t={t} />
          </aside>
        </div>
        <div id="review-local-delivery" tabIndex={-1}>
          <DeliveryPanel
            projectId={detail.project.id}
            tasks={detail.tasks}
            actions={detail.actions ?? []}
            t={t}
            onSaved={onSaved}
          />
        </div>
      </div>
    </>
  );
}

const roleLabels: Record<string, MessageKey> = {
  evidence: "evidence",
  main_manuscript: "main_manuscript",
  figure: "figure",
  table: "table",
  supplement: "supplement",
  analysis: "analysis",
  reviewer_response: "reviewer_response",
};

export function Readiness({
  workspace,
  t,
}: {
  workspace: Workspace;
  t: Translate;
}) {
  return (
    <Panel title={t("readiness")} className="readiness-panel">
      <div className="capability-list">
        {(["codex", "writing", "approval"] as const).map((key) => {
          const capability = workspace.capabilities[key];
          return (
            <details key={key} className="capability">
              <summary>
                <span>{t(key)}</span>
                <span className="capability-status">
                  {statusLabel(capability?.status || t("noCapability"), t)}
                </span>
              </summary>
              <p>{capability?.message}</p>
            </details>
          );
        })}
      </div>
      <SetupSnapshotView workspace={workspace} t={t} />
      <details className="protection">
        <summary>{t("protection")}</summary>
        <p>{workspace.protection_scope}</p>
      </details>
    </Panel>
  );
}

function SetupSnapshotView({
  workspace,
  t,
}: {
  workspace: Workspace;
  t: Translate;
}) {
  const snapshot = workspace.setup_snapshot;
  const freshnessLabels = {
    missing: "snapshotMissing",
    invalid: "snapshotInvalid",
    clock_skew: "snapshotClockSkew",
    stale: "snapshotStale",
    saved: "snapshotSaved",
  } as const;
  const labels = {
    environment: "snapshotEnvironment",
    vault: "snapshotVault",
    zotero: "snapshotZotero",
    notebooklm_auth: "snapshotNlm",
    llm_cli: "snapshotCli",
    skills: "snapshotSkills",
  } as const;
  const statuses = {
    passed: "snapshotPassed",
    failed: "snapshotFailed",
    cancelled: "snapshotCancelled",
    skipped: "snapshotSkipped",
    unknown: "snapshotUnknown",
  } as const;
  const freshness = snapshot?.freshness || "missing";
  return (
    <details className="protection">
      <summary>
        {t("setupSnapshot")}:{" "}
        {t(freshnessLabels[freshness] || "snapshotInvalid")}
      </summary>
      <p>{t("snapshotScope")}</p>
      {snapshot?.observed_at && (
        <p>
          {t("snapshotObserved")}: <time>{snapshot.observed_at}</time>
        </p>
      )}
      {snapshot && (
        <p>
          {t("snapshotWindow")}: {snapshot.display_max_age_seconds}
        </p>
      )}
      <ul>
        {Object.entries(labels).map(([key, label]) => {
          const status =
            freshness === "saved" ? snapshot?.components?.[key] : "unknown";
          const message =
            statuses[status as keyof typeof statuses] || "snapshotUnknown";
          return (
            <li key={key}>
              {t(label)}: {t(message)}
            </li>
          );
        })}
      </ul>
      <p>{t("snapshotNext")}</p>
    </details>
  );
}
