import { useEffect, useState } from "react";
import { api, segment } from "./api";
import { ErrorMessage, Panel, SourceLink } from "./components";
import type { Translate } from "./i18n";
import type { Artifact } from "./types";

export interface DiscoveryView {
  ok: true;
  artifact: { id: string; sha256: string; registered_at?: string };
  report: {
    binding: string;
    material_reference_count: number;
    material_bindings: { kind: string; id: string; status: string }[];
    unbound_source_material: string[];
    unknown_source_versions: string[];
    execution_verified: false;
    semantic_assessment: string;
  };
  discovery: {
    format: string;
    project_id: string;
    run_id: string;
    brief: string;
    needs: { id: string; text: string; status: string; families: string[] }[];
    completion: { status: string; reason: string; residual_need_ids: string[] };
    sources: {
      id: string;
      title: string;
      locator: string;
      relevance: string;
      version: string | null;
      access: string;
      reading_level: string;
      need_ids: string[];
    }[];
    attempts: {
      id: string;
      kind: string;
      input: string;
      status: string;
      outcome: string;
      tool: string | null;
      result_count: number | null;
    }[];
  };
}

export function discoveryRoute() {
  const [page, query = ""] = window.location.hash.slice(1).split("?", 2);
  const params = new URLSearchParams(query);
  const project = params.get("project");
  const artifact = params.get("discovery");
  const requested =
    page === "literature" && (params.has("project") || params.has("discovery"));
  const valid =
    requested &&
    params.getAll("project").length === 1 &&
    params.getAll("discovery").length === 1 &&
    !!project &&
    !!artifact &&
    project.length <= 256 &&
    artifact.length <= 256;
  return {
    requested,
    valid,
    project: valid ? project : null,
    artifact: valid ? artifact : null,
  };
}
export const discoveryLink = (project: string, artifact: string) =>
  "#literature?" +
  new URLSearchParams({ project, discovery: artifact }).toString();

