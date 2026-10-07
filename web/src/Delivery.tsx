import { useState } from "react";
import { api, metaToken, segment } from "./api";
import {
  EmptyState,
  ErrorMessage,
  InspectJson,
  MutationForm,
  Panel,
  SmallLabel,
} from "./components";
import { operationLabel, statusTone, type Translate } from "./i18n";
import type { DeliveryAction, Task } from "./types";

export function candidateArtifacts(
  task: Task,
): { path: string; sha256: string }[] {
  if (
    !task.result ||
    typeof task.result !== "object" ||
    !("artifacts" in task.result)
  )
    return [];
  const artifacts = task.result.artifacts;
  if (!Array.isArray(artifacts)) return [];
  return artifacts.filter(
    (artifact): artifact is { path: string; sha256: string } =>
      Boolean(
        artifact &&
        typeof artifact === "object" &&
        typeof artifact.path === "string" &&
        artifact.path.trim() &&
        typeof artifact.sha256 === "string" &&
        /^[0-9a-f]{64}$/i.test(artifact.sha256),
      ),
  );
}
export function deliveryEligible(task: Task): boolean {
  return (
    task.status === "completed" &&
    task.acceptance_current !== false &&
    candidateArtifacts(task).length > 0
  );
}

export interface DeliveryPanelProps {
  projectId: string;
  tasks: Task[];
  actions: DeliveryAction[];
  t: Translate;
  onSaved: (message: string) => Promise<void>;
}
export function DeliveryPanel({
  projectId,
  tasks,
  actions,
  t,
  onSaved,
}: DeliveryPanelProps) {
  const eligible = tasks.filter(deliveryEligible);
  return (
    <Panel title={t("proposalDelivery")} className="delivery-panel">
      <p className="tool-intro">{t("deliveryScopeNote")}</p>
      {eligible.length ? (
        <MutationForm
          t={t}
          fields={[]}
          submit={t("prepareDelivery")}
          successMessage={false}
          note={t("deliverySelectionNote")}
          onSubmit={async (data) => {
            const ids = data.getAll("task_ids").map(String);
            if (
              !ids.length ||
              ids.some((id) => !eligible.some((task) => task.id === id))
            )
              throw new Error(t("selectAcceptedTask"));
            await api(`/projects/${segment(projectId)}/delivery`, {
              task_ids: ids,
            });
            await onSaved(t("deliveryPrepared"));
          }}
        >
          <fieldset className="candidate-selection">
            <legend>{t("acceptedCandidates")}</legend>
            {eligible.map((task) => (
              <label key={task.id} className="candidate-option">
                <input type="checkbox" name="task_ids" value={task.id} />
                <span>
                  <strong>{t(operationLabel(task.operation))}</strong>
                  <code>{task.id}</code>
                  {candidateArtifacts(task).map((artifact) => (
                    <span
                      className="candidate-path"
                      key={`${artifact.path}-${artifact.sha256}`}
                    >
                      {artifact.path}
                      <code>{artifact.sha256}</code>
                    </span>
                  ))}
                </span>
              </label>
            ))}
          </fieldset>
        </MutationForm>
      ) : (
        <EmptyState>{t("noAcceptedCandidates")}</EmptyState>
      )}
      <div className="delivery-actions">
        {actions.map((action) => (
          <DeliveryCard
            key={action.id}
            action={action}
            t={t}
            onSaved={onSaved}
          />
        ))}
      </div>
    </Panel>
  );
}

export interface DeliveryCardProps {
  action: DeliveryAction;
  t: Translate;
  onSaved: (message: string) => Promise<void>;
}
export function DeliveryCard({ action, t, onSaved }: DeliveryCardProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const humanEnabled = Boolean(metaToken("research-hub-human-token"));
  async function operate(operation: "execute" | "reconcile") {
    setBusy(true);
    setError(null);
    try {
      await api(`/actions/${segment(action.id)}/${operation}`, {});
      await onSaved(
        t(
          operation === "execute"
            ? "deliveryExecutionUpdated"
            : "deliveryReconciled",
        ),
      );
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  }
  const label =
    action.status === "completed"
      ? t("deliveryComplete")
      : action.status === "approved"
        ? t("deliveryApproved")
        : action.status === "pending_external_action"
          ? t("deliveryPending")
          : action.status === "awaiting_human"
            ? t("awaiting_human")
            : t(action.status);
  return (
    <article className="delivery-card">
      <div className="task-heading">
        <div>
          <SmallLabel>{t("proposalBundle")}</SmallLabel>
          <code className="record-id">{action.id}</code>
        </div>
        <span className={`badge ${statusTone(action.status)}`}>{label}</span>
      </div>
      <InspectJson title={t("deliveryPacket")} value={action.packet} />
      <div className="authority-reference">
        <SmallLabel>{t("actionHash")}</SmallLabel>
        <code>{action.action_hash}</code>
      </div>
      {action.status === "awaiting_human" && (
        <section className="decision-box">
          <h4>{t("humanDecision")}</h4>
          {humanEnabled ? (
            <MutationForm
              key={action.action_hash}
              t={t}
              submit={t("recordDecision")}
              successMessage={false}
              fields={[
                {
                  name: "outcome",
                  label: t("outcome"),
                  defaultValue: "",
                  options: [
                    { value: "", label: t("chooseOutcome") },
                    { value: "accept", label: t("approveLocalBundle") },
                    { value: "decline", label: t("decline") },
                    { value: "cancel", label: t("cancelDelivery") },
                  ],
                },
                { name: "actor", label: t("actor") },
                { name: "rationale", label: t("rationale"), textarea: true },
              ]}
              onSubmit={async (data) => {
                await api(`/actions/${segment(action.id)}/decision`, {
                  ...Object.fromEntries(data),
                  action_hash: action.action_hash,
                });
                await onSaved(t("decisionSaved"));
              }}
            />
          ) : (
            <>
              <p>{t("approvalUnavailable")}</p>
              <pre className="cli-instruction">{`research-hub action decide ${action.id} --root <workspace> --outcome accept --actor <name> --rationale <reason>`}</pre>
              <button className="button secondary" disabled>
                {t("recordDecision")}
              </button>
            </>
          )}
        </section>
      )}
      <div className="button-row">
        {action.status === "approved" && (
          <button
            className="button primary"
            disabled={busy}
            onClick={() => void operate("execute")}
          >
            {t("createLocalBundle")}
          </button>
        )}
        {["pending_external_action", "completed"].includes(action.status) && (
          <button
            className="button secondary"
            disabled={busy}
            onClick={() => void operate("reconcile")}
          >
            {t("inspectDeliveryReceipt")}
          </button>
        )}
      </div>
      {error !== null && <ErrorMessage error={error} t={t} />}
      {action.receipt && (
        <section className="delivery-receipt">
          <h4>{t("deliveryReceipt")}</h4>
          <p className="muted small">{t("localReceiptNote")}</p>
          <dl className="metadata">
            <dt>{t("filePath")}</dt>
            <dd>
              <code>{action.receipt.path}</code>
            </dd>
            <dt>{t("fingerprint")}</dt>
            <dd>
              <code>{action.receipt.sha256}</code>
            </dd>
            <dt>{t("receiptVerifiedAt")}</dt>
            <dd>{action.receipt.verified_at}</dd>
          </dl>
        </section>
      )}
    </article>
  );
}
