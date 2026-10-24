import type { RevisionStatus, Task } from "./types";

/** Last received server assessment, not a live file check or human approval. */
export function taskFreshnessStatus(task: Task): RevisionStatus {
  const value = task.freshness;
  if (!value || typeof value !== "object" || Array.isArray(value))
    return "unknown";
  if (value.status === "stale") return "stale";
  if (
    value.status !== "current" ||
    task.acceptance_current === false ||
    !Array.isArray(value.reasons) ||
    value.reasons.length > 0 ||
    !Array.isArray(value.input_references) ||
    !Array.isArray(value.output_references)
  )
    return "unknown";
  if (task.result && value.output_references.length === 0) return "unknown";
  const references = [...value.input_references, ...value.output_references];
  if (
    !references.length ||
    references.some(
      (reference) =>
        !reference ||
        typeof reference !== "object" ||
        Array.isArray(reference) ||
        typeof reference.kind !== "string" ||
        typeof reference.ref !== "string" ||
        !reference.kind.trim() ||
        !reference.ref.trim() ||
        !["current", "stale", "unknown"].includes(reference.status),
    )
  )
    return "unknown";
  if (references.some((reference) => reference.status === "stale"))
    return "stale";
  return references.every((reference) => reference.status === "current")
    ? "current"
    : "unknown";
}