export function DiscoveryPanel({
  projectId,
  artifacts,
  selected,
  invalid,
  active,
  t,
}: {
  projectId: string;
  artifacts: Artifact[];
  selected: string | null;
  invalid: boolean;
  active: boolean;
  t: Translate;
}) {
  const [loaded, setLoaded] = useState<{
    project: string;
    artifact: string;
    value: DiscoveryView;
  } | null>(null);
  const [failure, setFailure] = useState<unknown>(null);
  const [refresh, setRefresh] = useState(0);
  const [limit, setLimit] = useState(50);
  useEffect(() => setLimit(50), [projectId, selected]);
  const choices = artifacts.filter(
    (a) => a.role === "evidence" && a.path?.startsWith("hub-discovery/"),
  );
  useEffect(() => {
    setLoaded(null);
    setFailure(null);
    if (!active || !selected || invalid) return;
    const controller = new AbortController();
    api<DiscoveryView>(
      `/projects/${segment(projectId)}/artifacts/${segment(selected)}/discovery`,
      undefined,
      controller.signal,
    )
      .then((value) => {
        if (controller.signal.aborted) return;
        if (value.discovery.format !== "research-discovery-observations/1.0")
          throw new Error("Unsupported saved discovery format.");
        if (
          value.discovery.project_id !== projectId ||
          value.artifact.id !== selected
        )
          throw new Error(
            "Discovery response belongs to a different selected project or artifact.",
          );
        setLoaded({ project: projectId, artifact: selected, value });
      })
      .catch((error) => {
        if (!controller.signal.aborted) setFailure(error);
      });
    return () => controller.abort();
  }, [projectId, selected, invalid, active, refresh]);
  const result =
    loaded?.project === projectId && loaded.artifact === selected
      ? loaded.value
      : null;
  return (
    <Panel title={t("discoveryTitle")}>
      <div className="discovery-body">
        <p className="small muted">{t("discoveryPlatform")}</p>
        {choices.length ? (
          <ul>
            {choices.map((a) => (
              <li key={a.id}>
                <a href={discoveryLink(projectId, a.id)}>
                  {t("discoveryOpen")} · {a.registered_at ?? a.id}
                </a>
                {!a.current && <span> — {t("changed")}</span>}
              </li>
            ))}
          </ul>
        ) : (
          <p>{t("discoveryEmpty")}</p>
        )}
        <details>
          <summary>{t("discoveryHelp")}</summary>
          <p>{t("discoveryIntro")}</p>
        </details>
        {invalid && <p role="alert">{t("discoveryInvalidLink")}</p>}
        {failure != null && (
          <>
            <ErrorMessage error={failure} t={t} />
            <button
              className="button secondary"
              onClick={() => setRefresh((n) => n + 1)}
            >
              {t("discoveryRefresh")}
            </button>
          </>
        )}
        {selected && !invalid && !result && !failure && (
          <p role="status">{t("loading")}</p>
        )}
        {result && (
          <section aria-label={t("discoveryResult")}>
            <h3>{result.discovery.brief}</h3>
            <p>
              {t("discoverySnapshot")}: <code>{result.artifact.sha256}</code>
            </p>
            <p role="status">
              {t("discoveryBinding")}: {result.report.binding}
            </p>
            <p>{t("discoveryLimits")}</p>
            <p>
              {t("discoveryReferenceCount")}:{" "}
              {result.report.material_reference_count}
            </p>
            <p>
              {t("discoveryUnbound")}:{" "}
              {result.report.unbound_source_material.join(", ") ||
                t("discoveryNone")}
            </p>
            <h4>{t("discoveryNeeds")}</h4>
            <ul>
              {result.discovery.needs.slice(0, limit).map((n) => (
                <li key={n.id}>
                  <strong>{n.text}</strong> — {n.status} ·{" "}
                  {n.families.join(", ")}
                </li>
              ))}
            </ul>
            <p>
              {result.discovery.completion.status}:{" "}
              {result.discovery.completion.reason}
            </p>
            <p>
              {t("discoveryResidual")}:{" "}
              {result.discovery.completion.residual_need_ids.join(", ") ||
                t("discoveryNone")}
            </p>
            <h4>{t("sources")}</h4>
            {result.discovery.sources.slice(0, limit).map((source) => (
              <article className="discovery-source" key={source.id}>
                <h5>{source.title}</h5>
                <div className="discovery-source-meta">
                  <code>{source.id}</code>
                  <SourceLink locator={source.locator} />
                </div>
                <p>{source.relevance}</p>
                <p>
                  {t("discoveryVersion")}:{" "}
                  {source.version ?? t("discoveryUnknown")} · {source.access}
                </p>
                <p>
                  {t("discoveryReading")}: {source.reading_level}
                </p>
                <p>
                  {t("discoverySourceBytes")}:{" "}
                  {result.report.material_bindings.find(
                    (b) => b.kind === "source" && b.id === source.id,
                  )?.status ?? t("discoveryUnboundShort")}
                </p>
              </article>
            ))}
            <details>
              <summary>{t("discoveryAttempts")}</summary>
              {result.discovery.attempts.slice(0, limit).map((a) => (
                <article key={a.id}>
                  <h5>
                    {a.id} · {a.kind}
                  </h5>
                  <p>{a.input}</p>
                  <p>
                    {a.tool ?? t("discoveryUnknown")} · {a.status} · {a.outcome}
                  </p>
                  <p>
                    {t("discoveryAttemptBytes")}:{" "}
                    {result.report.material_bindings.find(
                      (b) => b.kind === "attempt" && b.id === a.id,
                    )?.status ?? t("discoveryUnboundShort")}
                  </p>
                  <p>
                    {t("discoveryResultCount")}:{" "}
                    {a.result_count ?? t("discoveryUnknown")}
                  </p>
                </article>
              ))}
            </details>
            {Math.max(
              result.discovery.needs.length,
              result.discovery.sources.length,
              result.discovery.attempts.length,
            ) > limit && (
              <button
                className="button secondary"
                onClick={() => setLimit((n) => n + 50)}
              >
                {t("discoveryMore")}
              </button>
            )}
            <button
              className="button secondary"
              onClick={() => setRefresh((n) => n + 1)}
            >
              {t("discoveryRefresh")}
            </button>
          </section>
        )}
      </div>
    </Panel>
  );
}
