import { StrictMode } from "react";
import {
  act,
  render,
  screen,
  fireEvent,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { AbstractDraftComposer, type TextPreview } from "./AbstractDraft";
import {
  ComposerSessions,
  emptyComposer,
  MAX_COMPOSER_SESSIONS,
} from "./composerSession";
import { translator } from "./i18n";
import type { Artifact, Workspace } from "./types";
const t = translator("en");
const artifact: Artifact = {
  id: "file-a",
  path: "synthetic.txt",
  role: "evidence",
  sha256: "a".repeat(64),
  current: true,
};
const preview: TextPreview = {
  artifact_id: artifact.id,
  path: artifact.path,
  sha256: artifact.sha256,
  text: "BOM\ufeff\r\n😀 synthetic abstract",
  codepoint_length: 26,
  bytes_read: 32,
  truncated: false,
};
const source = {
  id: "source-a",
  kind: "source",
  data: { title: "Same title" },
};
const response = (value: unknown) =>
  new Response(JSON.stringify(value), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
const task = {
  id: "exact-task-a",
  operation: "paper-abstract-draft",
  mode: "connected",
  status: "ready",
};
const key = JSON.stringify(["legacy:1", "project-a", source.id]);
function props(sessions: ComposerSessions) {
  return {
    sessions,
    sessionKey: key,
    projectId: "project-a",
    source,
    artifacts: [artifact],
    initialArtifactId: artifact.id,
    initialPreview: preview,
    capability: { status: "unavailable", message: "Synthetic" },
    t,
    onPrepared: vi.fn(async () => {}),
    onCancel: vi.fn(),
    onReview: vi.fn(),
  };
}
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  localStorage.clear();
});
async function draft() {
  const user = userEvent.setup();
  await user.click(
    screen.getByRole("button", { name: t("abstractSelectEntire") }),
  );
  await user.type(screen.getByLabelText(t("abstractPurpose")), "Preserve A");
  return user;
}
it.each(["found", "lost"])(
  "settles a %s keyless response after unmount, preserving lock without callback or replay",
  async (outcome) => {
    const sessions = new ComposerSessions(),
      p = props(sessions);
    let resolve!: (value: Response) => void, reject!: (error: unknown) => void;
    const fetch = vi.fn(
      () =>
        new Promise<Response>((yes, no) => {
          resolve = yes;
          reject = no;
        }),
    );
    vi.stubGlobal("fetch", fetch);
    const view = render(<AbstractDraftComposer {...p} />);
    const user = await draft();
    await user.click(
      screen.getByRole("button", { name: t("abstractPrepare") }),
    );
    expect(sessions.acquire(key, emptyComposer())!.get().creating).toBe(true);
    view.unmount();
    // No hidden composer remains; settlement goes to its exact entry, not another project.
    await act(async () => {
      if (outcome === "found") resolve(response({ ok: true, task }));
      else reject(new TypeError("Synthetic lost response"));
    });
    const state = sessions.acquire(key, emptyComposer())!.get();
    expect(state.creating).toBe(false);
    expect(state.instructions).toBe("Preserve A");
    expect(state.preparedTaskId).toBe(outcome === "found" ? task.id : null);
    expect(state.preparationUncertain).toBe(outcome === "lost");
    expect(p.onPrepared).not.toHaveBeenCalled();
    expect(p.onReview).not.toHaveBeenCalled();
    render(<AbstractDraftComposer {...p} restoreVersion={99} />);
    expect(screen.getByLabelText(t("abstractPurpose"))).toHaveValue(
      "Preserve A",
    );
    expect(
      screen.getByRole("button", { name: t("abstractPrepare") }),
    ).toBeDisabled();
    expect(screen.getByLabelText(t("abstractChooseFile"))).toBeDisabled();
    expect(fetch).toHaveBeenCalledTimes(1);
  },
);
it("a remounted sending entry cannot dispatch again and settles into unknown", async () => {
  const sessions = new ComposerSessions(),
    p = props(sessions);
  let reject!: (error: unknown) => void;
  const fetch = vi.fn(
    () =>
      new Promise<Response>((_, no) => {
        reject = no;
      }),
  );
  vi.stubGlobal("fetch", fetch);
  const view = render(<AbstractDraftComposer {...p} />);
  const user = await draft();
  await user.click(screen.getByRole("button", { name: t("abstractPrepare") }));
  view.unmount();
  render(<AbstractDraftComposer {...p} />);
  expect(screen.getByRole("button", { name: t("preparing") })).toBeDisabled();
  await act(async () => {
    reject(new TypeError("Synthetic lost response"));
  });
  expect(screen.getByText(t("abstractPrepareUncertain"))).toBeVisible();
  expect(
    screen.queryByText(t("abstractPreparingLeave")),
  ).not.toBeInTheDocument();
  expect(fetch).toHaveBeenCalledTimes(1);
});
it.each(["unknown", "known", "sending"])(
  "invalidates changed artifact input without clearing the %s safety lock",
  async (phase) => {
    const sessions = new ComposerSessions(),
      p = props(sessions);
    const entry = sessions.acquire(key, {
      ...emptyComposer(),
      artifactId: artifact.id,
      preview,
      range: { start: 0, end: 4 },
      instructions: "Retained",
      preparationUncertain: phase === "unknown",
      preparedTaskId: phase === "known" ? task.id : null,
      creating: phase === "sending",
    })!;
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    render(
      <AbstractDraftComposer
        {...p}
        artifacts={[{ ...artifact, sha256: "b".repeat(64) }]}
      />,
    );
    await waitFor(() => expect(entry.get().preview).toBeNull());
    expect(entry.get().range).toBeNull();
    expect(screen.getByText(t("abstractInputInvalidated"))).toBeVisible();
    expect(entry.get().instructions).toBe("Retained");
    expect(entry.get().preparationUncertain).toBe(phase === "unknown");
    expect(entry.get().creating).toBe(phase === "sending");
    expect(screen.getByLabelText(t("abstractChooseFile"))).toBeDisabled();
    expect(fetch).not.toHaveBeenCalled();
  },
);
it("preserves a hydrated range on reopen but allows explicit unsent discard only", async () => {
  const sessions = new ComposerSessions(),
    p = props(sessions);
  const view = render(<AbstractDraftComposer {...p} restoreVersion={1} />);
  await draft();
  view.unmount();
  render(<AbstractDraftComposer {...p} restoreVersion={20} />);
  expect(
    screen.getByRole("button", { name: t("abstractPrepare") }),
  ).toBeEnabled();
  fireEvent.click(
    screen.getByRole("button", { name: t("abstractDiscardSession") }),
  );
  expect(p.onCancel).toHaveBeenCalledTimes(1);
  expect(sessions.has(key)).toBe(false);
});
it("bounded registry retains all unresolved identities and rejects oversized private input", () => {
  const sessions = new ComposerSessions();
  for (let i = 0; i < MAX_COMPOSER_SESSIONS; i++)
    expect(
      sessions.acquire(String(i), {
        ...emptyComposer(),
        preparationUncertain: true,
      }),
    ).not.toBeNull();
  expect(sessions.acquire("overflow", emptyComposer())).toBeNull();
  expect(sessions.discard("0")).toBe(false);
  const entry = sessions.acquire("0", emptyComposer())!;
  expect(
    entry.update({ preview: { ...preview, text: "😀".repeat(10001) } }),
  ).toBe(false);
  expect(entry.update({ instructions: "x".repeat(20001) })).toBe(false);
  expect(entry.get().preparationUncertain).toBe(true);
  expect(localStorage.length).toBe(0);
});
it("an obsolete operation token cannot overwrite a newer same-source intent", () => {
  const entry = new ComposerSessions().acquire(key, emptyComposer())!;
  entry.update({ operation: 1, creating: true });
  entry.update({ operation: 2, creating: true, instructions: "New A" });
  expect(entry.update({ creating: false, preparedTaskId: "old-A" }, 1)).toBe(
    false,
  );
  expect(entry.get()).toMatchObject({
    operation: 2,
    creating: true,
    preparedTaskId: null,
    instructions: "New A",
  });
});
it("exact namespaces isolate drafts and legacy re-entry cannot alias an earlier workspace session", () => {
  const sessions = new ComposerSessions();
  const workspace = { capabilities: {} } as Workspace;
  const legacy = sessions.scope(workspace);
  const a = sessions.scope({
    capabilities: {
      prepare_reconciliation: {
        version: 1,
        workspace_instance_id: "11111111-1111-4111-8111-111111111111",
      },
    },
  } as Workspace);
  expect(sessions.scope(workspace)).not.toBe(legacy);
  expect(a).toContain("11111111");
  expect(
    sessions.scope({
      capabilities: {
        prepare_reconciliation: {
          version: 2,
          workspace_instance_id: "11111111-1111-4111-8111-111111111111",
        },
      },
    } as Workspace),
  ).toMatch(/^invalid:/);
});

