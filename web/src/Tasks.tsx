import { useEffect, useId, useRef, useState } from "react";
import { api, downloadPacket, metaToken, segment } from "./api";
import {
  Disclosure,
  ErrorMessage,
  InspectJson,
  MutationForm,
  SmallLabel,
  StatusBadge,
} from "./components";
import { operationLabel, type Translate } from "./i18n";
import { AbstractDraftReview, uncertainMutation } from "./AbstractDraft";
import type { Operation, Task } from "./types";
import { taskFreshnessStatus } from "./taskFreshness";

export interface TaskComposerProps {
  projectId: string;
  operation: Operation;
  t: Translate;
  onSaved: (message: string) => Promise<void>;
}
export function TaskComposer({
  projectId,
  operation,
  t,
  onSaved,
}: TaskComposerProps) {
  const operations: Operation[] = [
    "frame",
    "synthesize",
    "outline",
    "draft",
    "review",
    "revise",
    "rebuttal",
    "audit",
  ];
  return (
    <MutationForm
      key={operation}
      t={t}
      submit={t("createTask")}
      note={t("taskHelp")}
      fields={[
        {
          name: "operation",
          label: t("operation"),
          defaultValue: operation,
          options: operations.map((value) => ({
            value,
            label: t(operationLabel(value)),
          })),
        },
        {
          name: "mode",
          label: t("mode"),
          options: [
            { value: "handoff", label: t("handoff") },
            { value: "connected", label: t("connected") },
          ],
        },
        { name: "instructions", label: t("instructions"), textarea: true },
      ]}
      onSubmit={async (data) => {
        await api(
          `/projects/${segment(projectId)}/tasks`,
          Object.fromEntries(data),
        );
        await onSaved(t("taskCreated"));
      }}
    />
  );
}

export function parseOutputArtifacts(
  value: string,
): { path: string; sha256: string }[] {
  return value
    .split(/\r?\n/)
    .filter((line) => line.trim())
    .map((line) => {
      const separator = line.lastIndexOf("|");
      const path = line.slice(0, separator).trim();
      const sha256 = line.slice(separator + 1).trim();
      if (separator < 1 || !path || !/^[0-9a-fA-F]{64}$/.test(sha256))
        throw new Error("invalid_artifacts");
      return { path, sha256 };
    });
}

