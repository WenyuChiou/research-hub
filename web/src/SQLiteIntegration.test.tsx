import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import fixture from "./test-fixtures/sqlite-service.json";
import App from "./App";
import {
  AbstractDraftComposer,
  AbstractDraftReview,
  originalRange,
  type TextPreview,
} from "./AbstractDraft";
import {
  artifactReference,
  isBlobArtifact,
  previewMatchesArtifact,
  readableArtifact,
} from "./sourceStorage";
import { intakeSupported, validSavedText } from "./textIntake";
import { sourceArtifactLabels } from "./sourceArtifact";
import { translator } from "./i18n";
import type { Artifact, Task, Workspace } from "./types";
const t = translator("en"),
  saved = fixture.saved,
  project = fixture.project_id;
const key = saved.intake.key,
  namespace = fixture.workspace.capabilities.text_intake.workspace_instance_id;
const prefix = `research-hub:text-intake:v1:${encodeURIComponent(location.origin)}:${namespace}:${encodeURIComponent(project)}:`;
const response = (v: unknown, status = 200) =>
  new Response(JSON.stringify(v), { status });
afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  history.replaceState({}, "", "/");
});
it("accepts actual private-service save/replay/lookup, exact labels and legacy preview", () => {
  for (const v of [saved, fixture.replay, fixture.lookup])
    expect(validSavedText(v, project, key)).toBe(true);
  expect(intakeSupported(fixture.workspace.capabilities.text_intake)).toBe(
    true,
  );
  const labels = sourceArtifactLabels(
    fixture.snapshot.records,
    fixture.snapshot.artifacts,
    project,
    t,
  );
  expect(labels[saved.artifact.id]).toContain(saved.record.data.title);
  expect(labels[saved.artifact.id]).toContain(saved.record.data.recorded_at);
  expect(labels[saved.artifact.id]).toContain(saved.preview.reference);
  expect(labels[saved.artifact.id]).not.toContain("undefined");
  const legacy = fixture.snapshot.artifacts.find(
    (a) => a.id === fixture.legacy_preview.preview.artifact_id,
  )!;
  expect(
    previewMatchesArtifact(
      fixture.legacy_preview.preview as TextPreview,
      legacy,
    ),
  ).toBe(true);
  expect(readableArtifact(legacy, project, saved.record.id)).toBe(true);
});
it.each([
  "unknown-version",
  "extra-field",
  "invented-path",
  "wrong-blob",
  "wrong-project",
  "wrong-source",
  "wrong-hash",
  "wrong-reference",
  "wrong-format",
  "wrong-bytes",
])("rejects %s without guessing a filesystem fallback", (kind) => {
  const value = structuredClone(saved);
  if (kind === "unknown-version") value.artifact.storage.version = 2;
  if (kind === "extra-field")
    Object.assign(value.artifact.storage, { unexpected: true });
  if (kind === "invented-path")
    Object.assign(value.artifact, { path: "fake.txt" });
  if (kind === "wrong-blob") value.artifact.storage.blob_id = "other";
  if (kind === "wrong-project") value.artifact.project_id = "other";
  if (kind === "wrong-source") value.artifact.source_record_id = "other";
  if (kind === "wrong-hash") value.preview.sha256 = "a".repeat(64);
  if (kind === "wrong-reference") value.preview.reference = "hub-source:other";
  if (kind === "wrong-format") value.preview.format = "txt";
  if (kind === "wrong-bytes") value.artifact.byte_length++;
  expect(validSavedText(value, project, key)).toBe(false);
});
it("unknown private capability is disabled and absent storage retains legacy admission", () => {
  const cap = fixture.workspace.capabilities.text_intake;
  expect(
    intakeSupported({
      ...cap,
      storage: { kind: "workspace_blob", version: 2 },
    }),
  ).toBe(false);
  const { storage, experimental, ...legacy } = cap;
  expect(intakeSupported(legacy)).toBe(true);
  expect(
    isBlobArtifact({
      ...saved.artifact,
      storage: { ...saved.artifact.storage, version: 2 },
    }),
  ).toBe(false);
});
it("mixed picker excludes unrelated BLOB and unknown storage; raw range preserves BOM CRLF emoji", async () => {
  const fetch = vi.fn(async () =>
    response({ ok: true, preview: saved.preview }),
  );
  vi.stubGlobal("fetch", fetch);
  const artifacts: Artifact[] = [
    ...fixture.snapshot.artifacts,
    {
      ...saved.artifact,
      id: "bad",
      storage: { ...saved.artifact.storage, version: 9 },
    },
  ];
  render(
    <AbstractDraftComposer
      projectId={project}
      source={saved.record}
      artifacts={artifacts}
      artifactLabels={sourceArtifactLabels(
        fixture.snapshot.records,
        artifacts,
        project,
        t,
      )}
      capability={{ status: "unavailable", message: "No provider" }}
      t={t}
      onPrepared={vi.fn()}
      onCancel={vi.fn()}
    />,
  );
  const picker = screen.getByLabelText(
    t("abstractChooseFile"),
  ) as HTMLSelectElement;
  expect([...picker.options].map((o) => o.value)).toContain(saved.artifact.id);
  expect([...picker.options].map((o) => o.value)).not.toContain(
    fixture.second_saved.artifact.id,
  );
  expect([...picker.options].map((o) => o.value)).not.toContain("bad");
  fireEvent.change(picker, { target: { value: saved.artifact.id } });
  fireEvent.click(screen.getByRole("button", { name: t("abstractReadText") }));
  const box = (await screen.findByLabelText(
    t("abstractText"),
  )) as HTMLTextAreaElement;
  const selected = "Selected 😀 abstract passage.";
  const start = box.value.indexOf(selected),
    end = start + selected.length;
  expect(originalRange(saved.preview.text, start, end)).toEqual(
    fixture.prepare_payload.source_selection && {
      start: fixture.prepare_payload.source_selection.start,
      end: fixture.prepare_payload.source_selection.end,
    },
  );
  expect(box.value).toBe(saved.preview.text.replace(/\r\n/g, "\n"));
  expect(fetch.mock.calls).toHaveLength(1);
});
it.each(["failed", "pending"])(
  "lost save lookup opens exact BLOB while bulk refresh is %s; zero POST/Run",
  async (mode) => {
    const identity = {
      version: 1,
      workspace_instance_id: namespace,
      project_id: project,
      key,
      state: "pending",
    };
    localStorage.setItem(prefix + key, JSON.stringify(identity));
    let reads = 0;
    const empty = {
      ...fixture.before_prepare,
      records: [],
      artifacts: [],
      tasks: [],
    };
    const fetch = vi.fn(
      async (input: RequestInfo | URL, options?: RequestInit) => {
        if (options?.method === "POST") throw Error("No automatic mutation");
        const url = String(input);
        if (url.endsWith("/workspace"))
          return response({
            ...fixture.workspace,
            projects: [fixture.before_prepare.project],
          });
        if (url.includes(`/source-text/${key}`))
          return response(fixture.lookup);
        if (++reads === 1) return response(empty);
        if (mode === "pending") return new Promise<Response>(() => {});
        return response({ ok: false, error: "Synthetic bulk failure" }, 503);
      },
    );
    vi.stubGlobal("fetch", fetch);
    render(<App />);
    fireEvent.click(
      await screen.findByRole("button", { name: t("intakeOpenSaved") }),
    );
    expect(await screen.findByLabelText(t("abstractText"))).toHaveValue(
      saved.preview.text.replace(/\r\n/g, "\n"),
    );
    expect(screen.getByLabelText(t("abstractChooseFile"))).toHaveValue(
      saved.artifact.id,
    );
    expect(screen.queryByText(/undefined/)).not.toBeInTheDocument();
    expect(
      fetch.mock.calls.filter((c) =>
        String(c[0]).includes(`/source-text/${key}`),
      ),
    ).toHaveLength(1);
    expect(
      fetch.mock.calls.some(
        (c) => c[1]?.method === "POST" || String(c[0]).endsWith("/run"),
      ),
    ).toBe(false);
  },
);
it("actual profile3 task review shows only selected passage and returns exact record without Run", () => {
  const back = vi.fn();
  render(
    <AbstractDraftReview
      task={fixture.prepared.task as unknown as Task}
      t={t}
      onReturnToSource={back}
    />,
  );
  expect(screen.getByText("Selected 😀 abstract passage.")).toBeVisible();
  expect(screen.queryByText(/PREFIX NOT SELECTED/)).not.toBeInTheDocument();
  fireEvent.click(
    screen.getByRole("button", { name: t("abstractReturnSource") }),
  );
  expect(back).toHaveBeenCalledWith(saved.record.id);
  expect(document.querySelector('a[href^="hub-source:"]')).toBeNull();
});
it("parked BLOB identity survives reload and late exact result cannot take newer navigation", async () => {
  const identity = {
    version: 1,
    workspace_instance_id: namespace,
    project_id: project,
    key,
    state: "pending",
  };
  localStorage.setItem(prefix + key, JSON.stringify(identity));
  let found = false;
  const fetch = vi.fn(
    async (input: RequestInfo | URL, options?: RequestInit) => {
      if (options?.method === "POST") throw Error("No replay or Run");
      const url = String(input);
      if (url.endsWith("/workspace"))
        return response({
          ...fixture.workspace,
          projects: [fixture.before_prepare.project],
        });
      if (url.includes(`/source-text/${key}`))
        return response(
          found
            ? fixture.lookup
            : { ok: true, intake: { version: 1, key, state: "not_observed" } },
        );
      return response({
        ...fixture.before_prepare,
        records: [],
        artifacts: [],
        tasks: [],
      });
    },
  );
  vi.stubGlobal("fetch", fetch);
  const first = render(<App />);
  await screen.findByText(t("intakeNotObserved"));
  fireEvent.click(screen.getByText(t("recoveryPark")));
  fireEvent.click(screen.getByText(t("recoveryParkConfirm")));
  expect(JSON.parse(localStorage.getItem(prefix + key)!)).toEqual(identity);
  first.unmount();
  render(<App />);
  await screen.findByText(t("recoverySeparate"));
  fireEvent.click(screen.getByText(t("recoverySeparate")));
  fireEvent.change(screen.getByLabelText(t("intakeTitle")), {
    target: { value: "New independent reading intent" },
  });
  fireEvent.click(screen.getByRole("link", { name: "Manuscript" }));
  expect(JSON.parse(localStorage.getItem(prefix + key)!)).toEqual(identity);
  found = true;
  fireEvent.click(screen.getByText(t("intakeCheck")));
  await screen.findByText(t("intakeOpenSaved"));
  expect(location.hash).toBe("#manuscript");
  expect(screen.getByLabelText(t("intakeTitle"))).toHaveValue(
    "New independent reading intent",
  );
  // Exact found record is now merged; only resolved pending identity may clear.
  expect(localStorage.getItem(prefix + key)).toBeNull();
  expect(
    fetch.mock.calls.some(
      (c) => c[1]?.method === "POST" || String(c[0]).endsWith("/run"),
    ),
  ).toBe(false);
});
