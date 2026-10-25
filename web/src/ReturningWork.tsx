import { EmptyState, Panel, StatusBadge } from "./components";
import { operationLabel, statusLabel, type Translate } from "./i18n";
import type { DeliveryAction, Page, ProjectDetail, Task } from "./types";

const savedTime = (task: Task) => {
  const timestamp = task.updated_at ? Date.parse(task.updated_at) : NaN;
  return Number.isFinite(timestamp) ? timestamp : -Infinity;
};

/** Project-scoped saved facts only: no provider checks, replay or eligibility gate. */
export function recentSavedTasks(tasks: Task[]): Task[] {
  return [...tasks].sort((a, b) => savedTime(b) - savedTime(a)).slice(0, 5);
}

function localActionLabel(action: DeliveryAction, t: Translate): string {
  switch (action.status) {
    case "completed":
      return t("deliveryComplete");
    case "approved":
      return t("deliveryApproved");
    case "pending_external_action":
      return t("deliveryPending");
    case "awaiting_human":
      return t("returnBundleReview");
    case "declined":
      return statusLabel("declined", t);
    case "cancelled":
      return statusLabel("cancelled", t);
    default:
      return t("returnUnknown");
  }
}

export function ReturningWork({
  detail,
  t,
  navigate,
}: {
  detail: ProjectDetail;
  t: Translate;
  navigate: (page: Page, focusId?: string) => void;
}) {
  const recent = recentSavedTasks(detail.tasks);
  const pending = detail.tasks.filter((task) =>
    [
      "ready",
      "awaiting_agent",
      "awaiting_human",
      "running",
      "blocked",
      "failed",
    ].includes(task.status),
  ).length;
  const accepted = detail.tasks.filter(
    (task) => task.status === "completed",
  ).length;
  const actions = detail.actions ?? [];
  return (
    <Panel
      title={t("recentActivity")}
      meta={<a href="#review">{t("viewReview")}</a>}
    >
      <p className="tool-intro">
        {t("returnScope")} <strong>{detail.project.title}</strong>
      </p>
      <p className="small muted">{t("returnNotResume")}</p>
      {recent.length ? (
        <>
          <p>
            {t("returnPending")}: {pending} · {t("returnAccepted")}: {accepted}
          </p>
          <p className="small muted">{t("returnAcceptanceNote")}</p>
          <div className="returning-list">
            {recent.map((task) => (
              <article key={task.id} className="research-record">
                <div className="record-title">
                  <strong>{t(operationLabel(task.operation))}</strong>
                  <StatusBadge status={task.status} t={t} />
                </div>
                <code>{task.id}</code>
                <p className="small muted">
                  {t("returnTaskUpdated")}:{" "}
                  {Number.isFinite(savedTime(task)) ? (
                    <time dateTime={task.updated_at}>{task.updated_at}</time>
                  ) : (
                    t("returnUnknown")
                  )}
                </p>
                <button
                  className="button secondary"
                  onClick={() => navigate("review", `review-task-${task.id}`)}
                >
                  {t("returnOpenTask")} {task.id}
                </button>
              </article>
            ))}
          </div>
          <p className="small muted">{t("returnBoundedTasks")}</p>
        </>
      ) : (
        <EmptyState>
          <p>{t("returnEmpty")}</p>
          <button
            className="button secondary"
            onClick={() => navigate("literature")}
          >
            {t("viewLiterature")}
          </button>
        </EmptyState>
      )}
      <h3>{t("returnLocalBundles")}</h3>
      <p className="small muted">{t("returnDeliveryScope")}</p>
      {actions.length ? (
        <div className="returning-list">
          {actions.slice(0, 5).map((action) => (
            <article key={action.id} className="research-record">
              <strong>{localActionLabel(action, t)}</strong>
              <p>
                <code>{action.id}</code>
              </p>
              {action.receipt ? (
                <>
                  <p className="file-path">{action.receipt.path}</p>
                  <p className="small muted">
                    {t("receiptVerifiedAt")}:{" "}
                    <time dateTime={action.receipt.verified_at}>
                      {action.receipt.verified_at}
                    </time>
                  </p>
                  <p className="small muted">{t("returnReceiptHistory")}</p>
                </>
              ) : (
                <p className="small muted">{t("returnNoReceipt")}</p>
              )}
            </article>
          ))}
        </div>
      ) : (
        <p>{t("returnNoBundles")}</p>
      )}
      {actions.length > 0 && (
        <>
          <p className="small muted">{t("returnBoundedBundles")}</p>
          <button
            className="button secondary"
            onClick={() => navigate("review", "review-local-delivery")}
          >
            {t("returnInspectBundles")}
          </button>
        </>
      )}
    </Panel>
  );
}