export interface TaskCardProps {
  task: Task;
  runnerAvailable?: boolean;
  onReturnToSource?: (sourceId: string) => void;
  approvalMessage: string;
  t: Translate;
  onSaved: (message: string) => Promise<void>;
}
export function TaskCard({
  task,
  approvalMessage,
  t,
  onSaved,
  runnerAvailable = false,
  onReturnToSource,
}: TaskCardProps) {
  const revisionHeadingId = useId();
  const revision = taskFreshnessStatus(task);
  const abstractDraft = task.operation === "paper-abstract-draft";
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [runLocked, setRunLocked] = useState(false);
  const runLock = useRef(false);
  const [runUncertain, setRunUncertain] = useState(false);
  useEffect(() => {
    // A new object with the same preparable state is not a receipt that an
    // uncertain Run never started. Only observed post-claim/review/terminal
    // state resolves this local uncertainty; never retry the write here.
    if (
      [
        "running",
        "awaiting_human",
        "completed",
        "failed",
        "cancelled",
        "declined",
        "blocked",
      ].includes(task.status)
    ) {
      runLock.current = false;
      setRunLocked(false);
      setRunUncertain(false);
    }
  }, [task]);
  const humanEnabled = Boolean(metaToken("research-hub-human-token"));
  const runnable =
    task.mode === "connected" &&
    ["ready", "awaiting_agent"].includes(task.status);
  const importable =
    !abstractDraft &&
    ["ready", "awaiting_agent", "blocked"].includes(task.status);
  const handoffable =
    !abstractDraft &&
    task.mode === "handoff" &&
    task.status === "awaiting_agent";
  const cancellable = [
    "ready",
    "awaiting_agent",
    "running",
    "awaiting_human",
    "blocked",
  ].includes(task.status);
  async function action(kind: "run" | "handoff" | "cancel" | "recover") {
    if (abstractDraft && kind === "run" && runLock.current) return;
    setBusy(true);
    setError(null);
    if (abstractDraft && kind === "run") {
      runLock.current = true;
      setRunLocked(true);
    }
    try {
      const value = await api<{ ok: true; task: Task; packet?: unknown }>(
        `/tasks/${segment(task.id)}/${kind}`,
        {},
      );
      if (kind === "handoff") {
        if (!value.packet)
          throw new Error("The handoff response did not contain a packet.");
        downloadPacket(value.packet, task.id);
      }
      const message =
        kind === "run"
          ? "runStarted"
          : kind === "handoff"
            ? "handoffDownloaded"
            : kind === "cancel"
              ? "taskCancelled"
              : "recoveryInspected";
      await onSaved(t(message));
    } catch (failure) {
      setError(failure);
      if (abstractDraft && kind === "run") {
        setRunUncertain(uncertainMutation(failure));
        if (!uncertainMutation(failure)) {
          runLock.current = false;
          setRunLocked(false);
        }
      }
    } finally {
      setBusy(false);
    }
  }
  return (
    <article className="task-card">
      <div className="task-heading">
        <div>
          <SmallLabel>
            {task.mode === "connected" ? t("connected") : t("handoff")}
          </SmallLabel>
          <h3>{t(operationLabel(task.operation))}</h3>
          <code className="record-id">{task.id}</code>
        </div>
        <StatusBadge status={task.status} t={t} />
      </div>
      <section
        className="tool-intro task-revision"
        aria-labelledby={revisionHeadingId}
      >
        <h4 id={revisionHeadingId}>{t("taskRevisionCheck")}</h4>
        <p>
          <strong>
            {t(
              revision === "current"
                ? "taskRevisionCurrent"
                : revision === "stale"
                  ? "taskRevisionStale"
                  : "taskRevisionUnknown",
            )}
          </strong>
        </p>
        <p>
          {t(
            revision === "current"
              ? "taskRevisionCurrentNote"
              : revision === "stale"
                ? "taskRevisionStaleNote"
                : "taskRevisionUnknownNote",
          )}
        </p>
        {task.status === "completed" && revision !== "current" && (
          <p>{t("taskRevisionHistoricalAcceptance")}</p>
        )}
      </section>
      <div className="button-row">
        {runnable && (
          <button
            className="button primary"
            disabled={
              busy || (abstractDraft && (!runnerAvailable || runLocked))
            }
            onClick={() => void action("run")}
          >
            {busy ? t("preparing") : t("runTask")}{" "}
            <span aria-hidden="true">↗</span>
          </button>
        )}
        {handoffable && (
          <button
            className="button secondary"
            disabled={busy}
            onClick={() => void action("handoff")}
          >
            {busy ? t("preparing") : t("downloadHandoff")}{" "}
            <span aria-hidden="true">↓</span>
          </button>
        )}
        {cancellable && (
          <button
            className="button secondary"
            disabled={busy}
            onClick={() => void action("cancel")}
          >
            {t("cancelTask")}
          </button>
        )}
      </div>
      {abstractDraft && (
        <>
          {runUncertain && <p role="status">{t("abstractRunUncertain")}</p>}
          {task.mode === "handoff" && (
            <p role="status">{t("abstractHandoffUnsupported")}</p>
          )}
          {!runnerAvailable && (
            <p role="status">{t("abstractRunnerUnavailable")}</p>
          )}
          <AbstractDraftReview
            task={task}
            t={t}
            onReturnToSource={onReturnToSource}
          />
        </>
      )}
      {task.status === "running" && (
        <Disclosure title={t("taskRecovery")}>
          <div className="tool-intro">
            <p>{t("taskRecoveryNote")}</p>
            <button
              className="button secondary"
              disabled={busy}
              onClick={() => void action("recover")}
            >
              {t("inspectInterruptedRun")}
            </button>
          </div>
        </Disclosure>
      )}
      {error !== null && <ErrorMessage error={error} t={t} />}
      {task.error && <ErrorMessage error={new Error(task.error)} t={t} />}
      {task.blocker && <p role="status">{task.blocker}</p>}
      {task.execution_provenance && (
        <InspectJson
          title={t("taskDiagnostics")}
          value={task.execution_provenance}
        />
      )}
      <details className="inspect">
        <summary>{t("taskDetails")}</summary>
        <dl className="metadata">
          <dt>{t("actionHash")}</dt>
          <dd>
            <code>{task.action_hash}</code>
          </dd>
          <dt>{t("status")}</dt>
          <dd>{task.status}</dd>
        </dl>
      </details>
      {task.result ? (
        <InspectJson title={t("taskOutput")} value={task.result} />
      ) : !task.error && !task.blocker ? (
        <p className="muted small">{t("noOutput")}</p>
      ) : null}
      {importable && (
        <Disclosure title={t("importResult")}>
          <MutationForm
            t={t}
            submit={t("importAction")}
            note={t("importHelp")}
            fields={[
              {
                name: "input_hash",
                label: t("inputHash"),
                hint: t("inputHashHelp"),
                pattern: "[0-9a-fA-F]{64}",
                maxLength: 64,
              },
              { name: "prose", label: t("prose"), textarea: true },
              {
                name: "status",
                label: t("outputStatus"),
                options: [
                  { value: "completed", label: t("completedOption") },
                  { value: "failed", label: t("failedOption") },
                ],
              },
              {
                name: "artifacts",
                label: t("outputArtifacts"),
                textarea: true,
                required: false,
                hint: t("outputArtifactsHelp"),
              },
            ]}
            onSubmit={async (data) => {
              let artifacts: { path: string; sha256: string }[];
              try {
                artifacts = parseOutputArtifacts(
                  String(data.get("artifacts") || ""),
                );
              } catch {
                throw new Error(t("invalidArtifacts"));
              }
              await api(`/tasks/${segment(task.id)}/result`, {
                input_hash: data.get("input_hash"),
                prose: data.get("prose"),
                status: data.get("status"),
                artifacts,
              });
              await onSaved(t("resultImported"));
            }}
          />
        </Disclosure>
      )}
      {task.status === "awaiting_human" && (
        <section className="decision-box">
          <h4>{t("humanDecision")}</h4>
          <p>{t("executionNote")}</p>
          {humanEnabled ? (
            <MutationForm
              key={task.action_hash}
              t={t}
              submit={t("recordDecision")}
              fields={[
                {
                  name: "outcome",
                  label: t("outcome"),
                  options: [
                    { value: "revise", label: t("requestRevision") },
                    { value: "accept", label: t("accept") },
                    { value: "decline", label: t("decline") },
                    { value: "cancel", label: t("cancelTask") },
                  ],
                },
                { name: "actor", label: t("actor") },
                { name: "rationale", label: t("rationale"), textarea: true },
              ]}
              onSubmit={async (data) => {
                await api(`/tasks/${segment(task.id)}/decision`, {
                  ...Object.fromEntries(data),
                  action_hash: task.action_hash,
                });
                await onSaved(t("decisionSaved"));
              }}
            />
          ) : (
            <>
              <p>{t("approvalUnavailable")}</p>
              <pre className="cli-instruction">{approvalMessage}</pre>
              <button className="button secondary" disabled>
                {t("recordDecision")}
              </button>
            </>
          )}
        </section>
      )}
    </article>
  );
}