it("StrictMode reopen retains read text/range without an automatic second read", async () => {
  const sessions = new ComposerSessions(),
    p = props(sessions);
  const fetch = vi.fn(async () => response({ ok: true, preview }));
  vi.stubGlobal("fetch", fetch);
  const view = render(
    <StrictMode>
      <AbstractDraftComposer {...p} initialPreview={undefined} />
    </StrictMode>,
  );
  await screen.findByLabelText(t("abstractText"));
  await draft();
  view.unmount();
  render(
    <StrictMode>
      <AbstractDraftComposer
        {...p}
        initialPreview={undefined}
        restoreVersion={12}
      />
    </StrictMode>,
  );
  expect(screen.getByLabelText(t("abstractPurpose"))).toHaveValue("Preserve A");
  expect(
    screen.getByRole("button", { name: t("abstractPrepare") }),
  ).toBeEnabled();
  expect(fetch).toHaveBeenCalledTimes(1);
});
it("capacity refusal is visible and never sends or silently evicts pending drafts", () => {
  const sessions = new ComposerSessions();
  for (let i = 0; i < MAX_COMPOSER_SESSIONS; i++)
    sessions.acquire(String(i), {
      ...emptyComposer(),
      preparationUncertain: true,
    });
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  render(<AbstractDraftComposer {...props(sessions)} />);
  expect(screen.getByText(t("abstractSessionFull"))).toBeVisible();
  expect(screen.getByLabelText(t("abstractChooseFile"))).toBeDisabled();
  expect(fetch).not.toHaveBeenCalled();
});
it("an invalid namespace binding cannot prepare through the legacy fallback", () => {
  const sessions = new ComposerSessions();
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  render(<AbstractDraftComposer {...props(sessions)} sessionKey={undefined} />);
  expect(screen.getByText(t("abstractSessionScopeInvalid"))).toBeVisible();
  expect(screen.getByLabelText(t("abstractChooseFile"))).toBeDisabled();
  expect(fetch).not.toHaveBeenCalled();
});

