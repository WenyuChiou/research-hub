import { expect, it } from "vitest";
import { observationsForNeed } from "./discoveryCoverage";

const knownNeedIds = new Set(["n", "n2", "n-other"]);

const attempt = (id: string, status: string, outcome: string, need_ids = ["n"]) =>
  ({ id, status, outcome, need_ids, result_count: null as number | null });

it("retains failed contrary observations beside successful closest observations", () => {
  const attempts = [attempt("closest", "observed", "success"), attempt("contrary", "observed", "timeout")];
  const result = observationsForNeed("n", attempts, [], knownNeedIds);
  expect(result.attempts).toEqual(attempts);
  expect(result.attemptsToInspect.map((a) => a.id)).toEqual(["contrary"]);
  expect(result.familyLinkage).toBe("unknown");
});

it("does not fabricate an omitted family or source from one successful attempt", () => {
  const result = observationsForNeed("n", [attempt("closest", "observed", "success")], [], knownNeedIds);
  expect(result.sources).toEqual([]);
  expect(result.familyLinkage).toBe("unknown");
  expect(result).not.toHaveProperty("covered");
  expect(result).not.toHaveProperty("completion");
});

it("preserves observed empty zero separately from an unknown count", () => {
  const empty = { ...attempt("empty", "observed", "empty"), result_count: 0 };
  const unknown = attempt("unknown", "observed", "unknown");
  const result = observationsForNeed("n", [empty, unknown], [], knownNeedIds);
  expect(result.attempts.map((a) => a.result_count)).toEqual([0, null]);
  expect(result.attemptsToInspect).toEqual([unknown]);
  expect(result.familyLinkage).toBe("unknown");
});

it.each(["planned", "declared", "unavailable"])("keeps %s records inspectable without promoting execution", (status) => {
  const value = attempt("a", status, "unknown");
  expect(observationsForNeed("n", [value], [], knownNeedIds).attemptsToInspect).toEqual([value]);
});

it("keeps partial, denied and error outcomes distinct", () => {
  const values = ["partial", "denied", "error"].map((outcome) => attempt(outcome, "observed", outcome));
  expect(observationsForNeed("n", values, [], knownNeedIds).attemptsToInspect).toEqual(values);
});

it("uses exact need IDs and retains overlapping source membership and versions", () => {
  const values = [attempt("a", "observed", "success", ["n", "n2"]), attempt("other", "observed", "success", ["n-other"])];
  const sources = [{ id: "s-v1", need_ids: ["n", "n2"], version: "v1" }, { id: "s-unknown", need_ids: ["n"], version: null }];
  expect(observationsForNeed("n", values, sources, knownNeedIds).attempts.map((a) => a.id)).toEqual(["a"]);
  expect(observationsForNeed("n", values, sources, knownNeedIds).sources).toEqual(sources);
  expect(observationsForNeed("n2", values, sources, knownNeedIds).sources).toEqual([sources[0]]);
  expect(observationsForNeed("N", values, sources, knownNeedIds).attempts).toEqual([]);
});

it("does not erase a failure when a later attempt succeeds or mutate supplied data", () => {
  const attempts = Object.freeze([Object.freeze(attempt("earlier", "observed", "timeout")), Object.freeze(attempt("alternate", "observed", "success"))]);
  const source = Object.freeze({ id: "s", need_ids: Object.freeze(["n"]), reading_level: "abstract", version: null });
  const sources = Object.freeze([source]);
  const before = JSON.stringify({ attempts, sources });
  const result = observationsForNeed("n", attempts, sources, knownNeedIds);
  expect(result.attemptsToInspect.map((a) => a.id)).toEqual(["earlier"]);
  expect(result.sources[0]).toBe(source);
  expect(JSON.stringify({ attempts, sources })).toBe(before);
});

