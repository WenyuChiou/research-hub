import type { Artifact, ResearchRecord } from "./types";
import type { Translate } from "./i18n";
/** Exact existing intake join; never infer identity from a similar title. */
export function linkedSourceArtifact(
  record: ResearchRecord,
  artifacts: Artifact[],
  projectId: string,
) {
  if (record.kind !== "source") return undefined;
  const binding = record.data.intake as Record<string, unknown> | undefined;
  return artifacts.find(
    (a) =>
      binding?.version === 1 &&
      a.id === binding.artifact_id &&
      a.sha256 === binding.sha256 &&
      a.source_record_id === record.id &&
      a.project_id === projectId &&
      a.origin === "hub-text-intake",
  );
}
export function sourceArtifactLabels(
  records: ResearchRecord[],
  artifacts: Artifact[],
  projectId: string,
  t: Translate,
): Record<string, string> {
  const labels: Record<string, string> = Object.create(null);
  for (const record of records) {
    const artifact = linkedSourceArtifact(record, artifacts, projectId);
    if (
      !artifact ||
      typeof record.data.title !== "string" ||
      !record.data.title.trim()
    )
      continue;
    const rawDate = record.data.recorded_at ?? artifact.registered_at;
    const date =
      typeof rawDate === "string" &&
      /^\d{4}-\d{2}-\d{2}T/.test(rawDate) &&
      Number.isFinite(Date.parse(rawDate))
        ? rawDate
        : undefined;
    const scope = t(
      record.data.reading_scope === "abstract"
        ? "intakeScopeAbstract"
        : "intakeScopeUnknown",
    );
    labels[artifact.id] =
      `${record.data.title} — ${scope}${date ? ` — ${t("sourceLocallySaved")} ${date}` : ""} — ${artifact.path}`;
  }
  return labels;
}
