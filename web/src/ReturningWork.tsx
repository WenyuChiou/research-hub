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
      className="returning-panel"
    >
      <div className="returning-header-box">
        <p className="returning-scope-line">
          {t("returnScope")} <strong>{detail.project.title}</strong>
        </p>
        <p className="small muted returning-subnote">{t("returnNotResume")}</p>
      </div>

      {recent.length ? (
        <div className="returning-section">
          <div className="returning-kpi-row">
            <span className="returning-kpi-pill">
              {t("returnPending")}: <strong>{pending}</strong>
            </span>
            <span aria-hidden="true" className="muted">·</span>
            <span className="returning-kpi-pill">
              {t("returnAccepted")}: <strong>{accepted}</strong>
            </span>
          </div>
          <p className="small muted returning-subnote">{t("returnAcceptanceNote")}</p>
          <div className="returning-list">
            {recent.map((task) => (
              <article key={task.id} className="returning-task-card">
                <div className="returning-task-main">
                  <div className="record-title">
                    <strong>{t(operationLabel(task.operation))}</strong>
                    <StatusBadge status={task.status} t={t} />
                  </div>
                  <div className="returning-task-meta">
                    <code className="task-id-chip">{task.id}</code>
                    <span className="small muted">
                      {t("returnTaskUpdated")}:{" "}
                      {Number.isFinite(savedTime(task)) ? (
                        <time dateTime={task.updated_at}>{task.updated_at}</time>
                      ) : (
                        t("returnUnknown")
                      )}
                    </span>
                  </div>
                </div>
                <button
                  type="button"
                  className="button secondary small returning-open-btn"
                  aria-label={`${t("returnOpenTask")} ${task.id}`}
                  onClick={() => navigate("review", `review-task-${task.id}`)}
                >
                  <span>{t("returnOpenTask")}</span>
                  <span aria-hidden="true">→</span>
                </button>
              </article>
            ))}
          </div>
          <p className="small muted returning-subnote">{t("returnBoundedTasks")}</p>
        </div>
      ) : (
        <EmptyState compact>
          <p>{t("returnEmpty")}</p>
          <button
            className="button secondary small"
            onClick={() => navigate("literature")}
          >
            {t("viewLiterature")}
          </button>
        </EmptyState>
      )}

      <div className="returning-bundles-section">
        <div className="returning-bundles-header">
          <h3>{t("returnLocalBundles")}</h3>
          {actions.length > 0 && (
            <button
              type="button"
              className="button secondary small"
              onClick={() => navigate("review", "review-local-delivery")}
            >
              {t("returnInspectBundles")}
            </button>
          )}
        </div>
        <p className="small muted returning-subnote">{t("returnDeliveryScope")}</p>
        {actions.length ? (
          <>
            <div className="returning-list">
              {actions.slice(0, 5).map((action) => (
                <article key={action.id} className="returning-task-card returning-bundle-card">
                  <div className="returning-task-main">
                    <div className="record-title">
                      <strong>{localActionLabel(action, t)}</strong>
                      <code className="task-id-chip">{action.id}</code>
                    </div>
                    {action.receipt ? (
                      <>
                        <p className="file-path">{action.receipt.path}</p>
                        <p className="small muted returning-subnote">
                          {t("receiptVerifiedAt")}:{" "}
                          <time dateTime={action.receipt.verified_at}>
                            {action.receipt.verified_at}
                          </time>
                        </p>
                        <p className="small muted returning-subnote">{t("returnReceiptHistory")}</p>
                      </>
                    ) : (
                      <p className="small muted returning-subnote">{t("returnNoReceipt")}</p>
                    )}
                  </div>
                </article>
              ))}
            </div>
            <p className="small muted returning-subnote">{t("returnBoundedBundles")}</p>
          </>
        ) : (
          <p className="small muted returning-empty-bundles">{t("returnNoBundles")}</p>
        )}
      </div>
    </Panel>
  );
}
