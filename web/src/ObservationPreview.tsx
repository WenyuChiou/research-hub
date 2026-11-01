import { useEffect, useState } from "react";
import { api, segment } from "./api";
import type { TextPreview } from "./AbstractDraft";
import type { Translate } from "./i18n";
import { SourceObservations } from "./ObservationHistory";
import { readableArtifact, previewMatchesArtifact } from "./sourceStorage";
import type { Artifact, ResearchRecord } from "./types";

export interface ObservationReadScope { projectId: string; artifacts: Artifact[]; active: boolean }

/** Exact registered references only; this function does not probe caller paths. */
export function observationArtifacts(record: ResearchRecord, scope?: ObservationReadScope): Artifact[] {
  if (!scope?.active || !scope.projectId || !record.id || record.kind !== "source" || typeof record.data.id !== "string" || !record.data.id.trim()) return [];
  const rows = Array.isArray(record.data.source_records) ? record.data.source_records : [];
  const ids = rows.map(o => o && typeof o === "object" ? o.observation_id : undefined);
  const selected: Artifact[] = [];
  for (const obs of rows) {
    if (!obs || typeof obs !== "object" || typeof obs.observation_id !== "string" || !obs.observation_id.trim() ||
      ids.filter(id => id === obs.observation_id).length !== 1 || typeof obs.work_id !== "string" || !obs.work_id.trim() ||
      obs.evidence_level !== "generated-summary" || obs.status !== "available" ||
      (obs.source_id !== record.data.id && obs.source_id !== record.id) || typeof obs.text_path !== "string" ||
      typeof obs.text_sha256 !== "string" || !/^[a-f0-9]{64}$/.test(obs.text_sha256)) continue;
    const matches = scope.artifacts.filter(a => a.project_id === scope.projectId && a.source_record_id === record.id &&
      a.path === obs.text_path && a.sha256 === obs.text_sha256 && readableArtifact(a, scope.projectId, record.id));
    if (matches.length === 1 && !selected.some(a => a.id === matches[0].id)) selected.push(matches[0]);
  }
  return selected;
}

export function ObservationPreview({ record, scope, t }: {record: ResearchRecord; scope?: ObservationReadScope; t: Translate}) {
  const artifacts = observationArtifacts(record, scope);
  const key = JSON.stringify([scope?.active, scope?.projectId, record.id, artifacts.map(a => [a.id, a.sha256, a.path, a.project_id, a.source_record_id, a.current])]);
  const [state, setState] = useState<{key: string; previews: TextPreview[]; status: "loading" | "ready" | "error"}>();
  useEffect(() => {
    if (!scope?.active || !artifacts.length) return;
    const controller = new AbortController();
    setState({key, previews: [], status: "loading"});
    void (async () => {
      const previews: TextPreview[] = [];
      let failed = false;
      for (const a of artifacts) {
        if (controller.signal.aborted) return;
        try {
          const result = await api<{ok:true;preview:TextPreview}>(`/projects/${segment(scope.projectId)}/artifacts/${segment(a.id)}/text`, undefined, controller.signal);
          if (!previewMatchesArtifact(result.preview, a)) throw new Error("Unbound observation preview");
          previews.push(result.preview);
        } catch { failed = true; }
      }
      if (!controller.signal.aborted) setState({key, previews, status: failed ? "error" : "ready"});
    })();
    return () => controller.abort();
    // key contains the exact project/source/artifact identities; no unscoped refresh.
  }, [key]);
  const current = state?.key === key ? state : undefined;
  return <>
    {artifacts.length > 0 && current?.status !== "ready" && <p role="status" className="small muted">{t(current?.status === "error" ? "observationPreviewError" : "observationPreviewLoading")}</p>}
    <SourceObservations record={record} t={t} context={scope ? {projectId:scope.projectId, artifacts:scope.artifacts,
      previews:scope.active && current && current.status !== "loading" ? current.previews : []} : undefined} />
  </>;
}
