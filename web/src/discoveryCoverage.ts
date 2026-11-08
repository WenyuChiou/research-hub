/** Read-only joins of supplied observations, not a research-coverage verdict. */
interface NeedLinked {
  id: string;
  need_ids?: unknown;
}

interface Attempt extends NeedLinked {
  status: string;
  outcome: string;
}

function needLinks(
  record: NeedLinked,
  knownNeedIds: ReadonlySet<string>,
): { ids: readonly string[]; hasIssues: boolean } {
  const ids = record.need_ids;
  // Retain valid exact links even in a mixed invalid response. The original
  // record stays intact; an issue is not a scientific or whole-record verdict.
  if (!Array.isArray(ids) || ids.length === 0)
    return { ids: [], hasIssues: true };
  const exactIds = ids.filter(
    (id): id is string => typeof id === "string" && /\S/.test(id),
  );
  const linkedIds = exactIds.filter((id) => knownNeedIds.has(id));
  return {
    ids: linkedIds,
    hasIssues: linkedIds.length !== ids.length || new Set(exactIds).size !== ids.length,
  };
}

export function observationsForNeed<A extends Attempt, S extends NeedLinked>(
  needId: string,
  attempts: readonly A[],
  sources: readonly S[],
  knownNeedIds: ReadonlySet<string>,
) {
  const attemptLinks = attempts.map((record) => ({ record, ...needLinks(record, knownNeedIds) }));
  const sourceLinks = sources.map((record) => ({ record, ...needLinks(record, knownNeedIds) }));
  const linkedAttempts = attemptLinks.filter((a) => a.ids.includes(needId)).map((a) => a.record);
  return {
    attempts: linkedAttempts,
    sources: sourceLinks.filter((s) => s.ids.includes(needId)).map((s) => s.record),
    // Snapshot-wide records with any bad association, including partly linked
    // records. Do not call all of them unassigned or drop their valid links.
    attemptsWithLinkIssues: attemptLinks.filter((a) => a.hasIssues).map((a) => a.record),
    sourcesWithLinkIssues: sourceLinks.filter((s) => s.hasIssues).map((s) => s.record),
    // A retained failure may have been resolved by other evidence. This is an
    // inspection count, never an unresolved-need or completion decision.
    attemptsToInspect: linkedAttempts.filter(
      (a) => a.status !== "observed" || !["success", "empty"].includes(a.outcome),
    ),
    // v1 links attempts to needs, not to a particular search family. Never
    // infer a family from a query, source title, attempt ID, or array order.
    familyLinkage: "unknown" as const,
  };
}
