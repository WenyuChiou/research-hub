import { expect, it } from "vitest";
import { linkedSourceArtifact, sourceArtifactLabels } from "./sourceArtifact";
import { translator } from "./i18n";
const t = translator("en");
const artifact = {
  id: "file-a",
  path: "hub-sources/opaque/copy.txt",
  project_id: "river",
  source_record_id: "source-a",
  origin: "hub-text-intake",
  role: "evidence",
  sha256: "a".repeat(64),
  current: true,
  registered_at: "2026-10-24T00:00:00Z",
};
const record = {
  id: "source-a",
  kind: "source",
  data: {
    title: "Synthetic paper",
    reading_scope: "abstract",
    intake: { version: 1, artifact_id: artifact.id, sha256: artifact.sha256 },
  },
};
it("labels exact saved source using declared scope and local date rather than publication date", () => {
  const label = sourceArtifactLabels([record], [artifact], "river", t)[
    artifact.id
  ];
  expect(label).toContain("Synthetic paper");
  expect(label).toContain(t("intakeScopeAbstract"));
  expect(label).toContain("Locally saved 2026-10-24T00:00:00Z");
  expect(label).toContain(artifact.path);
  expect(label).not.toMatch(/published/i);
});
it.each([
  { id: "other" },
  { sha256: "b".repeat(64) },
  { project_id: "other" },
  { source_record_id: "other" },
  { origin: "other" },
])("rejects mismatched exact join %j", (change) => {
  expect(
    linkedSourceArtifact(record, [{ ...artifact, ...change }], "river"),
  ).toBeUndefined();
  expect(
    sourceArtifactLabels([record], [{ ...artifact, ...change }], "river", t),
  ).toEqual({});
});
it("duplicate titles never join; invalid dates never become publication guesses; stale remains stale", () => {
  expect(
    sourceArtifactLabels([{ ...record, id: "other" }], [artifact], "river", t),
  ).toEqual({});
  expect(
    sourceArtifactLabels(
      [
        {
          ...record,
          data: {
            ...record.data,
            recorded_at: "invalid",
            published_at: "2020-01-01",
          },
        },
      ],
      [artifact],
      "river",
      t,
    )[artifact.id],
  ).not.toContain("Locally saved");
  expect(
    linkedSourceArtifact(record, [{ ...artifact, current: false }], "river")
      ?.current,
  ).toBe(false);
});
