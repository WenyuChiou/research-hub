import { useState, type ReactNode } from "react";
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
import type {
  Operation,
  Page,
  ProjectDetail,
  ResearchRecord,
  SearchResult,
  Workspace,
} from "./types";

export interface PagesProps {
  detail: ProjectDetail;
  workspace: Workspace;
  page: Page;
  t: Translate;
  onSaved: (message: string) => Promise<void>;
  navigate: (page: Page) => void;
}
const textValue = (value: unknown) => String(value ?? "");

export function ProjectPages({
  detail,
  workspace,
  page,
  t,
  onSaved,
  navigate,
}: PagesProps) {
  const [operation, setOperation] = useState<Operation>("frame");
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
  const pending = detail.tasks.find((task) => task.status === "awaiting_human") ?? detail.tasks.find((task) => ["running", "blocked"].includes(task.status));
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
          <article className="research-record" key={record.id}>
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
                <p className="file-path">{artifact.path}</p>
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
      <div hidden={page !== "overview"} className="page-content">
        <section className="next-step">
          <div>
            <SmallLabel>{t("nextStep")}</SmallLabel>
            <h2>
              {pending ? statusLabel(pending.status, t) : needSources ? t("search") : t(operationLabel(next.operation))}
            </h2>
            <p>{pending ? t("executionNote") : needSources ? t("noSources") : t(next.hint)}</p>
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
              {pending ? t("viewReview") : needSources ? t("viewLiterature") : t("prepareTask")}
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
            <Panel
              title={t("recentActivity")}
              meta={
                <a href="#review">
                  {t("viewReview")} <span aria-hidden="true">↗</span>
                </a>
              }
            >
              {detail.tasks.length ? (
                <div className="activity-list">
                  {detail.tasks
                    .slice(0, 5)
                    .reverse()
                    .map((task) => (
                      <div key={task.id} className="activity-row">
                        <span className="activity-mark" aria-hidden="true">
                          ↗
                        </span>
                        <div>
                          <strong>{t(operationLabel(task.operation))}</strong>
                          <code>{task.id}</code>
                        </div>
                        <StatusBadge status={task.status} t={t} />
                      </div>
                    ))}
                </div>
              ) : (
                <EmptyState>{t("noTasks")}</EmptyState>
              )}
            </Panel>
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
                <SourceLink locator={record.data.locator} />
                <p className="small muted">{textValue(record.data.doi)}</p>
                <code className="record-id">{record.id}</code>
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
            {recordList(records("screening"), "noScreening", (record) => (
              <>
                <div className="record-title">
                  <code>{textValue(record.data.source_id)}</code>
                  <span className="badge neutral">
                    {statusLabel(textValue(record.data.decision), t)}
                  </span>
                </div>
                <ReadText value={record.data.rationale} />
              </>
            ))}
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
                    <TaskCard
                      key={task.id}
                      task={task}
                      approvalMessage={workspace.capabilities.approval.message}
                      t={t}
                      onSaved={onSaved}
                    />
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
        <DeliveryPanel
          projectId={detail.project.id}
          tasks={detail.tasks}
          actions={detail.actions ?? []}
          t={t}
          onSaved={onSaved}
        />
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
      <details className="protection">
        <summary>{t("protection")}</summary>
        <p>{workspace.protection_scope}</p>
      </details>
    </Panel>
  );
}