it("retains valid portions of malformed links while exposing every anomalous record", () => {
  const missing = { id: "missing", status: "observed", outcome: "success" };
  const invalid = [undefined, null, "n", [], ["n", 3], ["n", "n"], [" "]];
  const attempts = [missing, ...invalid.map((need_ids, i) => ({ ...missing, id: `invalid-${i}`, need_ids }))];
  const sources = invalid.map((need_ids, i) => ({ id: `s-${i}`, need_ids }));
  const result = observationsForNeed("n", attempts, sources, knownNeedIds);
  expect(result.attempts.map((a) => a.id)).toEqual(["invalid-4", "invalid-5"]);
  expect(result.sources.map((s) => s.id)).toEqual(["s-4", "s-5"]);
  expect(result.attemptsWithLinkIssues).toEqual(attempts);
  expect(result.sourcesWithLinkIssues).toEqual(sources);
  expect(result.attemptsWithLinkIssues.length).toBe(8);
  expect(result.sourcesWithLinkIssues.length).toBe(7);
  expect(result.familyLinkage).toBe("unknown");
});

it("does not truncate 52 associated records before the view applies its visible limit", () => {
  const attempts = Array.from({ length: 52 }, (_, i) => attempt(`a-${i}`, "observed", "success"));
  const sources = Array.from({ length: 52 }, (_, i) => ({ id: `s-${i}`, need_ids: ["n"] }));
  const result = observationsForNeed("n", attempts, sources, knownNeedIds);
  expect(result.attempts).toHaveLength(52);
  expect(result.sources).toHaveLength(52);
  expect(result.attemptsWithLinkIssues.length).toBe(0);
  expect(result.sourcesWithLinkIssues.length).toBe(0);
});

it("exposes foreign-only IDs as issues without assigning them to any need", () => {
  const attempts = [attempt("foreign", "observed", "success", ["ghost"])];
  const sources = [{ id: "foreign-source", need_ids: ["ghost"] }];
  for (const needId of ["n", "ghost"]) {
    const result = observationsForNeed(needId, attempts, sources, new Set(["n"]));
    expect(result.attempts).toEqual([]);
    expect(result.sources).toEqual([]);
    expect(result.attemptsWithLinkIssues).toEqual(attempts);
    expect(result.sourcesWithLinkIssues).toEqual(sources);
  }
});

it("retains mixed known and foreign links plus the original anomalous records", () => {
  const mixed = Object.freeze({ ...attempt("mixed", "observed", "timeout"), need_ids: Object.freeze(["n", "ghost"]) });
  const source = Object.freeze({ id: "mixed-source", need_ids: Object.freeze(["n", "ghost"]), version: null });
  const attempts = Object.freeze([mixed]);
  const sources = Object.freeze([source]);
  const before = JSON.stringify({ attempts, sources });
  const result = observationsForNeed("n", attempts, sources, new Set(["n"]));
  expect(result.attempts).toEqual([mixed]);
  expect(result.sources).toEqual([source]);
  expect(result.attemptsToInspect).toEqual([mixed]);
  expect(result.attemptsWithLinkIssues[0]).toBe(mixed);
  expect(result.sourcesWithLinkIssues[0]).toBe(source);
  expect(result.familyLinkage).toBe("unknown");
  expect(observationsForNeed("ghost", attempts, sources, new Set(["n"])).attempts).toEqual([]);
  expect(observationsForNeed("ghost", attempts, sources, new Set(["n"])).sources).toEqual([]);
  expect(JSON.stringify({ attempts, sources })).toBe(before);
});

it("does not flag valid links to another known need as foreign", () => {
  const values = [attempt("other", "observed", "success", ["n2"])];
  const sources = [{ id: "shared", need_ids: ["n", "n2"] }];
  const result = observationsForNeed("n", values, sources, new Set(["n", "n2"]));
  expect(result.attempts).toEqual([]);
  expect(result.sources).toEqual(sources);
  expect(result.attemptsWithLinkIssues).toEqual([]);
  expect(result.sourcesWithLinkIssues).toEqual([]);
  expect(observationsForNeed("n2", values, sources, new Set(["n", "n2"])).attempts).toEqual(values);
});

it("requires actual snapshot membership even when the requested ID appears in a record", () => {
  const values = [attempt("a", "observed", "success")];
  const sources = [{ id: "s", need_ids: ["n"] }];
  const result = observationsForNeed("n", values, sources, new Set());
  expect(result.attempts).toEqual([]);
  expect(result.sources).toEqual([]);
  expect(result.attemptsWithLinkIssues).toEqual(values);
  expect(result.sourcesWithLinkIssues).toEqual(sources);
});
