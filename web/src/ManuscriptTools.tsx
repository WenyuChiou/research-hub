import { useState } from "react";
import { api, auditProject, segment, type AuditReport } from "./api";
import {
  ErrorMessage,
  InspectJson,
  MutationForm,
  Panel,
  ReadText,
  SmallLabel,
} from "./components";
import type { Translate } from "./i18n";
import type { ProjectDetail } from "./types";

interface ImpactReport {
  ok: true;
  impacts: { source: string; affected: string[]; reason: string }[];
  stale_tasks: {
    task_id: string;
    status: string;
    reason: string;
    acceptance_current: false;
  }[];
  automatic_semantic_sync: false;
}
export interface ManuscriptToolsProps {
  detail: ProjectDetail;
  t: Translate;
  onSaved: (message: string) => Promise<void>;
}

/** Uses the writing adapter's current state and reports; scientific rules stay there. */
export function ManuscriptTools({ detail, t, onSaved }: ManuscriptToolsProps) {
  const [binding, setBinding] = useState<{
    path: string;
    state: unknown;
  } | null>(null);
  const [audit, setAudit] = useState<AuditReport | null>(null);
  const [impact, setImpact] = useState<ImpactReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  async function inspect(operation: "bind" | "impact") {
    setBusy(true);
    setError(null);
    try {
      if (operation === "bind") {
        const result = await api<{ ok: true; path: string; state: unknown }>(
          `/projects/${segment(detail.project.id)}/bind`,
          {},
        );
        setBinding(result);
        await onSaved(t("manuscriptBound"));
      } else {
        const result = await api<ImpactReport>(
          `/projects/${segment(detail.project.id)}/impact`,
          {},
        );
        setImpact(result);
        await onSaved(t("impactUpdated"));
      }
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Panel title={t("writingChecks")} className="writing-tools">
      <div className="tool-intro">
        <p>{t("writingAuthorityNote")}</p>
        <div className="button-row">
          <button
            className="button secondary"
            disabled={busy}
            onClick={() => void inspect("bind")}
          >
            {t("bindManuscript")}
          </button>
          <button
            className="button secondary"
            disabled={busy}
            onClick={() => void inspect("impact")}
          >
            {t("inspectImpact")}
          </button>
        </div>
        {error !== null && <ErrorMessage error={error} t={t} />}
        {(binding || detail.manuscript) && (
          <div className="authority-reference">
            <SmallLabel>{t("authorityStatePath")}</SmallLabel>
            <code>
              {binding?.path ??
                `.research/projects/${detail.project.id}/manuscript_state.json`}
            </code>
          </div>
        )}
        {(detail.manuscript || binding) && (
          <InspectJson
            title={t("authorityState")}
            value={detail.manuscript ?? binding?.state}
          />
        )}
      </div>
      <MutationForm
        t={t}
        submit={t("runWritingCheck")}
        note={t("auditScopeNote")}
        reset={false}
        successMessage={false}
        disabled={busy}
        fields={[
          {
            name: "operation",
            label: t("writingCheck"),
            options: [
              { value: "state", label: t("checkState") },
              { value: "consistency", label: t("checkConsistency") },
              { value: "prose", label: t("checkProse") },
              { value: "candidate", label: t("checkCandidate") },
              { value: "docx", label: t("checkDocx") },
            ],
          },
          {
            name: "candidate",
            label: t("candidatePath"),
            hint: t("candidatePathHint"),
            required: false,
          },
        ]}
        onSubmit={async (data) => {
          const candidate = String(data.get("candidate") || "").trim();
          const report = await auditProject(detail.project.id, {
            operation: data.get("operation"),
            ...(candidate ? { candidate } : {}),
          });
          setAudit(report);
          await onSaved(t("auditUpdated"));
        }}
      />
      {audit && (
        <section className="audit-report" aria-label={t("auditReport")}>
          <div
            className={`notice ${audit.ok ? "notice-success" : "notice-error"}`}
            role={audit.ok ? "status" : "alert"}
          >
            <strong>
              {audit.ok ? t("auditChecksPassed") : t("auditFindings")}
            </strong>
            <span>{t("semanticNotPerformed")}</span>
          </div>
          <pre>
            {typeof audit.report === "string"
              ? audit.report
              : JSON.stringify(audit.report, null, 2)}
          </pre>
          <dl className="metadata">
            <dt>{t("checkExitCode")}</dt>
            <dd>{audit.exit_code}</dd>
            <dt>{t("adapterFingerprint")}</dt>
            <dd>
              <code>{audit.adapter_sha256}</code>
            </dd>
          </dl>
        </section>
      )}
      {impact && (
        <section className="impact-report" aria-label={t("impactReport")}>
          <h3>{t("impactReport")}</h3>
          <p className="muted small">{t("impactScopeNote")}</p>
          {impact.impacts.length ? (
            impact.impacts.map((entry, index) => (
              <article
                className="impact-entry"
                key={`${entry.source}-${index}`}
              >
                <SmallLabel>{t("source")}</SmallLabel>
                <code>{entry.source}</code>
                <SmallLabel>{t("affectedRecords")}</SmallLabel>
                <ReadText value={entry.affected} />
                <ReadText value={entry.reason} />
              </article>
            ))
          ) : (
            <p className="small">{t("noImpacts")}</p>
          )}
          <h4>{t("staleAcceptance")}</h4>
          {impact.stale_tasks.length ? (
            impact.stale_tasks.map((task) => (
              <article className="impact-entry" key={task.task_id}>
                <code>{task.task_id}</code>
                <span className="badge warn">{t("acceptanceStale")}</span>
                <ReadText value={task.reason} />
              </article>
            ))
          ) : (
            <p className="small">{t("noStaleTasks")}</p>
          )}
          <InspectJson title={t("inspect")} value={impact} />
        </section>
      )}
    </Panel>
  );
}
