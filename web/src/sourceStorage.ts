import type { Artifact } from "./types";
import type { TextPreview } from "./AbstractDraft";

/** Unknown descriptors never fall back to a filesystem interpretation. */
export function isBlobArtifact(a: Artifact): boolean {
  const s = a.storage;
  return (
    !!s &&
    typeof s === "object" &&
    !Array.isArray(s) &&
    Object.keys(s).sort().join(",") === "blob_id,kind,version" &&
    s.kind === "workspace_blob" &&
    s.version === 1 &&
    s.blob_id === a.id &&
    !("path" in a) &&
    a.role === "evidence" &&
    typeof a.source_record_id === "string" &&
    !!a.source_record_id &&
    typeof a.project_id === "string" &&
    !!a.project_id &&
    (a.format === "txt" || a.format === "md") &&
    Number.isInteger(a.byte_length) &&
    a.byte_length! > 0 &&
    a.byte_length! <= 40000 &&
    /^[0-9a-f]{64}$/.test(a.sha256)
  );
}
export function readableArtifact(
  a: Artifact,
  project: string,
  source: string,
): boolean {
  if ("storage" in a)
    return (
      isBlobArtifact(a) &&
      a.project_id === project &&
      a.source_record_id === source
    );
  return (
    a.role === "evidence" &&
    typeof a.path === "string" &&
    /\.(md|txt)$/i.test(a.path) &&
    (!a.project_id || a.project_id === project)
  );
}
export function artifactReference(a: Artifact): string {
  if ("storage" in a)
    return isBlobArtifact(a)
      ? `hub-source:${a.source_record_id}`
      : "Unsupported saved-text storage";
  return typeof a.path === "string" ? a.path : "Unavailable source reference";
}
export function previewMatchesArtifact(p: TextPreview, a: Artifact): boolean {
  if (
    !p ||
    p.artifact_id !== a.id ||
    p.sha256 !== a.sha256 ||
    p.truncated !== false ||
    typeof p.text !== "string"
  )
    return false;
  if (!("storage" in a))
    return !("storage" in p) && p.path === a.path && typeof a.path === "string";
  if (
    !isBlobArtifact(a) ||
    "path" in p ||
    p.reference !== artifactReference(a) ||
    p.format !== a.format ||
    !p.storage ||
    JSON.stringify(Object.keys(p.storage).sort()) !==
      JSON.stringify(["blob_id", "kind", "version"]) ||
    p.storage.kind !== "workspace_blob" ||
    p.storage.version !== 1 ||
    p.storage.blob_id !== a.id
  )
    return false;
  return (
    p.bytes_read === a.byte_length &&
    p.bytes_read === new TextEncoder().encode(p.text).length &&
    p.codepoint_length === Array.from(p.text).length
  );
}