it("recovery outcomes require exact namespace, project and preparation key, never absence", () => {
  const sessions = new ComposerSessions();
  const entry = sessions.acquire(
    JSON.stringify(["instance:A", "project-A", "source-A"]),
    { ...emptyComposer(), preparationKey: "request-A" },
  )!;
  sessions.settlePreparation("instance:B", "project-A", "request-A", "foreign");
  sessions.settlePreparation("instance:A", "project-B", "request-A", "foreign");
  sessions.settlePreparation("instance:A", "project-A", "request-B", "foreign");
  expect(entry.get()).toMatchObject({
    preparationKey: "request-A",
    preparedTaskId: null,
  });
  sessions.settlePreparation(
    "instance:A",
    "project-A",
    "request-A",
    "exact-task",
  );
  expect(entry.get().preparedTaskId).toBe("exact-task");
  sessions.settlePreparation("instance:A", "project-A", "request-A");
  expect(entry.get()).toMatchObject({
    preparationKey: "request-A",
    preparedTaskId: "exact-task",
  });
});
it("a retained keyed lock cannot be reset by separate intent while its recovery entry is absent", () => {
  const sessions = new ComposerSessions(),
    p = props(sessions);
  const entry = sessions.acquire(key, {
    ...emptyComposer(),
    artifactId: artifact.id,
    preview,
    instructions: "Unresolved exact key",
    preparationKey: "opaque-key",
  })!;
  const view = render(
    <AbstractDraftComposer {...p} separateIntentVersion={1} />,
  );
  view.rerender(<AbstractDraftComposer {...p} separateIntentVersion={2} />);
  expect(entry.get()).toMatchObject({
    preparationKey: "opaque-key",
    instructions: "Unresolved exact key",
  });
  expect(screen.getByLabelText(t("abstractChooseFile"))).toBeDisabled();
});
